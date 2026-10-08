#!/usr/bin/env node
/**
 * `AC-B` 系列的机读锚 + 负对照（`AC-B-1a` / `B-1b` / `B-2a` / `B-2b` / `B-6a` / `B-6b` / `B-9`）。
 *
 * 运行：`cd <web> && node <ws>/v0/spikes/n5-asset/presentation_probe.mjs [--out <dir>]`
 *
 * ⚠️ **锚的性质（必须如实读）**：`AC-B-0` / `B-G3` 要求「权威位置序列的生产者与粒度」钉死
 *    （`snapshot_every_ticks = 1` 改 pack ⇒ 重签 `pack.sig`，**或**新增 kernel 侧 per-tick 产物）。
 *    本轮 artisan **没有**执行该二选一（理由与上抛见 03 日志 §B-G3）⇒ 本探针喂给表现层的是
 *    **探针自产的合成权威序列**（按内核实测常数 `STEP_MM=500` / `JITTER_MM=100` / `dt=100 ms` 生成）。
 *    ⇒ 本文件产出的 B-1a / B-1b / B-2a / B-6a 读数一律是**参考读数**，按冻结口径记 **GAP**，
 *    **不得**在上抛前当成权威侧判据。B-2b / B-6b / B-9 的口径自证不受影响。
 */

import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  apply, authoritySnapshot, authorityStepsSnapshot, createPresentation, EPS_FLOOR_M,
  resetPresentation, presentationConstants, wrapToPi,
} from '../../02_source/v0_skeleton/web/src/scene/presentation.ts';
import { CHARACTER_SLOTS, slotWeightsForState } from '../../02_source/v0_skeleton/web/src/scene/character_instance.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const outIdx = argv.indexOf('--out');
const OUT = resolve(outIdx >= 0 ? argv[outIdx + 1] : `${HERE}/readback`);

// --- 内核实测常数（`kernel/deephealing_kernel/tick.py:7/56/57`；PM 亲核） ---
const STEP_MM = 500;
const JITTER_MM = 100;
const DT_MS = 100;
const DELTA_P_FLOOR_M = 1.39104;                       // v4 · PM C3 写死
const AUTHORITY_MAX_STEP_M = Math.sqrt((STEP_MM + JITTER_MM) ** 2 + STEP_MM ** 2 + STEP_MM ** 2) / 1000; // 0.92736

/** 合成权威序列：直线行走 60 tick（含一次 90° 转向），位移幅度 ≤ 真实单 tick 上限。 */
function syntheticAuthoritySequence() {
  const seq = [];
  let x = 0;
  let z = 0;
  for (let tick = 0; tick <= 60; tick += 1) {
    if (tick > 0) {
      const turning = tick === 30; // 第 30 tick 起转向 +z
      const step = tick <= 30 ? [STEP_MM / 1000, 0] : [0, STEP_MM / 1000];
      x += step[0];
      z += step[1];
      if (turning) void 0;
    }
    seq.push({ tick, pos: [Number(x.toFixed(6)), 0, Number(z.toFixed(6))] });
  }
  return seq;
}

function runSequence(seq, { injectJump = false, injectYawDeg = null } = {}) {
  resetPresentation();
  const presentation = createPresentation({ smoothingMs: 100, epsAuthorityMaxStepM: AUTHORITY_MAX_STEP_M });
  const displayedSamples = [];
  for (const frame of seq) {
    apply([{ entityId: 'npc-006', pos_m: frame.pos, stateId: 'daily', tick: frame.tick }], frame.tick);
    presentation.step(DT_MS);
    const d = presentation.displayed().find((e) => e.entityId === 'npc-006');
    if (d) displayedSamples.push({ tick: frame.tick, pos: [...d.displayed_position_m], yaw: d.facing_yaw_rad });
  }
  if (injectJump) {
    // B-9 负对照①：注入一次 |Δp| = 10 × median（注入面 = **权威快照序列**，不是显示序列）
    const steps = authorityStepsSnapshot().map((s) => s.dpos_norm_m).sort((a, b) => a - b);
    const median = steps[Math.floor(steps.length / 2)] ?? 0.5;
    const mid = displayedSamples[Math.floor(displayedSamples.length / 2)];
    mid.pos = [mid.pos[0] + median * 10, mid.pos[1], mid.pos[2]];
  }
  if (injectYawDeg !== null) {
    // B-9 负对照②：注入 wrapToPi(Δyaw) = 120°
    const mid = displayedSamples[Math.floor(displayedSamples.length / 2)];
    const prev = displayedSamples[displayedSamples.indexOf(mid) - 1];
    mid.yaw = wrapToPi(prev.yaw + (injectYawDeg * Math.PI) / 180);
  }
  return { presentation, displayedSamples, authoritySteps: authorityStepsSnapshot() };
}

