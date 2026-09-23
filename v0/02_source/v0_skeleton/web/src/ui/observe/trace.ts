/**
 * 因果追溯（M5.2 r2 · REQ §4 AC-5 / §1「可从事件记录追溯原因」+ AC-3.4 的**呈现侧**）。
 *
 * 目标：给定「徐琴为什么作出某个选择」，界面上能一路看到
 *   **事件 → 记忆 → 决策 → 可观察行动** —— 四个节点**全部**取自会话通道下发的
 *   `event` 消息（内核真实事件日志原样转发），本模块**不推断、不补造**任何节点。
 *
 * 节点来源（逐条可核）：
 *   ① 事件：同一 tick 的 `npc.action`（内核 [5] 记账段的顺序钉死：先 `npc.decision` /
 *      `npc.action`，再 `memory.written` ⇒ 该记忆记录由该 tick 的该动作产生）；
 *   ② 记忆：`memory.written` 事件（`layer=episodic`），ref 取自其 payload；
 *   ③ 决策：`npc.decision` 的 `memory_influence.signals`（形如 `episode:<kind>@ref=<R>`）
 *      —— **信号里的 ref 与记忆节点的 ref 逐字相等**才算连上；
 *   ④ 行动：该决策 tick 的 `npc.action.target_entity`（**可观察行动**，不是认知日志里的结论）。
 *
 * 诚实披露（M-15 / 呈现层不得自报）：当某个 signal 引用的 ref 在事件流里**没有**对应的
 * `memory.written` 事件时，本模块把它记进 `unlinked_signal_refs` 并在界面上标注
 * 「该 ref 无对应 memory.written 事件」——**不**伪造一条记忆事件来把链画满。
 *
 * 只读：本模块只写文本节点与 `dataset`，**不新增任何输入控件**（`writeControls()` 仍为空）。
 */

export interface CausalEventNode {
  seq: number | null;
  tick: number;
  type: string;
  action?: string;
  target_entity?: string | null;
}

export interface CausalMemoryNode {
  seq: number | null;
  tick: number;
  ref: string;
  kind: string | null;
  layer: string | null;
  importance: number | null;
}

export interface CausalDecisionNode {
  seq: number | null;
  tick: number;
  chosen_action: string | null;
  signals: string[];
  utility_delta: number | null;
  by_action: Record<string, number>;
}

export interface CausalActionNode {
  seq: number | null;
  tick: number;
  action: string | null;
  target_entity: string | null;
}

export interface CausalChain {
  npc_id: string;
  event: CausalEventNode | null;
  memory: CausalMemoryNode | null;
  decision: CausalDecisionNode | null;
  action: CausalActionNode | null;
  /** 决策信号里出现、但事件流中没有对应 `memory.written` 的 ref（透明披露，不补造） */
  unlinked_signal_refs: string[];
  /** 四节点齐全且「记忆 ref ↔ 信号 ref」逐字相等 */
  complete: boolean;
}

interface RawEvent {
  seq?: number;
  tick?: number;
  type?: string;
  actor?: string;
  payload?: Record<string, unknown>;
}

const MAX_EVENTS = 20000;
const SIGNAL_REF_RE = /@ref=([^@\s]+)/;
/**
 * **人物作用域**的事件类型（只对这些人建索引）：`actor` 是 NPC 的事件。
 * 其余事件（`world.init` / `snapshot.taken` / `intent.*`）的 `actor` 是 `world` 或会话，
 * 把它们也当人物会导致「向内容包请求 `npcs/world.json` ⇒ 404」（实测）。
 */
const NPC_SCOPED_EVENT_TYPES = new Set(['npc.action', 'npc.decision', 'memory.written', 'relation.changed']);

