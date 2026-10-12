/**
 * L1 渲染层入口——M3 真实现。
 *
 * 职责：消费 snapshot/delta/event，渲染 3D 场景与双模式 UI；把 pack 的 `worldview` 交给场景
 * （**两态读法**：表层 / 深层 = 同一几何，只换光照与材质亮度）。
 * 边界（硬）：零业务规则、零模型调用、零世界状态写；不直读事件日志文件。
 *
 * 世界观来源（R2 / F13 修正）：**不再静态 import pack#1 的 worldview.json**，也不再有第二份
 * 数值副本（`FALLBACK_WORLDVIEW` 已删除）。URL 由**会话的 `district_pack_id`** 决定：
 * `/packs/<district_pack_id>/worldview.json`（由宿主静态服务从 `districts/<pack>/worldview.json` 提供）
 * ⇒ 同一组 tone 数值在全树**只有一处定义点**（pack 数据文件）。
 *
 * REQ-20261012-001 追加（T1 折叠 / T2 观察对象可切换）：
 *   - 观察对象清单**运行时派生**（`overview` + `trace.npcIds()` 升序 + `worldview.anomalies[].at_entity`
 *     去重保序）—— 源码逻辑分支里**不得**出现任何具体 pack / NPC / 实体 id；
 *   - 选中 `entity` ⇒ 异常读只渲该实体一条、因果链切「该实体无 NPC 链」空态、事件流按实体过滤、
 *     **`setAutoObservationFocus(false)`**（房间 / 物件无 GLB ⇒ 如实不施加对焦，**不伪造**"已对焦"）；
 *   - `sessionStorage['deephealing.observe.view']` 持久化折叠态与所选对象，读写都在 `try/catch` 内，
 *     恢复时校验目标仍在派生清单内，未命中 ⇒ 回落 `overview` 并给出**可区分**的 reason。
 */

import { createScene, type SceneHandle } from './scene/world.js';
import { RenderClient, type ServerMessage } from './net/client.js';
import { LiveChannel } from './net/live.js';
import {
  ObservePanel,
  cameraSourceOf,
  focusReasonOf,
  focusReasonsOf,
  focusSourcesOf,
  observeOptionsFor,
  optionTargetCollisions,
  readFocusRows,
  readPersistedView,
  restoreDecisionOf,
  writePersistedView,
  type ObserveSelection,
  type ObserveTargetOption,
} from './ui/observe/panel.js';
import { CausalTrace, type CausalChain } from './ui/observe/trace.js';
import { InterventionPanel } from './ui/participate/intervention.js';
import { createPlayerUi, uiSetIntersection } from './ui/player/player_ui.ts';
import { mountCredits, creditsReport } from './ui/player/credits';
import type { Reading, Tone } from './scene/lighting.js';

export interface WorldviewDocument {
  schema_version: string;
  pack_id: string;
  tone: Tone;
  anomalies: Array<{ id: string; at_entity: string; kind: string; surface_read: string; underneath_read: string; reveal_at_tick: number }>;
  fault_lines: Array<{ id: string; about: string; kind: string; repair_via: string; repaired_state: string }>;
}

/** 世界观 URL：由会话 `district_pack_id` 决定（**唯一**取值路径）。 */
export function worldviewUrlFor(districtPackId: string): string {
  return `/packs/${districtPackId}/worldview.json`;
}

/**
 * NPC 档案 URL（M5.2 r2）：显示名等**人物级声明**只存在于内容包（`npcs/<id>.json`），
 * 渲染层**不写死**任何名字。取不到 ⇒ 退回 id（**不**伪造名字）。
 */
export function npcProfileUrlFor(districtPackId: string, npcId: string): string {
  return `/packs/${districtPackId}/npcs/${npcId}.json`;
}

/** 读 NPC 显示名（只读 GET；失败返回 null，不抛、不编造）。 */
export async function loadNpcDisplayName(districtPackId: string, npcId: string): Promise<string | null> {
  try {
    const response = await fetch(npcProfileUrlFor(districtPackId, npcId));
    if (!response.ok) return null;
    const document = (await response.json()) as { display_name?: unknown; person_id?: unknown };
    return typeof document.display_name === 'string' ? document.display_name : null;
  } catch {
    return null;
  }
}

