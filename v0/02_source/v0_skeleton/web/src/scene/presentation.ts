/**
 * S-2 · **表现层**（N5 / B-3）—— 权威状态与表现状态**分开**（REQ §三 S-2）。
 *
 * 硬边界（用户 §三.2 原文）：
 *   - 客户端**不得**擅自改变任务、关系、记忆或世界事实；
 *   - **允许**维护插值、动画混合、注视、镜头与 UI 等**表现状态**；
 *   - **禁止**客户端靠穿墙修正、瞬移或视觉遮挡掩盖权威移动问题；
 *   - 导航与碰撞有**明确权威归属**：内核决定真实位置，客户端只做「把位置表现得顺」。
 *
 * 本模块的实现形态（可机器判据，`AC-F-2a/F-2b/F-2c`）：
 *   - 权威容器 = 模块私有的 `authority` 对象，**只**由 `applyAuthority()` 赋值；
 *     `step()` 与所有表现写入路径**只读**它 ⇒「表现层变第二权威」在结构上不可能；
 *   - `AUTHORITY_WRITE_LOG` 逐次记录赋值来源，判据可核「赋值点集合 == {apply}」。
 */

import { CHARACTER_SLOTS, type CharacterSlot } from './character_instance.ts';

/** 权威侧单实体读数（由内核快照下发；**只读**）。 */
export interface AuthorityEntity {
  entityId: string;
  /** 权威位置（米）。 */
  pos_m: [number, number, number];
  /** 权威状态 id（内容包 `appearance.states[].id`）。 */
  stateId: string | null;
  tick: number;
}

/** 权威容器：**只有** `applyAuthority()` 能写。 */
interface AuthorityState {
  entities: Map<string, AuthorityEntity>;
  tick: number;
  epoch: number;
}

/** 表现层产物（可被探针读走；**不回流**权威）。 */
export interface DisplayedEntity {
  entityId: string;
  displayed_position_m: [number, number, number];
  facing_yaw_rad: number;
  slot_weights: Record<CharacterSlot, number>;
  gaze_target: string | null;
  interpolated: boolean;
}

export type CameraMode = 'inspection' | 'interactive';

/** `H-2` 写死的 `inspection` 取景（= `scene_assert.mjs:335` 的冻结值，**逐字**）。 */
export const INSPECTION_POSITION: readonly [number, number, number] = [18, 14, 24];
export const INSPECTION_LOOK_AT: readonly [number, number, number] = [9, 0, 6];
/** 既有 `setObservationCamera` 的**取证机位**（另一个概念，默认不激活）。 */
export const OBSERVATION_POSITION: readonly [number, number, number] = [5, 0.35, 17.4];
export const OBSERVATION_LOOK_AT: readonly [number, number, number] = [5, -0.2, 15];

/** ε 下限（`AC-B-6b` 写死 5 mm，米制）。 */
export const EPS_FLOOR_M = 0.005;
/** 采样对齐的 tick 时长（内核 `tick.py:7` 实测 100 ms）。 */
export const TICK_MS = 100;

export interface AuthorityWriteEntry {
  source: string;
  tick: number;
  epoch: number;
  entities: number;
}

const AUTHORITY_WRITE_LOG: AuthorityWriteEntry[] = [];

const authority: AuthorityState = { entities: new Map(), tick: 0, epoch: 0 };

let writeEpoch = 0;

/**
 * **唯一**的权威写入点（命名与 `AC-F-2b` 的判据面**逐字**一致：`apply`）。
 *
 * 本函数是全模块**唯一**触碰 `authority.*` 的代码；其余表现路径（`step()` 等）只读它
 * ⇒「表现层变第二权威」在**结构上**不可能。`authority_scan.mjs` 的 AST 判据核这一点。
 */
export function apply(entities: readonly AuthorityEntity[], tick: number, source = 'apply'): void {
  writeEpoch += 1;
  authority.entities = new Map(entities.map((e) => [e.entityId, { ...e, pos_m: [...e.pos_m] as [number, number, number] }]));
  authority.tick = tick;
  authority.epoch = writeEpoch;
  AUTHORITY_WRITE_LOG.push({ source, tick, epoch: writeEpoch, entities: entities.length });
}

