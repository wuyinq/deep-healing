-- 观测层（L7 / W9）只读分析查询 —— **M4 新增**。
-- 运行（需 duckdb；本机不可用，见 06_v0_m4_self_test.md 的 GAP 登记）：
--   duckdb -c ".read tools/duckdb_queries.sql"        （工作目录需能解析 events.jsonl 路径）
--
-- **口径映射（与 `observability_report.py` 逐组同语义）**：
--   ① hash_chain        ↔ 本文件第 1 组（哈希链自检：任何断链都是 CRITICAL）
--   ② tick_timeline     ↔ 本文件第 2 组（tick 时间线 / 推进速率 / 每 tick 事件密度）
--   ③ event_statistics  ↔ 本文件第 3 组（事件类型分布 + `npc.decision` 体积占比）
--   ④ npc_behaviour     ↔ 本文件第 4 组（NPC 行为分布：动作 / 分支 / 主导需求）
--
-- 只读保证：全部语句都是 SELECT / WITH … SELECT，**没有** INSERT/UPDATE/DELETE/COPY/CREATE。
-- 分析**不写**内核状态：事件日志与检查点在分析前后逐字节不变（见 test_observability.py）。

-- ---------------------------------------------------------------- 1) 哈希链自检
-- 断链计数必须为 0；`expected_prev` 与 `prev_hash` 不符即断链。
WITH e AS (
  SELECT seq, tick, type, prev_hash, hash,
         lag(hash) OVER (ORDER BY seq) AS expected_prev
  FROM read_json_auto('events.jsonl')
)
SELECT count(*) AS broken_links
FROM e
WHERE coalesce(expected_prev, repeat('0', 64)) <> prev_hash;

-- 断链明细（broken_links > 0 时用；正常运行时应为空集）
WITH e AS (
  SELECT seq, tick, type, prev_hash, hash,
         lag(hash) OVER (ORDER BY seq) AS expected_prev
  FROM read_json_auto('events.jsonl')
)
SELECT seq, tick, type, prev_hash, expected_prev
FROM e
WHERE coalesce(expected_prev, repeat('0', 64)) <> prev_hash
ORDER BY seq;

-- 链尾（链外锚点比对用；必须等于 `run` 打印的 chain_tail）
SELECT max_by(hash, seq) AS chain_tail, max(seq) AS last_seq, count(*) AS events
FROM read_json_auto('events.jsonl');

-- ---------------------------------------------------------------- 2) tick 时间线
-- 每个 tick 的事件密度（世界是否真的在推进 / 有没有空 tick）
SELECT tick,
       count(*) AS events,
       count(*) FILTER (WHERE type = 'npc.decision') AS decisions,
       count(*) FILTER (WHERE type = 'npc.action')   AS actions
FROM read_json_auto('events.jsonl')
GROUP BY tick
ORDER BY tick;

-- 推进速率：快照 tick 之间的间隔必须等于 `snapshot_every`（记录值）
SELECT payload.snapshot_tick AS tick,
       payload.snapshot_tick - lag(payload.snapshot_tick) OVER (ORDER BY payload.snapshot_tick) AS delta
FROM read_json_auto('events.jsonl')
WHERE type = 'snapshot.taken'
ORDER BY tick;

-- ---------------------------------------------------------------- 3) 事件统计
-- 事件类型分布 + 时间跨度（`npc.decision` 是 M4 新增；每 tick 每 NPC 一条）
SELECT type,
       count(*) AS n,
       min(tick) AS first_tick,
       max(tick) AS last_tick
FROM read_json_auto('events.jsonl')
GROUP BY type
ORDER BY n DESC;

-- 事件日志体积占比（D-M4-21：决策事件的体积必须折算进预算）
SELECT type,
       count(*) AS n,
       sum(length(to_json(payload))) AS payload_bytes,
       round(100.0 * sum(length(to_json(payload)))
             / (SELECT sum(length(to_json(payload))) FROM read_json_auto('events.jsonl')), 2) AS pct
FROM read_json_auto('events.jsonl')
GROUP BY type
ORDER BY payload_bytes DESC;

-- ---------------------------------------------------------------- 4) NPC 行为分布
-- 动作分布（谁在干什么）
SELECT payload.npc_id AS npc_id, payload.chosen_action AS action, count(*) AS n
FROM read_json_auto('events.jsonl')
WHERE type = 'npc.decision'
GROUP BY 1, 2
ORDER BY npc_id, n DESC;

-- 行为树分支分布（需求驱动的分支，不是班表）
SELECT payload.bt_branch AS branch, count(*) AS n,
       round(avg(payload.utility_score), 6) AS avg_utility
FROM read_json_auto('events.jsonl')
WHERE type = 'npc.decision'
GROUP BY 1
ORDER BY n DESC;

-- 主导需求分布 + 「日程不是唯一驱动」的证据面
SELECT payload.npc_id AS npc_id,
       payload.dominant_need AS dominant_need,
       count(*) AS n,
       round(avg(payload.dominant_deficit), 6) AS avg_deficit,
       count(*) FILTER (WHERE payload.schedule_is_driver) AS schedule_driver_rows
FROM read_json_auto('events.jsonl')
WHERE type = 'npc.decision'
GROUP BY 1, 2
ORDER BY npc_id, n DESC;
