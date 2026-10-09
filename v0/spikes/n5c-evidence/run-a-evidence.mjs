#!/usr/bin/env node
/**
 * N5 阶段 C · **A/B/D/I 类取证驱动**（真会话 + 真浏览器 1440×900 / 390×844）。
 *
 * 产出（全部**实机**；配置面读数一律注明）：
 *   - A-2a 七张图（含 `motion-sheet` 连续 8 帧）与 `narrow-390x844`，`<tag>` = 四段式（A-2b）；
 *   - A-8a 的**回落批次**（对照臂，供盲评混排用）；
 *   - AC-G G-1 的**真浏览器可见性**读数（credits AABB / display / 视口内）与 **D2 的构建产物字节锚**；
 *   - AC-I-5 窄屏 390×844 溢出读数；AC-I-4 WebGL 不可用 ⇒ 显式提示、不白屏；
 *   - AC-D 的原始逐帧读数（交给交付面 `spikes/n5-asset/perf_probe.mjs` 做统计）；
 *   - AC-B 的表现层读数（权威位移 → 显示位置/朝向/表现槽），喂给交付面 `presentation.ts`。
 *
 * 硬边界：**只读交付树**；产物落 `v0/spikes/n5c-evidence/readback/**` 与 `v0/spikes/n5-asset/shots/**`。
 */

import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKSPACE = resolve(HERE, '..', '..');
const SOURCE = join(WORKSPACE, '02_source');
const WEB = join(WORKSPACE, '.build', 'web');
const PACK = 'xingfu-xiaoqu-xuqin';
const READBACK = join(HERE, 'readback');
const SHOTS_READBACK = join(READBACK, 'shots');
const SHOTS_FROZEN = join(WORKSPACE, 'spikes', 'n5-asset', 'shots');
const OUT = join(HERE, 'runtime', 'a-evidence', 'out');
const RUNTIME = join(HERE, 'runtime', 'a-evidence', 'bridge');
const PORT = Number(8846);
mkdirSync(SHOTS_READBACK, { recursive: true });
mkdirSync(SHOTS_FROZEN, { recursive: true });
mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
const sha256 = (text) => createHash('sha256').update(text, 'utf8').digest('hex');

const CHROMIUM = [
  process.env.PW_CHROMIUM,
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1234',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
  // N5-C r2 / FIX-8：r1 读数绑定的 `chromium-1234` 已不在盘上（raven R-M2）⇒ 显式回落并**记名**。
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1248',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean).find((candidate) => existsSync(candidate));

/** N5-C r2 / FIX-8 + FIX-11：读数**统一元数据**（时刻/样本数/工具链/node/浏览器二进制/树头）。 */
const TREE_HEAD = spawnSync('git', ['-C', WORKSPACE, 'rev-parse', 'HEAD']).stdout.toString().trim();
const META = {
  node_version: process.version, node_binary: process.execPath,
  toolchain: `node ${process.version} + playwright ${JSON.parse(readFileSync(join(WORKSPACE, '..', 'node_modules', 'playwright', 'package.json'), 'utf8')).version} + chromium ${CHROMIUM ?? 'playwright-default'}`,
  browser_binary: CHROMIUM ?? null, tree_head: TREE_HEAD,
};

// ── 四段式 tag（A-2b；判定者 S）
const provenance = JSON.parse(readFileSync(join(SOURCE, 'v0_skeleton', 'web', 'assets', 'provenance.json'), 'utf8'));
const assetBundle = sha256(provenance.assets
  .map((asset) => `${asset.asset_id}:${asset.converted_sha256}`).sort().join('\n'));
const bindingModule = await import(join(SOURCE, 'v0_skeleton', 'web', 'src', 'scene', 'asset_binding.ts'));
const bindingLines = bindingModule.bindingSetLines();
const bindingSet = sha256(bindingLines.slice().sort().join('\n'));
const commitShort = spawnSync('git', ['-C', WORKSPACE, 'rev-parse', '--short=7', 'HEAD']).stdout.toString().trim();
const commitFull = spawnSync('git', ['-C', WORKSPACE, 'rev-parse', 'HEAD']).stdout.toString().trim();
// `config_hash`：**配置面**导出（注明非像素证据）；键序字典序 + 数字 toFixed(6) + 数组保序
const canonical = (value) => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  if (typeof value === 'number') return value.toFixed(6);
  return JSON.stringify(value);
};

