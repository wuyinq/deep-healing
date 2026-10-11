/**
 * S-1 / S-2 · **角色实例节点**（N5 / B-2）—— 把一个 `entity_id` 变成一个**多网格 + 骨骼 + 材质**
 * 的角色实例，而不是一个躯干 `BoxGeometry`（REQ §三 S-1 原文）。
 *
 * 结构与职责：
 *   - `character-instance:<entity_id>` 是一个 **`THREE.Group` 根**（`asset_binding.ts` 的绑定项决定
 *     它下面挂什么）；
 *   - **回落盒体**：`loader === null`（Node / 无 WebGL）或 GLB 加载失败 ⇒ Group 下不挂 GLB，
 *     只记 `degradations`（`AC-I-1` / `AC-I-2`：**不抛**，且 `characterReport()` 结构完整）；
 *   - **契约兼容层**：N2 的盒体部件（`torso`/`head`/…）**不因本模块改变**（R7）——
 *     本模块只**新增**节点，既有部件判据的取数路径一字不动。
 *
 * 五个表现槽（`AC-A-6a`：待机 / 行走 / 转身 / 说话 / 倾听）：
 *   本轮 rigged GLB = `web/assets/character/xuqin-body.glb` —— **AI 图生3D**（火山方舟 Ark /
 *   影眸 Hyper3D Gen-2，`model hyper3d-gen2-260112`）+ 本地 Blender 绑定。**许可状态 = 未证实**
 *   （`license = "unknown"` ⇒ 商用分发前须取得供应商书面许可；署名与商用限制说明见
 *   `web/src/ui/player/credits.ts`，来源登记面见 `web/assets/provenance.json`）。
 *   实测骨架 / 动画（重测读数见 `evidence/artisan/ac2-new-asset.json`）：`26` 骨
 *   （`skin = XuqinArmature`）、**2 条**动画 —— `Idle`（下标 0）、`Walk`（下标 1），各 `78` channels。
 *   ⇒ 槽位来源**逐槽显式标注**（`clip` = 真 GLB 动画；`procedural` = 由骨骼变换程序化驱动）。
 *   **不得**把程序化槽位说成「GLB 自带动画」（那会是自报冒充）。
 *   **动画接线现状（FU-003 已接线）**：`gltf.animations` 捕获 → `THREE.AnimationMixer`（根 =
 *   `gltf.scene`）→ 按 **clip 名** 建 `clipAction`（`Idle`/`Walk`）；`update(dtMs, motion?)` 内
 *   `mixer.update(dtMs / 1000)` 推进，`dispose()` 内 `stopAllAction()` 停住（`clip_weights` 可观测）。
 *   槽位来源**逐槽如实**：`idle`/`walk` = 真 GLB clip（`kind: 'clip'`）＋ `head` 关节在
 *   `mixer.update()` **之后**的程序化叠加 —— 有 mixer 且当前 clip 覆盖 `head` 时是「读后加」
 *   （`rotation.x = rotation.x + sway`）；**否则**（`E_NO_ANIMATIONS` 降级 / head 不被 clip 覆盖）
 *   改为**相对载入期基准姿态**（`rotation.x = baseX + sway`）—— 该形态**逐帧不累积**（r2/A1）。
 *   是**叠加**、不是 clip 自带；`turn` = root yaw 仍由**权威位移方向**驱动（**如实保留**：无 clip
 *   混合/降速细节）；`speak` / `listen` **未接线**（无对应 GLB clip，本轮未实现）。
 *   运动判据取自**表现层显示位移**的窗口净位移（阈值实测标定，见 `03_artisan_self_test.log`）；
 *   实测读数：真 GLB `26` 骨、2 条 clip 各 `78` channels，头部关节名 **`head`**（小写蛇形）。
 *   凡本表声称「已播放 / 已混合 / 正在驱动骨骼」必须有对应读数支撑；未实现即记 GAP。
 */

import * as THREE from 'three';
import { BINDINGS, bindingForEntity, recordBindingDegradation, type AssetBinding } from './asset_binding.ts';
import { SURFACES_EXT, type ExtSurfaceId } from './materials.ts';

/** 五个表现槽（`AC-A-6a` / `AC-B-3` / `AC-H-3`）。 */
export type CharacterSlot = 'idle' | 'walk' | 'turn' | 'speak' | 'listen';
export const CHARACTER_SLOTS: readonly CharacterSlot[] = ['idle', 'walk', 'turn', 'speak', 'listen'];

/** 槽位的**来源**：真 GLB 动画 / 程序化骨骼变换。**逐槽标注，不合并**。 */
export interface SlotSource {
  readonly slot: CharacterSlot;
  readonly kind: 'clip' | 'procedural';
  /** `clip` ⇒ GLB 动画下标；`procedural` ⇒ 驱动的骨骼名与它改写的量。 */
  readonly detail: string;
}

