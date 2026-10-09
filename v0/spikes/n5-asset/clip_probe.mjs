#!/usr/bin/env node
/**
 * AC-B-7 / AC-B-8 探针（`v0/spikes/n5-asset/clip_probe.mjs`）。
 *
 * ⚠️ **命名来源**：任务书 FIX-10 说「既有 `nav_probe.py` / `clip_probe.mjs` 在盘，直接跑」——
 * r2 实测**两者都不在盘**（`find` 全库 0 命中；`01_architecture_design.md:479` 把它们列为
 * 「阶段 B 才写」的待建工具，`01c_sentinel_criteria_review.md` 亦记「nav_probe.py 尚不存在」）。
 * ⇒ 本文件是 r2 **新建**的探针，不是「跑既有件」。
 *
 * B-7 判据（01a §B）：`|clip 切换时刻 − intent.applied 时刻| ≤ 2 tick`，且两个读数必须来自
 * **两个不同进程的产物**：clip 侧 = 渲染层 `presentation.ts` 的 `clip_timeline`；
 * intent 侧 = 内核事件流里的 `intent.applied`。
 * B-8 判据：不得只以事件日志为证据 ⇒ 必须**同时**给「表现槽读数 + 画面证据」。
 *
 * 输入（只读）：
 *   --clip   <clip_timeline 所在 json>（缺省 readback/presentation_report_n5c.json）
 *   --events <内核事件 jsonl>（缺省 runtime/c1c2/out/kernel-events-c1c2.jsonl）
 *   --shots  <画面证据目录>（缺省 spikes/n5-asset/shots）
 * 输出：`readback/b7b8-reading.json`（+ stdout 一行）
 */
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKSPACE = resolve(HERE, '..', '..');
const EVIDENCE = join(WORKSPACE, 'spikes', 'n5c-evidence');
const READBACK = join(EVIDENCE, 'readback');
const argv = process.argv.slice(2);
const arg = (name, fallback) => {
  const index = argv.indexOf(name);
  return index >= 0 && argv[index + 1] ? resolve(argv[index + 1]) : fallback;
};
const CLIP = arg('--clip', join(READBACK, 'presentation_report_n5c.json'));
const EVENTS = arg('--events', join(EVIDENCE, 'runtime', 'c1c2', 'out', 'kernel-events-c1c2.jsonl'));
const SHOTS = arg('--shots', join(WORKSPACE, 'spikes', 'n5-asset', 'shots'));
const TOLERANCE_TICKS = 2;
const CONVERSATIONAL_SLOTS = ['speak', 'listen'];

const reading = {
  task: 'b7b8-clip-probe', at_epoch: Math.floor(Date.now() / 1000),
  node_version: process.version, toolchain: `node ${process.version}`,
  browser_binary: 'not_applicable (pure data analysis of two on-disk artifacts)',
  tree_head: spawnSync('git', ['-C', WORKSPACE, 'rev-parse', 'HEAD']).stdout.toString().trim(),
  tool_provenance: {
    cited_by_taskbook: '既有 nav_probe.py / clip_probe.mjs 在盘',
    on_disk_before_r2: false,
    evidence: '`find <ws> -name "clip_probe*" -o -name "nav_probe*"` = 0 命中；'
      + '01_architecture_design.md:479 列为待建（阶段 B）；01c_sentinel_criteria_review.md 记「nav_probe.py 尚不存在」',
    this_file: 'r2 新建（artisan）',
  },
  inputs: { clip_timeline: CLIP, kernel_events: EVENTS, shots_dir: SHOTS },
  process_split: {
    clip_side: '渲染层 presentation.ts :: clip_timeline（浏览器/表现层进程的产物）',
    intent_side: '内核事件流 :: intent.applied（内核进程的产物）',
  },
  tolerance_ticks: TOLERANCE_TICKS,
};

const clipExists = existsSync(CLIP);
const eventsExist = existsSync(EVENTS);
reading.inputs_exist = { clip_timeline: clipExists, kernel_events: eventsExist };

