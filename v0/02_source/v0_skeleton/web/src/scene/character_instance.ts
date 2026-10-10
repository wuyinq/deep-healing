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
 *   ⚠️ **动画未接线 + 骨骼驱动实际为零（GAP）**：全仓**无** `AnimationMixer` / `clipAction`（实测零命中）⇒
 *   上述两条 clip **从未被播放**。全仓对**骨骼节点**的写入仅 `update()` 内一处，而它对 `node.name === 'Head'`
 *   做**大小写敏感**的严格相等比较；本轮 GLB 的 26 个关节名**全是小写蛇形**、头部关节名叫 **`head`**
 *   （**不存在**名为 `Head` 的节点；全仓也无任何把节点重命名为 `Head` 的赋值）⇒ 该判断**恒不命中**、
 *   `Head.rotation.x` **从未被写过** ⇒ **五个槽位的骨骼驱动实际为零**（连「部分实现」都不存在）。
 *   实测读数见 `evidence/artisan/r2/f1-joint-names.json`（关节名清单 + 比较式 + 重命名面）。
 *   凡本表声称「已播放 / 已混合 / 正在驱动骨骼」即为失实。`speak` / `listen` 无对应 GLB clip；
 *   `idle` / `turn` 的骨骼级驱动**未实现** —— 一并记为
 *   **GAP（动画未接线 + 骨骼写入空转 + 部分槽位无 clip）**并上抛，见任务书 §6 与 03 日志。
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
  { slot: 'idle', kind: 'procedural', detail: '**未接线**：计划中的脊柱/肩/头低频呼吸摆尚未实现 —— 全仓唯一的骨骼写入在 `update()`，但它比的是字符串 `Head`（大写 H，比较为严格相等、大小写敏感）、本轮 GLB 头部关节名是小写 `head` ⇒ **该写入恒不命中、实际驱动为零**；无 Spine / Shoulder 驱动（全仓无 AnimationMixer）⇒ GAP' },
  { slot: 'walk', kind: 'clip', detail: 'GLB animation[1]（Walk，78 channels；下标与通道数按重测 GLB，见 evidence/artisan/ac2-new-asset.json）—— **未接线**：全仓无 AnimationMixer ⇒ 从未播放 ⇒ GAP' },
  { slot: 'turn', kind: 'procedural', detail: '根 yaw 由**权威位移方向**驱动（presentation.ts 死区 + 限速 ⇒ world.ts 写 group.rotation.y）；**未接线**：不存在任何 clip 的降速混合（全仓无 AnimationMixer）⇒ GAP' },
  { slot: 'speak', kind: 'procedural', detail: '**未接线**：计划中的 Head 点头 + 双臂小幅开合尚未实现（无对应 GLB clip，且无 animation 播放路径）⇒ GAP' },
  { slot: 'listen', kind: 'procedural', detail: '**未接线**：计划中的 Head 侧倾 + 躯干微前倾尚未实现（无对应 GLB clip，且无 animation 播放路径）⇒ GAP' },
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
