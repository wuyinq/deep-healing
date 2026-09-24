/**
 * 场景装配（L1）——M3 真实现。
 *
 * **同一几何两态**（ADR-016 / D-7）：几何只由下发状态（`snapshot.state.entities`）决定，
 * 与「读法」（表层 / 深层）**无关**。读法只改光照与材质亮度（`lighting.ts`）。
 * ⇒ 顶点数（`position.count`）、**形状指纹**与实体 id 集合在两态下**逐项相同**。
 *
 * R3 / G2（Raven r2 R2-C1 的封堵）：判据量必须是**真的形状指纹**，不是顶点数。
 * `BoxGeometry(w,h,d)` 的 `position.count` **恒为 24**，与尺寸无关 ⇒ 只用顶点数的判据
 * 对「深层态换一套尺寸」不可见。现在的指纹 = 每实体 `size` + `geometry.parameters` +
 * **position attribute 浮点序列的确定性摘要**（微米级量化后 FNV-1a 64）⇒ 尺寸/顶点任一变化必变。
 *
 * R4 / R3-C1（PM 裁决的**有界补丁轮**，判据层）：R3 的判据仍**名不副实** —— 名字声称覆盖
 * 「渲染后几何」，实际只覆盖 `geometry.parameters` + `position` attribute + 装配后 `mesh.position`。
 * 于是「只作用于 `underneath` 读法」的三类注入**逃逸**（PM 独立复现）：
 *   - `mesh.scale.set(3,3,3)`     ⇒ 缩放不在比较面内；
 *   - `mesh.rotation.y = π/2`     ⇒ 旋转不在比较面内；
 *   - `camera.position.set(40,40,40)`（D-7 明文禁止「换相机」）⇒ **零判据**。
 * 加宽（**最小、语义不变**）：装配变换（`scale` 三分量 + `quaternion` 四分量）进**形状指纹**与
 * `geometry_digest`；`assemblyReport()` 从 mesh **读回** `mesh.scale` / `mesh.quaternion` 并暴露
 * `mesh_scales` / `mesh_rotations`；另增 `cameraReport()`（**从 `THREE.Camera` 实例读回**，
 * 不读实现源文本、不硬编码字面量）供 `two_reads_share_camera` 断言。
 *
 * 同时暴露**两条取数路径**，判据必须**都**跑：
 *   - `geometryFor(reading)`：装配函数的产物（纯函数路径）；
 *   - `assemblyReport()`：从**场景图的 mesh 层读回**（装配**之后**有没有再被改写，只有它能看见）。
 * 二者都经 `createScene()` 的句柄取数 ⇒ 判据不再只打自由函数。
 *
 * R3 / G1（Sentinel r2 CRITICAL 的封堵）：`createScene` 自己负责**画布尺寸跟随视口**
 * （`renderer.setSize(clientWidth, clientHeight, false)` + `ResizeObserver`/`resize` + DPR），
 * 并把 `camera.aspect` 同步 —— 此前全树无 `setSize`/`resize`，绘制缓冲停在默认 300×150。
 *
 * 只消费 snapshot/delta 的**世界状态**；人物**外形**来自内容包**只读 GET**（装配配置），
 * 失败退回**确定性通用人形**，**不伪造**具体人物特征。
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * **模块边界改写（N2 / D1，2026-09-24；替换原句「不得直读内容包文件」）**
 *
 * 原边界：实体与组件**只**来自下发状态，不得直读内容包文件。
 * 新边界（**更精确的措辞，不是放宽**）：
 *   - 世界**状态**（位置 / 需求 / 情绪 / 日程 / 关系 / 创伤标记 / tags）**只**消费
 *     snapshot/delta —— 一字未改；
 *   - 人物**外形**（瞳色 / 唇色 / 肤色 / 发色 / 衣色 / 面具）来自内容包
 *     `npcs/*.json` 的 `appearance` 块，经**只读 GET** 取得（沿用 `main.ts`
 *     `loadNpcDisplayName()` 的同一 URL 约定），作为**装配配置**使用；
 *   - 取不到 / 结构不合法 ⇒ 退回**确定性通用人形**（`character.ts` 的
 *     `defaultAppearanceFor()`，全字段 `design_fill`），**不伪造**任何具体人物特征；
 *   - 为什么不能随 state 下发：`world.schema.json` 的 `$defs/entity` 是
 *     `additionalProperties:false` ⇒ 加外形字段属**契约变更**（本轮非目标）。
 *
 * **确定性契约不变**：外形与读法**无关** —— 读法只改光照与材质亮度；部件表的
 * `source_hex`（来自装配配置）在两读法下逐项相同，只有**信息性**的 `material_hex`
 * （`mesh.material.color.getHexString()` 读回）随读法变。装配路径**零**
 * `Math.random` / `Date.now`。
 * ─────────────────────────────────────────────────────────────────────────────
 * **N2-r2 / F-1：取证机位（加法、可选、spike 专用）**
 *
 * 背景（门禁第 1 轮 CRITICAL）：徐琴（`npc-006`）位于世界 `(5.0, 0, 15.0)` m，
 * 与 `room-1052`（`sizeFor('room')=[5,3,5]`）**同点** ⇒ 严格落在该**不透明盒体内部**；
 * 默认相机 `(18,14,24) lookAt(9,0,6)` 在盒外 ⇒ 玩家在**默认取景**下看到的是**盒子**。
 *
 * 本模块因此新增 `setObservationCamera(view | null)`：把相机放到一个**世界里真实存在的
 * 室内视点**（`room-1052` 体块内部）取景。**这不是隐藏遮挡物**：房间内侧背面由 three 的
 * 默认 `FrontSide` 自然被剔除，`room` 盒的 `visible` / 材质 / 几何**一字未改**。
 *
 * **默认行为一字不变**：不调用它 ⇒ 相机与起点**逐项相同**（`DEFAULT_CAMERA_POSITION` /
 * `DEFAULT_CAMERA_LOOK_AT` 就是起点冻结值）；`setObservationCamera(null)` 恢复同一取景。
 * D-7 的相机判据面（`two_reads_share_camera` / `two_reads_use_same_render_camera` /
 * `scene_handle_camera_report_is_live`）**不受影响**（本 API 只改相机，不改几何/部件/读法）。
 * 默认取景下人物不可见属**已知缺陷**（已登记，交 N4）。
 * ─────────────────────────────────────────────────────────────────────────────
 */

import * as THREE from 'three';
import { applyHealingLighting, healingMaterial, type Reading, type Tone } from './lighting.ts';
import {
  buildCharacterParts, resolveAppearanceTable, resolveMaskDegradation, stateIdFor,
  type CharacterAppearance, type CharacterPart,
} from './character.ts';

export interface EntityBox {
  id: string;
  kind: string;
  position: [number, number, number];
  size: [number, number, number];
  /** R4 / R3-C1：装配时**打算**写入 mesh 的缩放（默认 `[1,1,1]`）。 */
  scale: [number, number, number];
  /** R4 / R3-C1：装配时**打算**写入 mesh 的旋转（四元数，默认 `[0,0,0,1]`）。 */
  quaternion: [number, number, number, number];
  geometry: THREE.BoxGeometry;
  /**
   * N2：**人物实体**的根 box = 躯干。其余部件经 `characterReport()` 暴露 ——
   * `buildEntityBoxes()` 仍保持「**每实体 1 个 box**」（R-06 钉死）。
   * `source_hex` 来自装配配置（包内 hex），**读法无关**。
   */
  source_hex?: string;
  /** N2：该 box 是否为人物实体的**根**（躯干）。 */
  character_root?: boolean;
  /** N2：该实体本帧的形态 id（`daily` / `masked`；仅人物实体）。 */
  state_id?: string;
}

