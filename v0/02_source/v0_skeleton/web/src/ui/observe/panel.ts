/**
 * 观察模式 UI（AC-M3-4 / AC-M3-8③）——M3 真实现。
 *
 * 世界视图 + 事件流 + NPC 档案（**脱敏**）+ 时间轴 + 指标 + 世界观两态读法。
 * **无任何写入口**：本类不持有 client、不渲染任何 input/button/submit 控件
 * （`listWriteControls()` 必须返回空数组 —— 真浏览器里的 DOM 枚举判据）。
 */

/**
 * 观察面板内**允许存在**的控件：只读视图控件（切换读法 / 切换模式），不产生任何上行意图。
 * 任何**不在**此清单里的控件（含新增的 `button`）都必须被判为写控件（R2 加严：R1 只看
 * `button[type=submit]`，漏掉普通 `button`）。
 */
const VIEW_ONLY_CONTROL_IDS = ['toggle-reading', 'toggle-mode'];
const WRITE_CONTROL_SELECTORS = ['input', 'textarea', 'select', 'form', '[contenteditable=true]', 'button[type=submit]'];

export interface ObservePanelState {
  tick: number;
  mode: 'observe' | 'participate';
  reading: 'surface' | 'underneath';
}

export class ObservePanel {
  readonly root: HTMLElement;
  private readonly tickEl: HTMLElement;
  private readonly eventEl: HTMLElement;
  private readonly anomalyEl: HTMLElement;
  private readonly npcEl: HTMLElement;
  private readonly metricEl: HTMLElement;
  private readonly liveEl: HTMLElement;
  private tick = 0;
  private events: Array<Record<string, unknown>> = [];

  constructor(host: HTMLElement) {
    this.root = host;
    // **R2 修正（F4 真浏览器实测）**：`index.html` 的 HUD 里已有 `#tick` 等只读占位元素；
    // 若再 `createElement` 一个同 id 元素，`document.getElementById('tick')` 会取到**静态那个**
    // （永不更新）⇒ 面板上可见的 tick 恒为 0、`reveal_at_tick` 永不触发。
    // 因此这里**复用**宿主里已存在的同 id 元素，只在缺失时创建。
    this.tickEl = this.adopt(host, 'tick', 'div');
    this.eventEl = this.adopt(host, 'event-stream', 'ul');
    this.anomalyEl = this.adopt(host, 'anomaly-read', 'div');
    this.npcEl = this.adopt(host, 'npc-profile', 'div');
    this.metricEl = this.adopt(host, 'metrics', 'div');
    // M4 / AC-M4-11③：观察窗的**实时通道读数**（只读文本节点，**不是**控件）
    this.liveEl = this.adopt(host, 'live-readout', 'div');
    // 只读控件：面板本体不产生任何输入控件
    this.root.append(this.tickEl, this.metricEl, this.liveEl, this.anomalyEl, this.eventEl, this.npcEl);
  }

  /** 复用宿主里已有的同 id 元素（避免同 id 重复 ⇒ 取到的永远是未被更新的那一个）。 */
  private adopt(host: HTMLElement, id: string, tag: 'div' | 'ul'): HTMLElement {
    const existing = host.querySelector(`#${id}`);
    if (existing) return existing as HTMLElement;
    const created = document.createElement(tag);
    created.id = id;
    host.append(created);
    return created;
  }

  /** **观察模式无写入口**的 UI 树判据（真浏览器里同样枚举）。 */
  listWriteControls(): string[] {
    const hits = WRITE_CONTROL_SELECTORS.filter((selector) => this.root.querySelector(selector) !== null);
    for (const button of Array.from(this.root.querySelectorAll('button'))) {
      if (!VIEW_ONLY_CONTROL_IDS.includes(button.id)) hits.push(`button#${button.id || '(no-id)'}`);
    }
    return hits;
  }

  apply(message: { t: string; tick: number; [key: string]: unknown }): void {
    if (typeof message.tick === 'number' && message.tick >= this.tick) {
      this.tick = message.tick;
      this.tickEl.textContent = `tick ${message.tick}`;
    }
    if (message.t === 'event') this.renderEventStream([message.event as Record<string, unknown>]);
    if (message.t === 'tick_meta') this.renderMetrics({ tick: this.tick, ms: Number(message.ms ?? 0), tokens_est: 0, cost_usd: 0 });
  }

  renderEventStream(events: Array<Record<string, unknown>>): void {
    for (const event of events) {
      this.events.push(event);
      const item = document.createElement('li');
      item.dataset.eventType = String(event.type ?? '');
      item.textContent = `t${event.tick} ${event.type}`;
      this.eventEl.append(item);
    }
  }

