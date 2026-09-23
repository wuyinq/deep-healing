#!/usr/bin/env node
/**
 * F3 端到端驱动（R2 / M3-03）：**真会话层 + 真桥 + 真内核**，验证「预算耗尽降级不得静默作废」。
 *
 * 运行：
 *   node spikes/s12-session/scripts/f3-budget-downgrade.mjs \
 *        --source <02_source 根> [--runtime <运行目录>] [--out <json 读数路径>]
 *
 * 两个场景（同一进程内两个会话，预算按会话记账）：
 *   A 降级时意图还在**会话层队列**里（33 条已 ack 为 queued，未过 tick 边界）
 *   B 降级时意图已过 tick 边界、落在**内核侧待应用队列**（33 条）
 *
 * 输出（stdout 一行 JSON）：逐条原始读数（ack 计数 / 队列长度 / 作废读数 / 内核事件计数）。
 * **不做判定** —— 判定与分类在 `spikes/s12-session/negctl/f3_budget_downgrade_negctl.py`，
 * 这样「改回静默作废 ⇒ 判据必须红」才是在**同一套读数**上判的。
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};

const SOURCE = resolve(option('source', join(process.cwd(), '02_source')));
const RUNTIME = resolve(option('runtime', join(SOURCE, '..', 'rt-f3')));
const OUT = option('out', null);

const { SessionServer } = await import(pathToFileURL(join(SOURCE, 'v0_skeleton/session/src/server.js')).href);
const { KernelClient } = await import(pathToFileURL(join(SOURCE, 'v0_skeleton/session/src/upstream.js')).href);

const kernelClient = new KernelClient({
  kernelSrc: join(SOURCE, 'v0_skeleton/kernel'),
  packSrc: join(SOURCE, 'v0_skeleton/districts', 'xingfu-xiaoqu'),
  runtimeDir: RUNTIME,
  seed: 20260921,
  snapshotEvery: 50,
  ticks: 300,
});
const bridgeRecords = [];
const meta = await kernelClient.subscribe([(record) => bridgeRecords.push(record)]);

let now = 0;
const server = new SessionServer({ kernelClient, clock: () => now });
const TARGETS = ['npc-001', 'npc-002', 'npc-003', 'npc-004', 'npc-005'];

async function newSession() {
  const created = await server.createSession({
    mode: 'participate', district_pack_id: 'xingfu-xiaoqu', client_version: '0.3.0',
  });
  if (created.status !== 201) throw new Error(`createSession -> ${created.status}`);
  return created.body.session_id;
}

async function submit(sessionId, id, target) {
  now += 6000; // 注入时钟：越过冷却与限流窗口（与单测同口径）
  const result = await server.onClientMessage(sessionId, JSON.stringify({
    t: 'intent', id, kind: 'delegate_instruction', target,
  }));
  return result.messages[0];
}

function readKernelEvents() {
  const path = join(RUNTIME, 'logs', 'kernel-events.jsonl');
  try {
    return readFileSync(path, 'utf8').split('\n').filter((line) => line.trim())
      .map((line) => JSON.parse(line));
  } catch {
    return [];
  }
}

async function scenario(tag, { tickBoundaryBeforeDowngrade }) {
  const sessionId = await newSession();
  const acks = [];
  for (let index = 0; index < 33; index += 1) {
    acks.push(await submit(sessionId, `${tag}-${index}`, TARGETS[index % TARGETS.length]));
  }
  let queuedAcks = acks.filter((ack) => ack.status === 'queued').length;
  let boundaryResults = [];
  if (tickBoundaryBeforeDowngrade) {
    boundaryResults = await server.onTickBoundary(1);
  }
  const budgetAck = await submit(sessionId, `${tag}-33`, TARGETS[0]);
  const outbox = server.drainOutbox(sessionId);
  const voidedAcks = outbox.filter((m) => m.t === 'intent_ack'
    && m.reason === 'E_BUDGET_EXHAUSTED' && m.id !== `${tag}-33`);
  const voidRecord = server.voidedIntents.find((entry) => entry.session_id === sessionId) ?? null;

  // 降级之后再推进 2 个 tick：被作废的意图**不得**被应用
  await server.onTickBoundary(2);
  await kernelClient.step(2);
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 300));

  const events = readKernelEvents();
  const mine = (event) => String((event.payload ?? {}).intent_id ?? '').startsWith(`${tag}-`);
  const rejected = events.filter((event) => event.type === 'intent.rejected' && mine(event));
  const applied = events.filter((event) => event.type === 'intent.applied' && mine(event));
  const voidAcks = bridgeRecords.filter((record) => record.kind === 'void_ack');
  const auditBudget = server.log.filter((entry) => entry.reason_code === 'E_BUDGET_EXHAUSTED').length;

  return {
    tag,
    tick_boundary_before_downgrade: Boolean(tickBoundaryBeforeDowngrade),
    session_id: sessionId,
    session_mode_after: server.sessions.get(sessionId).mode,
    queued_acks: queuedAcks,
    boundary_submitted: boundaryResults.length,
    budget_ack: { id: budgetAck.id, status: budgetAck.status, reason: budgetAck.reason },
    session_voided_acks: voidedAcks.length,
    session_voided_ids: voidedAcks.map((m) => m.id),
    session_pending_after: (server.queues.get(sessionId) ?? []).length,
    void_record: voidRecord,
    kernel_voided_count: voidRecord ? voidRecord.kernel_voided.length : 0,
    void_ack: voidAcks.length
      ? { count: voidAcks[voidAcks.length - 1].count, pending_after: voidAcks[voidAcks.length - 1].pending_after }
      : null,
    kernel_pending_after_void: voidAcks.length ? voidAcks[voidAcks.length - 1].pending_after : null,
    audit_budget_entries: auditBudget,
    kernel_intent_rejected_total: rejected.length,
    kernel_rejected_budget_exhausted: rejected.filter((e) => e.payload.reason_code === 'E_BUDGET_EXHAUSTED').length,
    kernel_rejected_readonly: rejected.filter((e) => e.payload.reason_code === 'E_MODE_READONLY').length,
    kernel_applied_total: applied.length,
    kernel_applied_ids: applied.map((e) => e.payload.intent_id),
  };
}

const readings = {
  source: SOURCE,
  runtime: RUNTIME,
  bridge_meta: { kernel_inside_copy: meta?.kernel_inside_copy, source_files: meta?.source_files },
  scenario_a_session_queue: await scenario('a', { tickBoundaryBeforeDowngrade: false }),
  scenario_b_kernel_queue: await scenario('b', { tickBoundaryBeforeDowngrade: true }),
};
readings.bridge_record_kinds = bridgeRecords.reduce((accumulator, record) => {
  accumulator[record.kind] = (accumulator[record.kind] ?? 0) + 1;
  return accumulator;
}, {});

await kernelClient.stop();
const text = JSON.stringify(readings, null, 2);
if (OUT) writeFileSync(OUT, `${text}\n`, 'utf8');
process.stdout.write(`${text}\n`);
process.exit(0);