function numberOf(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** 从 `episode:<kind>@ref=<R>` 取出 ref 与 kind。 */
export function parseSignal(signal: string): { kind: string | null; ref: string | null } {
  const match = SIGNAL_REF_RE.exec(signal);
  const ref = match ? match[1] : null;
  const head = signal.split('@')[0] ?? '';
  const kind = head.startsWith('episode:') ? head.slice('episode:'.length) : (head || null);
  return { kind, ref };
}

export class CausalTrace {
  readonly root: HTMLElement;
  private readonly el: HTMLElement;
  private readonly events: RawEvent[] = [];
  private readonly seenSeqs = new Set<number>();
  private readonly byNpc = new Map<string, {
    memories: RawEvent[]; decisions: RawEvent[]; actions: RawEvent[];
  }>();

  constructor(host: HTMLElement) {
    this.root = host;
    const existing = host.querySelector('#causal-trace');
    if (existing) {
      this.el = existing as HTMLElement;
    } else {
      const created = document.createElement('div');
      created.id = 'causal-trace';
      host.append(created);
      this.el = created;
    }
  }

  /** 摄入一条事件（会话通道下发的 `event` 消息内层对象）。 */
  ingest(event: Record<string, unknown>): void {
    const typed = event as RawEvent;
    const seq = numberOf(typed.seq);
    if (seq !== null) {
      // 会话层可能把同一条内核事件经多个连接重复下发（实测：一次页面加载两条会话）
      // ⇒ 按**内核事件自身的 seq**（全局单调唯一）去重，避免重复计数。
      if (this.seenSeqs.has(seq)) return;
      this.seenSeqs.add(seq);
    }
    if (this.events.length < MAX_EVENTS) this.events.push(typed);
    const actor = typeof typed.actor === 'string' ? typed.actor : '';
    if (!actor || !NPC_SCOPED_EVENT_TYPES.has(String(typed.type))) return;
    let bucket = this.byNpc.get(actor);
    if (!bucket) {
      bucket = { memories: [], decisions: [], actions: [] };
      this.byNpc.set(actor, bucket);
    }
    if (typed.type === 'memory.written') bucket.memories.push(typed);
    if (typed.type === 'npc.decision') bucket.decisions.push(typed);
    if (typed.type === 'npc.action') bucket.actions.push(typed);
  }

  /** 见过的 NPC（按 id 升序）。 */
  npcIds(): string[] {
    return [...this.byNpc.keys()].sort();
  }

  eventCount(): number {
    return this.events.length;
  }

  /** 客户端**收到**的原始事件（供验收驱动回读；不加工）。 */
  receivedEvents(): RawEvent[] {
    return this.events.map((event) => ({ ...event }));
  }

  /**
   * 某个 NPC 的因果链（**只从收到的事件里抽**）。
   *
   * 选链规则（显式、可复算）：取该 NPC **最后一条** `memory_influence.signals` 非空的
   * `npc.decision` 作为焦点；若一条都没有 ⇒ 取最后一条 `npc.decision`（此时记忆节点为 null，
   * 链不完整 —— 如实呈现，不补造）。
   */
  chainFor(npcId: string): CausalChain {
    const bucket = this.byNpc.get(npcId);
    const chain: CausalChain = {
      npc_id: npcId, event: null, memory: null, decision: null, action: null,
      unlinked_signal_refs: [], complete: false,
    };
    if (!bucket || bucket.decisions.length === 0) return chain;
    const withSignals = bucket.decisions.filter((event) => this.signalsOf(event).length > 0);
    const decisionEvent = (withSignals.length > 0 ? withSignals[withSignals.length - 1]
      : bucket.decisions[bucket.decisions.length - 1]);
    const payload = (decisionEvent.payload ?? {}) as Record<string, unknown>;
    const influence = (payload.memory_influence ?? {}) as Record<string, unknown>;
    const signals = this.signalsOf(decisionEvent);
    const decisionTick = numberOf(decisionEvent.tick) ?? 0;
    chain.decision = {
      seq: numberOf(decisionEvent.seq), tick: decisionTick,
      chosen_action: typeof payload.chosen_action === 'string' ? payload.chosen_action : null,
      signals,
      utility_delta: numberOf(influence.utility_delta),
      by_action: (influence.by_action ?? {}) as Record<string, number>,
    };

    // ② 记忆节点：信号 ref 与 `memory.written` 的 ref **逐字相等**才算连上。
    //    只认 `layer=episodic`：`memory_influence.signals` 来自 `fetch_episodes()`；`working` 层的 ref
    //    与 episodes **各自独立编号**（实测同一 tick 两条都是 16）⇒ 不按层过滤会张冠李戴。
    for (const signal of signals) {
      const { ref } = parseSignal(signal);
      if (!ref) continue;
      const memoryEvent = [...bucket.memories].reverse().find((event) => {
        const memoryPayload = (event.payload ?? {}) as Record<string, unknown>;
        return String(memoryPayload.ref ?? '') === ref && String(memoryPayload.layer ?? '') === 'episodic';
      });
      if (memoryEvent) {
        const memoryPayload = (memoryEvent.payload ?? {}) as Record<string, unknown>;
        chain.memory = {
          seq: numberOf(memoryEvent.seq), tick: numberOf(memoryEvent.tick) ?? 0, ref,
          kind: typeof memoryPayload.kind === 'string' ? memoryPayload.kind : null,
          layer: typeof memoryPayload.layer === 'string' ? memoryPayload.layer : null,
          importance: numberOf(memoryPayload.importance),
        };
        break;
      }
      chain.unlinked_signal_refs.push(ref);
    }

    // ① 事件节点：记忆节点所在 tick 的 `npc.action`（内核 [5] 段顺序钉死：动作在前、记忆在后）
    if (chain.memory) {
      const source = [...bucket.actions].reverse().find((event) => numberOf(event.tick) === chain.memory?.tick);
      if (source) {
        const sourcePayload = (source.payload ?? {}) as Record<string, unknown>;
        chain.event = {
          seq: numberOf(source.seq), tick: numberOf(source.tick) ?? 0, type: 'npc.action',
          action: typeof sourcePayload.action === 'string' ? sourcePayload.action : undefined,
          target_entity: (sourcePayload.target_entity as string | null | undefined) ?? null,
        };
      }
    }

    // ④ 行动节点：该决策 tick 的 `npc.action`（可观察行动）；内核只在**真的移动/改班表**时 emit，
    //    因此同 tick 没有时取**该决策之后第一条**（该决策的可观察后果），并把偏移如实报出。
    const sameTick = [...bucket.actions].reverse().find((event) => numberOf(event.tick) === decisionTick);
    const later = sameTick ?? [...bucket.actions].find((event) => (numberOf(event.tick) ?? 0) > decisionTick);
    if (later) {
      const actionPayload = (later.payload ?? {}) as Record<string, unknown>;
      chain.action = {
        seq: numberOf(later.seq), tick: numberOf(later.tick) ?? 0,
        action: typeof actionPayload.action === 'string' ? actionPayload.action : null,
        target_entity: (actionPayload.target_entity as string | null | undefined) ?? null,
      };
    }
    chain.complete = Boolean(chain.event && chain.memory && chain.decision && chain.action
      && chain.decision.signals.length > 0);
    return chain;
  }

  private signalsOf(event: RawEvent): string[] {
    const payload = (event.payload ?? {}) as Record<string, unknown>;
    const influence = (payload.memory_influence ?? {}) as Record<string, unknown>;
    const signals = influence.signals;
    return Array.isArray(signals) ? signals.filter((item): item is string => typeof item === 'string') : [];
  }

  /** 把链渲染进 HUD（只写文本节点；**不新增任何控件**）。 */
  render(npcId: string | null, label: string | null = null): CausalChain | null {
    if (npcId === null) {
      this.el.dataset.npcId = '';
      this.el.textContent = 'causal trace: no npc events yet';
      return null;
    }
    const chain = this.chainFor(npcId);
    const lines: string[] = [];
    const title = label ? `${label} (${npcId})` : npcId;
    lines.push(`causal trace · ${title} · ${chain.complete ? 'complete' : 'incomplete'}`);
    lines.push(`  1 事件  : ${chain.event
      ? `seq ${chain.event.seq} t${chain.event.tick} npc.action(${chain.event.action} → ${chain.event.target_entity})`
      : '（无：事件流里没有与该记忆同 tick 的 npc.action）'}`);
    lines.push(`  2 记忆  : ${chain.memory
      ? `seq ${chain.memory.seq} t${chain.memory.tick} memory.written layer=${chain.memory.layer} ref=${chain.memory.ref} kind=${chain.memory.kind} importance=${chain.memory.importance}`
      : '（无：信号引用的 ref 在事件流里没有对应的 memory.written 事件）'}`);
    lines.push(`  3 决策  : ${chain.decision
      ? `seq ${chain.decision.seq} t${chain.decision.tick} chosen=${chain.decision.chosen_action} utility_delta=${chain.decision.utility_delta} signals=[${chain.decision.signals.join(', ')}]`
      : '（无）'}`);
    lines.push(`  4 行动  : ${chain.action
      ? `seq ${chain.action.seq} t${chain.action.tick} npc.action(${chain.action.action} → ${chain.action.target_entity})`
      : '（无：该决策 tick 没有 npc.action）'}`);
    if (chain.unlinked_signal_refs.length > 0) {
      lines.push(`  注：signal ref(s) 无对应 memory.written 事件：${chain.unlinked_signal_refs.join(', ')}（不补造）`);
    }
    this.el.dataset.npcId = npcId;
    this.el.dataset.complete = String(chain.complete);
    this.el.dataset.memoryRef = chain.memory?.ref ?? '';
    this.el.dataset.actionTarget = chain.action?.target_entity ?? '';
    this.el.textContent = lines.join('\n');
    return chain;
  }
}