export async function loadWorldview(url: string): Promise<WorldviewDocument> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`E_PACK_INVALID: cannot load worldview (${response.status}) ${url}`);
  const document = (await response.json()) as WorldviewDocument;
  if (!document.tone?.surface || !document.tone?.underneath) {
    throw new Error('E_PACK_INVALID: worldview.tone.surface/underneath are required');
  }
  return document;
}

/**
 * T1/T2 的**纯视图模型**（对象清单派生 / 恢复决策 / 持久化读写）见
 * `./ui/observe/panel.ts` —— 放在那里是为了让 `node --test` 能直接判它
 * （`main.ts` 的局部 import 用 `.js` 说明符，Node 解析不了；`panel.ts` 零 import）。
 * 本文件的职责不变：**装配 + 选择语义 + 回读面**。
 */

export interface AppHandle {
  scene: SceneHandle;
  client: RenderClient;
  observe: ObservePanel;
  intervene: InterventionPanel;
  worldview: WorldviewDocument;
  live: LiveChannel;
  /** M5.2 r2 · 因果追溯（事件 → 记忆 → 决策 → 可观察行动） */
  trace: CausalTrace;
  setReading(reading: Reading): void;
  setMode(mode: 'observe' | 'participate'): void;
}

export async function bootstrap(options: { worldviewUrl?: string; autoConnect?: boolean; districtPackId?: string; liveUrl?: string } = {}): Promise<AppHandle> {
  const canvas = document.getElementById('scene') as HTMLCanvasElement | null;
  if (!canvas) throw new Error('missing #scene canvas');
  const hud = document.getElementById('hud') as HTMLElement;

  const client = new RenderClient();
  // **先建会话**（会话层是 `district_pack_id` 的权威）⇒ 世界观 URL 由它决定，渲染层不写死 pack。
  if (options.autoConnect !== false) {
    try {
      await client.connect({ url: '/ws', mode: 'observe', districtPackId: options.districtPackId });
    } catch {
      // 无会话层时仍尝试用显式传入的 pack id（离线开发）；**不**伪造任何世界状态或基调数值
    }
  }
  const packId = options.districtPackId ?? client.districtPackId;
  const worldview = await loadWorldview(options.worldviewUrl ?? worldviewUrlFor(packId));
  const tone: Tone = worldview.tone;

  const scene = createScene(canvas, { worldview: tone });

  // ── T2 选择态（先声明，供 `ObservePanel` 的 click 回调闭包引用） ──────────────
  let selection: ObserveSelection = { kind: 'overview', target: 'overview' };
  let persisted = true;
  let restoreReason = 'none';
  /** `world.ts` **没有 getter** ⇒ 用 `setAutoObservationFocus()` 的**回显值**记录；
   *  **不得**由 `focusViewReport()` 的长度反推（设计 §9.2 硬要求）。 */
  let autofocusEnabled = false;

  const observe = new ObservePanel(hud, { onSelect: (next) => applySelection(next) });
  // **M5.2 r2**：因果追溯面板（只读文本；事件全部来自会话通道下发的 `event` 消息）
  const trace = new CausalTrace(hud);
  // **N5 / A4（AC-H-2）**：玩家界面根与开发观察面板**分离** —— `#player-ui` 在 `#hud` **之外**；
  // 取不到根则**抛**（`E_PLAYER_UI_ROOT_MISSING`）。**已删除**旧的 `?? hud` 回退：
  // 回退会把「分离」重新变成「绿而未分离」，正是 PM C6 / Sentinel R-3 要堵的口子。
  const playerUi = createPlayerUi(document);
  const intervene = new InterventionPanel(playerUi.interventionHost, client);
  // **N5-C / AC-G G-1**：把 CC BY 4.0 署名挂进**玩家界面根**（`#player-ui`）⇒ 随页可见 + 随构建产物携带。
  // 只**新增**一个节点；不改 `#hud` / `#intervention-host` 的任何既有结构。
  const credits = mountCredits(document);
  // **M4 / W12**：观察窗接**实时通道**（只读 SSE）——页面显示的是**当前**时刻，不是回放。
  const live = new LiveChannel(options.liveUrl ?? '/live/stream');
  const npcNames = new Map<string, string>();

  client.onMessage((message: ServerMessage) => {
    scene.apply(message as { t: string; tick: number; state?: never; ops?: never });
    observe.apply(message);
    if (message.t === 'event') {
      const event = message.event as Record<string, unknown>;
      // 因果追溯：**逐条**摄入内核事件（不加工、不补造）
      trace.ingest(event);
      if (event?.type === 'task.state_changed') intervene.renderTaskEvolution([event.payload as Record<string, unknown>]);
      // 事件到位后 NPC 清单可能增长 ⇒ 刷新观察对象清单（签名不变则不重建）
      refreshTargets();
    }
  });

  /** 追溯焦点：有信号链的 NPC 优先，其次最近的 NPC；显示名来自内容包（取不到则用 id）。 */
  const focusNpc = (): string | null => {
    const ids = trace.npcIds();
    if (ids.length === 0) return null;
    const withChain = ids.filter((id) => trace.chainFor(id).complete);
    return withChain.length > 0 ? withChain[withChain.length - 1] : ids[ids.length - 1];
  };
  const pendingNames = new Set<string>();
  const renderNpcTrace = (npcId: string) => {
    if (npcNames.has(npcId)) {
      trace.render(npcId, npcNames.get(npcId) ?? null);
      return;
    }
    trace.render(npcId, null);
    if (pendingNames.has(npcId)) return;
    pendingNames.add(npcId);
    void loadNpcDisplayName(packId, npcId).then((name) => {
      npcNames.set(npcId, name);
      renderTraceForSelection();
    });
  };
  const renderTrace = () => {
    const npcId = focusNpc();
    if (npcId === null) {
      trace.render(null);
      return;
    }
    renderNpcTrace(npcId);
  };
  /** T2：因果链按所选对象分支（`overview` = 既有自动焦点；`npc` = 指定 NPC；`entity` = 实体空态）。 */
  const renderTraceForSelection = () => {
    if (selection.kind === 'npc') { renderNpcTrace(selection.target); return; }
    if (selection.kind === 'entity') { trace.renderEntityScope(selection.target); return; }
    renderTrace();
  };

  /** T2：观察对象清单（**运行时派生**，唯一取值路径）。 */
  const derivedOptions = (): ObserveTargetOption[] => observeOptionsFor(worldview, trace.npcIds());
  const refreshTargets = (): ObserveTargetOption[] => {
    const current = derivedOptions();
    observe.renderTargets(current, selection);
    return current;
  };

  /** T2：异常读渲染（按选择决定是否按实体过滤；`setReading` 与轮询共用同一路径）。 */
  const renderAnomalyReadsForSelection = (reading: Reading) => {
    const filter = selection.kind === 'entity' ? { entity: selection.target } : undefined;
    observe.renderAnomalyReads(worldview, observeTick(observe), reading, filter);
  };

  /** 自动对焦开关（记录 `world.ts` 的回显值）。 */
  const applyAutofocus = (enabled: boolean) => {
    autofocusEnabled = scene.setAutoObservationFocus(enabled).enabled;
  };

  /**
   * T2：应用一个选择（面板点击 / 启动恢复 / 回落都走这一条路径）。
   *
   * 语义表（设计 §4.4）：
   *   overview → `focusNpc()` 自动焦点、全部异常读、事件流不过滤、`setAutoObservationFocus(true)`；
   *   npc      → `trace.render(npcId, name)`、全部异常读、事件流不过滤、`setAutoObservationFocus(true)`；
   *   entity   → 异常读只渲该实体、`renderEntityScope()` 空态、事件流按实体过滤、
   *              **`setAutoObservationFocus(false)`**（无 GLB ⇒ 如实不施加，不伪造"已对焦"）。
   */
  const applySelection = (next: ObserveSelection, opts: { persist?: boolean } = {}): void => {
    selection = { kind: next.kind, target: next.target };
    observe.setSelection(selection);
    if (selection.kind === 'entity') {
      observe.setEventFilter({ entity: selection.target });
      applyAutofocus(false);
    } else {
      observe.setEventFilter(null);
      applyAutofocus(true);
    }
    renderAnomalyReadsForSelection(scene.reading());
    renderTraceForSelection();
    refreshTargets();
    if (opts.persist !== false) persistView();
  };

  /** 持久化当前视图（折叠态 + 所选对象）；写失败 ⇒ `persisted:false`（不抛）。 */
  const persistView = (): void => {
    persisted = writePersistedView({ collapsed: observe.isCollapsed(), kind: selection.kind, target: selection.target }) && persisted;
  };

  const modeBadge = document.getElementById('mode-badge');
  const readingBadge = document.getElementById('reading-badge');
  const setReading = (reading: Reading) => {
    scene.setReading(reading);
    renderAnomalyReadsForSelection(reading);
    if (readingBadge) readingBadge.textContent = reading;
  };
  const setMode = (mode: 'observe' | 'participate') => {
    client.mode = mode;
    if (modeBadge) modeBadge.textContent = mode;
    if (mode === 'participate') intervene.mount();
  };

  document.getElementById('toggle-reading')?.addEventListener('click', () => {
    setReading(scene.reading() === 'surface' ? 'underneath' : 'surface');
  });
  document.getElementById('toggle-mode')?.addEventListener('click', () => {
    setMode(client.mode === 'observe' ? 'participate' : 'observe');
  });
  // T1：折叠 / 展开（`ObservePanel` 内部已绑同一按钮的切换；此处只负责**持久化**）
  document.getElementById('observe-collapse-toggle')?.addEventListener('click', () => persistView());

  // ── 启动恢复（M-9：两个 fallback reason 必须**可区分**） ──────────────────────
  const restored = readPersistedView();
  persisted = restored.persisted;
  const stored = restored.view;
  const bootOptions = derivedOptions();
  const decision = restoreDecisionOf(stored, bootOptions, restored.persisted);
  restoreReason = decision.reason;
  // 折叠态与所选对象**分别**恢复：目标未命中只回落**选择**，折叠态照旧回读。
  if (stored !== null) observe.setCollapsed(stored.collapsed);
  applySelection(decision.selection, { persist: false });

  // 暴露给真浏览器验收脚本（Playwright）读取，不构成写路径
  (globalThis as unknown as { __deephealing?: unknown }).__deephealing = {
    scene, client, observe, intervene, worldview, live, trace, setReading, setMode,
    geometry: () => scene.geometry(),
    entityIds: () => scene.entityIds(),
    writeControls: () => observe.listWriteControls(),
    reading: () => scene.reading(),
    mode: () => client.mode,
    // R3 / G2：判据必须能经**应用装配路径**取数（含 mesh 层读回）
    geometryFor: (reading: Reading) => scene.geometryFor(reading),
    assemblyReport: () => scene.assemblyReport(),
    // R3 / G1：画布尺寸 / 绘制缓冲读数
    viewport: () => scene.viewport(),
    // **M4 / AC-M4-10③ + AC-M4-11③**：通道读数（当前 tick / 世界钟 / 墙上钟 / observers）
    liveReadout: () => observe.liveReadout(),
    liveProjection: () => live.stateProjection(),
    // **M5.2 r2 / AC-5 + W11**：因果追溯（事件 → 记忆 → 决策 → 可观察行动）
    traceNpcs: () => trace.npcIds(),
    traceFor: (npcId: string): CausalChain => trace.chainFor(npcId),
    receivedEvents: () => trace.receivedEvents(),
    /**
     * **REQ-20261012-001 · T1/T2 回读面**（只读；既有键与语义一律不变）。
     *
     * ⚠️ 两条硬口径：
     *   - `camera_source` **禁止 `?? 'none'` 兜底**：「读不到」= `'unknown'`，
     *     与「确实是 none」必须可区分；
     *   - `autofocus_enabled` 取自 `setAutoObservationFocus()` 的**回显值**，
     *     **不得**由 `focus_report_length` 反推。
     *
     * `focus_report_length === focus_candidate_count` 的**依据**（读 `world.ts:1574-1590` 可得）：
     * `focusViewReport()` 的每条记录**恰对应一个对焦候选** —— 关闭态是
     * `candidates.map(none,'disabled')`、多候选态 `ambiguous_target` 每候选一条、单候选态一条
     * ⇒ 记录数 = 在册真 GLB 候选数。故**关闭态**下 `length === 0` 确实推出「无在册真 GLB 候选」，
     * 不是空真；`focus_reason` 再把「本来没候选」与「按选择不施加」显式分开。
     *
     * **r2 MUST-1 修复（Raven R-1）**：`rows === null`（**读不到**）不再折叠成 `[]`：
     * `camera_source` 取 `'unknown'`，`focus_sources` / `focus_reasons` 取 `null` ——
     * 「读不到」与「读到了空」在任何回读键上都可区分（三态口径见 `panel.ts` 的取值函数）。
     */
    observeViewState: () => {
      const rows = readFocusRows(scene);
      const width = measureHudWidth(hud);
      const heights = measureHudHeights(hud, observe);
      const anomalyEntities = [...new Set((worldview.anomalies ?? [])
        .map((anomaly) => anomaly.at_entity)
        .filter((entity): entity is string => typeof entity === 'string' && entity !== ''))];
      const current = derivedOptions();
      return {
        collapsed: observe.isCollapsed(),
        selected: { kind: selection.kind, target: selection.target },
        options: current.map((option) => ({ ...option })),
        /** MUST-2：跨 kind 同 target 的**显式披露**（空 = 无撞名；非空 = 面板里出现同名不同 kind 的选项）。 */
        option_target_collisions: optionTargetCollisions(current),
        hud: {
          collapsed_height: heights.collapsed,
          expanded_height: heights.expanded,
          client_width: width.clientWidth,
          scroll_width: width.scrollWidth,
          root_font_size_px: rootFontSizePx(),
          object_count: current.length,
          viewport_width: viewportWidth(),
        },
        autofocus_enabled: autofocusEnabled,
        camera_source: cameraSourceOf(rows),
        focus_report_length: rows === null ? null : rows.length,
        focus_sources: focusSourcesOf(rows),
        focus_candidate_count: rows === null ? null : rows.length,
        focus_reasons: focusReasonsOf(rows),
        focus_reason: focusReasonOf(rows, autofocusEnabled),
        write_controls: observe.listWriteControls(),
        anomaly_read_entities: selection.kind === 'entity'
          ? anomalyEntities.filter((entity) => entity === selection.target)
          : anomalyEntities,
        event_stream_filter: observe.eventStreamFilter(),
        session_connected: client.session !== null,
        session_socket_ready_state: socketReadyStateOf(client),
        persisted,
        restore: restoreReason,
        events_received: trace.receivedEvents().length,
        npc_ids: trace.npcIds(),
        /** SHOULD-5：两态高度必须真的切一次 class 才能量 ⇒ 本接口**有瞬时副作用**，如实自报。 */
        measurement_side_effect: heights.sideEffect,
        measurement_restored: heights.restored,
      };
    },
    // **M5.2 r2 / AC-5④**：reload 回读用的**关键字段快照**（全部来自页面当前读数）
    // **N5 / AC-H-2**：玩家界面集合 / 开发观察面板集合 / 交集（playwright 断言的取数面）
    uiSets: () => uiSetIntersection(document),
    playerUiRoot: () => playerUi.root.id,
    // **N5-C / AC-G G-1**：署名面的页内读数（真浏览器断言用；Node 侧不参与）
    creditsReport: () => creditsReport(document),
    creditsEntries: () => credits.entries.length,
    acSnapshot: () => {
      const projection = (live.stateProjection() ?? {}) as Record<string, unknown>;
      const entities = Array.isArray(projection.entities)
        ? (projection.entities as Array<Record<string, unknown>>) : [];
      const npcs = entities
        .filter((entity) => entity.kind === 'npc')
        .map((entity) => ({
          id: entity.id,
          display_name: npcNames.get(String(entity.id)) ?? null,
          transform: entity.transform ?? null,
          needs: entity.needs ?? null,
          emotion: entity.emotion ?? null,
          schedule: entity.schedule ?? null,
          relations: entity.relations ?? null,
          trauma_flags: entity.trauma_flags ?? null,
        }));
      const focus = focusNpc();
      return {
        pack_id: packId,
        tick: observeTick(observe),
        channel_tick: live.channelTick,
        seed: projection.seed ?? null,
        state_hash: live.readout().stateHash,
        event_chain_hash: live.readout().eventChainHash,
        world_clock: live.worldClock,
        event_count: trace.eventCount(),
        events_seen_in_panel: observe.eventsSeen,
        npcs,
        trace: focus === null ? null : trace.chainFor(focus),
        trace_npcs: trace.npcIds(),
      };
    },
  };

  setMode('observe');
  setReading('surface');
  // **N5 / B-1 + B-2**：真 WebGL 下**动态** import `GLTFLoader` 并注入场景
  // （动态 import 使 Node / 无 WebGL 路径完全不碰该模块；失败**不抛**，记 degradations，回落盒体）。
  if (typeof window !== 'undefined') {
    // **AC-2（FU-013）**：装载时开启**自动对焦**（opt-in 加法件，默认关）。
    // 它只按对焦实体 GLB 的世界 AABB 派生观测机位（只改相机 position/quaternion），
    // **不改** `DEFAULT_CAMERA_POSITION` / `DEFAULT_CAMERA_LOOK_AT`，也不改任何 `presentation.ts` 常量；
    // 实体出现后每次 snapshot 自动生效，进入交互相机后自动停止施加。
    // **REQ-20261012-001**：若恢复出的是 `entity` 选择 ⇒ 必须**关**（房间 / 物件无 GLB，如实不施加）。
    applyAutofocus(selection.kind !== 'entity');
    void import('three/examples/jsm/loaders/GLTFLoader.js')
      .then(({ GLTFLoader }) => { scene.setCharacterLoader(new GLTFLoader()); })
      .catch(() => { scene.setCharacterLoader(null); });
  }
  scene.startRenderLoop();

  // 实时通道连入（只读；连不上不伪造任何读数，面板显示 offline）
  live.connect();
  const liveTimer = setInterval(() => {
    observe.renderLiveReadout(live.readout());
    // 清单随事件增长 ⇒ 每拍刷一次（签名不变则不重建 ⇒ 不丢焦点）
    refreshTargets();
    renderAnomalyReadsForSelection(scene.reading());
    renderTraceForSelection();
  }, 250);
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', () => { clearInterval(liveTimer); live.close(); });
  }
  observe.renderLiveReadout(live.readout());
  refreshTargets();

  // **M5.2 r2 修正（AC-5 真浏览器实测）**：此处原有**第二次** `client.connect()` —— 一次页面加载
  // 会建**两个会话**（两次 `POST /sessions`），两个 WS 同时喂 `apply()`，而 `apply()` 的
  // 「(tick, seq) 单调」判据是**按会话**成立的 ⇒ 两条会话的 seq 交错，后到的消息被大面积丢弃
  // （实测：面板 tick 卡在 10，而通道 tick 已 30）。上面的第一次 connect 已建立会话与 pack 归属，
  // 这里**删除重复连接**（零功能损失：`mode`/`districtPackId` 均已由第一次连接设定）。
  return { scene, client, observe, intervene, worldview, live, trace, setReading, setMode };
}