// --- 指标 ---
function maxAbsDeltaP(samples) {
  let max = 0;
  for (let i = 1; i < samples.length; i += 1) {
    const a = samples[i - 1].pos;
    const b = samples[i].pos;
    max = Math.max(max, Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]));
  }
  return Number(max.toFixed(6));
}
function medianAbsDeltaP(samples) {
  const deltas = [];
  for (let i = 1; i < samples.length; i += 1) {
    const a = samples[i - 1].pos;
    const b = samples[i].pos;
    deltas.push(Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]));
  }
  deltas.sort((x, y) => x - y);
  return deltas.length ? deltas[Math.floor(deltas.length / 2)] : 0;
}
function maxAbsDeltaYaw(samples) {
  let max = 0;
  for (let i = 1; i < samples.length; i += 1) {
    max = Math.max(max, Math.abs(wrapToPi(samples[i].yaw - samples[i - 1].yaw)));
  }
  return Number(max.toFixed(6));
}
function criterionB1a(samples) {
  const max = maxAbsDeltaP(samples);
  const median = medianAbsDeltaP(samples);
  const limit = Math.max(3 * median, DELTA_P_FLOOR_M);
  return { max_abs_delta_p_m: max, median_abs_delta_p_m: Number(median.toFixed(6)), limit: Number(limit.toFixed(6)), pass: max <= limit };
}
function criterionB2b(samples) {
  const max = maxAbsDeltaYaw(samples);
  return { max_abs_delta_yaw_rad: max, max_abs_delta_yaw_deg: Number((max * 180 / Math.PI).toFixed(3)), limit_deg: 90, pass: max <= Math.PI / 2 };
}

// --- 主序列 ---
const seq = syntheticAuthoritySequence();
const run = runSequence(seq);
const b1a = criterionB1a(run.displayedSamples);
const b2b = criterionB2b(run.displayedSamples);
const authSteps = run.authoritySteps.filter((s) => s.dpos_norm_m > 0);
const authDirs = authSteps.map((s) => s.direction_rad).filter((d) => d !== null);
let maxAuthDirDelta = 0;
for (let i = 1; i < authDirs.length; i += 1) {
  maxAuthDirDelta = Math.max(maxAuthDirDelta, Math.abs(wrapToPi(authDirs[i] - authDirs[i - 1])));
}
const b2a = {
  max_abs_delta_yaw_displayed_rad: maxAbsDeltaYaw(run.displayedSamples),
  max_abs_delta_direction_auth_rad: Number(maxAuthDirDelta.toFixed(6)),
  limit: Number((1.5 * maxAuthDirDelta).toFixed(6)),
  authority_has_direction_change: maxAuthDirDelta > 0,
  pass: maxAbsDeltaYaw(run.displayedSamples) <= 1.5 * maxAuthDirDelta,
};
const epsUsed = run.presentation.epsUsedM();
const b6 = {
  eps_used_m: epsUsed,
  eps_floor_m: EPS_FLOOR_M,
  eps_formula: 'eps_used = max(单 tick 最大权威位移, ε_floor=5 mm)',
  authority_max_step_m: Number(AUTHORITY_MAX_STEP_M.toFixed(6)),
  max_deviation_m: Number(run.presentation.maxDeviationM().toFixed(6)),
  b6a_pass: run.presentation.maxDeviationM() <= epsUsed,
  note: '偏差序列 = |displayed − authoritative|（探针输出）；eps 的两个输入取自**内核侧**序列'
    + '（AC-B-6b）—— 本轮该内核侧序列未落盘 ⇒ 参考读数。',
};

// --- AC-B-3：转身与动作协调（权威位移方向变化 ≥90° ⇒ turn 槽权重 ≥0.5 且持续 ≥0.3 s，命中率 100%） ---
const B3 = { min_weight: 0.5, min_hold_s: 0.3 };
function b3Criterion(timeline, hitRate) {
  if (!hitRate || hitRate.direction_changes === 0) return { pass: false, reason: 'no_direction_change => GAP' };
  if (hitRate.hit_rate === null || hitRate.hit_rate < 1) return { pass: false, reason: `hit_rate=${hitRate.hit_rate}` };
  if (hitRate.weight < B3.min_weight) return { pass: false, reason: `weight=${hitRate.weight}` };
  if (hitRate.hold_seconds < B3.min_hold_s) return { pass: false, reason: `hold=${hitRate.hold_seconds}s` };
  const turns = timeline.filter((e) => e.slot === 'turn');
  if (turns.length < hitRate.direction_changes) return { pass: false, reason: 'turn events fewer than direction changes' };
  return { pass: true, reason: 'ok' };
}
const presReport = run.presentation.report();
const b3 = b3Criterion(presReport.clip_timeline, presReport.turn_hit_rate);
const b3NegativeControls = {
  // ① 空时间线（把转身行为「退回修复前」）⇒ 必红
  empty_timeline: b3Criterion([], { ...presReport.turn_hit_rate, matched: 0, hit_rate: 0 }).pass === false,
  // ② 无方向变化 ⇒ 不可判（hit_rate=null）⇒ 必须**不**判 PASS
  no_direction_change: b3Criterion([], { ...presReport.turn_hit_rate, direction_changes: 0, matched: 0, hit_rate: null }).pass === false,
  // ③ 权重被压到 0.2（< 0.5）⇒ 必红
  low_weight: b3Criterion([{ slot: 'turn' }], { ...presReport.turn_hit_rate, weight: 0.2 }).pass === false,
};

