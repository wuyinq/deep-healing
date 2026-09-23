/**
 * 会话客户端（L1 → L2）——M3 真实现。
 *
 * 契约：
 *   connect({url, sessionId, mode}) -> TransportHandle
 *   apply(snapshotOrDelta) **幂等**：按 tick 丢弃过期、按 (tick, seq) 去重
 *   submitIntent(intent) 仅 participate 模式；observe 模式**本地即拒**（E_MODE_READONLY）
 *
 * 硬边界：零业务规则、零模型调用、零世界状态写；不直读内容包与事件日志文件。
 * 权威在服务端：客户端**不做预测**，跨 tick 边界的迟到消息一律丢弃、绝不回填。
 */

export type SessionMode = 'observe' | 'participate';

export interface ServerMessage {
  t: 'snapshot' | 'delta' | 'event' | 'tick_meta' | 'intent_ack' | 'error';
  tick: number;
  seq: number;
  [key: string]: unknown;
}

export interface SessionInfo {
  session_id: string;
  token: string;
  tick_rate: number;
  schema_version: string;
  impact_budget_remaining?: number;
}

export class RenderClient {
  private lastSeq = -1;
  private lastTick = -1;
  private applied = new Set<string>();
  private handler: ((message: ServerMessage) => void) | null = null;
  private socket: WebSocket | null = null;
  mode: SessionMode = 'observe';
  sessionId = '';
  session: SessionInfo | null = null;
  /** 本会话请求的街区包 id（**渲染层据此决定世界观 URL**，不写死 pack；R2 / F13）。 */
  districtPackId = 'xingfu-xiaoqu';

  async connect(opts: { url: string; mode: SessionMode; httpBase?: string; districtPackId?: string; clientVersion?: string }): Promise<SessionInfo> {
    this.mode = opts.mode;
    this.districtPackId = opts.districtPackId ?? this.districtPackId;
    const base = opts.httpBase ?? '';
    const response = await fetch(`${base}/sessions`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        mode: opts.mode,
        district_pack_id: this.districtPackId,
        client_version: opts.clientVersion ?? '0.3.0',
      }),
    });
    if (!response.ok) throw new Error(`E_SESSION_UNKNOWN: POST /sessions -> ${response.status}`);
    this.session = (await response.json()) as SessionInfo;
    this.sessionId = this.session.session_id;
    const wsUrl = `${opts.url}/${this.session.session_id}`;
    const socket = new WebSocket(wsUrl.startsWith('ws') ? wsUrl : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}${wsUrl}`);
    this.socket = socket;
    socket.onmessage = (event: MessageEvent) => {
      let message: ServerMessage;
      try {
        message = JSON.parse(String(event.data)) as ServerMessage;
      } catch {
        return;
      }
      if (this.apply(message) && this.handler) this.handler(message);
    };
    return this.session;
  }

  /** 幂等应用：丢弃乱序与过期（authority wins，V0 无客户端预测）。 */
  apply(message: ServerMessage): boolean {
    if (!message || typeof message.tick !== 'number' || typeof message.seq !== 'number') return false;
    const key = `${message.tick}:${message.seq}:${message.t}`;
    if (this.applied.has(key)) return false; // 同一消息 apply 两次 ⇒ 幂等
    if (message.tick < this.lastTick) return false; // 过期 tick ⇒ 丢弃
    if (message.tick === this.lastTick && message.seq <= this.lastSeq) return false; // 乱序 ⇒ 丢弃
    this.applied.add(key);
    this.lastTick = message.tick;
    this.lastSeq = message.seq;
    return true;
  }

  onMessage(handler: (message: ServerMessage) => void): void {
    this.handler = handler;
  }

  async submitIntent(intent: Record<string, unknown>): Promise<{ status: string; reason?: string }> {
    if (this.mode === 'observe') return { status: 'rejected', reason: 'E_MODE_READONLY' };
    if (!this.socket || this.socket.readyState !== 1) return { status: 'rejected', reason: 'E_KERNEL_UNAVAILABLE' };
    this.socket.send(JSON.stringify({ t: 'intent', ...intent }));
    return { status: 'queued' };
  }

  get appliedKeys(): string[] {
    return [...this.applied];
  }
}