function observeTick(panel: ObservePanel): number {
  const el = document.getElementById('tick');
  const match = el?.textContent?.match(/tick\s+(\d+)/);
  return match ? Number(match[1]) : 0;
}

/**
 * 启动参数（M5.2 r2）：`?pack=<district_pack_id>` 由**宿主页面**给出（只读查询参数），
 * 缺省保持既有默认包。⇒ 同一份构建可服务不同内容包，且**世界观 / NPC 档案**都从
 * 该 pack 的目录取（不再把非默认包的 NPC 名字请求打到默认包上 ⇒ 实测会 404）。
 */
function bootstrapOptionsFromLocation(): { districtPackId?: string } {
  if (typeof location === 'undefined') return {};
  const pack = new URLSearchParams(location.search).get('pack');
  return pack ? { districtPackId: pack } : {};
}

/**
 * 对焦读数的**取值口径**（`readFocusRows` / `cameraSourceOf` / `focusReasonOf` /
 * `focusSourcesOf` / `focusReasonsOf`）在 `./ui/observe/panel.ts` —— 与 r1 的视图模型同一理由：
 * 放在那里才能被 `node --test` 直接判（`main.ts` 的局部 import 用 `.js` 说明符，Node 解析不了）。
 * 本文件的职责不变：**取数（读 scene / 量 DOM）+ 组装回读面**。
 */

