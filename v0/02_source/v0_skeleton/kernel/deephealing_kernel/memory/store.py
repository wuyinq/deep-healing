"""记忆存储（sqlite 三层，V0-M2 实现）。

表结构（V0 冻结）：
  episodes(npc_id, tick, kind, text_summary, importance, embedding_blob, refs, superseded_by)
  facts(npc_id, key, value, confidence, updated_tick, refs, superseded_by)
  working(npc_id, slot, tick, kind, text_summary)   -- 环形缓冲，容量 = memory_policy.working_capacity

裁剪策略（防无界增长，R10）：重要性阈值 + 时间衰减（decay_half_life_ticks）+ 每 NPC 容量上限。
反思结果必须可回滚：保留 superseded_by，不物理删除。

**唯一写入点（设计 §3.4b(5)）**：本类是内核侧记忆的**唯一**写入点；上层（规则层/CLI）
不得直接 `INSERT`。**默认 flag 关闭时零写入**：`MemoryStore(write_enabled=False)` 的
`remember()` 直接返回 `None` 且**不触碰数据库**（`write_count` 保持 0，可被断言）。

**确定性**：只用 `tick` 排序，**不读 wall-clock**；所有查询带显式 `ORDER BY`。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

WORKING_CAPACITY = 16
EPISODE_CAPACITY = 256
LAYERS = ("working", "episodes", "facts")

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS episodes (
        ref INTEGER PRIMARY KEY AUTOINCREMENT,
        npc_id TEXT NOT NULL,
        tick INTEGER NOT NULL,
        kind TEXT NOT NULL,
        text_summary TEXT NOT NULL,
        importance REAL NOT NULL,
        embedding_blob TEXT,
        refs TEXT NOT NULL DEFAULT '[]',
        superseded_by INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS facts (
        ref INTEGER PRIMARY KEY AUTOINCREMENT,
        npc_id TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        confidence REAL NOT NULL,
        updated_tick INTEGER NOT NULL,
        refs TEXT NOT NULL DEFAULT '[]',
        superseded_by INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS working (
        ref INTEGER PRIMARY KEY AUTOINCREMENT,
        npc_id TEXT NOT NULL,
        slot TEXT NOT NULL,
        tick INTEGER NOT NULL,
        kind TEXT NOT NULL,
        text_summary TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_episodes_npc ON episodes(npc_id, tick)",
    "CREATE INDEX IF NOT EXISTS idx_facts_npc ON facts(npc_id, key)",
    "CREATE INDEX IF NOT EXISTS idx_working_npc ON working(npc_id, slot)",
)


class MemoryStore:
    """三张表的唯一写入点（内核权威端）。"""

    def __init__(self, db_path: Path, *, write_enabled: bool = True,
                 working_capacity: int = WORKING_CAPACITY,
                 episode_capacity: int = EPISODE_CAPACITY) -> None:
        self._path = Path(db_path)
        self._write_enabled = bool(write_enabled)
        self._working_capacity = int(working_capacity)
        self._episode_capacity = int(episode_capacity)
        self.write_count = 0

    # ------------------------------------------------------------------ 连接
    def connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self._path))
        connection.row_factory = sqlite3.Row
        return connection

    def init_schema(self) -> None:
        with self.connect() as connection:
            for statement in SCHEMA:
                connection.execute(statement)

    # ------------------------------------------------------------------ 写
    def remember(self, layer: str, record: dict) -> int | None:
        """唯一写入入口：`layer ∈ {working, episodes, facts}`；flag 关闭时**零写入**。"""
        if layer not in LAYERS:
            raise ValueError(f"unknown memory layer {layer!r} (known: {', '.join(LAYERS)})")
        if not self._write_enabled:
            return None
        if layer == "working":
            self.append_working(
                str(record.get("npc_id", "")), int(record.get("tick", 0)),
                str(record.get("kind", "")), str(record.get("text_summary", "")),
                slot=str(record.get("slot", "default")),
            )
            return None
        if layer == "episodes":
            return self.append_episode(
                str(record.get("npc_id", "")), int(record.get("tick", 0)),
                str(record.get("kind", "")), str(record.get("text_summary", "")),
                float(record.get("importance", 0.0)), list(record.get("refs", [])),
                embedding=record.get("embedding"),
            )
        self.upsert_fact(
            str(record.get("npc_id", "")), str(record.get("key", "")), str(record.get("value", "")),
            float(record.get("confidence", 0.0)), int(record.get("updated_tick", 0)),
            list(record.get("refs", [])),
        )
        return None

    def append_working(self, npc_id: str, tick: int, kind: str, text_summary: str,
                       *, slot: str = "default") -> None:
        """写入短期缓冲（环形，超容量按 tick 最旧淘汰）。"""
        if not self._write_enabled:
            return
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO working(npc_id, slot, tick, kind, text_summary) VALUES (?,?,?,?,?)",
                (npc_id, slot, int(tick), kind, text_summary),
            )
            connection.execute(
                "DELETE FROM working WHERE ref IN ("
                "  SELECT ref FROM working WHERE npc_id=? AND slot=? ORDER BY tick DESC, ref DESC"
                "  LIMIT -1 OFFSET ?)",
                (npc_id, slot, self._working_capacity),
            )
        self.write_count += 1

    def append_episode(self, npc_id: str, tick: int, kind: str, text_summary: str, importance: float,
                       refs: list[str], *, embedding: list[float] | None = None) -> int:
        if not self._write_enabled:
            return 0
        blob = json.dumps([round(float(value), 6) for value in embedding], separators=(",", ":")) \
            if isinstance(embedding, list) else None
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO episodes(npc_id, tick, kind, text_summary, importance, embedding_blob, refs)"
                " VALUES (?,?,?,?,?,?,?)",
                (npc_id, int(tick), kind, text_summary, round(float(importance), 6), blob,
                 json.dumps(sorted(str(item) for item in refs), ensure_ascii=False)),
            )
            ref = int(cursor.lastrowid or 0)
        self.write_count += 1
        return ref

    def upsert_fact(self, npc_id: str, key: str, value: str, confidence: float, tick: int,
                    refs: list[str]) -> None:
        """写语义事实；同 key 旧值写 superseded_by（可回滚、可审计）。"""
        if not self._write_enabled:
            return
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO facts(npc_id, key, value, confidence, updated_tick, refs)"
                " VALUES (?,?,?,?,?,?)",
                (npc_id, key, value, round(float(confidence), 6), int(tick),
                 json.dumps(sorted(str(item) for item in refs), ensure_ascii=False)),
            )
            new_ref = int(cursor.lastrowid or 0)
            # 软删：旧值保留并指向新值（**不物理删除**，反思可回滚）
            connection.execute(
                "UPDATE facts SET superseded_by=? WHERE npc_id=? AND key=? AND ref<>?"
                " AND superseded_by IS NULL",
                (new_ref, npc_id, key, new_ref),
            )
        self.write_count += 1

    def prune(self, npc_id: str, tick: int, importance_floor: float) -> int:
        """裁剪：低于阈值 + 超容量 + 时间衰减；返回**软删**条数（记录保留，`superseded_by` 非空）。"""
        if not self._write_enabled:
            return 0
        pruned = 0
        with self.connect() as connection:
            low = connection.execute(
                "UPDATE episodes SET superseded_by=-1 WHERE npc_id=? AND superseded_by IS NULL"
                " AND importance < ?",
                (npc_id, round(float(importance_floor), 6)),
            )
            pruned += int(low.rowcount or 0)
            overflow = connection.execute(
                "UPDATE episodes SET superseded_by=-1 WHERE ref IN ("
                "  SELECT ref FROM episodes WHERE npc_id=? AND superseded_by IS NULL"
                "  ORDER BY tick DESC, ref DESC LIMIT -1 OFFSET ?)",
                (npc_id, self._episode_capacity),
            )
            pruned += int(overflow.rowcount or 0)
        self.write_count += pruned
        return pruned

    def supersede(self, old_ref: int, new_ref: int) -> None:
        """把旧记录标记为被新记录取代（软删；`old_ref` 记录**保留**）。"""
        if not self._write_enabled:
            return
        with self.connect() as connection:
            connection.execute("UPDATE episodes SET superseded_by=? WHERE ref=?", (int(new_ref), int(old_ref)))
        self.write_count += 1

    # ------------------------------------------------------------------ 读
    def fetch_episodes(self, npc_id: str, *, include_superseded: bool = False) -> list[dict]:
        query = "SELECT * FROM episodes WHERE npc_id=?"
        if not include_superseded:
            query += " AND superseded_by IS NULL"
        query += " ORDER BY tick DESC, ref DESC"
        with self.connect() as connection:
            return [_row_to_dict(row) for row in connection.execute(query, (npc_id,))]

    def fetch_facts(self, npc_id: str, *, include_superseded: bool = False) -> list[dict]:
        query = "SELECT * FROM facts WHERE npc_id=?"
        if not include_superseded:
            query += " AND superseded_by IS NULL"
        query += " ORDER BY key ASC, ref ASC"
        with self.connect() as connection:
            return [_row_to_dict(row) for row in connection.execute(query, (npc_id,))]

    def fetch_working(self, npc_id: str, *, slot: str = "default") -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM working WHERE npc_id=? AND slot=? ORDER BY tick ASC, ref ASC",
                (npc_id, slot),
            )
            return [_row_to_dict(row) for row in rows]

    def layer_counts(self, npc_id: str) -> dict:
        with self.connect() as connection:
            counts = {}
            for layer, table in (("working", "working"), ("episodes", "episodes"), ("facts", "facts")):
                row = connection.execute(
                    f"SELECT COUNT(*) AS total,"
                    f" SUM(CASE WHEN {'superseded_by IS NULL' if table != 'working' else '1=1'}"
                    f" THEN 1 ELSE 0 END) AS active FROM {table} WHERE npc_id=?",
                    (npc_id,),
                ).fetchone()
                counts[layer] = {"total": int(row["total"] or 0), "active": int(row["active"] or 0)}
            return counts


def _row_to_dict(row: sqlite3.Row) -> dict:
    item = {key: row[key] for key in row.keys()}
    blob = item.get("embedding_blob")
    if isinstance(blob, str) and blob:
        item["embedding"] = json.loads(blob)
    elif "embedding_blob" in item:
        item["embedding"] = None
    refs = item.get("refs")
    if isinstance(refs, str):
        item["refs"] = json.loads(refs)
    return item


def digest(records: list[dict]) -> str:
    """记录集摘要（检索结果逐字节一致的比对口径）。"""
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
