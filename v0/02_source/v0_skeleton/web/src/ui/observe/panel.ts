/**
 * 观察模式 UI（AC-M3-4 / AC-M3-8③ / REQ-20261012-001 T1+T2）——M3 真实现。
 *
 * 世界视图 + 事件流 + NPC 档案（**脱敏**）+ 时间轴 + 指标 + 世界观两态读法。
 * **无任何写入口**：本类不持有 client、不渲染任何 input/button/submit 控件
 * （`listWriteControls()` 必须返回空数组 —— 真浏览器里的 DOM 枚举判据）。
 *
 * REQ-20261012-001 追加：
 *   - **T1 折叠**：`setCollapsed()` / `isCollapsed()` —— 只切 `#hud` 的 `class` / `dataset`
 *     与折叠按钮文案，**不增删任何节点**（`#tick` / `#causal-trace` 等被 `adopt()` 按 id 复用，
 *     移除会打断既有取数路径）。
 *   - **T2 对象选择**：`renderTargets()` 渲染**运行时派生**的观察对象按钮；每个按钮创建时把
 *     **元素引用**登记进 `viewControlRefs`（只读视图控件）。
 */

/**
 * 只读视图控件：允许存在于观察面板内、不产生任何上行意图的控件。
 *
 * ⚠️ **本名单只用于「构造时按 id 定位这几个既有节点」**，**不得**当作放行判据：
 * 放行一律按 `viewControlRefs` 里的**元素引用**判定（Raven 预审 M-3 实证：用 id 字符串做白名单时，
 * 注入第二个 `id="toggle-mode"` 的 button 会**逃逸**）。
 */
const VIEW_ONLY_CONTROL_IDS = ['toggle-reading', 'toggle-mode', 'observe-collapse-toggle'];

/**
 * **写形状**的 DOM 选择器。`[contenteditable]` 是 REQ §4.1 的原文口径
 * （`[contenteditable=true]` 会漏判 `contenteditable=""` / `"plaintext-only"` —— 预审 M-11 实证）。
 */
const WRITE_CONTROL_SELECTORS = ['input', 'textarea', 'select', 'form', '[contenteditable]', 'button[type=submit]'];

/**
 * 事件流空态的**中性可见文案**（r3 / SHOULD-7）。
 *
 * 面板**不是**事件通道的权威 ⇒ 用户可见文本只陈述本面板能确证的事实（「当前没有事件」），
 * **不对缺失原因下断言**。原因本身（机器可读）见 `EMPTY_REASON_*`，落在
 * `#event-stream[data-empty-reason]`，供验收/诊断读取。
 */
const EMPTY_TEXT_NO_EVENTS = '暂无事件';

/** 空态原因（机器可读）：本面板**尚未收到任何**事件记录。 */
const EMPTY_REASON_NO_EVENTS_RECEIVED = 'no-event-records-received';

/** 空态原因（机器可读）：收到了事件，但**没有一条**匹配当前的实体过滤。 */
const EMPTY_REASON_NO_MATCH_FOR_ENTITY = 'no-event-matches-entity-filter';

/** 观察对象（**运行时派生**；源码逻辑分支里**不得**出现任何具体 pack / NPC / 实体 id）。 */
export interface ObserveTargetOption {
  kind: 'overview' | 'npc' | 'entity';
  target: string;
  label: string;
}

