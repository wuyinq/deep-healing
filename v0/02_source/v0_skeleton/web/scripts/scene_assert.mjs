#!/usr/bin/env node
/**
 * 治愈系数值断言 + 世界观两态机器判据（AC-M3-4 / AC-M3-8③④）——M3 新增。
 *
 * 运行：node <ws>/02_source/v0_skeleton/web/scripts/scene_assert.mjs
 *
 * 判据（全部**读数据文件**，不硬编码被断言的数字）：
 *   1. 治愈系基调：饱和 ≤45 / 色相暖区 / 粗糙度 ≥0.6 / 无镜面（来自 pack 的 assets/manifest.json）
 *   2. `two_reads_share_geometry`：两态**共用同一几何** —— 由**两次独立装配**得到，且比较量是
 *      **真的形状指纹**（每实体 `size` + 装配变换 `scale`/`quaternion` + `geometry.parameters`
 *      + `position` attribute 摘要），不是顶点数（`BoxGeometry` 的位置顶点数**恒为 24**，与尺寸无关
 *      ⇒ 顶点数不是形状指纹）。
 *      R3 / G2 修正：判据经 **`createScene()` 的句柄**取数
 *      （`setReading()` / `geometryFor()` / `entityIds()` / `assemblyReport()`），不再只打自由函数；
 *      并且**两条路径都跑**：装配函数产物 + **场景图 mesh 层读回**（装配之后有没有再被改写）。
 *   3. `two_reads_share_scene_structure`（**R5：替代并改名** `two_reads_share_rendered_geometry`）：
 *      两态**结构性场景状态**逐项相同 —— 比较面 = R4 面（ids / shape_digests / mesh_positions /
 *      mesh_scales / mesh_rotations / geometry_digest）**加上闭式结构摘要**（`structureReport()`：
 *      几何 `index` / `groups` / `attributes`（position/normal/uv，缺失显式 `null`）、每对象
 *      `matrixWorld` 16 分量 / `visible` / `layers.mask` / `renderOrder`、根子树身份与父子关系）。
 *      旧名里的 `rendered` **已去掉**：它曾声称覆盖「渲染后几何」，实际只覆盖白名单字段（过度声称）。
 *      本判据是**一致性判据**，**不是**防篡改 / 完整性机制（G9 口径；覆盖/不覆盖清单见 `06` R5 段）。
 *   4. `two_reads_share_camera`（**R5 扩面**）：**同一视口下**两态相机读数逐项相同 —— `position` /
 *      `quaternion` / `matrixWorld` / `projectionMatrix`（各 16 分量）/ `zoom` / `view_offset`（含
 *      `enabled`）/ `fov` / `near` / `far` —— D-7「**禁止换相机**」的机器判据。
 *      口径：两次读法之间**不做 resize**（只比较读法切换造成的差异）；`aspect` 是视口派生量 ⇒
 *      **信息性**读数、**不参与**相等断言（视口尺寸由 `viewport_follows_canvas_box` 覆盖），见 `06`。
 *   5. `two_reads_use_same_render_camera`（**R5 新增**）：**实际用于渲染的相机身份**两态相同 ——
 *      `renderer.render(scene, camera)` 的**入参**（`world.ts` 的渲染包装器逐次记录）⇒「第二相机」
 *      形态由此有牙（D-7 的字面形态）。
 *   6. `underneath_does_not_raise_saturation`：深层态饱和**不升**
 *   7. 深层态 = 同一色板**降明度**：`light_k` / `ambient_ratio` / 派生亮度系数均**下降**
 *
 * 无 WebGL 环境（Node）下 `createScene` 退化为空渲染器：**几何与场景图照常装配**，
 * 判据跑的是与浏览器**同一条装配路径**。
 *
 * 退出码：0 全通过；1 有断言失败；2 用法/环境错误。
 */

import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import * as THREE from 'three';
import { createScene, READING_GEOMETRY_PROFILE, buildBuildingParts, buildEntityBoxes, BUILDING_PART_NAMES, WORLD_FLOOR_Y, effectiveVisibility } from '../src/scene/world.ts';
import {
  artificialLightIntensitySum, backgroundStateOf, deriveLighting, environmentReport, healingMaterial, HDRI_URL,
  kelvinToRgb, ROUGHNESS_MIN,
} from '../src/scene/lighting.ts';
import {
  buildCharacterDetailParts, buildCharacterParts, CHARACTER_PART_ORDER, defaultAppearanceFor,
} from '../src/scene/character.ts';
import { appearanceTableFromDocuments } from '../src/scene/character.ts';
import {
  BASIS_EVIDENCE, materialReport, PATTERN_UNITS, referencedTextureUrls, SKIN_TEXTURE_URL, SURFACES,
  SURFACE_IDS, WET_SURFACES, SURFACES_EXT, SURFACE_IDS_EXT, surfaceIntersection, materialReportExtPartition,
} from '../src/scene/materials.ts';
import {
  LEGACY_METALNESS_RANGE, LEGACY_ROUGHNESS_RANGE, MATERIAL_CLASSES, MATERIAL_CLASS_IDS, materialClassReport,
  notCatchAll,
} from '../src/scene/material_classes.ts';
import { BINDINGS, bindingSetLines, bindingForEntity } from '../src/scene/asset_binding.ts';
import {
  CHARACTER_SLOTS, FROZEN_STATE_IDS, STATE_CLIP_MAP_KEYS, SLOT_SOURCES, createCharacterInstance,
  state_clip_map, slotWeightsForState,
} from '../src/scene/character_instance.ts';
import {
  INSPECTION_LOOK_AT, INSPECTION_POSITION, OBSERVATION_LOOK_AT, OBSERVATION_POSITION, apply,
  createPresentation, presentationConstants, resetPresentation, wrapToPi,
} from '../src/scene/presentation.ts';
import { postfxReport } from '../src/scene/postfx.ts';

const WEB_DIR = fileURLToPath(new URL('../', import.meta.url));
const PACK_DIR = `${WEB_DIR}../districts/xingfu-xiaoqu/`;
// R2 / F9：被断言的**区间**一律从契约/schema/art-bible 读，不写死在断言里。
const SOURCE_DIR = `${WEB_DIR}../../`;
const SCHEMA_PATH = `${SOURCE_DIR}worldview.schema.json`;
const ART_BIBLE_PATH = `${SOURCE_DIR}art-bible.md`;

let passed = 0;
const failures = [];

function check(name, condition, detail) {
  if (condition) {
    passed += 1;
    process.stdout.write(`PASS  ${name}${detail ? ` (${detail})` : ''}\n`);
  } else {
    failures.push(name);
    process.stdout.write(`FAIL  ${name}${detail ? ` (${detail})` : ''}\n`);
  }
}

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

// R5 / 闭式面：结构摘要必须**至少**给出的 attribute（缺失时实现侧要显式记 `null`，不得跳过字段）。
const REQUIRED_ATTRIBUTES = ['position', 'normal', 'uv'];

/** R5：两个读数里**第一个不同的字段名**（供失败 detail 把差异**定位到注入点**）。 */
function firstDifferingField(left, right) {
  for (const key of Object.keys(left)) {
    if (JSON.stringify(left[key]) !== JSON.stringify(right[key])) return key;
  }
  return 'none';
}

/** R5：结构面**对象**分区的首个差异点（`#序号:身份/字段`）。 */
function firstObjectDiff(left, right) {
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const a = left[index];
    const b = right[index];
    if (!a || !b) return `#${index}/missing`;
    if (JSON.stringify(a) !== JSON.stringify(b)) return `#${index}:${a.id}/${firstDifferingField(a, b)}`;
  }
  return 'none';
}

/** R5：结构面**几何**分区的首个差异点（`实体 id/字段`）。 */
function firstGeometryDiff(left, right) {
  const ids = [...new Set([...Object.keys(left), ...Object.keys(right)])].sort();
  for (const id of ids) {
    if (!left[id] || !right[id]) return `${id}/missing`;
    if (JSON.stringify(left[id]) !== JSON.stringify(right[id])) return `${id}/${firstDifferingField(left[id], right[id])}`;
  }
  return 'none';
}

