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

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import * as THREE from 'three';
import { createScene, READING_GEOMETRY_PROFILE } from '../src/scene/world.ts';
import { deriveLighting, healingMaterial, kelvinToRgb, ROUGHNESS_MIN } from '../src/scene/lighting.ts';
import { appearanceTableFromDocuments } from '../src/scene/character.ts';

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

// ================================================================== 7) 汇总

process.stdout.write(`\nscene_assert: PASS=${passed} FAIL=${failures.length}\n`);
if (failures.length > 0) {
  process.stdout.write(`scene_assert: FAILED (${failures.join(', ')})\n`);
  process.exit(1);
}
process.stdout.write('scene_assert: OK\n');
process.exit(0);
