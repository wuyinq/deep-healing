/**
 * 内核桥客户端（L2 → 内核）——M3 真实现。
 *
 * 形态（D-2 / D-8）：本模块 spawn `bridge/kernel_bridge.py`（**Python 驱动桥**），
 * 桥把内核与 pack 复制到 `--runtime-dir` 并导入**副本** ⇒ 交付树零残渣。
 * 本模块**不**解析世界语义：只把桥的 stdout JSONL 原样搬给下行订阅者，把上行 intent
 * 写成一行 JSON 交给桥（由内核在 tick 边界出队应用）。
 *
 * 硬边界：零规则计算、零模型调用、**不缓存世界状态真值**、不写世界。
 */

import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';

export class KernelClient {
  constructor({ kernelSrc, packSrc, runtimeDir, seed = 20260921, snapshotEvery = 50, ticks = 300, python = 'python3' }) {
    this.kernelSrc = kernelSrc;
    this.packSrc = packSrc;
    this.runtimeDir = runtimeDir;
    this.seed = seed;
    this.snapshotEvery = snapshotEvery;
    this.ticks = ticks;
    this.python = python;
    this.child = null;
    this.handlers = [];
    this.meta = null;
    this.pendingAcks = [];
    this.ackWaiters = [];
    this.voidWaiters = [];
    this.snapshotWaiters = [];
    this.closed = false;
  }

  /** 启动桥并订阅只读流（`handlers` 收到桥原样搬运的 JSONL 记录）。 */
  async subscribe(handlers = []) {
    this.handlers = Array.isArray(handlers) ? handlers : [handlers];
    this.child = spawn(this.python, [
      '-B',
      new URL('../bridge/kernel_bridge.py', import.meta.url).pathname,
      '--kernel-src', this.kernelSrc,
      '--pack-src', this.packSrc,
      '--runtime-dir', this.runtimeDir,
      '--seed', String(this.seed),
      '--snapshot-every', String(this.snapshotEvery),
      '--ticks', String(this.ticks),
    ], { stdio: ['pipe', 'pipe', 'pipe'], env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });

    const reader = createInterface({ input: this.child.stdout });
    reader.on('line', (line) => {
      if (!line.trim()) return;
      let record;
      try {
        record = JSON.parse(line);
      } catch {
        return; // 非 JSON 行不是契约内容，丢弃（不解释、不猜）
      }
      if (record.kind === 'bridge_meta') this.meta = record;
      if (record.kind === 'intent_ack') {
        const waiter = this.ackWaiters.shift();
        if (waiter) waiter(record);
        else this.pendingAcks.push(record);
      }
      if (record.kind === 'void_ack') {
        const waiter = this.voidWaiters.shift();
        if (waiter) waiter(record);
      }
      if (record.kind === 'snapshot_ack') {
        const waiter = this.snapshotWaiters.shift();
        if (waiter) waiter(record);
      }
      for (const handler of this.handlers) handler(record);
    });
    this.child.stderr.on('data', () => { /* 桥的诊断输出不进入下行流 */ });
    await new Promise((resolve) => setTimeout(resolve, 300));
    return this.meta;
  }

  /** 推进 n 个 tick（由会话层的 tick 定时器驱动；桥逐 tick 调 `WorldKernel.step()`）。 */
  async step(n = 1) {
    if (!this.child) throw new Error('E_KERNEL_UNAVAILABLE: bridge is not subscribed');
    this.child.stdin.write(`${JSON.stringify({ cmd: 'step', n })}\n`);
  }

  /** 把意图交给内核入口；返回内核 ack（queued/rejected + reason）。 */
  async submitIntent(sessionId, intent, { mode = 'participate', impactBudgetRemaining } = {}) {
    if (!this.child) throw new Error('E_KERNEL_UNAVAILABLE: bridge is not subscribed');
    const payload = { ...intent, session_id: sessionId };
    const ackPromise = new Promise((resolve) => this.ackWaiters.push(resolve));
    this.child.stdin.write(`${JSON.stringify({
      cmd: 'intent', mode, intent: payload, impact_budget_remaining: impactBudgetRemaining,
    })}\n`);
    return ackPromise;
  }

  /**
   * 作废内核侧待应用意图（**唯一调用点 = 预算耗尽降级**）。
   * 桥逐条落 `intent.rejected{reasonCode}` 并清空队列；返回 `{voided:[ids], count, pending_after}`。
   * 桥不可用 / 无应答 ⇒ 返回空结果（**不**抛：降级本身不得因为桥慢而失败）。
   */
  async voidPendingIntents(sessionId, reasonCode = 'E_BUDGET_EXHAUSTED') {
    if (!this.child) return { voided: [], count: 0, pending_after: null, bridge: 'unavailable' };
    const ack = new Promise((resolve) => this.voidWaiters.push(resolve));
    const timeout = new Promise((resolve) => setTimeout(() => resolve(null), 5000));
    this.child.stdin.write(`${JSON.stringify({
      cmd: 'void_intents', session_id: sessionId, reason_code: reasonCode,
    })}\n`);
    const record = await Promise.race([ack, timeout]);
    if (!record) return { voided: [], count: 0, pending_after: null, bridge: 'timeout' };
    return { ...record, bridge: 'ok' };
  }

  /**
   * 向内核要一次**当前**快照（只读；用于新连接首帧补齐，R2 / F4）。
   * 返回 `{kind:'snapshot_ack', tick, state, state_hash}`；桥不可用 / 超时 ⇒ `null`。
   */
  async requestSnapshot() {
    if (!this.child) return null;
    const ack = new Promise((resolve) => this.snapshotWaiters.push(resolve));
    const timeout = new Promise((resolve) => setTimeout(() => resolve(null), 5000));
    this.child.stdin.write(`${JSON.stringify({ cmd: 'snapshot' })}\n`);
    return Promise.race([ack, timeout]);
  }

  async stop() {
    if (!this.child || this.closed) return;
    this.closed = true;
    this.child.stdin.write(`${JSON.stringify({ cmd: 'stop' })}\n`);
    await new Promise((resolve) => setTimeout(resolve, 200));
    this.child.kill();
  }
}