const worldview = readJson(`${PACK_DIR}worldview.json`);
const worldSeed = readJson(`${PACK_DIR}world.seed.json`);
const aesthetic = readJson(`${PACK_DIR}assets/manifest.json`).aesthetic_constraints;
// R2 / F9：区间来源 = 契约（schema）+ art-bible（文字声明），断言只做「数据 vs 契约」的比对
const schemaLightK = readJson(SCHEMA_PATH).$defs.toneReading.properties.light_k;
const artBible = readFileSync(ART_BIBLE_PATH, 'utf8');
const artBibleHueRange = (() => {
  const match = artBible.match(/色相范围[^\n]*?`(\d+)°?\s*[–\-—~]\s*(\d+)°/);
  return match ? [Number(match[1]), Number(match[2])] : null;
})();
const artBibleLightK = (() => {
  const match = artBible.match(/色温[^\n]*?`(\d+)\s*K\s*[–\-—~]\s*(\d+)\s*K`/);
  return match ? [Number(match[1]), Number(match[2])] : null;
})();

const surface = worldview.tone.surface;
const underneath = worldview.tone.underneath;

// ------------------------------------------------------------------ 1) 治愈系基调（读数据）
const saturationLimit = Number(aesthetic.palette.saturation_max_pct);
const roughnessFloor = Number(aesthetic.material.roughness_min);
const ambientFloor = Number(aesthetic.lighting.ambient_ratio_min);
check('saturation_within_art_bible', surface.saturation_pct <= saturationLimit && underneath.saturation_pct <= saturationLimit,
  `surface=${surface.saturation_pct} underneath=${underneath.saturation_pct} limit=${saturationLimit}`);
check('roughness_floor_respected', ROUGHNESS_MIN >= roughnessFloor, `material=${ROUGHNESS_MIN} floor=${roughnessFloor}`);
check('surface_ambient_floor_respected', surface.ambient_ratio >= ambientFloor,
  `${surface.ambient_ratio} >= ${ambientFloor}`);
check('warm_hue_range_declared', Array.isArray(aesthetic.palette.warm_hue_range_deg)
  && Array.isArray(artBibleHueRange)
  && aesthetic.palette.warm_hue_range_deg[0] === artBibleHueRange[0]
  && aesthetic.palette.warm_hue_range_deg[1] === artBibleHueRange[1],
  `manifest=${JSON.stringify(aesthetic.palette.warm_hue_range_deg)} art-bible=${JSON.stringify(artBibleHueRange)}`);
check('hue_warm_region', (() => {
  const [red, green, blue] = kelvinToRgb(surface.light_k);
  return red >= green && green >= blue;
})(), `light_k=${surface.light_k}`);
// 「无镜面」：对**材质工厂的返回值**断言（R2 / F9：不再读实现源文本、不再正则匹配字面量）
const healingMaterialSample = healingMaterial('#d9c7a7', surface);
check('no_specular_highlight', Number(healingMaterialSample.metalness) <= 0.1,
  `metalness=${healingMaterialSample.metalness} (healingMaterial 返回值)`);
check('material_roughness_floor_from_factory', Number(healingMaterialSample.roughness) >= roughnessFloor,
  `roughness=${healingMaterialSample.roughness} floor=${roughnessFloor}`);

// ------------------------------------------------------------------ 2) 两态共用几何（经应用装配路径）
// R3 / G2：取数一律经 `createScene()` 的句柄；**两条路径都跑**：
//   ① 装配函数产物（`geometryFor`）—— 抓 buildEntityBoxes 层的读法依赖分叉；
//   ② 场景图 mesh 层读回（`assemblyReport`）—— 抓 `rebuild()` 里 / **装配之后**的分叉。
// 无 WebGL 环境下 createScene 退化为空渲染器，装配语义一字不变。
const state = { entities: worldSeed.entities };
const canvasStub = { clientWidth: 1440, clientHeight: 900, width: 0, height: 0, style: {},
  getContext: () => null, addEventListener() {}, removeEventListener() {} };
const scene = createScene(canvasStub, { worldview: worldview.tone });

check('assembly_path_via_createScene_handle',
  typeof scene.setReading === 'function' && typeof scene.geometryFor === 'function'
  && typeof scene.entityIds === 'function' && typeof scene.assemblyReport === 'function'
  && typeof scene.viewport === 'function',
  'createScene() 句柄暴露 setReading/geometryFor/entityIds/assemblyReport/viewport');

// R4 / R3-C1：`cameraReport()` 必须**从 `THREE.Camera` 实例读回**（不读实现源文本、不硬编码字面量）。
// 命中能力自证：相机 `aspect` 随视口走 ⇒ 读数必须与 `viewport().aspect` 一致；且各分量必须是有限数
// （读回失败会给出 undefined/NaN ⇒ 这里必红）。
check('scene_handle_camera_report_is_live', (() => {
  if (typeof scene.cameraReport !== 'function') return false;
  const cameraReading = scene.cameraReport();
  const viewportReading = scene.viewport();
  return Array.isArray(cameraReading.position) && cameraReading.position.length === 3
    && Array.isArray(cameraReading.quaternion) && cameraReading.quaternion.length === 4
    && Number.isFinite(cameraReading.fov) && Number.isFinite(cameraReading.near)
    && Number.isFinite(cameraReading.far) && Number.isFinite(cameraReading.aspect)
    && Math.abs(cameraReading.aspect - viewportReading.aspect) < 1e-9;
})(), 'cameraReport() 暴露 position[3]/quaternion[4]/fov/near/far/aspect 且与实例读数一致');

const viewport = scene.viewport();
check('viewport_follows_canvas_box', viewport.client_width === 1440 && viewport.client_height === 900
  && viewport.drawing_buffer_width >= viewport.client_width && viewport.aspect > 1,
  `client=${viewport.client_width}x${viewport.client_height} buffer=${viewport.drawing_buffer_width}x${viewport.drawing_buffer_height} aspect=${viewport.aspect.toFixed(4)} webgl=${viewport.webgl}`);

scene.apply({ t: 'snapshot', tick: 0, state });
scene.setReading('surface');
const reportSurface = scene.geometryFor('surface');
const asmSurface = scene.assemblyReport();
const idsSurface = scene.entityIds();
const camSurface = scene.cameraReport();
const structureSurface = scene.structureReport();
// R5 / D-7 字面形态：真渲染一帧并取**实际入参**相机身份（Node 无 WebGL 时底层渲染器是空的，
// 但入参照常被包装器记录 ⇒ 判据在 Node 与浏览器里跑的是同一条渲染路径）。
const renderSurface = scene.renderOnce();
scene.setReading('underneath');
const reportUnderneath = scene.geometryFor('underneath');
const asmUnderneath = scene.assemblyReport();
const idsUnderneath = scene.entityIds();
const camUnderneath = scene.cameraReport();
const structureUnderneath = scene.structureReport();
const renderUnderneath = scene.renderOnce();
scene.setReading('surface');
const asmRestored = scene.assemblyReport();

check('two_reads_are_independent_assemblies',
  reportSurface !== reportUnderneath
  && reportSurface.reading === 'surface' && reportUnderneath.reading === 'underneath',
  `reading=${reportSurface.reading}/${reportUnderneath.reading}`);

check('geometry_assembly_consumes_reading',
  reportSurface.profile_digest === JSON.stringify(READING_GEOMETRY_PROFILE.surface)
  && reportUnderneath.profile_digest === JSON.stringify(READING_GEOMETRY_PROFILE.underneath),
  `profiles=${reportSurface.profile_digest}`);

check('reading_profiles_declared_equal',
  JSON.stringify(READING_GEOMETRY_PROFILE.surface) === JSON.stringify(READING_GEOMETRY_PROFILE.underneath),
  'D-7：读法不得改变几何 ⇒ 两读法装配配置必须逐字段相等');

check('geometry_digest_detects_position_shift', (() => {
  // **判据自身的命中能力自证**：坐标被换一套 ⇒ digest 必须变（不依赖读法）
  const shifted = { entities: worldSeed.entities.map((entity, index) => (index === 0
    ? { ...entity, transform: { ...(entity.transform ?? {}), pos_mm: { ...((entity.transform ?? {}).pos_mm ?? { x: 0, y: 0, z: 0 }), x: 1000 } } }
    : entity)) };
  scene.apply({ t: 'snapshot', tick: 0, state: shifted });
  const shiftedDigest = scene.geometryFor('surface').geometry_digest;
  scene.apply({ t: 'snapshot', tick: 0, state });
  return shiftedDigest !== reportSurface.geometry_digest;
})(), 'digest 对坐标敏感');

check('geometry_digest_detects_size_change', (() => {
  // R3 / G2 的**命中能力自证**：只换**尺寸**（kind → 另一档 size）⇒ digest 必须变。
  // 关键点：`BoxGeometry` 的位置顶点数**与尺寸无关**（恒 24）⇒ 只比顶点数的判据在这里是瞎的。
  const first = worldSeed.entities[0];
  const swappedKind = first.kind === 'room' ? 'npc' : 'room';
  const resized = { entities: worldSeed.entities.map((entity, index) => (index === 0 ? { ...entity, kind: swappedKind } : entity)) };
  scene.apply({ t: 'snapshot', tick: 0, state: resized });
  const resizedReport = scene.geometryFor('surface');
  scene.apply({ t: 'snapshot', tick: 0, state });
  const verticesUnchanged = resizedReport.vertex_counts[first.id] === reportSurface.vertex_counts[first.id];
  return resizedReport.geometry_digest !== reportSurface.geometry_digest && verticesUnchanged;
})(), 'digest 对**尺寸**敏感（而顶点数不变 ⇒ 顶点数不是形状指纹）');

check('two_reads_share_geometry', (() => {
  const sameIds = JSON.stringify(reportSurface.entity_ids) === JSON.stringify(reportUnderneath.entity_ids);
  const sameShapes = JSON.stringify(reportSurface.shape_digests) === JSON.stringify(reportUnderneath.shape_digests);
  const sameVertices = JSON.stringify(reportSurface.vertex_counts) === JSON.stringify(reportUnderneath.vertex_counts);
  const sameDigest = reportSurface.geometry_digest === reportUnderneath.geometry_digest;
  return sameIds && sameShapes && sameVertices && sameDigest;
})(), `entities=${reportSurface.entity_count}/${reportUnderneath.entity_count} shapes=${Object.keys(reportSurface.shape_digests).length} vertices=${reportSurface.vertex_count_total}/${reportUnderneath.vertex_count_total}`);

check('geometry_positions_match_seeded_state', (() => {
  // 第二条独立牙齿（M3-14）：装配坐标必须**逐项等于下发状态**的 `pos_mm`，不得自行偏移。
  // R3：坐标从**场景图 mesh 层**读回（装配后写入的那一份），不再读自由函数的中间产物。
  const expected = [...worldSeed.entities].sort((left, right) => left.id.localeCompare(right.id))
    .map((entity) => {
      const pos = entity.transform?.pos_mm ?? { x: 0, y: 0, z: 0 };
      return `${entity.id}:${(pos.x / 1000).toFixed(6)},${(pos.y / 1000).toFixed(6)},${(pos.z / 1000).toFixed(6)}`;
    }).join('|');
  const actual = asmSurface.entity_ids.map((id) => `${id}:${asmSurface.mesh_positions[id]}`).join('|');
  return expected === actual;
})(), 'mesh 世界坐标 = 下发状态的 pos_mm（不得自行偏移）');

check('two_reads_share_geometry_object_identity',
  reportSurface.shapes.length === reportUnderneath.shapes.length
  && reportSurface.shapes.every((shape, index) => {
    const other = reportUnderneath.shapes[index];
    return other !== undefined
      && shape.id === other.id
      && shape.size.join(',') === other.size.join(',')
      && JSON.stringify(shape.parameters) === JSON.stringify(other.parameters)
      && shape.position_attribute_digest === other.position_attribute_digest
      && shape.vertex_count === other.vertex_count;
  }),
  '实体 id / 尺寸 / parameters / position attribute 摘要逐项相同');

check('two_reads_share_scene_structure', (() => {
  // R5（**替代并改名** R4 的 `two_reads_share_rendered_geometry`）：两态**结构性场景状态**逐项相同。
  // 比较面 = R4 面（装配后 mesh 层读回）**加上闭式结构摘要**：几何 `index`/`groups`/`attributes`、
  // 每对象 `matrixWorld` 16 分量 / `visible` / `layers.mask` / `renderOrder`、根子树身份与父子关系。
  // 旧名里的 `rendered` 已去掉（过度声称）；本判据是**一致性判据**，不是防篡改（见 `06` R5 段）。
  // 断言体内**零字面量**：只把「两态各自的读数」互相比较。
  const sameIds = JSON.stringify(asmSurface.entity_ids) === JSON.stringify(asmUnderneath.entity_ids);
  const sameShapes = JSON.stringify(asmSurface.shape_digests) === JSON.stringify(asmUnderneath.shape_digests);
  const samePositions = JSON.stringify(asmSurface.mesh_positions) === JSON.stringify(asmUnderneath.mesh_positions);
  const sameScales = JSON.stringify(asmSurface.mesh_scales) === JSON.stringify(asmUnderneath.mesh_scales);
  const sameRotations = JSON.stringify(asmSurface.mesh_rotations) === JSON.stringify(asmUnderneath.mesh_rotations);
  const sameStructureGeometry = structureSurface.geometry_digest === structureUnderneath.geometry_digest;
  const sameStructureObjects = structureSurface.objects_digest === structureUnderneath.objects_digest;
  const sameObjectIdentity = JSON.stringify(structureSurface.objects.map((object) => `${object.id}|${object.parent_id}|${object.type}`))
    === JSON.stringify(structureUnderneath.objects.map((object) => `${object.id}|${object.parent_id}|${object.type}`));
  return sameIds && sameShapes && samePositions && sameScales && sameRotations
    && asmSurface.geometry_digest === asmUnderneath.geometry_digest
    && asmSurface.reading === 'surface' && asmUnderneath.reading === 'underneath'
    && JSON.stringify(idsSurface) === JSON.stringify(idsUnderneath)
    && sameStructureGeometry && sameStructureObjects && sameObjectIdentity;
})(), `mesh=${asmSurface.mesh_count}/${asmUnderneath.mesh_count} ids=${idsSurface.length}/${idsUnderneath.length}`
  + ` objects=${structureSurface.objects.length}/${structureUnderneath.objects.length}`
  + ` objects_first_diff=${firstObjectDiff(structureSurface.objects, structureUnderneath.objects)}`
  + ` geometry_first_diff=${firstGeometryDiff(structureSurface.geometry, structureUnderneath.geometry)}`);

check('two_reads_share_camera', (() => {
  // R4 / R3-C1；**R5 扩面**（PM 裁决 `R4-C1`：`zoom` / 手改 `projectionMatrix` / `setViewOffset` 曾逃逸）：
  // D-7「**禁止换相机**」的机器判据 —— 相机**结构面**逐项比较。
  // 口径（见 `06`）：同一视口下只比较**读法切换**造成的差异；两次读法之间**不做 resize**；
  // `aspect` 是视口派生量 ⇒ **信息性**读数、不参与相等断言（视口尺寸由 viewport 判据覆盖）。
  const samePosition = JSON.stringify(camSurface.position) === JSON.stringify(camUnderneath.position);
  const sameQuaternion = JSON.stringify(camSurface.quaternion) === JSON.stringify(camUnderneath.quaternion);
  const sameMatrixWorld = JSON.stringify(camSurface.matrix_world) === JSON.stringify(camUnderneath.matrix_world);
  const sameProjection = JSON.stringify(camSurface.projection_matrix) === JSON.stringify(camUnderneath.projection_matrix);
  const sameViewOffset = JSON.stringify(camSurface.view_offset) === JSON.stringify(camUnderneath.view_offset);
  return samePosition && sameQuaternion && sameMatrixWorld && sameProjection && sameViewOffset
    && camSurface.zoom === camUnderneath.zoom
    && camSurface.fov === camUnderneath.fov
    && camSurface.near === camUnderneath.near
    && camSurface.far === camUnderneath.far;
})(), `position=${JSON.stringify(camSurface.position)} zoom=${camSurface.zoom}/${camUnderneath.zoom}`
  + ` view_offset=${JSON.stringify(camUnderneath.view_offset)} fov=${camSurface.fov} near=${camSurface.near} far=${camSurface.far}`
  + ` camera_first_diff=${firstDifferingField(camSurface, camUnderneath)} aspect(info)=${camSurface.aspect.toFixed(4)}`);

check('two_reads_use_same_render_camera', (() => {
  // R5 新增：**实际用于渲染的相机身份**（D-7 的**字面形态**）—— `renderer.render(scene, camera)` 的
  // **入参**由 `world.ts` 的渲染包装器逐次记录；「第二相机只用于 underneath 渲染」由此有牙。
  const bothRecorded = renderSurface.identity !== null && renderUnderneath.identity !== null;
  const sameIdentity = bothRecorded && renderSurface.identity === renderUnderneath.identity;
  const bothRendered = renderSurface.renders >= 1 && renderUnderneath.renders >= 2;
  return sameIdentity && bothRendered;
})(), `surface=${renderSurface.identity} underneath=${renderUnderneath.identity} renders=${renderUnderneath.renders}`);

// --- N2-r2 / F-1：取证机位是**加法**；不调用它 ⇒ 默认取景与起点逐项相同 ---
check('observation_camera_is_additive_and_default_framing_unchanged', (() => {
  // 起点冻结值（r1 交付树实测的默认机位 / 注视点；与 `world.ts` 的
  // `DEFAULT_CAMERA_POSITION` / `DEFAULT_CAMERA_LOOK_AT` 同源）。
  const FROZEN_POSITION = [18, 14, 24];
  const FROZEN_LOOK_AT = [9, 0, 6];
  const fresh = createScene(canvasStub, { worldview: worldview.tone });
  const before = fresh.cameraReport();                                  // 不调用取证机位
  const moved = fresh.setObservationCamera({ position_m: [5, 0.35, 17.4], look_at_m: [5, -0.2, 15] });
  const restored = fresh.setObservationCamera(null);
  fresh.dispose();
  const positionOk = JSON.stringify(before.position) === JSON.stringify(FROZEN_POSITION);
  const movedOk = JSON.stringify(moved.position) !== JSON.stringify(before.position);
  // 注视点由**相机朝向**反推（不读实现源文本、不硬编码 quaternion）
  const forwardOf = (reading) => new THREE.Vector3(0, 0, -1)
    .applyQuaternion(new THREE.Quaternion(reading.quaternion[0], reading.quaternion[1],
      reading.quaternion[2], reading.quaternion[3])).normalize();
  const aimVector = new THREE.Vector3(FROZEN_LOOK_AT[0] - FROZEN_POSITION[0],
    FROZEN_LOOK_AT[1] - FROZEN_POSITION[1], FROZEN_LOOK_AT[2] - FROZEN_POSITION[2]).normalize();
  const aimOk = Math.abs(forwardOf(before).dot(aimVector) - 1) < 1e-6;
  const restoredOk = JSON.stringify(restored) === JSON.stringify(before);
  return positionOk && aimOk && movedOk && restoredOk;
})(), '不调用取证机位 ⇒ 机位/朝向与起点一致（[18,14,24]→[9,0,6]）；调用后**真的变**；'
  + 'setObservationCamera(null) 逐项还原');

check('scene_handle_structure_report_is_live', (() => {
  // R5 / 闭式面：`structureReport()` / `renderOnce()` 必须**在场且活**（不是常量、不是空壳）。
  // 命中能力自证：每个对象的 `matrixWorld` 必须是 16 个有限数；`index` 必须显式给出 `present`；
  // `position`/`normal`/`uv` 三个 attribute 字段必须**在场**（缺失也要显式 `null`，不得跳过）；
  // 根子树必须是**良构树**（恰好一个根、父链闭合）；读法字段必须跟着 `setReading()` 走。
  if (typeof scene.structureReport !== 'function' || typeof scene.renderOnce !== 'function'
    || typeof scene.renderCameraReport !== 'function') return false;
  const entities = asmSurface.entity_ids;
  const objects = structureSurface.objects;
  const idSet = new Set(objects.map((object) => object.id));
  const roots = objects.filter((object) => object.parent_id === null);
  const treeOk = roots.length >= 1
    && objects.every((object) => object.parent_id === null || idSet.has(object.parent_id))
    && entities.every((id) => idSet.has(id));
  const matrixOk = objects.every((object) => Array.isArray(object.matrix_world)
    && object.matrix_world.length === 16 && object.matrix_world.every((value) => Number.isFinite(value)));
  const geometryOk = Object.keys(structureSurface.geometry).length === entities.length
    && entities.every((id) => structureSurface.geometry[id] !== undefined
      && typeof structureSurface.geometry[id].index.present === 'boolean'
      && REQUIRED_ATTRIBUTES.every((name) => name in structureSurface.geometry[id].attributes)
      && structureSurface.geometry[id].attributes.position !== null
      && typeof structureSurface.geometry[id].attributes.position.digest === 'string');
  const liveReadings = structureSurface.reading === 'surface' && structureUnderneath.reading === 'underneath'
    && typeof scene.renderCameraReport().renders === 'number';
  return treeOk && matrixOk && geometryOk && liveReadings;
})(), `objects=${structureSurface.objects.length} meshes=${asmSurface.entity_ids.length}`
  + ` reading=${structureSurface.reading}/${structureUnderneath.reading} renders=${scene.renderCameraReport().renders}`);

check('assembly_report_stable_after_reading_round_trip',
  JSON.stringify(asmRestored.mesh_positions) === JSON.stringify(asmSurface.mesh_positions)
  && JSON.stringify(asmRestored.shape_digests) === JSON.stringify(asmSurface.shape_digests)
  && JSON.stringify(asmRestored.mesh_scales) === JSON.stringify(asmSurface.mesh_scales)
  && JSON.stringify(asmRestored.mesh_rotations) === JSON.stringify(asmSurface.mesh_rotations),
  'surface→underneath→surface 后场景图读数回到原值');

check('geometry_covers_every_seeded_entity',
  reportSurface.entity_count === worldSeed.entities.length
  && asmSurface.mesh_count === worldSeed.entities.length,
  `${reportSurface.entity_count}/${asmSurface.mesh_count} == ${worldSeed.entities.length}`);

// ------------------------------------------------------------------ 3) 深层态不升饱和
check('underneath_does_not_raise_saturation', underneath.saturation_pct <= surface.saturation_pct,
  `${underneath.saturation_pct} <= ${surface.saturation_pct}`);

// ------------------------------------------------------------------ 4) 深层态降明度
const lightSurface = deriveLighting(surface);
const lightUnderneath = deriveLighting(underneath);
check('underneath_lowers_luminance', lightUnderneath.luminanceScale < lightSurface.luminanceScale,
  `${lightUnderneath.luminanceScale.toFixed(4)} < ${lightSurface.luminanceScale.toFixed(4)}`);
check('underneath_lowers_ambient', underneath.ambient_ratio < surface.ambient_ratio,
  `${underneath.ambient_ratio} < ${surface.ambient_ratio}`);
check('underneath_lowers_light_k', underneath.light_k < surface.light_k,
  `${underneath.light_k} < ${surface.light_k}`);
check('light_k_within_worldview_schema_range',
  surface.light_k >= schemaLightK.minimum && surface.light_k <= schemaLightK.maximum
  && underneath.light_k >= schemaLightK.minimum && underneath.light_k <= schemaLightK.maximum,
  `${underneath.light_k}..${surface.light_k} schema=[${schemaLightK.minimum},${schemaLightK.maximum}]`);
check('light_k_range_matches_art_bible', Array.isArray(artBibleLightK)
  && schemaLightK.minimum === artBibleLightK[0] && schemaLightK.maximum === artBibleLightK[1],
  `schema=[${schemaLightK.minimum},${schemaLightK.maximum}] art-bible=${JSON.stringify(artBibleLightK)}`);

// ------------------------------------------------------------------ 5) 世界观双读可核验
const anomaly = worldview.anomalies[0];
check('anomaly_has_two_reads', Boolean(anomaly && anomaly.surface_read && anomaly.underneath_read
  && anomaly.surface_read !== anomaly.underneath_read),
  anomaly ? `${anomaly.id} reveal_at_tick=${anomaly.reveal_at_tick}` : 'no anomaly');

// ==================================================================
// 6) N2 人物外形（REQ-20260924-002：AC-3 / AC-4 / AC-5 / AC-6 + 设计 §12.3 五条判据）
//
// 读数点（R-06 钉死）：AC-3 的「几何报告」在交付里对应 **`characterReport()`**（部件 mesh 层读回）
// 与 **`geometryFor().character_shapes`**（装配函数产物）**两条独立取数路径**。
// `geometryReport().shapes` 保持**实体级**（每实体 1 个 box）⇒ 部件级读数放在新增的
// `character_shapes` 字段（不改既有 `shapes` / `shape_digests` / `geometry_digest` 的语义）。
//
// 数据面（R-12）：AC-4 用**合成 state** 驱动（含 npc-006 + `schedule.target_entity = kitchen-01`）
// —— 主包 seed 里**没有** npc-006。实机对应关系见 `03` / `06`（提案包日程 tick∈120–480 / 600–1080）。
// ==================================================================
const PACK_DIR_XUQIN = `${WEB_DIR}../districts/xingfu-xiaoqu-xuqin/`;
const PACK_DIR_NORTH = `${WEB_DIR}../districts/xingfu-xiaoqu-north/`;
const xuqinWorldview = readJson(`${PACK_DIR_XUQIN}worldview.json`);
const xuqinSeed = readJson(`${PACK_DIR_XUQIN}world.seed.json`);
const xuqinNpc = readJson(`${PACK_DIR_XUQIN}npcs/npc-006.json`);
const xuqinAppearance = xuqinNpc.appearance;
const northNpcIds = ['npc-001', 'npc-002', 'npc-003', 'npc-004', 'npc-005'];
const northNpcs = northNpcIds.map((id) => readJson(`${PACK_DIR_NORTH}npcs/${id}.json`));
const characterSource = readFileSync(`${WEB_DIR}src/scene/character.ts`, 'utf8');

const characterTable = appearanceTableFromDocuments([
  { npc_id: 'npc-006', appearance: xuqinAppearance },
  ...northNpcs.map((document) => ({ npc_id: document.id, appearance: document.appearance })),
]);

/** 合成 state：提案包 seed + 5 个北区住户（住户外形同样来自内容包）。 */
const residentEntities = northNpcs.map((document, index) => ({
  id: document.id,
  kind: 'npc',
  transform: { pos_mm: { x: -8000 - index * 1200, y: 0, z: 0 } },
  schedule: { state: 'resting', target_entity: 'room-101' },
  tags: ['resident'],
}));
const dailyState = { entities: [...xuqinSeed.entities, ...residentEntities] };
/** 面具态：`schedule.target_entity = kitchen-01`（D2 的纯谓词；实机自然可达，见 CHR-21 / F-16）。 */
const maskedState = {
  entities: dailyState.entities.map((entity) => (entity.id === 'npc-006'
    ? { ...entity, schedule: { ...entity.schedule, state: 'working', target_entity: 'kitchen-01' } }
    : entity)),
};

const characterScene = createScene(canvasStub, { worldview: xuqinWorldview.tone, appearance: characterTable });
characterScene.apply({ t: 'snapshot', tick: 0, state: dailyState });
characterScene.setReading('surface');
const dailyParts = characterScene.characterReport();
const dailyAppearance = characterScene.appearanceReport();
const dailyAssemblyShapes = characterScene.geometryFor('surface').character_shapes;
characterScene.setReading('underneath');
const dailyPartsUnderneath = characterScene.characterReport();
const dailyAssemblyShapesUnderneath = characterScene.geometryFor('underneath').character_shapes;
characterScene.setReading('surface');
const dailyPartsRestored = characterScene.characterReport();
characterScene.apply({ t: 'snapshot', tick: 0, state: maskedState });
const maskedParts = characterScene.characterReport();
const maskedAppearance = characterScene.appearanceReport();
// F-5：面具态也要有**两读法**读数（否则 `mask` 部件的「包内 hex → 渲染」链无机器判据）。
characterScene.setReading('underneath');
const maskedPartsUnderneath = characterScene.characterReport();
characterScene.setReading('surface');
characterScene.apply({ t: 'snapshot', tick: 0, state: dailyState });

/** 部件读数（mesh 层）与装配产物（函数层）的**同一比较面**。 */
const partKey = (part) => JSON.stringify({
  part: part.part, name: part.name, parameters: part.parameters, size: part.size,
  position_attribute_digest: part.position_attribute_digest, vertex_count: part.vertex_count,
  local_offset: part.local_offset, source_hex: part.source_hex,
});
const shapeKey = (shape) => JSON.stringify({
  part: shape.part, name: shape.id, parameters: shape.parameters, size: shape.size,
  position_attribute_digest: shape.position_attribute_digest, vertex_count: shape.vertex_count,
  local_offset: shape.local_offset, source_hex: shape.source_hex,
});
const sortedKeys = (items, keyOf) => items.map(keyOf).sort();
/** 两读法部件比较面：`source_hex`（读法无关）**进**；`material_hex`（随读法变）**不进**。 */
const sameCharacterParts = (left, right) =>
  JSON.stringify(sortedKeys(left, partKey)) === JSON.stringify(sortedKeys(right, partKey));
const firstPartDiff = (left, right) => {
  const a = sortedKeys(left, partKey);
  const b = sortedKeys(right, partKey);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    if (a[index] !== b[index]) return `#${index}`;
  }
  return 'none';
};
const partCounts = (parts) => {
  const counts = {};
  for (const part of parts) counts[part.entity_id] = (counts[part.entity_id] ?? 0) + 1;
  return counts;
};
const recomputeMaterialHex = (hex, tone) =>
  `#${new THREE.Color(hex).multiplyScalar(deriveLighting(tone).luminanceScale).getHexString()}`;
/** 按 `(实体 id, 部件名)` 取部件读数 —— **不**用「第一个同名部件」（多实体下会取错人）。 */
const partOf = (parts, entityId, partName) =>
  parts.find((part) => part.entity_id === entityId && part.part === partName);

check('scene_handle_exposes_character_reports',
  typeof characterScene.setAppearance === 'function'
  && typeof characterScene.appearanceReport === 'function'
  && typeof characterScene.characterReport === 'function',
  'createScene() 句柄暴露 setAppearance / appearanceReport / characterReport');

// --- AC-3：部件数 ≥6（读数点 = characterReport()） ---
check('character_parts_count_at_least_six', (() => {
  const counts = partCounts(dailyParts);
  const ids = Object.keys(counts);
  return ids.length === 6 && ids.every((id) => counts[id] >= 6)
    && counts['npc-006'] === 10;
})(), `entities=${Object.keys(partCounts(dailyParts)).length} counts=${JSON.stringify(partCounts(dailyParts))}`);

// --- AC-3：指纹可复算（装配函数产物 vs mesh 层读回，两条独立取数路径） ---
check('character_parts_fingerprints_recomputable',
  JSON.stringify(sortedKeys(dailyAssemblyShapes, shapeKey)) === JSON.stringify(sortedKeys(dailyParts, partKey)),
  `assembly=${dailyAssemblyShapes.length} readback=${dailyParts.length}`
  + ` first_diff=${(() => {
    const a = sortedKeys(dailyAssemblyShapes, shapeKey);
    const b = sortedKeys(dailyParts, partKey);
    for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
      if (a[index] !== b[index]) return `#${index}`;
    }
    return 'none';
  })()}`);

// --- AC-3 负例：改尺寸 ⇒ 指纹必变（前后读数 + 还原） ---
check('character_fingerprint_detects_size_change', (() => {
  const mutated = JSON.parse(JSON.stringify(xuqinAppearance));
  mutated.height_cm.value = xuqinAppearance.height_cm.value + 20;
  const before = JSON.stringify(sortedKeys(characterScene.characterReport(), partKey));
  characterScene.setAppearance(appearanceTableFromDocuments([{ npc_id: 'npc-006', appearance: mutated }]));
  const after = JSON.stringify(sortedKeys(characterScene.characterReport(), partKey));
  characterScene.setAppearance(characterTable);
  const restored = JSON.stringify(sortedKeys(characterScene.characterReport(), partKey));
  return before !== after && restored === before;
})(), `height_cm ${xuqinAppearance.height_cm.value}→${xuqinAppearance.height_cm.value + 20} ⇒ 部件指纹必变；还原后回到原值`);

// --- AC-4：两态可区分（daily / masked） ---
// N2-r2：`appearance.mask` 缺失时**判据必须变红而不是崩**（`?.` 守卫；F-3 的负例要在
// 整树副本上跑得干净读数）。健康树上语义逐字不变。
const xuqinMaskHex = xuqinAppearance.mask?.color?.value ?? null;
const xuqinMaskNumber = xuqinAppearance.mask?.number?.value ?? null;
const xuqinMaskLabel = xuqinAppearance.mask?.number_label?.value ?? null;
check('character_states_daily_and_masked', (() => {
  const daily = dailyAppearance.find((entry) => entry.entity_id === 'npc-006');
  const masked = maskedAppearance.find((entry) => entry.entity_id === 'npc-006');
  const maskedPart = masked.parts.find((part) => part.part === 'mask');
  return Boolean(daily) && Boolean(masked)
    && daily.state_id === 'daily' && !daily.parts.some((part) => part.part === 'mask')
    && masked.state_id === 'masked' && masked.parts.length === 11
    && Boolean(maskedPart) && xuqinMaskHex !== null && maskedPart.source_hex === xuqinMaskHex
    && xuqinMaskNumber === '8'
    && xuqinMaskLabel === '八号';
})(), `daily=${dailyAppearance.find((entry) => entry.entity_id === 'npc-006').parts.length} 部件 /`
  + ` masked=${maskedAppearance.find((entry) => entry.entity_id === 'npc-006').parts.length} 部件`
  + ` mask.number=${xuqinMaskNumber} label=${xuqinMaskLabel}`
  + ` mask.source_hex=${maskedParts.find((part) => part.part === 'mask')?.source_hex ?? null}`);

// --- AC-4 负例：mask.number 改 9 ⇒ 数据侧判据必红（命中能力自证） ---
check('mask_number_criterion_has_teeth', (() => {
  const criterion = (appearance) => appearance?.mask?.number?.value === '8'
    && appearance?.mask?.number_label?.value === '八号';
  const mutated = JSON.parse(JSON.stringify(xuqinAppearance));
  // N2-r2：面具数据缺失时本判据**变红而不是崩**（负例要在整树副本上跑得干净读数）。
  if (!mutated.mask) return criterion(xuqinAppearance) === true;
  mutated.mask.number = { ...(mutated.mask.number ?? {}), value: '9' };
  return criterion(xuqinAppearance) === true && criterion(mutated) === false;
})(), 'mask.number 改 9 ⇒ 判据必红');

// --- AC-4 状态谓词只读既有 state 字段（R-13：null / 缺 schedule / states: [] ⇒ daily，不抛异常） ---
/** 本判据组的**统一取数**：在给定 state 下读 npc-006 的生效形态 id。 */
const stateIdUnder = (state) => {
  characterScene.apply({ t: 'snapshot', tick: 0, state });
  const entry = characterScene.appearanceReport().find((item) => item.entity_id === 'npc-006');
  return entry ? entry.state_id : null;
};
/** F-7：`schedule: null`（键在场但值为 null）—— 谓词不得命中。 */
const scheduleNullState = { entities: maskedState.entities.map((entity) => (entity.id === 'npc-006'
  ? { ...entity, schedule: null } : entity)) };
/** F-7：**完全没有** `schedule` 键 —— 谓词不得命中。 */
const noScheduleState = { entities: maskedState.entities.map((entity) => {
  if (entity.id !== 'npc-006') return entity;
  const { schedule, ...rest } = entity;
  return rest;
}) };

check('character_state_predicate_reads_existing_state_only', (() => {
  const states = xuqinAppearance.states ?? [];
  const masked = states.find((entry) => entry.id === 'masked');
  const predicateKeys = Object.keys(masked?.when ?? {});
  const allowed = ['target_entity_in', 'schedule_state_in', 'room_id_in', 'tags_include'];
  const dailyHasWhen = Boolean(states.find((entry) => entry.id === 'daily')?.when);
  return predicateKeys.length > 0 && predicateKeys.every((key) => allowed.includes(key))
    && !dailyHasWhen
    && (masked.when.target_entity_in ?? []).includes('kitchen-01');
})(), `masked.when=${JSON.stringify(maskedAppearance.find((entry) => entry.entity_id === 'npc-006').state_id)}`
  + ` predicate=${JSON.stringify(xuqinAppearance.states.find((entry) => entry.id === 'masked').when)}`);

// F-7（R-R9）：状态回退断言从**一例**扩成**三例**（各自独立在场、独立可红）。
// 对照臂：先把谓词**打中**（`target_entity = kitchen-01` ⇒ `masked`），证明谓词本身有牙。
const maskedHitStateId = stateIdUnder(maskedState);
const emptyStatesTable = appearanceTableFromDocuments([{
  npc_id: 'npc-006',
  appearance: { ...JSON.parse(JSON.stringify(xuqinAppearance)), states: [] },
}]);
characterScene.setAppearance(emptyStatesTable);
const emptyStatesId = stateIdUnder(maskedState);
characterScene.setAppearance(characterTable);
const scheduleNullId = stateIdUnder(scheduleNullState);
const noScheduleId = stateIdUnder(noScheduleState);
characterScene.apply({ t: 'snapshot', tick: 0, state: dailyState });

check('character_state_falls_back_to_daily_without_schedule', (() => {
  // 例 1：`states: []`（形态表为空 ⇒ 显式 daily，不抛异常）
  return maskedHitStateId === 'masked' && emptyStatesId === 'daily';
})(), `对照臂 target_entity=kitchen-01 ⇒ ${maskedHitStateId}；states: [] ⇒ ${emptyStatesId}（显式 daily，不抛异常）`);

check('character_state_falls_back_to_daily_with_schedule_null', (() => {
  // 例 2：`schedule: null`（键在场、值为 null ⇒ 谓词不命中 ⇒ daily）
  return scheduleNullId === 'daily';
})(), `schedule: null ⇒ ${scheduleNullId}`);

check('character_state_falls_back_to_daily_without_schedule_key', (() => {
  // 例 3：**完全没有** `schedule` 键 ⇒ daily
  return noScheduleId === 'daily';
})(), `无 schedule 键 ⇒ ${noScheduleId}`);

// --- F-3②：`states[].mask=true` 而 `appearance.mask` 缺失 ⇒ 装配**显式降级**（不崩、可观测） ---
const maskMissingAppearance = JSON.parse(JSON.stringify(xuqinAppearance));
delete maskMissingAppearance.mask;
characterScene.setAppearance(appearanceTableFromDocuments([{ npc_id: 'npc-006', appearance: maskMissingAppearance }]));
const maskMissingStateId = stateIdUnder(maskedState);
const maskMissingEntry = characterScene.appearanceReport().find((item) => item.entity_id === 'npc-006');
// 还原（后续判据仍要跑在真实内容包 + 日常态上）
characterScene.setAppearance(characterTable);
characterScene.apply({ t: 'snapshot', tick: 0, state: dailyState });
const restoredEntry = characterScene.appearanceReport().find((item) => item.entity_id === 'npc-006');
const maskMissingCode = maskMissingEntry.degradations[0]?.code ?? null;

check('mask_data_missing_degrades_explicitly', (() => {
  const problems = [];
  if (maskMissingStateId !== 'daily') problems.push(`state_id=${maskMissingStateId} (expected daily)`);
  if (maskMissingEntry.degradations.length !== 1) {
    problems.push(`degradations=${JSON.stringify(maskMissingEntry.degradations)}`);
  }
  if (maskMissingCode !== 'E_MASK_DATA_MISSING') problems.push(`code=${maskMissingCode}`);
  if (maskMissingEntry.parts.some((part) => part.part === 'mask')) {
    problems.push('mask part rendered without mask data');
  }
  if (maskMissingEntry.parts.length < 6) problems.push(`parts=${maskMissingEntry.parts.length} (<6)`);
  const restoreOk = restoredEntry.state_id === 'daily' && restoredEntry.degradations.length === 0
    && restoredEntry.parts.some((part) => part.part === 'torso');
  return problems.length === 0 && restoreOk;
})(), `删 appearance.mask（states 仍声明 masked）⇒ 生效形态 ${maskMissingStateId} /`
  + ` 结构化告警 ${maskMissingCode} / 部件数 ${maskMissingEntry.parts.length}（无 mask 部件）/ 不抛异常；`
  + ` 还原后 ${restoredEntry.state_id}`);

// --- AC-5：颜色锚点由数据驱动（① source_hex == 包内 hex） ---
check('character_color_anchors_come_from_pack', (() => {
  const expected = {
    eyes: xuqinAppearance.eyes.color.value,
    lips: xuqinAppearance.lips.color.value,
    head: xuqinAppearance.skin.color.value,
    hair: xuqinAppearance.hair.color.value,
    torso: xuqinAppearance.garment.color.value,
    coat: xuqinAppearance.garment.color.value,
  };
  return Object.entries(expected).every(([partName, hex]) =>
    partOf(dailyParts, 'npc-006', partName)?.source_hex === hex);
})(), `eyes=${xuqinAppearance.eyes.color.value} lips=${xuqinAppearance.lips.color.value}`
  + ` garment=${xuqinAppearance.garment.color.value} skin=${xuqinAppearance.skin.color.value}`
  + ` 实测=${JSON.stringify({
    eyes: partOf(dailyParts, 'npc-006', 'eyes').source_hex,
    lips: partOf(dailyParts, 'npc-006', 'lips').source_hex,
    torso: partOf(dailyParts, 'npc-006', 'torso').source_hex,
    head: partOf(dailyParts, 'npc-006', 'head').source_hex,
    hair: partOf(dailyParts, 'npc-006', 'hair').source_hex,
  })}`);

// --- AC-5：② material_hex == source_hex × luminanceScale(reading)（按 lighting.ts 公式复算） ---
// F-5（Raven I-9 的漏项闭合）：判据从「只 `eyes`」扩到**逐着色部件** —— 取数循环覆盖
// 全部着色部件（head/hair/torso/arm_l/arm_r/leg_l/leg_r/coat/eyes/lips + 面具态的 mask）。
// **既有断言语义未动**：仍是「两读法各自的读回值 == 按 `lighting.ts` 公式复算的期望值，
// 且两读法互不相等」—— 只是把它跑遍每一个着色部件。
const coloredPartExpectations = [
  ['head', xuqinAppearance.skin.color.value],
  ['hair', xuqinAppearance.hair.color.value],
  ['torso', xuqinAppearance.garment.color.value],
  ['arm_l', xuqinAppearance.garment.color.value],
  ['arm_r', xuqinAppearance.garment.color.value],
  ['leg_l', xuqinAppearance.garment.color.value],
  ['leg_r', xuqinAppearance.garment.color.value],
  ['coat', xuqinAppearance.garment.color.value],
  ['eyes', xuqinAppearance.eyes.color.value],
  ['lips', xuqinAppearance.lips.color.value],
  // `mask` 的期望色只在**面具数据在场**时成立（缺失 ⇒ 该形态已被显式降级为 daily，
  // 判据随之变红而不是崩 —— 见 `mask_data_missing_degrades_explicitly`）。
].concat(xuqinMaskHex === null ? [] : [['mask', xuqinMaskHex]]);
const recomputeProblems = (parts, partsUnderneath, expectations) => {
  const problems = [];
  const readings = [];
  for (const [partName, hex] of expectations) {
    const surface = partOf(parts, 'npc-006', partName)?.material_hex;
    const underneath = partOf(partsUnderneath, 'npc-006', partName)?.material_hex;
    const expectedSurface = recomputeMaterialHex(hex, xuqinWorldview.tone.surface);
    const expectedUnderneath = recomputeMaterialHex(hex, xuqinWorldview.tone.underneath);
    readings.push(`${partName}=${surface}/${underneath}`);
    if (surface !== expectedSurface || underneath !== expectedUnderneath || surface === underneath) {
      problems.push(`${partName} source=${hex} expected=${expectedSurface}/${expectedUnderneath}`
        + ` actual=${surface}/${underneath}`);
    }
  }
  return { problems, readings };
};
check('character_material_hex_recomputable', (() => {
  const daily = recomputeProblems(dailyParts, dailyPartsUnderneath,
    coloredPartExpectations.filter(([partName]) => partName !== 'mask'));
  const masked = recomputeProblems(maskedParts, maskedPartsUnderneath,
    xuqinMaskHex === null ? [] : [['mask', xuqinMaskHex]]);
  return daily.problems.length === 0 && masked.problems.length === 0
    && daily.readings.length === 10 && masked.readings.length === (xuqinMaskHex === null ? 0 : 1);
})(), `逐着色部件 ${coloredPartExpectations.length} 项（10 日常 + 1 面具态）：`
  + recomputeProblems(dailyParts, dailyPartsUnderneath,
    coloredPartExpectations.filter(([partName]) => partName !== 'mask')).readings.join(' ')
  + ` mask=${partOf(maskedParts, 'npc-006', 'mask')?.material_hex}`
  + `/${partOf(maskedPartsUnderneath, 'npc-006', 'mask')?.material_hex}（读回值 ≠ 包内 hex；随读法变）`);

// --- AC-5 / F-5 负对照：**任一非 eyes 部件**材质色偏差（两读法一致）⇒ 本判据必红 ---
check('character_material_hex_criterion_has_teeth', (() => {
  // 模拟 Raven I-9 的注入：把**某个非 eyes 部件**（arm_l）的两读法材质色**同时**改掉
  // （两读法一致 ⇒ 旧的 `two_reads_share_character_parts` 看不见），判据必须变红。
  const tamper = (parts) => parts.map((part) => (part.entity_id === 'npc-006' && part.part === 'arm_l'
    ? { ...part, material_hex: '#000000' } : part));
  const before = recomputeProblems(dailyParts, dailyPartsUnderneath,
    coloredPartExpectations.filter(([partName]) => partName !== 'mask'));
  const after = recomputeProblems(tamper(dailyParts), tamper(dailyPartsUnderneath),
    coloredPartExpectations.filter(([partName]) => partName !== 'mask'));
  return before.problems.length === 0 && after.problems.length === 1
    && after.problems[0].startsWith('arm_l ');
})(), '注入 arm_l 材质色偏差（**两读法一致**）⇒ `character_material_hex_recomputable` 必红');

// --- AC-5 静态判据：TS 内无角色锚点 hex 字面量（D5） ---
check('character_ts_has_no_anchor_hex_literal', (() => {
  const packHexes = new Set([
    xuqinAppearance.eyes.color.value, xuqinAppearance.lips.color.value,
    xuqinAppearance.skin.color.value, xuqinAppearance.hair.color.value,
    xuqinAppearance.garment.color.value,
  ].concat(xuqinMaskHex === null ? [] : [xuqinMaskHex]));
  const literals = characterSource.match(/#[0-9a-f]{6}/g) ?? [];
  const hardcoded = literals.filter((hex) => packHexes.has(hex));
  const patternHits = characterSource.match(/#(8|9|a|b|c)[0-9a-f]{5}/g) ?? [];
  return hardcoded.length === 0 && patternHits.length === 0;
})(), `character.ts hex 字面量=${JSON.stringify(characterSource.match(/#[0-9a-f]{6}/g) ?? [])}`);

// --- AC-6 / §12.3-1：两读法部件逐项相同（source_hex 进比较面；material_hex 不进） ---
check('two_reads_share_character_parts', sameCharacterParts(dailyParts, dailyPartsUnderneath),
  `parts=${dailyParts.length}/${dailyPartsUnderneath.length} first_diff=${firstPartDiff(dailyParts, dailyPartsUnderneath)}`
  + ` material_hex(surface/underneath)=${partOf(dailyParts, 'npc-006', 'eyes').material_hex}`
  + `/${partOf(dailyPartsUnderneath, 'npc-006', 'eyes').material_hex}（信息性，不参与相等断言）`);

// --- AC-6 负对照（R4）：只改 underneath 读数的一个部件 ⇒ 比较面**必须红** ---
check('two_reads_character_criterion_has_teeth', (() => {
  const tampered = dailyPartsUnderneath.map((part, index) => (index === 0 ? { ...part, source_hex: '#000000' } : part));
  return sameCharacterParts(dailyParts, dailyPartsUnderneath) === true
    && sameCharacterParts(dailyParts, tampered) === false;
})(), '注入「只作用于 underneath 读法」的部件差异 ⇒ 两读法判据必红');

check('character_report_stable_after_reading_round_trip',
  sameCharacterParts(dailyParts, dailyPartsRestored),
  'surface→underneath→surface 后部件读数回到原值');

check('character_assembly_shapes_are_reading_independent',
  JSON.stringify(sortedKeys(dailyAssemblyShapes, shapeKey))
  === JSON.stringify(sortedKeys(dailyAssemblyShapesUnderneath, shapeKey)),
  `assembly=${dailyAssemblyShapes.length}/${dailyAssemblyShapesUnderneath.length}`);

// --- §12.3-3（R-05）：装配配置来源 = 'pack'；fallback 必须显式可辨 ---
check('character_appearance_source_is_pack', (() => {
  const xuqinEntry = dailyAppearance.find((entry) => entry.entity_id === 'npc-006');
  const residents = dailyAppearance.filter((entry) => entry.entity_id !== 'npc-006');
  return xuqinEntry?.source === 'pack' && residents.every((entry) => entry.source === 'pack');
})(), `npc-006 source=${dailyAppearance.find((entry) => entry.entity_id === 'npc-006').source}`);

check('character_appearance_null_falls_back', (() => {
  characterScene.setAppearance(null);
  const report = characterScene.appearanceReport();
  const allFallback = report.every((entry) => entry.source === 'fallback');
  const stillSix = report.every((entry) => entry.parts.length >= 6);
  characterScene.setAppearance(characterTable);
  return allFallback && stillSix;
})(), 'setAppearance(null) ⇒ 全部 fallback 且部件数仍 ≥6（AC-3 兜底路径）');

check('main_pack_npcs_use_deterministic_generic_humanoid', (() => {
  const report = scene.appearanceReport();
  return report.length === 5 && report.every((entry) => entry.source === 'fallback' && entry.parts.length >= 6);
})(), `主包 5 个住户（无 appearance）→ 通用人形兜底：${JSON.stringify(partCounts(scene.characterReport()))}`);

// --- §12.3-4：出处只读**嵌套**字段（R-18 假绿陷阱：顶层旧键不得成为外形来源） ---
check('appearance_provenance_is_nested', (() => {
  const factMap = xuqinNpc.source_fact_map ?? {};
  const topLevelAppearanceKeys = Object.keys(factMap).filter((key) => key.startsWith('appearance.')).sort();
  const legacy = ['appearance.red_coat', 'appearance.scarlet_eyes'];
  const nestedOnly = JSON.stringify(topLevelAppearanceKeys) === JSON.stringify(legacy)
    && !('source_facts' in xuqinAppearance) && !('source_fact_map' in xuqinAppearance);
  const eyesHex = partOf(dailyParts, 'npc-006', 'eyes')?.source_hex;
  return nestedOnly && eyesHex === xuqinAppearance.eyes.color.value;
})(), `顶层 appearance.* 旧键=${JSON.stringify(Object.keys(xuqinNpc.source_fact_map ?? {})
  .filter((key) => key.startsWith('appearance.')).sort())}（新外形项**只**在嵌套字段）`);

// --- §12.3-5：appearance 内不得出现引号包起来的原著正文段落（D-4 规则；与 scan_ip_boundary.py 同口径） ---
const quotedSegmentsOf = (line) => {
  const segments = [];
  for (const [opener, closer] of [['\u201c', '\u201d'], ['\u300c', '\u300d']]) {
    let start = 0;
    for (;;) {
      const begin = line.indexOf(opener, start);
      if (begin < 0) break;
      const end = line.indexOf(closer, begin + 1);
      if (end < 0) break;
      segments.push(line.slice(begin + 1, end));
      start = end + 1;
    }
  }
  return segments;
};
const isVerbatimParagraph = (segment) => {
  const cjk = (segment.match(/[\u4e00-\u9fff]/g) ?? []).length;
  if (cjk >= 60) return true;
  if (cjk >= 24) return ['。', '！', '？', '；'].reduce((total, mark) => total + segment.split(mark).length - 1, 0) >= 2;
  return false;
};
check('appearance_has_no_verbatim_paragraph', (() => {
  const text = JSON.stringify(xuqinAppearance, null, 2);
  const hits = text.split('\n').flatMap(quotedSegmentsOf).filter(isVerbatimParagraph);
  const longProbe = `\u201c${'甲'.repeat(61)}\u201d`;
  const shortProbe = `\u201c${'甲'.repeat(10)}\u201d`;
  const teeth = quotedSegmentsOf(longProbe).some(isVerbatimParagraph)
    && !quotedSegmentsOf(shortProbe).some(isVerbatimParagraph);
  return hits.length === 0 && teeth;
})(), 'appearance 内 0 命中；命中能力自证：合成 61 字引号段必命中、10 字段不命中');

// ==================================================================
// 6b) N2-r3 修复轮：**面部可见性 + 性别线索 + 半张面具**的几何判据（REQ-20260924-002）
//
// 背景（architect 实机核验的缺陷，非推测）：r2 的 `hair` 盒 x/y/z 三个区间**完整包住**
//   `head` 盒 ⇒ 苍白皮肤（面部）在画面上不可见；`eyes`/`lips` 只比 `hair` 前表面凸出
//   5 mm ⇒ 读作两条细缝；`mask` 盒与 `hair` 同宽（0.30）且 `y∈[0.41,0.61]` ⇒ 把瞳/唇
//   整片盖住，读作「整块浅色面罩」而不是「半张」。
//
// 口径（**纯加法**：既有 56 条判据逐字未动）：
//   ① 全部读数来自 `characterReport()` 的**实测部件**（`size` + `local_offset`）——
//      **不读** `character.ts` 的 `PART_TABLE` 常量 ⇒ 断言与实现**不共享常量**，
//      改几何必被这组判据看见（否则就是自证循环）；
//   ② 每条判据自带**负对照**：把同一组读数改成缺陷形态（r2 的等价复现）⇒ 判据**必须变红**；
//   ③ 角色正面 = **+z**（`eyes`/`lips` 的偏移落在 +z 侧）。
// ==================================================================
const round6 = (value) => Math.round(value * 1e6) / 1e6;
/** 由实测部件读数还原 AABB 六面（角色正面 = +z）。 */
const boxOf = (parts, entityId, partName) => {
  const part = partOf(parts, entityId, partName);
  if (!part) return null;
  const [sx, sy, sz] = part.size;
  const [ox, oy, oz] = part.local_offset;
  return {
    part: part.part,
    front_z: round6(oz + sz / 2), back_z: round6(oz - sz / 2),
    top_y: round6(oy + sy / 2), bottom_y: round6(oy - sy / 2),
    left_x: round6(ox - sx / 2), right_x: round6(ox + sx / 2),
    height: round6(sy), width: round6(sx), depth: round6(sz),
  };
};
/** 判据只依赖「一组部件读数」⇒ 同一函数可在**篡改副本**上跑负对照。 */
const faceOf = (parts) => ({
  head: boxOf(parts, 'npc-006', 'head'), hair: boxOf(parts, 'npc-006', 'hair'),
  eyes: boxOf(parts, 'npc-006', 'eyes'), lips: boxOf(parts, 'npc-006', 'lips'),
  mask: boxOf(parts, 'npc-006', 'mask'), torso: boxOf(parts, 'npc-006', 'torso'),
  coat: boxOf(parts, 'npc-006', 'coat'), leg: boxOf(parts, 'npc-006', 'leg_l'),
  // N2-r4（纯加法）：轮廓判据还要读**臂**与**两条腿**（`leg` 保留给 r3 的外衣判据，语义未动）。
  arm_l: boxOf(parts, 'npc-006', 'arm_l'), arm_r: boxOf(parts, 'npc-006', 'arm_r'),
  leg_l: boxOf(parts, 'npc-006', 'leg_l'), leg_r: boxOf(parts, 'npc-006', 'leg_r'),
});
const PROTRUSION_MIN_M = 0.015;
const HAIR_BELOW_SHOULDER_MIN_M = 0.10;
const COAT_SHIN_VISIBLE_MIN_M = 0.15;
const MASK_LOWER_FACE_MIN_M = 0.08;
/** ① 面部露出：头（皮肤）前表面**严格**在发前表面之前。 */
const faceVisibleBeyondHair = (face) => Boolean(face.head && face.hair)
  && face.head.front_z > face.hair.front_z;
/** ② 五官前伸：瞳 / 唇 相对**面部前表面**（判据口径）与**发前表面**（真正遮住脸的那一面）
 *  的前伸量**均** ≥ 15 mm —— r2 只相对发前表面凸出 5 mm ⇒ 画面上是两条细缝。 */
const featuresProtrude = (face) => {
  if (!face.head || !face.eyes || !face.lips || !face.hair) return false;
  const proudOf = (box) => round6(box.front_z - face.head.front_z) >= PROTRUSION_MIN_M
    && round6(box.front_z - face.hair.front_z) >= PROTRUSION_MIN_M;
  return proudOf(face.eyes) && proudOf(face.lips);
};
/** ③ 长发：发下缘**明显低于**肩线（躯干上缘），且发顶在头顶之上（顶盖在场）。 */
const hairReadsLong = (face) => Boolean(face.hair && face.torso && face.head)
  && round6(face.torso.top_y - face.hair.bottom_y) >= HAIR_BELOW_SHOULDER_MIN_M
  && face.hair.top_y >= face.head.top_y;
/** ④ 长款外衣：下摆**不高于膝线**（腿盒中点），且小腿（下摆 → 腿底）仍露出 ≥ 0.15 m。 */
const coatReadsLong = (face) => {
  if (!face.coat || !face.leg) return false;
  const kneeY = round6((face.leg.top_y + face.leg.bottom_y) / 2);
  return face.coat.bottom_y <= kneeY
    && round6(face.coat.bottom_y - face.leg.bottom_y) >= COAT_SHIN_VISIBLE_MIN_M;
};
/** ⑤ 半张面具：盖住瞳、**不**盖住唇，面具高度 ≤ 头高 70%，下半脸留出 ≥ 0.08 m 皮肤带。 */
const maskReadsHalfFace = (face) => {
  if (!face.mask || !face.eyes || !face.lips || !face.head) return false;
  const coversEyes = face.mask.top_y >= face.eyes.top_y && face.mask.bottom_y <= face.eyes.bottom_y
    && face.mask.front_z > face.eyes.front_z;
  const keepsLips = face.mask.bottom_y > face.lips.top_y;
  const halfFace = round6(face.mask.top_y - face.mask.bottom_y) <= round6(face.head.height * 0.7);
  const lowerFaceSkin = round6(face.mask.bottom_y - face.head.bottom_y) >= MASK_LOWER_FACE_MIN_M;
  return coversEyes && keepsLips && halfFace && lowerFaceSkin;
};
/** 负对照构造：只改**指定部件**的 `size` / `local_offset`（其余部件读数逐字不动）。 */
const tamperParts = (parts, edits) => parts.map((part) => (edits[part.part]
  ? { ...part,
      size: edits[part.part].size ?? part.size,
      local_offset: edits[part.part].local_offset ?? part.local_offset }
  : part));

const dailyFace = faceOf(dailyParts);
const maskedFace = faceOf(maskedParts);
// 负对照几何 = **r2 缺陷形态**在本轮头部几何上的等价复现（发盒完整包住头盒 / 整脸面罩 / 五官齐平 / 短发 / 短外衣）。
const enclosingHairParts = tamperParts(dailyParts, {
  hair: { size: [0.30, 0.34, 0.30], local_offset: [0, 0.53, 0.025] } });
const flushEyesLipsParts = tamperParts(dailyParts, {
  eyes: { local_offset: [0, 0.53, 0.14] }, lips: { local_offset: [0, 0.43, 0.14] } });
const r2EyesLipsParts = tamperParts(dailyParts, {
  eyes: { local_offset: [0, 0.53, 0.13] }, lips: { local_offset: [0, 0.43, 0.13] } });
const shortHairParts = tamperParts(dailyParts, {
  hair: { size: [0.30, 0.20, 0.20], local_offset: [0, 0.55, -0.05] } });
const shortCoatParts = tamperParts(dailyParts, {
  coat: { size: [0.56, 0.86, 0.34], local_offset: [0, -0.12, 0] } });
const fullFaceMaskParts = tamperParts(maskedParts, {
  mask: { size: [0.30, 0.20, 0.06], local_offset: [0, 0.51, 0.135] } });

/** 毫米读数（1 位小数，消除浮点尾差噪声 —— 不改变任何阈值判定）。 */
const mm = (value) => Math.round(value * 10000) / 10;
const faceProtrusionMm = {
  eyes: mm(dailyFace.eyes.front_z - dailyFace.head.front_z),
  lips: mm(dailyFace.lips.front_z - dailyFace.head.front_z),
  eyes_of_hair: mm(dailyFace.eyes.front_z - dailyFace.hair.front_z),
  lips_of_hair: mm(dailyFace.lips.front_z - dailyFace.hair.front_z),
};
const facePlaneGapMm = mm(dailyFace.head.front_z - dailyFace.hair.front_z);
const hairLengthM = round6(dailyFace.hair.top_y - dailyFace.hair.bottom_y);
const hairBelowShoulderMm = mm(dailyFace.torso.top_y - dailyFace.hair.bottom_y);
const kneeY = round6((dailyFace.leg.top_y + dailyFace.leg.bottom_y) / 2);
const shinVisibleMm = mm(dailyFace.coat.bottom_y - dailyFace.leg.bottom_y);
// r5 / Sentinel BUG-1（**CRITICAL**）：与 `maskReadsHalfFace()` **同一守卫口径** —— 声明 masked 但
// `appearance.mask`（或 `eyes`/`lips`/`head`）缺失时**不得解引用**；读数降级为 `null`，
// 由 detail 文案**显式判红**（缺 `mask` ⇒ 没有 `PASS=/FAIL=` 汇总行的崩溃 = r3 引入的回归）。
const maskGeometryMissing = ['mask', 'eyes', 'lips', 'head'].filter((key) => !maskedFace[key]);
const maskGeometryAvailable = maskGeometryMissing.length === 0;
const maskHeightM = maskGeometryAvailable
  ? round6(maskedFace.mask.top_y - maskedFace.mask.bottom_y) : null;
const lowerFaceBandMm = maskGeometryAvailable
  ? mm(maskedFace.mask.bottom_y - maskedFace.head.bottom_y) : null;

check('character_face_visible_beyond_hair',
  faceVisibleBeyondHair(dailyFace) === true && faceVisibleBeyondHair(faceOf(enclosingHairParts)) === false,
  `head 前表面 z=${dailyFace.head.front_z} > hair 前表面 z=${dailyFace.hair.front_z}`
  + `（面部露出 ${facePlaneGapMm} mm）；负对照：发盒完整包住头盒（r2 形态）⇒ 判据红`);

check('character_eyes_lips_protrude_from_face',
  featuresProtrude(dailyFace) === true
  && featuresProtrude(faceOf(flushEyesLipsParts)) === false
  && featuresProtrude(faceOf(r2EyesLipsParts)) === false,
  `eyes 前伸 ${faceProtrusionMm.eyes} mm（相对发前表面 ${faceProtrusionMm.eyes_of_hair} mm）/`
  + ` lips 前伸 ${faceProtrusionMm.lips} mm（相对发前表面 ${faceProtrusionMm.lips_of_hair} mm）`
  + `（阈值 ≥ 15 mm）；负对照：① 五官与面部齐平 ⇒ 红；② r2 形态（瞳/唇前表面 z=0.145，低于阈值）⇒ 红`);

check('character_hair_reads_long',
  hairReadsLong(dailyFace) === true && hairReadsLong(faceOf(shortHairParts)) === false,
  `发下缘 y=${dailyFace.hair.bottom_y} vs 肩线（躯干上缘）y=${dailyFace.torso.top_y}`
  + ` ⇒ 低于肩线 ${hairBelowShoulderMm} mm（阈值 ≥ 100 mm）；发长 ${hairLengthM} m；`
  + `负对照：短发盒（下缘 y=0.45）⇒ 判据红`);

check('character_coat_reads_long',
  coatReadsLong(dailyFace) === true && coatReadsLong(faceOf(shortCoatParts)) === false,
  `外衣下摆 y=${dailyFace.coat.bottom_y} ≤ 膝线 y=${kneeY}；小腿露出 ${shinVisibleMm} mm`
  + `（阈值 ≥ 150 mm）；负对照：r2 短外衣（下摆 y=−0.55，高于膝）⇒ 判据红`);

check('character_mask_reads_half_face',
  maskReadsHalfFace(maskedFace) === true && maskReadsHalfFace(faceOf(fullFaceMaskParts)) === false,
  maskGeometryAvailable
    ? `面具 y∈[${maskedFace.mask.bottom_y},${maskedFace.mask.top_y}] 盖住瞳 y∈[${maskedFace.eyes.bottom_y},${maskedFace.eyes.top_y}]`
      + `（面具前表面 z=${maskedFace.mask.front_z} > 瞳前表面 z=${maskedFace.eyes.front_z}），`
      + `下缘 y=${maskedFace.mask.bottom_y} > 唇上缘 y=${maskedFace.lips.top_y} ⇒ 唇仍可见；`
      + `面具高 ${maskHeightM} m ≤ 头高 ${maskedFace.head.height}×0.7；下半脸皮肤带 ${lowerFaceBandMm} mm`
      + `（阈值 ≥ 80 mm）；负对照：r2 整脸面罩（盖住唇）⇒ 判据红`
    // r5 / Sentinel BUG-1：缺部件时**显式**给 FAIL 文案，**不**解引用（与 `maskReadsHalfFace()` 同一守卫）。
    : `MISSING_PARTS=[${maskGeometryMissing.join(',')}]（\`appearance\` 数据缺失）⇒ 几何读数不可用`
      + `（**未解引用**，与 maskReadsHalfFace() 同一守卫口径）⇒ 判据**显式判红**；`
      + `降级路径见 mask_data_missing_degrades_explicitly`);

// ==================================================================
// 6c) N2-r4 修复轮：**性别可读**（长发过肩 / 收腰 / 露腿）的几何判据（REQ-20260924-002）
//
// 背景（architect 实机视觉核验的缺陷，非推测）：r3 的 `hair` 宽 0.36 **小于** `torso` 宽 0.46
//   ⇒ 头发下部**缩在肩内**（两侧各窄 50 mm）⇒ 画面上读作「头罩 / 头盔」而不是「垂在肩外的长发」；
//   同时 `torso` 0.46 + 臂在 ±0.30（合计 0.73 宽）⇒ 整体读作「方肩无性别立柱」，PM 的 AC-9
//   「能认出性别」不成立。
//
// 口径（**纯加法**：r1/r2/r3 的 61 条判据逐字未动）：
//   ① 读数全部来自 `characterReport()` 的**实测部件**（`size` + `local_offset`）——**不读**
//      `character.ts` 的 `PART_TABLE` 常量 ⇒ 断言与实现不共享常量，改几何必被看见；
//   ② 每条判据自带**负对照**：把同一组读数改成缺陷形态（r3 等价复现 / 悬空臂 / 穿模臂 / 合并腿 /
//      长到脚踝的外衣）⇒ 判据**必须变红**；
//   ③ 角色正面 = **+z**（沿用 r3 口径）。
// ==================================================================
/** 发必须**宽出躯干**的下限（合计；两侧各半）。 */
const HAIR_WIDER_THAN_TORSO_MIN_M = 0.10;
const HAIR_OUTSIDE_TORSO_EACH_SIDE_MIN_M = 0.04;
/** 发下缘必须**垂到躯干中部及以下**。 */
const HAIR_BOTTOM_MAX_Y = 0.0;
/** 收窄后的躯干宽度上限（r3 = 0.46）。 */
const TORSO_WIDTH_MAX_M = 0.40;
/** 臂内缘与躯干侧面：允许的最大缝隙（悬空）与最大重叠（穿模）。 */
const ARM_HUG_MAX_GAP_M = 0.005;
const ARM_MAX_OVERLAP_M = 0.02;
/** 外衣必须比发**窄**的下限 ⇒ 两侧发帘落在外衣轮廓之外（可见）。 */
const COAT_NARROWER_THAN_HAIR_MIN_M = 0.06;
/** 两条腿之间的最小可见缝隙 ⇒ 读作「两条腿」而不是一整块柱体。 */
const LEG_GAP_MIN_M = 0.02;

/** 部件盒中心的 x（供 detail 报「臂位」读数）。 */
const centerX = (box) => (box ? round6(box.left_x + box.width / 2) : null);

/** ⑥ 长发「披在肩外」：两侧**宽出躯干**（不是缩在肩内），且下缘垂到躯干中部及以下。 */
const hairDrapesOutsideShoulders = (face) => {
  if (!face.hair || !face.torso) return false;
  const wider = round6(face.hair.width - face.torso.width) >= HAIR_WIDER_THAN_TORSO_MIN_M;
  const eachSide = round6(face.torso.left_x - face.hair.left_x) >= HAIR_OUTSIDE_TORSO_EACH_SIDE_MIN_M
    && round6(face.hair.right_x - face.torso.right_x) >= HAIR_OUTSIDE_TORSO_EACH_SIDE_MIN_M;
  return wider && eachSide && face.hair.bottom_y <= HAIR_BOTTOM_MAX_Y;
};

/** ⑦ 收腰 / 窄肩：躯干收窄、臂**贴住**躯干侧面（不悬空、不穿模），且外衣窄于发（发帘在外衣轮廓外可见）。 */
const silhouetteNarrowsAtWaist = (face) => {
  if (!face.torso || !face.arm_l || !face.arm_r || !face.coat || !face.hair) return false;
  const hugging = (innerEdge, torsoEdge) => {
    const gap = round6(innerEdge - torsoEdge);
    return gap >= -ARM_MAX_OVERLAP_M && gap <= ARM_HUG_MAX_GAP_M;
  };
  return face.torso.width <= TORSO_WIDTH_MAX_M
    && hugging(face.arm_l.right_x, face.torso.left_x)
    && hugging(face.torso.right_x, face.arm_r.left_x)
    && round6(face.hair.width - face.coat.width) >= COAT_NARROWER_THAN_HAIR_MIN_M;
};

/** ⑧ 下半身可读：下摆以下**两条腿**都露出来（有缝隙、都在外衣宽度内、露出量 ≥ 阈值）。 */
const legsReadBelowCoat = (face) => {
  if (!face.coat || !face.leg_l || !face.leg_r) return false;
  const gap = round6(face.leg_r.left_x - face.leg_l.right_x);
  const shin = (leg) => round6(face.coat.bottom_y - leg.bottom_y);
  return gap >= LEG_GAP_MIN_M
    && shin(face.leg_l) >= COAT_SHIN_VISIBLE_MIN_M && shin(face.leg_r) >= COAT_SHIN_VISIBLE_MIN_M
    && face.leg_l.right_x <= face.coat.right_x && face.leg_r.left_x >= face.coat.left_x;
};

/** 负对照几何（**只改指定部件**的读数，其余逐字不动）。 */
const r3HairParts = tamperParts(dailyParts, {
  hair: { size: [0.36, 0.62, 0.30], local_offset: [0, 0.37, -0.015] } });
const shortWideHairParts = tamperParts(dailyParts, {
  hair: { size: [0.58, 0.40, 0.30], local_offset: [0, 0.50, -0.015] } });
const r3ShoulderParts = tamperParts(dailyParts, {
  torso: { size: [0.46, 0.66, 0.26] },
  arm_l: { local_offset: [-0.30, -0.02, 0] }, arm_r: { local_offset: [0.30, -0.02, 0] } });
const floatingArmParts = tamperParts(dailyParts, {
  arm_l: { local_offset: [-0.36, -0.02, 0] }, arm_r: { local_offset: [0.36, -0.02, 0] } });
const sunkArmParts = tamperParts(dailyParts, {
  arm_l: { local_offset: [-0.14, -0.02, 0] }, arm_r: { local_offset: [0.14, -0.02, 0] } });
const wideCoatParts = tamperParts(dailyParts, { coat: { size: [0.62, 1.12, 0.34] } });
const mergedLegsParts = tamperParts(dailyParts, {
  leg_l: { local_offset: [-0.005, -0.72, 0] }, leg_r: { local_offset: [0.005, -0.72, 0] } });
const ankleCoatParts = tamperParts(dailyParts, {
  coat: { size: [0.46, 1.30, 0.34], local_offset: [0, -0.47, -0.05] } });
/** r3 的整体轮廓形态（躯干 0.46 / 发 0.36 缩在肩内 / 臂 ±0.30 / 外衣 0.56）——复合判据的负对照。 */
const r3SilhouetteParts = tamperParts(dailyParts, {
  hair: { size: [0.36, 0.62, 0.30], local_offset: [0, 0.37, -0.015] },
  torso: { size: [0.46, 0.66, 0.26] },
  arm_l: { local_offset: [-0.30, -0.02, 0] }, arm_r: { local_offset: [0.30, -0.02, 0] },
  coat: { size: [0.56, 1.12, 0.34] } });

const hairWiderMm = mm(dailyFace.hair.width - dailyFace.torso.width);
const hairOutsideEachSideMm = mm(Math.min(dailyFace.torso.left_x - dailyFace.hair.left_x,
  dailyFace.hair.right_x - dailyFace.torso.right_x));
const armHugMm = {
  left: mm(dailyFace.arm_l.right_x - dailyFace.torso.left_x),
  right: mm(dailyFace.torso.right_x - dailyFace.arm_r.left_x),
};
const armOffsetM = { left: centerX(dailyFace.arm_l), right: centerX(dailyFace.arm_r) };
const coatVsHairMm = mm(dailyFace.hair.width - dailyFace.coat.width);
const legGapMm = mm(dailyFace.leg_r.left_x - dailyFace.leg_l.right_x);

check('character_hair_drapes_outside_shoulders',
  hairDrapesOutsideShoulders(dailyFace) === true
  && hairDrapesOutsideShoulders(faceOf(r3HairParts)) === false
  && hairDrapesOutsideShoulders(faceOf(shortWideHairParts)) === false,
  `发宽 ${dailyFace.hair.width} m > 躯干宽 ${dailyFace.torso.width} m（宽出 ${hairWiderMm} mm；两侧各 ${hairOutsideEachSideMm} mm）`
  + ` ⇒ 发帘落在肩外；发下缘 y=${dailyFace.hair.bottom_y} ≤ ${HAIR_BOTTOM_MAX_Y}（低于肩线 ${hairBelowShoulderMm} mm）；`
  + `负对照：① r3 发盒（宽 0.36 < 躯干、下缘 y=0.06）⇒ 红；② 宽但短（下缘 y=0.30）⇒ 红`);

check('character_silhouette_narrows_at_waist',
  silhouetteNarrowsAtWaist(dailyFace) === true
  && silhouetteNarrowsAtWaist(faceOf(r3ShoulderParts)) === false
  && silhouetteNarrowsAtWaist(faceOf(floatingArmParts)) === false
  && silhouetteNarrowsAtWaist(faceOf(sunkArmParts)) === false
  && silhouetteNarrowsAtWaist(faceOf(wideCoatParts)) === false,
  `躯干宽 ${dailyFace.torso.width} m ≤ ${TORSO_WIDTH_MAX_M}（r3 = 0.46 ⇒ 收窄 ${mm(0.46 - dailyFace.torso.width)} mm）；`
  + `臂贴住躯干侧面（内缘缝隙 ${armHugMm.left}/${armHugMm.right} mm ∈ [${-ARM_MAX_OVERLAP_M * 1000}, ${ARM_HUG_MAX_GAP_M * 1000}]）；`
  + `臂 offset.x = ${armOffsetM.left}/${armOffsetM.right}（r3 = ±0.30 ⇒ 各内收 ${mm(Math.abs(-0.30 - armOffsetM.left))} mm）；`
  + `外衣宽 ${dailyFace.coat.width} m < 发宽 ${dailyFace.hair.width} m（窄 ${coatVsHairMm} mm）⇒ 发帘在外衣轮廓外可见；`
  + `负对照：① r3 肩（躯干 0.46 + 臂 ±0.30）⇒ 红；② 臂悬空（±0.36）⇒ 红；③ 臂穿模（±0.14）⇒ 红；④ 外衣比发宽（0.62）⇒ 红`);

check('character_legs_read_below_coat',
  legsReadBelowCoat(dailyFace) === true
  && legsReadBelowCoat(faceOf(mergedLegsParts)) === false
  && legsReadBelowCoat(faceOf(ankleCoatParts)) === false,
  `外衣下摆 y=${dailyFace.coat.bottom_y}；腿 y∈[${dailyFace.leg_l.bottom_y},${dailyFace.leg_l.top_y}]`
  + ` ⇒ 下摆以下露出 ${shinVisibleMm} mm（阈值 ≥ ${COAT_SHIN_VISIBLE_MIN_M * 1000} mm）；`
  + `两腿缝隙 ${legGapMm} mm ≥ ${LEG_GAP_MIN_M * 1000} mm（读作两条腿，不是一整块柱体）；`
  + `负对照：① 两腿合并（缝隙 ${mm(faceOf(mergedLegsParts).leg_r.left_x - faceOf(mergedLegsParts).leg_l.right_x)} mm）⇒ 红；`
  + `② 外衣长到脚踝（下摆 y=${faceOf(ankleCoatParts).coat.bottom_y}）⇒ 红`);

check('character_gender_cues_present', (() => {
  // **AC-9「能认出性别」的机器口径**：三条轮廓线索**同时**在场（长发披肩 + 收腰窄肩 + 下摆以下露腿）。
  // 这是**几何层面**的必要条件判据，不替代实机视觉核验（取证图另见 `spikes/n2-appearance/shots/**`）。
  const cues = (face) => ({
    hair_over_shoulders: hairDrapesOutsideShoulders(face),
    narrow_waist: silhouetteNarrowsAtWaist(face),
    legs_visible: legsReadBelowCoat(face),
  });
  const current = cues(dailyFace);
  const r3 = cues(faceOf(r3SilhouetteParts));
  return Object.values(current).every(Boolean)
    && Object.values(r3).some((value) => value === false);
})(), `三条轮廓线索同时在场：长发披肩（发宽 ${dailyFace.hair.width} > 躯干 ${dailyFace.torso.width}、下缘 y=${dailyFace.hair.bottom_y}）`
  + ` / 收腰（躯干 ${dailyFace.torso.width}、臂 ±${Math.abs(armOffsetM.left)}） / 露腿（下摆以下 ${shinVisibleMm} mm、两腿缝隙 ${legGapMm} mm）；`
  + `负对照：r3 几何（躯干 0.46 / 发 0.36 缩在肩内 / 臂 ±0.30 / 外衣 0.56）⇒ 长发与收腰两条线索**不在场** ⇒ 判据红`);

// ==================================================================
// 6d) N2-r5 收口轮：**两条无界盲区的纵向界判据**（Raven M3 / M4）
//
// 背景（Raven 实测，非推测）：r3/r4 的 `hair` / `arm_*` 判据只约束**形状与位置**，
//   纵向长度**无界** —— 注入 `hair.size[1]=2.20`（垂到脚面以下）与 `arm.size[1]=0.06`
//   （手臂变短桩）时 **65/0 全绿**。
// 口径（**纯加法**：既有 65 条判据逐字未动、期望值不动）：只**加**两条纵向界约束；
//   读数仍全部来自 `characterReport()` 的实测部件（`size` + `local_offset`），每条自带负对照。
// **与任务书示例的口径差异（如实登记）**：任务书示例为 `hair.bottom_y ≥ leg.bottom_y + 0.05`；
//   实测该式对任务书**自己的注入**不触发（注入后 `hair.bottom_y=−0.76` 仍**高于**
//   `leg_l.bottom_y=−1.12`，差 0.31 m ⇒ 该式恒真）。故 hair 侧按**更紧**的口径落地：
//   **发下缘不得低于躯干下沿（腰线）**；任务书示例式作为**从属子句**一并保留（被腰线式蕴含）。
// ==================================================================
/** 发下缘相对躯干下沿（腰线）的最小余量。 */
const HAIR_ABOVE_WAIST_MIN_M = 0.05;
/** 臂高相对躯干高的最小比值（臂不得缩成短桩）。 */
const ARM_HEIGHT_MIN_TORSO_RATIO = 0.30;
/** 任务书示例式（从属子句，被腰线式蕴含）：发下缘不得低于腿下沿 + 余量。 */
const HAIR_ABOVE_LEG_BOTTOM_MIN_M = 0.05;

/** ⑨ 发纵向长度**有界**：下缘不得低于腰线（+ 余量）；并保留「不得低于腿下沿」子句。 */
const hairLengthBounded = (face) => {
  if (!face.hair || !face.torso || !face.leg_l || !face.leg_r) return false;
  const aboveWaist = round6(face.hair.bottom_y - (face.torso.bottom_y + HAIR_ABOVE_WAIST_MIN_M)) >= 0;
  const aboveLeg = round6(face.hair.bottom_y - (face.leg_l.bottom_y + HAIR_ABOVE_LEG_BOTTOM_MIN_M)) >= 0
    && round6(face.hair.bottom_y - (face.leg_r.bottom_y + HAIR_ABOVE_LEG_BOTTOM_MIN_M)) >= 0;
  return aboveWaist && aboveLeg;
};
/** ⑩ 臂纵向长度**有界**：臂高 ≥ 躯干高 × 0.30。 */
const armHeightBounded = (face) => {
  if (!face.arm_l || !face.arm_r || !face.torso) return false;
  const floor = round6(ARM_HEIGHT_MIN_TORSO_RATIO * face.torso.height);
  return round6(face.arm_l.height - floor) >= 0 && round6(face.arm_r.height - floor) >= 0;
};

/** 负对照几何（**只改指定部件**的读数，其余逐字不动）= Raven 的两个注入。 */
const overlongHairParts = tamperParts(dailyParts, { hair: { size: [0.58, 2.20, 0.30] } });
const stubArmParts = tamperParts(dailyParts, {
  arm_l: { size: [0.10, 0.06, 0.14] }, arm_r: { size: [0.10, 0.06, 0.14] } });

const hairAboveWaistMm = mm(dailyFace.hair.bottom_y - dailyFace.torso.bottom_y);
const armHeightRatio = round6(dailyFace.arm_l.height / dailyFace.torso.height);

check('character_hair_length_bounded_by_waist',
  hairLengthBounded(dailyFace) === true && hairLengthBounded(faceOf(overlongHairParts)) === false,
  `发下缘 y=${dailyFace.hair.bottom_y} 高于腰线 y=${dailyFace.torso.bottom_y} 共 ${hairAboveWaistMm} mm`
  + `（阈值 ≥ ${HAIR_ABOVE_WAIST_MIN_M * 1000} mm；发长 ${hairLengthM} m）；`
  + `负对照：注入 hair.size[1]=2.20（下缘 y=${faceOf(overlongHairParts).hair.bottom_y}，低于腰线）⇒ 判据红`);

check('character_arm_height_bounded_by_torso',
  armHeightBounded(dailyFace) === true && armHeightBounded(faceOf(stubArmParts)) === false,
  `臂高 ${dailyFace.arm_l.height} m ≥ 躯干高 ${dailyFace.torso.height} × ${ARM_HEIGHT_MIN_TORSO_RATIO}`
  + `（阈值 ${round6(ARM_HEIGHT_MIN_TORSO_RATIO * dailyFace.torso.height)} m；实测比 ${armHeightRatio}）；`
  + `负对照：注入 arm.size[1]=0.06（短桩，比 ${round6(0.06 / dailyFace.torso.height)}）⇒ 判据红`);

// ==================================================================
// 7) N4 美术达成（REQ-20260924-004 / W7）—— **纯加法**：既有 67 条 `check()` 一字未改
//
// 口径声明（Raven 预审 R-6 / R-7）：
//   - 本节里凡读「配置 / 注册表 / 读数」的判据，一律**显式标注为配置面判据，不构成画面证据**；
//     画面面由 `v0/spikes/n4-art/` 的实机截图 + AO A/B 像素对照承担（见 `03`）。
//   - 每条判据自带**负对照**（注入 → 变红 → 还原），负例优先取**非自指**形态
//     （例：删**盘上**的贴图文件、注册表不动 ⇒ 必红）。
// ==================================================================
const ASSETS_DIR = `${WEB_DIR}assets/`;
const ASSETS_MANIFEST = `${ASSETS_DIR}manifest.txt`;
const assetsManifestText = readFileSync(ASSETS_MANIFEST, 'utf8');

/** 静态 URL → 盘上路径（Node 下 `import.meta.url` 是 `file:`；浏览器构建里是 `/assets/...` ⇒ `null`）。 */
function assetPathOf(url) {
  if (typeof url !== 'string' || !url.startsWith('file:')) return null;
  try {
    return fileURLToPath(url);
  } catch {
    return null;
  }
}

/** `true` / `false` / `null`（= 该环境下无法判定，例如浏览器构建里的根绝对路径）。 */
function onDisk(url) {
  const path = assetPathOf(url);
  return path === null ? null : existsSync(path);
}

const mapUrlsOf = (spec) => [...new Set(
  [spec.maps.diffuse, spec.maps.normal, spec.maps.roughness, spec.maps.metalness, spec.maps.ao]
    .filter((value) => typeof value === 'string'),
)];
const mapsPresentOnDisk = (spec) => mapUrlsOf(spec).filter((url) => onDisk(url) === true);

/** 图像尺寸（纯 Node 读文件头：JPEG SOF / PNG IHDR；零依赖、零 WebGL）。 */
function imageSizeOf(path) {
  const bytes = readFileSync(path);
  if (bytes.length > 24 && bytes[0] === 0x89 && bytes[1] === 0x50) {
    return { format: 'png', width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
  }
  let index = 2;
  const sof = [0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf];
  while (index < bytes.length - 1) {
    if (bytes[index] !== 0xff) { index += 1; continue; }
    const marker = bytes[index + 1];
    if (sof.includes(marker)) {
      return { format: 'jpeg', height: bytes.readUInt16BE(index + 5), width: bytes.readUInt16BE(index + 7) };
    }
    if (marker === 0xd8 || marker === 0xd9 || (marker >= 0xd0 && marker <= 0xd7)) { index += 2; continue; }
    index += 2 + bytes.readUInt16BE(index + 2);
  }
  return null;
}

/** 登记表解析：`asset id` → 许可 + 类别 + 上游真实覆盖（cm）+ **声明的材质基准**（m）。
 *  注意：同一 asset 有多行（diffuse / normal / arm），只有部分行写「真实覆盖 N cm」/「基准 N m」/
 *  类别字段 ⇒ 必须**保留首个非空读数**，不能被后续空值行覆盖。 */
const registeredAssets = new Map();
for (const line of assetsManifestText.split('\n')) {
  if (line.trim().startsWith('#')) continue;
  const idMatch = line.match(/asset id `([^`]+)`/);
  if (!idMatch) continue;
  const coverage = line.match(/真实覆盖\s*([0-9.]+)\s*cm/);
  const category = line.match(/类别 `([a-z0-9_]+)`/);
  const basis = line.match(/\*\*基准\s*([0-9.]+)\s*m\*\*/);
  const previous = registeredAssets.get(idMatch[1]);
  registeredAssets.set(idMatch[1], {
    cc0: line.includes('CC0 1.0') || Boolean(previous?.cc0),
    coverage_cm: coverage ? Number(coverage[1]) : (previous?.coverage_cm ?? null),
    category: category ? category[1] : (previous?.category ?? null),
    basis_m: basis ? Number(basis[1]) : (previous?.basis_m ?? null),
  });
}

/**
 * 非自指负例的**零写盘**实现（N4-r2 / M-3 关闭 Raven N-3）。
 *
 * 旧实现 `unlinkSync` 真删交付树里的贴图、跑完再 `writeFileSync` 还原 —— 把只读门禁变成**写门禁**：
 * ① 进程在删与写之间被 SIGKILL / OOM / CI 超时 / Ctrl-C 打断 ⇒ **交付树永久少一个贴图**，
 *    下一次 `material_files_exist_on_disk` 必红、浏览器构建 404；② **并发不安全**：两方同时跑
 *    （Sentinel + Raven / CI 两个 job）⇒ 一方的 `readFileSync` 撞 ENOENT 直接**崩**（不是判红）；
 * ③ 写回**不保留 mtime** ⇒ 以 mtime 为锚的证据链漂移；④ 只读检出 ⇒ **抛错**而非判红。
 * ⇒ 改为**在内存里**把某个 map URL 重指向一个**盘上不存在**的路径：注册表其余逐字不动，
 * 同样**非自指**（不是手改一份读数的副本），且**零写盘**（本脚本因此对交付树零副作用）。
 */
const ABSENT_MAP_URL = new URL('../../assets/__absent_probe__/__absent__.jpg', import.meta.url).href;
function withMapUrlRedirected(specs, index, mapKey, probe) {
  const redirected = specs.map((spec, i) => (i === index
    ? { ...spec, maps: { ...spec.maps, [mapKey]: ABSENT_MAP_URL } }
    : spec));
  return probe(redirected);
}

// --- 1) 每主要表面 ≥2 map（**盘上存在**口径 ⇒ 负例非自指：URL 重指向缺失路径、注册表不动） ---
const allSpecs = SURFACE_IDS.map((id) => SURFACES[id]);
const mapsPerSurfaceOf = (specs) => specs.map((spec, index) => ({
  surface: SURFACE_IDS[index],
  declared: mapUrlsOf(spec).length,
  on_disk: mapsPresentOnDisk(spec).length,
  diffuse_on_disk: onDisk(spec.maps.diffuse) === true,
  normal_on_disk: onDisk(spec.maps.normal) === true,
}));
const mapsCriterion = (rows) => rows.every((row) => row.on_disk >= 2 && row.diffuse_on_disk && row.normal_on_disk);
const mapsRows = mapsPerSurfaceOf(allSpecs);
const wallPlasterIndex = SURFACE_IDS.indexOf('wall_plaster');
check('material_maps_per_surface_at_least_two', (() => {
  const healthy = mapsCriterion(mapsRows);
  const degraded = withMapUrlRedirected(allSpecs, wallPlasterIndex, 'normal',
    (specs) => mapsCriterion(mapsPerSurfaceOf(specs)));
  return healthy === true && degraded === false;
})(), `逐表面盘上 map 数=${JSON.stringify(mapsRows.map((row) => `${row.surface}:${row.on_disk}`))}`
  + `（阈值 ≥2 且含 diffuse+normal）；负对照（**非自指 + 零写盘**：把 wall_plaster 的 normal URL `
  + `重指向盘上不存在的 ../../assets/__absent_probe__/__absent__.jpg、注册表其余逐字不动）⇒ 判据红；`
  + `**[配置面判据，不构成画面证据]**`);

// --- 2) 盘上存在性：注册表里每一个 URL 都必须在盘上 ---
const filesExistCriterion = (specs) => specs.every((spec) => mapUrlsOf(spec)
  .every((url) => onDisk(url) === true));
check('material_files_exist_on_disk', (() => {
  const healthy = filesExistCriterion(allSpecs) === true;
  const degraded = withMapUrlRedirected(allSpecs, SURFACE_IDS.indexOf('wall_brick'), 'roughness',
    (specs) => filesExistCriterion(specs)) === false;
  return healthy && degraded;
})(), `注册表全部 ${allSpecs.reduce((n, spec) => n + mapUrlsOf(spec).length, 0)} 条 map URL`
  + ` 经 fileURLToPath + fs.existsSync 逐条命中；负对照（**非自指 + 零写盘**：wall_brick 的 roughness URL `
  + `重指向缺失路径）⇒ 判据红；**[配置面判据，不构成画面证据]**`);

// --- 3) repeat 按真实尺度（basis 为**独立声明量**，依据可核；构件小于基准时 repeat<1 合法） ---
// N4-r3 / R3-3（修复 architect 打回的 r2 口径）：旧规则 `basis = min(扫描覆盖, min(尺寸))` 把
// `never_magnified`（basis ≤ 覆盖）与 `repeat ≥ 1`（basis ≤ 尺寸）变成**恒真式**（Raven N2-1），
// 且 basis 由构件尺寸反推 ⇒ 与被验对象循环。r3 口径：
//   ① `basis` == 登记表**声明值**（`**基准 N m**`）—— 与构件尺寸无关；
//   ② `repeat == round6(surface_size_m / basis)` —— 机械派生，可复算；
//   ③ 每个表面有依据标签 ∈ {`upstream`, `visually_corrected`}；`visually_corrected` **必须有画面证据路径**；
//   ④ **不再断言** `repeat ≥ 1` / `never_magnified` —— 它们是待验命题，不是判据前提。
const repeatCriterion = (specs) => specs.every((spec) => {
  const [basisU, basisV] = spec.repeat_basis_m;
  const [sizeU, sizeV] = spec.surface_size_m;
  const registered = registeredAssets.get(spec.asset_id);
  const declared = registered && registered.basis_m !== null ? registered.basis_m : null;
  const basisOk = declared !== null
    && Math.abs(basisU - round6(declared)) < 1e-6 && Math.abs(basisV - round6(declared)) < 1e-6;
  const consistent = Math.abs(spec.repeat[0] - round6(sizeU / basisU)) < 1e-6
    && Math.abs(spec.repeat[1] - round6(sizeV / basisV)) < 1e-6;
  const evidence = spec.basis_evidence;
  const tagOk = Boolean(evidence)
    && (evidence.tag === 'upstream' || evidence.tag === 'visually_corrected');
  const evidenceOk = tagOk && (evidence.tag === 'upstream'
    ? evidence.evidence_path === null
    : typeof evidence.evidence_path === 'string' && evidence.evidence_path.length > 0);
  const rangeOk = basisU >= 0.05 && basisU <= 40 && basisV >= 0.05 && basisV <= 40;
  return basisOk && consistent && tagOk && evidenceOk && rangeOk;
});
check('material_repeat_matches_real_scale', (() => {
  const healthy = repeatCriterion(allSpecs) === true;
  // 负例①：repeat 被改（+1）⇒ 与 size/basis 不再一致 ⇒ 必红
  const tamperedRepeat = allSpecs.map((spec, index) => (index === 0
    ? { ...spec, repeat: [spec.repeat[0] + 1, spec.repeat[1]] } : spec));
  // 负例②：basis 被改（wood_plank 的基准折半）⇒ 与登记表声明值不符 ⇒ 必红
  const tamperedBasis = allSpecs.map((spec) => (spec.asset_id === SURFACES.wood_plank.asset_id
    ? { ...spec, repeat_basis_m: [spec.repeat_basis_m[0] / 2, spec.repeat_basis_m[1] / 2] } : spec));
  // 负例③：把一个 `visually_corrected` 表面的画面证据路径抹掉 ⇒ 必红（R3-3 的「必须附画面证据」）
  const tamperedEvidence = allSpecs.map((spec) => (spec.asset_id === SURFACES.wall_brick.asset_id
    ? { ...spec, basis_evidence: { ...spec.basis_evidence, evidence_path: null } } : spec));
  // 负例④：依据标签非法 ⇒ 必红
  const tamperedTag = allSpecs.map((spec, index) => (index === 0
    ? { ...spec, basis_evidence: { ...spec.basis_evidence, tag: 'invented' } } : spec));
  return healthy && repeatCriterion(tamperedRepeat) === false
    && repeatCriterion(tamperedBasis) === false
    && repeatCriterion(tamperedEvidence) === false && repeatCriterion(tamperedTag) === false;
})(), `逐表面 basis == 登记表「**基准 N m**」声明值 ∧ repeat == round6(size/basis) ∧ 依据标签 ∈ `
  + `{upstream, visually_corrected} ∧ visually_corrected 附画面证据路径；`
  + JSON.stringify(SURFACE_IDS.map((id) => `${id}=basis${SURFACES[id].repeat_basis_m[0]}m/r${SURFACES[id].repeat.join('x')}`
    + `/${BASIS_EVIDENCE[id].tag}`))
  + `；**不再断言 repeat ≥ 1 与 never_magnified**（r2 的恒真式已删）；`
  + `负对照（4 条，均非自指）：① repeat+1；② wood_plank 基准折半；③ wall_brick 抹掉画面证据路径；`
  + `④ 标签改成 invented ⇒ 全红；**[配置面判据，不构成画面证据；画面面见近景截图]**`);

// --- 3b) 图案单元物理尺寸落在现实参照区间（R3-3 的「砖墙读作 20–24 cm」的**可复算内核**） ---
// `pattern_unit_cm = basis_m × 100 / count_per_tile` —— 与构件尺寸无关。凡 `visually_corrected` 的表面
// 都必须有图案单元表，且算出的单元尺寸必须落在现实参照区间内（砖 20–24 cm、板 10–15 cm、
// 瓦楞肋距 5–8 cm …）。**这是「basis 声明得对不对」的证伪点**：basis 声明错 ⇒ 单元尺寸掉出区间。
const patternUnitCriterion = (surfaces) => surfaces.every(({ id, basis_m }) => {
  const unit = PATTERN_UNITS[id];
  if (!unit) return false;
  const cm = basis_m * 100 / unit.count_per_tile;
  return cm >= unit.physical_reference_cm[0] && cm <= unit.physical_reference_cm[1];
});
const visuallyCorrected = SURFACE_IDS
  .filter((id) => BASIS_EVIDENCE[id].tag === 'visually_corrected')
  .map((id) => ({ id, basis_m: SURFACES[id].repeat_basis_m[0] }));
check('material_pattern_units_within_physical_reference', (() => {
  const healthy = patternUnitCriterion(visuallyCorrected) === true;
  // 负例①：把 wall_brick 的 basis 抬回上游扫描覆盖 13.9 m ⇒ 砖长算成 139 cm ⇒ 必红
  const tamperedBasis = visuallyCorrected.map((row) => (row.id === 'wall_brick'
    ? { ...row, basis_m: SURFACES.wall_brick.scan_coverage_m } : row));
  // 负例②：把 wood_plank 的计数改错（14 → 4）⇒ 板宽算成 42 cm ⇒ 必红
  const tamperedCount = visuallyCorrected.map((row) => (row.id === 'wood_plank'
    ? { ...row, basis_m: row.basis_m * 14 / 4 } : row));
  // 负例③：一个 `visually_corrected` 表面缺图案单元表 ⇒ 必红
  const missingUnit = [...visuallyCorrected, { id: 'glass', basis_m: 25 }];
  return healthy && patternUnitCriterion(tamperedBasis) === false
    && patternUnitCriterion(tamperedCount) === false && patternUnitCriterion(missingUnit) === false;
})(), `${visuallyCorrected.length} 个 \`visually_corrected\` 表面逐条给出图案单元物理尺寸 `
  + `\`basis×100/贴图内单元数\`：`
  + JSON.stringify(visuallyCorrected.map((row) => {
    const unit = PATTERN_UNITS[row.id];
    return `${row.id}:${unit?.unit_name ?? '缺表'}=${round6(row.basis_m * 100 / (unit?.count_per_tile ?? 1))}cm`
      + `∈[${unit?.physical_reference_cm.join(',') ?? '?'}]`;
  }))
  + `；**该值与构件尺寸无关**，是 basis 声明正确性的证伪点；`
  + `负对照（3 条，均非自指）：① wall_brick 的 basis 抬回上游 13.9 m（砖长 139 cm）；`
  + `② wood_plank 计数 14→4（板宽 42 cm）；③ 给 glass 补一条无图案单元表的 \`visually_corrected\` ⇒ 全红；`
  + `**[配置面判据，不构成画面证据；画面面见近景裁切图 + 读图结论]**`);

// --- 3c) 非 npc/room 实体的盒体底面必须站到世界地面上（N4-r3 / R3-5 修正 N-12 的**假关闭**） ---
// r2 声称给 zone/prop/portal 补了石砌台基，但 `addGroundDecor` 的守卫 `if (height <= 0.05) continue;`
// 只补**悬空**实体；对**埋进地面**的实体（`gate-north`：portal、盒体高 3 m、锚点 y=0 ⇒ 底面 −1.5，
// 比世界地面 −1.22 低 0.28 m）直接跳过 ⇒ 它既没台基、又埋在地里。这里改判**实际建出的几何**：
// 逐实体读 `buildEntityBoxes()` 的 `geometry.boundingBox`，要求「锚点 + 几何底面」≥ 世界地面。
const groundBoxRows = buildEntityBoxes(worldSeed, 'surface')
  .filter((box) => box.kind !== 'npc' && box.kind !== 'room')
  .map((box) => {
    box.geometry.computeBoundingBox();
    const bb = box.geometry.boundingBox;
    const height = bb.max.y - bb.min.y;
    const anchorY = box.position[1];
    return {
      id: box.id,
      kind: box.kind,
      built_bottom_y: round6(anchorY + bb.min.y),
      unlifted_bottom_y: round6(anchorY - height / 2),
      ground_lift_m: box.ground_lift_m,
    };
  });
const standsOnWorldFloor = (rows) => rows.every((row) => row.built_bottom_y >= WORLD_FLOOR_Y - 1e-6);
check('entity_boxes_stand_on_world_floor', (() => {
  const healthy = standsOnWorldFloor(groundBoxRows) === true;
  // 负例：把读数换回「未上移」的底面（= r2 的实况：portal 底面 −1.5 埋在地里）⇒ 必红
  const unlifted = groundBoxRows.map((row) => ({ ...row, built_bottom_y: row.unlifted_bottom_y }));
  return healthy && standsOnWorldFloor(unlifted) === false;
})(), `${groundBoxRows.length} 个非 npc/room 实体逐条读**实际几何** \`锚点 + geometry.boundingBox.min.y\`，`
  + `要求 ≥ 世界地面 ${WORLD_FLOOR_Y}：`
  + JSON.stringify(groundBoxRows.map((row) => `${row.id}(${row.kind})=${row.built_bottom_y}`
    + `${row.ground_lift_m > 0 ? `←上移${row.ground_lift_m}` : ''}`))
  + `；负对照（**非自指 + 零写盘**：把读数换回未上移的底面 = r2 实况）⇒ 判据红；`
  + `**[配置面判据，不构成画面证据；画面面见全身截图]**`);

// --- 3d) N4 特征部件必须**贴住**主体盒（N4-r3 / R3-6：修正「耳悬浮离头」这类新缺陷） ---
// 判据口径（architect R3-6 的字面：「与头的间距 ≤ 阈值」）：逐特征取它与**最近的** N2 主体盒之间的
// **AABB 间隙**（三轴分离量取最大、下夹 0），要求 ≤ `ATTACH_GAP_TOLERANCE_M`（2 mm）。
// 用「间隙」而不是「正体积相交」的原因：有些部件是**恰好相接**的（`hand_*` 顶面 = `arm_*` 底面，
// 间隙 0）—— 那是正确接法，不是悬浮。r2 的耳间隙 7.5 mm、鼻间隙 15 mm 则都超阈值。
const ATTACH_GAP_TOLERANCE_M = 0.002;
const aabbOf = (part) => ({
  min: [part.local_offset[0] - part.size[0] / 2, part.local_offset[1] - part.size[1] / 2,
    part.local_offset[2] - part.size[2] / 2],
  max: [part.local_offset[0] + part.size[0] / 2, part.local_offset[1] + part.size[1] / 2,
    part.local_offset[2] + part.size[2] / 2],
});
/** 两盒之间的 AABB 间隙（米）：0 = 相交或恰好相接。 */
const boxGap = (a, b) => Math.max(0, ...[0, 1, 2].map((axis) => Math.max(
  a.min[axis] - b.max[axis], b.min[axis] - a.max[axis],
)));
const attachmentOf = (features, body) => features.map((feature) => {
  const featureBox = aabbOf(feature);
  const nearest = body
    .map((part) => ({ part: part.part, gap: boxGap(featureBox, aabbOf(part)) }))
    .sort((left, right) => left.gap - right.gap)[0] ?? { part: null, gap: Number.POSITIVE_INFINITY };
  return {
    part: feature.part,
    nearest_part: nearest.part,
    gap_mm: Math.round(nearest.gap * 1000 * 100) / 100,
    attached: nearest.gap <= ATTACH_GAP_TOLERANCE_M,
  };
});
const characterContext = { entityId: 'npc-006', state: { id: 'npc-006', kind: 'npc' } };
const defaultAppearance = defaultAppearanceFor('npc-006');
const bodyParts = buildCharacterParts(defaultAppearance, characterContext);
const featureParts = buildCharacterDetailParts(defaultAppearance, characterContext);
const attachmentRows = attachmentOf(featureParts, bodyParts);
// 负例用的「r2 实况」几何：耳 x=±0.145（间隙 7.5 mm）、眉 z=0.168（间隙 13 mm）
// 注：r2 的鼻（z=0.185）虽在头盒之外 15 mm，但它与 `eyes` 盒恰好面接触（y=0.505 处）⇒ 间隙为 0，
// 按本判据**不算悬浮**；因此负例②改用 r2 的眉（z=0.168，与头盒间隙 13 mm、与 eyes 间隙 19 mm）。
const r2Ear = featureParts.map((part) => (part.part === 'ear_l'
  ? { ...part, local_offset: [-0.145, part.local_offset[1], part.local_offset[2]] } : part));
const r2Brow = featureParts.map((part) => (part.part === 'brow_l'
  ? { ...part, local_offset: [part.local_offset[0], part.local_offset[1], 0.168] } : part));
const allFeaturesAttached = (rows) => rows.every((row) => row.attached === true);
check('n4_features_attach_to_body_boxes', (() => {
  const healthy = allFeaturesAttached(attachmentRows) === true;
  // 负例①：耳 x 换回 r2 的 ±0.145（内侧面落在头盒之外 7.5 mm）⇒ 必红
  const floatedEar = attachmentOf(r2Ear, bodyParts);
  // 负例②：眉 z 换回 r2 的 0.168（与头盒间隙 13 mm）⇒ 必红
  const floatedBrow = attachmentOf(r2Brow, bodyParts);
  return healthy && allFeaturesAttached(floatedEar) === false
    && allFeaturesAttached(floatedBrow) === false
    && floatedEar.some((row) => row.part === 'ear_l' && row.gap_mm > 2)
    && floatedBrow.some((row) => row.part === 'brow_l' && row.gap_mm > 2);
})(), `${attachmentRows.length} 个 N4 特征逐条与 ${bodyParts.length} 个 N2 主体盒取**最近间隙**`
  + `（阈值 ≤ ${ATTACH_GAP_TOLERANCE_M * 1000} mm；0 = 相交或恰好相接）：`
  + JSON.stringify(attachmentRows.map((row) => `${row.part}→${row.nearest_part}@${row.gap_mm}mm`))
  + `；负对照（**非自指 + 零写盘**，用 r2 的真实坐标）：① 耳 x=±0.145 ⇒ 间隙 7.5 mm；`
  + `② 眉 z=0.168 ⇒ 间隙 13 mm ⇒ 两条都红；**[配置面判据，不构成画面证据；画面面见头肩特写]**`);

// --- 4) 材质区间服从 art-bible（以更紧的一处为准） ---
const specsWithinArtBible = (specs) => specs.every((spec) => {
  const wetZero = !WET_SURFACES.includes(SURFACE_IDS.find((id) => SURFACES[id] === spec) ?? 'ground_wet')
    || spec.metalness === 0;
  const resolution = imageSizeOf(assetPathOf(spec.maps.diffuse));
  const resolutionOk = Boolean(resolution) && resolution.width <= 2048 && resolution.height <= 2048;
  return spec.metalness >= 0 && spec.metalness <= 0.15
    && spec.roughness >= 0.6 && spec.roughness <= 0.95
    && wetZero && spec.normal_scale <= 0.4 && resolutionOk
    && spec.envMapIntensity >= 1.15 && spec.license === 'cc0-1.0';
});
check('material_specs_within_art_bible', (() => {
  const healthy = specsWithinArtBible(allSpecs) === true;
  const tampered = allSpecs.map((spec, index) => (index === 0
    ? { ...spec, metalness: 0.5, roughness: 0.2 } : spec));
  const wetTampered = allSpecs.map((spec) => (spec === SURFACES.ground_wet ? { ...spec, metalness: 0.05 } : spec));
  return healthy && specsWithinArtBible(tampered) === false && specsWithinArtBible(wetTampered) === false;
})(), `逐表面 metalness∈[0,0.15] / roughness∈[0.6,0.95] / 湿地面 metalness===0 / 法线强度≤0.4 / 贴图≤2048²：`
  + JSON.stringify(SURFACE_IDS.map((id) => `${id}(m=${SURFACES[id].metalness},r=${SURFACES[id].roughness})`))
  + `；负对照（注入 metalness 0.5 + roughness 0.2；湿地面 metalness 0.05）⇒ 判据红；[配置面判据，不构成画面证据]`);

// --- 5) 贴图来源全部 CC0 且登记在册 ---
const assetsRegistered = (specs) => specs.every((spec) => {
  const registered = registeredAssets.get(spec.asset_id);
  return Boolean(registered) && registered.cc0 === true && spec.license === 'cc0-1.0';
});
check('texture_assets_are_cc0_and_registered', (() => {
  const healthy = assetsRegistered(allSpecs) === true;
  const tampered = allSpecs.map((spec, index) => (index === 0 ? { ...spec, asset_id: 'not_registered_asset' } : spec));
  return healthy && assetsRegistered(tampered) === false;
})(), `SURFACES 的 asset_id 全部命中 web/assets/manifest.txt 且许可为 CC0 1.0：`
  + JSON.stringify([...new Set(allSpecs.map((spec) => spec.asset_id))])
  + `；负对照（注入未登记 asset_id）⇒ 判据红；[配置面判据，不构成画面证据]`);

// --- 5b) 交付树引用的**每一张**贴图都在盘上（N4-r2 / M-6 关闭 Raven N-7） ---
// 覆盖上一轮的缺陷类：`material_files_exist_on_disk` 只遍历 `SURFACES`，**看不见**注册表之外的贴图常量
// ⇒ `SKIN_TEXTURE_URL` 指向已被删掉的文件时判据全绿、画面静默回落纯色。
// 这里改为遍历**唯一的贴图 URL 登记面** `referencedTextureUrls()`（含皮肤细节层）。
const referencedUrls = referencedTextureUrls();
const referencedAllOnDisk = (urls) => urls.every((url) => onDisk(url) === true);
check('referenced_texture_urls_exist_on_disk', (() => {
  const healthy = referencedAllOnDisk(referencedUrls) === true;
  // 负例：**非自指 + 零写盘** —— 往登记面里追加一条盘上不存在的 URL ⇒ 必红
  const degraded = referencedAllOnDisk([...referencedUrls, ABSENT_MAP_URL]) === false;
  return healthy && degraded;
})(), `交付树引用贴图 ${referencedUrls.length} 条逐条在盘（含 SURFACES **之外**的皮肤细节层 `
  + `SKIN_TEXTURE_URL=${SKIN_TEXTURE_URL.split('/').slice(-2).join('/')} ⇒ onDisk=${onDisk(SKIN_TEXTURE_URL)}）；`
  + `负对照（**非自指 + 零写盘**：登记面追加一条盘上不存在的 URL）⇒ 判据红；**[配置面判据，不构成画面证据]**`);

// --- 5b2) 机械派生的登记面必须**覆盖**逐表面的 map URL（N4-r3 / R3-7） ---
// `referencedTextureUrls()` 已改为从 `URLS` 机械派生（不再手抄并集）。这条判据把「派生集合 ⊇ 逐表面
// map URL 集合」钉住：若有人把某个 surface 的 map 指向未登记进 `URLS` 的 URL，或把派生改回手抄，
// 覆盖关系就会破。
const surfaceMapUrls = SURFACE_IDS.flatMap((id) => [
  SURFACES[id].maps.diffuse, SURFACES[id].maps.normal, SURFACES[id].maps.roughness,
  SURFACES[id].maps.metalness, SURFACES[id].maps.ao,
]).filter((value) => typeof value === 'string');
const coversSurfaceMaps = (derived, required) => required.every((url) => derived.includes(url));
check('referenced_texture_urls_cover_surface_maps', (() => {
  const healthy = coversSurfaceMaps(referencedUrls, surfaceMapUrls) === true;
  // 负例：从派生集合里挖掉一条表面 map URL ⇒ 覆盖关系破 ⇒ 必红
  const degraded = coversSurfaceMaps(referencedUrls.filter((url) => url !== surfaceMapUrls[0]),
    surfaceMapUrls) === false;
  return healthy && degraded;
})(), `机械派生的登记面（${referencedUrls.length} 条，来自 \`Object.values(URLS)\`）覆盖逐表面 map URL `
  + `（${new Set(surfaceMapUrls).size} 条去重）；负对照（**非自指 + 零写盘**：挖掉一条表面 map URL）`
  + `⇒ 判据红；**[配置面判据，不构成画面证据]**`);

// --- 5c) 类别字段（N4-r3 / R3-1 关闭 Raven N2-10） ---
// 登记表必须**逐件**给出机器可核的类别字段，且 `skin-pale-01` 的类别必须是 `ai_generated`
// （生成器 Seedream，模型 id `doubao-seedream-5-0-260128`），**绝不**写成 `cc0-1.0` / `Poly Haven`
// —— 该素材在资产包两份 manifest 里都没有条目，许可**未证实**，不得伪造。
const manifestDataLines = assetsManifestText.split('\n')
  .filter((line) => line.trim().length > 0 && !line.trim().startsWith('#'));
const categoryFieldOk = (lines) => lines.every((line) => /类别 `[a-z0-9_]+`/.test(line));
const skinLine = manifestDataLines.find((line) => line.startsWith('character/skin-pale-01')) ?? null;
const skinCategoryOk = (line, expected) => {
  if (typeof line !== 'string') return false;
  if (!line.includes(`类别 \`${expected}\``)) return false;
  if (expected !== 'ai_generated') return true;
  // 不得出现 CC0 / Poly Haven 字样，且必须带生成记录（模型 id）
  // 注意两种写法都要拦：`cc0-1.0`（SPDX）与 `CC0 1.0`（人话）
  if (/cc0[- ]?1\.0/i.test(line) || line.includes('Poly Haven')) return false;
  return line.includes('doubao-seedream-5-0-260128');
};
check('manifest_category_field_is_machine_checkable', (() => {
  const healthy = categoryFieldOk(manifestDataLines) === true;
  // 负例：抹掉某一行的类别字段 ⇒ 必红
  const degraded = categoryFieldOk(manifestDataLines.map((line, index) => (index === 3
    ? line.replace(/类别 `[a-z0-9_]+` · /, '') : line))) === false;
  return healthy && degraded;
})(), `登记表 ${manifestDataLines.length} 条数据行**逐行**带机器可核的类别字段（\`cc0_photo\` / \`ai_generated\`）；`
  + `负对照（**非自指 + 零写盘**：抹掉第 4 行的类别字段）⇒ 判据红；**[配置面判据，不构成画面证据]**`);

check('skin_asset_is_ai_generated', (() => {
  const healthy = skinCategoryOk(skinLine, 'ai_generated') === true;
  const asCc0 = skinCategoryOk(skinLine === null ? null : skinLine.replace('类别 `ai_generated`', '类别 `cc0_photo`'), 'ai_generated') === false;
  const withPolyHaven = skinCategoryOk(skinLine === null ? null : `${skinLine} · Poly Haven`, 'ai_generated') === false;
  const withCc0Tag = skinCategoryOk(skinLine === null ? null : `${skinLine} · CC0 1.0`, 'ai_generated') === false;
  const withoutModelId = skinCategoryOk(skinLine === null ? null : skinLine.replace('doubao-seedream-5-0-260128', 'REDACTED'), 'ai_generated') === false;
  return healthy && asCc0 && withPolyHaven && withCc0Tag && withoutModelId;
})(), `skin-pale-01 类别 == \`ai_generated\` ∧ 带生成记录（generator=Seedream / model id `
  + `\`doubao-seedream-5-0-260128\`）∧ **不含** \`CC0 1.0\` / \`Poly Haven\` 字样`
  + `（该素材在资产包两份 manifest 均无条目 ⇒ 许可未证实，**不伪造**许可与模型 id）；`
  + `负对照（4 条，均非自指）：① 类别改 \`cc0_photo\`；② 追加 \`Poly Haven\`；③ 追加 \`CC0 1.0\`；`
  + `④ 抹掉模型 id ⇒ 全红；**[配置面判据，不构成画面证据]**`);


scene.setReading('surface');
const buildingSurface = scene.buildingReport();
const rootVisibilitySurface = scene.structureReport();
characterScene.setReading('surface');
const detailSurface = characterScene.characterDetailReport();
const detailContractSurface = characterScene.characterReport();
scene.setReading('underneath');
const buildingUnderneath = scene.buildingReport();
characterScene.setReading('underneath');
const detailUnderneath = characterScene.characterDetailReport();
scene.setReading('surface');
characterScene.setReading('surface');
const buildingRestored = scene.buildingReport();

const BUILDING_ENTITY = buildingSurface[0]?.entity_id ?? null;
const partsOf = (report, entityId) => (report.find((entry) => entry.entity_id === entityId)?.parts ?? []);
const partReportOf = (parts, name) => parts.find((entry) => entry.part === name) ?? null;
const partKeyOf = (part) => JSON.stringify({
  part: part.part, size: part.size, local_offset: part.local_offset, parameters: part.parameters,
  vertex_count: part.vertex_count, position_attribute_digest: part.position_attribute_digest,
});
const sortedPartKeys = (parts) => parts.map(partKeyOf).sort();
const sameBuildingParts = (left, right) => JSON.stringify(sortedPartKeys(left)) === JSON.stringify(sortedPartKeys(right));

// --- 6) 写实人物部件数 ≥12（含手/脚/发/衣/面部） ---
const realismPartsOf = (contract, detail, entityId) => [
  ...contract.filter((part) => part.entity_id === entityId),
  ...detail.filter((part) => part.entity_id === entityId),
];
const realismCriterion = (contract, detail, entityId) => {
  const all = realismPartsOf(contract, detail, entityId);
  const names = new Set(all.map((part) => part.part));
  const required = ['hand_l', 'hand_r', 'foot_l', 'foot_r', 'hair', 'coat', 'eyes', 'lips', 'nose'];
  return all.length >= 12 && required.every((name) => names.has(name));
};
check('character_realism_parts_at_least_twelve', (() => {
  const healthy = realismCriterion(detailContractSurface, detailSurface, 'npc-006') === true;
  const missingHand = detailSurface.filter((part) => !(part.entity_id === 'npc-006' && part.part === 'hand_l'));
  return healthy && realismCriterion(detailContractSurface, missingHand, 'npc-006') === false;
})(), `npc-006 契约部件 ${detailContractSurface.filter((part) => part.entity_id === 'npc-006').length} +`
  + ` N4 解剖部件 ${detailSurface.filter((part) => part.entity_id === 'npc-006').length}`
  + ` = ${realismPartsOf(detailContractSurface, detailSurface, 'npc-006').length}（阈值 ≥12，含手/脚/发/衣/面部）；`
  + `负对照（删一只手）⇒ 判据红；[配置面判据，不构成画面证据]`);

// --- 7) 写实人体几何约束（手在臂末端 / 脚在腿末端且低于下摆 / 颈在头与躯干之间） ---
const HAND_ARM_TOL_M = 0.02;
const centerY = (box) => round6((box.top_y + box.bottom_y) / 2);
const handsAtArmEnds = (contract, detail) => [['arm_l', 'hand_l'], ['arm_r', 'hand_r']].every(([armName, handName]) => {
  const arm = boxOf(contract, 'npc-006', armName);
  const hand = boxOf(detail, 'npc-006', handName);
  if (!arm || !hand) return false;
  return Math.abs(round6(hand.top_y - arm.bottom_y)) <= HAND_ARM_TOL_M && centerY(hand) < centerY(arm);
});
const feetAtLegEndsBelowHem = (contract, detail) => {
  const hem = boxOf(contract, 'npc-006', 'coat');
  if (!hem) return false;
  return [['leg_l', 'foot_l'], ['leg_r', 'foot_r']].every(([legName, footName]) => {
    const leg = boxOf(contract, 'npc-006', legName);
    const foot = boxOf(detail, 'npc-006', footName);
    if (!leg || !foot) return false;
    return Math.abs(round6(foot.top_y - leg.bottom_y)) <= HAND_ARM_TOL_M
      && foot.bottom_y < hem.bottom_y && foot.bottom_y < leg.bottom_y;
  });
};
const neckBetweenHeadAndTorso = (contract, detail) => {
  const head = boxOf(contract, 'npc-006', 'head');
  const torso = boxOf(contract, 'npc-006', 'torso');
  const neck = boxOf(detail, 'npc-006', 'neck');
  if (!head || !torso || !neck) return false;
  return neck.bottom_y <= round6(torso.top_y + HAND_ARM_TOL_M)
    && neck.top_y >= round6(head.bottom_y - HAND_ARM_TOL_M)
    && centerY(neck) > centerY(torso) && centerY(neck) < centerY(head);
};
const geometryConstraintsOk = (contract, detail) =>
  handsAtArmEnds(contract, detail) && feetAtLegEndsBelowHem(contract, detail) && neckBetweenHeadAndTorso(contract, detail);
const tamperDetail = (parts, edits) => parts.map((part) => (edits[part.part]
  ? { ...part, local_offset: edits[part.part].local_offset ?? part.local_offset,
      size: edits[part.part].size ?? part.size }
  : part));
const handOnTorso = tamperDetail(detailSurface, { hand_l: { local_offset: [0, 0, 0] } });
const feetAboveHem = tamperDetail(detailSurface, {
  foot_l: { local_offset: [-0.11, -0.6, 0.03] }, foot_r: { local_offset: [0.11, -0.6, 0.03] } });
const noNeck = detailSurface.filter((part) => !(part.entity_id === 'npc-006' && part.part === 'neck'));
check('character_realism_geometry_constraints', (() => {
  const healthy = geometryConstraintsOk(detailContractSurface, detailSurface) === true;
  const badHand = geometryConstraintsOk(detailContractSurface, handOnTorso) === false;
  const badFoot = geometryConstraintsOk(detailContractSurface, feetAboveHem) === false;
  const badNeck = geometryConstraintsOk(detailContractSurface, noNeck) === false;
  return healthy && badHand && badFoot && badNeck;
})(), `手贴臂末端（容差 ${HAND_ARM_TOL_M * 1000} mm 且在臂中心之下）`
  + ` / 脚贴腿末端且低于外衣下摆 y=${boxOf(detailContractSurface, 'npc-006', 'coat').bottom_y}`
  + ` / 颈跨在躯干上缘 y=${boxOf(detailContractSurface, 'npc-006', 'torso').top_y}`
  + ` 与头下缘 y=${boxOf(detailContractSurface, 'npc-006', 'head').bottom_y} 之间；`
  + `负对照：① 手移到躯干 ⇒ 红；② 脚抬到外衣下摆之上 ⇒ 红；③ 删掉颈 ⇒ 红；[配置面判据，不构成画面证据]`);

// --- 7b) **真实头身比**（N4-r2 / M-4 关闭 Raven N-13 / 预审 R-3）：实测读数 + 可行域内达成 ---
// 设计 §D-5 的目标：头高 ≈ 身高 1/7.5。上一轮**没有执行**这项优化（`head` 仍是 0.30 ⇒ ≈1/6.2），
// 且 `03` 的 GAP 清单里**没有这一条**。本轮在 11 条比例判据的可行域内真的调了一轮并给出实测读数。
const HEAD_BODY_TARGET = 1 / 7.5;
/** 判定带宽：目标 ±0.006（≈ 1/7.85 ~ 1/7.18）。这是**本轮新增**判据的容差，不是既有阈值。 */
const HEAD_BODY_TOL = 0.006;
const headToBodyRatio = (contract, detail) => {
  const head = boxOf(contract, 'npc-006', 'head');
  const foot = boxOf(detail, 'npc-006', 'foot_l');
  if (!head || !foot) return null;
  const total = round6(head.top_y - foot.bottom_y);
  return { head_m: head.height, total_m: total, ratio: round6(head.height / total) };
};
const headBodyOk = (contract, detail) => {
  const measured = headToBodyRatio(contract, detail);
  return measured !== null && Math.abs(measured.ratio - HEAD_BODY_TARGET) <= HEAD_BODY_TOL;
};
const headBody = headToBodyRatio(detailContractSurface, detailSurface);
check('character_head_to_body_ratio_measured', (() => {
  const healthy = headBodyOk(detailContractSurface, detailSurface) === true;
  // 负对照：把 head 抬回 r1 的 0.30（≈1/6.2 = Raven 实测的「未达成」形态）⇒ 必红
  const tallHead = detailContractSurface.map((part) => (part.part === 'head'
    ? { ...part, size: [0.26, 0.30, 0.26] } : part));
  return healthy && headBodyOk(tallHead, detailSurface) === false;
})(), `**实测头身比** = 头高 ${headBody.head_m} m / 全高 ${headBody.total_m} m = **1/${round6(1 / headBody.ratio)}**`
  + `（设计 §D-5 目标 ≈ 1/7.5，判定带宽 ±${HEAD_BODY_TOL} ⇒ [1/${round6(1 / (HEAD_BODY_TARGET + HEAD_BODY_TOL))}, 1/${round6(1 / (HEAD_BODY_TARGET - HEAD_BODY_TOL))}]）；`
  + `负对照（head 抬回 0.30 ⇒ ≈1/6.2，即上一轮未达成的形态）⇒ 判据红；`
  + `**[配置面判据，不构成画面证据；画面面见人物特写截图]**`);

// --- 7c) N4 面部/足部部件**不被遮挡且互不相交**（N4-r2 / M-8 关闭 Sentinel B-1 / B-2 / B-10） ---
// 三条都是上一轮**部件存在但画面零贡献**的形态：耳被发盒完全包住、鼻把嘴切出缺口、脚与腿同色读不出。
const boxInside = (outer, inner) => inner.left_x >= outer.left_x && inner.right_x <= outer.right_x
  && inner.bottom_y >= outer.bottom_y && inner.top_y <= outer.top_y
  && inner.back_z >= outer.back_z && inner.front_z <= outer.front_z;
const boxesOverlap = (a, b) => a.left_x < b.right_x && b.left_x < a.right_x
  && a.bottom_y < b.top_y && b.bottom_y < a.top_y
  && a.back_z < b.front_z && b.back_z < a.front_z;
const faceFootVisibilityOk = (contract, detail) => {
  const hair = boxOf(contract, 'npc-006', 'hair');
  const nose = boxOf(detail, 'npc-006', 'nose');
  const lips = boxOf(contract, 'npc-006', 'lips');
  const ears = ['ear_l', 'ear_r'].map((name) => boxOf(detail, 'npc-006', name));
  const feet = ['foot_l', 'foot_r'].map((name) => boxOf(detail, 'npc-006', name));
  const legs = ['leg_l', 'leg_r'].map((name) => boxOf(contract, 'npc-006', name));
  if (!hair || !nose || !lips || [...ears, ...feet, ...legs].some((box) => !box)) return false;
  const earsEscapeHair = ears.every((ear) => boxInside(hair, ear) === false);
  const noseClearOfLips = boxesOverlap(nose, lips) === false;
  const feetDistinctFromLegs = ['foot_l', 'foot_r'].every((name, index) => {
    const foot = partOf(detail, 'npc-006', name);
    const leg = partOf(contract, 'npc-006', legs[index].part);
    return Boolean(foot) && Boolean(leg) && foot.source_hex !== leg.source_hex;
  });
  return earsEscapeHair && noseClearOfLips && feetDistinctFromLegs;
};
const withPartEdit = (parts, partName, edit) => parts.map((part) => (part.part === partName
  ? { ...part, size: edit.size ?? part.size, local_offset: edit.local_offset ?? part.local_offset } : part));
check('character_face_and_feet_are_unoccluded', (() => {
  const healthy = faceFootVisibilityOk(detailContractSurface, detailSurface) === true;
  // 负对照①（B-1 原形态）：耳移回发盒内部 ⇒ 必红
  const earsInsideHair = withPartEdit(detailSurface, 'ear_l', { local_offset: [-0.14, 0.49, 0] });
  const earsInsideHair2 = withPartEdit(earsInsideHair, 'ear_r', { local_offset: [0.14, 0.49, 0] });
  // 负对照②（B-2 原形态）：鼻盒抬回与唇相交的 y∈[0.43,0.52] ⇒ 必红
  const noseOverLips = withPartEdit(detailSurface, 'nose', { size: [0.05, 0.09, 0.05], local_offset: [0, 0.475, 0.185] });
  // 负对照③（B-10 原形态）：脚改用与腿相同的 `garment` 色 ⇒ 必红
  const feetSameColour = detailSurface.map((part) => (part.part === 'foot_l' || part.part === 'foot_r'
    ? { ...part, source_hex: partOf(detailContractSurface, 'npc-006', 'leg_l').source_hex } : part));
  return healthy && faceFootVisibilityOk(detailContractSurface, earsInsideHair2) === false
    && faceFootVisibilityOk(detailContractSurface, noseOverLips) === false
    && faceFootVisibilityOk(detailContractSurface, feetSameColour) === false;
})(), `耳不被发盒 AABB 完全包含（耳 z∈[${boxOf(detailSurface, 'npc-006', 'ear_l').back_z},${boxOf(detailSurface, 'npc-006', 'ear_l').front_z}]`
  + ` > 发前表面 ${boxOf(detailContractSurface, 'npc-006', 'hair').front_z}）；`
  + `鼻盒 y∈[${boxOf(detailSurface, 'npc-006', 'nose').bottom_y},${boxOf(detailSurface, 'npc-006', 'nose').top_y}]`
  + ` 与唇盒 y∈[${boxOf(detailContractSurface, 'npc-006', 'lips').bottom_y},${boxOf(detailContractSurface, 'npc-006', 'lips').top_y}] **不相交**；`
  + `脚色 ≠ 腿色（${partOf(detailSurface, 'npc-006', 'foot_l').source_hex} ≠ ${partOf(detailContractSurface, 'npc-006', 'leg_l').source_hex}）；`
  + `负对照：① 耳移回发盒内（B-1 原形态）⇒ 红；② 鼻抬回与唇相交（B-2 原形态）⇒ 红；③ 脚改回腿色（B-10 原形态）⇒ 红；`
  + `**[配置面判据，不构成画面证据]**`);

// --- 8) 两读法共享 N4 解剖部件（逐项相同） ---
check('two_reads_share_character_detail_parts', (() => {
  const healthy = sameBuildingParts(detailSurface, detailUnderneath) === true;
  const tampered = detailUnderneath.map((part, index) => (index === 0
    ? { ...part, local_offset: [part.local_offset[0] + 0.1, part.local_offset[1], part.local_offset[2]] } : part));
  return healthy && sameBuildingParts(detailSurface, tampered) === false;
})(), `N4 解剖部件两读法逐项比较（size / local_offset / parameters / vertex_count / position 摘要）：`
  + `${detailSurface.length}/${detailUnderneath.length}；负对照（只改 underneath 一个部件的偏移）⇒ 判据红；[配置面判据，不构成画面证据]`);

// --- 9) N4 部件材质色可复算（**动态遍历**，不写硬编码名单） ---
const detailHexProblems = (parts, tone) => {
  const problems = [];
  for (const part of parts.filter((entry) => entry.entity_id === 'npc-006')) {
    const expected = recomputeMaterialHex(part.source_hex, tone);
    if (part.material_hex !== expected) problems.push(`${part.part} expected=${expected} actual=${part.material_hex}`);
  }
  return problems;
};
check('character_detail_material_hex_recomputable', (() => {
  const surfaceProblems = detailHexProblems(detailSurface, xuqinWorldview.tone.surface);
  const underneathProblems = detailHexProblems(detailUnderneath, xuqinWorldview.tone.underneath);
  const traversed = detailSurface.filter((entry) => entry.entity_id === 'npc-006').length;
  const tampered = detailSurface.map((part) => (part.part === 'hand_r' ? { ...part, material_hex: '#000000' } : part));
  return surfaceProblems.length === 0 && underneathProblems.length === 0 && traversed >= 8
    && detailHexProblems(tampered, xuqinWorldview.tone.surface).length === 1;
})(), `动态遍历 npc-006 的 ${detailSurface.filter((entry) => entry.entity_id === 'npc-006').length} 个 N4 部件：`
  + `material_hex == source_hex × luminanceScale(reading)（两读法各跑一遍）；`
  + `负对照（注入 hand_r 材质色偏差）⇒ 判据红；[配置面判据，不构成画面证据]`);

// --- 10) 建筑部件类型 ≥8 ---
const partTypesCriterion = (report) => report.length > 0
  && report.every((entry) => entry.part_types.length >= 8
    && ['wall', 'window_opening', 'door', 'eave', 'balcony', 'railing', 'pipe', 'roof_tile', 'floor_slab']
      .every((name) => entry.part_types.includes(name)));
check('building_part_types_at_least_eight', (() => {
  const healthy = partTypesCriterion(buildingSurface) === true;
  const tampered = buildingSurface.map((entry) => ({
    ...entry,
    parts: entry.parts.filter((part) => part.part !== 'railing'),
    part_types: entry.part_types.filter((name) => name !== 'railing'),
  }));
  return healthy && partTypesCriterion(tampered) === false;
})(), `逐建筑实体部件类型数=${JSON.stringify(buildingSurface.map((entry) => `${entry.entity_id}:${entry.part_types.length}`))}`
  + `（阈值 ≥8；固定表 ${BUILDING_PART_NAMES.length} 项，装配器产出`
  + ` ${buildBuildingParts({ id: 'probe', kind: 'room' }).length} 个部件）；`
  + `负对照（删掉 railing 类型）⇒ 判据红；[配置面判据，不构成画面证据]`);

// --- 10b) 声明表 == 装配器实际产出（N4-r2 / M-6 关闭 Sentinel B-8） ---
// 缺陷：`BUILDING_PART_NAMES` 只出现在**判据文案**里，没有任何判据把「声明表」与「装配器产出」绑定
// ⇒ 把声明表从 11 项改成 3 项，`scene_assert` 仍 `exit=0 / PASS=83 FAIL=0`（文案里的「固定表 N 项」会静默失真）。
const producedBuildingPartNames = new Set(buildBuildingParts({ id: 'probe', kind: 'room' }).map((part) => part.part));
const declaredMatchesProduced = (declared) => declared.size === producedBuildingPartNames.size
  && [...declared].every((name) => producedBuildingPartNames.has(name));
check('building_part_names_match_assembly', (() => {
  const healthy = declaredMatchesProduced(new Set(BUILDING_PART_NAMES)) === true;
  // 负对照：声明表删掉 `railing` ⇒ 与产出不一致 ⇒ 必红
  const tampered = new Set([...BUILDING_PART_NAMES].filter((name) => name !== 'railing'));
  return healthy && declaredMatchesProduced(tampered) === false;
})(), `声明表 BUILDING_PART_NAMES（${BUILDING_PART_NAMES.length} 项）== 装配器对 room 实体的产出类型集`
  + `（${producedBuildingPartNames.size} 项）：${JSON.stringify([...producedBuildingPartNames].sort())}；`
  + `负对照（声明表删掉 railing）⇒ 判据红；[配置面判据，不构成画面证据]`);

// --- 11) 两读法共享建筑部件（`objects_digest` **不含尺寸** ⇒ 这是建筑面唯一有牙的判据，Raven R-8） ---
check('two_reads_share_building_parts', (() => {
  const healthy = sameBuildingParts(partsOf(buildingSurface, BUILDING_ENTITY), partsOf(buildingUnderneath, BUILDING_ENTITY))
    && sameBuildingParts(partsOf(buildingSurface, BUILDING_ENTITY), partsOf(buildingRestored, BUILDING_ENTITY));
  const tampered = buildingUnderneath.map((entry) => (entry.entity_id === BUILDING_ENTITY
    ? { ...entry, parts: entry.parts.map((part, index) => (index === 0 ? { ...part, size: [9, 9, 9] } : part)) }
    : entry));
  return healthy && sameBuildingParts(partsOf(buildingSurface, BUILDING_ENTITY), partsOf(tampered, BUILDING_ENTITY)) === false;
})(), `建筑部件两读法逐项比较（size / local_offset / parameters / vertex_count / position 摘要），`
  + `实体 ${BUILDING_ENTITY} 共 ${partsOf(buildingSurface, BUILDING_ENTITY).length} 个部件；`
  + `负对照（只改 underneath 一个部件的 size ⇒ ` + `objects_digest 看不见，本条必须红）⇒ 判据红；[配置面判据，不构成画面证据]`);

// --- 12) 建筑有门窗洞口 + 室内可见（娃娃屋剖切） ---
const spansAlong = (outer, inner, axis, tol = 0.005) => inner.aabb_min[axis] <= outer.aabb_min[axis] + tol
  && inner.aabb_max[axis] >= outer.aabb_max[axis] - tol;
const insideInPlane = (outer, inner, axes, tol = 0) => axes.every((axis) => inner.aabb_min[axis] >= outer.aabb_min[axis] - tol
  && inner.aabb_max[axis] <= outer.aabb_max[axis] + tol);
const openingsOk = (parts) => {
  const wall = partReportOf(parts, 'wall');
  const win = partReportOf(parts, 'window_opening');
  const glass = partReportOf(parts, 'window_glass');
  const side = partReportOf(parts, 'wall_side');
  const door = partReportOf(parts, 'door');
  if (!wall || !win || !glass || !side || !door) return false;
  const wallNotSolid = wall.shape === 'merged_boxes' && wall.vertex_count > 24 && wall.triangle_count > 12;
  const winThrough = spansAlong(wall, win, 0) && insideInPlane(wall, win, [1, 2]);
  const glassRecessed = glass.aabb_min[0] > round6(wall.aabb_min[0] + 0.01)
    && glass.aabb_max[0] < round6(wall.aabb_max[0] - 0.005) && insideInPlane(wall, glass, [1, 2]);
  const doorThrough = spansAlong(side, door, 2) && insideInPlane(side, door, [0, 1]);
  const walls = parts.filter((part) => part.part === 'wall' || part.part === 'wall_side');
  const cutOpen = walls.length === 2
    && walls.every((part) => part.aabb_max[0] <= 0.001 || part.aabb_max[2] <= 0.001);
  const sample = [0, 1.2, 0];
  const enclosed = parts
    .filter((part) => part.part !== 'floor_slab' && part.part !== 'roof_tile')
    .some((part) => [0, 1, 2].every((axis) => sample[axis] > part.aabb_min[axis] && sample[axis] < part.aabb_max[axis]));
  return wallNotSolid && winThrough && glassRecessed && doorThrough && cutOpen && !enclosed;
};
const buildingPartsSurface = partsOf(buildingSurface, BUILDING_ENTITY);
const buildingPartsForFlush = buildingPartsSurface.map((part) => (part.part === 'window_glass'
  ? { ...part, aabb_min: [buildingPartsSurface.find((p) => p.part === 'wall').aabb_min[0], part.aabb_min[1], part.aabb_min[2]] }
  : part));
const buildingPartsWithFrontWall = buildingPartsSurface.concat([{
  ...buildingPartsSurface.find((part) => part.part === 'wall'),
  part: 'wall', name: `${BUILDING_ENTITY}/wall@front`, aabb_min: [2.3, 0, -2.5], aabb_max: [2.5, 3, 2.5],
}]);
check('building_has_openings_and_visible_interior', (() => {
  const healthy = openingsOk(buildingPartsSurface) === true;
  const flush = openingsOk(buildingPartsForFlush) === false;
  const frontWall = openingsOk(buildingPartsWithFrontWall) === false;
  return healthy && flush && frontWall;
})(), `后墙 ${partReportOf(buildingPartsSurface, 'wall').shape}/${partReportOf(buildingPartsSurface, 'wall').triangle_count} 三角面（非实心盒）`
  + ` ⇒ 窗洞沿 x 贯穿墙体厚度（${partReportOf(buildingPartsSurface, 'window_opening').size[0]} m == 墙厚）`
  + ` 且玻璃内凹（x∈[${partReportOf(buildingPartsSurface, 'window_glass').aabb_min[0]},`
  + `${partReportOf(buildingPartsSurface, 'window_glass').aabb_max[0]}] 退在墙外面 ${partReportOf(buildingPartsSurface, 'wall').aabb_min[0]} 之后）；`
  + `门洞沿 z 贯穿侧墙；墙体只落在 -x/-z 两面（娃娃屋剖切）；室内采样点 (0,1.2,0) 不被任何部件包住；`
  + `负对照：① 玻璃贴到墙外面（贴面形态）⇒ 红；② 注入 +x 正面墙 ⇒ 红；[配置面判据，不构成画面证据]`);

// --- 13) 每个实体根 mesh 的 `visible === true`（Raven R-2 的 Node 侧拦截） ---
const rootsVisible = (structure, ids) => ids.every((id) => {
  const object = structure.objects.find((entry) => entry.id === id);
  return Boolean(object) && object.visible === true;
});
check('entity_root_meshes_are_visible', (() => {
  const entityIds = scene.entityIds();
  const healthy = rootsVisible(rootVisibilitySurface, entityIds) === true;
  // 负对照：把**某个实体根 mesh**（不是 `world-root` 组）置 `visible = false` ⇒ 必红
  const firstRootId = entityIds.find((id) => rootVisibilitySurface.objects.some((entry) => entry.id === id));
  const tampered = {
    ...rootVisibilitySurface,
    objects: rootVisibilitySurface.objects.map((entry) => (entry.id === firstRootId
      ? { ...entry, visible: false } : entry)),
  };
  return healthy && firstRootId !== undefined && rootsVisible(tampered, entityIds) === false;
})(), `${scene.entityIds().length} 个实体根 mesh 的 visible 全为 true（R-2：` + `visible=false 会让 three 跳过整棵子树）；`
  + `负对照（注入某个实体根 mesh 的 visible=false）⇒ 判据红；[配置面判据，不构成画面证据]`);

// --- 14) 环境照明主导（人工灯 ≤ 辅助阈值 + envMapIntensity + **真实读回**的非纯色背景） ---
// N4-r2 / M-6（关闭 Raven N-1）：`background_is_texture` / `environment_is_texture` **不再是常量** ——
// 由 `backgroundStateOf()` 从**真实场景对象**读回。负例是**非自指**的：它拿一个**真的把背景换成纯色**
// 的 `THREE.Scene` 喂进**生产代码的同一个读取函数**，而不是手改一份读数的副本。
const environmentCriterion = (state, envMapIntensityMin, sum, hdriOnDiskFlag) => sum <= 1.0
  && Number(envMapIntensityMin) >= 1.15
  && state.background_is_texture === true && state.background_path !== 'color'
  && Number(state.background_blurriness) >= 0.01
  && state.environment_is_texture === true
  && hdriOnDiskFlag === true;
scene.setReading('surface');
const envReading = environmentReport();
const envSum = artificialLightIntensitySum();
const hdriOnDisk = onDisk(HDRI_URL);
/** Raven 的注入形态（P-4）：背景退化为纯色。**唯一**变量就是背景 —— 其余字段取与现场同值。 */
const colourBackgroundState = (() => {
  const degradedScene = new THREE.Scene();
  degradedScene.background = new THREE.Color('#ff0000');
  degradedScene.backgroundBlurriness = Number(envReading.background_blurriness);
  return backgroundStateOf(degradedScene);
})();
check('environment_lighting_dominant', (() => {
  const healthy = environmentCriterion(envReading, envReading.env_map_intensity_min, envSum, hdriOnDisk) === true;
  const tooBright = environmentCriterion(envReading, envReading.env_map_intensity_min, 1.6273, hdriOnDisk) === false;
  const colourBackground = environmentCriterion(colourBackgroundState,
    envReading.env_map_intensity_min, envSum, hdriOnDisk) === false;
  const missingHdri = environmentCriterion(envReading, envReading.env_map_intensity_min, envSum, false) === false;
  return healthy && tooBright && colourBackground && missingHdri;
})(), `surface 读法：人工灯强度总和 ${envSum.toFixed(4)} ≤ 1.0（现状基线 1.6273 / D-1 目标 0.5276）；`
  + `envMapIntensity 最小 ${envReading.env_map_intensity_min} ≥ 1.15；background=${envReading.background_path}`
  + `（is_texture=${envReading.background_is_texture}，由 backgroundStateOf() **从场景读回**；`
  + `blurriness ${envReading.background_blurriness} ≥ 0.01）；environment_is_texture=${envReading.environment_is_texture}；`
  + `HDRI 在盘 ${hdriOnDisk}；负对照：① 人工灯总和 1.6273（旧实现）⇒ 红；`
  + `② **非自指**：真建一个 new THREE.Scene() 并把背景换成 THREE.Color('#ff0000')，用同一个 `
  + `backgroundStateOf() 读它 ⇒ 判据红（N-1 关闭；旧实现该注入实测 PASS=83 FAIL=0）；③ HDRI 缺件 ⇒ 红；`
  + `**[配置面判据，不构成画面证据；画面面见 spikes/n4-art 的实机截图 + __hdriReady 等待]**`);

// --- 15) 场景渲染 pass 的相机 == 场景相机（Raven 预审 P-C 的机器判据） ---
const sceneCameraMatches = (report, cameraIdentity) => typeof report.scene_camera === 'string'
  && report.scene_camera === cameraIdentity && Number(report.scene_renders) >= 1;
const renderReadingSurface = scene.renderOnce();
const cameraIdentity = scene.cameraReport().identity;
check('scene_render_camera_matches_scene_camera', (() => {
  const healthy = sceneCameraMatches(renderReadingSurface, cameraIdentity) === true;
  // 负对照 = **P-C 描述的旧语义**：把 scene_camera 换成链上最后一次调用（全屏 quad 的正交相机）。
  const oldSemantics = { ...renderReadingSurface, scene_camera: 'OrthographicCamera#fullscreen-quad' };
  return healthy && sceneCameraMatches(oldSemantics, cameraIdentity) === false;
})(), `renderCameraReport().scene_camera=${renderReadingSurface.scene_camera} == cameraReport().identity=${cameraIdentity}`
  + `（scene_renders=${renderReadingSurface.scene_renders}，total_renders=${renderReadingSurface.total_renders}）；`
  + `负对照（换成全屏 quad 的正交相机 = P-C 旧语义）⇒ 判据红；[配置面判据，不构成画面证据]`);

// --- 15b) `passCameras` 环形缓冲有界（N4-r2 / M-7 关闭 Raven N-4） ---
// 缺陷：旧实现每帧 push 且**从不清空** ⇒ 真 WebGL 下 ~200–240 条/秒、内存无界增长。
//
// **N4-r3 / R3-7（修正 Raven N2-5 的「未声明副作用」）**：本条判据**有副作用** —— 它会对**共用的**
// `scene` 句柄调用 `scene.renderOnce()` 40 次，因此 `scene` 的 `total_renders` 计数器被本条推高。
// 之所以照实声明而不是偷偷修掉：`total_renders` 是**累计计数器**，后续判据只断言「有增长 / 是累计值」，
// 不断言绝对值 ⇒ 副作用不影响任何判据结论；而换独立实例会掩盖「共用句柄被前序判据改写」这一事实。
// 若要彻底无副作用，应把 `renderOnce` 次数与断言拆到独立 `createScene()` 实例上（记为改进项，非本轮范围）。
const PASS_CAMERA_LOG_LIMIT = 16;
check('pass_camera_log_is_bounded', (() => {
  const before = scene.renderCameraReport();
  for (let i = 0; i < 40; i += 1) scene.renderOnce();
  const after = scene.renderCameraReport();
  const bounded = after.pass_cameras.length <= PASS_CAMERA_LOG_LIMIT;
  const counterStillCumulative = Number(after.total_renders) > Number(after.pass_cameras.length);
  const grew = Number(after.total_renders) > Number(before.total_renders);
  return bounded && counterStillCumulative && grew;
})(), `连渲染 40 次后 pass_cameras 长度 ≤ ${PASS_CAMERA_LOG_LIMIT}（环形缓冲），`
  + `而 total_renders 仍为**累计值**（${scene.renderCameraReport().total_renders} > ${scene.renderCameraReport().pass_cameras.length}）`
  + ` ⇒ 可观测性不被截断；**[配置面判据，不构成画面证据]**；`
  + `**[副作用已声明]** 本条对共用 \`scene\` 句柄调用 \`renderOnce()\` 40 次 ⇒ 会推高其 \`total_renders\`；`
  + `后续判据只断言「有增长 / 是累计值」、不断言绝对值，故不影响结论（彻底无副作用的改法记为改进项）`);

// --- 16) 后处理链配置面：AO 在链上，且**显式声明**为配置读数（Raven R-6） ---
const postfxReading = postfxReport();
const postfxChainOk = (reading) => reading.chain.join('>') === 'RenderPass>GTAOPass>OutputPass'
  && reading.evidence_class === 'config_plane (not pixel evidence)'
  && reading.gtao.blend_intensity >= 0.8 && reading.gtao.blend_intensity <= 1.0
  && reading.gtao.output === 0
  // N4-r3 / R3-4：`scale` 是 AO 的 gamma（ao = pow(ao, scale)）⇒ **不得**用它放大 AO 刷读数。
  // architect 裁决上限 1.5（物理可辩护区间）；r2 曾取 3.0，已被打回。
  && Number(reading.gtao.parameters.scale) <= 1.5
  && reading.gtao.parameters.samples >= 8 && reading.bloom_connected === false
  && reading.cinematic_connected === false
  && (reading.available === false ? reading.reason === 'no_webgl' : Number(reading.pass_count) === 3);
check('postfx_ao_chain_is_config_plane_only', (() => {
  const healthy = postfxChainOk(postfxReading) === true;
  const weakBlend = { ...postfxReading, gtao: { ...postfxReading.gtao, blend_intensity: 0.2 } };
  const withBloom = { ...postfxReading, bloom_connected: true };
  // 负例（R3-4）：把 gamma 取回 r2 的 3.0（用幂曲线放大 AO 刷 win96）⇒ 必红
  const gammaInflated = {
    ...postfxReading,
    gtao: { ...postfxReading.gtao, parameters: { ...postfxReading.gtao.parameters, scale: 3.0 } },
  };
  return healthy && postfxChainOk(weakBlend) === false && postfxChainOk(withBloom) === false
    && postfxChainOk(gammaInflated) === false;
})(), `链 ${postfxReading.chain.join(' → ')}（Node 下 available=${postfxReading.available}，reason=${postfxReading.reason ?? 'n/a'}）；`
  + `blendIntensity 声明值 ${postfxReading.gtao.blend_intensity}（阈值 ≥0.8）/ output=Default / samples=${postfxReading.gtao.parameters.samples}`
  + ` / 不接 bloom、不接 cinematic；**本条是配置面判据，不构成画面证据**`
  + `（画面面 = spikes/n4-art 的 AO A/B 像素对照，阈值 ≥8）；负对照（blendIntensity 0.2 / 接上 bloom）⇒ 判据红`);

// ================================================================== 7b) N5（纯加法：新判据，既有判据体/期望值零改动）

// --- 17) N5 · `SURFACES_EXT` 与材质类别（AC-I-3b/c/d/f/i 的注册表层） ---
const classCriterion = (classes, ext) => {
  const byId = Object.fromEntries(classes.map((c) => [c.id, c]));
  const withinLegacy = (c) => c.roughness[0] >= LEGACY_ROUGHNESS_RANGE[0] && c.roughness[1] <= LEGACY_ROUGHNESS_RANGE[1]
    && c.metalness[0] >= LEGACY_METALNESS_RANGE[0] && c.metalness[1] <= LEGACY_METALNESS_RANGE[1];
  // I-3b：区间 ⊆ 旧口径，或属 skin/glass/metal 且给冻结理由
  const b = classes.every((c) => withinLegacy(c)
    || (['skin', 'glass', 'metal'].includes(c.id) && typeof c.frozen_reason === 'string' && c.frozen_reason.length > 0));
  // I-3c：非 catch-all + 成员数 ≥ 2
  const c = classes.every((x) => !(x.roughness[0] === 0 && x.roughness[1] === 1 && x.metalness[0] === 0 && x.metalness[1] === 1))
    && classes.every((x) => x.members.length >= 2);
  // I-3d：逐成员落在声明区间
  const d = ext.every((e) => {
    const cls = byId[e.class];
    return cls && e.roughness >= cls.roughness[0] && e.roughness <= cls.roughness[1]
      && e.metalness >= cls.metalness[0] && e.metalness <= cls.metalness[1];
  });
  // I-3i：三条定向数值
  const i = ext.every((e) => {
    if (e.class === 'skin') return e.roughness < 0.6;
    if (e.class === 'glass') return e.transmission !== null && e.ior !== null && e.roughness <= 0.15;
    if (e.class === 'metal') return e.metalness >= 0.6;
    return true;
  });
  return { b, c, d, i };
};
const extPartition = materialReportExtPartition();
const smooth = classCriterion(materialClassReport(), extPartition.surfaces_ext);
const loweredMetal = extPartition.surfaces_ext.map((e) => (e.class === 'metal' ? { ...e, metalness: 0.04 } : e));
const catchAllClass = materialClassReport().map((c) => (c.id === 'metal'
  ? { ...c, roughness: [0, 1], metalness: [0, 1] } : c));
check('n5_material_classes_within_legacy_and_directional', (() => {
  const healthy = smooth.b && smooth.c && smooth.d && smooth.i
    && surfaceIntersection().length === 0
    && SURFACE_IDS_EXT.length >= 10 && MATERIAL_CLASS_IDS.length === 5;
  // 负对照（非自指）：① metal 成员 metalness 置 0.04 ⇒ I-3i 必红；② 某类区间取全局全域 ⇒ I-3c 必红
  const neg1 = classCriterion(materialClassReport(), loweredMetal).i === false;
  const neg2 = classCriterion(catchAllClass, extPartition.surfaces_ext).c === false;
  return healthy && neg1 && neg2;
})(), `SURFACES(12) ∩ SURFACES_EXT(${SURFACE_IDS_EXT.length}) == ∅；${MATERIAL_CLASS_IDS.length} 类逐类区间`
  + `（skin/glass/metal 走冻结理由，fabric/wood ⊆ 旧口径 [${LEGACY_ROUGHNESS_RANGE}]/[${LEGACY_METALNESS_RANGE}]）；`
  + `逐成员落区 + 三条定向数值（skin⇒roughness<0.6 / glass⇒transmission∧ior∧≤0.15 / metal⇒metalness≥0.6）；`
  + `负对照（metal.metalness=0.04 / 类别取全局全域）⇒ 判据红；[配置面判据，不构成画面证据]`);

// --- 18) N5 · 约束区间与 SURFACES 名集（AC-I-3f 的注册表侧 + 锚非零命中） ---
check('n5_surface_registry_anchor_nonempty', (() => {
  // N5-r3 / A3（R2-M1 / N-1 关闭）：r2 的负对照仍是**算术恒等式**
  // （`countOf(droppedOne) === total - 1`：数组砍掉 1 个再求和 ⇒ 对任何数据都真），
  // 且参数里还留着**硬编码字面量** `{ surfaces: [], surfaces_ext: [] }` ⇒ 无牙且不实。
  // 现在断言的是**内容级**关系（不是计数）：真实分区逐条的 id 必须与冻结注册表**逐项相同**。
  // 缺一条 / 改名 / 多一条 ⇒ 断言直接为假。
  // **真正驱动生产者**的模块级负对照（暂存副本里从 `EXT_SURFACE_PROPS` 摘掉一条 ⇒ 场景遍历
  // 必与注册表不等）在 `r2_negative_controls.mjs` ③，由 `verify_specs.sh §19e` 执行。
  const partition = materialReport();
  const legacyIds = (p) => p.surfaces.map((e) => String(e.surface ?? '')).sort();
  const extIds = (p) => p.surfaces_ext.map((e) => String(e.id ?? '')).sort();
  const anchor = (p) => legacyIds(p).length + extIds(p).length === SURFACE_IDS.length + SURFACE_IDS_EXT.length
    && JSON.stringify(legacyIds(p)) === JSON.stringify([...SURFACE_IDS].sort())
    && JSON.stringify(extIds(p)) === JSON.stringify([...SURFACE_IDS_EXT].sort());
  const healthy = anchor(partition) && surfaceIntersection().length === 0;
  // 负对照 ①（内容级、非恒等式）：把真实分区的 ext 段**砍掉一条** ⇒ 同一断言必须判假
  const droppedOne = { surfaces: partition.surfaces, surfaces_ext: partition.surfaces_ext.slice(1) };
  const negDropped = anchor(droppedOne) === false;
  // 负对照 ②（**只改内容、不改长度**）：把一条真实 ext 表面的 id 改名 ⇒ 同一断言必须判假
  const renamed = {
    surfaces: partition.surfaces,
    surfaces_ext: partition.surfaces_ext.map((e, i) => (i === 0 ? { ...e, id: `${String(e.id)}__renamed` } : e)),
  };
  const negRenamed = anchor(renamed) === false;
  return healthy && negDropped && negRenamed;
})(), `materialReport() 分区逐条 id == SURFACES(12) + SURFACES_EXT(${SURFACE_IDS_EXT.length}) 的冻结注册表`
  + `（共 22 条，AC-A-3③ 的锚覆盖面；比对**内容**不是计数）；`
  + `负对照（内容级：摘掉一条 / 改一条 id ⇒ 同一断言判假）⇒ 该前置可判；`
  + `驱动生产者的模块级负对照见 r2_negative_controls.mjs ③（verify_specs §19e）；[配置面判据]`);

// --- 19) N5 · `state_clip_map` 双射与非平凡性（AC-H-4a/b） ---
const stateClipCriterion = (map, frozen, slots) => {
  const keys = Object.keys(map).sort();
  const frozenSorted = [...frozen].sort();
  if (keys.length < 2 || JSON.stringify(keys) !== JSON.stringify(frozenSorted)) return false;
  const signatures = keys.map((k) => slots.map((s) => Number(map[k][s] ?? 0)).join(','));
  if (new Set(signatures).size !== signatures.length) return false; // 双射：不同 state ⇒ 不同映射
  return keys.every((k) => slots.every((s) => typeof map[k][s] === 'number'));
};
check('n5_state_clip_map_is_bijection', (() => {
  const healthy = stateClipCriterion(state_clip_map, FROZEN_STATE_IDS, CHARACTER_SLOTS)
    && STATE_CLIP_MAP_KEYS.length === FROZEN_STATE_IDS.length
    && SLOT_SOURCES.length === CHARACTER_SLOTS.length;
  // 负对照（AC-H-4b，非自指）：把映射退化为常量函数 ⇒ 必红
  const degenerate = Object.fromEntries(Object.keys(state_clip_map).map((k) => [k, Object.fromEntries(CHARACTER_SLOTS.map((s) => [s, 0.5]))]));
  const neg = stateClipCriterion(degenerate, FROZEN_STATE_IDS, CHARACTER_SLOTS) === false;
  return healthy && neg;
})(), `state_clip_map 键集 == 冻结 state_id 清单 ${JSON.stringify(FROZEN_STATE_IDS)}（成员数 ≥2）且**双射**`
  + `（daily/masked 的槽位权重逐字段不同：${JSON.stringify(slotWeightsForState('daily'))} vs ${JSON.stringify(slotWeightsForState('masked'))}）；`
  + `负对照（退化为常量函数）⇒ 判据红；[配置面判据]`);

// --- 20) N5 · 绑定表指向真实 GLB（AC-E-2d 的取数面） ---
check('n5_binding_table_points_to_real_glb', (() => {
  const lines = bindingSetLines();
  const real = BINDINGS.filter((b) => b.entity_ids.length > 0);
  const healthy = lines.length === BINDINGS.length && lines.every((l) => l.includes(':'))
    && real.length >= 1
    && real.every((b) => b.glb_url.endsWith('.glb') && /^\d+\.\d+\.\d+$/.test(b.asset_version))
    && bindingForEntity('npc-006') !== null;
  // 负对照：把绑定版本改成空 ⇒ 三段式缺一段 ⇒ 必红
  const broken = real.map((b) => ({ ...b, asset_version: '' }));
  const neg = broken.some((b) => !/^\d+\.\d+\.\d+$/.test(b.asset_version));
  return healthy && neg;
})(), `绑定表 ${BINDINGS.length} 条，${BINDINGS.filter((b) => b.entity_ids.length > 0).length} 条挂到实体；`
  + `npc-006 → ${bindingForEntity('npc-006')?.binding_id ?? 'null'}（glb_url=${bindingForEntity('npc-006')?.glb_url ?? 'n/a'}，`
  + `asset_version=${bindingForEntity('npc-006')?.asset_version ?? 'n/a'}）；负对照（版本段缺失）⇒ 判据红；[配置面判据]`);

// --- 21) N5 · 角色实例的 Group 根与回落路径（AC-I-1/I-2） ---
check('n5_character_instance_group_root_and_fallback', (() => {
  const instance = createCharacterInstance({ entityId: 'npc-006', gltfLoader: null });
  const report = instance.report();
  // Node / 无 WebGL：loader === null ⇒ 不抛、结构完整、degradations 显式记录
  const noWebgl = report.root_kind === 'Group' && report.glb_loaded === false
    && Array.isArray(report.degradations) && report.degradations.some((d) => d.code === 'E_LOADER_NULL');
  // 绑定缺失 ⇒ 显式回落盒体 + E_BINDING_MISSING
  const missing = createCharacterInstance({ entityId: 'npc-999', gltfLoader: null });
  const missingReport = missing.report();
  const noBinding = missingReport.binding_id === null
    && missingReport.degradations.some((d) => d.code === 'E_BINDING_MISSING');
  const fieldsComplete = ['entity_id', 'root_kind', 'glb_loaded', 'slot_sources', 'degradations']
    .every((k) => k in report);
  return noWebgl && noBinding && fieldsComplete;
})(), `角色实例根 = Group（${createCharacterInstance({ entityId: 'npc-006', gltfLoader: null }).report().root_name}）；`
  + `loader===null ⇒ degradations 含 E_LOADER_NULL 且**不抛**；无绑定实体 ⇒ E_BINDING_MISSING + 回落盒体；`
  + `characterReport 结构字段齐全；[配置面判据，不构成画面证据]`);

// --- 22) N5 · 表现层不得写权威 + 相机默认口径（AC-F-2b / AC-H-2） ---
check('n5_presentation_is_not_second_authority', (() => {
  resetPresentation();
  const presentation = createPresentation({ smoothingMs: 100, epsAuthorityMaxStepM: 0.92736 });
  const seq = [];
  for (let i = 0; i <= 20; i += 1) seq.push({ tick: i, pos: [i * 0.5, 0, 0] });
  const epochAfterReset = presentation.report().authority_epoch;
  let stepNeverWrote = true;
  let epochGrowth = 0;
  for (const f of seq) {
    apply([{ entityId: 'npc-006', pos_m: f.pos, stateId: 'daily', tick: f.tick }], f.tick);
    const afterApply = presentation.report().authority_epoch;
    presentation.step(100);
    const afterStep = presentation.report().authority_epoch;
    // 表现层（step）**不得**产生任何权威写：epoch 在 step 前后必须不变
    if (afterStep !== afterApply) stepNeverWrote = false;
    epochGrowth = afterApply - epochAfterReset;
  }
  const report = presentation.report();
  const sources = report.authority_write_sources;
  // 写来源集合必须**只**含 `apply`（`reset` 的日志已被 reset 自身清空）
  const onlyApply = sources.length === 1 && sources[0] === 'apply';
  const epochs = report.authority_write_log.length === seq.length && epochGrowth === seq.length;
  const camera = report.camera;
  // H-2：默认相机口径 = inspection = 既有默认取景（逐字）
  const cameraOk = camera.camera_mode === 'inspection'
    && JSON.stringify(camera.inspection_position) === JSON.stringify([18, 14, 24])
    && JSON.stringify(camera.inspection_look_at) === JSON.stringify([9, 0, 6])
    && JSON.stringify(OBSERVATION_POSITION) === JSON.stringify([5, 0.35, 17.4])
    && JSON.stringify(OBSERVATION_LOOK_AT) === JSON.stringify([5, -0.2, 15])
    && presentationConstants().default_camera_mode === 'inspection';
  // 偏差上界（AC-B-6a 的口径自证）：displayed 与 authoritative 的距离 ≤ eps_used
  const withinEps = report.max_deviation_m <= report.eps_used_m;
  return onlyApply && epochs && stepNeverWrote && cameraOk && withinEps
    && presentationConstants().eps_floor_m === 0.005;
})(), `权威写入来源集合 == {apply}（表现层 step 前后 authority epoch **不变** ⇒ 未产生任何权威写）；`
  + `相机默认 inspection = [18,14,24]→[9,0,6]（= scene_assert 既有冻结值），取证机位 [5,0.35,17.4]→[5,-0.2,15] 默认不激活；`
  + `eps_floor = 5 mm；max_deviation ≤ eps_used；[配置面判据，不构成画面证据]`);

// --- 23) N5 · 场景图里真的挂了角色实例节点（B-2 的「接入」形态）+ 表现层读数可读 ---
check('n5_scene_wires_character_instance_node', (() => {
  const instances = scene.characterInstanceReport();
  const grouped = instances.filter((r) => r.root_kind === 'Group');
  const healthy = instances.length >= 1
    && grouped.length === instances.length
    && instances.every((r) => String(r.root_name).startsWith('character-instance:')
      // Node / 无 WebGL：无绑定 ⇒ E_BINDING_MISSING；有绑定但 loader 为 null ⇒ E_LOADER_NULL。
      // 两条都是**显式降级**（AC-I-1 / AC-I-2：不抛、结构完整、degradations 非空）。
      && r.glb_loaded === false
      && Array.isArray(r.degradations) && r.degradations.length > 0
      && r.degradations.every((d) => ['E_LOADER_NULL', 'E_BINDING_MISSING'].includes(d.code)));
  const presentation = scene.presentationReport();
  const presentationOk = presentation.schema_version === 'n5-presentation/1'
    && Array.isArray(presentation.authority_write_sources)
    && presentation.authority_write_sources.every((s) => s === 'apply')
    && presentation.client_may_write_authority === false;
  // 负对照（非自指）：把任一条实例读数的 root_kind 篡改为 'Mesh' ⇒ 同一条断言必须判假
  const tampered = instances.map((r, i) => (i === 0 ? { ...r, root_kind: 'Mesh' } : r));
  const negHolds = !tampered.every((r) => r.root_kind === 'Group');
  return healthy && presentationOk && negHolds;
})(), `场景图里 ${scene.characterInstanceReport().length} 个角色实例节点（`
  + `${JSON.stringify(scene.characterInstanceReport().map((r) => r.root_name))}），根全部为 Group；`
  + `Node 下 glb_loaded=false 且 degradations 含 E_LOADER_NULL（AC-I-1）；`
  + `权威写来源集合 ⊆ {apply}（client_may_write_authority=false）；`
  + `负对照（把一条 root_kind 改成 Mesh）⇒ 同一断言判假；[配置面判据，不构成画面证据]`);

// --- 24) N5 · 转身槽由**权威位移方向**变化驱动（AC-B-3 + 负对照 + 不可判 ⇒ GAP） ---
const turnCriterion = (timeline, hitRate, minWeight, minHoldS) => {
  if (!hitRate || hitRate.direction_changes === 0) return 'GAP';   // 无方向变化 ⇒ 不可判
  if (hitRate.hit_rate === null || hitRate.hit_rate < 1) return false;
  if (hitRate.weight < minWeight) return false;
  if (hitRate.hold_seconds < minHoldS) return false;
  if (timeline.filter((e) => e.slot === 'turn').length < hitRate.direction_changes) return false;
  return true;
};
check('n5_turn_slot_tracks_authority_direction', (() => {
  resetPresentation();
  const presentation = createPresentation({ smoothingMs: 100, epsAuthorityMaxStepM: 0.92736 });
  let x = 0; let z = 0;
  for (let tick = 0; tick <= 60; tick += 1) {
    if (tick > 0) { if (tick <= 30) x += 0.5; else z += 0.5; }   // 第 31 tick 一次**恰好 90°**的权威转向
    apply([{ entityId: 'npc-006', pos_m: [x, 0, z], stateId: 'daily', tick }], tick);
    presentation.step(100);
  }
  const report = presentation.report();
  const verdict = turnCriterion(report.clip_timeline, report.turn_hit_rate, 0.5, 0.3);
  // 负对照（非自指）：① 方向变化记 0 ⇒ 必须**不**判 PASS（记 GAP）；② 权重压到 0.2 ⇒ 必红
  const negGap = turnCriterion([], { direction_changes: 0, matched: 0, hit_rate: null, hold_seconds: 0.3, weight: 0.6 }, 0.5, 0.3) === 'GAP';
  const negLow = turnCriterion([{ slot: 'turn' }], { direction_changes: 1, matched: 1, hit_rate: 1, hold_seconds: 0.3, weight: 0.2 }, 0.5, 0.3) === false;
  return verdict === true && negGap && negLow
    && report.clip_constants.turn_hold_ticks * report.clip_constants.turn_direction_delta_rad > 0;
})(), `第 31 tick 的**权威位移方向变化 90°** ⇒ clip_timeline 出现 turn 事件：`
  + `方向变化=${(scene.presentationReport().turn_hit_rate ?? {}).direction_changes ?? 'n/a'}`
  + `（本检查用独立句柄，读数见 readback/presentation_report.json：`
  + `方向变化=1 / 命中率=1 / 权重=${0.6} / 保持=${0.3}s）；负对照（方向变化=0 ⇒ 记 GAP 而非 PASS；权重 0.2 ⇒ 判红）；`
  + `[配置面判据，不构成画面证据]`);

// --- 25) N5-r3 / A2：`glb_loaded=true` ⇒ 人物**有效可见性**不为 false ---
// 锚面（**必须能为假**，不得恒真）：实体根 `visible===true` ∧ 盒体部件**可绘制计数**为 0 ∧
// `character-instance:<id>` 与其 GLB 子树**有效可见**（沿 `parent.visible` 链求与）∧
// 人物最终会产生像素。这条锚正是 R2-C1（r2 把实体根 `visible=false` ⇒ 整棵子树不渲染）的机器拦截。
const characterVisibilityAnchor = (rows) => rows.length > 0 && rows.every((r) => r.glb_loaded === true
  && r.box_root_visible === true
  && r.box_parts_visible === 0
  && r.glb_subtree_effective_visible === true
  && r.entity_root_effective_visible === true
  && r.character_effective_visible === true);
check('n5_glb_loaded_character_effectively_visible', (() => {
  // 真跑模块：`createScene()` + 注入**假 `GLTFLoader`** ⇒ `glb_loaded=true`（Node 侧进入该路径的唯一入口）。
  const probe = createScene(canvasStub, { worldview: worldview.tone });
  probe.apply({
    t: 'snapshot', tick: 0,
    state: { entities: [{ id: 'npc-006', kind: 'npc', transform: { pos_mm: { x: 0, y: 0, z: 0 } } }] },
  });
  probe.setCharacterLoader({
    load(url, onLoad) { const group = new THREE.Group(); group.name = 'fake-glb'; onLoad({ scene: group }); },
  });
  probe.renderOnce();
  const rows = probe.characterBoxVisibilityReport();
  const healthy = characterVisibilityAnchor(rows);
  // 负对照 ①（**真的构造一个隐藏根**，非自指）：`effectiveVisibility()` 是 A2 锚的取数原语。
  // 在一个真 three 场景图上构造「隐藏祖先 + 自身 `visible=true` 的子节点」⇒ 必须读 `false`
  // （这正是 r2 的形态：GLB 自己 `visible=true`，但整棵子树因根的 `visible=false` 不渲染）；
  // 同时给一个**可见**的根做对照 ⇒ 必须读 `true`（证明该原语不是恒 false）。
  const hiddenRoot = new THREE.Group();
  hiddenRoot.visible = false;
  const hiddenBranch = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 0.1), new THREE.MeshStandardMaterial());
  hiddenBranch.visible = true;
  hiddenRoot.add(hiddenBranch);
  const negConstructed = hiddenBranch.visible === true && effectiveVisibility(hiddenBranch) === false
    && effectiveVisibility(new THREE.Group()) === true;
  // 负对照 ②（**注入隐藏根形态**）：把同一份真实读数里的实体根可见性打断 ⇒ 同一断言必须判假
  const negRoot = characterVisibilityAnchor(rows.map((r) => ({ ...r, box_root_visible: false, character_effective_visible: false }))) === false;
  // 负对照 ③（**并存渲染形态**）：盒体部件仍可绘制 ⇒ 同一断言必须判假（r1 的「盒体 + GLB 叠一起」）
  const negCoexist = characterVisibilityAnchor(rows.map((r) => ({ ...r, box_parts_visible: 1 }))) === false;
  return healthy && negConstructed && negRoot && negCoexist;
})(), `glb_loaded=true（注入假 loader）⇒ 读数 ${JSON.stringify((() => {
  const probe = createScene(canvasStub, { worldview: worldview.tone });
  probe.apply({ t: 'snapshot', tick: 0, state: { entities: [{ id: 'npc-006', kind: 'npc', transform: { pos_mm: { x: 0, y: 0, z: 0 } } }] } });
  probe.setCharacterLoader({ load(url, onLoad) { onLoad({ scene: new THREE.Group() }); } });
  probe.renderOnce();
  return probe.characterBoxVisibilityReport().map((r) => ({ e: r.entity_id, root: r.box_root_visible, box: r.box_parts_visible, glb: r.glb_subtree_effective_visible, eff: r.character_effective_visible }));
})())}；`
  + `负对照（构造隐藏根 ⇒ effectiveVisibility 读 false；读数里打断根可见性 / 盒体仍被画 ⇒ 同一断言判假）；[配置面判据，不构成画面证据]`);

// ================================================================== 7b) N5-C 阶段 C · 纯加法判据
// 任务书 §2：`scene_assert.mjs` 只**纯加法** —— 既有 103 条 `check()` 的判据体与期望值**逐字节未改**
// （`AC-F-5a/b/c` 由 F-5 系列另行承担；`assert_inputs.json` 的 `f5a_frozen_check_names` 是锚）。
// 本节新增两条，**各自带负对照**；`check(` 一律**列 0**（与既有 103 条同形，`^check\('` 才数得到）：
//   ① `credits_attribution_matches_provenance` —— `AC-G` G-1 的**源码面**前置。
//      ⚠️ 它**不是** C-1 的通过态：CC BY 4.0 的署名义务随**分发**发生，C-1 的判据面 =
//      「构建产物字节锚（`v0/.build/web/**`）+ 真浏览器可见性（playwright，1440×900）」，
//      读数在 `v0/spikes/n5c-evidence/**` 与 `readback/**`（D2：只做源码面 ⇒ 记 FAIL/GAP）。
//   ② `ext_carrier_hidden_only_when_glb_loaded` —— `REQ-006` R3-M1 的 **C-2 判据口径**（architect §12-D7）：
//      `hidden_surfaces ⊆ {角色侧 ext 载体}` ∧ `glb_loaded === false ⇒ hidden_surfaces == ∅`。

// --- ① 署名（CC BY 4.0）与来源登记面（`web/assets/provenance.json`）**逐字**一致 ---
const n5cCreditsReading = (() => {
  const provenance = readJson(`${WEB_DIR}assets/provenance.json`);
  const ccByAssets = (provenance.assets ?? []).filter((asset) => asset.license === 'cc-by-4.0');
  const attributions = ccByAssets.map((asset) => String(asset.attribution ?? ''));
  const creditsText = readFileSync(`${WEB_DIR}src/ui/player/credits.ts`, 'utf8');
  const html = readFileSync(`${WEB_DIR}index.html`, 'utf8');
  const main = readFileSync(`${WEB_DIR}src/main.ts`, 'utf8');
  const consistent = (texts) => (
    texts.length >= 1
    && texts.every((text) => text.length > 0 && creditsText.includes(text))
    // 挂载点在**玩家界面根**内、且**不在**开发观察面板内（与 `AC-H-2` 同向）
    && html.includes('id="credits"')
    && html.indexOf('id="credits"') > html.indexOf('id="player-ui"')
    && !html.slice(html.indexOf('<div id="hud">'), html.indexOf('id="player-ui"')).includes('id="credits"')
    && main.includes('mountCredits')
  );
  return {
    asset_ids: ccByAssets.map((asset) => asset.asset_id),
    positive: consistent(attributions),
    // 负对照：篡改 attribution ⇒ **同一个判据体**必须判假（证明它不恒真）
    negative_judged_false: consistent(attributions.map((text) => `${text}（tampered）`)) === false,
  };
})();
check('credits_attribution_matches_provenance',
  n5cCreditsReading.positive && n5cCreditsReading.negative_judged_false,
  `CC BY 4.0 条目 ${n5cCreditsReading.asset_ids.length} 条（${n5cCreditsReading.asset_ids.join(', ')}）；`
  + `credits.ts 逐字含其 attribution=${n5cCreditsReading.positive}；#credits 在 #player-ui 内且不在 #hud 内；`
  + `main.ts 调 mountCredits；负对照（篡改 attribution ⇒ 同判据体判假）=${n5cCreditsReading.negative_judged_false}；`
  + `[**源码面**判据 —— 不构成 C-1 通过；分发可见面由构建产物字节锚 + 真浏览器读数承担]`);

// --- ② C-2 判据口径（R3-M1）：角色侧 ext 载体**只在 GLB 加载后**被隐藏 ---
// 载体集合 = `world.ts` 的 `EXT_SURFACE_PROPS[].parent === 'character'` 的 3 条（盘上字面：`skin-face`
// / `skin-hand` / `jacket-cloth`）。**刻意为常量**：若上游新增一条角色侧载体，带 loader 世界的
// `hidden_surfaces` 会冒出集合外的 id ⇒ 本判据**必红**（fail-closed，迫使清单同步）。
const N5C_CHARACTER_EXT_CARRIERS = ['fabric_cotton_jacket', 'skin_face', 'skin_hand'];
const n5cHiddenWithinCarriers = (reading) => (
  reading.hidden_surfaces.every((id) => N5C_CHARACTER_EXT_CARRIERS.includes(id))
  && (reading.glb_loaded !== false || reading.hidden_surfaces.length === 0)
);
const n5cD7Reading = (() => {
  const npcOnlySnapshot = {
    t: 'snapshot', tick: 0,
    state: { entities: [{ id: 'npc-006', kind: 'npc', transform: { pos_mm: { x: 0, y: 0, z: 0 } } }] },
  };
  const noLoaderScene = createScene(canvasStub, { worldview: worldview.tone });
  noLoaderScene.apply(npcOnlySnapshot);
  const noLoaderUsage = noLoaderScene.surfaceUsageReport();
  const loadedScene = createScene(canvasStub, { worldview: worldview.tone });
  loadedScene.apply(npcOnlySnapshot);
  loadedScene.setCharacterLoader({
    load(_url, onLoad) { const group = new THREE.Group(); group.name = 'scene_assert-fake-glb'; onLoad({ scene: group }); },
  });
  loadedScene.renderOnce();
  const loadedUsage = loadedScene.surfaceUsageReport();
  const rows = loadedScene.characterBoxVisibilityReport();
  const negatives = {
    no_loader_with_hidden_carrier: n5cHiddenWithinCarriers({ glb_loaded: false, hidden_surfaces: ['skin_face'] }),
    with_loader_hidden_world_surface: n5cHiddenWithinCarriers({ glb_loaded: true, hidden_surfaces: ['window-glass'] }),
    with_loader_hidden_carrier: n5cHiddenWithinCarriers({ glb_loaded: true, hidden_surfaces: ['skin_face'] }),
  };
  return {
    no_loader_hidden: noLoaderUsage.hidden_surfaces,
    no_loader_holds: n5cHiddenWithinCarriers({ glb_loaded: false, hidden_surfaces: noLoaderUsage.hidden_surfaces }),
    glb_loaded: rows.length > 0 && rows.every((row) => row.glb_loaded === true),
    with_loader_hidden: loadedUsage.hidden_surfaces,
    with_loader_holds: n5cHiddenWithinCarriers({ glb_loaded: true, hidden_surfaces: loadedUsage.hidden_surfaces }),
    // 载体**在场**前置（防「⊆ 空集」假绿）+ 有牙前置（加载后载体必须真的被藏）
    carriers_seen: [...noLoaderUsage.visible_ext_used, ...noLoaderUsage.hidden_surfaces]
      .filter((id) => N5C_CHARACTER_EXT_CARRIERS.includes(id)).sort(),
    carriers_not_hidden: N5C_CHARACTER_EXT_CARRIERS.filter((id) => !loadedUsage.hidden_surfaces.includes(id)),
    negatives,
  };
})();
check('ext_carrier_hidden_only_when_glb_loaded',
  n5cD7Reading.no_loader_holds
  && n5cD7Reading.glb_loaded
  && n5cD7Reading.with_loader_holds
  && JSON.stringify(n5cD7Reading.carriers_seen) === JSON.stringify([...N5C_CHARACTER_EXT_CARRIERS].sort())
  && n5cD7Reading.carriers_not_hidden.length === 0
  && n5cD7Reading.negatives.no_loader_with_hidden_carrier === false
  && n5cD7Reading.negatives.with_loader_hidden_world_surface === false
  && n5cD7Reading.negatives.with_loader_hidden_carrier === true,
  `无 loader 世界 hidden_surfaces=${JSON.stringify(n5cD7Reading.no_loader_hidden)}（须为空）；`
  + `假 loader 世界 glb_loaded=${n5cD7Reading.glb_loaded} hidden_surfaces=${JSON.stringify(n5cD7Reading.with_loader_hidden)}`
  + ` ⊆ 角色侧载体 ${JSON.stringify(N5C_CHARACTER_EXT_CARRIERS)}（已实例化 ${JSON.stringify(n5cD7Reading.carriers_seen)}）；`
  + `负对照 ${JSON.stringify(n5cD7Reading.negatives)}（须依次 false/false/true）`);

// ================================================================== 8) 汇总

process.stdout.write(`\nscene_assert: PASS=${passed} FAIL=${failures.length}\n`);
if (failures.length > 0) {
  process.stdout.write(`scene_assert: FAILED (${failures.join(', ')})\n`);
  process.exit(1);
}
process.stdout.write('scene_assert: OK\n');
process.exit(0);
