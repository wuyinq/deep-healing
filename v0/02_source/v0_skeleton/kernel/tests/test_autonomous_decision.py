"""W11 自主决策判据（AC-M4-8 ①~⑤；设计 §2 D-M4-1/D-M4-2/D-M4-9、§11 D-M4-15）。

五条判据逐条落地：
  ① **决策路径可观测**：真实事件流里出现 `npc.decision`，带 4 个必核字段 + 契约字段；
  ② **行为可分辨性**：≥2 个 tick 窗口，同一 NPC 在不同需求状态下选不同动作，
     且该动作**不是班表在那一刻的规定**（逐条列「班表说 X / 它选了 Y / 因为需求 Z」）；
     同时给「所选动作 vs 班表规定动作」的 `utility_score` **间距 > 0.05**（D-M4-20）；
  ③ **确定性不回退**：同 seed 同 tick 数**两次运行** `state_hash` / `chain_tail` 逐位相同；
  ④ **负例自证**：退回 `stub_decide` ⇒ ①②**必须变红**；
  ⑤ 内核零模型调用由 `test_rules_layer.py` + `V0_SELF_TEST.md` 的静态检查覆盖（本文件不重复）。

**④ 的负例形态（设计 §2 D-M4-1，Raven F-4 已关闭）**：`stub_decide` 的签名与 `decide` **不同**
（前者无 `pack_profiles`）⇒ 直接把 `autonomous_decide` 换成 `stub_decide` 会 **`TypeError`（假红）**。
故负例走 `WorldKernel(decision_source="deterministic_stub")` 构造参数 —— 这是 AC-M4-8④ 的**唯一**负例形态；
另有一条**注入点仍有效**的对抗用例（`test_injection_point_is_still_the_decision_stage`）证明
`tick_mod.autonomous_decide` 这个模块级别名仍可被替换（否则 M1 两条对抗判据会变成零命中假绿）。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SEED = 20260921
sys.path.insert(0, str(KERNEL_ROOT))

from deephealing_kernel import tick as tick_mod  # noqa: E402
from deephealing_kernel.events import EventLog  # noqa: E402
from deephealing_kernel.pack import load_pack  # noqa: E402
from deephealing_kernel.rules import decision as decision_mod  # noqa: E402
from deephealing_kernel.rules import utility as utility_mod  # noqa: E402
from deephealing_kernel.tick import WorldKernel  # noqa: E402

REQUIRED_FIELDS = ("npc_id", "dominant_need", "chosen_action", "utility_score", "bt_branch")
CONTRACT_FIELDS = ("dominant_deficit", "utility_ranking", "schedule_state", "schedule_is_driver",
                   "decision_source")


def _run(tmp_path: Path, *, ticks: int = 120, decision_source: str = "behaviour_tree",
         name: str = "a") -> tuple[object, EventLog]:
    pack = load_pack(PACK_DIR)
    log = EventLog(tmp_path / name / "events.jsonl")
    kernel = WorldKernel(pack=pack, seed=SEED, log=log, snapshot_every=50, checkpoint_dir=None,
                         decision_source=decision_source)
    kernel.run(ticks)
    return kernel, log


def _decisions(log: EventLog) -> list:
    return [event for event in log.read_all() if event.type == "npc.decision"]


# ---------------------------------------------------------------------------- ① 可观测
def test_decision_path_is_observable_in_the_real_event_stream(tmp_path):
    """① 真实事件流出现 `npc.decision`，每 tick 每 NPC 一条，且带必核 + 契约字段。"""
    _, log = _run(tmp_path, ticks=40)
    events = _decisions(log)
    npc_count = len(load_pack(PACK_DIR).npcs)
    assert len(events) == 40 * npc_count, (
        f"期望 40 tick x {npc_count} NPC = {40 * npc_count} 条 npc.decision，实测 {len(events)}"
    )
    for event in events[:20]:
        for field in REQUIRED_FIELDS:
            assert field in event.payload, f"npc.decision 缺少必核字段 {field}"
        for field in CONTRACT_FIELDS:
            assert field in event.payload, f"npc.decision 缺少契约字段 {field}"
        assert event.payload["decision_source"] == "behaviour_tree"
        assert event.payload["schedule_is_driver"] is False
        assert event.payload["bt_branch"] in decision_mod.BRANCH_LABELS
        assert 0.0 <= float(event.payload["dominant_deficit"]) <= 1.0
        assert float(event.payload["utility_score"]) >= 0.0
        assert isinstance(event.payload["utility_ranking"], list)
        assert event.payload["utility_ranking"], "utility_ranking 必须非空（前 3 名）"

    # 反例（同一条判据的自证）：桩路径下事件数为 0 ⇒ 上面这条断言必须红
    _, stub_log = _run(tmp_path, ticks=40, decision_source="deterministic_stub", name="stub")
    assert _decisions(stub_log) == [], "退回桩路径后 npc.decision 必须消失（否则①是恒真判据）"
    stub_actions = [event for event in stub_log.read_all() if event.type == "npc.action"]
    assert stub_actions and all(
        event.payload["decision_source"] == "deterministic_stub" for event in stub_actions
    ), "桩路径的 npc.action.decision_source 必须是 deterministic_stub"


# ---------------------------------------------------------------------------- ② 可分辨性
def _recompute(tmp_path: Path, npc_id: str, tick: int, weights: dict) -> dict:
    """独立复算（D-M4-15②）：只用**同一 tick 的世界状态** + 内容包权重 + 规则层模块。

    注意：decide 阶段发生在**执行之前** ⇒ tick T 的决策读的是 **tick T-1 执行完**的状态，
    故这里快进到 `tick - 1` 再读（每个样本用**独立**内核实例，避免跨样本的状态串味）。
    """
    pack = load_pack(PACK_DIR)
    probe = WorldKernel(pack=pack, seed=SEED,
                        log=EventLog(tmp_path / f"probe-{npc_id}-{tick}" / "events.jsonl"),
                        snapshot_every=0, checkpoint_dir=None)
    while probe.world.tick < tick - 1:
        probe.step()
    entity = probe.world.get(npc_id)
    assert entity is not None, f"{npc_id} 不在世界里"
    needs = entity.components.get("needs") or {}
    schedule_state = (entity.components.get("schedule") or {}).get("state") or "idle"
    records = decision_mod.requirement_mod.evaluate(
        decision_mod.satisfaction_view(needs),
        {"weights": decision_mod.normalized_weights(weights)},
    )
    dominant = records[0]
    blackboard = {
        "dominant_need": dominant.need_id,
        "dominant_deficit": dominant.deficit,
        "urgency": dominant.deficit,
        "schedule_state": schedule_state,
    }
    branch = decision_mod.branch_of(blackboard)
    candidates = (decision_mod.candidate_actions(schedule_state)
                  + decision_mod.branch_candidates(branch, schedule_state))
    ranked = utility_mod.score_actions(needs, weights, {"schedule_state": schedule_state}, candidates)
    return {"blackboard": blackboard, "branch": branch, "ranked": ranked,
            "schedule_state": schedule_state, "needs": needs}


def test_behaviour_is_distinguishable_by_need_state(tmp_path):
    """② 同一 NPC 在 ≥2 个 tick 窗口因需求不同选不同动作，且动作不是班表规定动作。"""
    _, log = _run(tmp_path, ticks=240)
    events = _decisions(log)
    assert events, "事件流里没有 npc.decision"

    by_npc: dict[str, list] = {}
    for event in events:
        by_npc.setdefault(event.payload["npc_id"], []).append(event)

    # 独立复算用：每个样本用独立内核实例读**同一 tick**的真实世界状态（见 `_recompute`）
    pack = load_pack(PACK_DIR)
    profiles = tick_mod.build_pack_profiles(pack)

    windows: list[dict] = []
    windows_per_npc: dict[str, int] = {}
    for npc_id in sorted(by_npc):
        weights = profiles[npc_id]["need_weights"]
        grouped: dict[str, list] = {}
        for event in by_npc[npc_id]:
            grouped.setdefault(event.payload["dominant_need"], []).append(event)
        windows_per_npc[npc_id] = len(grouped)

        for need in sorted(grouped):
            sample = grouped[need][0]
            recomputed = _recompute(tmp_path, npc_id, sample.tick, weights)
            ranked = recomputed["ranked"]
            top = ranked[0]
            # 独立复算逐字段一致（D-M4-15②）：动作 / 分数 / 前三名 / 分支 / 需求 / 日程态
            assert top["action"] == sample.payload["chosen_action"], (
                f"{npc_id}@{sample.tick} 独立复算动作 {top['action']!r} != 事件值 "
                f"{sample.payload['chosen_action']!r}")
            assert top["score"] == sample.payload["utility_score"], (
                f"{npc_id}@{sample.tick} 独立复算 utility_score {top['score']} != 事件值 "
                f"{sample.payload['utility_score']}")
            assert [item["action"] for item in ranked[:3]] == [
                item["action"] for item in sample.payload["utility_ranking"]
            ], "utility_ranking 前 3 名必须与独立复算的排序一致"
            assert recomputed["branch"] == sample.payload["bt_branch"], (
                f"{npc_id}@{sample.tick} 独立复算分支 {recomputed['branch']!r} != 事件值 "
                f"{sample.payload['bt_branch']!r}")
            assert recomputed["blackboard"]["dominant_need"] == sample.payload["dominant_need"]
            assert recomputed["blackboard"]["dominant_deficit"] == sample.payload["dominant_deficit"]
            assert recomputed["schedule_state"] == sample.payload["schedule_state"]

            mandated = decision_mod.candidate_actions(sample.payload["schedule_state"])[0]["action"]
            mandated_score = next((item["score"] for item in ranked
                                   if item["action"] == mandated), 0.0)
            windows.append({
                "npc_id": npc_id,
                "tick": sample.tick,
                "need": sample.payload["dominant_need"],
                "action": sample.payload["chosen_action"],
                "branch": sample.payload["bt_branch"],
                "deficit": sample.payload["dominant_deficit"],
                "score": sample.payload["utility_score"],
                "mandated": mandated,
                "mandated_score": mandated_score,
                "gap": round(float(sample.payload["utility_score"]) - float(mandated_score), 6),
            })

    # 「班表不是驱动」的证据窗口：动作**不等于**班表规定动作，且效用间距 > 0.05（D-M4-20）
    evidence = [w for w in windows if w["action"] != w["mandated"] and w["gap"] > 0.05]
    near_ties = [w for w in windows if w["action"] != w["mandated"] and w["gap"] <= 0.05]
    agrees = [w for w in windows if w["action"] == w["mandated"]]

    # 同一 NPC 在 ≥2 个需求窗口里选了不同动作（② 的核心）
    distinguishable: dict[str, set] = {}
    for window in evidence:
        distinguishable.setdefault(window["npc_id"], set()).add((window["need"], window["action"]))
    multi = {npc: pairs for npc, pairs in distinguishable.items()
             if len({pair[0] for pair in pairs}) >= 2 and len({pair[1] for pair in pairs}) >= 2}

    lines = [f"行为可分辨性逐条读数（②）: 证据窗口 {len(evidence)} / 近并列 {len(near_ties)} / "
             f"与班表一致 {len(agrees)} | 需求窗口数 {windows_per_npc}"]
    for window in evidence:
        lines.append(
            f"  {window['npc_id']}@{window['tick']}: 班表说 {window['mandated']!r}"
            f"（score {window['mandated_score']}） / 它选了 {window['action']!r}"
            f"（score {window['score']}） / 因为需求 {window['need']!r}"
            f"（deficit {window['deficit']}） | 分支 {window['branch']!r} | 间距 {window['gap']}")
    for window in near_ties + agrees:
        lines.append(f"  （非证据）{window['npc_id']}@{window['tick']}: 需求 {window['need']!r} ⇒ "
                     f"动作 {window['action']!r} vs 班表 {window['mandated']!r} | 间距 {window['gap']}")
    print("\n".join(lines))

    assert any(count >= 2 for count in windows_per_npc.values()), (
        f"没有任何 NPC 出现 ≥2 个需求窗口（实测 {windows_per_npc}）⇒ ② 未真正成立")
    assert len(evidence) >= 2, (
        f"「与班表不一致且间距 > 0.05」的证据窗口不足（实测 {len(evidence)} 条）⇒ 无法证明日程不是驱动")
    assert multi, (
        f"没有任何 NPC 在 ≥2 个需求窗口里选出 ≥2 个不同动作（实测 {distinguishable}）⇒ 行为不可分辨")


# ---------------------------------------------------------------------------- ③ 确定性
def test_same_seed_two_runs_are_bit_identical(tmp_path):
    """③ 同 seed 同 tick 数两次运行 `state_hash` / `chain_tail` 逐位相同。"""
    first, first_log = _run(tmp_path, ticks=300, name="run_a")
    second, second_log = _run(tmp_path, ticks=300, name="run_b")
    assert first.state_hash() == second.state_hash()
    assert first_log.last_hash == second_log.last_hash
    # 反例（自证）：换 seed ⇒ 哈希必须不同（否则「两次相同」是恒真判据）
    third_log = EventLog(tmp_path / "run_c" / "events.jsonl")
    third = WorldKernel(pack=load_pack(PACK_DIR), seed=SEED + 1, log=third_log,
                        snapshot_every=0, checkpoint_dir=None)
    third.run(300)
    assert third.state_hash() != first.state_hash(), "换 seed 后 state_hash 必须改变（判据可达性）"


# ---------------------------------------------------------------------------- ④ 负例自证
def test_negative_control_stub_decision_source_turns_observability_red(tmp_path):
    """④ 退回 `stub_decide` ⇒ ① 的观测面**必须变红**（事件数 0 + decision_source 改变）。"""
    _, log = _run(tmp_path, ticks=60, decision_source="deterministic_stub")
    assert _decisions(log) == [], "负例下 npc.decision 必须为 0（① 因此变红）"
    actions = [event for event in log.read_all() if event.type == "npc.action"]
    assert actions
    assert all(event.payload["decision_source"] == "deterministic_stub" for event in actions)

    # 负例下 `npc.action` 的 target 只能来自班表（不经过效用/行为树）⇒ 动作集合退化为 move/hold
    assert {event.payload["action"] for event in actions} <= {"move", "hold"}, (
        "桩路径的动作面必须退化成 M1 的 move/hold（效用动作 talk/work/walk 不得出现）"
    )


def test_injection_point_is_still_the_decision_stage(tmp_path):
    """④ 配套：`tick_mod.autonomous_decide` 仍可被替换（模块级别名，M1 对抗判据不零命中）。"""
    assert hasattr(tick_mod, "autonomous_decide")
    original = tick_mod.autonomous_decide
    calls: list[int] = []

    def counting(world, rng, tick, ctx, *, pack_profiles, **kwargs):
        calls.append(tick)
        return original(world, rng, tick, ctx, pack_profiles=pack_profiles, **kwargs)

    tick_mod.autonomous_decide = counting
    try:
        _run(tmp_path, ticks=5, name="patched")
    finally:
        tick_mod.autonomous_decide = original
    assert calls == [1, 2, 3, 4, 5], f"决策阶段必须每 tick 调用一次注入点，实测 {calls}"


# ---------------------------------------------------------------------------- 决策树 fail-closed
def test_decision_tree_rejects_capability_slots_at_construction():
    """决策树**构造期**拒绝 capability 槽位（不得静默走另一条分支）。"""
    with pytest.raises(ValueError):
        decision_mod.build_branch_tree({"type": "action", "slot": "intent.plan"})
    with pytest.raises(ValueError):
        decision_mod.build_branch_tree({"type": "selector", "children": [
            {"type": "branch", "label": "hold"},
            {"type": "action", "slot": "emotion.appraise"},
        ]})
    with pytest.raises(ValueError):
        decision_mod.build_branch_tree({"type": "branch", "label": "not-a-branch"})
    # 反向对照：合法规格必须能构建（证明上面的拒绝不是「恒抛」）
    assert decision_mod.build_branch_tree({"type": "branch", "label": "hold"})["label"] == "hold"


def test_decision_event_payload_satisfies_frozen_schema(tmp_path):
    """`npc.decision` 必须过 `events.schema.json` 的 `then` 子句（只加不松）。"""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((KERNEL_ROOT.parents[1] / "events.schema.json").read_text(encoding="utf-8"))
    _, log = _run(tmp_path, ticks=3, name="schema")
    events = _decisions(log)
    assert events
    for event in events[:10]:
        jsonschema.validate(event.to_dict(), schema)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-s"]))