export interface SceneStateEntity {
  id: string;
  kind: string;
  transform?: { pos_mm?: { x: number; y: number; z: number }; room_id?: string | null };
  /** N2：只**读**（形态谓词用）；外形**不**从这里来。 */
  schedule?: { state?: string | null; target_entity?: string | null };
  tags?: string[];
}

export interface SceneState {
  entities?: SceneStateEntity[];
}

/** N2：人物外形的**装配配置**（内容包只读 GET 的产物；`null` ⇒ 全部退回确定性通用人形）。 */
export interface SceneAssemblyOptions {
  appearance?: Map<string, CharacterAppearance> | null;
}

const MM = 1000; // 毫米 → 米（渲染单位）

/**
 * N2-r2 / F-1：**交付面默认取景**（= 起点冻结值，逐字节来自 r1 交付树）。
 * 默认行为一字不变：不调用 `setObservationCamera` ⇒ 相机就是这两个值。
 */
export const DEFAULT_CAMERA_POSITION: [number, number, number] = [18, 14, 24];
export const DEFAULT_CAMERA_LOOK_AT: [number, number, number] = [9, 0, 6];

/**
 * N2-r2 / F-1：**取证机位**入参（米制世界坐标）。`null` ⇒ 恢复默认取景。
 * 这是**世界里真实存在的视点**（室内视角），**不是**「隐藏遮挡物后拍照」的开关 ——
 * 本模块不提供任何改 `visible` / 材质 / 几何的入口。
 */
export interface ObservationCameraView {
  position_m: [number, number, number];
  look_at_m: [number, number, number];
}

/** R4 / R3-C1：默认装配变换 —— 两态都必须用它（语义不变：单位缩放 + 单位旋转）。 */
const DEFAULT_SCALE: [number, number, number] = [1, 1, 1];
const DEFAULT_QUATERNION: [number, number, number, number] = [0, 0, 0, 1];

/** 浮点读数统一到 6 位小数（消除尾差噪声，同时保留任何真实变换差异）。 */
const q6 = (value: number): string => value.toFixed(6);

/** 数值型 6 位收敛（与 `q6` 同一口径；用于可逐项比较的数值读数）。 */
const round6 = (value: number): number => Math.round(value * 1e6) / 1e6;

/** R5：矩阵 16 分量逐项（量化 `1e-6`）—— 消除浮点尾差噪声，同时保留任何真实变换差异。 */
function quantizeMatrix(matrix: THREE.Matrix4): number[] {
  return matrix.elements.map((value) => Math.round(Number(value) * 1e6));
}

/** R5：几何结构面**至少**必须给出的 attribute（缺失时显式记 `null`，不得跳过字段）。 */
const STRUCTURE_ATTRIBUTES: readonly string[] = ['position', 'normal', 'uv'];

/**
 * **读法 → 几何装配配置**（D-7 / ADR-016）。
 *
 * 这是 `scene_assert.mjs` 的**靶子**：几何装配路径**真的**接收读法（读法参数一路传到
 * `buildEntityBoxes`），而 D-7 要求几何**只由下发状态决定** ⇒ 本表两项**必须逐字段相等**。
 * 一旦某个读法被改成「第二套坐标 / 第二张地图」，两条独立装配就会分叉，
 * `two_reads_share_geometry` 必须红（R1 的恒真假绿即由此封堵）。
 */
export interface ReadingGeometryProfile {
  /** 该读法带来的装配偏移（毫米）；两读法当前**必须都是 0**。 */
  y_offset_mm: number;
  /** 该读法要丢掉的实体 kind（`null` = 不丢）；两读法当前**必须都是 `null`**。 */
  drop_kind: string | null;
}

export const READING_GEOMETRY_PROFILE: Record<Reading, ReadingGeometryProfile> = {
  surface: { y_offset_mm: 0, drop_kind: null },
  underneath: { y_offset_mm: 0, drop_kind: null },
};

export function readingGeometryProfile(reading: Reading): ReadingGeometryProfile {
  return READING_GEOMETRY_PROFILE[reading];
}

function sizeFor(kind: string): [number, number, number] {
  switch (kind) {
    case 'npc': return [0.8, 1.7, 0.8];
    case 'room': return [5, 3, 5];
    case 'prop': return [1.6, 0.6, 0.6];
    case 'portal': return [2, 3, 0.4];
    default: return [4, 0.4, 4];
  }
}

// ------------------------------------------------------------------ 形状指纹（R3 / G2）
const FNV64_OFFSET = 0xcbf29ce484222325n;
const FNV64_PRIME = 0x100000001b3n;
const U64_MASK = 0xffffffffffffffffn;

/**
 * `position` attribute 的**确定性形状摘要**（16 hex）。
 *
 * 为什么不是「顶点数」：`BoxGeometry` 的位置顶点数与尺寸**无关**（恒 24）⇒ 顶点数不是形状指纹。
 * 本摘要把每个浮点按**微米级量化**（`round(x * 1e6)`）后逐字节做 FNV-1a 64 ⇒ 消除浮点尾差噪声，
 * 同时对任何真实的坐标/尺寸变化敏感。确定性：同输入 ⇒ 同输出（无时间、无随机、无迭代顺序依赖）。
 */
export function digestPositions(values: ArrayLike<number>): string {
  let hash = FNV64_OFFSET;
  for (let index = 0; index < values.length; index += 1) {
    const quantized = Math.round(Number(values[index]) * 1e6);
    for (let shift = 0; shift < 32; shift += 8) {
      hash = ((hash ^ BigInt((quantized >> shift) & 0xff)) * FNV64_PRIME) & U64_MASK;
    }
  }
  return hash.toString(16).padStart(16, '0');
}

export interface EntityShape {
  id: string;
  /** 装配用的尺寸（米）；**尺寸必须进指纹**（顶点数对尺寸不敏感）。 */
  size: [number, number, number];
  /** R4 / R3-C1：装配变换的缩放分量；**必须进指纹**（此前 `scale` 注入可逃逸）。 */
  scale: [number, number, number];
  /** R4 / R3-C1：装配变换的旋转分量（四元数）；**必须进指纹**（此前 `rotation` 注入可逃逸）。 */
  quaternion: [number, number, number, number];
  /** `BoxGeometry.parameters`（width/height/depth + 分段数）。 */
  parameters: Record<string, number>;
  /** `position` attribute 的确定性摘要。 */
  position_attribute_digest: string;
  vertex_count: number;
}

function shapeOf(id: string, geometry: THREE.BoxGeometry, size: [number, number, number],
                 scale: [number, number, number], quaternion: [number, number, number, number]): EntityShape {
  const attribute = geometry.getAttribute('position');
  return {
    id,
    size: [size[0], size[1], size[2]],
    scale: [scale[0], scale[1], scale[2]],
    quaternion: [quaternion[0], quaternion[1], quaternion[2], quaternion[3]],
    parameters: { ...(geometry.parameters as unknown as Record<string, number>) },
    position_attribute_digest: digestPositions(attribute.array as unknown as ArrayLike<number>),
    vertex_count: attribute.count,
  };
}