export const SLOT_SOURCES: readonly SlotSource[] = [
  { slot: 'idle', kind: 'clip', detail: 'GLB `Idle`（animation[0]，78 channels）由 `AnimationMixer` 播放；**另**在 `mixer.update()` **之后**叠加 `head` 关节的程序化偏移（有 mixer 且 clip 覆盖 `head` 时「读后加」`rotation.x += sway`；否则相对载入期基准 `rotation.x = baseX + sway`。振幅 0.02 rad）—— 是**叠加**、不是 clip 自带' },
  { slot: 'walk', kind: 'clip', detail: 'GLB `Walk`（animation[1]，78 channels）由 `AnimationMixer` 播放；由**表现层显示位移**的窗口净位移判据在运动时激活（crossfade 0.3 s、`warp=false`）' },
  { slot: 'turn', kind: 'procedural', detail: '根 yaw 由**权威位移方向**驱动（presentation.ts 死区 + 限速 ⇒ world.ts 写 group.rotation.y）；**如实保留 GAP**：不存在任何 clip 的降速/混合细节（本轮未实现）' },
  { slot: 'speak', kind: 'procedural', detail: '**未接线**：计划中的头部点头 + 双臂小幅开合尚未实现（无对应 GLB clip，无播放路径）⇒ GAP' },
  { slot: 'listen', kind: 'procedural', detail: '**未接线**：计划中的头部侧倾 + 躯干微前倾尚未实现（无对应 GLB clip，无播放路径）⇒ GAP' },
];

// ─────────────────────────────────────────────────────────────────────────────
// FU-003 · 动画接线参数与判据（**实测标定**，见 03_artisan_self_test.log §1/§6）
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 运动判据的**采样窗口**（tick 数）：`TICK_MS = 100 ms` ⇒ `10` tick = `1.0 s`。
 *
 * 为什么用**窗口净位移**而不是「逐 tick 幅度」（raven 预审 C-1，本次实测确认）：
 * 真 demo（600 tick，真内核 `npc-006`）逐 tick 显示位移 `min=1 mm / p1=3 mm / p10=35 mm /
 * med=462 mm`；而内核权威位置的**确定性抖动**是 `JITTER_MM = 100`（x 轴 uniform ±100 mm/tick，
 * `kernel/.../tick.py` 与 `ecs.py`，直接写进权威位置）⇒ 逐 tick 幅度**无法**分开「真位移」与
 * 「噪声」：`静止臂 p99 < T < 运动臂 p1` 不成立（实测两分布重叠、静止臂样本 0）。
 * 改用「窗口两端净位移」：随机游走在**净位移**里相消（不随时间单调增大）——这与被预审否证的
 * 「连续 N 帧**累计**位移」兜底**不是同一形态**。
 */
export const MOTION_WINDOW_TICKS = 10;

/**
 * 进入运动态的**窗口净位移**阈值（米）。标定依据见 `03` §1：高于纯抖动模型 p999 = **0.578** m
 * （数值出处 `evidence/artisan/calib/motion-calibration.json` 的 `jitter_only_model_window_net_m.p999`；
 * 模型 = x 轴 uniform ±100 mm/tick 的 K=10 窗口净位移，40 万样本。r2/A4 修正：r1 注释误写 0.587）。
 *
 * **本判据的语义边界（r2/A6，两侧门禁同源登记）**：
 *   ① 本判据给的是「**显示位置在 K=10 窗口内的净位移 > 0.70 m**」，**不等于**内核自报的
 *      `action === 'walk'` —— 两者是**不同的量**，交集远小于 100%；
 *   ② 真机交叉表实测（`evidence/artisan/calib/action-cross-tab.json`，600 tick 真 demo）：
 *      内核 `walk` 标签的窗口里只有 **15.8%** 判 `Walk`（`rest` 10.0% / `talk` ~84% 判 Idle）
 *      ⇒ 「运动 ⇒ Walk」这条臂**灵敏度低**，`03` §7 如实标 GAP（REQ 规定的判据面 = 显示位移，
 *      两臂在该面上分布重叠：`walk` p10 0.408 m < `rest` p90 0.556 m ⇒ 无法区分）。
 */
export const MOTION_EPS_M = 0.7;

/** 退出运动态的**窗口净位移**阈值（米，迟滞下界 ⇒ 状态不抖动）。 */
export const MOTION_EXIT_M = 0.45;