const host = spawn('node', [
  join(HERE, 'serve-live.mjs'), '--tag', 'a-evidence', '--port', String(PORT), '--pack', PACK,
  '--out', OUT, '--runtime', RUNTIME, '--web', WEB, '--source', SOURCE,
  '--tick-ms', '50', '--snapshot-every', '1', '--seed', '20260921',
  '--run-seconds', '420', '--start-paused', 'false',
  '--memory-chain', '--capability-chain', '--emotion-pressure-threshold', '0.0', '--stub-remote-api', '1.0',
], { stdio: ['ignore', 'pipe', 'pipe'] });
// ⚠️ **实测踩过**：中途抛异常时宿主不会被回收 ⇒ 端口 8846 被占 ⇒ 下次运行 `SERVE_READY timeout`。
// 因此在任何退出路径上都回收宿主（含未捕获异常 / SIGINT）。
const killHost = () => { try { host.kill('SIGKILL'); } catch { /* 已退出 */ } };
process.on('exit', killHost);
process.on('SIGINT', () => { killHost(); process.exit(130); });
process.on('uncaughtException', (error) => { killHost(); throw error; });
if (host.pid) writeFileSync(join(OUT, 'host-a-evidence.pid'), `${host.pid}\n`);
await new Promise((ready, reject) => {
  const timer = setTimeout(() => reject(new Error('SERVE_READY timeout')), 90000);
  host.stdout.on('data', (chunk) => {
    writeFileSync(join(OUT, 'host-a-evidence.log'), String(chunk), { flag: 'a' });
    if (String(chunk).includes('SERVE_READY')) { clearTimeout(timer); ready(); }
  });
});