export function authorityWriteLog(): AuthorityWriteEntry[] {
  return AUTHORITY_WRITE_LOG.map((e) => ({ ...e }));
}

/** 权威写入的**来源集合**（去重；`report()` 与外部锚判据共用同一条取数路径）。 */
export function authorityWriteSources(): string[] {
  return [...new Set(AUTHORITY_WRITE_LOG.map((e) => e.source))];
}

export function authoritySnapshot(): { tick: number; epoch: number; entities: AuthorityEntity[] } {
  return {
    tick: authority.tick,
    epoch: authority.epoch,
    entities: [...authority.entities.values()].map((e) => ({ ...e, pos_m: [...e.pos_m] as [number, number, number] })),
  };
}

/** 权威的**单 tick 位移序列**（`AC-B-1b` / `AC-B-2a` / `AC-B-6b` 的锚；由权威位置算出）。 */
export interface AuthorityStep {
  entityId: string;
  tick: number;
  dpos_m: [number, number, number];
  dpos_norm_m: number;
  /** 权威位移方向（弧度，XY 平面；零位移 tick 记 `null`）。 */
  direction_rad: number | null;
}

const authoritySteps: AuthorityStep[] = [];

/** 转身槽的**保持时长**（tick 数）：0.3 s / 100 ms = 3 tick（`AC-B-3` 要求 ≥0.3 s）。 */
export const TURN_HOLD_TICKS = 3;
/** `AC-B-3` 的保持时长下限（秒）—— `N5-r2 / A4②` 的独立观测用它核对事件真满足下限。 */
export const TURN_HOLD_MIN_SECONDS = 0.3;
/** 转身槽被激活时的权重（`AC-B-3` 要求 ≥0.5）。 */
export const TURN_SLOT_WEIGHT = 0.6;
/** 触发转身槽的**权威位移方向**变化阈值（`AC-B-3`：≥90°）。 */
export const TURN_DIRECTION_DELTA_RAD = Math.PI / 2;
/**
 * 方向读数的**量化容差**：`direction_rad` 由 `toFixed(6)` 收敛 ⇒ 恰好 90° 的转向会读成
 * `1.570796 < π/2 = 1.5707963267948966`。不设容差会把**合规的直角转向**判成「没转」（假红）。
 */
export const TURN_DIRECTION_EPSILON = 1e-6;

/** 表现槽时间线事件（`AC-B-3` / `AC-B-7` / `AC-H-3` 的取数面）。 */
export interface ClipEvent {
  entityId: string;
  tick: number;
  slot: CharacterSlot;
  weight: number;
  /** 该事件的**保持时长**（tick 数 × 100 ms）。 */
  hold_ticks: number;
  /** 触发它的**权威位移方向**变化（弧度；仅 `turn` 事件有）。 */
  trigger_direction_delta_rad: number | null;
}

const clipTimeline: ClipEvent[] = [];
/** 每个实体当前的**权威位移方向**（用于检测 ≥90° 的方向变化）。 */
const lastDirection = new Map<string, number | null>();
/** 每个实体「转身槽保持到哪个 tick」。 */
const turnUntil = new Map<string, number>();

/** 由**内核侧**位置序列推进（生产者 = 权威快照，不是客户端读数）。 */
export function recordAuthorityStep(entityId: string, prev: [number, number, number] | null,
                                     next: [number, number, number], tick: number): void {
  if (!prev) return;
  const d: [number, number, number] = [next[0] - prev[0], next[1] - prev[1], next[2] - prev[2]];
  const norm = Math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
  authoritySteps.push({
    entityId,
    tick,
    dpos_m: d,
    dpos_norm_m: Number(norm.toFixed(6)),
    direction_rad: norm > EPS_FLOOR_M ? Number(Math.atan2(d[2], d[0]).toFixed(6)) : null,
  });
}

export function authorityStepsSnapshot(): AuthorityStep[] {
  return authoritySteps.map((s) => ({ ...s, dpos_m: [...s.dpos_m] as [number, number, number] }));
}

