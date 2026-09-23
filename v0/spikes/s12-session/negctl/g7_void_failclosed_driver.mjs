#!/usr/bin/env node
/**
 * G7 判据驱动（R3 / Raven r2 R2-M6）：桥侧作废**未确认**时，会话侧**不得**宣告作废。
 *
 * 在**隔离副本**的会话层上真跑（`--session-src <副本>/02_source/v0_skeleton/session`），
 * 内核客户端注入「桥超时」（`bridge: 'timeout'`、`pending_after: null`）：
 *   - 33 条已 ack 为 `queued` 的意图**不得**收到 `rejected{E_BUDGET_EXHAUSTED}` 作废宣告；
 *   - 必须收到**如实**状态（`rejected` + `E_KERNEL_UNAVAILABLE` + `rejected_pending_kernel`）
 *     **或**落一条 `error` 事件；
 *   - 会话队列必须**保留**（不得假装作废）；必须落 `downgrade_void_incomplete` 审计。
 *
 * 输出一行 JSON；判据不成立 ⇒ exit 1。
 */

import { pathToFileURL } from 'node:url';
import { join, resolve } from 'node:path';

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};

const SESSION = resolve(option('session-src', ''));
const { SessionServer } = await import(pathToFileURL(join(SESSION, 'src/server.js')).href);

class TimeoutVoidKernel {
  constructor() { this.calls = []; this.voidCalls = []; }
  async submitIntent(sessionId, intent, options = {}) {
    this.calls.push({ sessionId, intent, mode: options.mode });
    if (options.mode !== 'participate') return { id: intent.id, status: 'rejected', reason: 'E_MODE_READONLY' };
    return { id: intent.id, status: 'queued', reason: null };
  }
  async voidPendingIntents(sessionId, reasonCode = 'E_BUDGET_EXHAUSTED') {
    this.voidCalls.push({ sessionId, reasonCode });
    return { voided: [], count: 0, pending_after: null, bridge: 'timeout' };
  }
}

let now = 0;
const clock = () => now;
const kernel = new TimeoutVoidKernel();
const server = new SessionServer({ kernelClient: kernel, clock });
const created = await server.createSession({ mode: 'participate', district_pack_id: 'xingfu-xiaoqu', client_version: '0.3.0' });
const id = created.body.session_id;
const targets = ['npc-001', 'npc-002', 'npc-003', 'npc-004', 'npc-005'];

let trigger = null;
for (let index = 0; index < 34; index += 1) {
  now += 6000;
  const ack = (await server.onClientMessage(id, JSON.stringify({
    t: 'intent', id: `i-g7-${index}`, kind: 'delegate_instruction', target: targets[index % targets.length],
  }))).messages[0];
  if (ack.status !== 'queued') { trigger = { ...ack, id: `i-g7-${index}` }; break; }
}

const outbox = server.drainOutbox(id);
const voidDeclarations = outbox.filter((m) => m.t === 'intent_ack' && m.reason === 'E_BUDGET_EXHAUSTED'
  && m.id !== trigger.id);
const honestAcks = outbox.filter((m) => m.t === 'intent_ack' && m.reason === 'E_KERNEL_UNAVAILABLE'
  && /rejected_pending_kernel/.test(String(m.detail)));
const errorEvents = outbox.filter((m) => m.t === 'error' && m.reason === 'E_KERNEL_UNAVAILABLE');
const retained = server.pendingIntentCount(id);
const incomplete = server.voidIncomplete ?? [];
const auditIncomplete = server.log.filter((entry) => entry.status === 'downgrade_void_incomplete');

const criterionHolds = voidDeclarations.length === 0
  && (honestAcks.length >= 1 || errorEvents.length >= 1)
  && retained >= 1
  && incomplete.length === 1
  && incomplete[0].outcome === 'downgrade_void_incomplete'
  && auditIncomplete.length === 1
  && kernel.voidCalls.length >= 2;

const out = {
  trigger_reason: trigger ? trigger.reason : null,
  void_declarations: voidDeclarations.length,
  honest_acks: honestAcks.length,
  error_events: errorEvents.length,
  retained_in_queue: retained,
  void_incomplete_records: incomplete.length,
  audit_incomplete_entries: auditIncomplete.length,
  bridge_void_attempts: kernel.voidCalls.length,
  criterion_holds: criterionHolds,
};
process.stdout.write(`${JSON.stringify(out)}\n`);
process.exit(criterionHolds ? 0 : 1);
