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

import ast
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
SKELETON = KERNEL_ROOT.parent
CAPS_DIR = SKELETON / "capabilities"
RULES_DIR = KERNEL_ROOT / "deephealing_kernel" / "rules"

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


#: 规则层静态扫描的禁用 token（HTTP/SDK 面；与 AC-M4-4 的 `rg` 命令行**同一口径**）
FORBIDDEN_NETWORK_TOKENS = ("urllib", "requests", "httpx", "socket", "openai", "instructor")

#: **模型出口面**：这些名字段在规则层**任何**文件里出现 ⇒ 判红（**代码面**判定 ——
#: 注释与 docstring 天然不在 AST 名字面内）。旧口径只扫 HTTP/SDK token ⇒ 经**项目自身**出口
#: （`deephealing_kernel/providers/remote_api.py`）发起的模型调用完全看不见（判据面 ≠ 声称面）。
MODEL_EGRESS_SEGMENTS = frozenset({
    "remote_api",   # 项目自身远端模型出口：providers/remote_api.py
    "local_model",  # 项目自身本地模型 provider：providers/local_model.py
    "urllib", "requests", "httpx", "http", "aiohttp", "socket",
    "openai", "anthropic", "instructor",
})

#: **决策路径**（tick 阶段 [3] 的唯一入口）与 provider 层**零接触** —— 比「零模型调用」更严，
#: 且交付面当前已满足：`rules/decision.py` 不引用 `providers` 包的任何符号。
#: （否则「借道既有合法 import」就能把模型出口夹带进决策路径。）
DECISION_MODULE = "decision.py"
DECISION_MODULE_FORBIDDEN_SEGMENTS = MODEL_EGRESS_SEGMENTS | {"providers"}

#: 动态导入：常量字符串参数也要看（`importlib.import_module("providers.remote_api")`）
_DYNAMIC_IMPORT_CALLEES = frozenset({"import_module", "__import__"})


def _rules_layer_files() -> list[Path]:
    """规则层**全量**枚举（`rglob` 动态 + **非空断言**；禁止硬编码文件名清单）。

    旧口径是 3 个硬编码文件名（`requirement/utility/behaviour_tree`，**不含 `decision.py`**）
    ⇒ 把模型出口注入决策模块也照样绿。扫描面为空（目录被搬走 / 后缀变了）**必须判红**，
    不得退化成「零命中绿」。
    """
    files = sorted(RULES_DIR.rglob("*.py"))
    assert files, f"规则层扫描面为空：{RULES_DIR} 下没有任何 *.py（扫描面失效即判红）"
    return files


def test_call_capability_is_the_only_seam():
    """规则层不得自己发 HTTP / 用 SDK：**规则层全量**源码里不得出现网络客户端。"""
    files = _rules_layer_files()
    names = [path.name for path in files]
    assert "decision.py" in names, f"扫描面必须覆盖决策模块；实际扫描面={names}"
    for path in files:
        source = path.read_text(encoding="utf-8")
        code = [line for line in source.splitlines()
                if line.strip() and not line.strip().startswith("#")]
        hits = [line for line in code if any(token in line for token in FORBIDDEN_NETWORK_TOKENS)]
        assert not hits, f"规则层 {path.name} 出现网络/SDK 调用：{hits}"

    # 反向对照：providers/remote_api.py **必须**出现 urllib（证明上面的扫描面不是空转）
    provider_source = (KERNEL_ROOT / "deephealing_kernel" / "providers" / "remote_api.py").read_text(
        encoding="utf-8")
    assert "urllib" in provider_source


def _dotted_name(node: ast.AST) -> str | None:
    """`Name` / `Attribute` 链 ⇒ 点号名（`urllib.request.urlopen` / `remote_api.call`）。"""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _code_face_references(source: str, filename: str) -> list[tuple[int, str]]:
    """AST **代码面**引用清单（import / 属性链 / 裸名字 / 动态导入常量）。

    注释不参与（AST 里根本不存在）；docstring 是 `Constant` 节点、不在本函数采集的名字面内
    ⇒ `rules/decision.py` docstring 里的 `providers.remote_api` 字样**不会**让干净树变红。
    """
    tree = ast.parse(source, filename=filename)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append((node.lineno, node.module))
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.Attribute):
            dotted = _dotted_name(node)
            if dotted:
                found.append((node.lineno, dotted))
        elif isinstance(node, ast.Name):
            found.append((node.lineno, node.id))
        elif isinstance(node, ast.Call):
            callee = _dotted_name(node.func) or ""
            if callee.split(".")[-1] in _DYNAMIC_IMPORT_CALLEES and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.append((node.lineno, first.value))
    return found


def test_decision_path_has_no_model_seam():
    """AC-M4-4 的**代码面**判据：决策路径不得引用模型出口（**含项目自身**的 `providers` 包）。

    为什么需要它：`rg` 那条只扫 HTTP/SDK token，而本项目的模型出口是
    `deephealing_kernel/providers/remote_api.py` ⇒ 「经自身 provider 发起的模型调用」是**盲区**
    （判据面 ≠ 声称面）。本条走 AST 代码面，两级判定：

      ① 规则层**全量**：不得出现**模型出口面**名字（`remote_api` / `local_model` / 网络与 SDK 根）；
      ② **决策路径** `decision.py`：与 `providers` 包**零接触**（比「零模型调用」更严）。

    ② 之所以能这样定：盘上 `decision.py` 对 `providers` 包的引用数是 **0**
    （`rules/behaviour_tree.py:22` 那条 `providers.cassette` 是 **M2 既有**的**异常类型**导入
    —— `CassetteMiss` 必须原样上抛、不得吞成 FAILURE —— 不是模型调用，也不在决策路径上，
    故只在 ① 下放行，不进 ②）。
    """
    files = _rules_layer_files()
    assert files, f"规则层扫描面为空：{RULES_DIR}"
    violations: list[str] = []
    for path in files:
        forbidden = (DECISION_MODULE_FORBIDDEN_SEGMENTS if path.name == DECISION_MODULE
                     else MODEL_EGRESS_SEGMENTS)
        for lineno, dotted in _code_face_references(path.read_text(encoding="utf-8"), str(path)):
            if set(dotted.split(".")) & forbidden:
                violations.append(f"{path.name}:{lineno}: {dotted}")
    assert not violations, (
        "决策路径出现模型出口引用（AC-M4-4 要求零模型调用）：\n" + "\n".join(violations))


def test_call_capability_rejects_missing_registry():
    with pytest.raises(RuntimeError):
        behaviour_tree.call_capability("emotion.appraise", None, None, {})


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
