#!/usr/bin/env node
/**
 * N5-r2 的**模块本体**负对照（A3 / A4② / A4④ / A5）。
 *
 * r1 的负对照只作用于**纯函数**（把合成数据喂给一个纯谓词）⇒ 证明不了「模块本体真的有牙」。
 * 本脚本一律在 `/tmp` 副本上做**源码级注入**，再**真跑模块本体**，断言行为按预期翻转：
 *
 *   ① A4④  `character_instance.ts` 的 `new THREE.Group()` → `new THREE.Mesh()`
 *          ⇒ `report().root_kind` 必须**不再**是 `'Group'`（判据 `n5_character_instance_group_root_and_fallback` 会红）
 *   ② A4②  `presentation.ts` 的 `clipTimeline.push({` → `if (false) clipTimeline.push({`（删掉 turn 事件）
 *          ⇒ `turn_hit_rate.matched` 必须为 0 / `hit_rate` 为 0（判据红）
 *   ③ A3   `world.ts` 的 `EXT_SURFACE_PROPS` 摘掉一条 ext 表面（`window-glass`）
 *          ⇒ 场景遍历的 `ext_used` 必须**不等于** `ext_expected`（`material_probe` 的 I-3g 检查会红）
 *   ④ A5   真模块 + 注入假 `GLTFLoader` ⇒ `glb_loaded=true` 时盒体部件必须**全部隐藏**；
 *          loader=null ⇒ 盒体部件必须可见（回落路径保留）
 *
 * 只读交付源码；注入只在 `/tmp` 副本上做。退出码 0 = 全部按预期。
 */

import { cpSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import * as THREE from 'three';

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(HERE, '../../02_source/v0_skeleton/web');
const SRC = `${WEB}/src`;

const canvasStub = {
  clientWidth: 1440, clientHeight: 900, width: 0, height: 0, style: {},
  getContext: () => null, addEventListener() {}, removeEventListener() {},
};
const SNAPSHOT = {
  t: 'snapshot', tick: 0,
  state: { entities: [{ id: 'npc-006', kind: 'npc', transform: { pos_mm: { x: 0, y: 0, z: 0 } } }] },
};

const results = [];
function record(label, red, detail) {
  results.push({ label, red, detail });
  process.stdout.write(`  ${red ? 'RED(期望)' : 'GREEN(异常！)'}  ${label} — ${detail}\n`);
}

/**
 * `$TMPDIR` 副本 + 源码级注入（`needle` 找不到 ⇒ 直接抛，绝不静默跳过）。
 *
 * N5-r3 / R2-L3：暂存目录改到**系统临时目录**（r2 建在 `v0/spikes/n5-asset/` 这一证据面下，
 * 异常中断会留 `.stage-*` 残渣）。`three` 的解析要靠 worktree 根的 `node_modules`
 * ⇒ 在暂存目录里放一条 `node_modules` 符号链接，保持解析链。
 */
const stagedDirs = new Set();
process.on('exit', () => {
  for (const dir of stagedDirs) { try { rmSync(dir, { recursive: true, force: true }); } catch { /* 退出清理 */ } }
});

function stage(injections = []) {
  const tmp = mkdtempSync(join(tmpdir(), 'n5-negctl-'));
  stagedDirs.add(tmp);
  cpSync(SRC, `${tmp}/src`, { recursive: true });
  symlinkSync(resolve(HERE, '../../../node_modules'), `${tmp}/node_modules`, 'dir');
  for (const [rel, needle, replacement] of injections) {
    const path = `${tmp}/src/${rel}`;
    const text = readFileSync(path, 'utf8');
    if (!text.includes(needle)) throw new Error(`inject needle NOT FOUND in ${rel}: ${needle}`);
    writeFileSync(path, text.replace(needle, replacement), 'utf8');
  }
  return tmp;
}

/** 删掉暂存副本（交付/证据面不留残渣）。 */
function unstage(tmp) {
  stagedDirs.delete(tmp);
  rmSync(tmp, { recursive: true, force: true, maxRetries: 3 });
}

// ---------------------------------------------------------------- ① A4④：根换成 Mesh
{
  const tmp = stage([['scene/character_instance.ts', 'new THREE.Group()', 'new THREE.Mesh()']]);
  const mod = await import(`${tmp}/src/scene/character_instance.ts`);
  const report = mod.createCharacterInstance({ entityId: 'npc-006', gltfLoader: null }).report();
  record('A4④ 根换 Mesh ⇒ root_kind 不再是 Group', report.root_kind !== 'Group',
    `root_kind=${report.root_kind} derivation=${JSON.stringify(report.root_kind_derivation)}`);
  rmSync(tmp, { recursive: true, force: true });
}

// ---------------------------------------------------------------- ② A4②：删掉 turn 事件
{
  const tmp = stage([['scene/presentation.ts', 'clipTimeline.push({', 'if (false) clipTimeline.push({']]);
  const mod = await import(`${tmp}/src/scene/presentation.ts`);
  mod.resetPresentation();
  const presentation = mod.createPresentation({ smoothingMs: 100, epsAuthorityMaxStepM: 0.92736 });
  let x = 0; let z = 0;
  for (let tick = 0; tick <= 60; tick += 1) {
    if (tick > 0) { if (tick <= 30) x += 0.5; else z += 0.5; }
    mod.apply([{ entityId: 'npc-006', pos_m: [x, 0, z], stateId: 'daily', tick }], tick);
    presentation.step(100);
  }
  const hit = presentation.report().turn_hit_rate;
  record('A4② 删掉 turn 事件 ⇒ 命中率不再恒为 1', hit.direction_changes > 0 && hit.hit_rate !== 1,
    `direction_changes=${hit.direction_changes} matched=${hit.matched} hit_rate=${hit.hit_rate}`);
  rmSync(tmp, { recursive: true, force: true });
}

// ---------------------------------------------------------------- ③ A3：从场景摘掉一件 ext 表面
{
  const needle = "    { name: 'window-glass', surface: 'glass_window_clear', size: [0.04, 1.30, 1.60], position: [-2.40, 1.75, 0.40], parent: 'world' },\n";
  const tmp = stage([['scene/world.ts', needle, '']]);
  const mod = await import(`${tmp}/src/scene/world.ts`);
  const scene = mod.createScene(canvasStub, {
    worldview: JSON.parse(readFileSync(`${WEB}/../districts/xingfu-xiaoqu-xuqin/worldview.json`, 'utf8')).tone,
  });
  scene.apply(SNAPSHOT);
  const usage = scene.surfaceUsageReport();
  const red = JSON.stringify(usage.ext_used) !== JSON.stringify(usage.ext_expected);
  record('A3 摘掉一件 ext 表面 ⇒ 场景遍历必与注册表不等', red,
    `ext_used=${usage.ext_used.length}/${usage.ext_expected.length} missing=${JSON.stringify(usage.ext_expected.filter((id) => !usage.ext_used.includes(id)))}`);
  rmSync(tmp, { recursive: true, force: true });
}

// ---------------------------------------------------------------- ④ A1：GLB 已加载 ⇒ 盒体不渲染、人物仍有效可见
{
  const world = await import(`${SRC}/scene/world.ts`);
  const tone = JSON.parse(readFileSync(`${WEB}/../districts/xingfu-xiaoqu-xuqin/worldview.json`, 'utf8')).tone;

  // N5-r3 / A1+A2（PM §2 明文授权订正本条）：r2 的期望值 `box_root_visible === false` 是
  // **把回归写成期望**（实体根 `visible=false` ⇒ three 的 `projectObject()` 整棵子树 return ⇒
  // 真浏览器里人物整体消失）。订正后的期望：**实体根可见** ∧ **盒体部件可绘制计数 0** ∧
  // **GLB 子树有效可见** ∧ 人物最终会产生像素。
  const anchorHolds = (rows) => rows.length > 0 && rows.every((r) => r.glb_loaded === true
    && r.box_parts_visible === 0 && r.box_root_visible === true
    && r.glb_subtree_effective_visible === true && r.entity_root_effective_visible === true
    && r.character_effective_visible === true);

  const withLoader = world.createScene(canvasStub, { worldview: tone });
  withLoader.apply(SNAPSHOT);
  withLoader.setCharacterLoader({
    load(url, onLoad) { const g = new THREE.Group(); g.name = 'fake-glb'; onLoad({ scene: g }); },
  });
  withLoader.renderOnce();
  const loadedReport = withLoader.characterBoxVisibilityReport();
  record('A5/A1 glb_loaded=true ⇒ 盒体不渲染 ∧ 实体根可见 ∧ GLB 有效可见（不得并存渲染）', anchorHolds(loadedReport),
    JSON.stringify(loadedReport.map((r) => ({ e: r.entity_id, glb: r.glb_loaded, vis: r.box_parts_visible, total: r.box_parts_total, root: r.box_root_visible, drawn: r.box_root_drawn, glb_eff: r.glb_subtree_effective_visible, eff: r.character_effective_visible }))));

  const noLoader = world.createScene(canvasStub, { worldview: tone });
  noLoader.apply(SNAPSHOT);
  noLoader.renderOnce();
  const fallback = noLoader.characterBoxVisibilityReport();
  const fallbackOk = fallback.length > 0 && fallback.every((r) => r.glb_loaded === false
    && r.box_parts_visible > 0 && r.box_root_visible === true && r.character_effective_visible === true);
  record('A5/A1 glb_loaded=false ⇒ 盒体回落路径保留（部件可见、根可见）', fallbackOk,
    JSON.stringify(fallback.map((r) => ({ e: r.entity_id, glb: r.glb_loaded, vis: r.box_parts_visible, total: r.box_parts_total, eff: r.character_effective_visible }))));
}

// ---------------------------------------------------------------- ⑤ A1/A2 负对照：把 r2 的回归形态真注入 ⇒ 可见性锚必红
{
  // 真注入（暂存副本 + 源码级）：把实体根重新改成 `visible = !loaded`（= r2 的 R2-C1 形态），
  // 真跑模块 ⇒ `glb_subtree_effective_visible` / `character_effective_visible` 必须翻假、
  // 可见性锚必须判红。**这条证明锚有牙**（不是只读读数里被篡改的副本）。
  const needle = 'if (rootMaterial) rootMaterial.visible = !loaded;';
  const tmp = stage([['scene/world.ts', needle, 'rootMesh.visible = !loaded; // INJECTED(r2 regression)']]);
  const mod = await import(`${tmp}/src/scene/world.ts`);
  const tone = JSON.parse(readFileSync(`${WEB}/../districts/xingfu-xiaoqu-xuqin/worldview.json`, 'utf8')).tone;
  const scene = mod.createScene(canvasStub, { worldview: tone });
  scene.apply(SNAPSHOT);
  scene.setCharacterLoader({ load(url, onLoad) { onLoad({ scene: new THREE.Group() }); } });
  scene.renderOnce();
  const rows = scene.characterBoxVisibilityReport();
  const anchorHolds = (rs) => rs.length > 0 && rs.every((r) => r.glb_loaded === true
    && r.box_parts_visible === 0 && r.box_root_visible === true
    && r.glb_subtree_effective_visible === true && r.entity_root_effective_visible === true
    && r.character_effective_visible === true);
  record('A1/A2 负对照：注入 r2 形态（实体根 visible=false）⇒ 可见性锚必红', !anchorHolds(rows),
    JSON.stringify(rows.map((r) => ({ e: r.entity_id, root: r.box_root_visible, glb_eff: r.glb_subtree_effective_visible, eff: r.character_effective_visible }))));
  rmSync(tmp, { recursive: true, force: true });
}

const bad = results.filter((r) => !r.red);
process.stdout.write(`\nr2_negative_controls: cases=${results.length} as_expected=${results.length - bad.length} unexpected=${bad.length}\n`);
if (bad.length > 0) {
  process.stdout.write('r2_negative_controls: FAILED\n');
  process.exit(1);
}
process.stdout.write('r2_negative_controls: OK（全部按预期翻转）\n');
process.exit(0);
