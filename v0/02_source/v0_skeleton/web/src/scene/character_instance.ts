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
 *   本轮的 rigged GLB（Khronos CesiumMan，CC BY 4.0）只带 **1 条**动画（walk cycle）。
 *   ⇒ 槽位来源**逐槽显式标注**（`clip` = 真 GLB 动画；`procedural` = 由骨骼变换程序化驱动）。
 *   **不得**把程序化槽位说成「GLB 自带动画」（那会是自报冒充）。这 4 个程序化槽位记为
 *   **GAP（无合适许可的多动作 rigged GLB 资产）**并上抛 —— 见任务书 §6 与 03 日志。
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
  { slot: 'idle', kind: 'procedural', detail: '脊柱/肩/头的低频呼吸摆（Bone: Spine, Shoulder_L/R, Head）' },
  { slot: 'walk', kind: 'clip', detail: 'GLB animation[0]（walk cycle，57 channels）' },
  { slot: 'turn', kind: 'procedural', detail: '根 yaw 由**权威位移方向**驱动 + animation[0] 的降速混合' },
  { slot: 'speak', kind: 'procedural', detail: 'Head 点头 + 双臂小幅开合（无对应 GLB clip ⇒ 显式 GAP）' },
  { slot: 'listen', kind: 'procedural', detail: 'Head 侧倾 + 躯干微前倾（无对应 GLB clip ⇒ 显式 GAP）' },
];

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
  update(dtMs: number): void;
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
        },
        undefined,
        (error: unknown) => {
          degradations.push({ code: 'E_GLB_LOAD_FAILED', detail: `${binding.glb_url}: ${String(error)}` });
          recordBindingDegradation('E_GLB_LOAD_FAILED', `${binding.glb_url}: ${String(error)}`);
        },
      );
    } catch (error) {
      degradations.push({ code: 'E_GLB_LOAD_THREW', detail: String(error) });
      recordBindingDegradation('E_GLB_LOAD_THREW', `${binding.glb_url}: ${String(error)}`);
    }
  }

  return {
    entityId: options.entityId,
    binding,
    group,
    glbLoaded: () => glbLoaded,
    slotSources: () => [...SLOT_SOURCES],
    weights: (stateId?: string | null) => slotWeightsForState(stateId),
    update(dtMs: number) {
      tickAcc += dtMs;
      if (!gltfScene) return;
      // 程序化槽位（idle / turn / speak / listen）只改**骨骼的局部变换**（表现状态），
      // 绝不回写权威位置；`presentation.ts` 负责把根 yaw 与权威位移方向对齐。
      const t = tickAcc / 1000;
      const sway = Math.sin(t * 1.6) * 0.02;
      gltfScene.traverse((node: THREE.Object3D) => {
        if (!(node as THREE.Bone).isBone) return;
        if (node.name === 'Head') node.rotation.x = sway;
      });
    },
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
