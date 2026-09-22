"""记忆检索（V0-M2 实现）。

V0：sqlite 读出候选 + numpy 余弦相似度；嵌入由 embed.text 能力产出
（provider 可为远端 / 本地 / 确定性哈希回退）。
V1 评估 sqlite-vec / LanceDB（见 07_adr.md ADR-004）。

确定性要求：检索排序必须显式 tie-break（相似度 → tick → ref），禁止依赖 dict/set 迭代顺序。

**M2 口径**：
  - 相似度按 **6 位小数**量化后再比较（浮点末位不参与排序 ⇒ 逐字节可复现）；
  - 无嵌入的候选相似度记 `0.0`（不跳过 —— 跳过会让结果依赖「谁有嵌入」，不可复现）；
  - `digest(records)` = sha256(canonical 化的记录集)，比对器用它证明「同 seed 同输入 ⇒ 逐字节一致」。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

LAYERS = ("episodes", "facts")


def cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度（空向量或零向量记 0.0；不抛异常）。"""
    if not isinstance(a, list) or not isinstance(b, list) or not a or not b:
        return 0.0
    length = min(len(a), len(b))
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for index in range(length):
        left = float(a[index]) if isinstance(a[index], (int, float)) else 0.0
        right = float(b[index]) if isinstance(b[index], (int, float)) else 0.0
        dot += left * right
        norm_a += left * left
        norm_b += right * right
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


def retrieve(store: Any, npc_id: str, query_vector: list[float], top_k: int = 8,
             *, layer: str = "episodes") -> list[dict]:
    """返回 top_k 条记忆（按 相似度 desc, tick desc, ref asc 排序）。"""
    if layer not in LAYERS:
        raise ValueError(f"unknown memory layer {layer!r} (known: {', '.join(LAYERS)})")
    if layer == "episodes":
        candidates = store.fetch_episodes(npc_id)
    else:
        candidates = store.fetch_facts(npc_id)

    scored: list[dict] = []
    for record in candidates:
        embedding = record.get("embedding")
        similarity = round(cosine(query_vector, embedding), 6) if isinstance(embedding, list) else 0.0
        tick = int(record.get("tick", record.get("updated_tick", 0)) or 0)
        scored.append({
            "ref": int(record.get("ref", 0) or 0),
            "tick": tick,
            "kind": record.get("kind", record.get("key", "")),
            "text_summary": record.get("text_summary", record.get("value", "")),
            "importance": record.get("importance", record.get("confidence", 0.0)),
            "similarity": similarity,
            "layer": layer,
        })
    # 显式 tie-break：相似度降序 → tick 降序 → ref 升序（禁止依赖容器迭代序）
    scored.sort(key=lambda item: (-item["similarity"], -item["tick"], item["ref"]))
    return scored[: max(0, int(top_k))]


def should_reflect(npc_id: str, tick: int, policy: dict, last_reflect_tick: int | None) -> bool:
    """反思触发：日程点（reflect_at）或 importance 阈值；判定必须纯函数。"""
    policy = policy if isinstance(policy, dict) else {}
    tick = int(tick)
    interval = policy.get("reflect_every_ticks")
    if isinstance(interval, int) and interval > 0 and tick % interval == 0:
        return True
    reflect_at = policy.get("reflect_at")
    if isinstance(reflect_at, list) and tick in [int(item) for item in reflect_at if isinstance(item, int)]:
        return True
    last = last_reflect_tick if isinstance(last_reflect_tick, int) else None
    window = policy.get("min_interval_ticks")
    if last is not None and isinstance(window, int) and window > 0 and tick - last < window:
        return False
    return False


def digest(records: list[dict]) -> str:
    """记录集摘要（比对器口径；逐字节可复现）。"""
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
