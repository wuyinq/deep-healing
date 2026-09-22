"""记忆存储（sqlite 三层，V0 骨架）。

表结构（V0 冻结）：
  episodes(npc_id, tick, kind, text_summary, importance, embedding_blob, refs, superseded_by)
  facts(npc_id, key, value, confidence, updated_tick, refs, superseded_by)
  working(npc_id, slot, tick, kind, text_summary)   -- 环形缓冲，容量 = memory_policy.working_capacity

裁剪策略（防无界增长，R10）：重要性阈值 + 时间衰减（decay_half_life_ticks）+ 每 NPC 容量上限。
反思结果必须可回滚：保留 superseded_by，不物理删除。
"""

from __future__ import annotations

from pathlib import Path


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path

    def init_schema(self) -> None:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'memory-store'")

    def append_working(self, npc_id: str, tick: int, kind: str, text_summary: str) -> None:
        """写入短期缓冲（环形，超容量按 tick 最旧淘汰）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'memory-store'")

    def append_episode(
        self, npc_id: str, tick: int, kind: str, text_summary: str, importance: float, refs: list[str]
    ) -> int:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'memory-store'")

    def upsert_fact(self, npc_id: str, key: str, value: str, confidence: float, tick: int, refs: list[str]) -> None:
        """写语义事实；同 key 旧值写 superseded_by（可回滚、可审计）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'memory-store'")

    def prune(self, npc_id: str, tick: int, importance_floor: float) -> int:
        """裁剪：低于阈值 + 超容量 + 时间衰减；返回删除条数。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'memory-store'")
