/**
 * 内核上行/下行桥（V0 骨架）。
 *
 * 内核是唯一权威：本模块只把内核事件/快照搬给会话，把会话意图搬给内核意图队列；
 * 不做任何规则计算、不做模型调用、不缓存世界状态真值。
 */

export class KernelClient {
  constructor({ kernelWsUrl }) {
    this.kernelWsUrl = kernelWsUrl;
  }

  /** 订阅内核只读流（events/snapshots/ticks）。 */
  async subscribe(handlers) {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "session-upstream")');
  }

  /** 把意图投递到内核意图队列；返回内核 ack（queued/rejected + reason）。 */
  async submitIntent(sessionId, intent) {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "session-upstream")');
  }
}