/** clip 切换的 crossfade 时长（秒）—— `≥ 0.3 s` ⇒ 以 `TICK_MS` 采样有 ≥3 个中间权重点。 */
export const CROSSFADE_S = 0.3;

/** `head` 程序化叠加振幅（弧度；`0.02 rad ≈ 1.15°`）。 */
export const HEAD_SWAY_RAD = 0.02;

/** 运动状态：**只由调用方（`world.ts`）从表现层显示位移推导**，实例不自造、不读权威。 */
export interface MotionState { readonly moving: boolean }

/**
 * 显示位移 → 是否在动。`epsM` = 位移死区（**米**，严格大于才算运动）。
 *
 * 调用方传的是**窗口两端**的显示位置（相隔 `MOTION_WINDOW_TICKS`），不是相邻 tick ——
 * 阈值与采样间隔的语义分工见 `03` §6（L-1）。
 */
export function motionFromDisplacement(
  prev: readonly [number, number, number] | null,
  next: readonly [number, number, number],
  epsM: number,
): boolean {
  if (!prev) return false;
  const dx = Number(next[0]) - Number(prev[0]);
  const dy = Number(next[1]) - Number(prev[1]);
  const dz = Number(next[2]) - Number(prev[2]);
  const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);
  if (!Number.isFinite(distance) || !Number.isFinite(epsM)) return false;
  return distance > epsM;
}

/**
 * `report().animation` 的读数面（**纯加法**）。
 *
 * 硬约束：**每个数值必须有限**（无 mixer ⇒ `0` / `{}`，不得 `NaN`）——
 * `test/render-client.test.ts` 的 `assertNoNonFinite()` 递归遍历整份 `report()`；
 * `mixer_time_s` 取 `mixer.time`（**秒**），不是 `dtMs`。
 */
export interface AnimationReport {
  /** GLB 实际 clip 条数（无 mixer ⇒ 0）。 */
  clip_count: number;
  /** 按 GLB 顺序的 clip 名（无 mixer ⇒ `[]`）。 */
  clip_names: string[];
  /** 当前**权重最大**的 action 名；mixer 无 mixer/无 clip ⇒ `null`。
   *  **回落分支**（r2/A5，raven L-1）：过渡起点等**所有 action 权重全为 0** 时，本条**回落**到
   *  状态机目标态 `activeClip`（不是 `null`）——见下面的 `if (best === null) best = activeClip;`。 */
  active_clip: string | null;
  /** `mixer.time`（秒；无 mixer ⇒ 0）。 */
  mixer_time_s: number;
  /**
   * r2 / A3（raven M-5）：`dispose()` 之后 mixer 是否**真被停住**（`dispose()` 内实测
   * `actions` 全部 `!isRunning()`；`mixer === null` ⇒ `false`，不用空集造「没有东西可停」的假绿）。
   * 三条既有条件（逐帧 head 恒定 / `mixer_time_s` 不增 / `active_clip === null`）全部由
   * `dispose()` 里 `gltfScene = null` 的首行短路保证 ⇒ 删掉 `stopAllAction()` 它们**仍全过**；
   * 本字段是**唯一**对「是否真调过 `stopAllAction()`」有区分力的读数。
   */
  mixer_stopped: boolean;
  /** 逐 clip 有效权重（crossfade 过渡期两值同时 >0；无 mixer ⇒ `{}`）。 */
  clip_weights: Record<string, number>;
  /** 由 clip track 名（`head.quaternion`，**精确匹配**）判定。 */
  head_driven_by_clip: boolean;
  /** 实际命中的关节名（GLB 事实：`head`，小写蛇形）；无 mixer/无该关节 ⇒ `null`。 */
  head_joint: string | null;
  /** 本帧叠加量（弧度；未叠加 ⇒ 0）。 */
  head_sway_rad: number;
  /**
   * 本帧 `head` 局部姿态相对**载入期基准姿态**的偏差（四元数夹角，弧度；无 head 骨 ⇒ 0）。
   * r2 / A2（raven M-2）：`head_sway_rad` 只报**当帧叠加量** ⇒ 「累积」这类缺陷在它上面**看不见**
   * （实测缺陷态：当帧 0.006866 rad 而绝对偏差 0.249837 rad，低估 ~36×）；本字段报**绝对**偏差。
   */
  head_delta_from_base_rad: number;
  /** 本帧 `head` 局部四元数（AC-4 的 clip-only 对照面；无 mixer ⇒ `[0,0,0,0]` 占位）。 */
  head_local_quaternion: [number, number, number, number];
  /** crossfade 剩余时长（秒）——「无突跳」的数值证据；无过渡 ⇒ 0。 */
  crossfade_pending_s: number;
  /** 判据参数（只读，便于外部复核标定口径）。 */
  motion_window_ticks: number;
  motion_eps_m: number;
  motion_exit_m: number;
}

