/**
 * 真实 PBR 材质库（N4 / W3）—— **纯数据注册表 + 惰性贴图加载**。
 *
 * 设计约束（REQ-20260924-004 / 01 方案 D-3 + Raven 预审 R-7 / P-D）：
 *   1. **Node 可 import、不发请求**：`SURFACES` 是纯数据；`loadSurfaceMaterials()` 只在**真 WebGL**
 *      下被调用（`world.ts` 传入 `THREE.TextureLoader`），失败**不抛**、回落纯色并记 `degradations`。
 *   2. **引用方式**：一律 `new URL('../../assets/<...>', import.meta.url).href` 的**静态字符串字面量**
 *      （Vite 静态解析并 emit；Node 下退化为 `file://` 字符串、不发请求）。**禁止**动态拼接。
 *   3. **真实尺度 repeat**：`repeat = [表面米数 / repeat_basis_m]`，`repeat_basis_m` 逐材质取自
 *      **上游权威读数**（Poly Haven API `dimensions` 字段，单位 cm），与 `web/assets/manifest.txt`
 *      的「真实覆盖 N cm」登记行同源 ⇒ 可由判据机械复核（`material_repeat_matches_real_scale`）。
 *   4. **区间**（以更紧的一处为准，Raven R-11）：`roughness ∈ [0.6, 0.95]`、`metalness ∈ [0, 0.15]`、
 *      水/湿地面 `metalness === 0`、法线强度 ≤ 0.4、贴图 ≤ 2048²。
 *   5. `materialReport()` **必须**暴露 `degradations`（否则「注册表绿、画面纯色」可同时成立）。
 */

import * as THREE from 'three';

export type SurfaceId = 'wall_plaster' | 'wall_brick' | 'roof_tile' | 'pavement_brick'
  | 'road_asphalt' | 'ground_grass' | 'ground_wet' | 'wood_plank'
  | 'metal_corrugated' | 'glass' | 'fabric_cotton' | 'leather_red';

/** 一个表面引用的贴图（**URL 字符串**；`roughness`/`metalness`/`ao` 可指向同一张 arm 打包图）。 */
export interface SurfaceMaps {
  diffuse: string;
  normal: string;
  roughness: string;
  metalness?: string;
  ao?: string;
}

export interface SurfaceSpec {
  /** 对应资产包 manifest 的 asset id（上游 id，不是本地目录名）。 */
  asset_id: string;
  maps: SurfaceMaps;
  /** `[surface_size_m[0] / repeat_basis_m[0], surface_size_m[1] / repeat_basis_m[1]]`（模块初始化时派生）。 */
  repeat: [number, number];
  /**
   * **上游扫描覆盖**（米）—— Poly Haven API `dimensions`（cm）/100，**真值、非设计参数**。
   * 它是 `repeat_basis_m` 的**上界**：`repeat_basis_m ≤ scan_coverage_m` 恒成立（永不把贴图放大到
   * 比源照片还大）。
   */
  scan_coverage_m: number;
  /**
   * **材质基准**（米）：该贴图在**这个表面上**被映射到的真实世界尺寸（来自 `BASIS_M` 的声明值）。
   * `repeat = surface_size_m / repeat_basis_m` —— 构件小于基准时 `repeat < 1` **合法**（贴图被放大）。
   */
  repeat_basis_m: [number, number];
  /** `repeat_basis_m` 的取证来源（人类可读；与 `web/assets/manifest.txt` 的登记行同源）。 */
  repeat_basis_source: string;
  /** `repeat_basis_m` 的**依据标签 + 画面证据路径**（R3-3：`visually_corrected` 必须附画面证据）。 */
  basis_evidence: BasisEvidence;
  /** 该材质在交付面里承载的**代表表面米数**（用于反推 repeat）。 */
  surface_size_m: [number, number];
  /** art-bible §3：0.0–0.15；水/湿地面**恒 0**。 */
  metalness: number;
  /** art-bible §3 / assets/manifest.json：本项目取更紧的 [0.6, 0.95]。 */
  roughness: number;
  /** AC-1：主材质 `envMapIntensity ≥ 1.15`。 */
  envMapIntensity: number;
  /** art-bible §3：法线强度 ≤ 0.4。 */
  normal_scale: number;
  license: 'cc0-1.0';
  source_library: string;
  asset_page: string;
  /** 与上游/契约语义的**显式偏差**（不得静默；不伪造）。 */
  deviation?: string;
  transparent?: boolean;
  opacity?: number;
}

const round6 = (value: number): number => Math.round(value * 1e6) / 1e6;

