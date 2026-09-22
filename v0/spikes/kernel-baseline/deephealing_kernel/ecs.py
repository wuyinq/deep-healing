"""薄 ECS（差异化内核，V0 骨架）。

设计要点：
  - 组件数组 + 实体索引；系统按固定顺序执行（顺序在代码里写死，不依赖字典迭代）；
  - 组件字段由 world.schema.json 冻结；新增组件属内核契约变更（需 ADR）；
  - 查询结果一律**按 entity id 排序**返回，保证迭代顺序确定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

COMPONENTS = (
    "transform",
    "needs",
    "emotion",
    "schedule",
    "relations",
    "memory_ref",
    "trauma_flags",
)


@dataclass(slots=True)
class Entity:
    id: str
    kind: str
    components: dict[str, Any] = field(default_factory=dict)


class World:
    """世界状态容器（唯一写点在 tick 的执行阶段）。"""

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}

    def spawn(self, entity: Entity) -> None:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'ecs'")

    def despawn(self, entity_id: str) -> None:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'ecs'")

    def get(self, entity_id: str) -> Entity | None:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'ecs'")

    def query(self, kind: str | None = None, has: Iterable[str] = ()) -> list[Entity]:
        """按 kind / 组件存在性查询；返回按 entity id 升序排序的列表。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'ecs'")

    def set_component(self, entity_id: str, name: str, value: Any) -> None:
        """**只在执行阶段调用**；越界调用由 Sentinel 的静态/运行时检查拦截。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'ecs'")

    def to_state(self) -> dict:
        """导出为 world.schema.json 兼容的 state（entities 已按 id 排序）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'ecs'")

    def apply_delta(self, ops: list[dict]) -> None:
        """应用 delta 操作（权威侧生成；客户端侧只读消费）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'delta'")

    def systems(self) -> list[Callable[["World"], None]]:
        """固定顺序的系统列表（顺序即契约）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'tick-loop'")
