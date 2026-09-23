#!/usr/bin/env python3
"""AC-4 对照场景（M5.2 r1 · 设计 §7.1 AC-4 行 / Raven M-14 / M-15）。

**唯一变量 = 是否注入「关键经历事件」**；其余全部相同（同人物、同初始状态、同 seed、同内容包）。

三条对照臂（Raven M-14 硬性）：
  - **A** 无经历 · 短 tick（`short_ticks`）；
  - **B** 无经历 · 长 tick（`ticks`，与 C 同 tick 数）；
  - **C** 有经历 · 与 B **同 tick 数**，唯一差异 = 库里预置一条关键经历（`kind=<注入动作>`，importance 高）。

三条臂的内核记忆写入**一律关闭**（`write_enabled=False`）⇒ 库内容完全由「是否注入」决定，
tick 循环不会自行制造经历（否则 C 的经历会被自产记录挤出窗口，注入就不成立了）。

**注入对象的选择规则（显式、可复核，不是事后挑数）**：先用臂 B 跑一遍，统计每个 NPC
「注入动作出现在 `utility_ranking` 前 3 **但不是第 1**」的决策次数 —— 这是「一条经历**有机会**
改变选择」的必要条件；取计数最大者（并列取 `npc_id` 最小者）。该统计一并公布在
`target_selection` 段。**若计数全为 0 ⇒ 本场景在结构上无法观测经历效应，如实报 GAP。**

「被治愈」的**可观察量**（M-14：不得写成恒真式）：
  ① **决策分布向单一分支的收敛程度** `branch_convergence` = 后 1/4 的 top branch 占比 − 前 1/4；
  ② `top_branch_share`（是否塌成单一分支）；
  ③ `relations` 轨迹（末态）；④ 需求压力趋势（**辅助读数**，不参与判据）。

判据（`criteria` 段，全部为真才 `pass`）：
  - `tick_count_is_not_the_cause`：A 与 B 在**同一时间窗**（前 `short_ticks`）内的 `npc.action`
    序列**逐字节相同** ⇒ 同 seed 下「多跑 tick」不改变该窗内轨迹，差异只可能来自经历；
  - `experience_effect`：C 在该窗内与 B **不同**，且差异**能被事件解释**
    （「关键经历 → 记忆 ref → 哪次决策 → 哪个可观察行动」的链）；
  - `experience_effect_exceeds_tick_effect`：窗口内 `|C − B| > 0` 而 `|A − B| == 0`
    （tick 数在窗口内的贡献恰为 0 ⇒ 经历效应严格更大）；
  - `no_spontaneous_healing`：**无经历**臂 B **没有**「被治愈」——top branch 占比不塌成单一分支
    （`<= 0.60`）且无收敛趋势（`|branch_convergence| <= 0.05`）。

退出码：**0** 全部判据为真；**1** 有判据为假；**2** 前置输入缺失（`status=skipped_missing_input`）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True

DEFAULT_SEED = 20260921
DEFAULT_TICKS = 480
DEFAULT_SHORT_TICKS = 120
SAMPLE_EVERY = 5
OUTDOOR_THRESHOLD_MM = 1500
TOP_BRANCH_CEILING = 0.60
CONVERGENCE_TOLERANCE = 0.05
INJECT_KIND = "walk"
INJECT_IMPORTANCE = 0.95


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AC-4 contrast scenario (injected key experience)")
    parser.add_argument("--kernel-root", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--ticks", type=int, default=DEFAULT_TICKS)
    parser.add_argument("--short-ticks", type=int, default=DEFAULT_SHORT_TICKS)
    parser.add_argument("--json", dest="json_path", default=None)
    return parser.parse_args(argv)


def _q(value: float) -> float:
    return round(float(value), 6)


def _digest(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _run_arm(pack_dir: Path, seed: int, ticks: int, *, inject_for: str | None,
             scratch: Path, name: str) -> dict:
    from deephealing_kernel.events import EventLog
    from deephealing_kernel.memory.store import MemoryStore
    from deephealing_kernel.pack import load_pack
    from deephealing_kernel.tick import WorldKernel

    db_path = scratch / f"{name}.sqlite"
    if inject_for:
        seeder = MemoryStore(db_path)                       # 预置关键经历（本工具唯一一次写入）
        seeder.init_schema()
        seeder.append_episode(inject_for, 0, INJECT_KIND,
                              f"injected:key-experience:{INJECT_KIND}", INJECT_IMPORTANCE,
                              ["injected:key-experience"])
    reader = MemoryStore(db_path, write_enabled=False)       # 内核侧只读：不自行制造经历
    reader.init_schema()

    log_path = scratch / f"{name}.jsonl"
    kernel = WorldKernel(pack=load_pack(pack_dir), seed=seed, log=EventLog(log_path),
                         snapshot_every=0, checkpoint_dir=None, memory_store=reader)

    outdoor = Counter()
    samples = Counter()
    window_outdoor = Counter()
    window_samples = Counter()
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
            distance = math.hypot(int(here.get("x", 0)) - int(there.get("x", 0)),
                                  int(here.get("z", 0)) - int(there.get("z", 0)))
            if distance > OUTDOOR_THRESHOLD_MM:
                outdoor[entity.id] += 1
                if tick <= _SHORT_TICKS[0]:
                    window_outdoor[entity.id] += 1
            if tick <= _SHORT_TICKS[0]:
                window_samples[entity.id] += 1

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    decisions = [event for event in events if event["type"] == "npc.decision"]
    actions = [{"tick": int(event["tick"]), "npc_id": event["actor"],
                "action": event["payload"].get("action"),
                "target_entity": event["payload"].get("target_entity")}
               for event in events if event["type"] == "npc.action"]

    window_actions = [item for item in actions if item["tick"] <= _SHORT_TICKS[0]]

    def top_share(items):
        if not items:
            return 0.0
        return _q(Counter(items).most_common(1)[0][1] / len(items))

    def mean(items):
        return _q(sum(items) / len(items)) if items else 0.0

    branch_by_quarter: list[list[str]] = [[], [], [], []]
    deficit_by_quarter: list[list[float]] = [[], [], [], []]
    for event in decisions:
        quarter = min(3, (int(event["tick"]) - 1) * 4 // max(1, int(ticks)))
        branch_by_quarter[quarter].append(str(event["payload"].get("bt_branch")))
        deficit = event["payload"].get("dominant_deficit")
        deficit_by_quarter[quarter].append(float(deficit) if isinstance(deficit, (int, float)) else 0.0)

    action_counter = Counter(item["action"] for item in actions)
    window_counter = Counter(item["action"] for item in window_actions)
    total_actions = max(1, sum(action_counter.values()))
    window_total = max(1, sum(window_counter.values()))
    return {
        "name": name,
        "ticks": int(ticks),
        "injected_for": inject_for,
        "actions": actions,
        "window_actions": window_actions,
        "action_histogram": dict(sorted(action_counter.items())),
        "window_action_histogram": dict(sorted(window_counter.items())),
        "branch_histogram": dict(sorted(Counter(str(event["payload"].get("bt_branch"))
                                                for event in decisions).items())),
        "walk_share": _q(action_counter.get(INJECT_KIND, 0) / total_actions),
        "window_walk_share": _q(window_counter.get(INJECT_KIND, 0) / window_total),
        "outdoor_share": _q(sum(outdoor.values()) / max(1, sum(samples.values()))),
        "window_outdoor_share": _q(sum(window_outdoor.values()) / max(1, sum(window_samples.values()))),
        "top_branch_share": top_share([str(event["payload"].get("bt_branch")) for event in decisions]),
        "branch_convergence": _q(top_share(branch_by_quarter[3]) - top_share(branch_by_quarter[0])),
        "needs_pressure_first_quarter": mean(deficit_by_quarter[0]),
        "needs_pressure_last_quarter": mean(deficit_by_quarter[3]),
        "needs_trend": _q(mean(deficit_by_quarter[3]) - mean(deficit_by_quarter[0])),
        "relations_final": {entity.id: dict(sorted((entity.components.get("relations") or {}).items()))
                            for entity in kernel.world.query(kind="npc")},
        "state_hash": kernel.state_hash(),
        "memory_read_decisions": sum(1 for event in decisions
                                     if (event["payload"].get("memory_influence") or {}).get("signals")),
        "event_digest": _digest(events),
        "decisions": decisions,
    }


_SHORT_TICKS = [DEFAULT_SHORT_TICKS]


def _sequence(arm: dict, *, window: bool = False) -> list[tuple]:
    items = arm["window_actions"] if window else arm["actions"]
    return [(item["tick"], item["npc_id"], item["action"], item["target_entity"]) for item in items]


def _explain(divergence: tuple | None, arm_c: dict, arm_b: dict) -> dict | None:
    """「关键经历 → 记忆 ref → 哪次决策 → 哪个可观察行动」的可复核链。"""
    if divergence is None:
        return None
    tick, npc_id, action, target = divergence
    decision = next((event for event in arm_c["decisions"]
                     if int(event["tick"]) == int(tick) and event["payload"].get("npc_id") == npc_id), None)
    if decision is None:
        return None
    influence = decision["payload"].get("memory_influence") or {}
    counterpart = next((item for item in _sequence(arm_b, window=True)
                        if item[0] == tick and item[1] == npc_id), None)
    return {
        "tick": int(tick),
        "npc_id": npc_id,
        "key_experience": {"npc_id": arm_c["injected_for"], "kind": INJECT_KIND,
                           "importance": INJECT_IMPORTANCE},
        "memory_ref_chain": influence.get("signals"),
        "utility_delta": influence.get("utility_delta"),
        "by_action": influence.get("by_action"),
        "decision": {"chosen_action": decision["payload"].get("chosen_action"),
                     "bt_branch": decision["payload"].get("bt_branch"),
                     "dominant_need": decision["payload"].get("dominant_need"),
                     "utility_ranking": decision["payload"].get("utility_ranking")},
        "observable_action": {
            "with_experience": {"action": action, "target_entity": target},
            "without_experience": {"action": counterpart[2], "target_entity": counterpart[3]}
            if counterpart else None,
        },
    }


def _select_target(arm_b: dict) -> tuple[str | None, dict]:
    """注入对象的选择规则（显式）：注入动作进入 `utility_ranking` 前 3 **但不是第 1** 的次数最多者。"""
    counts: dict[str, int] = {}
    for event in arm_b["decisions"]:
        ranking = event["payload"].get("utility_ranking") or []
        if not ranking:
            continue
        if ranking[0].get("action") == INJECT_KIND:
            continue
        if any(item.get("action") == INJECT_KIND for item in ranking):
            npc_id = str(event["payload"].get("npc_id"))
            counts[npc_id] = counts.get(npc_id, 0) + 1
    if not counts or max(counts.values()) == 0:
        return None, {"counts": counts, "rule": "max(count of decisions where injected action is a "
                                                "top-3 runner-up); tie -> smallest npc_id"}
    target = sorted(counts, key=lambda key: (-counts[key], key))[0]
    return target, {"counts": dict(sorted(counts.items())),
                    "rule": "max(count of decisions where injected action is a top-3 runner-up); "
                            "tie -> smallest npc_id", "selected": target}


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    kernel_root = Path(args.kernel_root).expanduser()
    pack_dir = Path(args.pack).expanduser()
    missing = []
    if not (kernel_root / "deephealing_kernel").is_dir():
        missing.append(f"kernel_root has no deephealing_kernel package: {kernel_root}")
    if not (pack_dir / "pack.json").is_file():
        missing.append(f"pack has no pack.json: {pack_dir}")
    if missing:
        _emit({"status": "skipped_missing_input", "missing": missing}, args.json_path)
        return 2

    sys.path.insert(0, str(kernel_root))
    _SHORT_TICKS[0] = int(args.short_ticks)
    scratch = Path(tempfile.mkdtemp(prefix="m52-contrast-"))
    arm_a = _run_arm(pack_dir, args.seed, args.short_ticks, inject_for=None, scratch=scratch,
                     name="A_no_experience_short")
    arm_b = _run_arm(pack_dir, args.seed, args.ticks, inject_for=None, scratch=scratch,
                     name="B_no_experience_long")
    target, selection = _select_target(arm_b)
    if target is None:
        _emit({"status": "skipped_no_observable_target", "target_selection": selection,
               "arms": {"B_no_experience_long": _strip(arm_b)}}, args.json_path)
        return 1
    arm_c = _run_arm(pack_dir, args.seed, args.ticks, inject_for=target, scratch=scratch,
                     name="C_with_experience")

    seq_a = _sequence(arm_a, window=True)
    seq_b_window = _sequence(arm_b, window=True)
    seq_c_window = _sequence(arm_c, window=True)
    divergence = next((item for item, other in zip(seq_c_window, seq_b_window) if item != other), None)

    window_gap_cb = _q(abs(arm_c["window_walk_share"] - arm_b["window_walk_share"]))
    window_gap_ab = _q(abs(arm_a["window_walk_share"] - arm_b["window_walk_share"]))

    criteria = {
        "tick_count_is_not_the_cause": {
            "pass": seq_a == seq_b_window,
            "reading": {"window_actions_A": len(seq_a), "window_actions_B": len(seq_b_window),
                        "window_prefix_identical": seq_a == seq_b_window,
                        "window": int(args.short_ticks)},
        },
        "experience_effect": {
            "pass": bool(divergence is not None),
            "reading": {"first_divergence_tick_in_window": divergence[0] if divergence else None,
                        "window_walk_share_C": arm_c["window_walk_share"],
                        "window_walk_share_B": arm_b["window_walk_share"]},
        },
        "experience_effect_exceeds_tick_effect": {
            "pass": bool(window_gap_cb > 0.0 and window_gap_ab == 0.0),
            "reading": {"window_walk_gap_C_vs_B": window_gap_cb,
                        "window_walk_gap_A_vs_B": window_gap_ab,
                        "window_outdoor_gap_C_vs_B": _q(abs(arm_c["window_outdoor_share"]
                                                            - arm_b["window_outdoor_share"])),
                        "window_outdoor_gap_A_vs_B": _q(abs(arm_a["window_outdoor_share"]
                                                            - arm_b["window_outdoor_share"]))},
        },
        "no_spontaneous_healing": {
            "pass": bool(arm_b["top_branch_share"] <= TOP_BRANCH_CEILING
                         and abs(arm_b["branch_convergence"]) <= CONVERGENCE_TOLERANCE),
            "reading": {"top_branch_share_B": arm_b["top_branch_share"], "ceiling": TOP_BRANCH_CEILING,
                        "branch_convergence_B": arm_b["branch_convergence"],
                        "convergence_tolerance": CONVERGENCE_TOLERANCE,
                        "branch_convergence_C": arm_c["branch_convergence"],
                        "needs_trend_B_aux": arm_b["needs_trend"],
                        "needs_trend_C_aux": arm_c["needs_trend"]},
        },
    }
    explanation = _explain(divergence, arm_c, arm_b)
    document = {
        "status": "measured",
        "seed": int(args.seed), "ticks": int(args.ticks), "short_ticks": int(args.short_ticks),
        "sample_every": SAMPLE_EVERY, "outdoor_threshold_mm": OUTDOOR_THRESHOLD_MM,
        "injected_kind": INJECT_KIND, "injected_importance": INJECT_IMPORTANCE,
        "target_selection": selection,
        "arms": {"A_no_experience_short": _strip(arm_a), "B_no_experience_long": _strip(arm_b),
                 "C_with_experience": _strip(arm_c)},
        "explanation_chain": explanation,
        "criteria": criteria,
        "all_pass": all(item["pass"] for item in criteria.values()) and explanation is not None,
        "scope": {"kernel_root": str(kernel_root.resolve()), "pack": str(pack_dir.resolve())},
    }
    _emit(document, args.json_path)
    return 0 if document["all_pass"] else 1


def _strip(arm: dict) -> dict:
    return {key: value for key, value in arm.items()
            if key not in ("actions", "window_actions", "decisions")}


def _emit(document: dict, json_path: str | None) -> None:
    text = json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True)
    sys.stdout.write(text + "\n")
    if json_path:
        target = Path(json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