/** 静态 URL 字面量（Vite 静态解析；Node 下退化为 `file://` 字符串）。 */
const URLS = {
  grey_plaster_diffuse: new URL('../../assets/grey_plaster/Diffuse.jpg', import.meta.url).href,
  grey_plaster_normal: new URL('../../assets/grey_plaster/nor_gl.jpg', import.meta.url).href,
  grey_plaster_arm: new URL('../../assets/grey_plaster/arm.jpg', import.meta.url).href,

  brick_wall_04_diffuse: new URL('../../assets/brick_wall_04/Diffuse.jpg', import.meta.url).href,
  brick_wall_04_normal: new URL('../../assets/brick_wall_04/nor_gl.jpg', import.meta.url).href,
  brick_wall_04_arm: new URL('../../assets/brick_wall_04/arm.jpg', import.meta.url).href,

  clay_roof_tiles_02_diffuse: new URL('../../assets/clay_roof_tiles_02/Diffuse.jpg', import.meta.url).href,
  clay_roof_tiles_02_normal: new URL('../../assets/clay_roof_tiles_02/nor_gl.jpg', import.meta.url).href,
  clay_roof_tiles_02_arm: new URL('../../assets/clay_roof_tiles_02/arm.jpg', import.meta.url).href,

  brick_pavement_diffuse: new URL('../../assets/brick_pavement/Diffuse.jpg', import.meta.url).href,
  brick_pavement_normal: new URL('../../assets/brick_pavement/nor_gl.jpg', import.meta.url).href,
  brick_pavement_arm: new URL('../../assets/brick_pavement/arm.jpg', import.meta.url).href,

  asphalt_02_diffuse: new URL('../../assets/asphalt_02/Diffuse.jpg', import.meta.url).href,
  asphalt_02_normal: new URL('../../assets/asphalt_02/nor_gl.jpg', import.meta.url).href,
  asphalt_02_arm: new URL('../../assets/asphalt_02/arm.jpg', import.meta.url).href,

  grass_ground_diffuse: new URL('../../assets/grass_ground/Diffuse.jpg', import.meta.url).href,
  grass_ground_normal: new URL('../../assets/grass_ground/nor_gl.jpg', import.meta.url).href,
  grass_ground_arm: new URL('../../assets/grass_ground/arm.jpg', import.meta.url).href,

  brushed_concrete_diffuse: new URL('../../assets/brushed_concrete/Diffuse.jpg', import.meta.url).href,
  brushed_concrete_normal: new URL('../../assets/brushed_concrete/nor_gl.jpg', import.meta.url).href,
  brushed_concrete_arm: new URL('../../assets/brushed_concrete/arm.jpg', import.meta.url).href,

  black_painted_planks_diffuse: new URL('../../assets/black_painted_planks/Diffuse.jpg', import.meta.url).href,
  black_painted_planks_normal: new URL('../../assets/black_painted_planks/nor_gl.jpg', import.meta.url).href,
  black_painted_planks_arm: new URL('../../assets/black_painted_planks/arm.jpg', import.meta.url).href,

  corrugated_iron_02_diffuse: new URL('../../assets/corrugated_iron_02/Diffuse.jpg', import.meta.url).href,
  corrugated_iron_02_normal: new URL('../../assets/corrugated_iron_02/nor_gl.jpg', import.meta.url).href,
  corrugated_iron_02_arm: new URL('../../assets/corrugated_iron_02/arm.jpg', import.meta.url).href,

  cotton_jersey_diffuse: new URL('../../assets/cotton_jersey/Diffuse.jpg', import.meta.url).href,
  cotton_jersey_normal: new URL('../../assets/cotton_jersey/nor_gl.jpg', import.meta.url).href,
  cotton_jersey_arm: new URL('../../assets/cotton_jersey/arm.jpg', import.meta.url).href,

  leather_red_02_diffuse: new URL('../../assets/leather_red_02/coll2.jpg', import.meta.url).href,
  leather_red_02_normal: new URL('../../assets/leather_red_02/nor_gl.jpg', import.meta.url).href,
  leather_red_02_arm: new URL('../../assets/leather_red_02/arm.jpg', import.meta.url).href,

  skin_pale_diffuse: new URL('../../assets/character/skin-pale-01.jpg', import.meta.url).href,
} as const;

/**
 * 上游 Poly Haven API 的 `dimensions`（cm → m）—— **扫描覆盖**，逐项实测，见 `web/assets/manifest.txt`。
 * 这是「这张贴图在真实世界里覆盖多大一片」的**上游真值**，**不是**设计参数。
 */
const SCAN_COVERAGE_M = {
  grey_plaster: 10.0,
  brick_wall_04: 13.9,
  clay_roof_tiles_02: 25.0,
  brick_pavement: 20.0,
  asphalt_02: 30.0,
  grass_ground: 25.1,
  brushed_concrete: 25.0,
  black_painted_planks: 16.0,
  corrugated_iron_02: 27.0,
  cotton_jersey: 2.636,
  leather_red_02: 0.3,
} as const;

/**
 * **逐表面「材质基准」声明值**（N4-r3 / R3-3）：这张贴图在**这个表面上**被映射到的真实世界尺寸。
 *
 * 依据必须**可核**，且**不得由构件尺寸反推**（r2 的 `min(扫描覆盖, 构件尺寸)` 规则被 architect 打回：
 * 它让 `repeat ≥ 1` / `never_magnified` 变成恒真式）。两条合法依据：
 *
 * - `upstream`：取上游 Poly Haven API 的 `dimensions`（= `SCAN_COVERAGE_M`）。适用于**没有可数图案单元**
 *   的贴图（灰泥 / 沥青 / 拉毛混凝土 / 草地 / 针织物 / 皮革粒面）——它们没有「一块砖」这样的尺度锚点，
 *   上游米数是唯一可核依据。
 * - `visually_corrected`：**独立测量**「贴图内图案单元数 × 该单元的物理参照尺寸」得到覆盖米数。
 *   适用于有可数单元的贴图。**必须附画面证据**（裁切图 + 读图结论），见 `BASIS_EVIDENCE`。
 *
 * 为什么砖 / 板 / 瓦 / 瓦楞必须走 `visually_corrected`：上游 `dimensions` 对这些贴图**系统性偏大**
 * 约 5–20 倍（Raven N2-1 已指出 `dimensions` 不可靠：`leather_red_02` 一处 600 cm / 一处 30 cm 自相矛盾）。
 * 若照抄上游，`brick_wall_04` 13.9 m ÷ 贴图内 10 块砖 = **1.39 m 一块砖**，物理上不可能。
 */
