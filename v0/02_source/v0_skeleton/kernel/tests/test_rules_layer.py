"""W4 规则层用例：需求 → 效用 → 行为树，且「调用原子能力」是唯一接缝。

运行：
    cd <workspace>/02_source/v0_skeleton/kernel && \
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_rules_layer.py -q -p no:cacheprovider

判据（设计 §3.2）：
  1. 需求层 `evaluate` 可比较且显式 tie-break（`deficit` 降序 → `need_id` 升序）；
  2. 效用层 `score_actions` 纯函数 + 显式 tie-break（分数 → 需求 id → 目标 id）；
  3. 行为树节点语义 `SUCCESS/FAILURE/RUNNING`，未知槽位**构建期**即报错（fail fast）；
  4. 叶子 `call_capability` 是规则层与能力层**唯一**接缝（规则层不得自己发 HTTP / SDK）；
  5. 至少一次「调用原子能力 → 校验结果 → 决定后续」（由 selector 分支体现）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
SKELETON = KERNEL_ROOT.parent
CAPS_DIR = SKELETON / "capabilities"

from deephealing_kernel.providers.deterministic_rule import DeterministicRuleProvider  # noqa: E402
from deephealing_kernel.registry import CapabilityRegistry  # noqa: E402
from deephealing_kernel.rules import behaviour_tree, requirement, utility  # noqa: E402


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry(CAPS_DIR, CAPS_DIR / "pins.json")
    registry.register_adapter("deterministic_rule", DeterministicRuleProvider())
    return registry


NEEDS = {"physiology": 0.9, "safety": 0.9, "belonging": 0.2,
         "esteem": 0.2, "self_actualization": 0.1}


# --------------------------------------------------------------------------- 需求层
def test_requirement_evaluate_is_ordered_and_deterministic():
    first = requirement.evaluate(NEEDS, {"weights": {}, "npc_id": "npc-001", "tick": 3})
    second = requirement.evaluate(dict(reversed(list(NEEDS.items()))), {})
    assert [item.need_id for item in first] == [item.need_id for item in second]
    # deficit = (1 - level) × weight ⇒ 最不满足的 belonging 必须排首位；同分时按 need_id 字典序
    assert first[0].need_id == "belonging"
    assert first[0].deficit >= first[-1].deficit
    assert [item.need_id for item in first] == sorted(
        [item.need_id for item in first],
        key=lambda name: (-[item.deficit for item in first if item.need_id == name][0], name))

    # 反向对照：把需求整体压低 ⇒ 首位 deficit 必须**变大**（证明打分不是常量）
    lower = requirement.evaluate({name: 0.1 for name in NEEDS}, {})
    assert lower[0].deficit > first[0].deficit

    # 空输入必须不炸（全函数）
    assert len(requirement.evaluate({}, {})) == 5


# --------------------------------------------------------------------------- 效用层
def test_utility_score_actions_is_pure_and_tie_broken():
    candidates = [
        {"action": "talk", "need": "belonging", "when_state": "working"},
        {"action": "rest", "need": "physiology", "when_state": "working"},
        {"action": "work", "need": "esteem", "when_state": "working"},
    ]
    first = utility.score_actions(NEEDS, {}, {"schedule_state": "working"}, candidates)
    second = utility.score_actions(NEEDS, {}, {"schedule_state": "working"},
                                   list(reversed(candidates)))
    assert first == second, "输入顺序不得影响结果（禁止依赖容器迭代序）"
    assert first[0]["action"] == "rest"
    for previous, current in zip(first, first[1:]):
        assert (-previous["score"], previous["need"], previous["target_entity"] or "") \
            <= (-current["score"], current["need"], current["target_entity"] or "")

    # 日程情境加成必须真的生效（数据驱动，非硬编码）
    with_state = utility.score_actions(NEEDS, {}, {"schedule_state": "working"}, candidates)
    without = utility.score_actions(NEEDS, {}, {}, candidates)
    assert with_state[0]["score"] >= without[0]["score"]
    assert with_state != without

    assert utility.need_pressure(NEEDS, {}) > utility.need_pressure({}, {})
    assert utility.select([], {}) is None
    assert utility.select(candidates, {"needs": NEEDS})["action"] == "rest"


# --------------------------------------------------------------------------- 行为树
def test_behaviour_tree_build_fails_fast_on_unknown_slot():
    registry = _registry()
    spec = {"type": "sequence", "children": [{"type": "action", "slot": "no.such.slot"}]}
    with pytest.raises(ValueError):
        behaviour_tree.build_tree(spec, registry, None)
    # 反向对照：已知槽位必须构建成功
    ok = behaviour_tree.build_tree({"type": "action", "slot": "emotion.appraise"}, registry, None)
    assert ok["slot"] == "emotion.appraise"
    with pytest.raises(ValueError):
        behaviour_tree.build_tree({"type": "sequence", "children": []}, registry, None)
    with pytest.raises(ValueError):
        behaviour_tree.build_tree({"type": "wat"}, registry, None)


def test_behaviour_tree_selector_falls_through_on_failure():
    """至少一次「调用原子能力 → 校验结果 → 决定后续」：失败即走另一分支。"""
    registry = _registry()
    blackboard = {
        "npc_id": "npc-001",
        "tick": 3,
        "needs_pressure": 0.9,                     # 条件成立 ⇒ 走 sequence
        "needs": NEEDS,
        "schedule_state": "working",
        "candidate_actions": [{"action": "rest", "need": "physiology"}],
        "event_summary": "还好",
        "current_emotion": {},
        "observations": [],
        "existing_relations": {},
    }
    spec = {
        "type": "selector",
        "children": [
            {"type": "sequence", "children": [
                {"type": "condition", "key": "needs_pressure", "op": ">=", "value": 0.5},
                {"type": "action", "slot": "intent.plan",
                 "payload": {"npc_id": "$npc_id", "tick": "$tick", "needs": "$needs",
                             "schedule_state": "$schedule_state", "candidate_actions": "$candidate_actions"},
                 "store_as": "plan"},
            ]},
            {"type": "action", "slot": "emotion.appraise",
             "payload": {"npc_id": "$npc_id", "tick": "$tick", "event_summary": "$event_summary",
                         "current_emotion": "$current_emotion"},
             "store_as": "emotion"},
        ],
    }
    outcome = behaviour_tree.run_tree(spec, blackboard, registry, None)
    assert outcome["status"] == behaviour_tree.SUCCESS
    assert "plan" in blackboard and "emotion" not in blackboard, "条件成立时必须只走第一条分支"

    # 反向对照：把条件改成不成立 ⇒ 必须走**第二条**分支（selector 真的在决定后续）
    blackboard["needs_pressure"] = 0.0
    outcome2 = behaviour_tree.run_tree(spec, blackboard, registry, None)
    assert outcome2["status"] == behaviour_tree.SUCCESS
    assert "emotion" in blackboard

    # 条件节点缺键 / 类型不对 ⇒ FAILURE（不抛异常）
    assert behaviour_tree.tick({"type": "condition", "key": "missing", "op": ">=", "value": 1},
                               {}, None) == behaviour_tree.FAILURE
    assert behaviour_tree.tick({"type": "condition", "key": "needs_pressure", "op": ">=", "value": "x"},
                               blackboard, None) == behaviour_tree.FAILURE


def test_call_capability_is_the_only_seam():
    """规则层不得自己发 HTTP / 用 SDK：源码里不得出现网络客户端。"""
    forbidden = ("urllib", "requests", "httpx", "socket", "openai", "instructor")
    for name in ("requirement.py", "utility.py", "behaviour_tree.py"):
        source = (KERNEL_ROOT / "deephealing_kernel" / "rules" / name).read_text(encoding="utf-8")
        code = [line for line in source.splitlines()
                if line.strip() and not line.strip().startswith("#")]
        hits = [line for line in code if any(token in line for token in forbidden)]
        assert not hits, f"规则层 {name} 出现网络/SDK 调用：{hits}"

    # 反向对照：providers/remote_api.py **必须**出现 urllib（证明上面的扫描面不是空转）
    provider_source = (KERNEL_ROOT / "deephealing_kernel" / "providers" / "remote_api.py").read_text(
        encoding="utf-8")
    assert "urllib" in provider_source


def test_call_capability_rejects_missing_registry():
    with pytest.raises(RuntimeError):
        behaviour_tree.call_capability("emotion.appraise", None, None, {})


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
