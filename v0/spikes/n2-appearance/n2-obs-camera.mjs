#!/usr/bin/env node
/**
 * F-1 取证机位工具（N2-r2 / spike 专用；**非交付面**）。
 *
 * 职责（只读）：
 *   `--mode baseline` —— 抓**默认相机读数**（`cameraReport()`）+ 徐琴**部件 AABB**，落盘冻结基线。
 *                        必须在改 `world.ts` **之前**跑一次（起点读数），改完再跑一次逐项比对
 *                        ⇒ 证明「默认取景未被改」。
 *
 * 用法：
 *   node spikes/n2-appearance/n2-obs-camera.mjs --mode baseline --out spikes/n2-appearance/readback
 */
import { writeFileSync, mkdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const WS = fileURLToPath(new URL('../../', import.meta.url));
const WEB = `${WS}02_source/v0_skeleton/web/`;
const PACK = `${WS}02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin/`;

const { createScene, buildCharacterPartsForState } = await import(`${WEB}src/scene/world.ts`);
const { appearanceTableFromDocuments } = await import(`${WEB}src/scene/character.ts`);

const readJson = (path) => JSON.parse(readFileSync(path, 'utf8'));

const worldview = readJson(`${PACK}worldview.json`);
const seed = readJson(`${PACK}world.seed.json`);
const npc006 = readJson(`${PACK}npcs/npc-006.json`);

const args = process.argv.slice(2);
const argOf = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const MODE = argOf('--mode', 'baseline');
const OUT = argOf('--out', `${HERE}readback`);

/** 与 `scene_assert.mjs` 同一 canvas stub 口径（Node 无 WebGL ⇒ 空渲染器，装配照常）。 */
const canvasStub = { clientWidth: 1440, clientHeight: 900, width: 0, height: 0, style: {},
  getContext: () => null, addEventListener() {}, removeEventListener() {} };

const table = appearanceTableFromDocuments([{ npc_id: 'npc-006', appearance: npc006.appearance }]);
const state = { entities: seed.entities };
const scene = createScene(canvasStub, { worldview: worldview.tone, appearance: table });
scene.apply({ t: 'snapshot', tick: 0, state });
scene.setReading('surface');

/** 徐琴的**世界 AABB**（人物放置点 + 部件局部偏移 ± 半尺寸）—— 数据来自交付面自己的装配器。 */
function characterAabb(stateId) {
  const entity = state.entities.find((item) => item.id === 'npc-006');
  const parts = buildCharacterPartsForState({ entities: [entity] }, { appearance: table });
  const placement = [
    (entity.transform?.pos_mm?.x ?? 0) / 1000,
    (entity.transform?.pos_mm?.y ?? 0) / 1000,
    (entity.transform?.pos_mm?.z ?? 0) / 1000,
  ];
  const boxes = parts.map((part) => ({
    part: part.part,
    center: [placement[0] + part.local_offset[0], placement[1] + part.local_offset[1],
      placement[2] + part.local_offset[2]],
    size: part.size,
    source_hex: part.source_hex,
  }));
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const box of boxes) {
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], box.center[axis] - box.size[axis] / 2);
      max[axis] = Math.max(max[axis], box.center[axis] + box.size[axis] / 2);
    }
  }
  return { state_id: stateId, placement, boxes, min, max,
    center: [0, 1, 2].map((axis) => (min[axis] + max[axis]) / 2) };
}

const daily = characterAabb('daily');
const report = {
  mode: MODE,
  default_camera: scene.cameraReport(),
  daily_aabb: daily,
  state_id_reported: scene.appearanceReport().find((entry) => entry.entity_id === 'npc-006')?.state_id,
  parts: scene.characterReport().filter((part) => part.entity_id === 'npc-006')
    .map((part) => ({ part: part.part, source_hex: part.source_hex, material_hex: part.material_hex,
      size: part.size, local_offset: part.local_offset })),
};
mkdirSync(OUT, { recursive: true });
writeFileSync(`${OUT}/n2-obs-camera-${MODE}.json`, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
process.stdout.write(`${JSON.stringify(report)}\n`);