const BASIS_M: Record<SurfaceId, number> = {
  wall_plaster: 10.0,      // upstream：灰泥无尺度锚点
  wall_brick: 2.2,         // visually_corrected：贴图内 10 块砖 × 22 cm
  roof_tile: 4.5,          // visually_corrected：贴图内 18 条瓦垄 × 25 cm
  pavement_brick: 2.1,     // visually_corrected：贴图内 10 块铺装砖 × 21 cm
  road_asphalt: 30.0,      // upstream：沥青无尺度锚点
  ground_grass: 25.1,      // upstream：草地无尺度锚点
  ground_wet: 25.0,        // upstream：拉毛混凝土无尺度锚点
  wood_plank: 1.68,        // visually_corrected：贴图内 14 条板缝 × 12 cm
  metal_corrugated: 2.08,  // visually_corrected：贴图内 32 道瓦楞 × 6.5 cm
  glass: 25.0,             // upstream（该表面复用拉毛混凝土，见 declared_deviation）
  fabric_cotton: 2.636,    // upstream：针织物无尺度锚点
  leather_red: 0.3,        // upstream：取上游 `scale` 字段（与 `dimensions` 冲突，见 declared_conflicts）
};

/** 每个基准值的**依据来源**与（`visually_corrected` 必须有的）画面证据路径。 */
export interface BasisEvidence {
  readonly tag: 'upstream' | 'visually_corrected';
  /** 画面核验证据（裁切图 / 读图结论落盘路径）；`upstream` 为 `null`。 */
  readonly evidence_path: string | null;
  /** 一句人类可读的依据。 */
  readonly note: string;
}

const READBACK = 'v0/spikes/n4-art/readback';

export const BASIS_EVIDENCE: Record<SurfaceId, BasisEvidence> = {
  wall_plaster: { tag: 'upstream', evidence_path: null, note: 'Poly Haven dimensions 10.0 m（灰泥无可数单元）' },
  wall_brick: {
    tag: 'visually_corrected', evidence_path: `${READBACK}/tex-crop-brick_wall_04.png`,
    note: '裁切图读作 10 块砖/贴图宽（5 块/512px）；标准砖长 20–24 cm ⇒ 覆盖 2.2 m',
  },
  roof_tile: {
    tag: 'visually_corrected', evidence_path: `${READBACK}/tex-crop-clay_roof_tiles_02.png`,
    note: '裁切图读作 18 条瓦垄/贴图宽（9 条/512px）；筒瓦垄宽 20–30 cm ⇒ 覆盖 4.5 m',
  },
  pavement_brick: {
    tag: 'visually_corrected', evidence_path: `${READBACK}/tex-crop-brick_pavement.png`,
    note: '裁切图读作 10 块铺装砖/贴图宽；联锁砖长 18–24 cm ⇒ 覆盖 2.1 m',
  },
  road_asphalt: { tag: 'upstream', evidence_path: null, note: 'Poly Haven dimensions 30.0 m（沥青无可数单元）' },
  ground_grass: { tag: 'upstream', evidence_path: null, note: 'Poly Haven dimensions 25.1 m（草地无可数单元）' },
  ground_wet: { tag: 'upstream', evidence_path: null, note: 'Poly Haven dimensions 25.0 m（拉毛混凝土无可数单元）' },
  wood_plank: {
    tag: 'visually_corrected', evidence_path: `${READBACK}/tex-crop-black_painted_planks.png`,
    note: '裁切图读作 14 条板缝/贴图宽（7 条/512px）；木板板宽 10–15 cm ⇒ 覆盖 1.68 m',
  },
  metal_corrugated: {
    tag: 'visually_corrected', evidence_path: `${READBACK}/tex-crop-corrugated_iron_02.png`,
    note: '裁切图读作 32 道瓦楞/贴图宽（16 道/512px）；瓦楞铁肋距 5–8 cm ⇒ 覆盖 2.08 m',
  },
  glass: { tag: 'upstream', evidence_path: null, note: 'Poly Haven dimensions 25.0 m（复用拉毛混凝土）' },
  fabric_cotton: { tag: 'upstream', evidence_path: null, note: 'Poly Haven dimensions 2.636 m（针织无可数单元）' },
  leather_red: { tag: 'upstream', evidence_path: null, note: '上游 `scale` 字段 30 cm（与 `dimensions` 600 cm 冲突，见 declared_conflicts）' },
};