  renderTimeline(checkpoints: Array<{ tick: number; state_hash: string }>): void {
    const list = document.createElement('ol');
    list.id = 'timeline';
    for (const checkpoint of [...checkpoints].sort((left, right) => left.tick - right.tick)) {
      const item = document.createElement('li');
      item.dataset.tick = String(checkpoint.tick);
      item.textContent = `t${checkpoint.tick} ${checkpoint.state_hash.slice(0, 12)}`;
      list.append(item);
    }
    const previous = this.root.querySelector('#timeline');
    if (previous) previous.remove();
    this.root.append(list);
  }

  renderMetrics(metrics: { tick: number; ms: number; tokens_est: number; cost_usd: number }): void {
    this.metricEl.textContent = `tick ${metrics.tick} · ${metrics.ms.toFixed(1)}ms · tokens ${metrics.tokens_est} · $${metrics.cost_usd.toFixed(4)}`;
  }

  /** NPC 档案必须脱敏：不显示玩家原文、不显示内部 trauma 原始数值。 */
  renderNpcProfile(profile: Record<string, unknown>): void {
    const safe = {
      id: profile.id,
      display_name: profile.display_name,
      healing_face: profile.healing_face ?? [],
      hidden_face: profile.hidden_face ?? [],
      trauma_labels: Array.isArray(profile.trauma_flags)
        ? (profile.trauma_flags as Array<{ id?: string }>).map((flag) => flag.id)
        : [],
    };
    this.npcEl.textContent = JSON.stringify(safe);
  }

  /**
   * 世界观两态读法（AC-M3-8③⑤）：`reveal_at_tick` **前后**各给一次可核验输出。
   * 表层读法显示 `surface_read`；深层读法（且已过 `reveal_at_tick`）显示 `underneath_read`。
   */
  renderAnomalyReads(
    worldview: { anomalies?: Array<{ id: string; at_entity: string; surface_read: string; underneath_read: string; reveal_at_tick: number }> },
    tick: number,
    reading: 'surface' | 'underneath',
  ): void {
    const lines: string[] = [];
    for (const anomaly of worldview.anomalies ?? []) {
      const revealed = tick >= anomaly.reveal_at_tick;
      const text = reading === 'underneath' && revealed ? anomaly.underneath_read : anomaly.surface_read;
      lines.push(`${anomaly.id}@${anomaly.at_entity} ${reading === 'underneath' && revealed ? 'underneath' : 'surface'} t=${tick} revealed=${revealed}: ${text}`);
    }
    this.anomalyEl.dataset.reading = reading;
    this.anomalyEl.dataset.tick = String(tick);
    this.anomalyEl.textContent = lines.join('\n');
  }

  get eventsSeen(): number {
    return this.events.length;
  }

  /**
   * 实时通道读数（M4 / AC-M4-11③）：页面显示的是**当前**时刻（通道 tick + 世界钟 + 墙上钟对照）。
   *
   * 只读：只写文本节点与 `dataset`，**不新增任何控件**（`listWriteControls()` 仍必须为空）。
   * `channelTick` 与墙上钟的分钟差**如实披露**（1× 档下世界钟领先，属预期，不是错误）。
   */
  renderLiveReadout(readout: {
    connected: boolean;
    channelTick: number;
    worldClock: string;
    wallClock: string;
    observers: number;
    timezone: string;
    stateHash: string;
    clockOffsetMinutes: number;
  }): void {
    this.liveEl.dataset.connected = String(readout.connected);
    this.liveEl.dataset.channelTick = String(readout.channelTick);
    this.liveEl.dataset.worldClock = readout.worldClock;
    this.liveEl.dataset.wallClock = readout.wallClock;
    this.liveEl.dataset.observers = String(readout.observers);
    this.liveEl.dataset.stateHash = readout.stateHash;
    this.liveEl.dataset.clockOffsetMinutes = String(readout.clockOffsetMinutes);
    this.liveEl.textContent = [
      `live channel ${readout.connected ? 'connected' : 'offline'} (read-only)`,
      `world tick ${readout.channelTick} · world clock ${readout.worldClock} ${readout.timezone}`,
      `wall clock ${readout.wallClock} · offset +${readout.clockOffsetMinutes} min (expected at 1x)`,
      `observers ${readout.observers} · state ${readout.stateHash.slice(0, 12)}`,
    ].join('\n');
  }

  /** 实时读数（供真浏览器验收脚本读取；不经 DOM 解析）。 */
  liveReadout(): Record<string, string> {
    return { ...this.liveEl.dataset } as Record<string, string>;
  }
}