const browser = await chromium.launch({
  headless: true, executablePath: CHROMIUM,
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const pageErrors = [];
page.on('console', (msg) => { if (msg.type() === 'error') pageErrors.push(msg.text()); });
page.on('pageerror', (error) => pageErrors.push(String(error)));

await page.goto(`http://127.0.0.1:${PORT}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 60000 });
await page.waitForTimeout(6000);   // 让世界跑起来（肖/徐琴走动 + 事件）
const creditsReport = await page.evaluate(() => globalThis.__deephealing.creditsReport());
const uiSets = await page.evaluate(() => globalThis.__deephealing.uiSets());
const viewportInfo = await page.evaluate(() => globalThis.__deephealing.viewport());
const cameraModes = await page.evaluate(() => ({
  camera: globalThis.__deephealing.scene.cameraReport?.() ?? null,
}));
const configExport = await page.evaluate(() => ({
  // ⚠️ **只用配置面读数**：`presentationReport()` 含逐 tick 的显示实体 ⇒ 逐次运行不同，
  // 不能进 `config_hash`（会让 A-2b 的 `<tag>` 不可复现）。实测踩过。
  postfx: globalThis.__deephealing.scene.postfxReport?.() ?? null,
  material: globalThis.__deephealing.scene.materialReport?.() ?? null,
  camera: globalThis.__deephealing.scene.cameraReport?.() ?? null,
}));
const configHash = sha256(canonical(configExport));
const TAG = `${commitShort}-${assetBundle.slice(0, 12)}-${bindingSet.slice(0, 8)}-${configHash.slice(0, 8)}`;

// ── A-2a 七张图（真浏览器，1440×900；机位用交付面 `setObservationCamera`，默认不激活）
const shots = [];
const shoot = async (name, options = {}) => {
  if (options.camera) {
    await page.evaluate((view) => globalThis.__deephealing.scene.setObservationCamera(view), options.camera);
    await page.waitForTimeout(600);
  }
  const file = join(SHOTS_READBACK, `${name}-${TAG}.png`);
  await page.screenshot({ path: file });
  copyFileSync(file, join(SHOTS_FROZEN, `${name}-${TAG}.png`));
  const reading = await page.evaluate(() => ({
    camera: globalThis.__deephealing.scene.cameraReport(),
    entities: globalThis.__deephealing.entityIds(),
    npc: (() => {
      const snap = globalThis.__deephealing.acSnapshot();
      return snap.npcs.map((npc) => ({ id: npc.id, transform: npc.transform }));
    })(),
  }));
  shots.push({ name, file, camera: reading.camera?.position ?? null, entities: reading.entities.length });
  return reading;
};

const INDOOR_WIDE = { position_m: [5, 0.35, 17.4], look_at_m: [5, -0.2, 15.0] };
const INDOOR_CLOSEUP = { position_m: [5, 0.58, 15.95], look_at_m: [5, 0.45, 15.05] };

// ================================================================ N5-C r2 / FIX-1
// **AC-A 取证集重拍 + 取景写死**：① 全身图（角色占画高 ≥ 1/3）；② 真面部特写（脸占画面 ≥ 15%）；
// ③ 交互镜头（显式调交付面 `enterInteractiveCamera()` 并把 `camera_mode == "interactive"` 写进读数）。
// 机位**由机读输入算出**（npc 世界位置 + 交付面 `characterReport()` 的部件表），并把
// **投影复算**（屏幕投影的占高/占面 + 像素裁剪框）与**裁剪复核**（浏览器按该框再截一张）一并落盘。
const VIEW_W = 1440;
const VIEW_H = 900;
const FOV_DEG = 45;
const FRAME_FULL_BODY_TARGET = 0.45;   // 目标：角色占画高 ~45%（判据下限 ≥ 1/3）
const FRAME_FACE_TARGET = 0.22;        // 目标：脸占画面面积 ~22%（判据下限 ≥ 15%）
const FOV_TAN = Math.tan((FOV_DEG * Math.PI / 180) / 2);

const sub3 = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross3 = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const unit3 = (a) => { const n = Math.hypot(a[0], a[1], a[2]); return [a[0] / n, a[1] / n, a[2] / n]; };

/** 世界点 → 屏幕像素（标准针孔投影；已用 sentinel 公布的 `637.2/-475.2`、`505.3/-1116.3` 复算校准）。 */
const projectPoint = (position, lookAt, world) => {
  const forward = unit3(sub3(lookAt, position));
  const right = unit3(cross3(forward, [0, 1, 0]));
  const up = cross3(right, forward);
  const d = sub3(world, position);
  const xv = dot3(d, right);
  const yv = dot3(d, up);
  const zv = dot3(d, forward);
  const aspect = VIEW_W / VIEW_H;
  const ndcX = xv / (zv * FOV_TAN * aspect);
  const ndcY = yv / (zv * FOV_TAN);
  return { px: ((ndcX + 1) / 2) * VIEW_W, py: ((1 - ndcY) / 2) * VIEW_H, depth_m: zv };
};

const partBounds = (parts, names) => {
  const picked = parts.filter((part) => names.includes(part.part));
  if (picked.length === 0) return null;
  const low = [Infinity, Infinity, Infinity];
  const high = [-Infinity, -Infinity, -Infinity];
  for (const part of picked) {
    for (let axis = 0; axis < 3; axis += 1) {
      const centre = Number(part.local_offset[axis]);
      const half = Number(part.size[axis]) / 2;
      low[axis] = Math.min(low[axis], centre - half);
      high[axis] = Math.max(high[axis], centre + half);
    }
  }
  return { low, high };
};

/** 交付面读数 → 取景输入（npc 世界位置 + 部件表；全部来自页面，不在本文件里编造）。 */
const readFramingInputs = (page) => page.evaluate(() => {
  const parts = globalThis.__deephealing.scene.characterReport()
    .filter((part) => part.entity_id === 'npc-006')
    .map((part) => ({ part: part.part, size: part.size, local_offset: part.local_offset }));
  const snapshot = globalThis.__deephealing.acSnapshot();
  const npc = snapshot.npcs.find((item) => item.id === 'npc-006') ?? null;
  const millimetres = npc?.transform?.pos_mm ?? null;
  return {
    parts,
    pos_m: millimetres === null ? null : [millimetres.x / 1000, millimetres.y / 1000, millimetres.z / 1000],
    state_id: npc?.transform?.state_id ?? null,
  };
});

/**
 * 取景写死 + 机读复算：从页面读出 npc 位置/部件表 ⇒ 算出机位 ⇒ 截图 ⇒ **再读一次**位置/部件表
 * 并用**同一投影公式**复算占高/占面（不是把目标值抄回来）。允许重试（人物在动）。
 */
const framedShot = async (page, name, mode) => {
  const attempts = [];
  for (let attempt = 1; attempt <= 4; attempt += 1) {
    const inputs = await readFramingInputs(page);
    if (inputs.pos_m === null) return { name, mode, ok: false, reason: 'no npc-006 in snapshot', attempts };
    const body = partBounds(inputs.parts, inputs.parts.map((part) => part.part));
    const head = partBounds(inputs.parts, ['head']);
    if (body === null || head === null) return { name, mode, ok: false, reason: 'characterReport missing parts', attempts };
    const bodyHeight = body.high[1] - body.low[1];
    const bodyCentreY = (body.high[1] + body.low[1]) / 2;
    const headCentre = [0, 1, 2].map((axis) => (head.high[axis] + head.low[axis]) / 2);
    let view;
    if (mode === 'full_body') {
      // 竖直视角 45° ⇒ 画高 = 2·d·tan(22.5°) ⇒ d = 身高 / (2·tan22.5°·目标占高)
      const distance = bodyHeight / (2 * FOV_TAN * FRAME_FULL_BODY_TARGET);
      view = {
        position_m: [inputs.pos_m[0], inputs.pos_m[1] + bodyCentreY, inputs.pos_m[2] + distance],
        look_at_m: [inputs.pos_m[0], inputs.pos_m[1] + bodyCentreY, inputs.pos_m[2]],
      };
    } else {
      const faceArea = (head.high[0] - head.low[0]) * (head.high[1] - head.low[1]);
      const distance = Math.sqrt(faceArea / (2 * FOV_TAN * FOV_TAN * (VIEW_W / VIEW_H) * FRAME_FACE_TARGET));
      view = {
        position_m: [inputs.pos_m[0] + headCentre[0], inputs.pos_m[1] + headCentre[1], inputs.pos_m[2] + headCentre[2] + distance],
        look_at_m: [inputs.pos_m[0] + headCentre[0], inputs.pos_m[1] + headCentre[1], inputs.pos_m[2] + headCentre[2]],
      };
    }
    await page.evaluate((v) => globalThis.__deephealing.scene.setObservationCamera(v), view);
    const file = join(SHOTS_READBACK, `${name}-${TAG}.png`);
    await page.screenshot({ path: file });
    // **复算**（截图后再读一次页面状态；用同一投影公式）
    const after = await readFramingInputs(page);
    const afterBody = partBounds(after.parts, after.parts.map((part) => part.part));
    const afterHead = partBounds(after.parts, ['head']);
    const corners = [];
    for (const axisX of [afterBody.low[0], afterBody.high[0]]) {
      for (const axisY of [afterBody.low[1], afterBody.high[1]]) {
        for (const axisZ of [afterBody.low[2], afterBody.high[2]]) {
          corners.push([after.pos_m[0] + axisX, after.pos_m[1] + axisY, after.pos_m[2] + axisZ]);
        }
      }
    }
    const projected = corners.map((corner) => projectPoint(view.position_m, view.look_at_m, corner));
    const bodyTop = Math.min(...projected.map((p) => p.py));
    const bodyBottom = Math.max(...projected.map((p) => p.py));
    const frameHeightFraction = (bodyBottom - bodyTop) / VIEW_H;
    const faceCorners = [];
    for (const axisX of [afterHead.low[0], afterHead.high[0]]) {
      for (const axisY of [afterHead.low[1], afterHead.high[1]]) {
        for (const axisZ of [afterHead.low[2], afterHead.high[2]]) {
          faceCorners.push([after.pos_m[0] + axisX, after.pos_m[1] + axisY, after.pos_m[2] + axisZ]);
        }
      }
    }
    const faceProjected = faceCorners.map((corner) => projectPoint(view.position_m, view.look_at_m, corner));
    const faceBox = {
      x0: Math.max(0, Math.min(...faceProjected.map((p) => p.px))),
      y0: Math.max(0, Math.min(...faceProjected.map((p) => p.py))),
      x1: Math.min(VIEW_W, Math.max(...faceProjected.map((p) => p.px))),
      y1: Math.min(VIEW_H, Math.max(...faceProjected.map((p) => p.py))),
    };
    const inFrame = faceProjected.every((p) => p.px >= 0 && p.px <= VIEW_W && p.py >= 0 && p.py <= VIEW_H && p.depth_m > 0);
    const record = {
      attempt, file, camera_view: { position_m: view.position_m, look_at_m: view.look_at_m },
      npc_pos_m_at_shot: after.pos_m, state_id_at_shot: after.state_id,
      body_local_aabb: afterBody, head_local_aabb: afterHead,
      frame_height_fraction: Number(frameHeightFraction.toFixed(4)),
      body_top_px: Number(bodyTop.toFixed(1)), body_bottom_px: Number(bodyBottom.toFixed(1)),
      face_px_box: { x0: Math.round(faceBox.x0), y0: Math.round(faceBox.y0), x1: Math.round(faceBox.x1), y1: Math.round(faceBox.y1) },
      face_in_frame: inFrame,
      face_area_fraction: Number((((faceBox.x1 - faceBox.x0) * (faceBox.y1 - faceBox.y0)) / (VIEW_W * VIEW_H)).toFixed(4)),
    };
    attempts.push(record);
    const good = mode === 'full_body'
      ? record.frame_height_fraction >= 1 / 3
      : record.face_area_fraction >= 0.15 && record.face_in_frame;
    if (good || attempt === 4) {
      // **裁剪复核**：由**浏览器**按投影框再截一张（脸框外扩 12%）
      let cropFile = null;
      if (mode === 'face') {
        const padX = (record.face_px_box.x1 - record.face_px_box.x0) * 0.12;
        const padY = (record.face_px_box.y1 - record.face_px_box.y0) * 0.12;
        const clip = {
          x: Math.max(0, record.face_px_box.x0 - padX), y: Math.max(0, record.face_px_box.y0 - padY),
          width: Math.min(VIEW_W, record.face_px_box.x1 + padX) - Math.max(0, record.face_px_box.x0 - padX),
          height: Math.min(VIEW_H, record.face_px_box.y1 + padY) - Math.max(0, record.face_px_box.y0 - padY),
        };
        cropFile = join(SHOTS_READBACK, `${name}-crop-${TAG}.png`);
        await page.screenshot({ path: cropFile, clip });
        record.crop_file = cropFile;
        record.crop_clip = clip;
      }
      copyFileSync(file, join(SHOTS_FROZEN, `${name}-${TAG}.png`));
      if (cropFile) copyFileSync(cropFile, join(SHOTS_FROZEN, `${name}-crop-${TAG}.png`));
      return { name, mode, ok: good, file, record, attempts };
    }
  }
  return { name, mode, ok: false, attempts };
};

const panoReading = await shoot('pano-1440x900');
await shoot('near-1440x900', { camera: INDOOR_WIDE });
// FIX-1①②：**重拍的取景写死证据**（全身 ≥1/3 画高；面部特写 ≥15% 画面 + 裁剪复核）
const fullBodyShot = await framedShot(page, 'full-body-1440x900', 'full_body');
const faceShot = await framedShot(page, 'closeup-face-1440x900', 'face');
// FIX-1③：页内读数（仍是 inspection —— 交付页**没有**可编程的进入入口；模块级读数见下 `interactive_camera`）
const pageCameraReading = await page.evaluate(() => globalThis.__deephealing.scene.presentationReport().camera);
await shoot('interactive-cam-1440x900', { camera: fullBodyShot.record?.camera_view ?? INDOOR_WIDE });
// motion-sheet：同机位连续 8 帧（含转身）
const motionFrames = [];
for (let index = 0; index < 8; index += 1) {
  const file = join(SHOTS_READBACK, `motion-sheet-${TAG}-f${index + 1}.png`);
  await page.evaluate((view) => globalThis.__deephealing.scene.setObservationCamera(view), INDOOR_WIDE);
  await page.waitForTimeout(700);
  await page.screenshot({ path: file });
  motionFrames.push(file);
}
await page.evaluate(() => globalThis.__deephealing.scene.setObservationCamera(null));

// ── 回落批次（A-8a 盲评的第二批）：`setAppearance(null)` ⇒ 通用人形兜底（交付面既有入口）
const fallbackReport = await page.evaluate(() => {
  globalThis.__deephealing.scene.setAppearance(null);
  return { set_appearance_null: true };
});
await page.waitForTimeout(1500);
const fallbackShots = [];
for (const [name, camera] of [['fallback-pano-1440x900', null], ['fallback-closeup-1440x900', INDOOR_WIDE]]) {
  if (camera) {
    await page.evaluate((view) => globalThis.__deephealing.scene.setObservationCamera(view), camera);
    await page.waitForTimeout(600);
  }
  const file = join(SHOTS_READBACK, `${name}-${TAG}.png`);
  await page.screenshot({ path: file, timeout: 30000 });
  copyFileSync(file, join(SHOTS_FROZEN, `${name}-${TAG}.png`));
  fallbackShots.push(file);
}
const fallbackCharacter = await page.evaluate(() => ({
  character_degradations: (() => {
    try { return globalThis.__deephealing.scene.characterReport?.()?.degradations ?? null; } catch { return null; }
  })(),
  appearance_source: (() => {
    try { return globalThis.__deephealing.scene.appearanceReport?.()?.source ?? null; } catch { return null; }
  })(),
}));
await page.evaluate(() => globalThis.__deephealing.scene.setObservationCamera(null));
// **构建产物缺口（机器读数，不靠人眼）**：`vite build` 不搬运未被 import 的静态件
const buildProductGap = {
  glb_in_build_product: existsSync(join(WEB, 'assets', 'character', 'xuqin-body.glb')),
  glb_in_delivery_tree: existsSync(join(SOURCE, 'v0_skeleton', 'web', 'assets', 'character', 'xuqin-body.glb')),
  build_character_dir_exists: existsSync(join(WEB, 'assets', 'character')),
};

// ── D：原始逐帧读数（30 s；DPR1；固定相机路径 = 探针自带机位）
// ⚠️ **顺序敏感（实测踩过）**：这段是 30 s 的忙 `rAF` 循环，会把 CPU 占满 ⇒ 期间新开页面
// 可能**启动超时**。所以它被搬到 I-5/I-4 之后（同页面、同构建产物、读数字段不变）。
const measurePerf = () => page.evaluate(async () => {
  const frames = [];
  const heapStart = globalThis.performance?.memory?.usedJSHeapSize ?? null;
  const start = performance.now();
  let last = start;
  await new Promise((done) => {
    const loop = () => {
      const now = performance.now();
      frames.push(Number((now - last).toFixed(3)));
      last = now;
      if (now - start >= 30000) { done(); return; }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  });
  return {
    frames, heap_start: heapStart, heap_end: globalThis.performance?.memory?.usedJSHeapSize ?? null,
    viewport: { width: window.innerWidth, height: window.innerHeight, dpr: window.devicePixelRatio },
    camera_path: 'probe-owned camera (setObservationCamera INDOOR_WIDE at capture)', warmup: 100, note: 'real browser rAF deltas',
  };
});
// `perf_frames_n5c.json` 的落盘在调用点（见 I-4 段之后）。

// ── I-5：窄屏 390×844 溢出 + 控件 AABB（**在 D 之前**跑：避免被 30 s 忙循环饿死）
const narrow = await browser.newPage({ viewport: { width: 390, height: 844 } });
await narrow.goto(`http://127.0.0.1:${PORT}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
let narrowBooted = true;
try {
  await narrow.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 90000 });
} catch { narrowBooted = false; }
await narrow.waitForTimeout(3000);
const narrowReading = await narrow.evaluate(() => {
  const rect = (id) => {
    const element = document.getElementById(id);
    if (!element) return null;
    const box = element.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  };
  const inViewport = (box) => Boolean(box) && box.x >= 0 && box.y >= 0
    && box.x + box.width <= window.innerWidth && box.y + box.height <= window.innerHeight;
  const scrollWidth = document.documentElement.scrollWidth;
  const clientWidth = document.documentElement.clientWidth;
  return {
    viewport: { width: window.innerWidth, height: window.innerHeight },
    scroll_width: scrollWidth, client_width: clientWidth,
    no_horizontal_overflow: scrollWidth <= clientWidth,
    booted: Boolean(globalThis.__deephealing),
    credits: (() => {
      try { return globalThis.__deephealing.creditsReport(); } catch { return null; }
    })(),
    broadcast_boxes: { player_ui: rect('player-ui'), hud: rect('hud'), credits: rect('credits') },
    controls_in_viewport: { credits: inViewport(rect('credits')), player_ui: inViewport(rect('player-ui')) },
  };
});
const narrowFile = join(SHOTS_READBACK, `narrow-390x844-${TAG}.png`);
await narrow.screenshot({ path: narrowFile });
copyFileSync(narrowFile, join(SHOTS_FROZEN, `narrow-390x844-${TAG}.png`));
await narrow.close();

// ── I-4：WebGL 不可用 ⇒ 显式提示、不白屏、不抛未捕获异常
const noWebgl = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const noWebglErrors = [];
noWebgl.on('pageerror', (error) => noWebglErrors.push(String(error)));
await noWebgl.addInitScript(() => {
  const original = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function getContext(type, ...rest) {
    if (String(type).includes('webgl')) return null;
    return original.call(this, type, ...rest);
  };
});
await noWebgl.goto(`http://127.0.0.1:${PORT}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
await noWebgl.waitForTimeout(6000);
const noWebglReading = await noWebgl.evaluate(() => ({
  app_booted: Boolean(globalThis.__deephealing),
  scene_present: Boolean(document.getElementById('scene')),
  body_text_visible: document.body.innerText.trim().length > 0,
  degradations: (() => {
    try { return globalThis.__deephealing.scene.characterReport?.()?.degradations ?? null; } catch { return null; }
  })(),
  canvas_size: (() => {
    const canvas = document.getElementById('scene');
    return canvas ? { width: canvas.width, height: canvas.height } : null;
  })(),
}));
const noWebglShot = join(SHOTS_READBACK, `webgl-disabled-1440x900-${TAG}.png`);
await noWebgl.screenshot({ path: noWebglShot });
await noWebgl.close();

// ── D：现在跑 30 s 逐帧读数（其它页面都已关闭 ⇒ 无 CPU 争用；机位写死 = 取证机位）
await page.evaluate((view) => globalThis.__deephealing.scene.setObservationCamera(view), INDOOR_WIDE);
await page.waitForTimeout(800);
const perfRaw = await measurePerf();
writeFileSync(join(READBACK, 'perf_frames_n5c.json'), `${JSON.stringify(perfRaw)}\n`);
await page.evaluate(() => globalThis.__deephealing.scene.setObservationCamera(null));

// ── B：表现层读数（权威位移 → 显示位置/朝向/表现槽；喂给交付面 presentation.ts）
await sleep(1000);
const presentation = await import(join(SOURCE, 'v0_skeleton', 'web', 'src', 'scene', 'presentation.ts'));
/** FIX-1③：`AC-A-3⑦` 的**可进入性读数** —— 显式调交付面 `enterInteractiveCamera()`。 */
const interactiveEngine = presentation.createPresentation({ smoothingMs: 100, epsAuthorityMaxStepM: 0.92736 });
const cameraBeforeEnter = interactiveEngine.cameraReport();
interactiveEngine.enterInteractiveCamera();
const cameraAfterEnter = interactiveEngine.cameraReport();
const interactiveCameraReading = {
  entry_point: 'web/src/scene/presentation.ts :: enterInteractiveCamera()',
  scope: 'module_level_node_side（交付面模块的实例；交付页当前**未**暴露可编程入口 ⇒ 页内 camera_mode 仍为 inspection）',
  before_enter: cameraBeforeEnter,
  after_enter: cameraAfterEnter,
  camera_mode_after_enter: cameraAfterEnter.camera_mode,
  interactive_entered_after_enter: cameraAfterEnter.interactive_entered,
  page_presentation_camera: pageCameraReading,
};
// FIX-1⑤：`AC-A-3⑥` 点名的阴影 `mapSize` / `radius` 读数（页面侧，来自真光源实例）
const shadowReading = await page.evaluate(() => globalThis.__deephealing.scene.environmentReport().sun_shadow ?? null);
const records = readFileSync(join(OUT, 'bridge-records-a-evidence.jsonl'), 'utf8')
  .split('\n').filter(Boolean).map((line) => JSON.parse(line));
const snapshots = records.filter((record) => record.kind === 'snapshot')
  .sort((left, right) => Number(left.tick) - Number(right.tick));
presentation.resetPresentation();
const engine = presentation.createPresentation({ smoothingMs: 100, epsAuthorityMaxStepM: 0.92736 });
const displayedSamples = [];
for (const snapshot of snapshots) {
  const npc = (snapshot.state?.entities ?? []).find((entity) => entity.id === 'npc-006');
  if (!npc) continue;
  const pos = npc.transform?.pos_mm ?? { x: 0, y: 0, z: 0 };
  presentation.apply([{ entityId: 'npc-006', pos_m: [pos.x / 1000, pos.y / 1000, pos.z / 1000],
                        stateId: 'daily', tick: Number(snapshot.tick) }], Number(snapshot.tick));
  engine.step(100);
  const row = engine.displayed().find((entity) => entity.entityId === 'npc-006');
  if (row) displayedSamples.push({ tick: Number(snapshot.tick), pos: row.displayed_position_m,
                                   yaw: row.facing_yaw_rad });
}
const wrapToPi = presentation.wrapToPi;
const deltasP = displayedSamples.slice(1).map((row, index) => Math.hypot(
  row.pos[0] - displayedSamples[index].pos[0], row.pos[1] - displayedSamples[index].pos[1],
  row.pos[2] - displayedSamples[index].pos[2]));
const deltasYaw = displayedSamples.slice(1).map((row, index) =>
  Math.abs(wrapToPi(row.yaw - displayedSamples[index].yaw)));
const bReading = {
  samples: displayedSamples.length,
  max_abs_delta_p_m: deltasP.length ? Math.max(...deltasP) : 0,
  median_abs_delta_p_m: deltasP.length ? [...deltasP].sort((a, b) => a - b)[Math.floor(deltasP.length / 2)] : 0,
  delta_p_floor_m: 1.39104,
  max_abs_delta_yaw_deg: deltasYaw.length ? Math.max(...deltasYaw) * 180 / Math.PI : 0,
  slot_events: presentation.clipTimelineSnapshot().filter((event) => event.entityId === 'npc-006').length,
  turn_hit_rate: presentation.turnHitRate(),
  max_deviation_m: engine.maxDeviationM(),
  eps_used_m: engine.epsUsedM(),
  authority_steps: presentation.authorityStepsSnapshot().length,
  moving_ticks: presentation.authorityStepsSnapshot().filter((step) => step.dpos_norm_m > 0).length,
};
writeFileSync(join(READBACK, 'presentation_report_n5c.json'), `${JSON.stringify(bReading, null, 2)}\n`);

// ── D2 ①：**构建产物字节锚**（交付面 `.build/web/**` 里真的带署名串）
const buildHit = spawnSync('grep', ['-rl', '© 2017 Cesium', WEB]).stdout.toString().trim().split('\n').filter(Boolean);
const buildAnchor = {
  web_dir: WEB,
  attribution_string: '© 2017 Cesium — CC BY 4.0 International（经 Khronos glTF-Sample-Assets 分发：Models/CesiumMan/glTF-Binary/CesiumMan.glb）',
  files_containing_attribution: buildHit.map((file) => file.replace(`${WEB}/`, '')),
  hit_count: buildHit.length,
  index_html_has_credits_mount: (() => {
    try { return readFileSync(join(WEB, 'index.html'), 'utf8').includes('id="credits"'); } catch { return false; }
  })(),
  sha256_of_hit_files: Object.fromEntries(buildHit.map((file) => {
    const relative = file.replace(`${WEB}/`, '');
    return [relative, createHash('sha256').update(readFileSync(file)).digest('hex')];
  })),
};

await browser.close();
await sleep(800);
host.kill('SIGTERM');
await sleep(500);

const reading = {
  task: 'a-evidence', at_epoch: Math.floor(Date.now() / 1000),
  ...META,
  framing: {
    viewport: { width: VIEW_W, height: VIEW_H }, fov_deg: FOV_DEG,
    full_body_shot: fullBodyShot, face_shot: faceShot,
    criteria: { full_body_min_frame_height_fraction: 1 / 3, face_min_area_fraction: 0.15 },
  },
  interactive_camera: interactiveCameraReading,
  shadow_readout: shadowReading,
  tag: TAG, tag_parts: { commit_short: commitShort, commit_full: commitFull,
                         asset_bundle_sha256: assetBundle, binding_set_sha256: bindingSet,
                         config_hash: configHash },
  workspace: WORKSPACE, web_dir: WEB, pack: PACK, out_dir: OUT,
  shots, shot_names: shots.map((shot) => shot.name), motion_frames: motionFrames,
  fallback_shots: fallbackShots, narrow_shot: narrowFile, webgl_disabled_shot: noWebglShot,
  fallback_batch: {
    mode: '`scene.setAppearance(null)` ⇒ 通用人形兜底（A-8a 盲评第二批；交付面既有入口）',
    report: fallbackReport,
    character: fallbackCharacter,
    shots: fallbackShots,
    build_product_gap: buildProductGap,
  },
  credits_report_1440: creditsReport, ui_sets: uiSets, viewport: viewportInfo,
  camera_report_default: cameraModes, pano_reading: panoReading,
  build_artifact_anchor: buildAnchor,
  narrow_390x844: narrowReading,
  webgl_disabled: { ...noWebglReading, page_errors: noWebglErrors.slice(0, 5) },
  perf_raw_frames_file: join(READBACK, 'perf_frames_n5c.json'),
  presentation: bReading,
  page_errors_1440: pageErrors.slice(0, 8),
  config_plane_note: 'configExport（presentationConstants/postfxReport/materialReport）属**配置面**读数，不是像素证据',
};
writeFileSync(join(READBACK, 'a-evidence-reading.json'), `${JSON.stringify(reading, null, 2)}\n`);
process.stdout.write(`A_EVIDENCE ${JSON.stringify({
  tag: TAG, shots: shots.length, motion_frames: motionFrames.length,
  credits_within_viewport: creditsReport.within_viewport,
  narrow_overflow_ok: narrowReading.no_horizontal_overflow,
  webgl_disabled: { booted: noWebglReading.app_booted, errors: noWebglErrors.length },
  build_anchor_files: buildAnchor.hit_count, presentation: { samples: bReading.samples,
    max_dp: bReading.max_abs_delta_p_m, slots: bReading.slot_events },
})}\n`);
process.exit(0);
