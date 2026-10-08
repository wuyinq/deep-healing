#!/usr/bin/env node
/**
 * 材质类别 / `SURFACES_EXT` 机读锚（N5 / `AC-I-3b/c/d/e/f/g/h/i`、`AC-A-3③`）。
 *
 * 运行：`cd <web> && node <ws>/v0/spikes/n5-asset/material_probe.mjs [--out <dir>]`
 * 输出：`<out>/material_report.json`（本探针**只读**交付源码，产物写独立输出目录 —— R5）。
 *
 * 判据面（本探针只**取数**，判定由 S/R 按冻结口径做；负对照由 `tools/material_class_check.py` 提供）：
 *   - `surfaces`（既有 12 条，逐字段原样）· `surfaces_ext`（N5 新表面 10 条）· `classes`（5 类）
 *   - `intersection`（`I-3f`：必须为空）
 *   - `scene_used_surfaces`（`I-3g`：场景实际使用面 ⊆ 并集，且每面恰好归一个表）
 */

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  materialReport, SURFACES_EXT, SURFACE_IDS, SURFACE_IDS_EXT, SURFACES, surfaceIntersection,
} from '../../02_source/v0_skeleton/web/src/scene/materials.ts';
import {
  LEGACY_METALNESS_RANGE, LEGACY_ROUGHNESS_RANGE, MATERIAL_CLASSES, MATERIAL_CLASS_IDS,
  materialClassReport, notCatchAll,
} from '../../02_source/v0_skeleton/web/src/scene/material_classes.ts';
import { createScene } from '../../02_source/v0_skeleton/web/src/scene/world.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const outIdx = argv.indexOf('--out');
const OUT = resolve(outIdx >= 0 ? argv[outIdx + 1] : `${HERE}/readback`);

// ------------------------------------------------------------------ N5-r2 / A3：场景使用面 = **真实场景遍历**
// r1 的缺陷（Sentinel 指控 8 / raven §A5）：`SURFACE_IDS.filter((id) => Boolean(SURFACES[id]))` 恒真
// （`SURFACE_IDS = Object.keys(SURFACES)`）⇒ `scene_used_surfaces` 恒等于「注册表并集」，
// 场景**实际**用了什么**根本没被测**；`SURFACES_EXT` 的 10 条也从未被任何 mesh 实例化。
// 现在：经 `createScene()` 真装配一次世界，再从**场景图 mesh 的材质表**取集合。
const PACK_DIR = resolve(HERE, '../../02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin');
const worldview = JSON.parse(readFileSync(`${PACK_DIR}/worldview.json`, 'utf8'));
const canvasStub = {
  clientWidth: 1440, clientHeight: 900, width: 0, height: 0, style: {},
  getContext: () => null, addEventListener() {}, removeEventListener() {},
};
const usageScene = createScene(canvasStub, { worldview: worldview.tone });
usageScene.apply({
  t: 'snapshot',
  tick: 0,
  state: { entities: [{ id: 'npc-006', kind: 'npc', transform: { pos_mm: { x: 0, y: 0, z: 0 } } }] },
});
usageScene.setReading('surface');
const usage = usageScene.surfaceUsageReport();

// N5-r3 / R2-L1（**取数顺序订正**）：`materialReport()` 里的 ext 分区走 `extBindingOf(id)`，而绑定表由
// `mountExtSurfaceProps()` 在**装配时**填充 ⇒ 必须在 `createScene()` + `apply()` **之后**求值，
// 否则 `surfaces_ext[].bound` 恒 `null`（r2 的缺陷：看起来有读数、实际恒空）。
const report = materialReport();

const payload = {
  schema_version: 'n5-material-probe/3',
  generated_by: 'artisan',
  generated_at_epoch: Math.floor(Date.now() / 1000),
  web_dir: resolve(HERE, '../../02_source/v0_skeleton/web'),
  surfaces_legacy: report.surfaces,
  surfaces_ext: report.surfaces_ext,
  classes: report.classes,
  intersection: surfaceIntersection(),
  union_size: SURFACE_IDS.length + SURFACE_IDS_EXT.length,
  /** `I-3g` 的机读面：**场景遍历**得到的实际使用面（r1 的注册表 filter 已删除）。 */
  scene_used_surfaces: usage.scene_used_surfaces,
  scene_used_legacy: usage.legacy_used,
  scene_used_ext: usage.ext_used,
  /**
   * N5-r3 / A6（N-4 关闭）：**渲染面** —— 只统计「真的会被画」的表面（自身 `visible` ∧ 材质可见性
   * ∧ 祖先链可见）。r2 的 `surfaceUsageReport()` **不看 `visible`** ⇒ 整棵子树被藏时读数依旧全绿。
   */
  scene_visible_used_surfaces: usage.visible_used_surfaces,
  scene_visible_legacy: usage.visible_legacy_used,
  scene_visible_ext: usage.visible_ext_used,
  /** 场景里有、但**不可见**的表面（N-4 的盲区读数；本探针世界应为空）。 */
  scene_hidden_surfaces: usage.hidden_surfaces,
  /**
   * N5-r3 / A6：**legacy 侧下界**（探针世界是**合成 snapshot**：1 个 npc、无 zone/prop ⇒ 建筑部件
   * 不生成）⇒ 期望被实例化的只有**地面族** 4 条。r2 的 legacy 侧是单向 ⊆（4/12 也全绿）。
   */
  legacy_floor: ['ground_grass', 'ground_wet', 'pavement_brick', 'road_asphalt'],
  scene_unregistered: usage.unregistered,
  ext_expected_in_scene: usage.ext_expected,
  scene_probe: {
    method: 'createScene().surfaceUsageReport()（场景图 mesh 的 userData.surface 遍历）',
    world: '合成 snapshot（1 个 npc-006，无 zone/prop/portal；**内核未运行**）',
    npc_entities: 1,
    viewport: [1440, 900],
  },
  legacy_ranges: { roughness: LEGACY_ROUGHNESS_RANGE, metalness: LEGACY_METALNESS_RANGE },
  class_ids: MATERIAL_CLASS_IDS,
  ext_surface_count: SURFACE_IDS_EXT.length,
  bound_to: Object.fromEntries(SURFACE_IDS_EXT.map((id) => [id, SURFACES_EXT[id].bound_to])),
  classes_summary: materialClassReport().map((c) => ({
    id: c.id, members: c.members, member_count: c.member_count,
    roughness: c.roughness, metalness: c.metalness,
    containment: c.containment, within_legacy: c.within_legacy, not_catch_all: c.not_catch_all,
  })),
};