/**
 * **上游数据自相矛盾**的显式登记（R3-3 / Raven U-6、N2-1）。
 *
 * `leather_red_02` 在 Poly Haven API 上同时给出两个尺度字段且**相差 20 倍**：
 * `dimensions` = 600 cm、`scale` = 30 cm。二者不可能同时正确（皮革不可能一张照片拍 6 m 大）。
 * 本实现取 `scale` = 30 cm（0.3 m）作为基准——理由：皮革粒面是**微观**纹理，
 * 30 cm 量级与「一件外套上看得见粒面」相符；600 cm 会让 0.38 m 的袖子只显示贴图的 6%，
 * 粒面被放大到 6 cm 一颗，肉眼读作噪点。
 *
 * 这是**声明**而非隐瞒：任何复核者都可据此重新判断。`600 cm` 分支若被采用，
 * `leather_red` 的 `repeat` 会从 `[1.266667, 3.733333]` 变成 `[0.063333, 0.186667]`。
 */
export const DECLARED_CONFLICTS: readonly Record<string, unknown>[] = [
  {
    asset_id: 'leather_red_02',
    field_a: { name: 'dimensions', value_cm: 600 },
    field_b: { name: 'scale', value_cm: 30 },
    ratio: 20,
    adopted: 'scale',
    adopted_value_cm: 30,
    why: '皮革粒面是微观纹理，30 cm 量级与外套上可见粒面相符；600 cm 会让粒面放大到 6 cm/颗',
    alternative_effect: 'leather_red.repeat → [0.063333, 0.186667]（贴图放大 20 倍）',
    reviewer_action: '可据此重新裁决；本实现不掩盖该冲突',
  },
] as const;

const POLY_HAVEN = 'Poly Haven';

/**
 * **贴图内图案单元的物理尺寸**（R3-3 的「构件尺寸 / basis / repeat / 依据来源 / 画面可辨性」五列表的
 * 可复算内核）。`pattern_unit_cm = basis_m × 100 / count_per_tile` —— 注意它与**构件尺寸无关**：
 * 一张贴图被声明为覆盖 `basis` 米，贴图内有 `count` 个图案单元 ⇒ 每个单元恒为 `basis/count` 米，
 * 无论它被贴到 1 m 的门还是 5 m 的墙上。
 *
 * `count_per_tile` 是**视觉计数**（裁切图见 `BASIS_EVIDENCE[<surface>].evidence_path`），
 * `physical_reference_cm` 是该单元在现实世界里的常见尺寸区间 —— 二者相互独立，故本表可被证伪：
 * 若 `basis` 声明错了，`pattern_unit_cm` 就会掉出参照区间。
 */
export interface PatternUnit {
  /** 单元名称（中文，供五列表阅读）。 */
  readonly unit_name: string;
  /** 该贴图内此单元的个数（视觉计数）。 */
  readonly count_per_tile: number;
  /** 该单元在现实世界的常见尺寸区间（cm）。 */
  readonly physical_reference_cm: readonly [number, number];
}

export const PATTERN_UNITS: Partial<Record<SurfaceId, PatternUnit>> = {
  wall_brick: { unit_name: '砖长', count_per_tile: 10, physical_reference_cm: [20, 24] },
  pavement_brick: { unit_name: '铺装砖长', count_per_tile: 10, physical_reference_cm: [18, 24] },
  roof_tile: { unit_name: '瓦垄宽', count_per_tile: 18, physical_reference_cm: [20, 30] },
  wood_plank: { unit_name: '板宽', count_per_tile: 14, physical_reference_cm: [10, 15] },
  metal_corrugated: { unit_name: '瓦楞肋距', count_per_tile: 32, physical_reference_cm: [5, 8] },
};

/** 该表面的图案单元物理尺寸（cm）；无图案单元的表面返回 `null`。 */
export function patternUnitCm(surfaceId: SurfaceId): number | null {
  const unit = PATTERN_UNITS[surfaceId];
  if (!unit) return null;
  return Math.round((BASIS_M[surfaceId] * 100 / unit.count_per_tile) * 100) / 100;
}

/** 该表面的图案单元尺寸是否落在现实参照区间内（无图案单元的表面返回 `null`）。 */
export function patternUnitWithinReference(surfaceId: SurfaceId): boolean | null {
  const unit = PATTERN_UNITS[surfaceId];
  const cm = patternUnitCm(surfaceId);
  if (!unit || cm === null) return null;
  return cm >= unit.physical_reference_cm[0] && cm <= unit.physical_reference_cm[1];
}

/** 表面定义（**不含** `repeat` / `repeat_basis_m` / `basis_evidence`）：前两者由 `spec()` 从 `BASIS_M`
 *  与 `surface_size_m` **派生**，后者由 `BASIS_EVIDENCE` 注入 —— 避免手抄漂移。 */
type SurfaceInput = Omit<SurfaceSpec, 'repeat' | 'repeat_basis_m' | 'basis_evidence'>;

