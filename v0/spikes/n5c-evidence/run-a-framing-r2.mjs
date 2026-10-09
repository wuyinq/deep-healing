#!/usr/bin/env node
/**
 * N5-C r2 / FIX-1（**取景重拍**）—— 只重拍两张「取景写死」的证据图，不重跑整套 A 取证。
 *
 * 为什么要单独一支脚本（r2 实测发现）：
 *   ① 交付面在浏览器里**真正画出来的角色是 GLB**（`xuqin-body.glb`，CesiumMan），
 *      它被挂在实体根 mesh 下 `position(0,0,0)` ⇒ 其**自身**原点即实体放置点；
 *      模型的 AABB（从 .glb 的 POSITION min/max 逐节点变换后取并集，见 `glbAabb()`）
 *      是 y∈[0, 1.5065] / x∈[±0.569] / z∈[-0.131, 0.181]。
 *   ② 而**盒体部件表**（`characterReport()`）用的是「躯干居中、脚在 y=-1.22」的另一套局部系
 *      ⇒ 两者竖直相差 1.22 m。用盒体表瞄准 ⇒ 画面里根本没有人（r2 第一次重拍的实测结果）。
 *   ⇒ 本脚本**只**用「GLB 的 AABB + 交付面渲染位置（`scene.geometry()`）」算机位，
 *     并按同一组数复算占高/占面（投影复算），再交浏览器按投影框裁剪（裁剪复核）。
 *
 * 产物：`readback/full-body-1440x900-<tag>.png`、`readback/closeup-face-1440x900-<tag>.png`
 *      + `-crop-`，`readback/a-evidence-framing-r2.json`；同名图同步 copy 到 `spikes/n5-asset/shots/`。
 */
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
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
const PORT = 8847;
const NPC = 'npc-006';
mkdirSync(SHOTS_READBACK, { recursive: true });
mkdirSync(SHOTS_FROZEN, { recursive: true });
mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
const sha256 = (text) => createHash('sha256').update(text, 'utf8').digest('hex');
const CHROMIUM = [
  process.env.PW_CHROMIUM,
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1248',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean).find((candidate) => existsSync(candidate));

// ── 四段式 tag（与 run-a-evidence.mjs 逐字同口径）
const provenance = JSON.parse(readFileSync(join(SOURCE, 'v0_skeleton', 'web', 'assets', 'provenance.json'), 'utf8'));
const assetBundle = sha256(provenance.assets.map((a) => `${a.asset_id}:${a.converted_sha256}`).sort().join('\n'));
const bindingModule = await import(join(SOURCE, 'v0_skeleton', 'web', 'src', 'scene', 'asset_binding.ts'));
const bindingSet = sha256(bindingModule.bindingSetLines().slice().sort().join('\n'));
const commitShort = spawnSync('git', ['-C', WORKSPACE, 'rev-parse', '--short=7', 'HEAD']).stdout.toString().trim();
const commitFull = spawnSync('git', ['-C', WORKSPACE, 'rev-parse', 'HEAD']).stdout.toString().trim();
const canonical = (value) => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((k) => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
  }
  if (typeof value === 'number') return value.toFixed(6);
  return JSON.stringify(value);
};

