#!/usr/bin/env python3
"""AC-10 行为多样性度量（M5.2 r1 · 自研，设计 §5.5 冻结接口）。

口径（**与 PM 参考件一致**，`01_architecture_design.md` §5.5 / REQ §4）：
  - 每 **5** tick 采样一次位置；到该 NPC「家」（`pack_profiles[npc_id].home_entity`
    的 `transform.pos_mm`）的**水平距离 > 1500mm** 记一次「室外」；
  - 默认 `seed=20260921`、`ticks=1440`。

判据（REQ §4，**逐字不动**，不得为凑绿放宽）：
  - **10-a** 单一 `bt_branch` 占比 <= 60%；
  - **10-b** 单一 `dominant_need` 占比 <= 60%；
  - **10-c** 每个 NPC 的不同 `chosen_action` 数 >= 3；
  - **10-d-1** 全体室外采样占比 >= 20%；
  - **10-d-2** 各自室外占比 >= 20% 的 NPC 数 >= **2**。

**两条臂（M5.2 r3 / FIX-5 · Raven §2.3）**：本工具默认测的是**记忆链关闭**的配置
（`memory_store=None`），这正是**交付门禁口径**（`verify_specs.sh` §15）；`--memory` 打开
**接线臂**（内核 tick 的记忆链，等价 `cli.py --memory-chain`）⇒ 两组读数必须**并列公布**。
接线会改变行为读数（实测 w=0.20：10a 0.3031→0.3810、10d1 0.3250→0.2444）⇒
**不得**把接线臂读数当交付门禁口径，也不得反过来。

**敏感性扫描开关（`--weight` / `--signal-window` / `--min-importance`）**：仅在**本进程内**覆盖
`rules/decision.py` 的模块级常量（不写盘），用于给出「达标是机制还是调参」的敏感性读数。
**这些开关不是门禁**：门禁读数一律用缺省值（w=0.20 / window=3 / min_importance=0.5）。

**10-d-1 / 10-d-2 的边界比较用未舍入值（M5.2 r3 / FIX-10① · Sentinel LOW-1）**：
占比的**判定**读原始浮点（`>= 0.20`），**公布**仍给 4 位小数；两者一并入 JSON
（`*_raw` 字段）⇒ 消除「真值 0.19996 被舍入成 0.2000 后判过」的 1/10000 量级松弛。

输出键（Raven L-4：**禁止**同名键两义）：
  - `pack_npcs` = 内容包 `npcs/*.json` 的文件数；
  - `npcs_in_decisions` = 出现在 `npc.decision` 事件里的**不同** `npc_id` 数。

退出码：**0** = 五条判据全绿；**1** = 判据已评估但至少一条为 ❌；
        **2** = 前置输入缺失（JSON 里 `status=skipped_missing_input`，**不得**当 PASS）。

本工具**只读**被测树：`sys.dont_write_bytecode` 打开，事件日志与记忆库落临时目录。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True

SAMPLE_EVERY = 5
OUTDOOR_THRESHOLD_MM = 1500
DEFAULT_SEED = 20260921
DEFAULT_TICKS = 1440
PASS_EXIT = 0
RED_EXIT = 1
SKIP_EXIT = 2


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AC-10 behaviour-diversity measurement (kernel read-only)",
    )
    parser.add_argument("--kernel-root", required=True,
                        help="directory containing the deephealing_kernel package")
    parser.add_argument("--pack", required=True, help="district pack directory")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--ticks", type=int, default=DEFAULT_TICKS)
    parser.add_argument("--json", dest="json_path", default=None,
                        help="write the same JSON document to this path")
    parser.add_argument("--memory", action="store_true",
                        help="[r3/FIX-5] 接线臂：给内核 tick 传 MemoryStore（等价 `cli.py --memory-chain`）；"
                             "缺省 = **未接线**（= 交付门禁口径）")
    parser.add_argument("--weight", type=float, default=None,
                        help="[敏感性扫描，非门禁] 覆盖 MEMORY_SIGNAL_WEIGHT（缺省 0.20）")
    parser.add_argument("--signal-window", type=int, default=None,
                        help="[敏感性扫描，非门禁] 覆盖 MEMORY_SIGNAL_WINDOW（缺省 3）")
    parser.add_argument("--min-importance", type=float, default=None,
                        help="[敏感性扫描，非门禁] 覆盖 MEMORY_SIGNAL_MIN_IMPORTANCE（缺省 0.5）")
    return parser.parse_args(argv)


def _emit(document: dict, json_path: str | None) -> None:
    text = json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True)
    sys.stdout.write(text + "\n")
    if json_path:
        target = Path(json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")


def _share(counter: Counter, total: int) -> tuple[str | None, float]:
    if not counter or total <= 0:
        return None, 0.0
    label, count = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0]
    return label, round(count / total, 4)


def _scan_pack(pack_dir: Path) -> tuple[int, int]:
    """返回 `(files_scanned, pack_npcs)`：包目录下常规文件总数 / `npcs/*.json` 文件数。"""
    files_scanned = sum(1 for item in sorted(pack_dir.rglob("*")) if item.is_file())
    pack_npcs = sum(1 for item in sorted((pack_dir / "npcs").glob("*.json")) if item.is_file())
    return files_scanned, pack_npcs


def measure(kernel_root: Path, pack_dir: Path, seed: int, ticks: int, *,
            wired: bool = False, weight: float | None = None,
            signal_window: int | None = None, min_importance: float | None = None) -> dict:
    if str(kernel_root) not in sys.path:
        sys.path.insert(0, str(kernel_root))

    from deephealing_kernel.cli import load_pack           # noqa: PLC0415
    from deephealing_kernel.events import EventLog         # noqa: PLC0415
    from deephealing_kernel.rules import decision as decision_mod  # noqa: PLC0415
    from deephealing_kernel.tick import WorldKernel        # noqa: PLC0415

    # 敏感性扫描：**只在进程内**覆盖模块级常量（不写盘；门禁缺省值不受影响）
    overrides: dict[str, object] = {}
    if weight is not None:
        decision_mod.MEMORY_SIGNAL_WEIGHT = float(weight)
        overrides["MEMORY_SIGNAL_WEIGHT"] = float(weight)
    if signal_window is not None:
        decision_mod.MEMORY_SIGNAL_WINDOW = int(signal_window)
        overrides["MEMORY_SIGNAL_WINDOW"] = int(signal_window)
    if min_importance is not None:
        decision_mod.MEMORY_SIGNAL_MIN_IMPORTANCE = float(min_importance)
        overrides["MEMORY_SIGNAL_MIN_IMPORTANCE"] = float(min_importance)

    pack = load_pack(pack_dir)
    scratch = Path(tempfile.mkdtemp(prefix="m52-ac10-"))
    log_path = scratch / "events.jsonl"
    kernel_extra: dict = {}
    if wired:
        from deephealing_kernel.memory.store import MemoryStore    # noqa: PLC0415
        store = MemoryStore(scratch / "kernel_memory.sqlite", write_enabled=True)
        store.init_schema()
        kernel_extra["memory_store"] = store
    kernel = WorldKernel(pack=pack, seed=seed, log=EventLog(log_path),
                         snapshot_every=0, checkpoint_dir=None, **kernel_extra)

    outdoor: Counter = Counter()
    samples: Counter = Counter()
    for tick in range(1, int(ticks) + 1):
        kernel.step()
        if tick % SAMPLE_EVERY:
            continue
        for entity in kernel.world.query(kind="npc"):
            samples[entity.id] += 1
            home_id = (kernel.pack_profiles.get(entity.id) or {}).get("home_entity")
            home = kernel.world.get(home_id) if isinstance(home_id, str) and home_id else None
            if home is None:
                continue
            here = (entity.components.get("transform") or {}).get("pos_mm") or {}
            there = (home.components.get("transform") or {}).get("pos_mm") or {}
            distance = math.hypot(
                int(here.get("x", 0)) - int(there.get("x", 0)),
                int(here.get("z", 0)) - int(there.get("z", 0)),
            )
            if distance > OUTDOOR_THRESHOLD_MM:
                outdoor[entity.id] += 1

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    decisions = [event["payload"] for event in events if event.get("type") == "npc.decision"]
    total_decisions = len(decisions)

    branch_counter = Counter(str(item.get("bt_branch")) for item in decisions)
    need_counter = Counter(str(item.get("dominant_need")) for item in decisions)

    npc_ids = sorted({str(item.get("npc_id")) for item in decisions})
    per_npc_actions: dict[str, int] = {}
    for npc_id in npc_ids:
        per_npc_actions[npc_id] = len({str(item.get("chosen_action")) for item in decisions
                                       if str(item.get("npc_id")) == npc_id})
    min_actions = min(per_npc_actions.values()) if per_npc_actions else 0

    per_npc_outdoor: dict[str, float] = {}
    per_npc_outdoor_raw: dict[str, float] = {}
    for npc_id in sorted(samples):
        raw = outdoor.get(npc_id, 0) / max(1, samples[npc_id])
        per_npc_outdoor_raw[npc_id] = raw
        per_npc_outdoor[npc_id] = round(raw, 4)
    # **FIX-10①**：边界判定读**未舍入**值（真值 0.19996 不再被舍入成 0.2000 判过）
    above = sorted(npc_id for npc_id, share in per_npc_outdoor_raw.items() if share >= 0.20)

    outdoor_total = sum(outdoor.values())
    sample_total = sum(samples.values())
    outdoor_share_raw = outdoor_total / max(1, sample_total)
    outdoor_share = round(outdoor_share_raw, 4)

    top_branch, branch_share = _share(branch_counter, total_decisions)
    top_need, need_share = _share(need_counter, total_decisions)

    files_scanned, pack_npcs = _scan_pack(pack_dir)
    scope_consistent = bool(
        pack_npcs >= 1
        and files_scanned >= pack_npcs
        and len(npc_ids) <= pack_npcs
        and sample_total > 0
    )

    document = {
        "ticks": int(ticks),
        "seed": int(seed),
        "sample_every": SAMPLE_EVERY,
        "outdoor_threshold_mm": OUTDOOR_THRESHOLD_MM,
        "pack_npcs": pack_npcs,
        "npcs_in_decisions": len(npc_ids),
        "decisions": total_decisions,
        "10a_top_branch": top_branch,
        "10a_share": branch_share,
        "10a_pass": bool(total_decisions > 0 and branch_share <= 0.60),
        "10b_top_need": top_need,
        "10b_share": need_share,
        "10b_pass": bool(total_decisions > 0 and need_share <= 0.60),
        "10c_min_actions_per_npc": min_actions,
        "10c_pass": bool(min_actions >= 3),
        "10d1_outdoor_share": outdoor_share,
        "10d1_outdoor_share_raw": outdoor_share_raw,
        "10d1_pass": bool(outdoor_share_raw >= 0.20),
        "10d2_npcs_at_or_above_20pct": len(above),
        "10d2_npcs": above,
        "10d2_pass": bool(len(above) >= 2),
        "per_npc_outdoor": per_npc_outdoor,
        "per_npc_outdoor_raw": per_npc_outdoor_raw,
        "boundary_rule": "10d1/10d2 compare UNROUNDED shares (FIX-10①); rounded values are display only",
        "arm": "wired" if wired else "unwired",
        "memory_signal": {
            "MEMORY_SIGNAL_WEIGHT": decision_mod.MEMORY_SIGNAL_WEIGHT,
            "MEMORY_SIGNAL_WINDOW": decision_mod.MEMORY_SIGNAL_WINDOW,
            "MEMORY_SIGNAL_MIN_IMPORTANCE": decision_mod.MEMORY_SIGNAL_MIN_IMPORTANCE,
            "overrides": overrides,
        },
        "per_npc_actions": per_npc_actions,
        "branches": dict(sorted(branch_counter.items())),
        "needs": dict(sorted(need_counter.items())),
        "actions": dict(sorted(Counter(str(item.get("chosen_action")) for item in decisions).items())),
        "scope": {
            "kernel_root": str(kernel_root.resolve()),
            "pack": str(pack_dir.resolve()),
            "files_scanned": files_scanned,
            "pack_npcs": pack_npcs,
            "npcs_in_decisions": len(npc_ids),
            "samples_total": sample_total,
            "consistent": scope_consistent,
        },
    }
    document["all_pass"] = bool(
        document["10a_pass"] and document["10b_pass"] and document["10c_pass"]
        and document["10d1_pass"] and document["10d2_pass"] and scope_consistent
    )
    return document


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    kernel_root = Path(args.kernel_root).expanduser()
    pack_dir = Path(args.pack).expanduser()
    missing: list[str] = []
    if not (kernel_root / "deephealing_kernel").is_dir():
        missing.append(f"kernel_root has no deephealing_kernel package: {kernel_root}")
    if not (pack_dir / "pack.json").is_file():
        missing.append(f"pack has no pack.json: {pack_dir}")
    if missing:
        _emit({"status": "skipped_missing_input", "missing": missing,
               "scope": {"kernel_root": str(kernel_root), "pack": str(pack_dir)}},
              args.json_path)
        return SKIP_EXIT

    document = measure(kernel_root, pack_dir, int(args.seed), int(args.ticks),
                       wired=bool(args.memory), weight=args.weight,
                       signal_window=args.signal_window, min_importance=args.min_importance)
    document["status"] = "measured"
    _emit(document, args.json_path)
    return PASS_EXIT if document["all_pass"] else RED_EXIT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