const INPUTS: Record<SurfaceId, SurfaceInput> = {
  wall_plaster: {
    asset_id: 'grey_plaster',
    maps: { diffuse: URLS.grey_plaster_diffuse, normal: URLS.grey_plaster_normal, roughness: URLS.grey_plaster_arm },
    scan_coverage_m: SCAN_COVERAGE_M.grey_plaster,
    repeat_basis_source: 'polyhaven_api_dimensions:1000cm',
    surface_size_m: [5.0, 3.0],
    metalness: 0.0, roughness: 0.86, envMapIntensity: 1.2, normal_scale: 0.35,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/grey_plaster',
  },
  wall_brick: {
    asset_id: 'brick_wall_04',
    maps: { diffuse: URLS.brick_wall_04_diffuse, normal: URLS.brick_wall_04_normal, roughness: URLS.brick_wall_04_arm },
    scan_coverage_m: SCAN_COVERAGE_M.brick_wall_04,
    repeat_basis_source: 'visual_pattern_count:10x22cm',
    surface_size_m: [5.0, 3.0],
    metalness: 0.0, roughness: 0.9, envMapIntensity: 1.2, normal_scale: 0.4,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/brick_wall_04',
  },
  roof_tile: {
    asset_id: 'clay_roof_tiles_02',
    maps: {
      diffuse: URLS.clay_roof_tiles_02_diffuse,
      normal: URLS.clay_roof_tiles_02_normal,
      roughness: URLS.clay_roof_tiles_02_arm,
    },
    scan_coverage_m: SCAN_COVERAGE_M.clay_roof_tiles_02,
    repeat_basis_source: 'visual_pattern_count:18x25cm',
    surface_size_m: [5.6, 5.6],
    metalness: 0.0, roughness: 0.82, envMapIntensity: 1.2, normal_scale: 0.4,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/clay_roof_tiles_02',
  },
  pavement_brick: {
    asset_id: 'brick_pavement',
    maps: {
      diffuse: URLS.brick_pavement_diffuse,
      normal: URLS.brick_pavement_normal,
      roughness: URLS.brick_pavement_arm,
    },
    scan_coverage_m: SCAN_COVERAGE_M.brick_pavement,
    repeat_basis_source: 'visual_pattern_count:10x21cm',
    surface_size_m: [5.0, 5.0],
    metalness: 0.0, roughness: 0.85, envMapIntensity: 1.2, normal_scale: 0.35,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/brick_pavement',
  },
  road_asphalt: {
    asset_id: 'asphalt_02',
    maps: { diffuse: URLS.asphalt_02_diffuse, normal: URLS.asphalt_02_normal, roughness: URLS.asphalt_02_arm },
    scan_coverage_m: SCAN_COVERAGE_M.asphalt_02,
    repeat_basis_source: 'polyhaven_api_dimensions:3000cm',
    surface_size_m: [240, 8],
    metalness: 0.02, roughness: 0.78, envMapIntensity: 1.3, normal_scale: 0.3,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/asphalt_02',
  },
  ground_grass: {
    asset_id: 'grass_ground',
    maps: { diffuse: URLS.grass_ground_diffuse, normal: URLS.grass_ground_normal, roughness: URLS.grass_ground_arm },
    scan_coverage_m: SCAN_COVERAGE_M.grass_ground,
    repeat_basis_source: 'polyhaven_api_dimensions:2510cm',
    surface_size_m: [240, 240],
    metalness: 0.0, roughness: 0.9, envMapIntensity: 1.2, normal_scale: 0.3,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/grass_ground',
  },
  ground_wet: {
    asset_id: 'brushed_concrete',
    maps: {
      diffuse: URLS.brushed_concrete_diffuse,
      normal: URLS.brushed_concrete_normal,
      roughness: URLS.brushed_concrete_arm,
    },
    scan_coverage_m: SCAN_COVERAGE_M.brushed_concrete,
    repeat_basis_source: 'polyhaven_api_dimensions:2500cm',
    surface_size_m: [240, 4.0],
    metalness: 0.0, roughness: 0.62, envMapIntensity: 1.3, normal_scale: 0.25,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/brushed_concrete',
    deviation: '湿地面（REQ W3）**无专用 CC0 扫描**：采用 `brushed_concrete`（水泥/混凝土湿面）作承载材质，'
      + 'metalness 按 REQ 字面恒 0；不是水面/水洼模拟，湿感仅来自低粗糙（0.62）+ 环境反射。',
  },
  wood_plank: {
    asset_id: 'black_painted_planks',
    maps: {
      diffuse: URLS.black_painted_planks_diffuse,
      normal: URLS.black_painted_planks_normal,
      roughness: URLS.black_painted_planks_arm,
    },
    scan_coverage_m: SCAN_COVERAGE_M.black_painted_planks,
    repeat_basis_source: 'visual_pattern_count:14x12cm',
    surface_size_m: [1.1, 2.1],
    metalness: 0.0, roughness: 0.8, envMapIntensity: 1.2, normal_scale: 0.35,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/black_painted_planks',
  },
  metal_corrugated: {
    asset_id: 'corrugated_iron_02',
    maps: {
      diffuse: URLS.corrugated_iron_02_diffuse,
      normal: URLS.corrugated_iron_02_normal,
      roughness: URLS.corrugated_iron_02_arm,
    },
    scan_coverage_m: SCAN_COVERAGE_M.corrugated_iron_02,
    repeat_basis_source: 'visual_pattern_count:32x6.5cm',
    // M-2：本表面被**栏杆**（2.2×0.9，最大用户）与**落水管**（0.14×3.2）共用 ⇒ `surface_size_m` 取
    // 较大构件（栏杆），basis = min(27, 2.2, 0.9) = **0.9 m** ⇒ 瓦楞节距 0.9/32 ≈ 28 mm。
    // 落水管共用同一贴图实例（repeat 2.44×1）⇒ 0.14 m 管径上约 5 道瓦楞，肉眼可辨（不再是 0.5% 的色块）。
    surface_size_m: [2.2, 0.9],
    metalness: 0.15, roughness: 0.7, envMapIntensity: 1.3, normal_scale: 0.4,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/corrugated_iron_02',
  },
  glass: {
    asset_id: 'brushed_concrete',
    maps: {
      diffuse: URLS.brushed_concrete_diffuse,
      normal: URLS.brushed_concrete_normal,
      roughness: URLS.brushed_concrete_arm,
    },
    scan_coverage_m: SCAN_COVERAGE_M.brushed_concrete,
    repeat_basis_source: 'polyhaven_api_dimensions:2500cm',
    surface_size_m: [1.6, 1.3],
    metalness: 0.0, roughness: 0.6, envMapIntensity: 1.5, normal_scale: 0.2,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/brushed_concrete',
    deviation: '玻璃（REQ W3）**无专用 CC0 扫描**：资产包内无玻璃扫描 ⇒ 复用 `brushed_concrete` 的'
      + '色图/法线/粗糙（当作「积灰 + 微起伏的旧玻璃」），并以半透明（opacity 0.45）+ 高环境反射表达。'
      + '**不伪造**不存在的玻璃 asset id；此偏差已登记。',
    transparent: true,
    opacity: 0.45,
  },
  fabric_cotton: {
    asset_id: 'cotton_jersey',
    maps: { diffuse: URLS.cotton_jersey_diffuse, normal: URLS.cotton_jersey_normal, roughness: URLS.cotton_jersey_arm },
    scan_coverage_m: SCAN_COVERAGE_M.cotton_jersey,
    repeat_basis_source: 'polyhaven_api_dimensions:263.6cm',
    surface_size_m: [0.38, 0.7],
    metalness: 0.0, roughness: 0.9, envMapIntensity: 1.2, normal_scale: 0.3,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/cotton_jersey',
  },
  leather_red: {
    asset_id: 'leather_red_02',
    maps: { diffuse: URLS.leather_red_02_diffuse, normal: URLS.leather_red_02_normal, roughness: URLS.leather_red_02_arm },
    scan_coverage_m: SCAN_COVERAGE_M.leather_red_02,
    repeat_basis_source: 'polyhaven_scale_field:30cm',
    surface_size_m: [0.38, 1.12],
    metalness: 0.0, roughness: 0.7, envMapIntensity: 1.3, normal_scale: 0.35,
    license: 'cc0-1.0', source_library: POLY_HAVEN, asset_page: 'https://polyhaven.com/a/leather_red_02',
  },
};

