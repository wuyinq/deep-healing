#!/usr/bin/env python3
"""M4 自主决策真跑读数（spike；AC-M4-8 ①②③④）。

运行：PYTHONDONTWRITEBYTECODE=1 python3 spikes/s15-autonomy/decision_evidence.py
产物：`spikes/s15-autonomy/logs/*.json`（原始读数；判定在 `03` / `V0_SELF_TEST.md` 里引用）。

**本脚本不是交付面**（`spikes/**`）；它只调用交付实现（`rules/decision.py` 等），不复制实现。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
KERNEL = WORKSPACE / "02_source" / "v0_skeleton" / "kernel"
PACK = WORKSPACE / "02_source" / "v0_skeleton" / "districts" / "xingfu-xiaoqu"
LOGS = HERE / "logs"
RUNTIME = HERE / "runtime"
LOGS.mkdir(parents=True, exist_ok=True)
RUNTIME.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(KERNEL))

from deephealing_kernel import tick as tick_mod  # noqa: E402
from deephealing_kernel.events import EventLog  # noqa: E402
from deephealing_kernel.pack import load_pack  # noqa: E402
from deephealing_kernel.rules import decision as decision_mod  # noqa: E402
from deephealing_kernel.rules import utility as utility_mod  # noqa: E402
from deephealing_kernel.tick import WorldKernel  # noqa: E402

SEED = 20260921


def write(name: str, payload) -> None:
    path = LOGS / name
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    print(f"wrote {path}", flush=True)


def run(name: str, ticks: int, *, decision_source: str = "behaviour_tree"):
    out = RUNTIME / name
    out.mkdir(parents=True, exist_ok=True)
    log = EventLog(out / "events.jsonl")
    kernel = WorldKernel(pack=load_pack(PACK), seed=SEED, log=log, snapshot_every=50,
                         checkpoint_dir=out / "checkpoints", decision_source=decision_source)
    kernel.run(ticks)
    return kernel, log


def recompute(npc_id: str, tick: int, weights: dict) -> dict:
    """独立复算（D-M4-15②）：同一 tick 的世界状态 + 内容包权重 + 规则层模块。"""
    probe = WorldKernel(pack=load_pack(PACK), seed=SEED,
                        log=EventLog(RUNTIME / "probe" / f"{npc_id}-{tick}" / "events.jsonl"),
                        snapshot_every=0, checkpoint_dir=None)
    while probe.world.tick < tick - 1:
        probe.step()
    entity = probe.world.get(npc_id)
    needs = entity.components.get("needs") or {}
    state = (entity.components.get("schedule") or {}).get("state") or "idle"
    records = decision_mod.requirement_mod.evaluate(
        decision_mod.satisfaction_view(needs),
        {"weights": decision_mod.normalized_weights(weights)})
    dominant = records[0]
    blackboard = {"dominant_need": dominant.need_id, "dominant_deficit": dominant.deficit,
                  "urgency": dominant.deficit, "schedule_state": state}
    branch = decision_mod.branch_of(blackboard)
    candidates = (decision_mod.candidate_actions(state)
                  + decision_mod.branch_candidates(branch, state))
    ranked = utility_mod.score_actions(needs, weights, {"schedule_state": state}, candidates)
    return {"blackboard": blackboard, "branch": branch, "ranked": ranked, "schedule_state": state}


def main() -> int:
    kernel, log = run("decisions", 240)
    events = [event for event in log.read_all() if event.type == "npc.decision"]
    profiles = tick_mod.build_pack_profiles(load_pack(PACK))
    npcs = len(profiles)

    write("decision-observability.json", {
        "criterion_1": "① 决策路径可观测：真实事件流出现 npc.decision（每 tick 每 NPC 一条）",
        "ticks": 240, "npcs": npcs, "decision_events": len(events),
        "expected": 240 * npcs,
        "passed": len(events) == 240 * npcs,
        "sample": events[0].payload if events else None,
        "required_fields_present": sorted(events[0].payload) if events else [],
    })

    # ② 行为可分辨性
    by_npc: dict[str, list] = {}
    for event in events:
        by_npc.setdefault(event.payload["npc_id"], []).append(event)
    windows = []
    for npc_id in sorted(by_npc):
        weights = profiles[npc_id]["need_weights"]
        grouped: dict[str, list] = {}
        for event in by_npc[npc_id]:
            grouped.setdefault(event.payload["dominant_need"], []).append(event)
        for need in sorted(grouped):
            sample = grouped[need][0]
            recomputed = recompute(npc_id, sample.tick, weights)
            ranked = recomputed["ranked"]
            mandated = decision_mod.candidate_actions(sample.payload["schedule_state"])[0]["action"]
            mandated_score = next((item["score"] for item in ranked if item["action"] == mandated), 0.0)
            windows.append({
                "npc_id": npc_id, "tick": sample.tick,
                "dominant_need": sample.payload["dominant_need"],
                "dominant_deficit": sample.payload["dominant_deficit"],
                "schedule_state": sample.payload["schedule_state"],
                "schedule_mandated_action": mandated,
                "schedule_mandated_score": mandated_score,
                "chosen_action": sample.payload["chosen_action"],
                "utility_score": sample.payload["utility_score"],
                "bt_branch": sample.payload["bt_branch"],
                "gap": round(float(sample.payload["utility_score"]) - float(mandated_score), 6),
                "recompute_action": ranked[0]["action"],
                "recompute_score": ranked[0]["score"],
                "recompute_branch": recomputed["branch"],
                "recompute_matches": (
                    ranked[0]["action"] == sample.payload["chosen_action"]
                    and ranked[0]["score"] == sample.payload["utility_score"]
                    and recomputed["branch"] == sample.payload["bt_branch"]
                    and recomputed["blackboard"]["dominant_need"] == sample.payload["dominant_need"]
                ),
            })
    evidence = [w for w in windows if w["chosen_action"] != w["schedule_mandated_action"] and w["gap"] > 0.05]
    write("behaviour-discriminability.json", {
        "criterion_2": "② 同一 NPC 在不同需求状态下选不同动作，且该动作不是班表在那一刻的规定（间距 > 0.05）",
        "windows_total": len(windows), "evidence_windows": len(evidence),
        "all_recomputations_match": all(w["recompute_matches"] for w in windows),
        "evidence": evidence,
        "narrative_lines": [
            f"{w['npc_id']}@{w['tick']}: 班表说 {w['schedule_mandated_action']!r}"
            f"（score {w['schedule_mandated_score']}） / 它选了 {w['chosen_action']!r}"
            f"（score {w['utility_score']}） / 因为需求 {w['dominant_need']!r}"
            f"（deficit {w['dominant_deficit']}） | 分支 {w['bt_branch']!r} | 间距 {w['gap']}"
            for w in evidence
        ],
        "passed": len(evidence) >= 2 and all(w["recompute_matches"] for w in windows),
    })

    # ③ 确定性（两次独立运行逐位相同）+ verify --expected-hash
    first, first_log = run("det_a", 300)
    second, second_log = run("det_b", 300)
    write("determinism-baseline.json", {
        "criterion_3": "③ 同 seed 同 tick 数两次运行 state_hash / chain_tail 逐位相同",
        "state_hash_300": first.state_hash(),
        "chain_tail_300": first_log.last_hash,
        "second_state_hash_300": second.state_hash(),
        "second_chain_tail_300": second_log.last_hash,
        "identical": first.state_hash() == second.state_hash()
                     and first_log.last_hash == second_log.last_hash,
        "old_baseline_M1M2": {
            "state_hash": "9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f",
            "chain_tail": "baecca9219a9bbabfc0e46349834438cc0c61ba44fd6315aeda26fb65acfd786",
            "note": "历史值（M1/M2 口径，不再作断言）；决策路径切换必然改变基线（AC-M4-8⑥）",
        },
    })

    # ④ 负例：退回桩
    _, stub_log = run("stub", 60, decision_source="deterministic_stub")
    stub_events = [event for event in stub_log.read_all() if event.type == "npc.decision"]
    stub_actions = [event for event in stub_log.read_all() if event.type == "npc.action"]
    write("negative-stub.json", {
        "criterion_4": "④ 退回 stub_decide ⇒ ①②必须变红",
        "stub_decision_events": len(stub_events),
        "stub_action_decision_source": sorted({event.payload["decision_source"] for event in stub_actions}),
        "stub_action_set": sorted({event.payload["action"] for event in stub_actions}),
        "passed": len(stub_events) == 0
                  and sorted({event.payload["decision_source"] for event in stub_actions}) == ["deterministic_stub"],
    })
    print("DECISION_EVIDENCE_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
