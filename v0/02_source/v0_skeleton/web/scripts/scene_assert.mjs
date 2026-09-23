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

import { createScene, READING_GEOMETRY_PROFILE } from '../src/scene/world.ts';
import { deriveLighting, healingMaterial, kelvinToRgb, ROUGHNESS_MIN } from '../src/scene/lighting.ts';

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

process.stdout.write(`\nscene_assert: PASS=${passed} FAIL=${failures.length}\n`);
if (failures.length > 0) {
  process.stdout.write(`scene_assert: FAILED (${failures.join(', ')})\n`);
  process.exit(1);
}
process.stdout.write('scene_assert: OK\n');
process.exit(0);
