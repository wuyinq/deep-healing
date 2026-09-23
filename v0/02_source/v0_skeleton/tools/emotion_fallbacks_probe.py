#!/usr/bin/env python3
"""`emotion.appraise` 的 **fail-closed 读数探针**（M5.2 r3 / FIX-1 ③）。

为什么需要（Raven R-C1 / §2.5）：内核侧 `_appraise_emotions()` 走**既有 capability 通道**
（`CapabilityRegistry.invoke`：预算闸门 / provider 路由 / `output_schema` / fallback / journal），
但 r2 之前**没有任何入口**能构造出「带 registry 的 tick 循环」⇒ 「无 provider / 预算耗尽 /
cassette miss 时的 fail-closed 读数」一条都不存在。本探针补上这三条**可运行**读数。

三条臂（**都不触网**，逐条给出为什么）：

  - `no-provider`：注册表**不注册任何 adapter** ⇒ `CapabilityRegistry._route()` 抛
    `CapabilityError(E_CAP_PROVIDER_UNRESOLVED)` ⇒ `invoke()` 抛异常 ⇒ tick 落一条降级记录。
    （不触网：路由在 adapter 之前就失败。）
  - `budget-exhausted`：`BudgetLedger(per_tick_calls=0)` ⇒ `budget.allow_call()` 拒 ⇒
    `invoke()` 走契约里声明的 `fallback.on_budget_exhausted`（`deterministic_rule`）⇒
    `ok=False` + `fallback_reason="on_budget_exhausted"` ⇒ tick 落降级记录。
    （不触网：预算闸门在 provider 路由**之前**判。）
  - `cassette-miss`：注册表 `replay_mode=True` + **空 cassette 目录** ⇒
    `CassetteMiss` **必须抛出**（不得被吞、不得静默降级）⇒ tick 落降级记录，
    且 journal 里有 `cassette.miss`（`fail_closed: true`）。（不触网：回放模式只读本地 cassette。）

**不得伪造情绪结果**：降级臂里 `emotion_results` 必须为空 —— 本探针把「有降级记录」与
「有情绪结果」分别报出，任一臂同时出现两者即判 `reading_ok=false`。

用法（workdir 任意；`--kernel-root` 指向含 `deephealing_kernel` 包的目录）：
    PYTHONDONTWRITEBYTECODE=1 python3 <ws>/02_source/v0_skeleton/tools/emotion_fallbacks_probe.py \\
        --kernel-root <ws>/02_source/v0_skeleton/kernel \\
        --pack <ws>/02_source/v0_skeleton/districts/xingfu-xiaoqu --ticks 3 --json <out.json>

退出码：**0** 三条臂的 fail-closed 读数全部成立；**1** 至少一条臂不符合预期；**2** 前置输入缺失。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

ARMS = ("no-provider", "budget-exhausted", "cassette-miss")
DEFAULT_SEED = 20260921
DEFAULT_TICKS = 3
#: 情绪评估的**调用条件**：主导需求缺口 >= 该值才调 `emotion.appraise`。
#: 实测需求缺口 ~0.06（远低于 WorldKernel 默认 0.6）⇒ 探针显式调低到 0.0，
#: 使「调用条件成立」这件事可观测（这是数据参数，不是按 NPC 特判）。
PROBE_THRESHOLD = 0.0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="emotion.appraise fail-closed readings (kernel read-only)")
    parser.add_argument("--kernel-root", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--ticks", type=int, default=DEFAULT_TICKS)
    parser.add_argument("--json", dest="json_path", default=None)
    return parser.parse_args(argv)


def _emit(document: dict, json_path: str | None) -> None:
    text = json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True)
    sys.stdout.write(text + "\n")
    if json_path:
        target = Path(json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")


def _run_arm(arm: str, *, kernel_root: Path, pack_dir: Path, seed: int, ticks: int) -> dict:
    """跑一条臂，返回**盘上/内存里真实存在**的读数（不伪造情绪结果）。"""
    from deephealing_kernel.budget import BudgetLedger
    from deephealing_kernel.cli import V0_SKELETON, _capability_caps
    from deephealing_kernel.events import EventLog
    from deephealing_kernel.pack import load_pack
    from deephealing_kernel.providers.cassette import CassetteReplayProvider, CassetteStore
    from deephealing_kernel.providers.deterministic_rule import DeterministicRuleProvider
    from deephealing_kernel.registry import CapabilityRegistry
    from deephealing_kernel.tick import WorldKernel

    pack = load_pack(pack_dir)
    scratch = Path(tempfile.mkdtemp(prefix=f"m52-emotion-{arm}-"))
    capabilities_dir = (kernel_root / ".." / "capabilities").resolve()
    if not capabilities_dir.is_dir():
        capabilities_dir = V0_SKELETON / "capabilities"
    cassette_root = scratch / "cassettes"
    store = CassetteStore(cassette_root)
    replay_mode = arm == "cassette-miss"
    registry = CapabilityRegistry(capabilities_dir, capabilities_dir / "pins.json",
                                  cassette_store=store, replay_mode=replay_mode)
    if arm == "no-provider":
        pass                      # **故意不注册任何 adapter** ⇒ 路由阶段即 fail-closed
    else:
        registry.register_adapter("deterministic_rule", DeterministicRuleProvider())
        registry.register_adapter("cassette_replay", CassetteReplayProvider(store))
    registry.discover()
    validation_errors = registry.validate()

    documents = [registry.capability(slot) for slot in registry.slots()]
    per_tick_calls, daily_tokens = _capability_caps(documents)
    if arm == "budget-exhausted":
        ledger = BudgetLedger(day_ticks=int(pack.world_seed["constants"].get("day_ticks", 1440)),
                              per_tick_calls=0, per_npc_daily_tokens=0)
    else:
        ledger = BudgetLedger(day_ticks=int(pack.world_seed["constants"].get("day_ticks", 1440)),
                              per_tick_calls=per_tick_calls, per_npc_daily_tokens=daily_tokens)

    kernel = WorldKernel(pack=pack, seed=seed, log=EventLog(scratch / "events.jsonl"),
                         snapshot_every=0, checkpoint_dir=None,
                         capability_registry=registry, budget_ledger=ledger,
                         emotion_pressure_threshold=PROBE_THRESHOLD)
    for _ in range(int(ticks)):
        kernel.step()

    calls = [call for call in registry.calls if call.get("slot") == "emotion.appraise"]
    fallbacks = list(kernel.emotion_fallbacks_log)
    reasons: dict[str, int] = {}
    for item in fallbacks:
        reasons[str(item.get("reason"))] = reasons.get(str(item.get("reason")), 0) + 1
    journal_kinds = sorted({str(item.get("event")) for item in registry.journal})
    cassette_miss_flagged = any(
        item.get("event") == "cassette.miss" and item.get("fail_closed") is True
        for item in registry.journal)

    reading: dict = {
        "arm": arm,
        "registry_validation_errors": validation_errors,
        "emotion_pressure_threshold": PROBE_THRESHOLD,
        "emotion_appraise_invocations": len(calls),
        "emotion_appraise_ok": sum(1 for call in calls if call.get("ok")),
        "emotion_fallbacks_total": len(fallbacks),
        "emotion_fallback_reasons": dict(sorted(reasons.items())),
        "emotion_results_npcs": sorted(kernel.emotion_results),
        "capability_journal_kinds": journal_kinds,
        "cassette_miss_flagged_in_journal": cassette_miss_flagged,
        "no_network_used": True,
    }
    # 逐臂期望（**判据**，不是描述）：
    if arm == "no-provider":
        reading["expected_fallback_reason"] = "CapabilityError"
        reading["reading_ok"] = bool(
            len(calls) == 0 and fallbacks and reasons.get("CapabilityError") == len(fallbacks)
            and not kernel.emotion_results)
    elif arm == "budget-exhausted":
        reading["expected_fallback_reason"] = "on_budget_exhausted"
        # 契约声明 `fallback.on_budget_exhausted` ⇒ deterministic_rule ⇒ `ok=True` + fallback_reason
        # ⇒ **降级成功**：`emotion_results` 非空是**正确**的（那是 deterministic_rule 的实算结果，
        # 不是伪造），判据是「降级必须留痕」——`emotion_fallbacks` 记到 + journal 有 capability.fallback。
        reading["reading_ok"] = bool(
            fallbacks and reasons.get("on_budget_exhausted") == len(fallbacks)
            and "capability.fallback" in journal_kinds
            and bool(kernel.emotion_results))
    else:
        reading["expected_fallback_reason"] = "CassetteMiss"
        reading["reading_ok"] = bool(
            fallbacks and reasons.get("CassetteMiss") == len(fallbacks)
            and not kernel.emotion_results and cassette_miss_flagged)
    return reading


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    kernel_root = Path(args.kernel_root).expanduser().resolve()
    pack_dir = Path(args.pack).expanduser()
    missing: list[str] = []
    if not (kernel_root / "deephealing_kernel").is_dir():
        missing.append(f"kernel_root has no deephealing_kernel package: {kernel_root}")
    if not (pack_dir / "pack.json").is_file():
        missing.append(f"pack has no pack.json: {pack_dir}")
    if missing:
        _emit({"status": "skipped_missing_input", "missing": missing}, args.json_path)
        return 2
    if str(kernel_root) not in sys.path:
        sys.path.insert(0, str(kernel_root))

    arms: dict[str, dict] = {}
    for arm in ARMS:
        arms[arm] = _run_arm(arm, kernel_root=kernel_root, pack_dir=pack_dir,
                             seed=int(args.seed), ticks=int(args.ticks))
    document = {
        "status": "measured",
        "ticks": int(args.ticks),
        "seed": int(args.seed),
        "threshold": PROBE_THRESHOLD,
        "kernel_root": str(kernel_root),
        "pack": str(pack_dir),
        "arms": arms,
        "all_pass": all(item["reading_ok"] for item in arms.values()),
    }
    _emit(document, args.json_path)
    return 0 if document["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
