#!/usr/bin/env python3
"""认知层**参与度**探测器（M5.2 r3 / §3.3 ①③ —— **不是门禁**）。

背景（Raven §2.4 · B-9 上抛项）：C1（`rest` 同时缓解 `safety`）让需求压力长期停在 ~0.06，
而 `COGNITION_TREE_SPEC` 第一条 `sequence` 的门是 `needs_pressure >= 0.30`
⇒ **长跑里认知树退化为「只调 `emotion.appraise`」**（实测 60 tick：改前树 15 次调用
`intent.plan` / `emotion.appraise` / `relation.infer` 各 5，交付树只剩 `emotion.appraise` 5 次）。
改门限会改**冻结**的 `COGNITION_TREE_SPEC` 语义 ⇒ 属设计决策（已上抛 PM，B-9）⇒
本轮**只提供可观测性**：本工具让「能力层是否参与」这件事**可复算**。

**它明确不是门禁**：不进 `verify_specs.sh`，不产生 PASS/FAIL 判据，退出码只表示
「探针自身能否完成测量」（0 = 测到；2 = 前置输入缺失）。把它读成判据 = 越界。

用法（workdir 任意；`--kernel-root` 指向含 `deephealing_kernel` 包的目录）：
    PYTHONDONTWRITEBYTECODE=1 python3 <ws>/02_source/v0_skeleton/tools/cognition_participation_probe.py \\
        --kernel-root <ws>/02_source/v0_skeleton/kernel \\
        --pack <ws>/02_source/v0_skeleton/districts/xingfu-xiaoqu --ticks 60 --json <out.json>

**对照树**：同一命令把 `--kernel-root` 指向 `/tmp/m52-ref/02_source/v0_skeleton/kernel`
（r1 配方的改前树）即得「改前 vs 交付」对照读数。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True

DEFAULT_SEED = 20260921
DEFAULT_TICKS = 60
EXIT_MEASURED, EXIT_SKIP = 0, 2


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="cognition participation probe (NOT a gate: no PASS/FAIL criterion; "
                    "exit code only reports whether the measurement completed)")
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
        return EXIT_SKIP
    if str(kernel_root) not in sys.path:
        sys.path.insert(0, str(kernel_root))

    from deephealing_kernel.cli import _run_cognition          # noqa: PLC0415
    from deephealing_kernel.events import EventLog             # noqa: PLC0415
    from deephealing_kernel.pack import load_pack              # noqa: PLC0415
    from deephealing_kernel.tick import WorldKernel            # noqa: PLC0415

    pack = load_pack(pack_dir)
    scratch = Path(tempfile.mkdtemp(prefix="m52-cognition-probe-"))
    kernel = WorldKernel(pack=pack, seed=int(args.seed), log=EventLog(scratch / "events.jsonl"),
                         snapshot_every=0, checkpoint_dir=None)
    for _ in range(int(args.ticks)):
        kernel.step()

    report = _run_cognition(pack, kernel, out_dir=scratch, replay_mode=False, memory_writes=False)
    journal_path = Path(report["artifacts"]["journal"])
    records = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()
               if line.strip()]

    calls_by_slot: Counter = Counter()
    for record in records:
        if record.get("event") == "capability.call":
            calls_by_slot[str(record.get("slot"))] += 1
    cycles = [record for record in records if record.get("event") == "cognition.cycle"]
    statuses = Counter(str(record.get("tree_status")) for record in cycles)
    deficits = [float((record.get("top_requirement") or {}).get("deficit") or 0.0) for record in cycles]

    document = {
        "status": "measured",
        "gate": False,
        "note": ("探测器，非门禁：用于观测「认知树长跑是否退化为只调 emotion.appraise」"
                 "（Raven §2.4 / PM 上抛项 B-9）。本工具不参与任何 PASS/FAIL 判定。"),
        "kernel_root": str(kernel_root),
        "pack": str(pack_dir),
        "seed": int(args.seed),
        "ticks": int(args.ticks),
        "capability_calls_total": sum(calls_by_slot.values()),
        "capability_calls_by_slot": dict(sorted(calls_by_slot.items())),
        "distinct_slots_called": sorted(calls_by_slot),
        "cycles": len(cycles),
        "tree_status_counts": dict(sorted(statuses.items())),
        "top_deficit_last_cycle": deficits[-1] if deficits else None,
        "top_deficit_max": max(deficits) if deficits else None,
        # **口径提醒**：`top_requirement.deficit`（主导需求缺口）**不是**树门所用的 `needs_pressure`
        # —— 后者是 `utility.need_pressure(needs, {})` 的聚合量，journal 未导出 ⇒ 本工具不比较两者，
        # 只用「哪些 slot 真的被调用」这一条**可复算**的事实判定参与度。
        "pressure_note": ("tree gate is on needs_pressure (>= 0.30) which the journal does not export; "
                          "participation is judged from capability.call slots only"),
        "degraded_to_emotion_only": bool(calls_by_slot) and set(calls_by_slot) == {"emotion.appraise"},
        "artifacts": report["artifacts"],
    }
    _emit(document, args.json_path)
    return EXIT_MEASURED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
