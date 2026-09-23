"""自主决策层（V0-M4 新增，设计 §2 D-M4-1 / D-M4-2 / §4.1）。

**这一层是 tick 阶段 [3] 的唯一入口**：需求（`requirement`）→ 效用（`utility`）→ 行为树分支
（本模块的 `DECISION_TREE`）→ intents。日程（`schedules/*.json`）从「唯一驱动」降为
「**先验/约束之一**」（`schedule_is_driver = False`）。

硬约束（AC-M4-4 / AC-M4-8⑤）：
  - **零模型调用**：本模块不 import 任何网络/SDK（`providers.remote_api` 是唯一出口）；
  - **零 wall-clock**：不读 `time.*`、不读 `os.environ`；
  - **零容器迭代序依赖**：所有遍历显式 `sorted`，并列一律 `(score desc, need asc, target asc)`；
  - **确定性**：同 seed 同 tick 数两次运行 `state_hash` / `chain_tail` 逐位相同。

命名遮蔽（D-M4-22）：本模块一律 `from . import behaviour_tree as bt`，
**禁止** `from .behaviour_tree import tick`（与 `deephealing_kernel.tick` 同名，会遮蔽模块）。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from . import behaviour_tree as bt
from . import requirement as requirement_mod
from . import utility as utility_mod

DECISION_SOURCE = "behaviour_tree"

#: 行为树分支标签（闭集；`npc.decision.bt_branch` 的取值面）
BRANCH_LABELS = ("flee", "restore", "work", "socialize", "explore", "hold")

#: 分支 → 语义动作族（**行为树分支把该动作加进候选集** ⇒ 需求驱动的分支真的会改变动作，
#: 而不只是给动作贴标签）
BRANCH_ACTIONS = {
    "flee": "flee",
    "restore": "rest",
    "work": "work",
    "socialize": "talk",
    "explore": "walk",
    "hold": None,
}

#: 分支 → 该分支缓解的需求（与 `ACTION_NEED` 同源；用于候选集扩展）
BRANCH_NEED = {
    "flee": "safety",
    "restore": "physiology",
    "work": "esteem",
    "socialize": "belonging",
    "explore": "self_actualization",
    "hold": None,
}

#: 日程状态 → 候选 (action, need)（**唯一权威**；`cli.py` 从本模块导入，避免两份漂移）
CANDIDATE_ACTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "idle": (("rest", "physiology"), ("talk", "belonging"), ("walk", "self_actualization")),
    "working": (("work", "esteem"), ("talk", "belonging"), ("rest", "physiology")),
    "socializing": (("talk", "belonging"), ("work", "esteem"), ("rest", "physiology")),
    "resting": (("rest", "physiology"), ("walk", "self_actualization"), ("talk", "belonging")),
    "moving": (("walk", "self_actualization"), ("rest", "physiology"), ("talk", "belonging")),
    "interrupted": (("flee", "safety"), ("rest", "physiology"), ("talk", "belonging")),
}

#: 动作 → 该动作**缓解**的需求（数据映射；`hold` 不缓解任何需求）
ACTION_NEED: dict[str, str | None] = {
    "rest": "physiology",
    "work": "esteem",
    "talk": "belonging",
    "walk": "self_actualization",
    "flee": "safety",
    "hold": None,
}

#: 需求动力学（**确定性、6 位小数**）：
#:   ① 所有需求每 tick 自然**累积**（压力上升）；
#:   ② 被选中动作对**自身需求**按比例**缓解**（乘性衰减用加性 delta 表达 ⇒ 与 `ecs.system_movement`
#:      的加性语义一致，且永不越界）。
#: 这样「需求 → 效用 → 动作 → 需求演化」构成**闭环**：刚被满足的需求压力下降，
#: 其他需求上升 ⇒ 同一 NPC 在不同需求状态下**真的会换动作**（AC-M4-8② 的来源）。
BUILDUP_PER_TICK = 0.004
RELIEF_RATIO = 0.30

#: 安全紧急度阈值（行为树第一条 `sequence` 的判据值；数据规格的一部分）
URGENCY_THRESHOLD = 0.6

# ---------------------------------------------------------------------- 行为树数据规格
# 只允许 `selector` / `sequence` / `condition` / `branch` 四种节点。
# **出现 capability 槽位节点（`action` / `slot`）在构造期即抛错**（fail-closed）。
DECISION_TREE: dict[str, Any] = {
    "type": "selector",
    "children": [
        # ① **紧急避险**（主导需求缺口 >= 阈值 **且** 主导需求是 safety）⇒ flee
        {"type": "sequence", "children": [
            {"type": "condition", "key": "urgency", "op": ">=", "value": URGENCY_THRESHOLD},
            {"type": "condition", "key": "dominant_need", "op": "==", "value": "safety"},
            {"type": "branch", "label": "flee"},
        ]},
        # ② 需求 → 分支（纯数据映射；safety 未达紧急阈值时是「回家避险」而非「狂奔」）
        {"type": "sequence", "children": [
            {"type": "condition", "key": "dominant_need", "op": "==", "value": "physiology"},
            {"type": "branch", "label": "restore"},
        ]},
        {"type": "sequence", "children": [
            {"type": "condition", "key": "dominant_need", "op": "==", "value": "safety"},
            {"type": "branch", "label": "restore"},
        ]},
        {"type": "sequence", "children": [
            {"type": "condition", "key": "dominant_need", "op": "==", "value": "belonging"},
            {"type": "branch", "label": "socialize"},
        ]},
        {"type": "sequence", "children": [
            {"type": "condition", "key": "dominant_need", "op": "==", "value": "esteem"},
            {"type": "branch", "label": "work"},
        ]},
        {"type": "sequence", "children": [
            {"type": "condition", "key": "dominant_need", "op": "==", "value": "self_actualization"},
            {"type": "branch", "label": "explore"},
        ]},
        # ③ 兜底：原地不动（默认分支，恒成功）
        {"type": "branch", "label": "hold"},
    ],
}


def branch_candidates(branch: str, state: str) -> list[dict]:
    """行为树分支 ⇒ **追加**到日程候选集的候选动作（已在集合里则返回空）。

    这一步让行为树**载重**：分支不是标签，它真的改变候选集与最终动作
    （例：safety 压力跨过紧急阈值 ⇒ `flee` 分支把「避险」加入候选 ⇒ 效用层据此选中它）。
    """
    action = BRANCH_ACTIONS.get(branch)
    need = BRANCH_NEED.get(branch)
    if not action or not need:
        return []
    if any(item["action"] == action for item in candidate_actions(state)):
        return []
    return [{"action": action, "need": need, "when_state": state}]

_ALLOWED_NODE_TYPES = ("selector", "sequence", "condition", "branch")
#: 能力槽位痕迹：出现即构造期抛错（决策树**不得**调用模型）
_CAPABILITY_MARKERS = ("action", "slot", "capability", "call_capability", "store_as")


def build_branch_tree(spec: Any) -> dict:
    """按数据规格构建**纯分支**树；非法节点 / 能力槽位节点 ⇒ **构造期**抛 `ValueError`。

    这是 D-M4-1 的 fail-closed 面：决策树一旦被塞进 capability 槽位，导入期就炸，
    不会退化成「静默走另一条分支」。
    """
    if not isinstance(spec, dict):
        raise ValueError("decision tree node must be a JSON object")
    kind = str(spec.get("type", ""))
    if kind not in _ALLOWED_NODE_TYPES:
        raise ValueError(
            f"decision tree node type {kind!r} is not allowed "
            f"(only {_ALLOWED_NODE_TYPES}; capability slots are forbidden)"
        )
    for marker in _CAPABILITY_MARKERS:
        if marker in spec:
            raise ValueError(
                f"decision tree node declares capability marker {marker!r} "
                "(the decision tree must never call a model)"
            )
    if kind in ("selector", "sequence"):
        children = spec.get("children")
        if not isinstance(children, list) or not children:
            raise ValueError(f"{kind} node must declare a non-empty children array")
        return {"type": kind, "children": [build_branch_tree(child) for child in children]}
    if kind == "condition":
        operator = str(spec.get("op", "=="))
        if operator not in bt._OPS:  # noqa: SLF001 —— 复用行为树既有算子表（同一口径，不另立一份）
            raise ValueError(f"unknown condition operator {operator!r}")
        return {"type": "condition", "key": str(spec.get("key", "")), "op": operator,
                "value": spec.get("value")}
    label = str(spec.get("label", ""))
    if label not in BRANCH_LABELS:
        raise ValueError(f"branch label {label!r} is not in BRANCH_LABELS={BRANCH_LABELS}")
    return {"type": "branch", "label": label}


#: 导入期即构建 ⇒ **构造期 fail-closed**（规格被改坏时 import 就失败，而不是运行期静默兜底）
COMPILED_DECISION_TREE = build_branch_tree(DECISION_TREE)


def _eval_branch(node: dict, blackboard: dict) -> tuple[bool, str | None]:
    """求值纯分支树 ⇒ `(是否成功, 分支标签)`。无 wall-clock、无模型调用、无容器序依赖。"""
    kind = node.get("type")
    if kind == "selector":
        for child in node["children"]:
            ok, label = _eval_branch(child, blackboard)
            if ok:
                return True, label
        return False, None
    if kind == "sequence":
        label: str | None = None
        for child in node["children"]:
            ok, child_label = _eval_branch(child, blackboard)
            if not ok:
                return False, None
            if child_label is not None:
                label = child_label
        return True, label
    if kind == "condition":
        left = blackboard.get(node["key"])
        right = node.get("value")
        if isinstance(left, bool) or isinstance(right, bool):
            return False, None
        if isinstance(left, str) or isinstance(right, str):
            return (str(left) == str(right)), None
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            return False, None
        return bool(bt._OPS[node["op"]](float(left), float(right))), None  # noqa: SLF001
    return True, str(node.get("label"))


def branch_of(blackboard: dict) -> str:
    """求值 `COMPILED_DECISION_TREE` ⇒ 分支标签（兜底 `hold`）。"""
    ok, label = _eval_branch(COMPILED_DECISION_TREE, blackboard)
    if ok and label in BRANCH_LABELS:
        return label
    return "hold"


# ---------------------------------------------------------------------- 候选动作目录
def candidate_actions(state: str) -> list[dict]:
    """日程状态 → 候选动作（**数据映射**，无 `if 分支按 NPC 特判`）。

    `cli.py` 从本模块导入同一份表（单一权威；迁移自 `cli._candidate_actions`，语义不变）。
    """
    table = CANDIDATE_ACTIONS.get(state) or CANDIDATE_ACTIONS["idle"]
    return [{"action": action, "need": need, "when_state": state} for action, need in table]


# ---------------------------------------------------------------------- 决策记录
@dataclass(frozen=True, slots=True)
class Decision:
    """一条可核验的决策记录（`npc.decision` 事件的来源）。"""

    npc_id: str
    tick: int
    dominant_need: str
    dominant_deficit: float
    chosen_action: str
    utility_score: float
    utility_ranking: list[dict]
    bt_branch: str
    schedule_state: str
    target_entity: str | None

    def to_payload(self) -> dict:
        """事件 payload（D-M4-2 的必填字段逐字对齐）。"""
        return {
            "npc_id": self.npc_id,
            "dominant_need": self.dominant_need,
            "dominant_deficit": self.dominant_deficit,
            "chosen_action": self.chosen_action,
            "utility_score": self.utility_score,
            "utility_ranking": copy.deepcopy(self.utility_ranking),
            "bt_branch": self.bt_branch,
            "schedule_state": self.schedule_state,
            "schedule_is_driver": False,
            "target_entity": self.target_entity,
            "decision_source": DECISION_SOURCE,
        }


def _q(value: float) -> float:
    return round(float(value), 6)


# ---------------------------------------------------------------------- 需求/效用口径桥接
# `utility.py`（动作打分器）把 `needs` 当**需求压力**（其 docstring：加权需求压力）；
# `requirement.py` 的 `level` 是**满足度**（`deficit = (1 - level) * weight`）。
# 两者直接混用会得到**反向**的排序（一个按压力降序、一个按压力升序）。
# 桥接口径（**单一权威，就这一处**）：
#   ① 需求层传「满足度 = 1 - 压力」⇒ 其 `deficit == 压力 × 权重`，与效用层**同序**；
#   ② 权重按该 NPC 的最大权重归一化后传入 ⇒ `deficit ∈ [0, 1]`（与事件契约的取值域一致），
#      **排序不变**（正比例缩放）。
NEEDS = utility_mod.NEEDS
DEFAULT_WEIGHTS = utility_mod.DEFAULT_WEIGHTS


def satisfaction_view(needs: dict) -> dict:
    """需求压力 → 满足度视图（`requirement.evaluate` 的 `level` 入参）。"""
    return {need: _q(1.0 - max(0.0, min(1.0, float(needs.get(need) or 0.0)))) for need in NEEDS}


def normalized_weights(weights: dict) -> dict:
    """按该 NPC 的最大权重归一化（保证 `deficit ∈ [0,1]`；排序不变）。"""
    effective = {
        need: float(weights.get(need, DEFAULT_WEIGHTS.get(need, 1.0)))
        for need in NEEDS
    }
    top = max(effective.values()) or 1.0
    return {need: _q(value / top) for need, value in effective.items()}


def _needs_delta(action: str, needs: dict) -> dict[str, float] | None:
    """动作 × 当前需求压力 → 需求增量（确定性、6 位小数；无需求可动返回 None）。

    口径（与 `utility.py` 的 docstring 一致）：`needs` 组件是**需求压力**。
      - 所有需求 +`BUILDUP_PER_TICK`（自然累积）；
      - 被选中动作缓解的需求 −`RELIEF_RATIO × 当前压力`（乘性衰减的加性表达）。
    """
    keys = sorted(key for key in needs if isinstance(needs.get(key), (int, float)))
    if not keys:
        return None
    delta = {key: BUILDUP_PER_TICK for key in keys}
    target = ACTION_NEED.get(action)
    if target in delta:
        delta[target] = _q(BUILDUP_PER_TICK - RELIEF_RATIO * float(needs[target]))
    return delta


def _resolve_target(action: str, branch: str, entity: Any, world: Any, profile: dict,
                    schedule: dict) -> str | None:
    """动作 × 分支 → 目标实体（**确定性**：并列按 `(距离, entity_id)` 升序）。

    - `restore` / `flee` → `pack_profiles[npc_id]["home_entity"]`
    - `work` → 当前日程块 `target_entity`（无则 home）
    - `socialize` → **最近的其他 NPC**
    - `explore` → 日程块目标集合 / 街区门户 / 中庭（取距离最近者）
    - `hold` → 不动（None）
    """
    home = profile.get("home_entity")
    if branch in ("restore", "flee"):
        return home if isinstance(home, str) and home else None
    if branch == "work":
        target = schedule.get("target_entity")
        if isinstance(target, str) and target and world.get(target) is not None:
            return target
        return home if isinstance(home, str) and home else None
    if branch == "hold":
        return None

    candidates: list[str] = []
    if branch == "socialize":
        candidates = [other.id for other in world.query(kind="npc") if other.id != entity.id]
    elif branch == "explore":
        target = schedule.get("target_entity")
        if isinstance(target, str) and target:
            candidates.append(target)
        if isinstance(home, str) and home:
            candidates.append(home)
        for other in world.query():
            if other.id == entity.id:
                continue
            tags = other.components.get("tags") or []
            if any(str(tag) in ("portal", "courtyard", "atrium") for tag in tags):
                candidates.append(other.id)
    if not candidates:
        return home if isinstance(home, str) and home else None

    origin = (entity.components.get("transform") or {}).get("pos_mm") or {}

    def sort_key(entity_id: str) -> tuple[int, str]:
        target = world.get(entity_id)
        if target is None:
            return (1 << 62, entity_id)
        pos = (target.components.get("transform") or {}).get("pos_mm") or {}
        distance = sum(abs(int(pos.get(axis, 0)) - int(origin.get(axis, 0))) for axis in ("x", "y", "z"))
        return (distance, entity_id)

    return sorted(set(candidates), key=sort_key)[0]


# ---------------------------------------------------------------------- 决策入口
def decide(world: Any, rng: Any, tick: int, ctx: Any, *,
           pack_profiles: dict[str, dict]) -> list[dict]:
    """tick 阶段 [3] 的决策入口：需求 → 效用 → 行为树分支 → intents。

    返回的每条 intent 在 M1 协议之上**额外**带 `decision` 子字典（D-M4-2 的事件来源）；
    日程桩路径不产出该键 ⇒ `tick.py` 只在非空时 emit `npc.decision`。
    """
    # 延迟导入：`tick.py` 在模块级导入本模块 ⇒ 这里若在模块级反向导入会成环。
    # `_step_towards` 是 M1 冻结的整数毫米步进（含 `rng.stream("npc.<id>.move")` 抽取语义），
    # 复用而非复制，避免两处漂移。
    from ..tick import _step_towards

    intents: list[dict] = []
    day_ticks = int(world.constants.get("day_ticks") or (24 * 60))
    for entity in world.query(kind="npc"):  # query 已按 entity id 升序
        profile = pack_profiles.get(entity.id) or {}
        weights = profile.get("need_weights") or {}
        needs = copy.deepcopy(entity.components.get("needs") or {})
        schedule = copy.deepcopy(entity.components.get("schedule") or {})
        schedule_changed = False

        # ① 日程先验：块边界推进（数据驱动，不再是唯一驱动）
        until_tick = schedule.get("until_tick")
        if until_tick is not None and tick >= int(until_tick):
            advanced = _next_block(world.schedule_index.get(entity.id, []), int(until_tick))
            if advanced is not None:
                schedule["entry_id"] = advanced.get("entry_id", schedule.get("entry_id"))
                schedule["state"] = advanced["state"]
                schedule["target_entity"] = advanced.get("target_entity")
                schedule["until_tick"] = int(advanced["end_tick"])
            else:
                schedule["until_tick"] = int(until_tick) + day_ticks
            schedule_changed = True

        state = str(schedule.get("state") or "idle")

        # ② 需求 → 行为树分支 → 候选集（**需求驱动的分支真的会改变候选**）
        #   需求层用「满足度视图 + 归一化权重」⇒ deficit == 压力 × 权重，与效用层**同序**（见桥接口径）
        records = requirement_mod.evaluate(
            satisfaction_view(needs),
            {"weights": normalized_weights(weights), "npc_id": entity.id, "tick": tick},
        )
        dominant = records[0] if records else None
        blackboard = {
            "dominant_need": dominant.need_id if dominant is not None else "physiology",
            "dominant_deficit": dominant.deficit if dominant is not None else 0.0,
            "urgency": dominant.deficit if dominant is not None else 0.0,
            "schedule_state": state,
        }
        branch = branch_of(blackboard)

        # ③ 效用：日程候选（先验/约束）+ 行为树分支追加的候选
        candidates = candidate_actions(state) + branch_candidates(branch, state)
        ranked = utility_mod.score_actions(needs, weights, {"schedule_state": state}, candidates)
        top = ranked[0] if ranked else {"action": "hold", "need": "physiology", "score": 0.0}

        # ④ 动作 × 分支 → 目标解析 → 整数毫米步进
        action = str(top["action"])
        target_entity = _resolve_target(action, branch, entity, world, profile, schedule)
        move_delta = {"x": 0, "y": 0, "z": 0}
        jitter = 0
        if target_entity:
            target = world.get(target_entity)
            if target is not None:
                move_delta, jitter = _step_towards(entity, target, rng)
        moved = any(move_delta.values()) or jitter != 0

        decision = Decision(
            npc_id=entity.id,
            tick=int(tick),
            dominant_need=blackboard["dominant_need"],
            dominant_deficit=_q(blackboard["dominant_deficit"]),
            chosen_action=action,
            utility_score=_q(top["score"]),
            utility_ranking=[{"action": item["action"], "need": item["need"], "score": item["score"]}
                             for item in ranked[:3]],
            bt_branch=branch,
            schedule_state=state,
            target_entity=target_entity,
        )

        intents.append({
            "npc_id": entity.id,
            "action": action if moved else "hold",
            "target_entity": target_entity,
            "move_delta_mm": move_delta,
            "jitter_mm": jitter,
            "needs_delta": _needs_delta(action, needs),
            "schedule": schedule if schedule_changed else None,
            "moved": moved,
            "schedule_changed": schedule_changed,
            "decision": decision.to_payload(),
        })
    return intents


def _next_block(blocks: list[dict], current_until_tick: int) -> dict | None:
    """取「start_tick 严格大于当前 until_tick」中最小的一块（无则 None）。

    与 `tick._next_block` 同语义（本模块自带一份，避免在决策路径上反向依赖 tick 模块的
    模块级符号；顺序由数据决定，非代码分支）。
    """
    candidates = [block for block in blocks if int(block.get("start_tick", 0)) > current_until_tick]
    if not candidates:
        return None
    return min(candidates, key=lambda block: (int(block["start_tick"]), str(block.get("state", ""))))
