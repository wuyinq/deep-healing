/**
 * L2 会话传输层（**非权威**）——M3 真实现。
 *
 * 硬边界（消灭「双权威」漂移，R7）：
 *   - 不持有世界状态真值；不做规则计算；不做模型调用；**不改世界状态**；
 *   - 只做搬运与权限检查；权威写入唯一发生在内核 tick 的执行阶段。
 *
 * 权限判定发生在**唯一入口** `onClientMessage`：observe 会话的任何上行 intent 一律
 * `intent_ack{status:rejected, reason:E_MODE_READONLY}`，且**必须落 `intent.rejected` 事件**
 * （经 `kernelClient.submitIntent(..., {mode:'observe'})`，由内核入口写入事件链）。
 * participate 会话经 `InterventionPolicy` 校验后**入队**，只在 `onTickBoundary` 交给内核 ⇒
 * 意图**只在 tick 边界应用**（V0 关闭客户端预测）。
 */

import { randomUUID } from 'node:crypto';

import { checkUpstream, assertMode } from './mode.js';
import { InterventionPolicy, DEFAULT_POLICY } from './policy.js';
import {
  ERROR_CODES,
  MESSAGE_TYPES,
  SCHEMA_VERSION,
  TICK_RATE,
  makeError,
  makeIntentAck,
  makeSnapshot,
  makeDelta,
  makeEvent,
  makeTickMeta,
  validateClientMessage,
  validateCreateSessionRequest,
  validateServerMessage,
} from './protocol.js';

export { ERROR_CODES, MESSAGE_TYPES };

const KNOWN_PACKS = new Set(['xingfu-xiaoqu', 'xingfu-xiaoqu-north']);

export class SessionServer {
  constructor({ kernelClient, policy = DEFAULT_POLICY, clock = () => Date.now(), snapshotEveryTicks = 50, knownPacks = KNOWN_PACKS, recorder = null }) {
    this.kernelClient = kernelClient;
    this.policy = policy instanceof InterventionPolicy ? policy : new InterventionPolicy(policy, { clock });
    this.clock = clock;
    this.snapshotEveryTicks = snapshotEveryTicks;
    this.knownPacks = knownPacks;
    // **只读录像**（R2 / F11）：`createSession({record:true})` 的会话把每条**下行**消息交给注入的
    // recorder。本层**不碰文件系统**（落盘位置与形态由宿主决定：spike 落 `spikes/s12-session/logs/`），
    // 也**不写世界状态** —— 录像只是下行消息的副本。
    this.recorder = recorder;
    this.recordingSessions = new Set();
    this.sessions = new Map();
    this.queues = new Map(); // session_id -> 待应用的意图（tick 边界出队）
    this.outboxes = new Map(); // session_id -> 下行消息
    this.voidedIntents = []; // 预算耗尽降级时的作废读数（R2 / M3-03）
    this.voidIncomplete = []; // 桥侧作废**未确认**的降级读数（R3 / G7：不得宣告作废）
    this.mergedIntents = 0; // 重复 id 合并计数（R2 / F10）
    this.log = []; // 会话层自己的审计流水（**不含** token / 玩家原文）
  }

  /** POST /sessions —— 建会话并返回 {session_id, token, tick_rate, schema_version, ...}。 */
  async createSession(body) {
    const checked = validateCreateSessionRequest(body);
    if (!checked.ok) return { status: 400, body: { error: checked.reason, detail: checked.detail } };
    if (!this.knownPacks.has(checked.value.district_pack_id)) {
      return {
        status: 400,
        body: { error: 'E_PACK_INVALID', detail: `unknown district_pack_id ${checked.value.district_pack_id}` },
      };
    }
    const sessionId = `sess_${randomUUID().replace(/-/g, '').slice(0, 16)}`;
    const token = randomUUID(); // **不入日志**：本对象之外的任何落盘/打印都不得含它
    const session = {
      session_id: sessionId,
      token,
      mode: assertMode(checked.value.mode),
      district_pack_id: checked.value.district_pack_id,
      client_version: checked.value.client_version,
      record: checked.value.record,
      created_ms: this.clock(),
      tick: 0,
      seq: 0,
    };
    this.sessions.set(sessionId, session);
    this.queues.set(sessionId, []);
    this.outboxes.set(sessionId, []);
    if (session.record && this.recorder) {
      this.recordingSessions.add(sessionId);
      if (typeof this.recorder.open === 'function') this.recorder.open(sessionId);
    }
    const response = {
      session_id: sessionId,
      token,
      tick_rate: TICK_RATE,
      schema_version: SCHEMA_VERSION,
      snapshot_every_ticks: this.snapshotEveryTicks,
    };
    if (session.mode === 'participate') {
      response.impact_budget_remaining = this.policy.remainingBudget(sessionId);
    }
    return { status: 201, body: response };
  }

