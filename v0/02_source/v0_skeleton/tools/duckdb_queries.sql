-- 观测层（L7）示例查询：duckdb 直接读事件日志 JSONL，只读、不改内核状态。
-- 运行：duckdb -c ".read tools/duckdb_queries.sql"   （需先 duckdb；本机未装，见 09_risks_open_questions.md）

-- 1) 事件类型分布（判断世界是否在推进）
SELECT type, count(*) AS n, min(tick) AS first_tick, max(tick) AS last_tick
FROM read_json_auto('events.jsonl')
GROUP BY type
ORDER BY n DESC;

-- 2) 能力调用成本与降级率（AC-7 / AC-10 的观测口径）
SELECT payload.capability.id AS capability_id,
       payload.capability.version AS version,
       payload.provider AS provider,
       count(*) AS calls,
       round(avg(payload.ms), 2) AS avg_ms,
       sum(coalesce(payload.tokens_est, 0)) AS tokens_est
FROM read_json_auto('events.jsonl')
WHERE type = 'capability.invoked'
GROUP BY 1, 2, 3
ORDER BY calls DESC;

SELECT payload.capability.id AS capability_id, payload.reason AS reason, count(*) AS n
FROM read_json_auto('events.jsonl')
WHERE type = 'capability.fallback'
GROUP BY 1, 2
ORDER BY n DESC;

-- 3) 玩家介入审计（AC-4 / 防滥用）
SELECT payload.session_id, payload.kind, payload.target,
       count(*) AS intents, sum(payload.impact_cost) AS impact
FROM read_json_auto('events.jsonl')
WHERE type = 'intent.applied'
GROUP BY 1, 2, 3
ORDER BY intents DESC;

SELECT payload.reason_code, count(*) AS n
FROM read_json_auto('events.jsonl')
WHERE type = 'intent.rejected'
GROUP BY 1
ORDER BY n DESC;

-- 4) 快照时间轴（回放 scrubber 的数据源）
SELECT payload.snapshot_tick AS tick, payload.state_hash, payload.rng_state_digest
FROM read_json_auto('events.jsonl')
WHERE type = 'snapshot.taken'
ORDER BY tick;

-- 5) 哈希链自检（任何断链都是 CRITICAL）
WITH e AS (
  SELECT seq, prev_hash, hash, lag(hash) OVER (ORDER BY seq) AS expected_prev
  FROM read_json_auto('events.jsonl')
)
SELECT count(*) AS broken_links
FROM e
WHERE expected_prev IS NOT NULL AND prev_hash <> expected_prev;