/** 折叠态呈现面的快照（只用于校验 `measureHudHeights()` 收尾是否复原）。 */
function collapsePresentationOf(hud: HTMLElement, button: HTMLElement | null): string {
  return JSON.stringify({
    className: hud.className,
    datasetCollapsed: hud.dataset.collapsed ?? null,
    buttonText: button ? button.textContent : null,
  });
}

/**
 * AC-1：同一页面实例、同一数据时刻、**连续**取两态高度（`getBoundingClientRect().height`）。
 *
 * **r2 SHOULD-5（Raven R-7）**：真实的另一种折叠态高度只能靠真的切一次 class 量出来
 * （`getComputedStyle` 不给"假设态"的盒高；离屏克隆需要整棵子树且不保证同布局）⇒ 副作用**无法消除**。
 * 因此改为：① 把副作用面**收到最小** —— 只切 `#hud` 的 CSS 钩子 class，**不再**改 `dataset` 与按钮文案；
 * ② 同步完成并**校验复原**，把 `measurement_side_effect: true` 与 `measurement_restored` 随读数一起报出。
 * 一次调用内「切换 + 量取 + 复原」全部同步执行 ⇒ 其它脚本观测不到中间态。
 */
function measureHudHeights(hud: HTMLElement, observe: ObservePanel): {
  collapsed: number; expanded: number; sideEffect: boolean; restored: boolean;
} {
  const button = hud.querySelector('#observe-collapse-toggle') as HTMLElement | null;
  const before = collapsePresentationOf(hud, button);
  const wasCollapsed = observe.isCollapsed();
  hud.classList.toggle('collapsed', false);
  const expanded = hud.getBoundingClientRect().height;
  hud.classList.toggle('collapsed', true);
  const collapsed = hud.getBoundingClientRect().height;
  hud.classList.toggle('collapsed', wasCollapsed);
  return {
    collapsed,
    expanded,
    sideEffect: true,
    restored: collapsePresentationOf(hud, button) === before,
  };
}

