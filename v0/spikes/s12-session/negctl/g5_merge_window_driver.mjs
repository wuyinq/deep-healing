#!/usr/bin/env node
/**
 * G5 判据驱动（R3 / Raven r2 R2-M5）：合并窗口**不得**产生「已 ack 为 queued 却永不应用」。
 *
 * 在**隔离副本**的会话层上真跑（`--session-src <副本>/02_source/v0_skeleton/session`）：
 *   ① 同 id 窗口内、**仍在队列** ⇒ 允许合并（队列只 1 条）；
 *   ② 该意图经 tick 边界**离开队列**后，同 id（仍在窗口内）再次提交 ⇒
 *      **不得**再回 `queued + merged`；判据：`pending_intent_count() ≥ 1` **或** ack ≠ `queued`；
 *   ③ 合并键必须含 `target`：同 id **不同 target** 不得合并。
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

class FakeKernel {
  constructor() { this.calls = []; this.kernelPending = new Map(); }
  async submitIntent(sessionId, intent, options = {}) {
    this.calls.push({ sessionId, intent, mode: options.mode });
    if (options.mode !== 'participate') return { id: intent.id, status: 'rejected', reason: 'E_MODE_READONLY' };
    this.kernelPending.set(sessionId, [...(this.kernelPending.get(sessionId) ?? []), intent.id]);
    return { id: intent.id, status: 'queued', reason: null };
  }
  async voidPendingIntents(sessionId) {
    this.kernelPending.set(sessionId, []);
    return { voided: [], count: 0, pending_after: 0, bridge: 'ok' };
  }
}

let now = 0;
const clock = () => now;
const kernel = new FakeKernel();
const server = new SessionServer({ kernelClient: kernel, clock });
const created = await server.createSession({ mode: 'participate', district_pack_id: 'xingfu-xiaoqu', client_version: '0.3.0' });
const id = created.body.session_id;
const message = (intentId, target) => JSON.stringify({ t: 'intent', id: intentId, kind: 'delegate_instruction', target });

const ack1 = (await server.onClientMessage(id, message('i-g5', 'npc-001'))).messages[0];
now += 100;
const ack2 = (await server.onClientMessage(id, message('i-g5', 'npc-001'))).messages[0];
const mergedWhileQueued = ack2.status === 'queued' && /merged/.test(String(ack2.detail))
  && server.pendingIntentCount(id) === 1;

await server.onTickBoundary(1);
const queueEmptiedAfterTick = server.pendingIntentCount(id) === 0;

now += 100;
const ack3 = (await server.onClientMessage(id, message('i-g5', 'npc-001'))).messages[0];
const criterionHolds = ack3.status !== 'queued' || server.pendingIntentCount(id) >= 1;
const swallowedByMerge = ack3.status === 'queued' && server.pendingIntentCount(id) === 0;

now += 2000; // 越过全局冷却，让下一次提交能真正入队
const ackTarget1 = (await server.onClientMessage(id, message('i-g5t', 'npc-004'))).messages[0];
now += 1000;
const ackTarget2 = (await server.onClientMessage(id, message('i-g5t', 'npc-005'))).messages[0];
const targetKeyHolds = ackTarget2.status === 'queued' && !/merged/.test(String(ackTarget2.detail ?? ''))
  && server.pendingIntentCount(id) === 2; // 两个不同 target 的意图各占一个队列条目（ack3 已被拒，不入队）

const out = {
  ack1: ack1.status,
  ack2_status: ack2.status, ack2_detail: ack2.detail ?? null, merged_while_queued: mergedWhileQueued,
  queue_emptied_after_tick: queueEmptiedAfterTick,
  ack3_status: ack3.status, ack3_detail: ack3.detail ?? null,
  pending_after_third: server.pendingIntentCount(id),
  criterion_holds: criterionHolds, swallowed_by_merge: swallowedByMerge,
  ack_target1: ackTarget1.status, ack_target2: ackTarget2.status,
  ack_target2_detail: ackTarget2.detail ?? null, target_key_holds: targetKeyHolds,
};
process.stdout.write(`${JSON.stringify(out)}\n`);
process.exit(criterionHolds && !swallowedByMerge && targetKeyHolds && mergedWhileQueued && queueEmptiedAfterTick ? 0 : 1);