export function resetPresentation(): void {
  // 复位**也**走 `apply`（唯一写点）⇒ AST 判据的赋值点集合仍 == {apply}。
  apply([], 0, 'reset');
  AUTHORITY_WRITE_LOG.length = 0;
  authoritySteps.length = 0;
  clipTimeline.length = 0;
  lastDirection.clear();
  turnUntil.clear();
}

/**
 * N5-r3 / A4（N-2 / R2-M2 关闭）：从**独立观测面** `authority_steps`（由权威快照的位移算出，
 * 本模块**只读**它来配对）重建「权威位移方向变化 ≥ 阈值」的 tick 序列。
 *
 * r2 的缺陷（raven N-2）：`turnHits[].matched` 的四个合取项**全部取自同一 push 块内刚写下的值**
 * ⇒ 只要该分支执行就**结构性必真** ⇒ `hit_rate ≡ 1`，判据读到的「命中率」不是测量结果，
 * 而是「回读自己刚 push 的事件」。现在改为：**观测**来自 `authority_steps`，
 * **配对对象**是 `clip_timeline` 的 turn 事件 ⇒ 无对应 turn 事件时判红（不是回读自身）。
 */
function observedTurnDirectionChanges(): Array<{ entityId: string; tick: number; direction_delta_rad: number }> {
  const out: Array<{ entityId: string; tick: number; direction_delta_rad: number }> = [];
  const last = new Map<string, number | null>();
  for (const step of authoritySteps) {
    if (step.direction_rad === null) continue;
    const prev = last.get(step.entityId) ?? null;
    last.set(step.entityId, step.direction_rad);
    if (prev === null) continue;
    const delta = Math.abs(wrapToPi(step.direction_rad - prev));
    if (delta >= TURN_DIRECTION_DELTA_RAD - TURN_DIRECTION_EPSILON) {
      out.push({ entityId: step.entityId, tick: step.tick, direction_delta_rad: Number(delta.toFixed(6)) });
    }
  }
  return out;
}

/**
 * 配对判定（**外部可复核**）：该观测到的方向变化，是否真的在 `clip_timeline` 里有对应 turn 事件，
 * 且该事件的权重/保持时长满足 `AC-B-3` 下限、`turnUntil` 真的覆盖保持窗。
 * 任一条件不成立 ⇒ `false`（判据随之判红）。**没有 turn 事件 ⇒ false**（不是回读自己刚写的事件）。
 */
function turnSlotMatched(change: { entityId: string; tick: number }): boolean {
  const event = clipTimeline.find((e) => e.entityId === change.entityId
    && e.tick === change.tick && e.slot === 'turn');
  if (event === undefined) return false;
  if (Number(event.weight) < TURN_SLOT_WEIGHT) return false;
  if ((Number(event.hold_ticks) * TICK_MS) / 1000 < TURN_HOLD_MIN_SECONDS) return false;
  if ((turnUntil.get(change.entityId) ?? -1) < change.tick + TURN_HOLD_TICKS) return false;
  return true;
}

/** 表现槽时间线（`AC-B-3` / `AC-B-7` / `AC-H-3` 的取数面）。 */
export function clipTimelineSnapshot(): ClipEvent[] {
  return clipTimeline.map((e) => ({ ...e }));
}

/**
 * `AC-B-3` 的命中率：每次**权威位移方向变化 ≥90°**都必须出现 `turn` 槽权重 ≥0.5 且持续 ≥0.3 s。
 * 无方向变化 ⇒ `hit_rate = null`（**不可判** ⇒ 记 GAP，不得 PASS）。
 */
export function turnHitRate(): {
  direction_changes: number;
  matched: number;
  hit_rate: number | null;
  hold_seconds: number;
  weight: number;
} {
  // N5-r3 / A4：`direction_changes` = **独立观测**（`authority_steps` 的方向变化），
  // `matched` = 该观测与 `clip_timeline` 的 turn 事件**逐 tick 配对**的结果 ⇒ 可**为假**（不再是恒 1）。
  const changes = observedTurnDirectionChanges();
  const matched = changes.filter((change) => turnSlotMatched(change)).length;
  return {
    direction_changes: changes.length,
    matched,
    hit_rate: changes.length === 0 ? null : Number((matched / changes.length).toFixed(6)),
    hold_seconds: (TURN_HOLD_TICKS * TICK_MS) / 1000,
    weight: TURN_SLOT_WEIGHT,
  };
}