function shapeDigestString(shape: EntityShape): string {
  return `${shape.id}:${shape.size.join(',')}`
    + `:s=${shape.scale.map(q6).join(',')}`
    + `:q=${shape.quaternion.map(q6).join(',')}`
    + `:${JSON.stringify(shape.parameters)}:${shape.position_attribute_digest}`;
}

/**
 * N2：人物实体的**部件表**（装配函数的产物；读法**无关** ⇒ 两读法逐项相同）。
 * 顺序 = 实体 id 字典序 × `CHARACTER_PART_ORDER`（确定性，无遍历顺序依赖）。
 */
export function buildCharacterPartsForState(
  state: SceneState | undefined,
  options: SceneAssemblyOptions = {},
): CharacterPart[] {
  const entities = [...(state?.entities ?? [])]
    .filter((entity) => entity.kind === 'npc')
    .sort((left, right) => left.id.localeCompare(right.id));
  const parts: CharacterPart[] = [];
  for (const entity of entities) {
    parts.push(...buildCharacterParts(
      options.appearance?.get(entity.id) ?? null,
      { entityId: entity.id, state: entity },
    ));
  }
  return parts;
}

/**
 * **几何的唯一装配点**：只读 `state` + 读法的装配配置（当前两项配置等价 ⇒ 两读法同几何）。
 * 读法**不能**引入第二套几何：它的唯一作用点就是 `READING_GEOMETRY_PROFILE`，
 * 而该表被 `scene_assert.mjs` 用「两次独立装配」直接比较。
 *
 * N2（R-06 钉死）：`kind === 'npc'` 的实体仍只有**一个** box，且它就是人形的**根 mesh = 躯干**
 * （尺寸 / 色值来自 `character.ts` 的装配器）⇒ `entity_count` 与「每实体 1 box」的语义
 * **零改动**；其余部件**只**经 `characterReport()` / `character_shapes` 暴露。
 */
export function buildEntityBoxes(
  state: SceneState | undefined,
  reading: Reading = 'surface',
  options: SceneAssemblyOptions = {},
): EntityBox[] {
  const profile = readingGeometryProfile(reading);
  const entities = [...(state?.entities ?? [])]
    .filter((entity) => entity.kind !== profile.drop_kind)
    .sort((left, right) => left.id.localeCompare(right.id));
  return entities.map((entity) => {
    const pos = entity.transform?.pos_mm ?? { x: 0, y: 0, z: 0 };
    const position = [pos.x / MM, (pos.y + profile.y_offset_mm) / MM, pos.z / MM] as [number, number, number];
    const scale = [DEFAULT_SCALE[0], DEFAULT_SCALE[1], DEFAULT_SCALE[2]] as [number, number, number];
    const quaternion = [DEFAULT_QUATERNION[0], DEFAULT_QUATERNION[1], DEFAULT_QUATERNION[2],
      DEFAULT_QUATERNION[3]] as [number, number, number, number];
    const appearance = entity.kind === 'npc' ? (options.appearance?.get(entity.id) ?? null) : null;
    if (entity.kind === 'npc') {
      const characterParts = buildCharacterParts(appearance, { entityId: entity.id, state: entity });
      const root = characterParts.find((part) => part.is_root) ?? characterParts[0];
      const size = (root?.size ?? sizeFor(entity.kind)) as [number, number, number];
      return {
        id: entity.id,
        kind: entity.kind,
        position,
        size,
        scale,
        quaternion,
        geometry: new THREE.BoxGeometry(size[0], size[1], size[2]),
        source_hex: root?.source_hex,
        character_root: true,
        state_id: stateIdFor(appearance, { entityId: entity.id, state: entity }),
      };
    }
    const size = sizeFor(entity.kind);
    return {
      id: entity.id,
      kind: entity.kind,
      position,
      size,
      scale,
      quaternion,
      geometry: new THREE.BoxGeometry(size[0], size[1], size[2]),
    };
  });
}

/** N2：部件级**装配函数产物**（与 `characterReport()` 的 mesh 层读回逐项可比）。 */
export interface CharacterShape extends EntityShape {
  /** 部件名（固定字段名表）。 */
  part: string;
  is_root: boolean;
  /** 相对根 mesh 的局部偏移（装配时**打算**写入的值）。 */
  local_offset: [number, number, number];
  /** 来自装配配置的包内 hex（读法无关）。 */
  source_hex: string;
}

export interface GeometryReport {
  /** **实际参与装配的读法**（证明读法真被接收，而不是被静默丢弃）。 */
  reading: Reading;
  entity_count: number;
  entity_ids: string[];
  vertex_count_total: number;
  vertex_counts: Record<string, number>;
  /** 每实体的**形状指纹**（尺寸 + 装配变换 + parameters + position attribute 摘要）。 */
  shapes: EntityShape[];
  /** 每实体的指纹摘要串（便于逐项比较）。 */
  shape_digests: Record<string, string>;
  /** 几何指纹：两态必须逐项相同（含坐标 + 形状指纹；不含任何读法相关量）。 */
  geometry_digest: string;
  /** 该读法所用的装配配置指纹（两读法必须相同）。 */
  profile_digest: string;
  /**
   * N2（AC-3 的「可复算」）：**人物部件**的形状指纹 —— 由**装配函数**（`character.ts` 的
   * `buildCharacterParts()`）算出，与 `characterReport()`（**mesh 层读回**）逐项比对。
   * 这是**第二条独立取数路径**，不是「同一入参算两遍」。
   * 注意：`shapes` 保持**实体级**（R-06：每实体 1 个 box）⇒ 部件级读数放在本字段，
   * 不改既有 `shapes` / `shape_digests` / `geometry_digest` 的语义。
   */
  character_shapes: CharacterShape[];
}

/** 机器判据（`scene_assert.mjs` 消费）：形状指纹 + 实体 id 集合 + 坐标 + 顶点数。 */
export function geometryReport(
  state: SceneState | undefined,
  reading: Reading = 'surface',
  options: SceneAssemblyOptions = {},
): GeometryReport {
  const boxes = buildEntityBoxes(state, reading, options);
  const vertexCounts: Record<string, number> = {};
  const shapeDigests: Record<string, string> = {};
  const shapes: EntityShape[] = [];
  let total = 0;
  const parts: string[] = [];
  for (const box of boxes) {
    const shape = shapeOf(box.id, box.geometry, box.size, box.scale, box.quaternion);
    shapes.push(shape);
    shapeDigests[box.id] = shapeDigestString(shape);
    vertexCounts[box.id] = shape.vertex_count;
    total += shape.vertex_count;
    parts.push(`${box.id}:${box.vertex_count}:${box.position.join(',')}:${shapeDigestString(shape)}`);
  }
  // N2：部件级读数 —— 与装配同源（同一条 `character.ts` 纯函数路径），读法无关。
  const characterShapes: CharacterShape[] = buildCharacterPartsForState(state, options).map((part) => {
    const geometry = new THREE.BoxGeometry(part.size[0], part.size[1], part.size[2]);
    const shape = shapeOf(part.name, geometry, part.size, DEFAULT_SCALE, DEFAULT_QUATERNION);
    return {
      ...shape,
      part: part.part,
      is_root: part.is_root,
      // r5 / Raven M5：**口径统一** —— 根部件（躯干）的 `local_offset` 恒取「相对人物放置点」= [0,0,0]，
      // 与 mesh 读回侧（`characterReport()`：`mesh.position − character_placement`）**同一口径**。
      // 此前直接透传 `PART_TABLE.offset`，与读回侧相等**仅因** `torso.offset` 恰为 [0,0,0]；
      // 一旦有人**合法地**把 `torso.offset` 设为非 0，两侧口径不同 ⇒ 断言**假红**。
      local_offset: part.is_root
        ? [0, 0, 0]
        : [part.local_offset[0], part.local_offset[1], part.local_offset[2]],
      source_hex: part.source_hex,
    };
  });
  return {
    reading,
    entity_count: boxes.length,
    entity_ids: boxes.map((box) => box.id),
    vertex_count_total: total,
    vertex_counts: vertexCounts,
    shapes,
    shape_digests: shapeDigests,
    geometry_digest: parts.join('|'),
    profile_digest: JSON.stringify(readingGeometryProfile(reading)),
    character_shapes: characterShapes,
  };
}

