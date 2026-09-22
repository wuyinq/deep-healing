"""W5 / AC-M2-5：记忆三层真跑 + 内核唯一写入点 + 检索逐字节可复现。

运行：
    cd <workspace>/02_source/v0_skeleton/kernel && \
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_memory_layers.py -q -p no:cacheprovider

判据（设计 §3.3 / §3.4b(5)）：
  1. 短期 / 长期 / 反思三层真跑（`working` / `episodes` / `facts`）；
  2. 写入经**内核唯一写入点**；**默认 flag 关闭时零写入**；
  3. 同 seed 同输入 ⇒ 检索结果**逐字节一致**（比对器 = `digest`）；
  4. `prune` 后容量不超上限、旧事实保留 `superseded_by`（软删，不物理删除）；
  5. **负例自证**：改 tie-break 顺序 ⇒ 比对器必须报不一致。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deephealing_kernel.memory import retrieve as retrieve_mod
from deephealing_kernel.memory.store import MemoryStore

EPISODES = [
    {"tick": 10, "kind": "visit", "text_summary": "去看了老张", "importance": 0.8, "refs": ["tick:10"]},
    {"tick": 12, "kind": "meal", "text_summary": "一起吃饭", "importance": 0.5, "refs": ["tick:12"]},
    {"tick": 12, "kind": "talk", "text_summary": "聊了很久", "importance": 0.9, "refs": ["tick:12"]},
]


def _seed_store(path: Path, *, enabled: bool = True, capacity: int = 256) -> MemoryStore:
    store = MemoryStore(path, write_enabled=enabled, episode_capacity=capacity)
    store.init_schema()
    for index, item in enumerate(EPISODES):
        store.remember("episodes", {"npc_id": "npc-001", **item, "embedding": [1.0, 0.0, float(index)]})
    store.remember("working", {"npc_id": "npc-001", "tick": 10, "kind": "visit", "text_summary": "去看了老张"})
    store.remember("working", {"npc_id": "npc-001", "tick": 11, "kind": "walk", "text_summary": "在院子里走"})
    store.upsert_fact("npc-001", "resident.name", "老张", 0.9, 10, ["tick:10"])
    store.upsert_fact("npc-001", "resident.mood", "平静", 0.7, 11, ["tick:11"])
    return store


# --------------------------------------------------------------------------- 三层
def test_three_layers_round_trip(tmp_path):
    store = _seed_store(tmp_path / "memory.sqlite")
    counts = store.layer_counts("npc-001")
    assert counts["working"]["total"] == 2
    assert counts["episodes"]["total"] == 3
    assert counts["facts"]["total"] == 2
    assert store.fetch_episodes("npc-001")[0]["tick"] == 12  # ORDER BY tick DESC, ref DESC
    assert [fact["key"] for fact in store.fetch_facts("npc-001")] == ["resident.mood", "resident.name"]

    # 反向对照：空库必须真的空（证明上面不是「恒有数据」）
    empty = MemoryStore(tmp_path / "empty.sqlite")
    empty.init_schema()
    assert empty.layer_counts("npc-001")["episodes"]["total"] == 0


def test_writes_are_off_by_default(tmp_path):
    """**默认 flag 关闭 ⇒ 零写入**（设计 §3.4b(5)）。"""
    path = tmp_path / "off.sqlite"
    store = MemoryStore(path, write_enabled=False)
    store.init_schema()
    assert store.remember("episodes", {"npc_id": "npc-001", **EPISODES[0]}) is None
    assert store.append_episode("npc-001", 1, "k", "t", 0.9, []) == 0
    store.upsert_fact("npc-001", "k", "v", 1.0, 1, [])
    assert store.prune("npc-001", 10, 0.9) == 0
    assert store.write_count == 0
    assert store.layer_counts("npc-001")["episodes"]["total"] == 0

    # 反向对照：打开 flag 后同样的调用必须真的写进去（证明「零写入」不是恒零）
    enabled = MemoryStore(path, write_enabled=True)
    enabled.init_schema()
    enabled.remember("episodes", {"npc_id": "npc-001", **EPISODES[0]})
    assert enabled.layer_counts("npc-001")["episodes"]["total"] == 1


def test_retrieval_is_byte_identical(tmp_path):
    """同 seed 同输入 ⇒ 检索结果**逐字节一致**（比对器口径）。"""
    first = _seed_store(tmp_path / "a.sqlite")
    second = _seed_store(tmp_path / "b.sqlite")
    query = [1.0, 0.0, 2.0]

    left = retrieve_mod.retrieve(first, "npc-001", query, top_k=8)
    right = retrieve_mod.retrieve(second, "npc-001", query, top_k=8)
    assert retrieve_mod.digest(left) == retrieve_mod.digest(right)
    assert left == right
    # 排序键：相似度降序 → tick 降序 → ref 升序（逐对校验，避免只看首条）
    assert [item["tick"] for item in left] == [12, 12, 10]
    for previous, current in zip(left, left[1:]):
        assert (-previous["similarity"], -previous["tick"], previous["ref"]) \
            <= (-current["similarity"], -current["tick"], current["ref"])

    # 强制并列（同相似度 + 同 tick）⇒ ref 升序必须生效（tie-break 真的可达）
    class _TiedStore:
        def fetch_episodes(self, npc_id):
            return [
                {"ref": 9, "tick": 5, "kind": "k", "text_summary": "b", "importance": 0.5, "embedding": [1.0, 0.0]},
                {"ref": 3, "tick": 5, "kind": "k", "text_summary": "a", "importance": 0.5, "embedding": [1.0, 0.0]},
            ]

    tied = retrieve_mod.retrieve(_TiedStore(), "npc-001", [1.0, 0.0], top_k=2)
    assert [item["ref"] for item in tied] == [3, 9]

    # 负例自证：改 tie-break 顺序 ⇒ 比对器必须报不一致
    mutated = sorted(left, key=lambda item: (item["similarity"], item["tick"], item["ref"]))
    assert retrieve_mod.digest(mutated) != retrieve_mod.digest(left)

    # 负例自证 2：把结果顺序整体倒置（= 依赖容器迭代序的典型形态）⇒ 同样报不一致
    reversed_list = list(reversed(left))
    assert reversed_list != left
    assert retrieve_mod.digest(reversed_list) != retrieve_mod.digest(left)


def test_prune_is_soft_and_bounded(tmp_path):
    """`prune` 只软删（保留 `superseded_by`），且容量不超上限。"""
    store = MemoryStore(tmp_path / "prune.sqlite", episode_capacity=2)
    store.init_schema()
    for index in range(5):
        store.append_episode("npc-001", index, "k", f"episode-{index}", 0.9, [])
    pruned = store.prune("npc-001", 5, 0.95)   # 阈值高于全部 importance ⇒ 只由容量裁剪生效
    assert pruned >= 3
    active = store.fetch_episodes("npc-001")
    assert len(active) <= 2
    # 软删：被裁的记录**仍然在库**，且带 superseded_by
    all_records = store.fetch_episodes("npc-001", include_superseded=True)
    assert len(all_records) == 5
    assert any(record["superseded_by"] is not None for record in all_records)

    # 反向对照：物理删除的实现会让 include_superseded=True 也只剩 ≤2 条
    assert len(all_records) != len(active)


def test_fact_supersede_keeps_history(tmp_path):
    store = _seed_store(tmp_path / "facts.sqlite")
    store.upsert_fact("npc-001", "resident.mood", "安心", 0.8, 20, ["tick:20"])
    active = store.fetch_facts("npc-001")
    assert [fact["value"] for fact in active if fact["key"] == "resident.mood"] == ["安心"]
    history = [fact for fact in store.fetch_facts("npc-001", include_superseded=True)
               if fact["key"] == "resident.mood"]
    assert len(history) == 2
    old = [fact for fact in history if fact["value"] == "平静"][0]
    new = [fact for fact in history if fact["value"] == "安心"][0]
    assert old["superseded_by"] == new["ref"]

    # 反向对照：改回「物理删除」形态 ⇒ 历史条数会塌成 1（本断言必红）
    assert len(history) != 1


def test_working_is_a_ring_buffer(tmp_path):
    store = MemoryStore(tmp_path / "ring.sqlite", working_capacity=3)
    store.init_schema()
    for tick in range(6):
        store.append_working("npc-001", tick, "k", f"w{tick}")
    kept = store.fetch_working("npc-001")
    assert len(kept) == 3
    assert [item["tick"] for item in kept] == [3, 4, 5]   # 淘汰最旧
    # 反向对照：容量大于写入量时不得淘汰（证明淘汰只在超容量时发生）
    store.append_working("npc-002", 0, "k", "w0")
    assert len(store.fetch_working("npc-002")) == 1


def test_should_reflect_is_pure():
    policy = {"reflect_every_ticks": 50, "reflect_at": [7, 19], "min_interval_ticks": 5}
    assert retrieve_mod.should_reflect("npc-001", 50, policy, None) is True
    assert retrieve_mod.should_reflect("npc-001", 7, policy, None) is True
    assert retrieve_mod.should_reflect("npc-001", 8, policy, None) is False
    # 反向对照：两个不同输入必须给出不同结果（证明不是恒真/恒假）
    assert retrieve_mod.should_reflect("npc-001", 50, policy, None) != \
        retrieve_mod.should_reflect("npc-001", 8, policy, None)


def test_cosine_edges():
    assert retrieve_mod.cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert retrieve_mod.cosine([], [1.0]) == 0.0
    assert retrieve_mod.cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
    # 反向对照：正交向量不得被判为相似
    assert retrieve_mod.cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