// ── .glb 的模型空间 AABB（POSITION accessor min/max 逐节点变换后取并集）
const glbAabb = (file) => {
  const buffer = readFileSync(file);
  const total = buffer.readUInt32LE(8);
  let offset = 12;
  let gltf = null;
  while (offset < total) {
    const chunkLength = buffer.readUInt32LE(offset);
    const chunkType = buffer.readUInt32LE(offset + 4);
    if (chunkType === 0x4E4F534A) gltf = JSON.parse(buffer.subarray(offset + 8, offset + 8 + chunkLength).toString('utf8'));
    offset += 8 + chunkLength;
  }
  const multiply = (a, b) => {
    const out = new Array(16).fill(0);
    for (let r = 0; r < 4; r += 1) for (let c = 0; c < 4; c += 1) {
      out[c * 4 + r] = a[0 * 4 + r] * b[c * 4 + 0] + a[1 * 4 + r] * b[c * 4 + 1]
        + a[2 * 4 + r] * b[c * 4 + 2] + a[3 * 4 + r] * b[c * 4 + 3];
    }
    return out;
  };
  const trs = (node) => {
    if (node.matrix) return node.matrix;
    const t = node.translation ?? [0, 0, 0];
    const [x, y, z, w] = node.rotation ?? [0, 0, 0, 1];
    const s = node.scale ?? [1, 1, 1];
    const rot = [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w), 0,
      2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w), 0,
      2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y), 0, 0, 0, 0, 1];
    const scale = [s[0], 0, 0, 0, 0, s[1], 0, 0, 0, 0, s[2], 0, 0, 0, 0, 1];
    const trans = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, t[0], t[1], t[2], 1];
    return multiply(trans, multiply(rot, scale));
  };
  const apply = (m, p) => [m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12],
    m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13],
    m[2] * p[0] + m[6] * p[1] + m[10] * p[2] + m[14]];
  const low = [Infinity, Infinity, Infinity];
  const high = [-Infinity, -Infinity, -Infinity];
  const visit = (index, parent) => {
    const node = gltf.nodes[index];
    const world = multiply(parent, trs(node));
    if (node.mesh !== undefined) {
      for (const prim of gltf.meshes[node.mesh].primitives ?? []) {
        const accessor = gltf.accessors[prim.attributes.POSITION];
        if (!accessor.min) continue;
        for (const cx of [accessor.min[0], accessor.max[0]]) {
          for (const cy of [accessor.min[1], accessor.max[1]]) {
            for (const cz of [accessor.min[2], accessor.max[2]]) {
              const p = apply(world, [cx, cy, cz]);
              for (let axis = 0; axis < 3; axis += 1) {
                low[axis] = Math.min(low[axis], p[axis]);
                high[axis] = Math.max(high[axis], p[axis]);
              }
            }
          }
        }
      }
    }
    for (const child of node.children ?? []) visit(child, world);
  };
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  for (const scene of gltf.scenes ?? []) for (const root of scene.nodes ?? []) visit(root, identity);
  return { low, high };
};

const GLB = join(SOURCE, 'v0_skeleton', 'web', 'assets', 'character', 'xuqin-body.glb');
const BLENDER = glbAabb(GLB);
// CesiumMan：发/头在最上端 ⇒ 取「顶部 0.28 m」为面部箱（宽取 ±0.10、进深取全模型 z 范围）。
const FACE_BOX = {
  low: [-0.10, BLENDER.high[1] - 0.28, BLENDER.low[2]],
  high: [0.10, BLENDER.high[1], BLENDER.high[2]],
};

const host = spawn('node', [join(HERE, 'serve-live.mjs'), '--tag', 'a-evidence-framing', '--port', String(PORT),
  '--pack', PACK, '--out', OUT, '--runtime', RUNTIME, '--web', WEB, '--source', SOURCE,
  '--tick-ms', '50', '--snapshot-every', '1', '--seed', '20260921',
  '--run-seconds', '600', '--start-paused', 'false', '--memory-chain', '--capability-chain',
], { stdio: ['ignore', 'pipe', 'pipe'] });
const killHost = () => { try { host.kill('SIGKILL'); } catch { /* 已退出 */ } };
process.on('exit', killHost);
process.on('SIGINT', () => { killHost(); process.exit(130); });
process.on('uncaughtException', (error) => { killHost(); throw error; });
await new Promise((ready, reject) => {
  const timer = setTimeout(() => reject(new Error('SERVE_READY timeout')), 90000);
  host.stdout.on('data', (chunk) => {
    writeFileSync(join(OUT, 'host-a-evidence-framing.log'), String(chunk), { flag: 'a' });
    if (String(chunk).includes('SERVE_READY')) { clearTimeout(timer); ready(); }
  });
});