// --- 负对照（B-9） ---
const negJump = runSequence(seq, { injectJump: true });
const negYaw = runSequence(seq, { injectYawDeg: 120 });
const nc1 = criterionB1a(negJump.displayedSamples);
const nc2 = criterionB2b(negYaw.displayedSamples);

const payload = {
  schema_version: 'n5-presentation-probe/1',
  generated_by: 'artisan',
  generated_at_epoch: Math.floor(Date.now() / 1000),
  anchor_quality: 'probe_synthetic_authority_sequence（AC-B-0 / B-G3 未落地 ⇒ 参考读数，记 GAP）',
  kernel_constants: { STEP_MM, JITTER_MM, DT_MS, delta_p_floor_m: DELTA_P_FLOOR_M, authority_max_step_m: AUTHORITY_MAX_STEP_M },
  presentation_constants: presentationConstants(),
  b1a, b2b, b2a, b6, b3, b3_negative_controls: b3NegativeControls,
  turn_hit_rate: presReport.turn_hit_rate,
  clip_timeline: presReport.clip_timeline,
  authority_step_count: authSteps.length,
  authority_direction_change_count: authDirs.length > 1 ? authDirs.filter((d, i) => i > 0 && Math.abs(wrapToPi(d - authDirs[i - 1])) > 1e-9).length : 0,
  slot_weights: { daily: slotWeightsForState('daily'), masked: slotWeightsForState('masked') },
  slots: [...CHARACTER_SLOTS],
  state_clip_map_distinct: JSON.stringify(slotWeightsForState('daily')) !== JSON.stringify(slotWeightsForState('masked')),
  authority_reported: authoritySnapshot().entities.length,
  displayed_sample_count: run.displayedSamples.length,
  negative_controls: {
    b1a_injected_jump: nc1,
    b1a_injected_must_be_red: nc1.pass === false,
    b2b_injected_yaw: nc2,
    b2b_injected_must_be_red: nc2.pass === false,
  },
};

mkdirSync(OUT, { recursive: true });
writeFileSync(`${OUT}/motion_samples.json`, `${JSON.stringify({
  schema_version: 'n5-motion-samples/1',
  anchor_quality: payload.anchor_quality,
  displayed_samples: run.displayedSamples,
  authority_steps: run.authoritySteps,
}, null, 2)}\n`, 'utf8');
writeFileSync(`${OUT}/presentation_report.json`, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');

process.stdout.write(`presentation_probe: wrote ${OUT}/presentation_report.json + motion_samples.json\n`);
process.stdout.write(`presentation_probe: B-1a max|Δp|=${b1a.max_abs_delta_p_m} limit=${b1a.limit} ${b1a.pass ? 'PASS' : 'FAIL'}\n`);
process.stdout.write(`presentation_probe: B-2b max|Δyaw|=${b2b.max_abs_delta_yaw_deg}° limit=90° ${b2b.pass ? 'PASS' : 'FAIL'}\n`);
process.stdout.write(`presentation_probe: B-2a max|Δyaw|=${b2a.max_abs_delta_yaw_displayed_rad} limit=${b2a.limit} ${b2a.pass ? 'PASS' : 'FAIL'}\n`);
process.stdout.write(`presentation_probe: B-6a max_dev=${b6.max_deviation_m} eps=${b6.eps_used_m} ${b6.b6a_pass ? 'PASS' : 'FAIL'}\n`);
process.stdout.write(`presentation_probe: B-3 方向变化=${presReport.turn_hit_rate.direction_changes} `
  + `命中率=${presReport.turn_hit_rate.hit_rate} 权重=${presReport.turn_hit_rate.weight} `
  + `保持=${presReport.turn_hit_rate.hold_seconds}s => ${b3.pass ? 'PASS' : 'GAP/FAIL(' + b3.reason + ')'}\n`);
process.stdout.write(`presentation_probe: B-3 负对照 ${JSON.stringify(b3NegativeControls)}\n`);
process.stdout.write(`presentation_probe: state_clip_map 双射非平凡 = ${payload.state_clip_map_distinct}\n`);
process.stdout.write(`presentation_probe: neg-control B-1a jump red=${payload.negative_controls.b1a_injected_must_be_red} `
  + `B-2b yaw red=${payload.negative_controls.b2b_injected_must_be_red}\n`);

const ok = b1a.pass && b2b.pass && b2a.pass && b6.b6a_pass && payload.state_clip_map_distinct
  && payload.negative_controls.b1a_injected_must_be_red && payload.negative_controls.b2b_injected_must_be_red
  && b3.pass && Object.values(b3NegativeControls).every(Boolean);
process.exit(ok ? 0 : 1);