/** 从**场景图 mesh 层**读回的装配读数（R3 / G2③c：装配之后是否又被改写）。 */
export interface AssemblyReport {
  reading: Reading;
  entity_ids: string[];
  shape_digests: Record<string, string>;
  /** mesh 的世界坐标（装配后写入的那一份）。 */
  mesh_positions: Record<string, string>;
  /** R4 / R3-C1：从 mesh 读回的**缩放**（逐项可比较；此前不在比较面内 ⇒ 可逃逸）。 */
  mesh_scales: Record<string, string>;
  /** R4 / R3-C1：从 mesh 读回的**旋转四元数**（逐项可比较；此前不在比较面内 ⇒ 可逃逸）。 */
  mesh_rotations: Record<string, string>;
  geometry_digest: string;
  mesh_count: number;
}

/** 画布/绘制缓冲读数（R3 / G1①：必须随视口变化）。 */
export interface ViewportReport {
  client_width: number;
  client_height: number;
  drawing_buffer_width: number;
  drawing_buffer_height: number;
  pixel_ratio: number;
  aspect: number;
  webgl: boolean;
}

/**
 * 相机读数（R4 / R3-C1；**R5 / 闭式化扩面**）：D-7「**禁止换相机**」的机器读数。
 * 一律**从 `THREE.Camera` 实例读回**（不读实现源文本、不硬编码字面量）。
 * R5 扩面（PM 裁决 `R4-C1`：`zoom` / 手改 `projectionMatrix` / `setViewOffset` 曾可逃逸）：
 * `matrixWorld` / `projectionMatrix`（各 16 分量逐项）/ `zoom` / `view_offset`（含 `enabled`）/
 * `fov` / `near` / `far`。
 * `aspect` 是**视口派生量** ⇒ 作为**信息性**读数（是否参与相等断言由 `scene_assert.mjs` 决定并在 `06` 声明）。
 */
export interface CameraReport {
  position: [number, number, number];
  quaternion: [number, number, number, number];
  /** `matrixWorld` 16 分量逐项（量化 `1e-6`）。 */
  matrix_world: number[];
  /** `projectionMatrix` 16 分量逐项（量化 `1e-6`）。 */
  projection_matrix: number[];
  zoom: number;
  /** three 0.180：`PerspectiveCamera.view`（旧名 `viewOffset`）；未设置 ⇒ 显式 `null`。 */
  view_offset: ViewOffsetReport | null;
  fov: number;
  near: number;
  far: number;
  aspect: number;
}

/** R5：`setViewOffset()` 读数（`enabled` 显式给出；未设置由 `CameraReport.view_offset = null` 表达）。 */
export interface ViewOffsetReport {
  enabled: boolean;
  full_width: number;
  full_height: number;
  offset_x: number;
  offset_y: number;
  width: number;
  height: number;
}

/**
 * R5 / **闭式面**：几何结构摘要（`index` / `groups` / 每个 attribute）。
 * 明确**不含**光照 / 材质色相明度 —— 两态**按设计**必须不同（见 `06` R5 段的「不覆盖」清单）。
 */
export interface AttributeStructure {
  name: string;
  item_size: number;
  count: number;
  digest: string;
}

/** `geometry.index` 摘要；无 index ⇒ `{present:false, count:null, digest:null}`（**显式**，不得省略字段）。 */
export interface IndexStructure {
  present: boolean;
  count: number | null;
  digest: string | null;
}

export interface GeometryStructure {
  index: IndexStructure;
  /** 逐组 `start` / `count` / `materialIndex`。 */
  groups: Array<{ start: number; count: number; materialIndex: number }>;
  groups_digest: string;
  /** 每个 attribute 的 `{name,itemSize,count,digest}`；缺失者（含 `position`/`normal`/`uv`）显式 `null`。 */
  attributes: Record<string, AttributeStructure | null>;
  /** 整个几何结构面的摘要（index + groups + attributes）。 */
  digest: string;
}

/** R5 / **闭式面**：对象结构摘要（根子树逐对象）。 */
export interface ObjectStructure {
  /** **稳定身份**：优先 `name`（mesh = 实体 id；根 = `world-root`），无名字时用 `类型#序号`。 */
  id: string;
  parent_id: string | null;
  type: string;
  /** `matrixWorld` 16 分量逐项（量化 `1e-6`）—— 同时覆盖根变换 / 父级 Group / `matrixAutoUpdate`。 */
  matrix_world: number[];
  visible: boolean;
  layers_mask: number;
  render_order: number;
}

/**
 * R5 / **闭式面**：结构性场景状态摘要（几何结构 + 对象结构）。
 * 口径 = **遍历式摘要**（不是逐字段白名单）⇒ 新增结构性字段会被自动捕获。
 */
export interface StructureReport {
  reading: Reading;
  /** 每实体 id → 几何结构摘要。 */
  geometry: Record<string, GeometryStructure>;
  geometry_digest: string;
  /** 场景**根子树**的对象身份与父子关系（DFS 有序）。 */
  objects: ObjectStructure[];
  objects_digest: string;
}

/**
 * R5 / D-7 的**字面形态**：**实际用于渲染的相机身份** —— `renderer.render(scene, camera)` 的**入参**读数。
 * `identity` = 渲染时真正传入的那个相机（`类型#uuid`）⇒「第二相机」形态由此有牙。
 */
export interface RenderCameraReport {
  identity: string | null;
  renders: number;
  reading: Reading | null;
}

interface RendererLike {
  setPixelRatio(value: number): void;
  setSize(width: number, height: number, updateStyle?: boolean): void;
  render(scene: THREE.Scene, camera: THREE.Camera): void;
  dispose(): void;
}

/**
 * 建渲染器（R3 / G1 的 headless 容忍）：无 WebGL 上下文时退化为**空渲染器**。
 * 只有光栅化不可用 —— **几何与场景图照常装配**，因此 `scene_assert` 的装配判据跑的
 * 是同一条装配路径（不是「为绿放宽判据」：被断言的量一个都没变）。
 */