export interface ObserveSelection {
  kind: 'overview' | 'npc' | 'entity';
  target: string;
}

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
  /** T2：观察对象选择容器（`index.html` 里的空容器；缺失时按既有 `adopt()` 口径补建）。 */
  private readonly targetsEl: HTMLElement;
  /** T1：折叠按钮（既有静态节点；缺失 ⇒ `null`，功能降级但**不抛**）。 */
  private readonly collapseButton: HTMLElement | null;
  private tick = 0;
  private events: Array<Record<string, unknown>> = [];
  /** T1 状态（默认展开，与现状一致）。 */
  private collapsed = false;
  /** T2 状态（默认总览 = 既有 `focusNpc()` 自动行为）。 */
  private selected: ObserveSelection = { kind: 'overview', target: 'overview' };
  private options: ObserveTargetOption[] = [];
  /** `renderTargets` 的重建签名（M-10：仅在派生清单**变化**时重建，避免每次轮询都丢焦点）。 */
  private targetSignature: string | null = null;
  /**
   * **允许集合 = 元素引用集合**（不是 id 字符串）：构造时登记既有只读控件节点，
   * `renderTargets` 时登记自己创建的按钮节点。判定见 `listWriteControls()`。
   */
  private readonly viewControlRefs = new Set<Element>();
  /** 上一次由**本 panel** 创建的观察对象按钮（重建时只清理这些引用）。 */
  private readonly targetRefs = new Set<Element>();
  /** 事件流过滤（`{entity}`；`null` = 不按实体过滤）。 */
  private eventFilter: { entity?: string } | null = null;
  private renderedEventCount = 0;
  private readonly onSelect: ((selection: ObserveSelection) => void) | null;

  constructor(host: HTMLElement, options: { onSelect?: (selection: ObserveSelection) => void } = {}) {
    this.root = host;
    this.onSelect = options.onSelect ?? null;
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
    // REQ-20261012-001 · T2：对象选择容器（`index.html` 提供空容器）
    this.targetsEl = this.adopt(host, 'observe-targets', 'div');
    // 只读控件：面板本体不产生任何输入控件
    this.root.append(this.tickEl, this.metricEl, this.liveEl, this.anomalyEl, this.eventEl, this.npcEl);
    this.collapseButton = host.querySelector('#observe-collapse-toggle') as HTMLElement | null;
    // **加严（预审 M-3）**：白名单按**元素引用**登记（id 只用于定位这几个既有节点）。
    for (const id of VIEW_ONLY_CONTROL_IDS) this.registerViewControl(host.querySelector(`#${id}`));
    this.collapseButton?.addEventListener('click', () => this.setCollapsed(!this.collapsed));
    this.syncCollapseState();
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

  /** 把一个**只读视图控件**按元素引用登记进允许集合（`null` ⇒ 忽略）。 */
  private registerViewControl(element: Element | null): void {
    if (element) this.viewControlRefs.add(element);
  }

  /**
   * **观察模式无写入口**的 UI 树判据（真浏览器里同样枚举）。
   *
   * 加严口径（预审 M-3 / M-11）：
   *   - 放行按 `viewControlRefs` 的**元素引用**，**不得**按 id 字符串 —— 否则复制一个
   *     `id="toggle-mode"` 的第二个 button 会逃逸；
   *   - `[contenteditable]`（而非 `[contenteditable=true]`）⇒ `contenteditable=""` /
   *     `"plaintext-only"` 都命中。
   *
   * **r2 补覆盖（Raven R-2 / B5-B7）**：`root.querySelectorAll()` 的**天然视野**不含
   * 三类「有写形状却在选择器视野外」的形态 ⇒ 这里显式下钻：
   *   ① **开放 shadow root**（`element.shadowRoot`，逐层递归）；
   *   ② **同源 iframe**（`iframe.contentDocument`，逐层递归；跨源读不到 ⇒ 不覆盖，见边界声明）；
   *   ③ **`document.designMode === 'on'`**（整页可编辑但**零 `contenteditable` 属性**）⇒
   *      判红并给出显式原因串 `document:designMode=on`。
   * **r3 补覆盖（Raven R2-1 / §16.4.3-N1）**：`querySelectorAll('*')` 只返回**后代**、**不含 scope 自身**
   * ⇒ 若只对「后代」取下钻字段，则**作用域根 `#hud` 自己**的 shadow root 永远进不了枚举集合。
   * 现在**对 scope 自身也取一次** `shadowRoot`（见循环内 `const own = …`）⇒ 该层已被覆盖。
   * 下钻**只**加枚举深度，**不**放宽放行判据：普通节点（如 `div`）仍不得命中。
   *
   * **边界声明（必须随交付保留，不得读作"全无写入口"）**：
   *   ① 作用域 = `#hud` 子树；`#player-ui` 内的真写控件**不在**作用域内（L-5）。
   *   ② 本判据只证「无**写形状**的 DOM 节点」，**不证**「无写行为」——事件委托、白名单控件
   *      自身的副作用（如折叠按钮写 `sessionStorage`）一律看不见（M-4 / E-4）。
   *   ③ **跨源 iframe** 与 **closed shadow root**（`attachShadow({mode:'closed'})`）**读不到** ⇒ 不覆盖。
   *   ④ 作用域可被脚本搬走：容器移出 `#hud` 后其中节点不再被枚举（E-5 / R-10）。
   *   ⑤ **时点快照**：判据只反映**调用那一刻**的 DOM（之后由 `MutationObserver` / 定时器插入的节点不在内）；
   *      `srcdoc` iframe 在 `readyState='loading'` 期间其 `contentDocument` 还是空的（R2-L5）。
   *   ⑥ `<template>` 的 `content` 内节点**不在文档树**中（不可渲染/不可点）⇒ 不枚举、也不构成写入口（R2-L6）。
   *   ⑦ `document.designMode` 只看**顶层文档**；子文档自身的 `designMode` 不单独判红（E-5'）。
   *   ⑧ id 唯一性的范围：文档对象不可达时，`takenIds()` 只能保证**面板内**唯一（R1.5 / E-6'）。
   */
  listWriteControls(): string[] {
    const hits = new Set<string>();
    const scopes: Array<Element | Document | ShadowRoot> = [this.root];
    const visited = new Set<unknown>();
    while (scopes.length > 0) {
      const scope = scopes.shift() as Element | Document | ShadowRoot;
      if (visited.has(scope)) continue;
      visited.add(scope);
      for (const selector of WRITE_CONTROL_SELECTORS) {
        if (scope.querySelector(selector) !== null) hits.add(selector);
      }
      for (const button of Array.from(scope.querySelectorAll('button'))) {
        if (!this.viewControlRefs.has(button)) hits.add(`button#${button.id || '(no-id)'}`);
      }
      // r3（Raven R2-1）：`scope.querySelectorAll('*')` 只给**后代**、**不含 scope 自身**
      // ⇒ 作用域根（`#hud`）**自己**的 shadow root 会漏掉（对 `ShadowRoot` / `Document` 是 no-op）。
      const own = (scope as Element & { shadowRoot?: ShadowRoot | null }).shadowRoot;
      if (own) scopes.push(own);
      for (const element of Array.from(scope.querySelectorAll('*'))) {
        const shadow = (element as Element & { shadowRoot?: ShadowRoot | null }).shadowRoot;
        if (shadow) scopes.push(shadow);
        if (element.tagName === 'IFRAME') {
          const nested = sameOriginDocumentOf(element as HTMLIFrameElement);
          if (nested) scopes.push(nested);
        }
      }
    }
    if (designModeIsOn(this.root)) hits.add('document:designMode=on');
    return [...hits];
  }

  /**
   * T1：折叠 / 展开。**只切 class / dataset / 按钮文案**，不增删任何节点（`adopt()` 按 id 复用）。
   */
  setCollapsed(collapsed: boolean): void {
    this.collapsed = Boolean(collapsed);
    this.syncCollapseState();
  }

  isCollapsed(): boolean {
    return this.collapsed;
  }

  private syncCollapseState(): void {
    this.root.classList.toggle('collapsed', this.collapsed);
    this.root.dataset.collapsed = String(this.collapsed);
    if (this.collapseButton) {
      // 按钮文案描述**将发生的动作**：展开态显示「折叠」，折叠态显示「展开」。
      this.collapseButton.textContent = this.collapsed ? '展开' : '折叠';
      this.collapseButton.setAttribute('aria-expanded', String(!this.collapsed));
    }
  }

  /**
   * T2：渲染观察对象选择控件（只读视图控件）。
   *
   * - 每个对象一个 `<button type="button" id="observe-target-<slug>">`，带
   *   `dataset.viewControl="read-only"` / `dataset.target` / `dataset.kind`；
   * - 渲染一律用 `textContent`（**不用** `innerHTML`）；
   * - 仅在派生清单**签名变化**时重建（M-10）；重建时只清理**上一次由本 panel 创建**的引用，
   *   并恢复按钮引用登记（`viewControlRefs`）。
   */
  renderTargets(options: ObserveTargetOption[], selected: ObserveSelection | null = null): void {
    this.options = options.map((option) => ({ ...option }));
    if (selected) this.selected = { ...selected };
    const signature = this.options.map((option) => `${option.kind}:${option.target}:${option.label}`).join('|');
    if (signature !== this.targetSignature) {
      this.rebuildTargets();
      this.targetSignature = signature;
    }
    this.syncTargetPressedState();
  }

  private rebuildTargets(): void {
    for (const ref of this.targetRefs) {
      this.viewControlRefs.delete(ref);
      ref.remove();
    }
    this.targetRefs.clear();
    const taken = this.takenIds();
    for (const option of this.options) {
      const button = document.createElement('button');
      button.type = 'button';
      button.id = targetButtonId(option, taken);
      taken.add(button.id);
      button.dataset.viewControl = 'read-only';
      button.dataset.target = option.target;
      button.dataset.kind = option.kind;
      button.textContent = option.label;
      button.setAttribute('aria-pressed', 'false');
      button.addEventListener('click', () => {
        this.selected = { kind: option.kind, target: option.target };
        this.syncTargetPressedState();
        this.onSelect?.({ kind: option.kind, target: option.target });
      });
      this.viewControlRefs.add(button);
      this.targetRefs.add(button);
      this.targetsEl.append(button);
    }
  }

  /** 文档里已被占用的 `id`（用于保证新按钮 id **唯一**；读不到 ⇒ 只按本次渲染去重）。 */
  private takenIds(): Set<string> {
    const taken = new Set<string>();
    try {
      const owner = this.targetsEl.ownerDocument as Document | null | undefined;
      for (const element of Array.from(owner?.querySelectorAll('[id]') ?? [])) {
        const id = (element as HTMLElement).id;
        if (id) taken.add(id);
      }
    } catch {
      // 拿不到文档不在异常路径上放大：退化为「本次渲染内唯一」
    }
    for (const ref of this.viewControlRefs) {
      const id = (ref as HTMLElement).id;
      if (id) taken.add(id);
    }
    return taken;
  }

  private syncTargetPressedState(): void {
    for (const ref of this.targetRefs) {
      const button = ref as HTMLElement;
      const pressed = button.dataset.kind === this.selected.kind && button.dataset.target === this.selected.target;
      button.setAttribute('aria-pressed', String(pressed));
    }
  }

  /** T2：设置当前选中（程序化，用于启动恢复；不触发 `onSelect`）。 */
  setSelection(selection: ObserveSelection): void {
    this.selected = { ...selection };
    this.syncTargetPressedState();
  }

  /** T2：面板侧状态读数（供 `main.ts` 装配与真浏览器回读）。 */
  viewState(): { collapsed: boolean; selected: ObserveSelection; options: ObserveTargetOption[]; targetIds: string[] } {
    return {
      collapsed: this.collapsed,
      selected: { ...this.selected },
      options: this.options.map((option) => ({ ...option })),
      targetIds: [...this.targetRefs].map((ref) => (ref as HTMLElement).id),
    };
  }

  apply(message: { t: string; tick: number; [key: string]: unknown }): void {
    if (typeof message.tick === 'number' && message.tick >= this.tick) {
      this.tick = message.tick;
      this.tickEl.textContent = `tick ${message.tick}`;
    }
    if (message.t === 'event') this.renderEventStream([message.event as Record<string, unknown>]);
    if (message.t === 'tick_meta') this.renderMetrics({ tick: this.tick, ms: Number(message.ms ?? 0), tokens_est: 0, cost_usd: 0 });
  }

  /**
   * 事件流。`filter` 传入 ⇒ 按实体过滤；**不传** ⇒ 沿用面板当前过滤态
   * （默认 `null` = 不过滤，与今天逐字相同）。
   *
   * 实体字段来源（R-4）：冻结契约 `v0/02_source/events.schema.json` 里可用的实体字段只有
   * 两处 —— 顶层 `actor`（pattern 含实体 id）与 `npc.action` / `npc.decision` 的
   * `payload.target_entity`。**无匹配 ⇒ 显式空态**，不伪造事件。
   */
  renderEventStream(events: Array<Record<string, unknown>>, filter?: { entity?: string }): void {
    const before = this.eventFilter?.entity ?? null;
    for (const event of events) this.events.push(event);
    if (filter !== undefined) this.eventFilter = filter;
    const effective = this.eventFilter?.entity ?? null;
    if (effective !== before) { this.rebuildEventItems(); return; }
    this.removeEmptyStateItems();
    for (const event of events) {
      if (effective !== null && !eventMatchesEntity(event, effective)) continue;
      this.eventEl.append(this.eventItemFor(event));
      this.renderedEventCount += 1;
    }
    this.syncEventStreamState();
  }

  /** 切换/清空实体过滤（按当前事件缓冲**重渲**，如实呈现匹配或空态）。 */
  setEventFilter(filter: { entity?: string } | null): void {
    this.eventFilter = filter;
    this.rebuildEventItems();
  }

  eventStreamFilter(): { entity: string | null } {
    return { entity: this.eventFilter?.entity ?? null };
  }

  private eventItemFor(event: Record<string, unknown>): HTMLElement {
    const item = document.createElement('li');
    item.dataset.eventType = String(event.type ?? '');
    item.textContent = `t${event.tick} ${event.type}`;
    return item;
  }

  private removeEmptyStateItems(): void {
    for (const child of Array.from(this.eventEl.children) as HTMLElement[]) {
      if (child.dataset.emptyState) child.remove();
    }
  }

  private rebuildEventItems(): void {
    for (const child of Array.from(this.eventEl.children)) child.remove();
    this.renderedEventCount = 0;
    const effective = this.eventFilter?.entity ?? null;
    for (const event of this.events) {
      if (effective !== null && !eventMatchesEntity(event, effective)) continue;
      this.eventEl.append(this.eventItemFor(event));
      this.renderedEventCount += 1;
    }
    this.syncEventStreamState();
  }

  private syncEventStreamState(): void {
    const effective = this.eventFilter?.entity ?? null;
    this.eventEl.dataset.filterEntity = effective ?? '';
    this.eventEl.dataset.renderedCount = String(this.renderedEventCount);
    if (this.events.length === 0) {
      // SHOULD-7（r3 落地）：**可见文本不得断言因果** —— 面板不是事件通道的权威，
      // 「为什么没有事件」这一事实改由**机器可读**字段承载（`#event-stream[data-empty-reason]`），
      // 用户可见文本只陈述本面板自身能确证的事实（当前没有事件）。
      this.eventEl.dataset.emptyReason = EMPTY_REASON_NO_EVENTS_RECEIVED;
      this.appendEmptyState('empty', EMPTY_TEXT_NO_EVENTS);
      return;
    }
    if (this.renderedEventCount === 0) {
      this.eventEl.dataset.emptyReason = EMPTY_REASON_NO_MATCH_FOR_ENTITY;
      this.appendEmptyState('no-match-for-entity',
        `实体 ${String(effective)} 暂无事件（事件流中无 actor / payload.target_entity 匹配项）`);
      return;
    }
    delete this.eventEl.dataset.emptyReason;
  }

  private appendEmptyState(kind: string, text: string): void {
    const item = document.createElement('li');
    item.dataset.emptyState = kind;
    item.textContent = text;
    this.eventEl.append(item);
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
   *
   * `filter`（REQ-20261012-001 · T2）：传 `{entity}` ⇒ 只渲 `at_entity === entity` 的那一条；
   * **不传 ⇒ 渲染文本与今天逐字相同**（既有调用点零改动）。附加读回键
   * `dataset.entityFilter`（`''` = 不按实体过滤 —— 是「不过滤」这个事实的**显式**读数，不是兜底值）。
   */
  renderAnomalyReads(
    worldview: { anomalies?: Array<{ id: string; at_entity: string; surface_read: string; underneath_read: string; reveal_at_tick: number }> },
    tick: number,
    reading: 'surface' | 'underneath',
    filter?: { entity?: string },
  ): void {
    const entityFilter = filter?.entity ?? null;
    const lines: string[] = [];
    for (const anomaly of worldview.anomalies ?? []) {
      if (entityFilter !== null && anomaly.at_entity !== entityFilter) continue;
      const revealed = tick >= anomaly.reveal_at_tick;
      const text = reading === 'underneath' && revealed ? anomaly.underneath_read : anomaly.surface_read;
      lines.push(`${anomaly.id}@${anomaly.at_entity} ${reading === 'underneath' && revealed ? 'underneath' : 'surface'} t=${tick} revealed=${revealed}: ${text}`);
    }
    this.anomalyEl.dataset.reading = reading;
    this.anomalyEl.dataset.tick = String(tick);
    this.anomalyEl.dataset.entityFilter = entityFilter ?? '';
    this.anomalyEl.textContent = lines.join('\n');
  }

  get eventsSeen(): number {
    return this.events.length;
  }

  /** 已收到的事件（只读快照；供回读面与真浏览器取证）。 */
  receivedEvents(): Array<Record<string, unknown>> {
    return this.events.map((event) => ({ ...event }));
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

/**
 * 事件是否属于某实体。字段依据（冻结契约 `events.schema.json`）：
 *   - 顶层 `actor`（`pattern` 含实体 id；`npc.action` / `npc.decision` / `memory.written` 的 actor = NPC id）；
 *   - `payload.target_entity`（`npc.action` / `npc.decision` 声明为 `string|null`）——
 *     这是**房间 / 物件实体**唯一可能出现的字段（异常点实体是房间/物件，不是 NPC）。
 * 两处都不匹配 ⇒ 该事件不属于该实体（**不猜、不补造**）。
 */
export function eventMatchesEntity(event: Record<string, unknown>, entity: string): boolean {
  if (typeof event.actor === 'string' && event.actor === entity) return true;
  const payload = event.payload;
  if (payload && typeof payload === 'object') {
    const target = (payload as Record<string, unknown>).target_entity;
    if (typeof target === 'string' && target === entity) return true;
  }
  return false;
}

/** 由目标 id 派生 DOM 安全 slug（**不硬编码**任何具体 id）。 */
export function slugForTarget(target: string): string {
  const slug = target.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return slug === '' ? 'unnamed' : slug;
}

/**
 * 对象按钮的 DOM id（SHOULD-6 / R-4）：**必须唯一**，并在需要时**用 kind 消歧**。
 *
 * 为什么不是「一律加 kind 前缀」：r1 的用例逐字断言了 `observe-target-<slug>` 这组 id
 * （`render-client.test.ts` 的 `req20261012_t2_…`），而任务书同时要求「既有用例零删除、
 * 即使删除 hunk = 0」⇒ 改写那行断言不可行。因此取**目的等价**的规则：
 *   ① **无冲突** ⇒ 沿用 r1 既有 id（`observe-target-<slug>`）—— 兼容、可点击、可复算；
 *   ② **base 已被占用**（跨 kind 同 target / slug 非单射）⇒ 改用**带 kind 的**限定名
 *      （`observe-target-<kind>-<slug>`）消歧；
 *   ③ 限定名也被占用 ⇒ 追加 `-2` / `-3`…。
 * 如此「同 id 多按钮」这一实际危害被消除（R-4 的关闭判据），且撞名情形 id 里带 kind 可自辨。
 */
export function targetButtonId(option: ObserveTargetOption, taken: ReadonlySet<string>): string {
  const slug = slugForTarget(option.target);
  const base = `observe-target-${slug}`;
  if (!taken.has(base)) return base;
  const qualified = `observe-target-${option.kind}-${slug}`;
  if (!taken.has(qualified)) return qualified;
  let suffix = 2;
  while (taken.has(`${qualified}-${suffix}`)) suffix += 1;
  return `${qualified}-${suffix}`;
}

/** 跨源 iframe：读 `contentDocument` 拿不到（或抛）⇒ 返回 `null`（**不覆盖**，属显式边界）。 */
function sameOriginDocumentOf(frame: HTMLIFrameElement): Document | null {
  try {
    return frame.contentDocument ?? null;
  } catch {
    return null;
  }
}

/**
 * `document.designMode === 'on'` ⇒ 整页可编辑，但**没有任何** `contenteditable` 属性
 * （属性选择器看不见它）⇒ 这是「有写形状却在选择器视野外」的第三类形态，必须判红。
 * 读不到 ⇒ `false`（不抛）。
 */
function designModeIsOn(root: Element): boolean {
  try {
    // 定位于**该元素所属的文档**；取不到就退回全局 `document`（仅为定位，**不是**取值兜底：
    // 两条路径都拿不到时返回 `false`，而「读不到 ⇒ 判红」本身不适用于"文档不存在"这种非浏览器场景）。
    const doc = (root.ownerDocument ?? (typeof document === 'undefined' ? null : document)) as
      (Document & { designMode?: string }) | null;
    return doc?.designMode === 'on';
  } catch {
    return false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 观察视图模型（REQ-20261012-001 · T2 / AC-10）—— **纯函数 + 可注入存储**
//
// 放在本文件（而非 `main.ts`）的**唯一理由**是可判性：`main.ts` 的局部 import 用 `.js` 说明符
// （vite 口径），Node 的 `--test` 路径解析不了 ⇒ 放在 `panel.ts`（零 import、零 DOM 依赖）
// 才能被 `node --test` 直接跑判据。**语义归属不变**：装配与选择语义仍在 `main.ts`。
// ─────────────────────────────────────────────────────────────────────────────

/** 持久化键（`sessionStorage`；**否**用 `localStorage` —— 跨会话残留会污染验收读数）。 */
export const OBSERVE_VIEW_KEY = 'deephealing.observe.view';

export interface PersistedObserveView {
  collapsed: boolean;
  kind: ObserveSelection['kind'];
  target: string;
}

/**
 * T2：观察对象清单 —— **运行时派生**（唯一取值路径）。
 *
 * 顺序与去重规则（设计 §4.4）：`overview` 恒在首位 → `npcIds()` **升序** → `anomalies[].at_entity`
 * **按 worldview 顺序**。
 *
 * **去重键 = `(kind, target)` 二元组**（r2 修复 MUST-2 / Raven R-3）：只去「同一 kind 同一 target」
 * 的重复项；**跨 kind 的同名目标不得合并** —— 否则 `at_entity` 与某个 NPC id 同名（或等于 `'overview'`）时
 * 该**实体**会从清单里**静默消失**、在 UI 上不可选且无任何提示。
 * 跨 kind 撞名仍会出现在清单里，并由 `optionTargetCollisions()` 显式披露。
 * 空 / 非字符串 `at_entity` 跳过。
 */
export function observeOptionsFor(
  worldview: { anomalies?: Array<{ at_entity?: unknown }> },
  npcIds: readonly string[],
): ObserveTargetOption[] {
  const options: ObserveTargetOption[] = [{ kind: 'overview', target: 'overview', label: '总览' }];
  const seen = new Set<string>([optionKey('overview', 'overview')]);
  for (const npcId of [...npcIds].sort()) {
    if (typeof npcId !== 'string' || npcId === '') continue;
    const key = optionKey('npc', npcId);
    if (seen.has(key)) continue;
    seen.add(key);
    options.push({ kind: 'npc', target: npcId, label: npcId });
  }
  for (const anomaly of worldview.anomalies ?? []) {
    const entity = anomaly?.at_entity;
    if (typeof entity !== 'string' || entity === '') continue;
    const key = optionKey('entity', entity);
    if (seen.has(key)) continue;
    seen.add(key);
    options.push({ kind: 'entity', target: entity, label: entity });
  }
  return options;
}

/** 选项的身份键：`(kind, target)` 二元组（**不是** target 单值）。 */
function optionKey(kind: ObserveTargetOption['kind'], target: string): string {
  return `${kind}\u0000${target}`;
}

/**
 * MUST-2（Raven R-3）的**显式披露**：同一个 `target` 出现在**多个 kind** 下的目标清单。
 * 非空 ⇒ 面板里会出现「同名但不同 kind」的两个选项，调用方/回读面据此可知情（**不静默**）。
 */
export function optionTargetCollisions(options: readonly ObserveTargetOption[]): string[] {
  const kindsByTarget = new Map<string, Set<string>>();
  for (const option of options) {
    const kinds = kindsByTarget.get(option.target) ?? new Set<string>();
    kinds.add(option.kind);
    kindsByTarget.set(option.target, kinds);
  }
  return [...kindsByTarget.entries()]
    .filter(([, kinds]) => kinds.size > 1)
    .map(([target]) => target)
    .sort();
}

/**
 * AC-10：启动恢复的**决策**（纯函数）。
 *
 * reason 取值**必须可区分**（M-9）：
 *   `ok`                             命中（目标在派生清单内）
 *   `fallback:empty-options-at-boot`  启动那一刻**该 kind 的候选面为空**（抢跑：NPC 事件还没到）
 *   `fallback:target-not-in-options`  候选面非空但目标已消失
 *   `none`                            没有持久化记录；`unavailable` 存储不可用
 * 折叠态与所选对象**分别**恢复：目标未命中只回落**选择**（折叠态由调用方照旧回读）。
 */
export function restoreDecisionOf(
  stored: PersistedObserveView | null,
  options: readonly ObserveTargetOption[],
  storageUsable: boolean,
): { reason: string; selection: ObserveSelection } {
  if (stored === null) {
    return { reason: storageUsable ? 'none' : 'unavailable', selection: { kind: 'overview', target: 'overview' } };
  }
  const sameKindOptions = options.filter((option) => option.kind === stored.kind);
  if (sameKindOptions.some((option) => option.target === stored.target)) {
    return { reason: 'ok', selection: { kind: stored.kind, target: stored.target } };
  }
  return {
    reason: sameKindOptions.length === 0 ? 'fallback:empty-options-at-boot' : 'fallback:target-not-in-options',
    selection: { kind: 'overview', target: 'overview' },
  };
}

/**
 * 读回持久化视图。
 *
 * 两种失败**必须分开**（不混淆）：**存储不可用**（取不到 / 抛错）⇒ `persisted:false`；
 * **内容损坏**（非 JSON / 字段类型不符 / 超长）⇒ `persisted:true` + `view:null`（存储本身是好的）。
 * 两种情况都**不得抛**。
 */
export function readPersistedView(): { view: PersistedObserveView | null; persisted: boolean } {
  let raw: string | null;
  try {
    if (typeof sessionStorage === 'undefined') return { view: null, persisted: false };
    raw = sessionStorage.getItem(OBSERVE_VIEW_KEY);
  } catch {
    return { view: null, persisted: false };
  }
  if (raw === null) return { view: null, persisted: true };
  try {
    const parsed = JSON.parse(raw) as Partial<PersistedObserveView> | null;
    const kind = parsed?.kind;
    if (typeof parsed?.collapsed !== 'boolean' || typeof parsed?.target !== 'string'
      || (kind !== 'overview' && kind !== 'npc' && kind !== 'entity')) {
      return { view: null, persisted: true };
    }
    return { view: { collapsed: parsed.collapsed, kind, target: parsed.target }, persisted: true };
  } catch {
    return { view: null, persisted: true };
  }
}

/** 写持久化视图：不可用 ⇒ `false`（**不得抛**）。 */
export function writePersistedView(view: PersistedObserveView): boolean {
  try {
    if (typeof sessionStorage === 'undefined') return false;
    sessionStorage.setItem(OBSERVE_VIEW_KEY, JSON.stringify(view));
    return true;
  } catch {
    return false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 对焦读数的**三态**取值（r2 MUST-1 / MUST-4）
//
// 为什么放在本文件：这几个函数决定 `camera_source` / `focus_reason` / `focus_sources` /
// `focus_reasons` 四个回读键的取值，必须能被 `node --test` **直接判**（`main.ts` 的局部
// import 用 `.js` 说明符，Node 解析不了）。`main.ts` 只做「取数 + 组装」，取值口径在这里。
//
// 硬口径（设计 §9.2 + r2 MUST-1）：**读不到 ≠ 读到了空**。三态必须可区分：
//   `rows === null`      ⇒ 读不到（抛错 / 非数组 / 无该方法）
//   `rows.length === 0`  ⇒ 读到了，确实是空
//   `rows.length > 0`    ⇒ 读到了 N 条
// ─────────────────────────────────────────────────────────────────────────────

/** 对焦读数行（`world.ts` 的 `FocusRecord` 投影）。 */
export interface FocusRow {
  entity_id: string;
  applied: boolean;
  source: 'aabb' | 'none';
  reason?: string;
}

/**
 * 读对焦读数。**读不到 ⇒ `null`**（与「读到了空数组」必须可区分）：
 * 缺方法 / 抛错 / 返回非数组 三种情况一律 `null` —— 调用方**不得**把 `null` 折成 `[]`。
 */
export function readFocusRows(reader: unknown): FocusRow[] | null {
  try {
    const report = (reader as { focusViewReport?: unknown } | null | undefined)?.focusViewReport;
    if (typeof report !== 'function') return null;
    const rows = (report as () => unknown).call(reader);
    return Array.isArray(rows) ? (rows as FocusRow[]) : null;
  } catch {
    return null;
  }
}

/** 读到的 `source` 取值集合；**读不到 ⇒ `null`**（不是 `[]`）。 */
export function focusSourcesOf(rows: readonly FocusRow[] | null): string[] | null {
  if (rows === null) return null;
  return [...new Set(rows.map((row) => String(row?.source)))];
}

/** 读到的 `reason` 取值集合；**读不到 ⇒ `null`**（不是 `[]`）。 */
export function focusReasonsOf(rows: readonly FocusRow[] | null): string[] | null {
  if (rows === null) return null;
  return [...new Set(rows
    .map((row) => row?.reason)
    .filter((reason): reason is string => typeof reason === 'string'))];
}

/**
 * `camera_source` ∈ `'none' | 'aabb' | 'unknown'`（设计 §9.2 硬口径）。
 *
 * - `rows === null`（**读不到**）⇒ **`'unknown'`** —— 不得与「确实没有相机源」混为一谈；
 * - 读到了且全为 `none` ⇒ `'none'`；全为 `aabb` ⇒ `'aabb'`；混合 / 出现未知取值 ⇒ `'unknown'`。
 *
 * 到达条件（三种，全部可达且可复现）：
 *   ① `'none'`    = 读到了记录，且唯一取值是 `none`（今日本环境常态：无在册真 GLB 候选）；
 *   ② `'aabb'`    = 读到了记录，且唯一取值是 `aabb`（有在册真 GLB 候选且真的施加了对焦）；
 *   ③ `'unknown'` = `focusViewReport()` 抛错 / 返回非数组 / 不存在，**或**读到了非 `aabb|none` 的取值。
 */
export function cameraSourceOf(rows: readonly FocusRow[] | null): 'none' | 'aabb' | 'unknown' {
  if (rows === null) return 'unknown';
  // 这里**不**写 `focusSourcesOf(rows) ?? []`：`??` 兜底在本函数里是多余且危险的写法
  // （它会把「上游忘了先处理 null」重新伪装成"确实是 none"）⇒ 直接就地求值，读不到的分支已在上面返回。
  const sources = [...new Set(rows.map((row) => String(row?.source)))];
  if (sources.length === 0) return 'none';
  if (sources.length === 1 && sources[0] === 'aabb') return 'aabb';
  if (sources.length === 1 && sources[0] === 'none') return 'none';
  return 'unknown';
}

/**
 * 对焦情形的一句话原因（设计 §9.2「按选择不施加」与「本来就没候选」必须用**两个不同的值**区分）。
 *   `unreadable`                       读不到读数（与「无候选」不同）
 *   `no-registered-real-glb-candidate` 读到了且为空 ⇒ 本来就没有在册真 GLB 候选
 *   `selection-suppressed-autofocus`   读到了且非空，但自动对焦被**按选择关掉**
 *   `autofocus-evaluated`              读到了且非空、自动对焦开着（正常求值路径）
 */
export function focusReasonOf(rows: readonly FocusRow[] | null, autofocusEnabled: boolean): string {
  if (rows === null) return 'unreadable';
  if (rows.length === 0) return 'no-registered-real-glb-candidate';
  if (!autofocusEnabled) return 'selection-suppressed-autofocus';
  return 'autofocus-evaluated';
}
