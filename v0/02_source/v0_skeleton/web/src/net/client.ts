/**
 * 会话客户端（L1 → L2）——V0 骨架。
 *
 * 契约：
 *   connect({url, session_id, mode}) -> TransportHandle
 *   apply(snapshotOrDelta) 幂等：按 tick 丢弃过期、按 seq 去重
 *   submitIntent(intent) 仅 participate 模式；observe 模式本地即拒（E_MODE_READONLY）
 */

export type SessionMode = 'observe' | 'participate';

export interface ServerMessage {
  t: 'snapshot' | 'delta' | 'event' | 'tick_meta' | 'intent_ack' | 'error';
  tick: number;
  seq: number;
  [key: string]: unknown;
}

export class RenderClient {
  private lastSeq = -1;
  private lastTick = -1;
  private mode: SessionMode = 'observe';

  async connect(opts: { url: string; sessionId: string; mode: SessionMode }): Promise<void> {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-client")');
  }

  /** 幂等应用：丢弃乱序与过期（authority wins，V0 无客户端预测）。 */
  apply(message: ServerMessage): boolean {
    if (message.tick < this.lastTick) return false;
    if (message.tick === this.lastTick && message.seq <= this.lastSeq) return false;
    this.lastTick = message.tick;
    this.lastSeq = message.seq;
    return true;
  }

  onMessage(handler: (message: ServerMessage) => void): void {
    this.handler = handler;
  }

  async submitIntent(intent: Record<string, unknown>): Promise<{ status: string; reason?: string }> {
    if (this.mode === 'observe') return { status: 'rejected', reason: 'E_MODE_READONLY' };
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-client")');
  }

  private handler: ((message: ServerMessage) => void) | null = null;
}
