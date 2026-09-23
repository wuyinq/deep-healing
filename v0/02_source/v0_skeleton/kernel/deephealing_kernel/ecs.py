"""薄 ECS（差异化内核，V0-M1 实现）。

设计要点：
  - 组件数组 + 实体索引；系统按固定顺序执行（顺序在代码里写死，不依赖字典迭代）；
  - 组件字段由 world.schema.json 冻结；新增组件属内核契约变更（需 ADR）；
  - 查询结果一律**按 entity id 排序**返回，保证迭代顺序确定。

M1 实现口径：
  - `query()` 遍历 `sorted(self._entities)`（**不是** dict 迭代顺序）；
  - `to_state()` 只导出 world.schema.json 允许的键，且对 `entities` / `trauma_flags` / `tags` /
    `memory_ref.fact_keys` 四项按 `snapshot.schema.json` 的 `normalization.sort_arrays` 显式排序
    （**修复轮 2 / G4 / Raven R22.3**：原先此处写的 `traversal_flags` 是**不存在**的字段——
    `world.schema.json` / `snapshot.schema.json` / 内核代码里 grep 均 0 命中；`sort_arrays` 实际只有上述四项）；
  - `weather` 是**内容包元数据**，不进内核状态（有意丢弃，见 pack.py 的显式断言与 06 记录）。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .snapshot import canonical_json

COMPONENTS = (
    "transform",
    "needs",
    "emotion",
    "schedule",
    "relations",
    "memory_ref",
    "trauma_flags",
)

# `world.schema.json` 的 entity 允许键里，除 `id` / `kind` 与上面 7 个组件外只有 `tags`。
# 它不是「组件」（不入 COMPONENTS，避免改冻结骨架的语义），但**必须**参与 state 导出与写入，
# 否则内容包声明的 tags 会被静默丢弃（state 与 seed 不等价 ⇒ 数据丢失）。
SCALAR_ENTITY_KEYS = ("tags",)
ENTITY_KEYS = COMPONENTS + SCALAR_ENTITY_KEYS


@dataclass(slots=True)
class Entity:
    id: str
    kind: str
    components: dict[str, Any] = field(default_factory=dict)


def _q(value: float) -> float:
    """6 位小数量化（与 `rules.decision._q` 同口径；关系值不得引入浮点末位噪声）。"""
    return round(float(value), 6)


def _normalize_component(name: str, value: Any) -> Any:
    """按 normalization.sort_arrays 显式排序（禁止依赖插入/迭代顺序）。"""
    if name == "tags":
        return sorted(str(item) for item in value)
    if name == "relations":
        return {key: value[key] for key in sorted(value)}
    if name == "trauma_flags":
        # **全序**排序键（修复轮 B1 / 预审 R3）：原键 `(id, since_tick, severity)` 在「三者相同、
        # 仅 `healed_tick` 不同」的两条上**平局**，而 `sorted` 稳定 ⇒ 平局顺序由**输入顺序**决定
        # ⇒ 同一逻辑状态两种 `state_hash`（违反确定性内核的核心不变量）。
        # 改用**契约序列化本身**作键：天然全序（字符串比较），且与 snapshot 的序列化同源。
        return sorted((copy.deepcopy(item) for item in value), key=canonical_json)
    if name == "memory_ref":
        item = copy.deepcopy(value)
        if "fact_keys" in item and item["fact_keys"] is not None:
            item["fact_keys"] = sorted(str(key) for key in item["fact_keys"])
        return item
    return copy.deepcopy(value)


class World:
    """世界状态容器（唯一写点在 tick 的执行阶段）。"""

    def __init__(self, seed: int = 0, constants: dict | None = None) -> None:
        self._entities: dict[str, Entity] = {}
        self._pending: list[dict] = []
        self.seed = seed
        self.constants: dict = dict(constants) if constants else {}
        self.tick = 0
        # `npc_id -> 日程块列表`（内容包驱动；由内核在建世界时注入，见 tick.build_schedule_index）
        self.schedule_index: dict[str, list[dict]] = {}
        # **M5.2 r1**：本 tick **实际写入**的关系变更（由 `system_relations` 填充、[5] 记账段读取 emit）。
        # 它是「读了实际写点」的凭据，不是 decide 阶段的自报值。
        self.relation_changes: list[dict] = []

    # ------------------------------------------------------------------ 实体
    def spawn(self, entity: Entity) -> None:
        if entity.id in self._entities:
            raise ValueError(f"duplicate entity id: {entity.id}")
        self._entities[entity.id] = entity

    def despawn(self, entity_id: str) -> None:
        self._entities.pop(entity_id, None)

    def get(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def query(self, kind: str | None = None, has: Iterable[str] = ()) -> list[Entity]:
        """按 kind / 组件存在性查询；返回按 entity id 升序排序的列表。"""
        required = tuple(sorted(has))
        result: list[Entity] = []
        for entity_id in sorted(self._entities):  # 显式升序，禁止 dict 迭代顺序
            entity = self._entities[entity_id]
            if kind is not None and entity.kind != kind:
                continue
            if any(name not in entity.components for name in required):
                continue
            result.append(entity)
        return result

    def set_component(self, entity_id: str, name: str, value: Any) -> None:
        """**只在执行阶段调用**；越界调用由 Sentinel 的静态/运行时检查拦截。"""
        entity = self._entities.get(entity_id)
        if entity is None:
            raise KeyError(f"unknown entity: {entity_id}")
        if name not in ENTITY_KEYS:
            raise ValueError(f"unknown component {name!r} (new components require an ADR)")
        entity.components[name] = value

    # ------------------------------------------------------------------ 意图暂存
    def stage_intents(self, intents: list[dict]) -> None:
        """decide 阶段暂存意图（只读上下文；真正写世界在 execute 阶段）。"""
        self._pending = list(intents)

    def pending_intents(self) -> list[dict]:
        return list(self._pending)

    def clear_intents(self) -> None:
        self._pending = []

    # ------------------------------------------------------------------ 状态导出
    def to_state(self) -> dict:
        """导出为 world.schema.json 兼容的 state（entities 已按 id 排序）。"""
        entities: list[dict] = []
        for entity in self.query():
            item: dict[str, Any] = {"id": entity.id, "kind": entity.kind}
            for name in ENTITY_KEYS:
                if name in entity.components:
                    item[name] = _normalize_component(name, entity.components[name])
            entities.append(item)
        return {
            "schema_version": "1.0.0",
            "seed": self.seed,
            "tick": self.tick,
            "constants": copy.deepcopy(self.constants),
            "entities": entities,
        }

    def apply_delta(self, ops: list[dict]) -> None:
        """应用 delta 操作（权威侧生成；客户端侧只读消费）。"""
        for op in ops:
            kind = op.get("op")
            if kind == "set_component":
                self.set_component(op["entity"], op["name"], op["value"])
            elif kind == "despawn":
                self.despawn(op["entity"])
            elif kind == "spawn":
                self.spawn(Entity(id=op["id"], kind=op["kind"], components=dict(op.get("components", {}))))
            else:
                raise ValueError(f"unknown delta op: {kind!r}")

    def systems(self) -> list[Callable[["World"], None]]:
        """固定顺序的系统列表（顺序即契约）。"""
        return list(SYSTEMS)


# ---------------------------------------------------------------------- 系统（固定顺序）
def system_schedule(world: World) -> None:
    """系统 1：按 decide 阶段暂存的意图推进日程边界（写 schedule 组件）。"""
    for intent in world.pending_intents():
        schedule = intent.get("schedule")
        if schedule is not None:
            world.set_component(intent["npc_id"], "schedule", dict(schedule))


def system_relations(world: World) -> None:
    """系统 1b（**M5.2 r1 新增**）：应用 decide 阶段暂存的关系（友善度）增量（写 `relations` 组件）。

    **C-1 口径（Raven 预审 CRITICAL，硬性）**：`relations` 的值形状**保持数值标量**
    `{peer_id: number ∈ [-1,1]}`（`world.schema.json#/$defs/relations` 冻结；改成对象形状会直接让
    `test_state_passes_world_schema` 变红，那是**真回归**）。`updated_tick` / `source_event`
    **不进组件**，只进 `relation.changed` 事件（由 [5] 记账段读取本函数填充的
    `world.relation_changes` 后 emit）——「为什么变了」由**事件记录**回答。

    放在 `system_movement` **之前**：后者末尾会 `clear_intents()`，之后就读不到暂存意图了。
    """
    world.relation_changes = []
    for intent in world.pending_intents():
        delta = intent.get("relations_delta")
        if not isinstance(delta, dict) or not delta:
            continue
        npc_id = intent["npc_id"]
        entity = world.get(npc_id)
        if entity is None:
            continue
        relations = dict(entity.components.get("relations") or {})
        changed = False
        for peer_id in sorted(delta):
            amount = delta[peer_id]
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount == 0:
                continue
            raw_before = relations.get(peer_id, 0.0)
            before = float(raw_before) if isinstance(raw_before, (int, float)) \
                and not isinstance(raw_before, bool) else 0.0
            after = _q(min(1.0, max(-1.0, before + float(amount))))
            if after == before:
                continue
            relations[peer_id] = after
            changed = True
            world.relation_changes.append({
                "npc_id": npc_id,
                "peer_npc_id": str(peer_id),
                "from": _q(before),
                "to": after,
                "tick": int(world.tick),
                "source_event": str(intent.get("relation_source_event") or "npc.action"),
            })
        if changed:
            world.set_component(npc_id, "relations", relations)


def system_movement(world: World) -> None:
    """系统 2：按 decide 阶段暂存的意图朝 target 走一步（写 transform / needs 组件）。"""
    for intent in world.pending_intents():
        npc_id = intent["npc_id"]
        entity = world.get(npc_id)
        if entity is None:
            continue
        delta = intent.get("move_delta_mm")
        jitter = int(intent.get("jitter_mm", 0))
        if delta or jitter:
            transform = copy.deepcopy(entity.components.get("transform") or {"pos_mm": {"x": 0, "y": 0, "z": 0}})
            pos = transform.setdefault("pos_mm", {"x": 0, "y": 0, "z": 0})
            pos["x"] = int(pos.get("x", 0)) + int((delta or {}).get("x", 0)) + jitter
            pos["y"] = int(pos.get("y", 0)) + int((delta or {}).get("y", 0))
            pos["z"] = int(pos.get("z", 0)) + int((delta or {}).get("z", 0))
            world.set_component(npc_id, "transform", transform)
        needs_delta = intent.get("needs_delta")
        if needs_delta:
            needs = copy.deepcopy(entity.components.get("needs") or {})
            for key in sorted(needs_delta):
                if key not in needs:
                    continue
                needs[key] = min(1.0, max(0.0, float(needs[key]) + float(needs_delta[key])))
            world.set_component(npc_id, "needs", needs)
    world.clear_intents()


SYSTEMS: tuple[Callable[[World], None], ...] = (system_schedule, system_relations, system_movement)