const browser = await chromium.launch({ headless: true, executablePath: CHROMIUM,
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const pageErrors = [];
page.on('console', (msg) => { if (msg.type() === 'error') pageErrors.push(msg.text()); });
page.on('pageerror', (error) => pageErrors.push(String(error)));
await page.goto(`http://127.0.0.1:${PORT}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 60000 });
await page.waitForTimeout(6000);

// 渲染位置：`scene.geometry()` 的实体位置（= 场景**真的**建出来的位置，不是 live 投影）
const renderedPosition = () => page.evaluate(() => {
  const report = globalThis.__deephealing.scene.structureReport();
  const objects = report.objects ?? [];
  const root = objects.find((item) => item.id === 'npc-006') ?? null;
  const glb = objects.find((item) => String(item.id).startsWith('glb:')) ?? null;
  // `structureReport().matrix_world` 经 `quantizeMatrix()` = elements × 1e6（整数化）⇒ 除回米制。
  const translation = (matrix) => (Array.isArray(matrix) && matrix.length >= 16
    ? [matrix[12] / 1e6, matrix[13] / 1e6, matrix[14] / 1e6] : null);
  return {
    object_count: objects.length,
    root_matrix_translation: root === null ? null : translation(root.matrix_world),
    glb_object_id: glb?.id ?? null,
    glb_matrix_translation: glb === null ? null : translation(glb.matrix_world),
  };
});

const VIEW_W = 1440;
const VIEW_H = 900;
const FOV_TAN = Math.tan((45 * Math.PI / 180) / 2);
const sub3 = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross3 = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const unit3 = (a) => { const n = Math.hypot(a[0], a[1], a[2]); return [a[0] / n, a[1] / n, a[2] / n]; };
const projectPoint = (position, lookAt, world) => {
  const forward = unit3(sub3(lookAt, position));
  const right = unit3(cross3(forward, [0, 1, 0]));
  const up = cross3(right, forward);
  const d = sub3(world, position);
  const zv = dot3(d, forward);
  return { px: ((dot3(d, right) / (zv * FOV_TAN * (VIEW_W / VIEW_H)) + 1) / 2) * VIEW_W,
    py: ((1 - dot3(d, up) / (zv * FOV_TAN)) / 2) * VIEW_H, depth_m: zv };
};
const cornersOf = (low, high) => {
  const out = [];
  for (const x of [low[0], high[0]]) for (const y of [low[1], high[1]]) for (const z of [low[2], high[2]]) out.push([x, y, z]);
  return out;
};
const worldCorners = (origin, box) => cornersOf(
  [origin[0] + box.low[0], origin[1] + box.low[1], origin[2] + box.low[2]],
  [origin[0] + box.high[0], origin[1] + box.high[1], origin[2] + box.high[2]]);

const take = async (name, mode) => {
  const attempts = [];
  for (let attempt = 1; attempt <= 6; attempt += 1) {
    const rendered = await renderedPosition();
    const placement = rendered.root_matrix_translation;
    if (!placement) return { name, mode, ok: false, reason: `no npc-006 world matrix (${JSON.stringify(rendered)})`, attempts };
    const origin = placement.map(Number);
    const bodyHeight = BLENDER.high[1] - BLENDER.low[1];
    const bodyCentreY = (BLENDER.high[1] + BLENDER.low[1]) / 2;
    const faceSizeX = FACE_BOX.high[0] - FACE_BOX.low[0];
    const faceSizeY = FACE_BOX.high[1] - FACE_BOX.low[1];
    const faceCentre = [0, 1, 2].map((axis) => (FACE_BOX.low[axis] + FACE_BOX.high[axis]) / 2);
    let view;
    if (mode === 'full_body') {
      const distance = bodyHeight / (2 * FOV_TAN * 0.45);
      view = { position_m: [origin[0], origin[1] + bodyCentreY, origin[2] + distance],
        look_at_m: [origin[0], origin[1] + bodyCentreY, origin[2]] };
    } else {
      const distance = Math.sqrt((faceSizeX * faceSizeY) / (2 * FOV_TAN * FOV_TAN * (VIEW_W / VIEW_H) * 0.24));
      view = { position_m: [origin[0] + faceCentre[0], origin[1] + faceCentre[1], origin[2] + faceCentre[2] + distance],
        look_at_m: [origin[0] + faceCentre[0], origin[1] + faceCentre[1], origin[2] + faceCentre[2]] };
    }
    await page.evaluate((v) => globalThis.__deephealing.scene.setObservationCamera(v), view);
    const file = join(SHOTS_READBACK, `${name}-${TAG}.png`);
    await page.screenshot({ path: file });
    const after = (await renderedPosition()).root_matrix_translation.map(Number);
    const drift = Math.hypot(after[0] - origin[0], after[1] - origin[1], after[2] - origin[2]);
    const bodyProjected = worldCorners(after, BLENDER).map((c) => projectPoint(view.position_m, view.look_at_m, c));
    const faceProjected = worldCorners(after, FACE_BOX).map((c) => projectPoint(view.position_m, view.look_at_m, c));
    const faceBox = {
      x0: Math.max(0, Math.min(...faceProjected.map((p) => p.px))),
      y0: Math.max(0, Math.min(...faceProjected.map((p) => p.py))),
      x1: Math.min(VIEW_W, Math.max(...faceProjected.map((p) => p.px))),
      y1: Math.min(VIEW_H, Math.max(...faceProjected.map((p) => p.py))),
    };
    const record = {
      attempt, file, mode, camera_view: view, glb_model_aabb: BLENDER, face_box_local: FACE_BOX,
      rendered_position_m_before: origin, rendered_position_m_after: after, aim_drift_m: Number(drift.toFixed(4)),
      frame_height_fraction: Number(((Math.max(...bodyProjected.map((p) => p.py))
        - Math.min(...bodyProjected.map((p) => p.py))) / VIEW_H).toFixed(4)),
      body_top_px: Number(Math.min(...bodyProjected.map((p) => p.py)).toFixed(1)),
      body_bottom_px: Number(Math.max(...bodyProjected.map((p) => p.py)).toFixed(1)),
      face_px_box: { x0: Math.round(faceBox.x0), y0: Math.round(faceBox.y0), x1: Math.round(faceBox.x1), y1: Math.round(faceBox.y1) },
      face_in_frame: faceProjected.every((p) => p.px >= 0 && p.px <= VIEW_W && p.py >= 0 && p.py <= VIEW_H && p.depth_m > 0),
      face_area_fraction: Number((((faceBox.x1 - faceBox.x0) * (faceBox.y1 - faceBox.y0)) / (VIEW_W * VIEW_H)).toFixed(4)),
    };
    attempts.push(record);
    const aimed = drift <= 0.05;
    const good = mode === 'full_body'
      ? (record.frame_height_fraction >= 1 / 3 && aimed)
      : (record.face_area_fraction >= 0.15 && record.face_in_frame && aimed);
    if (good || attempt === 6) {
      let cropFile = null;
      if (mode === 'face') {
        const padX = (record.face_px_box.x1 - record.face_px_box.x0) * 0.12;
        const padY = (record.face_px_box.y1 - record.face_px_box.y0) * 0.12;
        const x = Math.max(0, record.face_px_box.x0 - padX);
        const y = Math.max(0, record.face_px_box.y0 - padY);
        const width = Math.min(VIEW_W, record.face_px_box.x1 + padX) - x;
        const height = Math.min(VIEW_H, record.face_px_box.y1 + padY) - y;
        // **裁剪复核 = 对已落盘的那一张 PNG 做真裁剪**（另开一页把 PNG 按偏移画进画布再截图），
        // 而不是「再实时截一张」——后者会因世界继续推进而拍到另一时刻（r2 第一次实测踩到）。
        const cropHtml = join(HERE, 'runtime', 'face-crop', `crop-${name}-${TAG}.html`);
        mkdirSync(dirname(cropHtml), { recursive: true });
        writeFileSync(cropHtml, `<!doctype html><meta charset="utf-8"><style>
  html,body{margin:0;padding:0;background:#000}
  #frame{position:relative;overflow:hidden;width:${Math.round(width)}px;height:${Math.round(height)}px}
  #frame img{position:absolute;left:${-Math.round(x)}px;top:${-Math.round(y)}px}
</style><div id="frame"><img src="${pathToFileURL(file).href}"></div>`);
        const cropPage = await browser.newPage({ viewport: { width: Math.round(width), height: Math.round(height) } });
        await cropPage.goto(pathToFileURL(cropHtml).href, { waitUntil: 'load' });
        await cropPage.waitForFunction(() => [...document.images].every((img) => img.complete && img.naturalWidth > 0),
          null, { timeout: 15000 });
        cropFile = file.replace(/\.png$/, '-crop.png');
        await cropPage.screenshot({ path: cropFile });
        await cropPage.close();
        record.crop_file = cropFile;
        record.crop_clip = { x, y, width, height };
        record.crop_source = file;
        record.crop_method = 'crop of the on-disk PNG（真裁剪，非二次实时截图）';
      }
      copyFileSync(file, join(SHOTS_FROZEN, file.split('/').pop()));
      if (cropFile) copyFileSync(cropFile, join(SHOTS_FROZEN, cropFile.split('/').pop()));
      return { name, mode, ok: good, file, record, attempts };
    }
  }
  return { name, mode, ok: false, attempts };
};

const TAG = process.env.FRAMING_TAG ?? `${commitShort}-${assetBundle.slice(0, 12)}-${bindingSet.slice(0, 8)}-${
  sha256(canonical(await page.evaluate(() => ({
    postfx: globalThis.__deephealing.scene.postfxReport?.() ?? null,
    material: globalThis.__deephealing.scene.materialReport?.() ?? null,
    camera: globalThis.__deephealing.scene.cameraReport?.() ?? null,
  })))).slice(0, 8)}`;

// 场景里必须先真的有 npc-006 的世界矩阵（状态经 WS 到达后才建；6 s 常量等待不够稳）。
await page.waitForFunction(() => (globalThis.__deephealing.scene.structureReport().objects ?? [])
  .some((item) => item.id === 'npc-006'), null, { timeout: 60000 });
await page.waitForTimeout(1500);

const diagnostic = await renderedPosition();
process.stdout.write(`FRAMING_DIAG ${JSON.stringify(diagnostic)}\n`);

const fullBody = await take('full-body-1440x900', 'full_body');
const face = await take('closeup-face-1440x900', 'face');
await page.evaluate(() => globalThis.__deephealing.scene.setObservationCamera(null));
for (const shot of [fullBody, face]) {
  process.stdout.write(`ATTEMPTS ${shot.name} ok=${shot.ok} ` + JSON.stringify(shot.attempts.map((a) => ({
    attempt: a.attempt, drift: a.aim_drift_m, frac: a.frame_height_fraction,
    face_frac: a.face_area_fraction, face_in: a.face_in_frame, cam: a.camera_view?.position_m,
  }))) + '\n');
}

const reading = {
  task: 'a-evidence-framing-r2', at_epoch: Math.floor(Date.now() / 1000), tag: TAG,
  node_version: process.version, browser_binary: CHROMIUM ?? null,
  toolchain: `node ${process.version} + playwright 1.63.0 + chromium ${CHROMIUM ?? 'playwright-default'}`,
  tree_head: commitFull,
  why: 'FIX-1 取景重拍：机位与投影复算改用**实际渲染出来的 GLB**（xuqin-body.glb / CesiumMan）的 AABB，'
     + '而不是盒体部件表（两者竖直相差 1.22 m ⇒ 用盒体表瞄准会拍到墙）。',
  glb: { file: GLB, model_aabb: BLENDER, face_box_local: FACE_BOX },
  full_body_shot: fullBody, face_shot: face,
  criteria: { full_body_min_frame_height_fraction: 1 / 3, face_min_area_fraction: 0.15 },
  page_errors: pageErrors.slice(0, 5),
};
writeFileSync(join(READBACK, 'a-evidence-framing-r2.json'), `${JSON.stringify(reading, null, 2)}\n`);
process.stdout.write(`A_FRAMING ${JSON.stringify({ tag: TAG, full_body: fullBody.ok, face: face.ok,
  full_body_fraction: fullBody.record?.frame_height_fraction, face_fraction: face.record?.face_area_fraction,
  node: process.version })}\n`);

await browser.close();
await sleep(500);
killHost();
await sleep(300);
process.exit(fullBody.ok && face.ok ? 0 : 1);
