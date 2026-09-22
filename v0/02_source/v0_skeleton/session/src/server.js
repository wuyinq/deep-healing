/**
 * L2 会话传输层（非权威）——V0 骨架。
 *
 * 硬边界（消灭「双权威」漂移，R7）：
 *   - 不持有世界状态真值；不做规则计算；不做模型调用；不改世界状态；
 *   - 只做搬运与权限检查；权威写入唯一发生在内核 tick 的执行阶段。
 */

export const MESSAGE_TYPES = ['snapshot', 'delta', 'event', 'tick_meta', 'intent_ack', 'error'];

export const ERROR_CODES = [
  'E_MODE_READONLY',
  'E_FORBIDDEN_ACTION',
  'E_RATE_LIMITED',
  'E_COOLDOWN',
  'E_BUDGET_EXHAUSTED',
  'E_TARGET_UNKNOWN',
  'E_SCHEMA_INVALID',
  'E_SESSION_UNKNOWN',
  'E_SESSION_EXPIRED',
  'E_KERNEL_UNAVAILABLE',
  'E_PACK_INVALID',
  'E_CASSETTE_MISS',
];

export class SessionServer {
  constructor({ kernelClient, policy }) {
    this.kernelClient = kernelClient;
    this.policy = policy;
    this.sessions = new Map();
  }

  /** POST /sessions —— 建会话并返回 {session_id, token, tick_rate, schema_version}。 */
  async createSession(body) {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "session-server")');
  }

  /** WS 上行入口：只做鉴权 + 策略校验 + 转发内核，绝不改世界状态。 */
  async onClientMessage(sessionId, raw) {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "session-server")');
  }

  /** 内核 → 客户端：按 seq 单调广播 snapshot/delta/event。 */
  broadcast(message) {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "session-server")');
  }
}
