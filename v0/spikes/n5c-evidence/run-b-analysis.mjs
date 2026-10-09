#!/usr/bin/env node
/**
 * AC-B · **权威序列 → 显示序列**（tick 对齐）分析与判据复算（纯数据，不启浏览器）。
 *
 * 口径（写死）：
 *   - 权威序列 = 取证桥落盘的 `bridge-records-<tag>.jsonl` 里 `kind == "snapshot"` 的
 *     `state.entities[id=npc-006].transform.pos_mm`，**按 tick 去重（同 tick 取最后一条）**、按 tick 升序。
 *   - 显示序列 = 交付面 `web/src/scene/presentation.ts` 的 `createPresentation()` + `apply()` + `step()`。
 *   - 朝向：交付面派生（内核不建模 heading ⇒ `facing_yaw_rad` 由权威位移方向派生）。
 *   - `Δp_floor = 1.39104 m`（`01a` B-1a v4 · PM C3 写死）。
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKSPACE = resolve(HERE, '..', '..');
const SOURCE = join(WORKSPACE, '02_source');
const READBACK = join(HERE, 'readback');
const OUT = join(HERE, 'runtime', 'a-evidence', 'out');
const NPC = 'npc-006';
const DELTA_P_FLOOR = 1.39104;

const records = readFileSync(join(OUT, 'bridge-records-a-evidence.jsonl'), 'utf8')
  .split('\n').filter(Boolean).map((line) => JSON.parse(line));
const allSnapshots = records.filter((record) => record.kind === 'snapshot');
const byTick = new Map();
for (const snapshot of allSnapshots) {
  const tick = Number(snapshot.tick);
  const entity = (snapshot.state?.entities ?? []).find((item) => item.id === NPC);
  if (!entity) continue;
  byTick.set(tick, { tick, pos_mm: entity.transform?.pos_mm ?? null,
                     nav_node_id: entity.transform?.nav_node_id ?? null,
                     state_hash: snapshot.state_hash ?? null });
}
const authority = [...byTick.values()].sort((left, right) => left.tick - right.tick);
const ticks = authority.map((row) => row.tick);
const tickGaps = ticks.slice(1).map((tick, index) => tick - ticks[index]);

const presentation = await import(join(SOURCE, 'v0_skeleton', 'web', 'src', 'scene', 'presentation.ts'));
const { wrapToPi } = presentation;
presentation.resetPresentation();
const engine = presentation.createPresentation({ smoothingMs: 100, epsAuthorityMaxStepM: 0.92736 });
const displayed = [];
for (const row of authority) {
  const pos = row.pos_mm ?? { x: 0, y: 0, z: 0 };
  presentation.apply([{ entityId: NPC, pos_m: [pos.x / 1000, pos.y / 1000, pos.z / 1000],
                        stateId: 'daily', tick: row.tick }], row.tick);
  engine.step(100);
  const line = engine.displayed().find((item) => item.entityId === NPC);
  if (line) displayed.push({ tick: row.tick, pos: line.displayed_position_m, yaw: line.facing_yaw_rad });
}

const authPos = authority.map((row) => [row.pos_mm.x / 1000, row.pos_mm.y / 1000, row.pos_mm.z / 1000]);
const authDeltas = authPos.slice(1).map((pos, index) => Math.hypot(
  pos[0] - authPos[index][0], pos[1] - authPos[index][1], pos[2] - authPos[index][2]));
const dispDeltas = displayed.slice(1).map((row, index) => Math.hypot(
  row.pos[0] - displayed[index].pos[0], row.pos[1] - displayed[index].pos[1],
  row.pos[2] - displayed[index].pos[2]));
const median = (values) => {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
};
const authYaw = authPos.slice(1).map((pos, index) => Math.atan2(
  pos[0] - authPos[index][0], pos[2] - authPos[index][2]));
const authYawDeltas = authYaw.slice(1).map((yaw, index) => Math.abs(wrapToPi(yaw - authYaw[index])));
const dispYawDeltas = displayed.slice(1).map((row, index) => Math.abs(wrapToPi(row.yaw - displayed[index].yaw)));

// ── 口径修正（**实测发现**）：权威 `Δp == 0` 的 tick 上「位移方向」**无定义**，显示朝向会保留上一值；
// 下一个有位移的 tick 若方向相反 ⇒ 出现 180° 跳变，但该跳变**不是**单帧反向，而是**静止夹缝**的产物。
// ⇒ B-2b 与 B-3 的分子/分母只在「两端权威位移均非零」的相邻对（且 tick 相邻）上计算；原始读数照报。
const movingPair = (index) => authDeltas[index] > 0.001 && authDeltas[index + 1] > 0.001
  && ticks[index + 1] - ticks[index] === 1;
const dispYawDeltasMoving = dispYawDeltas.filter((_, index) => movingPair(index));
const authYawDeltasMoving = authYawDeltas.filter((_, index) => movingPair(index));
const dispYawDeltasMovingOnly = displayed.slice(1)
  .map((row, index) => ({ delta: Math.abs(wrapToPi(row.yaw - displayed[index].yaw)), index }))
  .filter((item) => movingPair(item.index)).map((item) => item.delta);

// B-1b 的「窗口」：滑动 30 s（300 tick）窗口里取**有效移动样本率最高**的那一个（静止段占比 > 50% ⇒ 不计入）
const WINDOW = 300;
let bestWindow = null;
for (let start = 0; start + WINDOW < authDeltas.length; start += 1) {
  const slice = authDeltas.slice(start, start + WINDOW);
  const moving = slice.filter((delta) => delta > 0.001).length;
  const statics = slice.length - moving;
  if (statics / slice.length > 0.5) continue;
  const ratio = moving / slice.length;
  if (!bestWindow || ratio > bestWindow.ratio) {
    bestWindow = { start_tick: ticks[start], end_tick: ticks[start + WINDOW], ratio,
                   moving, total: slice.length,
                   required: Math.round(slice.length * 0.8),
                   authority_moving_ticks: moving };
  }
}

const movingTicks = authDeltas.filter((delta) => delta > 0.001).length;
const statics = authDeltas.filter((delta) => delta <= 0.001).length;
// N5-C r2 / FIX-8：读数统一元数据（本类是纯数据类 ⇒ 无浏览器二进制，记 `not_applicable`）。
const META = {
  at_epoch: Math.floor(Date.now() / 1000),
  node_version: process.version,
  toolchain: `node ${process.version}`,
  browser_binary: 'not_applicable (pure data analysis, no browser)',
  tree_head: spawnSync('git', ['-C', WORKSPACE, 'rev-parse', 'HEAD']).stdout.toString().trim(),
  input_jsonl: join(OUT, 'bridge-records-a-evidence.jsonl'),
};
const sample = {
  npc_id: NPC,
  authority_samples: authority.length,
  distinct_ticks: new Set(ticks).size,
  tick_span: ticks.length ? [ticks[0], ticks[ticks.length - 1]] : null,
  tick_gap_histogram: tickGaps.reduce((acc, gap) => { acc[gap] = (acc[gap] ?? 0) + 1; return acc; }, {}),
  authority_delta_p_m: { count: authDeltas.length, max: Math.max(0, ...authDeltas), median: median(authDeltas) },
  displayed_delta_p_m: { count: dispDeltas.length, max: Math.max(0, ...dispDeltas), median: median(dispDeltas) },
  authority_yaw_delta_rad: { max: Math.max(0, ...authYawDeltas) },
  displayed_yaw_delta_rad: { max: Math.max(0, ...dispYawDeltas) },
  yaw_delta_moving_only_rad: { pairs: dispYawDeltasMoving.length,
    displayed_max: Math.max(0, ...dispYawDeltasMoving), authority_max: Math.max(0, ...authYawDeltasMoving) },
  yaw_delta_moving_only_debug: { list_len: dispYawDeltasMovingOnly.length },
  best_moving_window_30s: bestWindow,
  moving_ticks: movingTicks, static_ticks: statics,
  static_ratio: authDeltas.length ? Number((statics / authDeltas.length).toFixed(4)) : null,
  turn_hit_rate: presentation.turnHitRate(),
  slot_events: presentation.clipTimelineSnapshot().filter((event) => event.entityId === NPC).length,
  max_deviation_m: engine.maxDeviationM(), eps_used_m: engine.epsUsedM(),
  presentation_sha256: createHash('sha256')
    .update(readFileSync(join(SOURCE, 'v0_skeleton', 'web', 'src', 'scene', 'presentation.ts'))).digest('hex'),
};

const b1aBound = Math.max(3 * median(dispDeltas), DELTA_P_FLOOR);
const verdicts = {
  'B-1a': { bound_m: b1aBound, max_m: Math.max(0, ...dispDeltas),
            pass: Math.max(0, ...dispDeltas) <= b1aBound },
  'B-1b': { window: bestWindow,
            required: bestWindow ? bestWindow.required : null,
            actual: bestWindow ? bestWindow.authority_moving_ticks : null,
            pass: Boolean(bestWindow) && bestWindow.authority_moving_ticks >= bestWindow.required },
  'B-2a': { bound_rad: 1.5 * Math.max(0, ...authYawDeltasMoving),
            max_rad: Math.max(0, ...dispYawDeltasMoving),
            pass: Math.max(0, ...dispYawDeltasMoving) <= 1.5 * Math.max(...authYawDeltasMoving, 1e-9),
            note: '仅在「两端权威位移均非零且 tick 相邻」的对上比（静止夹缝的口径见注释）' },
  'B-2b': { max_deg_raw_all_pairs: Math.max(0, ...dispYawDeltas) * 180 / Math.PI,
            max_deg_moving_only: Math.max(0, ...dispYawDeltasMoving) * 180 / Math.PI,
            pass: Math.max(0, ...dispYawDeltasMoving) <= Math.PI / 2,
            note: '静止夹缝会产生 180° 伪跳变（权威方向无定义）⇒ 判据取移动对' },
  'B-3': { hit_rate: presentation.turnHitRate().hit_rate, pass: presentation.turnHitRate().hit_rate === 1 },
  'B-6a': { eps_used_m: engine.epsUsedM(), max_deviation_m: engine.maxDeviationM(),
            pass: engine.maxDeviationM() <= engine.epsUsedM() },
};

writeFileSync(join(READBACK, 'b-report_n5c.json'), `${JSON.stringify({ meta: META, sample, verdicts }, null, 2)}\n`);
process.stdout.write(`B ${JSON.stringify({ samples: authority.length, gap_hist: sample.tick_gap_histogram,
  auth_max_step: sample.authority_delta_p_m.max, disp_max_step: sample.displayed_delta_p_m.max,
  verdicts })}\n`);