/**
 * **`AC-H-4a` 的映射表**：身份/行为 `state_id` → 该状态下的槽位权重。
 *
 * 读数路径（`AC-H-4a` 写死）：`web/src/scene/character_instance.ts` 的 `state_clip_map`。
 * `state_id` 集合来源 = 内容包 `npcs/npc-006.json` 的 `appearance.states[].id` **冻结清单**
 * （= `["daily", "masked"]`，落 `web/scripts/assert_inputs.json`）。
 *
 * 非平凡性（`AC-H-4a`）：成员数 ≥2 **且** 与 `state_id` 集合**双射**；注入两个**不同** `state_id`
 * ⇒ 映射**必须不同**（负对照 `AC-H-4b`：把本表退化为常量函数 ⇒ H-4a 必红）。
 */
export const state_clip_map: Readonly<Record<string, Readonly<Record<CharacterSlot, number>>>> = {
  daily: { idle: 0.65, walk: 0.35, turn: 0.0, speak: 0.0, listen: 0.0 },
  masked: { idle: 0.25, walk: 0.15, turn: 0.0, speak: 0.60, listen: 0.0 },
};

export const STATE_CLIP_MAP_KEYS: readonly string[] = Object.keys(state_clip_map);

/** 槽位权重归一化（同一 `state_id` ⇒ 逐字段相同；读法无关）。 */
export function slotWeightsForState(stateId: string | null | undefined): Record<CharacterSlot, number> {
  const entry = (stateId && state_clip_map[stateId]) || state_clip_map.daily;
  const total = CHARACTER_SLOTS.reduce((sum, slot) => sum + Number(entry[slot] ?? 0), 0);
  const out = {} as Record<CharacterSlot, number>;
  for (const slot of CHARACTER_SLOTS) {
    out[slot] = total > 0 ? Number((Number(entry[slot] ?? 0) / total).toFixed(6)) : 0;
  }
  return out;
}

/** 内容包 `appearance.states[].id` 的**冻结清单**（`AC-H-4a` 的判据输入）。 */
export const FROZEN_STATE_IDS: readonly string[] = ['daily', 'masked'];

export interface CharacterInstanceOptions {
  entityId: string;
  /** `false` ⇒ 强制走回落盒体（`AC-I-2` 的负对照注入面）。 */
  bindingAvailable?: boolean;
  /** GLTFLoader（真 WebGL 时由 `world.ts` 注入；Node 下为 `null`）。 */
  gltfLoader?: { load: (url: string, onLoad: (gltf: unknown) => void, onProgress?: unknown, onError?: (e: unknown) => void) => void } | null;
  /** 该实例的 `SURFACES_EXT` 表面（默认取绑定表）。 */
  extSurfaces?: readonly ExtSurfaceId[];
}

export interface CharacterInstance {
  entityId: string;
  binding: AssetBinding | null;
  /** **`Group` 根**（`AC-S1` 的字面形态）。 */
  group: THREE.Group;
  glbLoaded(): boolean;
  slotSources(): SlotSource[];
  /** 槽位权重（`AC-B-3` 的 `turn` 权重即取自此）。 */
  weights(stateId?: string | null): Record<CharacterSlot, number>;
  /**
   * 推一帧。**兼容**：单参 `update(dtMs)` 仍可用（缺省第 2 参 ⇒ **保持当前 clip**，不推断、不抖动）。
   * `motion` 由**调用方**（`world.ts`）从表现层显示位移推导（实例不读 `presentation`）。
   */
  update(dtMs: number, motion?: MotionState | null): void;
  /** 动画读数面（= `report().animation`；纯加法，便于判据直接取数）。 */
  animationReport(): AnimationReport;
  report(): Record<string, unknown>;
  dispose(): void;
}

const MM = 1000;

/**
 * 建一个角色实例。**不抛**：任何失败都落到 `degradations` 并回落盒体路径。
 */