/** `wrapToPi`（最短弧归一化；`AC-B-2a` 的口径）。 */
export function wrapToPi(rad: number): number {
  let x = rad;
  while (x > Math.PI) x -= 2 * Math.PI;
  while (x < -Math.PI) x += 2 * Math.PI;
  return x;
}

export interface PresentationOptions {
  /** 插值时间常数（ms）；表现为「到权威位置的指数靠近」，**不越过**目标。 */
  smoothingMs?: number;
  /** 每 tick 的最大权威位移（米）——由**内核侧**序列给出，用于 `eps_used`（`AC-B-6b`）。 */
  epsAuthorityMaxStepM?: number;
  /** 注视目标（`entity_id` 或场景节点名）。 */
  gazeTarget?: string | null;
}

export interface Presentation {
  /** 推一帧表现更新。**只读**权威容器。 */
  step(dtMs: number): void;
  displayed(): DisplayedEntity[];
  /** 表现层到权威位置的距离（`AC-B-6a` 的分子）。 */
  maxDeviationM(): number;
  epsUsedM(): number;
  cameraMode(): CameraMode;
  enterInteractiveCamera(): void;
  resetCamera(): void;
  cameraReport(): Record<string, unknown>;
  report(): Record<string, unknown>;
  dispose(): void;
}

const DEFAULT_PRESENTATION: Omit<PresentationOptions, never> = { smoothingMs: 120, epsAuthorityMaxStepM: 0.92736 };