/**
 * **材质基准**（N4-r3 / R3-3，替代被 architect 打回的 r2 规则）：`repeat_basis_m` = 这张贴图在
 * **这个表面上**被映射到的真实世界尺寸，取自 `BASIS_M` 的**声明值**（依据见 `BASIS_EVIDENCE`）。
 *
 * r2 的旧规则 `basis = min(扫描覆盖, min(构件尺寸))` 已被**打回**，原因是它把两条待验命题变成了
 * **恒真式**（Raven N2-1）：`basis ≤ 扫描覆盖` ⇒ `never_magnified` 永真；`basis ≤ min(尺寸)` ⇒
 * `repeat ≥ 1` 永真。于是判据永远绿，而 `basis` 本身由构件尺寸反推 ⇒ 与被验对象循环。
 *
 * r3 口径：`basis` 是**独立声明量**，由「上游米数」或「贴图内图案单元数 × 物理参照」核定；
 * `repeat = surface_size_m / repeat_basis_m` 是**它的下游结果**。构件小于基准时 `repeat < 1`
 * **是允许且正确的物理结果**（例：1.1 m 的门铺 1.68 m 基准的板贴图 ⇒ 只显示 65% 的贴图）。
 *
 * 代价如实记录：`repeat < 1` 的表面贴图被**放大**，放大倍数 = `扫描覆盖 / 基准`，逐表面给读数
 * （见 `materialReport()` 的 `magnification`）。`glass` 与 `fabric_cotton` 因此记 **GAP**。
 */
export function materialBasisM(declaredBasisM: number): [number, number] {
  return [round6(declaredBasisM), round6(declaredBasisM)];
}

/** 派生 `repeat_basis_m` 与 `repeat`：`repeat = surface_size_m / repeat_basis_m`（AC-3 的「按真实尺度」口径）。 */
function spec(surfaceId: SurfaceId, input: SurfaceInput): SurfaceSpec {
  const repeat_basis_m = materialBasisM(BASIS_M[surfaceId]);
  return {
    ...input,
    repeat_basis_m,
    /** 依据标签 + 画面证据路径（R3-3）：让 `SURFACES` 自描述，判据可直接核。 */
    basis_evidence: BASIS_EVIDENCE[surfaceId],
    repeat: [
      round6(input.surface_size_m[0] / repeat_basis_m[0]),
      round6(input.surface_size_m[1] / repeat_basis_m[1]),
    ],
  };
}

export const SURFACES: Record<SurfaceId, SurfaceSpec> = Object.fromEntries(
  Object.entries(INPUTS).map(([id, input]) => [id, spec(id as SurfaceId, input)]),
) as Record<SurfaceId, SurfaceSpec>;