function createRenderer(canvas: HTMLCanvasElement): { renderer: RendererLike; webgl: boolean } {
  try {
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    return { renderer: renderer as unknown as RendererLike, webgl: true };
  } catch {
    return { renderer: { setPixelRatio() {}, setSize() {}, render() {}, dispose() {} }, webgl: false };
  }
}

/**
 * N2：**部件读数**（从场景图的部件 mesh 层**读回**）。
 *
 * 颜色**拆两个字段**（R-01 / R-08 钉死）：
 *   - `source_hex`：来自**装配配置**（包内 hex）⇒ **读法无关**，**进**两读法比较面；
 *   - `material_hex`：`mesh.material.color.getHexString()` **读回** ⇒ 随读法变
 *     （`luminanceScale`），**仅信息性**、**不进任何相等断言**。
 * 实测（主包 tone）：`#8b1919` → surface `791414` / underneath `580c0c`，**都不等于** `8b1919`
 * ⇒ 禁止写「读回值 == 包内 hex」这类断言。
 */
export interface CharacterPartReport {
  entity_id: string;
  /** 部件名（固定字段名表，**不是**下标）。 */
  part: string;
  /** 场景图对象名：根 mesh = 实体 id；其余 = `"<实体 id>/<部件名>"`。 */
  name: string;
  is_root: boolean;
  /** `geometry.parameters`（从 mesh 读回）。 */
  parameters: Record<string, number>;
  size: [number, number, number];
  /** 相对根 mesh 的局部偏移（从 `mesh.position` 读回；父级变换不计入）。 */
  local_offset: [number, number, number];
  position_attribute_digest: string;
  vertex_count: number;
  /** **读法无关**（装配配置里的包内 hex）。 */
  source_hex: string;
  /** **信息性**：材质色的读回值（随读法变，不进相等断言）。 */
  material_hex: string;
}

/** N2：逐实体外形读数（含装配配置的**来源**）。 */
export interface AppearanceEntityReport {
  entity_id: string;
  /** 该实体本帧的形态 id（`daily` / `masked`）。 */
  state_id: string;
  /**
   * R-05：装配配置的来源 —— `'pack'` = 宿主传入 / 从内容包只读 GET 取到的**真**外形；
   * `'fallback'` = 退回确定性通用人形（**不得**把 fallback 读成「人物可辨识」）。
   */
  source: 'pack' | 'fallback';
  /**
   * N2-r2 / F-3：**显式降级告警**（结构化；无降级 ⇒ 空数组）。
   * 当前唯一形态：`E_MASK_DATA_MISSING`（`states[].mask=true` 而 `appearance.mask` 缺失
   * ⇒ 生效形态显式回落到 `daily`，**不**渲染无面具的「面具态」、**不**抛异常）。
   */
  degradations: Array<{ code: string; detail: string; requested_state_id: string }>;
  parts: CharacterPartReport[];
}

export interface SceneHandle {
  apply(message: { t: string; tick: number; state?: SceneState; ops?: unknown[] }): void;
  setReading(reading: Reading): void;
  reading(): Reading;
  entityIds(): string[];
  geometry(): GeometryReport;
  geometryFor(reading: Reading): GeometryReport;
  /**
   * N2（R-05）：注入人物外形的**装配配置**（宿主传入的会话值 ⇒ 来源记 `'pack'`）。
   * `null` ⇒ 清空并退回确定性通用人形。
   */
  setAppearance(table: Map<string, CharacterAppearance> | null): void;
  /** N2：逐实体外形读数（含 `source: 'pack' | 'fallback'`）。 */
  appearanceReport(): AppearanceEntityReport[];
  /** N2：**部件读数**（从部件 mesh 层读回；含 `source_hex` / `material_hex`）。 */
  characterReport(): CharacterPartReport[];
  /** 场景图（mesh 层）读数：装配之后有没有再被改写。 */
  assemblyReport(): AssemblyReport;
  /** R4 / R3-C1：相机读数（D-7「不换相机」的机器判据取数点）。 */
  cameraReport(): CameraReport;
  /**
   * N2-r2 / F-1：**取证机位**（加法、可选、spike 专用）。`null` ⇒ 恢复**默认取景**。
   * 只改相机；不碰 `room` 盒的 `visible` / 材质 / 几何（室内视点的可见性来自
   * three 默认 `FrontSide` 对盒体内侧的剔除）。返回改后相机读数。
   */
  setObservationCamera(view: ObservationCameraView | null): CameraReport;
  /** R5 / 闭式面：**结构性场景状态**摘要（几何结构 + 对象结构）。 */
  structureReport(): StructureReport;
  /** R5：渲染一帧并返回**实际入参**相机身份（D-7「不换相机」的字面形态）。 */
  renderOnce(): RenderCameraReport;
  /** R5：最近一次渲染的相机身份读数（不触发渲染）。 */
  renderCameraReport(): RenderCameraReport;
  /** 画布尺寸 / 绘制缓冲（G1 的机器读数）。 */
  viewport(): ViewportReport;
  /** 把画布尺寸同步到当前视口（`setSize` + DPR + camera.aspect）。 */
  resize(): ViewportReport;
  startRenderLoop(): void;
  dispose(): void;
}