export function createPresentation(options: PresentationOptions = {}): Presentation {
  const opts = { ...DEFAULT_PRESENTATION, ...options };
  const displayed = new Map<string, DisplayedEntity>();
  const prevAuthPos = new Map<string, [number, number, number]>();
  let cameraMode: CameraMode = 'inspection';
  let gazeTarget: string | null = opts.gazeTarget ?? null;
  const deviations: number[] = [];

  function ensure(entityId: string): DisplayedEntity {
    let entry = displayed.get(entityId);
    if (!entry) {
      const auth = authority.entities.get(entityId);
      const start: [number, number, number] = auth ? [...auth.pos_m] as [number, number, number] : [0, 0, 0];
      entry = {
        entityId,
        displayed_position_m: start,
        facing_yaw_rad: 0,
        slot_weights: zeroWeights(),
        gaze_target: gazeTarget,
        interpolated: false,
      };
      displayed.set(entityId, entry);
    }
    return entry;
  }

  return {
    step(dtMs: number) {
      // **只读** authority：本函数绝不写 `authority.entities`（结构上的第二权威隔离）。
      const alpha = Math.min(1, dtMs / Math.max(1, opts.smoothingMs ?? 120));
      for (const [entityId, auth] of authority.entities) {
        const entry = ensure(entityId);
        const prev = entry.displayed_position_m;
        const dx = auth.pos_m[0] - prev[0];
        const dy = auth.pos_m[1] - prev[1];
        const dz = auth.pos_m[2] - prev[2];
        // 指数靠近，**不越过**目标（不会瞬移，也不会过冲）
        const next: [number, number, number] = [
          prev[0] + dx * alpha,
          prev[1] + dy * alpha,
          prev[2] + dz * alpha,
        ];
        entry.displayed_position_m = next;
        entry.interpolated = Math.abs(dx) + Math.abs(dy) + Math.abs(dz) > 1e-9;

        // 朝向：由**权威位移方向**派生（内核不建模 heading —— 实测 0 命中）
        const before = prevAuthPos.get(entityId) ?? null;
        recordAuthorityStep(entityId, before, auth.pos_m, auth.tick);
        prevAuthPos.set(entityId, [...auth.pos_m] as [number, number, number]);
        const steps = authoritySteps.filter((s) => s.entityId === entityId);
        const lastStep = steps.length > 0 ? steps[steps.length - 1] : null;
        const lastDir = [...steps].reverse().find((s) => s.direction_rad !== null);
        if (lastDir && lastDir.direction_rad !== null) {
          const target = lastDir.direction_rad;
          // ---------------------------------------------------------- AC-B-3：转身槽由**权威位移方向**变化驱动
          const prevDir = lastDirection.get(entityId) ?? null;
          if (prevDir !== null) {
            const delta = Math.abs(wrapToPi(target - prevDir));
            if (delta >= TURN_DIRECTION_DELTA_RAD - TURN_DIRECTION_EPSILON) {
              clipTimeline.push({
                entityId, tick: auth.tick, slot: 'turn', weight: TURN_SLOT_WEIGHT,
                hold_ticks: TURN_HOLD_TICKS, trigger_direction_delta_rad: Number(delta.toFixed(6)),
              });
              turnUntil.set(entityId, auth.tick + TURN_HOLD_TICKS);
              // ---------------------------------------------------------- N5-r3 / A4（N-2 关闭）
              // r2 在这里**回读自己刚 push 的事件**来算 `matched` ⇒ 四个合取项全部来自同一
              // block 内刚落盘的常量 ⇒ 结构性恒真、`hit_rate ≡ 1`。
              // 现在这里**不再**记录命中：命中与否由 `turnHitRate()` 在报告时**独立配对**
              // （观测面 = `authority_steps` 的方向变化；配对对象 = `clip_timeline` 的 turn 事件）。
            }
          }
          lastDirection.set(entityId, target);
          // ---------------------------------------------------------------- N5-C r2 / FIX-3
          // **方向死区 + 朝向限速**（只改呈现代码；权威位置/朝向的派生口径不变）。
          //
          // 实测根因（r2，`run-b-analysis.mjs` 的红读数）：内核单 tick 位置带 `JITTER_MM = 100` 抖动
          // 与偶发 ~0.5 m 单 tick 跳变 ⇒ **权威位移方向**在静止点附近逐 tick 反 180°；而本层
          // `smoothingMs = TICK_MS` ⇒ `alpha = 1` ⇒ 朝向**逐 tick 直接快照**目标 ⇒ 单帧 180° 反向跳变。
          // 实测：阈值取 5 mm 时 692 对仍反 180°、取 200 mm 时仍剩 148 对 ⇒ **纯幅度死区不足以封堵**
          // （噪声幅度与真位移同量级），必须在**朝向变化率**上封堵。
          //
          // ① 死区：本 tick 权威位移 ≤ `EPS_FLOOR_M`（近静止）⇒ 保留上一朝向，不跟随方向噪声；
          // ② 限速：一次 ≥90° 的方向变化按 `AC-B-3` **自己的**转向保持窗 `TURN_HOLD_TICKS` 表达
          //    （0.3 s / 3 tick）⇒ 单帧朝向变化 ≤ `TURN_DIRECTION_DELTA_RAD / TURN_HOLD_TICKS` = 30°。
          //    ⇒ 「不得逐 tick 翻转」在**表现状态**层面成立；**不**掩盖权威位移（`B-1a`/`B-6a` 的
          //    位置口径一字未动），槽位与命中率（`B-3`）仍取**原始** `authority_steps`。
          const nearStatic = lastStep === null || lastStep.dpos_norm_m <= EPS_FLOOR_M;
          if (!nearStatic) {
            const maxTurnPerTick = TURN_DIRECTION_DELTA_RAD / TURN_HOLD_TICKS;
            const yawDelta = wrapToPi(target - entry.facing_yaw_rad);
            const limited = Math.max(-maxTurnPerTick, Math.min(maxTurnPerTick, yawDelta));
            entry.facing_yaw_rad = wrapToPi(entry.facing_yaw_rad + limited * alpha);
          }
        }
        // 运行期槽位权重（**表现状态**；`state_clip_map` 是身份/行为态映射，二者互不替代）
        const turning = (turnUntil.get(entityId) ?? -1) >= auth.tick;
        const moving = (lastDir?.dpos_norm_m ?? 0) > EPS_FLOOR_M;
        entry.slot_weights = turning
          ? { idle: 0.1, walk: 0.1, turn: TURN_SLOT_WEIGHT, speak: 0.1, listen: 0.1 }
          : moving
            ? { idle: 0.1, walk: 0.9, turn: 0, speak: 0, listen: 0 }
            : { idle: 1, walk: 0, turn: 0, speak: 0, listen: 0 };
        const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);
        deviations.push(Number(distance.toFixed(6)));
      }
    },
    displayed: () => [...displayed.values()].map((d) => ({
      ...d,
      displayed_position_m: [...d.displayed_position_m] as [number, number, number],
      slot_weights: { ...d.slot_weights },
    })),
    maxDeviationM: () => (deviations.length ? Math.max(...deviations) : 0),
    epsUsedM: () => Math.max(Number(opts.epsAuthorityMaxStepM ?? 0), EPS_FLOOR_M),
    cameraMode: () => cameraMode,
    enterInteractiveCamera: () => { cameraMode = 'interactive'; },
    resetCamera: () => { cameraMode = 'inspection'; },
    cameraReport: () => ({
      camera_mode: cameraMode,
      inspection_position: [...INSPECTION_POSITION],
      inspection_look_at: [...INSPECTION_LOOK_AT],
      observation_position: [...OBSERVATION_POSITION],
      observation_look_at: [...OBSERVATION_LOOK_AT],
      observation_active: false,
      /** `interactive` 的可进入性（`AC-A-3⑦` 的取数面）。 */
      interactive_enterable: true,
      interactive_entered: cameraMode === 'interactive',
    }),
    report: () => ({
      schema_version: 'n5-presentation/1',
      authority_epoch: authority.epoch,
      authority_tick: authority.tick,
      authority_write_log: authorityWriteLog(),
      authority_write_sources: [...new Set(authorityWriteLog().map((e) => e.source))],
      displayed: [...displayed.values()].map((d) => ({
        ...d,
        displayed_position_m: [...d.displayed_position_m] as [number, number, number],
        slot_weights: { ...d.slot_weights },
      })),
      authority_steps: authorityStepsSnapshot(),
      /** `AC-B-3` / `AC-B-7` / `AC-H-3`：表现槽时间线 + 转身命中率。 */
      clip_timeline: clipTimelineSnapshot(),
      turn_hit_rate: turnHitRate(),
      clip_constants: {
        turn_hold_ticks: TURN_HOLD_TICKS,
        turn_slot_weight: TURN_SLOT_WEIGHT,
        turn_direction_delta_rad: Number(TURN_DIRECTION_DELTA_RAD.toFixed(6)),
      },
      max_deviation_m: deviations.length ? Math.max(...deviations) : 0,
      eps_used_m: Math.max(Number(opts.epsAuthorityMaxStepM ?? 0), EPS_FLOOR_M),
      eps_floor_m: EPS_FLOOR_M,
      camera: {
        camera_mode: cameraMode,
        inspection_position: [...INSPECTION_POSITION],
        inspection_look_at: [...INSPECTION_LOOK_AT],
      },
      slots: [...CHARACTER_SLOTS],
      /**
       * N5-r2 / A4③：**不再是字面量**。r1 的缺陷（raven R-3）：`client_may_write_authority: false`
       * 是 `report()` 里的字面量 ⇒ 被测模块自报自己合规，判据没有外部锚。
       * 现在由**实际的权威写日志**派生（外部锚 = `authority_scan.mjs` 的 AST 扫描，已进 N5 门禁小节）。
       */
      client_may_write_authority: authorityWriteSources().some((s) => s !== 'apply'),
    }),
    dispose() {
      displayed.clear();
      prevAuthPos.clear();
      deviations.length = 0;
    },
  };
}

function zeroWeights(): Record<CharacterSlot, number> {
  const out = {} as Record<CharacterSlot, number>;
  for (const slot of CHARACTER_SLOTS) out[slot] = 0;
  return out;
}

/** 供 `presentation.ts` 之外的消费者（探针 / 判据）使用的常量快照。 */
export function presentationConstants(): Record<string, unknown> {
  return {
    inspection_position: [...INSPECTION_POSITION],
    inspection_look_at: [...INSPECTION_LOOK_AT],
    observation_position: [...OBSERVATION_POSITION],
    observation_look_at: [...OBSERVATION_LOOK_AT],
    eps_floor_m: EPS_FLOOR_M,
    tick_ms: TICK_MS,
    default_camera_mode: 'inspection',
  };
}
