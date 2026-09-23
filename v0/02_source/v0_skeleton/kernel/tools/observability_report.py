"""观测层（L7 / W9）只读分析报告 —— **纯 Python 实现**（M4 新增）。

**为什么是纯 Python**：本机没有 duckdb CLI，也没有 python `duckdb` 模块（实测：
`python3 -m pip install --no-index duckdb` 在离线环境下不可用）。SQL 文本已交付
（`tools/duckdb_queries.sql`），但**「SQL 文本已写」不等于「查询已跑」** —— 因此本文件用
纯 Python 跑**同语义**的四组分析，并**逐组给出 `sql_equivalent` 口径映射**（可逐条对照）。

四组（与 SQL 文件逐组同序同义）：
  ① `hash_chain`       —— 哈希链自检（0 断链）+ 链尾
  ② `tick_timeline`    —— tick 时间线 / 推进速率 / 每 tick 事件密度
  ③ `event_statistics` —— 事件类型分布 + 体积占比（D-M4-21 的预算输入）
  ④ `npc_behaviour`    —— NPC 行为分布（动作 / 分支 / 主导需求）

**只读纪律**：本文件只 `open(..., "r")`；除 `--out` 指定的报告文件外**不写任何路径**，
也不触碰内核状态（`test_observability.py` 用「分析前后逐字节 sha256 比对」证明）。

用法：
    python3 tools/observability_report.py --events <events.jsonl> [--checkpoints <dir>] [--out <json>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[1]
if str(KERNEL_ROOT) not in sys.path:
    sys.path.insert(0, str(KERNEL_ROOT))

from deephealing_kernel.snapshot import canonical_json, chained_hash, GENESIS_HASH  # noqa: E402

GROUP_KEYS = ("hash_chain", "tick_timeline", "event_statistics", "npc_behaviour")


def _read_events(path: Path) -> tuple[list[dict], list[str]]:
    """逐行读 JSONL（**不**抛异常）：返回 (文档列表, 行级错误列表)。"""
    documents: list[dict] = []
    errors: list[str] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                document = json.loads(text)
            except ValueError as exc:
                errors.append(f"line {lineno}: not JSON ({exc})")
                continue
            if not isinstance(document, dict):
                errors.append(f"line {lineno}: not a JSON object")
                continue
            documents.append(document)
    return documents, errors


# ---------------------------------------------------------------------------- ① 哈希链自检
def hash_chain(documents: list[dict], read_errors: list[str]) -> dict:
    """重算每条事件的 `hash` 并检查 `prev_hash` 链接（与 SQL 第 1 组同语义）。"""
    broken: list[dict] = []
    expected_prev = GENESIS_HASH
    expected_seq = 0
    for index, document in enumerate(documents):
        seq = document.get("seq")
        if seq != expected_seq:
            broken.append({"line_index": index, "seq": seq, "expected_seq": expected_seq,
                           "reason": "seq_gap"})
        prev = document.get("prev_hash")
        if prev != expected_prev:
            broken.append({"line_index": index, "seq": seq, "reason": "prev_hash_mismatch",
                           "prev_hash": prev, "expected_prev": expected_prev})
        recomputed = chained_hash(str(prev), {
            "seq": seq,
            "tick": document.get("tick"),
            "type": document.get("type"),
            "actor": document.get("actor"),
            "payload": document.get("payload"),
        })
        if recomputed != document.get("hash"):
            broken.append({"line_index": index, "seq": seq, "reason": "hash_not_reproducible",
                           "hash": document.get("hash"), "recomputed": recomputed})
        expected_prev = str(document.get("hash"))
        expected_seq = (seq + 1) if isinstance(seq, int) else expected_seq + 1
    return {
        "sql_equivalent": "duckdb_queries.sql 第 1 组：lag(hash) OVER (ORDER BY seq) <> prev_hash",
        "events": len(documents),
        "broken_links": len(broken) + len(read_errors),
        "broken_detail": broken[:20],
        "read_errors": read_errors[:20],
        "chain_tail": expected_prev,
        "last_seq": documents[-1].get("seq") if documents else None,
    }


# ---------------------------------------------------------------------------- ② tick 时间线
def tick_timeline(documents: list[dict]) -> dict:
    """每 tick 的事件密度 + 快照 tick 间隔（与 SQL 第 2 组同语义）。"""
    per_tick: dict[int, Counter] = defaultdict(Counter)
    for document in documents:
        tick = document.get("tick")
        if not isinstance(tick, int):
            continue
        per_tick[tick][str(document.get("type"))] += 1
    snapshot_ticks = sorted(
        int(document["payload"]["snapshot_tick"])
        for document in documents
        if document.get("type") == "snapshot.taken"
        and isinstance(document.get("payload"), dict)
        and isinstance(document["payload"].get("snapshot_tick"), int)
    )
    deltas = [b - a for a, b in zip(snapshot_ticks, snapshot_ticks[1:])]
    return {
        "sql_equivalent": "duckdb_queries.sql 第 2 组：GROUP BY tick + snapshot_tick 的 lag 差",
        "ticks_observed": len(per_tick),
        "first_tick": min(per_tick) if per_tick else None,
        "last_tick": max(per_tick) if per_tick else None,
        "events_per_tick": {str(tick): sum(per_tick[tick].values()) for tick in sorted(per_tick)},
        "snapshot_ticks": snapshot_ticks,
        "snapshot_deltas": deltas,
        "snapshot_delta_uniform": len(set(deltas)) <= 1,
    }


# ---------------------------------------------------------------------------- ③ 事件统计
def event_statistics(documents: list[dict]) -> dict:
    """事件类型分布 + payload 体积占比（与 SQL 第 3 组同语义；D-M4-21 的预算输入）。"""
    counts: Counter = Counter()
    byte_sizes: Counter = Counter()
    spans: dict[str, list[int]] = defaultdict(list)
    total_bytes = 0
    for document in documents:
        event_type = str(document.get("type"))
        counts[event_type] += 1
        size = len(canonical_json(document.get("payload") or {}).encode("utf-8"))
        byte_sizes[event_type] += size
        total_bytes += size
        tick = document.get("tick")
        if isinstance(tick, int):
            spans[event_type].append(tick)
    return {
        "sql_equivalent": "duckdb_queries.sql 第 3 组：GROUP BY type + length(to_json(payload)) 占比",
        "events": len(documents),
        "by_type": {
            event_type: {
                "n": counts[event_type],
                "first_tick": min(spans[event_type]) if spans[event_type] else None,
                "last_tick": max(spans[event_type]) if spans[event_type] else None,
                "payload_bytes": byte_sizes[event_type],
                "payload_pct": round(100.0 * byte_sizes[event_type] / total_bytes, 2) if total_bytes else 0.0,
            }
            for event_type in sorted(counts)
        },
        "payload_bytes_total": total_bytes,
    }


# ---------------------------------------------------------------------------- ④ NPC 行为分布
def npc_behaviour(documents: list[dict]) -> dict:
    """动作 / 分支 / 主导需求分布（与 SQL 第 4 组同语义）。"""
    actions: Counter = Counter()
    branches: Counter = Counter()
    needs: Counter = Counter()
    schedule_driver_rows = 0
    decisions = 0
    for document in documents:
        if document.get("type") != "npc.decision":
            continue
        payload = document.get("payload") or {}
        decisions += 1
        npc_id = str(payload.get("npc_id"))
        actions[f"{npc_id}|{payload.get('chosen_action')}"] += 1
        branches[str(payload.get("bt_branch"))] += 1
        needs[f"{npc_id}|{payload.get('dominant_need')}"] += 1
        if payload.get("schedule_is_driver"):
            schedule_driver_rows += 1
    return {
        "sql_equivalent": "duckdb_queries.sql 第 4 组：GROUP BY npc_id / chosen_action / bt_branch",
        "decisions": decisions,
        "action_distribution": dict(sorted(actions.items())),
        "branch_distribution": dict(sorted(branches.items())),
        "dominant_need_distribution": dict(sorted(needs.items())),
        "schedule_is_driver_rows": schedule_driver_rows,
        "schedule_is_driver_expected": 0,
    }


# ---------------------------------------------------------------------------- 入口
def analyze(events_path: Path, *, checkpoint_dir: Path | None = None) -> dict:
    """跑四组只读分析（**不写任何文件**）。"""
    documents, read_errors = _read_events(Path(events_path))
    report = {
        "schema_version": "1.0.0",
        "tool": "observability_report.py",
        "read_only": True,
        "events_path": str(Path(events_path)),
        "events_sha256": hashlib.sha256(Path(events_path).read_bytes()).hexdigest(),
        "hash_chain": hash_chain(documents, read_errors),
        "tick_timeline": tick_timeline(documents),
        "event_statistics": event_statistics(documents),
        "npc_behaviour": npc_behaviour(documents),
        "duckdb_available": _duckdb_available(),
        "sql_queries_path": str(KERNEL_ROOT / "tools" / "duckdb_queries.sql"),
    }
    if checkpoint_dir is not None:
        checkpoints = sorted(Path(checkpoint_dir).glob("*.json"))
        report["checkpoints"] = {
            "dir": str(Path(checkpoint_dir)),
            "count": len(checkpoints),
            "ticks": [int(path.stem) for path in checkpoints],
        }
    return report


def _duckdb_available() -> dict:
    """如实登记 duckdb 可用性（**不假装跑过**）。"""
    try:
        import duckdb  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return {"module": False, "reason": f"{type(exc).__name__}: {exc}"}
    return {"module": True, "reason": None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="observability_report")
    parser.add_argument("--events", required=True)
    parser.add_argument("--checkpoints", default=None)
    parser.add_argument("--out", default=None, help="报告输出路径（缺省 = stdout）")
    args = parser.parse_args(argv)

    events_path = Path(args.events)
    if not events_path.exists():
        print(f"E_EVENTS_NOT_FOUND: {events_path.name}", file=sys.stderr)
        return 1
    report = analyze(events_path,
                     checkpoint_dir=Path(args.checkpoints) if args.checkpoints else None)
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