export function createScene(
  canvas: HTMLCanvasElement,
  options: { worldview: Tone; appearance?: Map<string, CharacterAppearance> | null },
): SceneHandle {
  const created = createRenderer(canvas);
  const webgl = created.webgl;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#f3efe8');
  scene.fog = new THREE.Fog('#e9e2d6', 40, 120);

  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 500);
  camera.position.set(DEFAULT_CAMERA_POSITION[0], DEFAULT_CAMERA_POSITION[1], DEFAULT_CAMERA_POSITION[2]);
  camera.lookAt(DEFAULT_CAMERA_LOOK_AT[0], DEFAULT_CAMERA_LOOK_AT[1], DEFAULT_CAMERA_LOOK_AT[2]);

  let currentReading: Reading = 'surface';

  // ---------------------------------------------------------------- R5：渲染相机入参记录
  // D-7「**禁止换相机**」的**字面形态**：全部渲染都经这个包装器 ⇒ 记录
  // `renderer.render(scene, camera)` 的**实际入参**（「第二相机」形态由此可辨）。
  // 渲染语义一字未改（纯透传；Node 无 WebGL 时底层仍是空渲染器）。
  let renderCameraIdentity: string | null = null;
  let renderCameraReading: Reading | null = null;
  let renderCount = 0;
  const renderer: RendererLike = {
    setPixelRatio(value) { created.renderer.setPixelRatio(value); },
    setSize(width, height, updateStyle) { created.renderer.setSize(width, height, updateStyle); },
    render(target, usedCamera) {
      created.renderer.render(target, usedCamera);
      renderCameraIdentity = `${usedCamera.type}#${usedCamera.uuid}`;
      renderCameraReading = currentReading;
      renderCount += 1;
    },
    dispose() { created.renderer.dispose(); },
  };

  /** R5：渲染一帧 —— **唯一**的 `renderer.render(scene, camera)` 调用点（相机入参由此可被记录）。 */
  function renderFrame(): void {
    renderer.render(scene, camera);
  }

  applyHealingLighting(scene, options.worldview.surface);

  const root = new THREE.Group();
  root.name = 'world-root';
  scene.add(root);

  let latestState: SceneState | undefined;
  const meshes = new Map<string, THREE.Mesh>();
  /**
   * N2：**部件 mesh**（key = 场景图对象名）。与 `meshes` **分离** ⇒ 既有取数路径
   * （`entityIds()` / `assemblyReport()` / `structureReport()` 的 `geometry` 分区）零改动。
   */
  const partMeshes = new Map<string, THREE.Mesh>();
  /**
   * N2（R-05）：人物外形的**装配配置**。优先取**宿主传入的会话值**
   * （`createScene(canvas, { appearance })` 或 `setAppearance()`）；`?pack=` **仅兜底**。
   * `null` ⇒ 全部退回确定性通用人形（来源记 `'fallback'`）。
   */
  let appearanceTable: Map<string, CharacterAppearance> | null = options.appearance ?? null;
  let appearanceAutoLoadAttempted = options.appearance !== undefined && options.appearance !== null;
  const palette = ['#d9c7a7', '#c9b79c', '#e2d6c2', '#b9a98f', '#d6c3ab'];

  /** N2：兜底 packId —— `?pack=` 查询参数（与 `main.ts` 同一约定），缺省主读数包。 */
  function queryPackId(): string {
    try {
      if (typeof location !== 'undefined' && location && location.search) {
        const pack = new URLSearchParams(location.search).get('pack');
        if (pack) return pack;
      }
    } catch {
      // 无 location（Node 判据 / 沙箱）⇒ 用缺省包；不伪造任何读数
    }
    return 'xingfu-xiaoqu';
  }

  // ---------------------------------------------------------------- G1：画布跟随视口
  let lastSize = { width: 1, height: 1 };
  let pixelRatio = 1;

  function resize(): ViewportReport {
    const width = Math.max(1, Math.round(Number(canvas.clientWidth) || Number(globalThis.innerWidth) || 1));
    const height = Math.max(1, Math.round(Number(canvas.clientHeight) || Number(globalThis.innerHeight) || 1));
    pixelRatio = Math.min(Number(globalThis.devicePixelRatio) || 1, 2);
    renderer.setPixelRatio(pixelRatio);
    // 第三个参数 = false：**不**让 three 去改内联样式（尺寸由 CSS 决定，绘制缓冲跟着 CSS 走）
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    lastSize = { width, height };
    return viewport();
  }

  function viewport(): ViewportReport {
    const bufferWidth = Number(canvas.width) || Math.round(lastSize.width * pixelRatio);
    const bufferHeight = Number(canvas.height) || Math.round(lastSize.height * pixelRatio);
    return {
      client_width: Math.round(Number(canvas.clientWidth) || lastSize.width),
      client_height: Math.round(Number(canvas.clientHeight) || lastSize.height),
      drawing_buffer_width: bufferWidth,
      drawing_buffer_height: bufferHeight,
      pixel_ratio: pixelRatio,
      aspect: camera.aspect,
      webgl,
    };
  }

  /**
   * R4 / R3-C1；**R5 / 闭式化扩面**：相机读数 —— 从 `THREE.Camera` 实例读回
   * （D-7「不换相机」的机器判据取数点）。
   */
  function cameraReport(): CameraReport {
    const perspective = camera as THREE.PerspectiveCamera;
    // 读数前把 `matrixWorld` 与当前变换对齐（浏览器里 `render()` 每帧本就如此；Node 无渲染循环）。
    camera.updateMatrixWorld(true);
    const view = perspective.view;
    return {
      position: [camera.position.x, camera.position.y, camera.position.z],
      quaternion: [camera.quaternion.x, camera.quaternion.y, camera.quaternion.z, camera.quaternion.w],
      matrix_world: quantizeMatrix(camera.matrixWorld),
      projection_matrix: quantizeMatrix(perspective.projectionMatrix),
      zoom: Number(perspective.zoom),
      view_offset: view === null ? null : {
        enabled: Boolean(view.enabled),
        full_width: Number(view.fullWidth),
        full_height: Number(view.fullHeight),
        offset_x: Number(view.offsetX),
        offset_y: Number(view.offsetY),
        width: Number(view.width),
        height: Number(view.height),
      },
      fov: Number(perspective.fov),
      near: Number(perspective.near),
      far: Number(perspective.far),
      aspect: Number(perspective.aspect),
    };
  }

  let resizeObserver: { disconnect(): void } | null = null;
  if (typeof (globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver === 'function') {
    const Observer = (globalThis as unknown as { ResizeObserver: new (cb: () => void) => { observe(el: unknown): void; disconnect(): void } }).ResizeObserver;
    resizeObserver = new Observer(() => { resize(); });
    try {
      (resizeObserver as unknown as { observe(el: unknown): void }).observe(canvas);
    } catch {
      resizeObserver = null;
    }
  }
  const onWindowResize = () => { resize(); };
  if (typeof (globalThis as unknown as { addEventListener?: unknown }).addEventListener === 'function') {
    (globalThis as unknown as { addEventListener(t: string, h: () => void): void }).addEventListener('resize', onWindowResize);
  }
  resize(); // 首帧就按真实视口设尺寸（此前停在 three 的默认 300×150）

  function materialFor(index: number): THREE.MeshStandardMaterial {
    return healingMaterial(palette[index % palette.length] as string, options.worldview[currentReading]);
  }

  function rebuild(state: SceneState | undefined): void {
    latestState = state;
    for (const mesh of meshes.values()) root.remove(mesh);
    meshes.clear();
    partMeshes.clear();
    const boxes = buildEntityBoxes(state, currentReading, { appearance: appearanceTable });
    boxes.forEach((box, index) => {
      // N2：人物实体的根 mesh = 躯干，其材质色 = 装配配置里的**包内 hex**（读法无关的 source_hex）；
      // 静物仍走既有调色板。两读法只改 `luminanceScale` ⇒ 几何与部件表逐项相同。
      const material = box.character_root
        ? healingMaterial(box.source_hex ?? (palette[index % palette.length] as string), options.worldview[currentReading])
        : materialFor(index);
      const mesh = new THREE.Mesh(box.geometry, material);
      mesh.name = box.id;
      mesh.position.set(...box.position);
      // R4 / R3-C1：装配变换（缩放 + 旋转）**真写入** mesh —— 默认单位变换 ⇒ 语义不变；
      // 装配后 mesh 层的 `scale`/`rotation` 分叉因此可被 `assemblyReport()` 读回并判红。
      mesh.scale.set(box.scale[0], box.scale[1], box.scale[2]);
      mesh.quaternion.set(box.quaternion[0], box.quaternion[1], box.quaternion[2], box.quaternion[3]);
      mesh.userData.entity_id = box.id;
      mesh.userData.kind = box.kind;
      if (box.character_root) {
        mesh.userData.part = 'torso';
        mesh.userData.source_hex = box.source_hex;
        mesh.userData.state_id = box.state_id ?? 'daily';
        // 人物**放置点**（部件局部偏移以它为原点 ⇒ 根部件的 `local_offset` 恒为 [0,0,0]）
        mesh.userData.character_placement = [box.position[0], box.position[1], box.position[2]];
      }
      root.add(mesh);
      meshes.set(box.id, mesh);
      if (box.kind !== 'npc') return;
      // N2（D3 / R-09）：其余部件 = **根 mesh 的子 mesh**，对象名 `"<实体 id>/<部件名>"`。
      // 部件名来自固定字段名表（`character.ts` 的 `CHARACTER_PART_NAMES`），**不含下标**。
      const entity = (state?.entities ?? []).find((item) => item.id === box.id);
      const parts = buildCharacterParts(
        appearanceTable?.get(box.id) ?? null,
        { entityId: box.id, state: entity },
      );
      for (const part of parts) {
        if (part.is_root) {
          partMeshes.set(part.name, mesh);
          continue;
        }
        const partMesh = new THREE.Mesh(
          new THREE.BoxGeometry(part.size[0], part.size[1], part.size[2]),
          healingMaterial(part.source_hex, options.worldview[currentReading]),
        );
        partMesh.name = part.name;
        partMesh.position.set(part.local_offset[0], part.local_offset[1], part.local_offset[2]);
        partMesh.userData.entity_id = box.id;
        partMesh.userData.part = part.part;
        partMesh.userData.source_hex = part.source_hex;
        mesh.add(partMesh);
        partMeshes.set(part.name, partMesh);
      }
    });
  }

  /** N2：**部件读数**（从部件 mesh 层读回；`source_hex` 读法无关，`material_hex` 仅信息性）。 */
  function characterReport(): CharacterPartReport[] {
    const names = [...partMeshes.keys()].sort();
    return names.map((name) => {
      const mesh = partMeshes.get(name) as THREE.Mesh;
      const geometry = mesh.geometry as THREE.BoxGeometry;
      const parameters = { ...(geometry.parameters as unknown as Record<string, number>) };
      const attribute = geometry.getAttribute('position');
      const material = mesh.material as THREE.MeshStandardMaterial;
      const entityId = String(mesh.userData.entity_id ?? '');
      const part = String(mesh.userData.part ?? (name === entityId ? 'torso' : name.slice(entityId.length + 1)));
      const isRoot = mesh.parent === root;
      // `local_offset` 的口径 = **相对人物放置点**的偏移 ⇒ 根部件（躯干）恒为 [0,0,0]，
      // 其余部件 = 相对根 mesh 的局部坐标。这样与装配函数产物（`character_shapes`）逐项可比。
      const placement = isRoot && Array.isArray(mesh.userData.character_placement)
        ? (mesh.userData.character_placement as number[])
        : [0, 0, 0];
      return {
        entity_id: entityId,
        part,
        name,
        is_root: isRoot,
        parameters,
        size: [Number(parameters.width), Number(parameters.height), Number(parameters.depth)] as [number, number, number],
        local_offset: [
          round6(mesh.position.x - (placement[0] ?? 0)),
          round6(mesh.position.y - (placement[1] ?? 0)),
          round6(mesh.position.z - (placement[2] ?? 0)),
        ] as [number, number, number],
        position_attribute_digest: digestPositions(attribute.array as unknown as ArrayLike<number>),
        vertex_count: attribute.count,
        // 装配配置里的**包内 hex**（读法无关）；缺装配配置时退回通用人形的中性色
        source_hex: String(mesh.userData.source_hex ?? ''),
        // **读回**值：随读法变（`luminanceScale`）⇒ 仅信息性，不进相等断言
        material_hex: `#${material.color.getHexString()}`,
      };
    });
  }

  /** N2：逐实体外形读数（含 `source: 'pack' | 'fallback'`，R-05）。 */
  function appearanceReport(): AppearanceEntityReport[] {
    const all = characterReport();
    return [...meshes.keys()]
      .filter((id) => (meshes.get(id) as THREE.Mesh).userData.kind === 'npc')
      .sort()
      .map((id) => {
        // N2-r2 / F-3：**显式降级**读数（结构化告警）—— 与装配/`state_id` 同一条判定路径。
        const entity = (latestState?.entities ?? []).find((item) => item.id === id);
        const degradation = resolveMaskDegradation(
          appearanceTable?.get(id) ?? null,
          { entityId: id, state: entity },
        );
        return {
          entity_id: id,
          state_id: String((meshes.get(id) as THREE.Mesh).userData.state_id ?? 'daily'),
          source: appearanceTable?.has(id) ? 'pack' as const : 'fallback' as const,
          degradations: degradation.degraded && degradation.code !== null
            ? [{ code: degradation.code, detail: degradation.detail ?? '', requested_state_id: degradation.requested_state_id }]
            : [],
          parts: all.filter((part) => part.entity_id === id),
        };
      });
  }

  /**
   * N2：惰性自动接线（**只读**）。宿主未注入装配配置时，按实体 id 解析一次内容包
   * （`?pack=` 兜底）。取不到 ⇒ 保持 `null`（退回确定性通用人形，**不伪造**）。
   */
  function maybeAutoLoadAppearance(): void {
    if (appearanceAutoLoadAttempted) return;
    const npcIds = [...new Set((latestState?.entities ?? [])
      .filter((entity) => entity.kind === 'npc')
      .map((entity) => entity.id))].sort();
    // r5 / Raven M8：置位**必须在** `npcIds.length === 0` 之后 —— 否则首个 snapshot 不含 NPC 时
    // 会被记成「已尝试过」⇒ 后续 NPC **永久**走通用人形兜底且**无提示**（一次性缺口）。
    if (npcIds.length === 0) return;
    appearanceAutoLoadAttempted = true;
    void resolveAppearanceTable({ packId: queryPackId(), npcIds }).then((table) => {
      if (table.size === 0) return;
      appearanceTable = table;
      rebuild(latestState);
    }).catch(() => {
      // 只读 GET 失败 ⇒ 保持退回路径；不伪造
    });
  }

  /** 从场景图读回装配结果（**装配之后**的真相；网格层分叉只在这里可见）。 */
  function assemblyReport(): AssemblyReport {
    const ids = [...meshes.keys()].sort();
    const shapeDigests: Record<string, string> = {};
    const meshPositions: Record<string, string> = {};
    const meshScales: Record<string, string> = {};
    const meshRotations: Record<string, string> = {};
    const parts: string[] = [];
    for (const id of ids) {
      const mesh = meshes.get(id) as THREE.Mesh;
      const geometry = mesh.geometry as THREE.BoxGeometry;
      const size = [geometry.parameters.width, geometry.parameters.height, geometry.parameters.depth] as [number, number, number];
      // R4 / R3-C1：缩放与旋转也**从 mesh 读回**（此前只读 position ⇒ scale/rotation 注入可逃逸）
      const scale: [number, number, number] = [mesh.scale.x, mesh.scale.y, mesh.scale.z];
      const quaternion: [number, number, number, number] = [mesh.quaternion.x, mesh.quaternion.y,
        mesh.quaternion.z, mesh.quaternion.w];
      const shape = shapeOf(id, geometry, size, scale, quaternion);
      shapeDigests[id] = shapeDigestString(shape);
      meshPositions[id] = [mesh.position.x, mesh.position.y, mesh.position.z].map(q6).join(',');
      meshScales[id] = scale.map(q6).join(',');
      meshRotations[id] = quaternion.map(q6).join(',');
      // 口径（**与 R3 一致**）：装配 `geometry_digest` **不含**世界坐标 —— 浏览器里跨 tick 的合法位移
      // 会让它抖动（f4 的 `*_assembly_two_reads_same_geometry` 会因此**假红**，实测已复现并修正）。
      // 缩放/旋转是**装配变换**（恒定）⇒ 进摘要安全；坐标由 `mesh_positions` 单独逐项比较
      // （`scene_assert` 在静态状态上跑，不受 tick 影响）。
      parts.push(`${id}:${shapeDigests[id]}:s=${meshScales[id]}:q=${meshRotations[id]}`);
    }
    return {
      reading: currentReading,
      entity_ids: ids,
      shape_digests: shapeDigests,
      mesh_positions: meshPositions,
      mesh_scales: meshScales,
      mesh_rotations: meshRotations,
      geometry_digest: parts.join('|'),
      mesh_count: ids.length,
    };
  }

  /** R5 / 闭式面：**几何结构摘要**（`index` / `groups` / 每个 attribute）。 */
  function geometryStructureOf(geometry: THREE.BufferGeometry): GeometryStructure {
    const index = geometry.getIndex();
    const groups = geometry.groups.map((group) => ({
      start: Number(group.start),
      count: Number(group.count),
      materialIndex: Number(group.materialIndex ?? 0),
    }));
    const names = new Set<string>([...STRUCTURE_ATTRIBUTES, ...Object.keys(geometry.attributes)]);
    const attributes: Record<string, AttributeStructure | null> = {};
    for (const name of [...names].sort()) {
      const attribute = geometry.getAttribute(name) as THREE.BufferAttribute | undefined;
      attributes[name] = attribute
        ? {
          name,
          item_size: Number(attribute.itemSize),
          count: Number(attribute.count),
          digest: digestPositions(attribute.array as unknown as ArrayLike<number>),
        }
        : null;
    }
    const indexStructure: IndexStructure = index === null
      ? { present: false, count: null, digest: null }
      : { present: true, count: Number(index.count), digest: digestPositions(index.array as unknown as ArrayLike<number>) };
    return {
      index: indexStructure,
      groups,
      groups_digest: JSON.stringify(groups),
      attributes,
      digest: JSON.stringify({ index: indexStructure, groups, attributes }),
    };
  }

  /**
   * R5 / **闭式面**：**结构性场景状态**摘要 —— 遍历式（不是逐字段白名单）：
   * 几何 `index`/`groups`/`attributes`、每对象 `matrixWorld` 16 分量 / `visible` /
   * `layers.mask` / `renderOrder`、以及根子树的**身份与父子关系**。
   * 判据体内**零字面量**：只把「两态各自的读数」互相比较（`scene_assert.mjs`）。
   */
  function structureReport(): StructureReport {
    // 读数前把世界矩阵与当前场景图对齐（浏览器里 `render()` 每帧本就如此；Node 里没有渲染循环）。
    scene.updateMatrixWorld(true);
    const geometry: Record<string, GeometryStructure> = {};
    const geometryParts: string[] = [];
    for (const id of [...meshes.keys()].sort()) {
      const mesh = meshes.get(id) as THREE.Mesh;
      const structure = geometryStructureOf(mesh.geometry as THREE.BufferGeometry);
      geometry[id] = structure;
      geometryParts.push(`${id}:${structure.digest}`);
    }
    const objects: ObjectStructure[] = [];
    let ordinal = 0;
    const walk = (object: THREE.Object3D, parentId: string | null): void => {
      ordinal += 1;
      // **稳定身份**：`name` 优先（mesh = 实体 id；根 = `world-root`）—— 不用 `id`/`uuid`
      // （它们在每次 `rebuild()` 后都会变 ⇒ 会把「同一结构」误判成不同）。
      const identity = object.name || `${object.type}#${ordinal}`;
      objects.push({
        id: identity,
        parent_id: parentId,
        type: object.type,
        matrix_world: quantizeMatrix(object.matrixWorld),
        visible: Boolean(object.visible),
        layers_mask: Number(object.layers.mask),
        render_order: Number(object.renderOrder),
      });
      for (const child of object.children) walk(child, identity);
    };
    for (const child of scene.children) walk(child, null);
    return {
      reading: currentReading,
      geometry,
      geometry_digest: geometryParts.join('|'),
      objects,
      objects_digest: JSON.stringify(objects),
    };
  }

  return {
    apply(message) {
      if (message.t === 'snapshot') {
        rebuild(message.state);
        maybeAutoLoadAppearance();
        return;
      }
      if (message.t === 'delta') {
        // 增量：实体集合不变时只更新位置；**绝不**重建几何以外的读法相关量
        for (const op of (message.ops ?? []) as Array<{ entity?: string; component?: string; value?: unknown }>) {
          const mesh = op.entity ? meshes.get(op.entity) : undefined;
          if (!mesh || op.component !== 'transform') continue;
          const pos = (op.value as { pos_mm?: { x: number; y: number; z: number } } | undefined)?.pos_mm;
          if (!pos) continue;
          mesh.position.set(pos.x / MM, pos.y / MM, pos.z / MM);
        }
      }
    },
    setReading(reading) {
      currentReading = reading;
      applyHealingLighting(scene, options.worldview[reading]);
      // 读法经 `READING_GEOMETRY_PROFILE` 真正参与一次装配；两读法配置等价 ⇒ 数值不变
      rebuild(latestState);
    },
    reading: () => currentReading,
    entityIds: () => [...meshes.keys()].sort(),
    geometry: () => geometryReport(latestState, currentReading, { appearance: appearanceTable }),
    // 读法**真的**被接收并一路传到装配（`buildEntityBoxes(state, reading)`）；
    // 两读法同几何是**装配配置等价**的结果，不再是「同一个入参算两遍」
    geometryFor: (reading) => geometryReport(latestState, reading, { appearance: appearanceTable }),
    setAppearance(table) {
      // R-05：宿主传入的会话值 ⇒ 来源记 `'pack'`；`?pack=` 只作兜底，不覆盖宿主
      appearanceTable = table;
      appearanceAutoLoadAttempted = true;
      rebuild(latestState);
    },
    appearanceReport,
    characterReport,
    assemblyReport,
    cameraReport,
    /**
     * N2-r2 / F-1：**取证机位**。`null` ⇒ 逐项恢复到 `DEFAULT_CAMERA_POSITION` /
     * `DEFAULT_CAMERA_LOOK_AT`（起点冻结值）⇒ 「不调用它」与「调用后再置 null」读数相同。
     */
    setObservationCamera(view) {
      const position = view === null ? DEFAULT_CAMERA_POSITION : view.position_m;
      const target = view === null ? DEFAULT_CAMERA_LOOK_AT : view.look_at_m;
      camera.position.set(position[0], position[1], position[2]);
      camera.lookAt(target[0], target[1], target[2]);
      camera.updateMatrixWorld(true);
      return cameraReport();
    },
    structureReport,
    renderCameraReport: () => ({
      identity: renderCameraIdentity,
      renders: renderCount,
      reading: renderCameraReading,
    }),
    renderOnce() {
      renderFrame();
      return { identity: renderCameraIdentity, renders: renderCount, reading: renderCameraReading };
    },
    viewport,
    resize,
    startRenderLoop() {
      const loop = () => {
        renderFrame();
        globalThis.requestAnimationFrame(loop);
      };
      loop();
    },
    dispose() {
      if (resizeObserver) resizeObserver.disconnect();
      if (typeof (globalThis as unknown as { removeEventListener?: unknown }).removeEventListener === 'function') {
        (globalThis as unknown as { removeEventListener(t: string, h: () => void): void }).removeEventListener('resize', onWindowResize);
      }
      renderer.dispose();
    },
  };
}