export const SURFACE_IDS: readonly SurfaceId[] = Object.keys(SURFACES) as SurfaceId[];

/** 需要「水/湿地面」语义的表面（`metalness === 0` 的**字面**口径，REQ W3）。 */
export const WET_SURFACES: readonly SurfaceId[] = ['ground_wet'] as const;

export function materialSpecFor(surface: SurfaceId): SurfaceSpec {
  return SURFACES[surface];
}

/** 贴图 URL 的**去重**列表（供 `material_files_exist_on_disk` / 体积统计用）。 */
export function surfaceMapUrls(): string[] {
  const urls = new Set<string>();
  for (const id of SURFACE_IDS) {
    const spec0 = SURFACES[id];
    urls.add(spec0.maps.diffuse);
    urls.add(spec0.maps.normal);
    urls.add(spec0.maps.roughness);
    for (const extra of [spec0.maps.metalness, spec0.maps.ao]) if (extra) urls.add(extra);
  }
  return [...urls].sort();
}

/**
 * **全部被交付树引用的贴图 URL**（N4-r2 / M-6 关闭 Raven N-7）。
 *
 * 为什么需要它：`material_files_exist_on_disk` 只遍历 `SURFACES`，**看不见**注册表之外的贴图常量 ——
 * 上一轮就因此出过「注册表绿、`SKIN_TEXTURE_URL` 指向已被删掉的文件、画面回落纯色」的盲区，
 * 修复只还原了**那一个文件**、**没有**补上覆盖**这一类**的判据。
 * ⇒ 这里给出**唯一的贴图 URL 登记面**：凡交付树里被引用的贴图都必须登记在这里，
 * 判据遍历它做盘上存在性检查（`skin_pale_diffuse` 就是靠这条被覆盖的）。
 */
export function referencedTextureUrls(): string[] {
  // N4-r3 / R3-7（修正 Raven N2-6 的「人工并集」）：**不再手抄并集** —— 直接从唯一的 URL 登记面
  // `URLS` **机械派生**。手抄并集（旧实现 `[...surfaceMapUrls(), URLS.skin_pale_diffuse]`）的问题：
  // 它只覆盖「今天记得写进去的那几个」，**新增**的 URL 常量会静默逃出盘上存在性检查
  // —— 正是 M-6 要封的那一类盲区。现在任何新增 URL 都自动被覆盖。
  return [...new Set(Object.values(URLS))].sort();
}

/** 人物皮肤贴图 URL（W5；`character.ts` 的装配侧只读它，不做 IO）。 */
export const SKIN_TEXTURE_URL: string = URLS.skin_pale_diffuse;

// ------------------------------------------------------------------ 惰性加载（**只在真 WebGL 下调用**）
export interface MaterialDegradation {
  surface: string;
  code: string;
  detail: string;
}

/** 表面 → 实际绑定读数（浏览器侧；Node 下恒为 `null`）。 */
export interface SurfaceBinding {
  map: boolean;
  normal_map: boolean;
  roughness_map: boolean;
  metalness_map: boolean;
  image_width: number;
  image_height: number;
}

const textureCache = new Map<string, THREE.Texture>();
const degradations: MaterialDegradation[] = [];
const built = new Map<string, THREE.MeshStandardMaterial>();
let loadAttempted = false;

function loadTexture(loader: THREE.TextureLoader, url: string, colour: boolean): THREE.Texture {
  const key = `${url}#${colour ? 'srgb' : 'linear'}`;
  const cached = textureCache.get(key);
  if (cached) return cached.clone();
  const texture = loader.load(url, undefined, undefined, () => {
    degradations.push({ surface: url, code: 'E_TEXTURE_LOAD_FAILED', detail: url });
  });
  texture.colorSpace = colour ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  textureCache.set(key, texture);
  return texture.clone();
}

function applyRepeat(texture: THREE.Texture, repeat: [number, number]): void {
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(repeat[0], repeat[1]);
  texture.needsUpdate = true;
}

/**
 * 把注册表条目变成**真的** `MeshStandardMaterial`（含真实贴图）。
 * `loader === null`（Node / 无 WebGL）⇒ 返回 `null`（**不抛**；调用方回落纯色）。
 * 贴图加载失败 ⇒ **不抛**，记 `degradations`，已加载的部分照常绑定。
 */
export function loadSurfaceMaterials(
  loader: THREE.TextureLoader | null,
  spec0: SurfaceSpec,
  options: { luminanceScale?: number; tint?: string } = {},
): THREE.MeshStandardMaterial | null {
  if (!loader) return null;
  loadAttempted = true;
  const scale = typeof options.luminanceScale === 'number' ? options.luminanceScale : 1;
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color(options.tint ?? '#ffffff').multiplyScalar(scale),
    roughness: spec0.roughness,
    metalness: spec0.metalness,
    envMapIntensity: spec0.envMapIntensity,
    transparent: Boolean(spec0.transparent),
    opacity: spec0.opacity ?? 1,
  });
  try {
    const map = loadTexture(loader, spec0.maps.diffuse, true);
    const normalMap = loadTexture(loader, spec0.maps.normal, false);
    const roughnessMap = loadTexture(loader, spec0.maps.roughness, false);
    applyRepeat(map, spec0.repeat);
    applyRepeat(normalMap, spec0.repeat);
    applyRepeat(roughnessMap, spec0.repeat);
    material.map = map;
    material.normalMap = normalMap;
    material.normalScale = new THREE.Vector2(spec0.normal_scale, spec0.normal_scale);
    material.roughnessMap = roughnessMap;
    material.metalnessMap = roughnessMap;
    built.set(spec0.asset_id + '@' + spec0.surface_size_m.join('x'), material);
  } catch (error) {
    degradations.push({ surface: spec0.asset_id, code: 'E_MATERIAL_BUILD_FAILED', detail: String(error) });
    return null;
  }
  return material;
}

