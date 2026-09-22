"""记忆检索（V0 骨架）。

V0：sqlite 读出候选 + numpy 余弦相似度；嵌入由 embed.text 能力产出
（provider 可为远端 / 本地 / 确定性哈希回退）。
V1 评估 sqlite-vec / LanceDB（见 07_adr.md ADR-004）。

确定性要求：检索排序必须显式 tie-break（相似度 → tick → ref），禁止依赖 dict/set 迭代顺序。
"""

from __future__ import annotations

from typing import Any


def retrieve(store: Any, npc_id: str, query_vector: list[float], top_k: int = 8) -> list[dict]:
    """返回 top_k 条记忆（按 相似度 desc, tick desc, ref asc 排序）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'memory-retrieve'")


def cosine(a: list[float], b: list[float]) -> float:
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'memory-retrieve'")


def should_reflect(npc_id: str, tick: int, policy: dict, last_reflect_tick: int | None) -> bool:
    """反思触发：日程点（reflect_at）或 importance 阈值；判定必须纯函数。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'memory-retrieve'")