if (!clipExists || !eventsExist) {
  reading.verdict = 'GAP';
  reading.reason = `输入缺件（clip=${clipExists} events=${eventsExist}）⇒ 不可判（不得记 PASS）`;
} else {
  const clipPayload = JSON.parse(readFileSync(CLIP, 'utf8'));
  const timeline = Array.isArray(clipPayload.clip_timeline) ? clipPayload.clip_timeline : [];
  const events = readFileSync(EVENTS, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line));
  const applied = events.filter((event) => event.type === 'intent.applied');
  const conversational = timeline.filter((event) => CONVERSATIONAL_SLOTS.includes(String(event.slot)));
  const allSlots = [...new Set(timeline.map((event) => String(event.slot)))].sort();
  const pairings = conversational.map((event) => {
    const nearest = applied
      .map((intent) => ({ tick: Number(intent.tick), id: String(intent.payload?.intent_id ?? '') }))
      .sort((left, right) => Math.abs(left.tick - Number(event.tick)) - Math.abs(right.tick - Number(event.tick)))[0] ?? null;
    return { slot: event.slot, clip_tick: Number(event.tick), nearest_intent: nearest,
      delta_ticks: nearest === null ? null : Math.abs(nearest.tick - Number(event.tick)) };
  });
  const withinTolerance = pairings.filter((pair) => pair.delta_ticks !== null && pair.delta_ticks <= TOLERANCE_TICKS);
  reading.clip_side = {
    clip_events_total: timeline.length, slots_present: allSlots,
    conversational_slot_events: conversational.length,
    clip_timeline_source: clipPayload.schema_version ?? null,
  };
  reading.intent_side = { intent_applied_events: applied.length,
    intent_ids: applied.map((event) => String(event.payload?.intent_id ?? '')) };
  reading.pairings = pairings.slice(0, 10);
  if (conversational.length === 0) {
    reading.verdict = 'GAP';
    reading.reason = `clip_timeline 里**没有任何** speak/listen 槽事件（只有 ${JSON.stringify(allSlots)}）`
      + '⇒ 无法把「对话/倾听的表现反馈」与 intent.applied 配对 ⇒ 按 AC-A-4d 记 GAP，不得 PASS。'
      + '（根因与 C-4 的表现槽映射同源：槽权重只由转身/移动派生，与决策动作无关。）';
  } else if (withinTolerance.length === conversational.length) {
    reading.verdict = 'PASS';
    reading.reason = `${conversational.length} 条对话槽事件全部落在 ${TOLERANCE_TICKS} tick 容差内`;
  } else {
    reading.verdict = 'FAIL';
    reading.reason = `${conversational.length - withinTolerance.length} 条对话槽事件超出 ${TOLERANCE_TICKS} tick`;
  }
  // B-8：不得只靠日志 ⇒ 必须同时给表现槽读数 + 画面证据
  const shots = existsSync(SHOTS) ? readdirSync(SHOTS).filter((file) => file.endsWith('.png')) : [];
  reading.b8 = {
    slot_readout_present: timeline.length > 0,
    picture_evidence_files: shots.length,
    picture_evidence_examples: shots.slice(0, 3),
    pass: timeline.length > 0 && shots.length > 0,
    note: 'B-8 只要求「两路证据都在场」；对话槽本身缺席（见上）⇒ B-7 = GAP，B-8 的槽位面随之 GAP。',
  };
}

writeFileSync(join(READBACK, 'b7b8-reading.json'), `${JSON.stringify(reading, null, 2)}\n`);
process.stdout.write(`B7B8 ${JSON.stringify({ verdict: reading.verdict, reason: reading.reason,
  clip_events: reading.clip_side?.clip_events_total ?? null,
  conversational: reading.clip_side?.conversational_slot_events ?? null,
  intent_applied: reading.intent_side?.intent_applied_events ?? null })}\n`);