export function createCharacterInstance(options: CharacterInstanceOptions): CharacterInstance {
  const binding = options.bindingAvailable === false ? null : bindingForEntity(options.entityId);
  const group = new THREE.Group();
  group.name = `character-instance:${options.entityId}`;
  group.userData.entity_id = options.entityId;
  group.userData.binding_id = binding?.binding_id ?? null;

  const degradations: Array<{ code: string; detail: string }> = [];
  let glbLoaded = false;
  let gltfScene: THREE.Object3D | null = null;
  let tickAcc = 0;
  /**
   * r2 / MUST-2（侦察官 MEDIUM-1）：`dispose()` 之后**在飞的 `load` 回调**仍会 `group.add(scene0)`
   * 并置 `glbLoaded=true` ⇒ 脱链 group 持 GPU 资源（死实例）。此标志让晚到回调**首行短路**，
   * 既不 `group.add` 也不 `recordBindingDegradation`。`report()` 字段与 `dispose()` 其余语义一字不改。
   */
  let disposed = false;

  // ── FU-003 / W1：`AnimationMixer` 生命周期（`null` = 无 mixer / GLB 无 clip）
  let mixer: THREE.AnimationMixer | null = null;
  /** 按 **clip 名** 索引的 action（不用下标：下标会随 GLB 重导出漂移）。 */
  const actions = new Map<string, THREE.AnimationAction>();
  /** 状态机当前目标态（`report().active_clip` 另按**权重最大**现算）。 */
  let activeClip: string | null = null;
  /** crossfade 结束时刻（以 `mixer.time` 秒为基准；`≤ mixer.time` ⇒ 无过渡）。 */
  let crossfadeEndsAtS = 0;
  // ── FU-003 / W3：命中的 `head` 关节（GLB **小写蛇形** 名）与上一帧叠加量
  let headBone: THREE.Bone | null = null;
  let headSwayRad = 0;
  /**
   * r2 / A1+A2：**载入期基准姿态**（载入后、任何 sway 之前捕获一次）。
   * 无 mixer / head 不被 clip 覆盖时以它为准做「相对基准」叠加 ⇒ **不累积**；同时供 A2 的
   * `head_delta_from_base_rad` 报**绝对**偏差。
   */
  let headBaseX = 0;
  const headBaseQuat = new THREE.Quaternion();
  /** r2 / A3：`dispose()` 里实测的「mixer 真被停住」读数（未 dispose / 无 mixer ⇒ `false`）。 */
  let mixerStopped = false;
  const extSurfaces = (options.extSurfaces ?? (binding?.ext_surfaces ?? [])) as readonly ExtSurfaceId[];

  if (!binding) {
    degradations.push({ code: 'E_BINDING_MISSING', detail: `${options.entityId} 无绑定项 ⇒ 回落盒体` });
    recordBindingDegradation('E_BINDING_MISSING', options.entityId);
  } else if (!options.gltfLoader) {
    degradations.push({ code: 'E_LOADER_NULL', detail: 'loader === null（无 WebGL / Node）⇒ 回落盒体' });
    recordBindingDegradation('E_LOADER_NULL', `${options.entityId}:${binding.binding_id}`);
  } else {
    try {
      options.gltfLoader.load(
        binding.glb_url,
        (gltf: unknown) => {
          // r2 / MUST-2：晚到的在飞回调在 `dispose()` 之后必须**首行短路**（不挂 GLB、不记降级）。
          if (disposed) return;
          const scene0 = (gltf as { scene?: THREE.Object3D })?.scene;
          if (!scene0 || !(scene0 as THREE.Object3D).isObject3D) {
            degradations.push({ code: 'E_GLB_EMPTY', detail: 'GLB 无 scene' });
            recordBindingDegradation('E_GLB_EMPTY', binding.glb_url);
            return;
          }
          gltfScene = scene0;
          scene0.name = `glb:${binding.binding_id}`;
          scene0.traverse((node: THREE.Object3D) => {
            const mesh = node as THREE.Mesh;
            if (mesh.isMesh) {
              mesh.castShadow = true;
              mesh.receiveShadow = true;
            }
          });
          group.add(scene0);
          glbLoaded = true;
          // ── FU-003 / W1：动画接线。
          // **顺序硬约束**（raven 预审 M-5）：本分支必须在上面两行**之后** ——
          // `scene_assert.mjs` 的检查 25 用**不带 `animations`** 的假 loader 调
          // `onLoad({ scene: group })` 并要求 `glb_loaded === true`；在此 early-return 会把它判红。
          const animations = (gltf as { animations?: THREE.AnimationClip[] }).animations;
          if (!Array.isArray(animations) || animations.length === 0) {
            // 缺失/空 ⇒ 显式降级（**不抛**，保持「构造期不抛」的既有不变量）。
            degradations.push({ code: 'E_NO_ANIMATIONS', detail: `${binding.binding_id}: GLB 无动画 clip ⇒ 不建 mixer` });
            recordBindingDegradation('E_NO_ANIMATIONS', binding.glb_url);
          } else {
            mixer = new THREE.AnimationMixer(scene0);
            for (const clip of animations) actions.set(clip.name, mixer.clipAction(clip));
            // 初始态 = `Idle`（角色静置是默认态）；无 `Idle` ⇒ 第一条 clip。
            const initial = actions.has('Idle') ? 'Idle' : animations[0]?.name ?? null;
            if (initial !== null) {
              activeClip = initial;
              actions.get(initial)?.play();
            }
          }
          // ── FU-003 / W3：按**实际关节名**精确匹配（本轮 GLB 事实：`head`，小写蛇形；
          // `hem_*` 等不含 `head` 字样 ⇒ 禁止模糊 `includes('head')`）。
          scene0.traverse((node: THREE.Object3D) => {
            if ((node as THREE.Bone).isBone && node.name === 'head') {
              headBone = node as THREE.Bone;
              // r2 / A1+A2：**载入期基准姿态** —— 在任何 sway 之前捕获一次。此处 mixer 尚未
              // `update()` 过，读到的是 GLB 的静止姿态（head 的局部旋转/四元数）。
              // 无 mixer / head 不被 clip 覆盖时以它为基准叠加 ⇒ 不累积（raven M-2）。
              headBaseX = headBone.rotation.x;
              headBaseQuat.copy(headBone.quaternion);
            }
          });
        },
        undefined,
        (error: unknown) => {
          // L-2：失败路径与成功路径**同口径短路** —— `dispose()` 之后晚到的失败**不得**再写
          // 局部 `degradations`，也不得写模块级降级表（`recordBindingDegradation`）。
          // `dispose()` **之前**的失败照记（不变量）。
          if (disposed) return;
          degradations.push({ code: 'E_GLB_LOAD_FAILED', detail: `${binding.glb_url}: ${String(error)}` });
          recordBindingDegradation('E_GLB_LOAD_FAILED', `${binding.glb_url}: ${String(error)}`);
        },
      );
    } catch (error) {
      // L-2：同款短路（防御性一致化；见设计 §2.3 的诚实边界 —— 该分支在 `dispose()` 之后
      // 结构上不可达，因为 `gltfLoader.load(...)` 只在构造期调用一次、且在 `createCharacterInstance()`
      // 返回前就已完成；该行只在调用形态改变（移入 `update()` / 加重试 / 二次调用）后才变活）。
      // 语义与 `if (disposed) return;` **逐项相同**（`dispose()` 之后零写入）；此处用 `!disposed`
      // 包裹而非裸 `return;`：本函数返回类型为 `CharacterInstance`，裸 `return;` 会引入
      // **本轮新增**的 TS2322 诊断（设计 §8 R-4 要求改前/改后对照、不引入新诊断）。
      if (!disposed) {
        degradations.push({ code: 'E_GLB_LOAD_THREW', detail: String(error) });
        recordBindingDegradation('E_GLB_LOAD_THREW', `${binding.glb_url}: ${String(error)}`);
      }
    }
  }

  /**
   * `head` 是否被任一 action 的 `head.quaternion` 轨道覆盖（**判定面 = track 存在性**，
   * 不是「有没有 head 骨」——与 `head_driven_by_clip` 同一口径）。
   * r2 / A1：它就是「『读后加』不累积」那条前提（mixer 每帧重写 `head.quaternion`）的**可判定形态**。
   */
  function clipDrivesHead(): boolean {
    return [...actions.values()].some((action) =>
      action.getClip().tracks.some((track: THREE.KeyframeTrack) => track.name === 'head.quaternion'));
  }

  /** FU-003 / W4：`report().animation` 的取数（**纯加法**；无 mixer ⇒ `0` / `{}`，全部有限）。 */
  function animationReport(): AnimationReport {
    const clipNames = [...actions.keys()];
    const weights: Record<string, number> = {};
    let best: string | null = null;
    let bestWeight = 0;
    for (const [name, action] of actions) {
      // **只在 action 真的在跑时**读权重：three 的 `getEffectiveWeight()` 对**从未 play** 的
      // action 保留构造期的陈旧值 1（`_updateWeight()` 只在 `mixer._update()` 里被调用）
      // ⇒ 直接读会让「未播放的 clip」贡献 1、权重和变成 2（实测踩到）。
      const raw = action.isRunning() ? Number(action.getEffectiveWeight()) : 0;
      const value = Number.isFinite(raw) ? raw : 0;
      weights[name] = value;
      if (value > bestWeight) {
        bestWeight = value;
        best = name;
      }
    }
    // 权重全 0（过渡起点/未播放）⇒ 回落到状态机目标态，不给假 `null`。
    if (best === null) best = activeClip;
    const headQuat: [number, number, number, number] = headBone === null
      ? [0, 0, 0, 0]
      : [headBone.quaternion.x, headBone.quaternion.y, headBone.quaternion.z, headBone.quaternion.w];
    const headDrivenByClip = clipDrivesHead();
    // r2 / A2：**绝对**偏差（相对载入期基准的姿态偏差；四元数夹角 ⇒ 对任意轴都成立）。
    const headDeltaFromBase = headBone === null
      ? 0
      : 2 * Math.acos(Math.min(1, Math.abs(headBone.quaternion.dot(headBaseQuat))));
    const pendingS = mixer === null ? 0 : Math.max(0, crossfadeEndsAtS - mixer.time);
    return {
      clip_count: clipNames.length,
      clip_names: clipNames,
      active_clip: mixer === null ? null : best,
      mixer_time_s: mixer === null ? 0 : Number(mixer.time),
      mixer_stopped: mixerStopped,
      clip_weights: weights,
      head_driven_by_clip: headDrivenByClip,
      head_joint: headBone === null ? null : headBone.name,
      head_sway_rad: Number(headSwayRad),
      head_delta_from_base_rad: Number.isFinite(headDeltaFromBase) ? Number(headDeltaFromBase) : 0,
      head_local_quaternion: headQuat,
      crossfade_pending_s: Number.isFinite(pendingS) ? Number(pendingS.toFixed(6)) : 0,
      motion_window_ticks: MOTION_WINDOW_TICKS,
      motion_eps_m: MOTION_EPS_M,
      motion_exit_m: MOTION_EXIT_M,
    };
  }

  return {
    entityId: options.entityId,
    binding,
    group,
    glbLoaded: () => glbLoaded,
    slotSources: () => [...SLOT_SOURCES],
    weights: (stateId?: string | null) => slotWeightsForState(stateId),
    update(dtMs: number, motion?: MotionState | null) {
      tickAcc += dtMs;
      if (!gltfScene) return;
      // ── FU-003 / W2：Idle ↔ Walk 状态机。
      // 判据由**调用方**从表现层显示位移推导（实例不自造、不读权威）；
      // `motion` 缺省（`undefined`/`null`）⇒ **不上报** ⇒ 保持当前 clip（不推断、不抖动）。
      if (mixer !== null && motion !== null && motion !== undefined) {
        const desired = motion.moving ? 'Walk' : 'Idle';
        const next = actions.get(desired) ?? null;
        if (next === null) {
          // GLB 变体缺该 clip ⇒ 保持当前态（不抛），只登记一次。
          if (!degradations.some((d) => d.code === 'E_CLIP_MISSING')) {
            degradations.push({ code: 'E_CLIP_MISSING', detail: `GLB 无 clip \`${desired}\` ⇒ 保持当前态` });
          }
        } else if (desired !== activeClip) {
          const current = activeClip === null ? null : actions.get(activeClip) ?? null;
          next.reset().play();
          if (current !== null) current.crossFadeTo(next, CROSSFADE_S, false);
          activeClip = desired;
          crossfadeEndsAtS = mixer.time + CROSSFADE_S;
        }
        // `desired === activeClip` ⇒ **零操作**（不重复 fade）。
      }
      if (mixer !== null) mixer.update(dtMs / 1000);
      // ── FU-003 / W3：`head` 关节的叠加 —— **必须在 `mixer.update()` 之后**。
      // **主路径形态钉死为「读后加」**（`rotation.x = rotation.x + sway`）：赋值形态
      // （`rotation.x = sway`）会抹掉 clip 在 head 上的 x 分量 ⇒ 画面失真**而 AC-4 仍绿**
      // （raven 预审 M-1 / 假绿 ⑤）。three@0.180 的 `rotation`↔`quaternion` 双向同步 + mixer 每帧
      // 把 `head.quaternion` 重写一遍 ⇒ 每帧「读后加一次」**不累积**（帧末 `rotation.x = clipX + sway`，
      // 下一帧被 mixer 覆盖）。
      // r2 / A1（raven M-2）：**上面这条前提**（mixer 每帧重写 `head.quaternion`）在
      // `E_NO_ANIMATIONS`（GLB 无 clip）/ head 不被任何 clip 覆盖时**不成立**，此时「读后加」会
      // **逐帧累积**（raven 实测 120 帧到 0.249837 rad ≈ 14.3°）⇒ 按前提分支：前提成立 ⇒ 与 r1
      // **逐字相同**的「读后加」；不成立 ⇒ 相对**载入期基准姿态** `headBaseX`（在任何 sway 之前
      // 捕获一次）⇒ 有界、不累积（|偏差| ≤ `HEAD_SWAY_RAD`）。
      // 只改关节**局部**变换，**不回写权威**。
      headSwayRad = 0;
      if (headBone !== null) {
        const sway = Math.sin((tickAcc / 1000) * 1.6) * HEAD_SWAY_RAD;
        if (mixer !== null && clipDrivesHead()) {
          headBone.rotation.x = headBone.rotation.x + sway;
        } else {
          headBone.rotation.x = headBaseX + sway;
        }
        headSwayRad = sway;
      }
    },
    animationReport: () => animationReport(),
    report() {
      const boxes = 1 + group.children.length;
      // N5-r2 / A4④：`root_kind` 由**对象自身**派生（`isGroup` / `type`），不再是字面量字符串。
      // r1 的缺陷（raven R-4）：判据比较的是 `report()` 里写死的 `'Group'`，**没有检查对象类型**。
      // 负对照（`/tmp` 副本把 `new THREE.Group()` 换成 `new THREE.Mesh()`）⇒ 这里会读成 `Mesh` ⇒ 判据红。
      const isGroupObject = (group as unknown as { isGroup?: boolean }).isGroup === true;
      const rootKind = isGroupObject || group.type === 'Group' ? 'Group' : String(group.type);
      return {
        entity_id: options.entityId,
        root_kind: rootKind,
        root_kind_derivation: {
          type: String(group.type),
          is_group: isGroupObject,
        },
        root_name: group.name,
        binding_id: binding?.binding_id ?? null,
        glb_url: binding?.glb_url ?? null,
        asset_version: binding?.asset_version ?? null,
        glb_loaded: glbLoaded,
        node_count: group.children.length,
        child_kinds: group.children.map((c) => (c as THREE.Mesh).isMesh ? 'mesh' : 'group'),
        ext_surfaces: [...extSurfaces],
        ext_surface_count: extSurfaces.length,
        binding_set_sha256_stub: null,
        state_clip_map_keys: [...STATE_CLIP_MAP_KEYS],
        frozen_state_ids: [...FROZEN_STATE_IDS],
        slot_weights_daily: slotWeightsForState('daily'),
        slot_weights_masked: slotWeightsForState('masked'),
        slot_sources: SLOT_SOURCES.map((s) => ({ ...s })),
        /** FU-003 / W4：动画读数（**纯加法**；既有字段一字不改）。 */
        animation: animationReport(),
        /** 预留给 `/1000` 的米制换算：Group 的世界缩放恒 1（不得偷偷缩放角色）。 */
        scale: [group.scale.x, group.scale.y, group.scale.z],
        /** 角色实例的放置点由**权威** transform 决定（`presentation.ts` 的 `applyAuthority`）。 */
        local_position_m: [group.position.x, group.position.y, group.position.z],
        mm_per_unit: MM,
        degradations: degradations.map((d) => ({ ...d })),
      };
    },
    dispose() {
      // r2 / MUST-2：先置标志（阻断此后到达的 `onLoad`），既有三行语义**一字不改**。
      disposed = true;
      group.clear();
      gltfScene = null;
      glbLoaded = false;
      // ── FU-003 / W1（AC-9）：停住 mixer 并释放引用 ⇒ 之后逐帧不再驱动骨骼动画、
      // `mixer_time_s` 不再增长、`active_clip === null`（三条件须**同时**成立）。
      // `headBone` 引用保留（不再被写：`update()` 因 `gltfScene === null` 首行短路）⇒
      // AC-9 的「逐帧 head 本地旋转恒定」读的是**真对象**，不是被抹成 0 的读数。
      mixer?.stopAllAction();
      // r2 / A3（raven M-5）：**有区分力的读数** —— 直接问 action 自己「还跑着吗」。
      // 上面三条既有条件全部由 `gltfScene = null` 的首行短路保证 ⇒ 删掉上一行 `stopAllAction()`
      // 它们**仍全过**（raven 实测，见 05 §6 M-5）；本行是唯一会因此转红的读数。
      // `mixer === null`（无 mixer / 已 dispose）⇒ `false`，不用空集造「没有东西可停」的假绿。
      mixerStopped = mixer !== null && [...actions.values()].every((action) => !action.isRunning());
      mixer = null;
      actions.clear();
      activeClip = null;
      headSwayRad = 0;
    },
  };
}

/** 供判据使用的绑定表只读视图（`AC-E-2d` 的取数面）。 */
export function bindingTableLines(): string[] {
  return BINDINGS.map((b) => `${b.binding_id}:${b.glb_url}:${b.asset_version}`).sort();
}

/** 该绑定使用的扩展表面是否都真在 `SURFACES_EXT` 里（`AC-I-3g` 的前置）。 */
export function extSurfacesResolvable(bindingId: string): boolean {
  const b = BINDINGS.find((x) => x.binding_id === bindingId);
  if (!b) return false;
  return b.ext_surfaces.every((id) => Boolean(SURFACES_EXT[id as ExtSurfaceId]));
}
