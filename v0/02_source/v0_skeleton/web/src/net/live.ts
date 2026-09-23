/**
 * 实时观察通道客户端（M4 / W12；AC-M4-10 / AC-M4-11③）——**只读**。
 *
 * 消费内核侧 `live.py` 的 SSE 通道：
 *   - `event: state` —— **当前** tick 的 `world.to_state()` 只读投影（不是从 genesis 重放）；
 *   - `event: clock` —— 同一 tick 的世界钟读数（UTC+8）。
 *
 * 边界（硬）：**零写路径** —— 本类只有 `EventSource`（HTTP GET）与本地读数缓存，
 * 不发任何上行请求、不提供任何写世界的方法。UI 面板因此不新增写控件。
 */

export interface LiveClockFrame {
  tick: number;
  clock: string;
  timezone: string;
}

export interface LiveStateFrame {
  tick: number;
  world_day?: number;
  timezone?: string;
  state_hash: string;
  event_chain_hash: string;
  observers?: number;
  read_only?: boolean;
  state?: Record<string, unknown>;
}

export interface LiveReadout {
  connected: boolean;
  channelTick: number;
  worldClock: string;
  timezone: string;
  observers: number;
  stateHash: string;
  eventChainHash: string;
  /** 浏览器侧墙上钟（UTC+8），由 `Intl` 取，**不**参与世界状态 */
  wallClock: string;
  /** 通道 tick 与墙上钟的分钟差（**原始量披露**：1× 档下世界钟会领先，属预期） */
  clockOffsetMinutes: number;
}

/** 墙上钟（UTC+8）读数：`HH:MM`。 */
export function wallClockUtc8(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(now);
  return parts;
}

function minutesOf(text: string): number | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(text.trim());
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2]);
}

export class LiveChannel {
  readonly url: string;
  private source: EventSource | null = null;
  private state: LiveStateFrame | null = null;
  private clock: LiveClockFrame | null = null;

  constructor(url = '/live/stream') {
    this.url = url;
  }

  /** 连入通道（只读 GET）。返回是否已建立连接。 */
  connect(): boolean {
    if (this.source) return true;
    if (typeof EventSource === 'undefined') return false;
    this.source = new EventSource(this.url);
    this.source.addEventListener('state', (event) => {
      try {
        this.state = JSON.parse((event as MessageEvent).data) as LiveStateFrame;
      } catch {
        // 非法帧**不**污染读数（保持上一帧，不伪造）
      }
    });
    this.source.addEventListener('clock', (event) => {
      try {
        this.clock = JSON.parse((event as MessageEvent).data) as LiveClockFrame;
      } catch {
        /* 同上 */
      }
    });
    return true;
  }

  close(): void {
    if (this.source) {
      this.source.close();
      this.source = null;
    }
  }

  get connected(): boolean {
    return this.source !== null && this.source.readyState !== EventSource.CLOSED;
  }

  /** 通道**读到**的 tick（不是从 0 重放：通道连入即推当前 tick）。 */
  get channelTick(): number {
    return this.state?.tick ?? this.clock?.tick ?? 0;
  }

  get worldClock(): string {
    return this.clock?.clock ?? '';
  }

  get observers(): number {
    return Number(this.state?.observers ?? 0);
  }

  readout(now: Date = new Date()): LiveReadout {
    const wall = wallClockUtc8(now);
    const world = minutesOf(this.worldClock);
    const wallMinutes = minutesOf(wall);
    const offset = world !== null && wallMinutes !== null
      ? (world - wallMinutes + 24 * 60) % (24 * 60)
      : 0;
    return {
      connected: this.connected,
      channelTick: this.channelTick,
      worldClock: this.worldClock,
      timezone: this.clock?.timezone ?? this.state?.timezone ?? 'UTC+8',
      observers: this.observers,
      stateHash: String(this.state?.state_hash ?? ''),
      eventChainHash: String(this.state?.event_chain_hash ?? ''),
      wallClock: wall,
      clockOffsetMinutes: offset,
    };
  }

  /** 只读投影（原样透传内核的 `world.to_state()`；**不**重算、**不**自造）。 */
  stateProjection(): Record<string, unknown> | null {
    return this.state?.state ?? null;
  }
}