mkdirSync(OUT, { recursive: true });
const outPath = `${OUT}/material_report.json`;
writeFileSync(outPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
process.stdout.write(`material_probe: wrote ${outPath}\n`);
process.stdout.write(`material_probe: legacy=${SURFACE_IDS.length} ext=${SURFACE_IDS_EXT.length} classes=${MATERIAL_CLASS_IDS.length} intersection=${surfaceIntersection().length}\n`);
process.stdout.write(`material_probe: class catch-all check = ${MATERIAL_CLASS_IDS.map((id) => `${id}:${notCatchAll(id)}`).join(' ')}\n`);

// --- 非零命中前置（AC-A-3③ 注：锚集合为空 ⇒ 记 GAP，不得 PASS） ---
const anchorCount = report.surfaces.length + report.surfaces_ext.length;
if (anchorCount === 0) {
  process.stdout.write('material_probe: ANCHOR_EMPTY => GAP (not PASS)\n');
  process.exit(3);
}

// --- 结构性自检（本探针自身的一致性；判定仍由 S/R 做） ---
const problems = [];
if (surfaceIntersection().length !== 0) problems.push(`I-3f violated: intersection=${JSON.stringify(surfaceIntersection())}`);
for (const id of MATERIAL_CLASS_IDS) {
  const decl = MATERIAL_CLASSES[id];
  if (decl.members.length < 2) problems.push(`I-3c violated: class ${id} has ${decl.members.length} member(s)`);
  if (!notCatchAll(id)) problems.push(`I-3c violated: class ${id} is catch-all`);
}
const declaredMembers = MATERIAL_CLASS_IDS.flatMap((id) => [...MATERIAL_CLASSES[id].members]).sort();
const extIds = [...SURFACE_IDS_EXT].sort();
if (JSON.stringify(declaredMembers) !== JSON.stringify(extIds)) {
  problems.push(`class membership != SURFACES_EXT ids: ${JSON.stringify(declaredMembers)} vs ${JSON.stringify(extIds)}`);
}
// I-3d：逐成员实测值落在其类别声明区间内
for (const entry of report.surfaces_ext) {
  const cls = MATERIAL_CLASSES[entry.class];
  const r = Number(entry.roughness);
  const m = Number(entry.metalness);
  if (!(r >= cls.roughness[0] && r <= cls.roughness[1])) problems.push(`I-3d violated: ${entry.id} roughness ${r} ∉ [${cls.roughness}]`);
  if (!(m >= cls.metalness[0] && m <= cls.metalness[1])) problems.push(`I-3d violated: ${entry.id} metalness ${m} ∉ [${cls.metalness}]`);
}
// I-3g（N5-r3 / A6 加严）：改读**渲染面**（`visible_*`）—— 注册表里的每条 ext 表面**都必须真的
// 被画出来**（不只是「在场景图里」）。r2 用的是 `scene_used_*`（不看 `visible`）⇒ 整棵子树被藏时
// 依旧全绿（raven N-4 的盲区）。负对照 = 从场景里摘掉一条 ext 表面（`r2_negative_controls.mjs` ③）。
if (JSON.stringify(usage.visible_ext_used) !== JSON.stringify(usage.ext_expected)) {
  const missing = usage.ext_expected.filter((id) => !usage.visible_ext_used.includes(id));
  problems.push(`I-3g: 未**可见**实例化的 ext 表面：${JSON.stringify(missing)}`);
}
if (usage.hidden_surfaces.length > 0) problems.push(`I-3g: 场景里有表面被藏（不可见）：${JSON.stringify(usage.hidden_surfaces)}`);
// I-3g legacy 侧**下界**（N5-r3 / A6）：r2 的 legacy 侧是单向 ⊆ ⇒ 4/12 也全绿。本探针世界是
// 合成 snapshot（1 npc、无 zone/prop）⇒ 只有地面族 4 条会被实例化，它们**必须都在**。
const LEGACY_FLOOR = ['ground_grass', 'ground_wet', 'pavement_brick', 'road_asphalt'];
const floorMissing = LEGACY_FLOOR.filter((id) => !usage.visible_legacy_used.includes(id));
if (floorMissing.length > 0) problems.push(`I-3g: legacy 侧下界未满足（探针世界地面族缺失）：${JSON.stringify(floorMissing)}`);
if (usage.unregistered.length > 0) problems.push(`I-3g: 场景使用了未登记表面：${JSON.stringify(usage.unregistered)}`);
if (problems.length > 0) {
  process.stdout.write('material_probe: SELFCHECK_FAIL\n');
  for (const p of problems) process.stdout.write(`  - ${p}\n`);
  process.exit(1);
}
process.stdout.write('material_probe: SELFCHECK_OK\n');
process.exit(0);