/** AC-9：当前态的 `clientWidth` / `scrollWidth`；读不到 ⇒ `null`（不伪装成 0）。 */
function measureHudWidth(hud: HTMLElement): { clientWidth: number | null; scrollWidth: number | null } {
  try {
    const clientWidth = hud.clientWidth;
    const scrollWidth = hud.scrollWidth;
    return {
      clientWidth: typeof clientWidth === 'number' ? clientWidth : null,
      scrollWidth: typeof scrollWidth === 'number' ? scrollWidth : null,
    };
  } catch {
    return { clientWidth: null, scrollWidth: null };
  }
}

/** root font-size（`rem → px` 折算的唯一依据）；读不到 ⇒ `null`。 */
function rootFontSizePx(): number | null {
  try {
    if (typeof window === 'undefined' || typeof window.getComputedStyle !== 'function') return null;
    const value = Number.parseFloat(window.getComputedStyle(document.documentElement).fontSize);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

function viewportWidth(): number | null {
  if (typeof window === 'undefined') return null;
  return typeof window.innerWidth === 'number' ? window.innerWidth : null;
}

/** 会话 socket 就绪态（`0..3`）；读不到 ⇒ `null`（不伪装成某个具体状态）。 */
function socketReadyStateOf(client: RenderClient): number | null {
  const socket = (client as unknown as { socket?: { readyState?: unknown } | null }).socket;
  return typeof socket?.readyState === 'number' ? socket.readyState : null;
}

void bootstrap(bootstrapOptionsFromLocation());