  /** 会话层审计流水（脱敏；token 永不出现）。 */
  auditRecord(entry) {
    this.log.push({ ...entry, token: '***REDACTED***' });
  }

  /** WS 上行入口：鉴权 + 协议校验 + 权限判定 + 策略校验 + 入队。**绝不改世界状态**。 */
  async onClientMessage(sessionId, raw) {
    const session = this.sessions.get(sessionId);
    if (!session) {
      return { messages: [makeError({ tick: 0, seq: 0, reason: 'E_SESSION_UNKNOWN', detail: sessionId })] };
    }
    let parsed;
    try {
      parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    } catch (error) {
      return this.#reply(session, makeError({
        tick: session.tick, seq: session.seq, reason: 'E_SCHEMA_INVALID', detail: String(error),
      }));
    }
    const checked = validateClientMessage(parsed);
    if (!checked.ok) {
      return this.#reply(session, makeIntentAck({
        tick: session.tick, seq: session.seq, id: String(parsed?.id ?? ''),
        status: 'rejected', reason: checked.reason, detail: checked.detail,
      }), { reasonCode: checked.reason, intentId: String(parsed?.id ?? ''), kind: parsed?.kind, target: parsed?.target });
    }

    const intent = checked.value;
    // ---- 唯一权限入口：observe 一律拒（含录像路径），不得静默接受 ----
    const permissionError = checkUpstream(session.mode);
    if (permissionError) {
      const ack = makeIntentAck({
        tick: session.tick, seq: session.seq, id: intent.id, status: 'rejected',
        reason: permissionError, detail: `session mode ${session.mode} is read-only`,
      });
      await this.kernelClient.submitIntent(session.session_id, {
        id: intent.id, kind: intent.kind ?? 'delegate_instruction', target: intent.target ?? '',
      }, { mode: 'observe' });
      return this.#reply(session, ack, {
        reasonCode: permissionError, intentId: intent.id, kind: intent.kind, target: intent.target,
      });
    }

    const verdict = this.policy.evaluate(session.session_id, {
      id: intent.id,
      kind: intent.kind ?? 'delegate_instruction',
      target: intent.target,
    }, session.tick);
    if (verdict.ok && verdict.merged) {
      // **重复 id 合并**（R2 / F10）：同 id 在 `duplicate_merge_window_ms` 内重复提交 ⇒
      // 不新增队列条目（tick 边界只会有一条 `intent.applied`），ack 仍是 `queued` 并带 merged 说明。
      this.mergedIntents += 1;
      return this.#reply(session, makeIntentAck({
        tick: session.tick, seq: session.seq, id: intent.id, status: 'queued',
        detail: verdict.detail,
        impactBudgetRemaining: this.policy.remainingBudget(session.session_id),
      }), { intentId: intent.id, kind: intent.kind, target: intent.target, merged: true });
    }
    if (!verdict.ok) {
      // 新上行一律拒：经内核入口落 `intent.rejected`（observe 通道，fail-closed）
      await this.kernelClient.submitIntent(session.session_id, {
        id: intent.id, kind: intent.kind ?? 'delegate_instruction', target: intent.target ?? '',
      }, { mode: 'observe' });
      // **预算耗尽降级**（R2 / M3-03）：降级只影响**新**上行；已 ack 为 queued 的意图
      // 必须逐条补发 `intent.rejected{E_BUDGET_EXHAUSTED}` 并清空队列 —— 禁止静默作废。
      if (verdict.downgradeToObserve) await this.downgradeToObserve(session);
      const ack = makeIntentAck({
        tick: session.tick, seq: session.seq, id: intent.id, status: 'rejected',
        reason: verdict.reason, detail: verdict.detail,
        impactBudgetRemaining: this.policy.remainingBudget(session.session_id),
      });
      return this.#reply(session, ack, {
        reasonCode: verdict.reason, intentId: intent.id, kind: intent.kind, target: intent.target,
      });
    }

    const text = intent.payload?.instruction_text;
    const queued = {
      id: intent.id,
      kind: intent.kind ?? 'delegate_instruction',
      target: intent.target,
      impact_cost: verdict.impactCost,
      instruction_digest: text === undefined ? undefined : InterventionPolicy.digest(this.policy.sanitizeInstructionText(text)),
      client_tick: intent.client_tick,
      queued_tick: session.tick,
    };
    this.queues.get(session.session_id).push(queued);
    return this.#reply(session, makeIntentAck({
      tick: session.tick, seq: session.seq, id: intent.id, status: 'queued',
      impactBudgetRemaining: this.policy.remainingBudget(session.session_id),
    }), { intentId: intent.id, kind: queued.kind, target: queued.target, queued: true });
  }

  /**
   * **tick 边界**：把队列里的意图交给内核（内核在它自己的 tick 边界出队应用）。
   * 返回每个意图的内核 ack；队列为空 ⇒ 空数组（零副作用）。
   */
  async onTickBoundary(tick) {
    const results = [];
    for (const [sessionId, queue] of this.queues.entries()) {
      const session = this.sessions.get(sessionId);
      if (!session) continue;
      session.tick = tick;
      while (queue.length) {
        const item = queue.shift();
        // R3 / G5：出队即登记「已离开队列」⇒ 同 id 再次提交不再被合并（按新意图入队）
        this.policy.markIntentLeavesQueue(sessionId, item.id);
        const ack = await this.kernelClient.submitIntent(sessionId, {
          id: item.id, kind: item.kind, target: item.target,
          impact_cost: item.impact_cost, instruction_digest: item.instruction_digest,
        }, { mode: session.mode, impactBudgetRemaining: this.policy.remainingBudget(sessionId) });
        results.push({ session_id: sessionId, intent_id: item.id, ack });
      }
    }
    return results;
  }

  /**
   * **预算耗尽降级**（R2 / M3-03；`policy.impact_budget.on_exhausted = 'observe_and_drop_queued'`）。
   *
   * 语义（与契约同名）：降级为观察 + **作废待应用队列**。降级只影响**新**上行；
   * 此前已 `intent_ack{status:'queued'}` 的意图必须**逐条**补发
   * `intent.rejected{E_BUDGET_EXHAUSTED}`（会话层 ack 进下行 outbox + 内核事件流），
   * 并清空两侧队列 ⇒ 不存在「已 ack 但静默失效」的意图。
   *
   * **R3 / G7（fail-closed 方向）**：桥侧作废**未确认**（`bridge != 'ok'` 或
   * `pending_after > 0`）时，会话侧**不得**宣告作废 —— 否则会出现「已告知客户端作废、
   * 内核却照常应用」的 fail-open 窗口（Raven r2 R2-M6）。此时：
   *   - 先**重试一次**桥侧作废；
   *   - 仍不确认 ⇒ **保留**会话队列，ack 降级为**如实**状态
   *     （`rejected` + `E_KERNEL_UNAVAILABLE` + detail `rejected_pending_kernel`），
   *     并额外落一条 `error` 事件 + `downgrade_void_incomplete` 审计；
   *   - 保留的队列会在下个 tick 边界以 **observe 通道**提交 ⇒ 内核按 `E_MODE_READONLY` 拒，
   *     即「没被宣告作废的意图不会静默生效」。
   *
   * 返回 `{outcome, session_voided, kernel_voided:{...}}`（可核验读数，进审计流水）。
   */
  async downgradeToObserve(session) {
    session.mode = 'observe';
    const queue = this.queues.get(session.session_id) ?? [];
    let kernelVoided = await this.kernelClient.voidPendingIntents(session.session_id, 'E_BUDGET_EXHAUSTED');
    let confirmed = this.#voidConfirmed(kernelVoided);
    if (!confirmed) {
      kernelVoided = await this.kernelClient.voidPendingIntents(session.session_id, 'E_BUDGET_EXHAUSTED');
      confirmed = this.#voidConfirmed(kernelVoided);
    }

    if (!confirmed) {
      // ---- 未确认 ⇒ 不宣告作废（fail-closed）----
      const record = {
        session_id: session.session_id,
        outcome: 'downgrade_void_incomplete',
        session_voided: [],
        kernel_voided: Array.isArray(kernelVoided.voided) ? kernelVoided.voided : [],
        kernel_bridge: kernelVoided.bridge ?? 'unknown',
        kernel_pending_after: kernelVoided.pending_after ?? null,
        retained_in_queue: queue.map((item) => item.id),
      };
      this.voidedIntents.push(record);
      this.voidIncomplete.push(record);
      this.auditRecord({
        at_ms: this.clock(), session_id: session.session_id, mode: session.mode,
        intent_id: null, kind: null, target: null, reason_code: 'E_KERNEL_UNAVAILABLE',
        status: 'downgrade_void_incomplete', kernel_bridge: record.kernel_bridge,
        kernel_pending_after: record.kernel_pending_after,
      });
      for (const item of queue) {
        this.#reply(session, makeIntentAck({
          tick: session.tick, seq: session.seq, id: item.id, status: 'rejected',
          reason: 'E_KERNEL_UNAVAILABLE',
          detail: `rejected_pending_kernel: bridge=${record.kernel_bridge} `
            + `pending_after=${record.kernel_pending_after}（桥侧作废未确认 ⇒ **未**宣告作废）`,
          impactBudgetRemaining: this.policy.remainingBudget(session.session_id),
        }), { reasonCode: 'E_KERNEL_UNAVAILABLE', intentId: item.id, kind: item.kind, target: item.target });
      }
      this.#reply(session, makeError({
        tick: session.tick, seq: session.seq, reason: 'E_KERNEL_UNAVAILABLE',
        detail: `downgrade_void_incomplete: bridge=${record.kernel_bridge} `
          + `pending_after=${record.kernel_pending_after} retained=${record.retained_in_queue.length}`,
      }));
      return record;
    }

    // ---- 已确认 ⇒ 会话侧清空 + 逐条如实作废 ----
    const voided = queue.splice(0, queue.length);
    for (const item of voided) this.policy.markIntentLeavesQueue(session.session_id, item.id);
    for (const item of voided) {
      this.#reply(session, makeIntentAck({
        tick: session.tick, seq: session.seq, id: item.id, status: 'rejected',
        reason: 'E_BUDGET_EXHAUSTED',
        detail: `voided on budget downgrade: cost=${item.impact_cost} queued_tick=${item.queued_tick}`,
        impactBudgetRemaining: this.policy.remainingBudget(session.session_id),
      }), { reasonCode: 'E_BUDGET_EXHAUSTED', intentId: item.id, kind: item.kind, target: item.target });
    }
    const record = {
      session_id: session.session_id,
      outcome: 'downgrade_void_complete',
      session_voided: voided.map((item) => item.id),
      kernel_voided: Array.isArray(kernelVoided.voided) ? kernelVoided.voided : [],
      kernel_bridge: kernelVoided.bridge ?? 'unknown',
      kernel_pending_after: kernelVoided.pending_after ?? null,
    };
    this.voidedIntents.push(record);
    return record;
  }

  /** 桥侧作废是否**已确认**（`bridge === 'ok'` 且内核侧 `pending_after === 0`）。 */
  #voidConfirmed(kernelVoided) {
    return Boolean(kernelVoided) && kernelVoided.bridge === 'ok'
      && Number(kernelVoided.pending_after ?? Number.NaN) === 0;
  }

  /** 会话侧**待应用**意图数（G5 判据：同 id 二次提交后必须 ≥1 或 ack ≠ queued）。 */
  pendingIntentCount(sessionId) {
    return (this.queues.get(sessionId) ?? []).length;
  }

  /**
   * **新连接首帧补齐**（R2 / F4 实测缺陷）：客户端连上时若刚过一个 `snapshot_every` 周期，
   * 它会在最长一个周期内**看不到任何世界状态**（且此前的 delta 因无快照基座被丢弃）。
   * 本方法向内核要一次当前快照并只推给该会话（**不**改世界、**不**进事件链）。
   */
  async primeSession(sessionId) {
    const session = this.sessions.get(sessionId);
    if (!session) return { ok: false, reason: 'E_SESSION_UNKNOWN' };
    const snapshot = await this.kernelClient.requestSnapshot();
    if (!snapshot || snapshot.kind !== 'snapshot_ack') {
      return { ok: false, reason: 'E_KERNEL_UNAVAILABLE' };
    }
    const message = makeSnapshot({
      tick: Number(snapshot.tick ?? session.tick), seq: 0,
      state: snapshot.state, stateHash: snapshot.state_hash,
    });
    const checked = validateServerMessage(message);
    if (!checked.ok) return { ok: false, reason: checked.reason, detail: checked.detail };
    session.tick = Number(snapshot.tick ?? session.tick);
    session.seq += 1;
    const stamped = { ...message, seq: session.seq };
    this.outboxes.get(sessionId).push(stamped);
    this.recordDownstream(sessionId, stamped);
    return { ok: true, tick: session.tick };
  }

  /** 内核 → 客户端：按 seq 单调广播 snapshot/delta/event/tick_meta。 */
  broadcast(message) {
    const checked = validateServerMessage(message);
    if (!checked.ok) {
      return { ok: false, reason: checked.reason, detail: checked.detail };
    }
    for (const [sessionId, outbox] of this.outboxes.entries()) {
      const session = this.sessions.get(sessionId);
      session.seq += 1;
      const stamped = { ...message, seq: session.seq };
      outbox.push(stamped);
      this.recordDownstream(sessionId, stamped);
    }
    return { ok: true, message };
  }

  /** 把桥搬运来的记录映射为下行消息（**不解释状态**，只搬运）。 */
  broadcastKernelRecord(record) {
    const tick = Number(record.tick ?? 0);
    if (record.kind === 'snapshot') {
      return this.broadcast(makeSnapshot({ tick, seq: 0, state: record.state, stateHash: record.state_hash }));
    }
    if (record.kind === 'delta') {
      return this.broadcast(makeDelta({ tick, seq: 0, ops: record.ops ?? [] }));
    }
    if (record.kind === 'event') {
      return this.broadcast(makeEvent({ tick, seq: 0, event: record.event }));
    }
    if (record.kind === 'tick_meta') {
      return this.broadcast(makeTickMeta({ tick, seq: 0, ms: Number(record.ms ?? 0) }));
    }
    return { ok: false, reason: 'E_SCHEMA_INVALID', detail: `unmapped bridge kind ${record.kind}` };
  }

  drainOutbox(sessionId) {
    const outbox = this.outboxes.get(sessionId) ?? [];
    this.outboxes.set(sessionId, []);
    return outbox;
  }

  /** 只读录像出口（R2 / F11）：`record:true` 的会话，每条**下行**消息都交给注入的 recorder。 */
  recordDownstream(sessionId, message) {
    if (!this.recorder || !this.recordingSessions.has(sessionId)) return;
    this.recorder.record(sessionId, message);
  }

  #reply(session, message, audit) {
    const checked = validateServerMessage(message);
    if (!checked.ok) throw new Error(`internal: ${checked.reason} ${checked.detail}`);
    session.seq += 1;
    const stamped = { ...message, seq: session.seq };
    this.outboxes.get(session.session_id).push(stamped);
    this.recordDownstream(session.session_id, stamped);
    if (audit) {
      this.auditRecord({
        at_ms: this.clock(), session_id: session.session_id, mode: session.mode,
        intent_id: audit.intentId, kind: audit.kind, target: audit.target,
        reason_code: audit.reasonCode ?? null, status: stamped.status ?? 'error',
      });
    }
    return { messages: [stamped] };
  }
}

export { InterventionPolicy, DEFAULT_POLICY };