/**
 * **人物皮肤细节层**（W5）：`skin-pale-01` 是平场、无烘焙阴影/高光/方向光的皮肤细节贴图
 * （逐项复核见 `<ws>/03_artisan_self_test.log`）⇒ 只作**乘性细节层**用：绑定 `map`，色锚点仍是
 * `内容包规范肤色 × luminanceScale` ⇒ 既有 `character_material_hex_recomputable` 的语义**逐字不变**。
 * 该表面**不进** `SURFACES`（不是建筑/场地表面，不参与 `material_*` 注册表判据）。
 */
export function loadSkinDetailMaterial(
  loader: THREE.TextureLoader | null,
  options: { luminanceScale?: number; tint?: string } = {},
): THREE.MeshStandardMaterial | null {
  if (!loader) return null;
  loadAttempted = true;
  const scale = typeof options.luminanceScale === 'number' ? options.luminanceScale : 1;
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color(options.tint ?? '#ffffff').multiplyScalar(scale),
    roughness: 0.72,
    metalness: 0,
    envMapIntensity: 1.1,
  });
  try {
    const map = loadTexture(loader, URLS.skin_pale_diffuse, true);
    applyRepeat(map, [1, 1]);
    material.map = map;
    built.set('skin-pale-01@detail', material);
  } catch (error) {
    degradations.push({ surface: 'skin-pale-01', code: 'E_SKIN_DETAIL_FAILED', detail: String(error) });
    return null;
  }
  return material;
}

/** 表面 → 贴图绑定读数（从**真的**材质实例读回；Node 下恒 `null`）。 */
function bindingOf(spec0: SurfaceSpec): SurfaceBinding | null {
  const material = built.get(spec0.asset_id + '@' + spec0.surface_size_m.join('x'));
  if (!material) return null;
  const image = material.map?.image as { width?: number; height?: number } | undefined;
  return {
    map: Boolean(material.map),
    normal_map: Boolean(material.normalMap),
    roughness_map: Boolean(material.roughnessMap),
    metalness_map: Boolean(material.metalnessMap),
    image_width: Number(image?.width ?? 0),
    image_height: Number(image?.height ?? 0),
  };
}

/** 逐表面读数（AC-3 / D-7）：注册表 + 实际绑定 + `degradations`（**必须**暴露）。 */
export function materialReport(): Array<Record<string, unknown>> {
  return SURFACE_IDS.map((id) => {
    const spec0 = SURFACES[id];
    const urls = [spec0.maps.diffuse, spec0.maps.normal, spec0.maps.roughness,
      spec0.maps.metalness, spec0.maps.ao].filter((value): value is string => typeof value === 'string');
    const distinct = [...new Set(urls)];
    return {
      surface: id,
      asset_id: spec0.asset_id,
      license: spec0.license,
      source_library: spec0.source_library,
      asset_page: spec0.asset_page,
      maps: { ...spec0.maps },
      map_count: distinct.length,
      map_urls: distinct,
      repeat: spec0.repeat,
      scan_coverage_m: spec0.scan_coverage_m,
      material_basis_m: spec0.repeat_basis_m,
      repeat_basis_m: spec0.repeat_basis_m,
      repeat_basis_source: spec0.repeat_basis_source,
      /** 依据标签（`upstream` / `visually_corrected`）与画面证据路径（R3-3）。 */
      basis_evidence: BASIS_EVIDENCE[id],
      /** 贴图相对源照片的**放大倍数** = 扫描覆盖 / 基准（>1 ⇒ 放大）。r2 声称「永不放大」，已被打回。 */
      magnification: [
        round6(spec0.scan_coverage_m / spec0.repeat_basis_m[0]),
        round6(spec0.scan_coverage_m / spec0.repeat_basis_m[1]),
      ],
      /** 贴图在构件上被显示的比例（`repeat` 的倒数意义）：< 1 ⇒ 只显示贴图的一部分。 */
      surface_size_m: spec0.surface_size_m,
      metalness: spec0.metalness,
      roughness: spec0.roughness,
      envMapIntensity: spec0.envMapIntensity,
      normal_scale: spec0.normal_scale,
      transparent: Boolean(spec0.transparent),
      deviation: spec0.deviation ?? null,
      load_attempted: loadAttempted,
      bound: bindingOf(spec0),
      degradations: degradations.filter((entry) => distinct.includes(entry.surface)
        || entry.surface === spec0.asset_id),
    };
  });
}

/** 主材质 `envMapIntensity` 的最小值（AC-1 的机器读数；纯数据，Node 可读）。 */
export function envMapIntensityMin(): number {
  return SURFACE_IDS.reduce((min, id) => Math.min(min, SURFACES[id].envMapIntensity), Number.POSITIVE_INFINITY);
}
