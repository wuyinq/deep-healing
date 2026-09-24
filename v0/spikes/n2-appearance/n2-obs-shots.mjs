#!/usr/bin/env node
/**
 * F-1 实机取证（N2-r2 / spike 专用，**非交付面**）：室内取证机位下的徐琴可辨识性。
 *
 * 机位（**从实测部件 AABB 反推**，见 `readback/n2-obs-camera-baseline.json`）：
 *   - 徐琴 AABB = x∈[4.635,5.365] y∈[-1.12,0.70] z∈[14.83,15.17]（高 1.82 m，中心 (5,-0.21,15)）；
 *   - `room-1052` 盒 AABB = x∈[2.3,7.3] y∈[-1.5,1.5] z∈[12.5,17.5]（sizeFor('room')=[5,3,5]）；
 *   - 两个机位都落在该盒**内部**（真实存在的室内视点），且**不**改 `room` 的任何属性。
 *
 * **世界冻结口径（关键）**：室内取证全程 `POST /control/pause` ⇒ 角色**位置不变**，
 * 「日常态 vs 面具态」的逐像素差异因此**只**来自形态（面具部件），而不是「人走开了」。
 * 最后再 `resume` 并把世界驱动到 `tick ≥ 130`，证明**实机日程真的能**到达面具态。
 *
 * 产出 9 张图（`shots/`）+ 读数（`readback/n2-obs-shots.json`）：
 *   ① `n2-default-wide-daily` / ② `n2-default-wide-masked` —— **默认交付取景**（玩家看到的是盒子）
 *   ③ `n2-obs-indoor-daily` / ④ `n2-obs-indoor-masked` —— 室内取证机位（日常 / 面具，同位置）
 *   ⑤ `n2-obs-indoor-closeup-daily` / ⑥ `...-masked` —— 室内近景（瞳/唇/发可判读）
 *   ⑦ `n2-obs-indoor-control-generic` —— 对照臂：`setAppearance(null)` ⇒ 通用人形（非达标证据）
 *   ⑧ `n2-obs-indoor-daily-2` —— 同机位**重拍**（确定性自证）
 *   ⑨ `n2-obs-indoor-masked-driven` —— 世界放行后**驱动到 tick ≥ 130** 的真实面具态
 *
 * 用法（workdir `<ws>`）：
 *   node spikes/n2-appearance/n2-obs-shots.mjs --url http://127.0.0.1:8811 --out spikes/n2-appearance
 */
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';

import { chromium } from 'playwright';

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};
const URL_BASE = option('url', 'http://127.0.0.1:8811');
const OUT = resolve(option('out', 'spikes/n2-appearance'));
const PACK = option('pack', 'xingfu-xiaoqu-xuqin');
const NPC = option('npc', 'npc-006');
const MASK_TICK_MIN = Number(option('mask-tick-min', 130));
const MAX_WAIT_MS = Number(option('max-wait-ms', 120000));

/** 室内取证机位（米制世界坐标）—— 见文件头推导。 */
const INDOOR_WIDE = { position_m: [5.0, 0.35, 17.4], look_at_m: [5.0, -0.2, 15.0] };
/**
 * 近景机位（N2-r3 修正）：
 *   r2 值 = `{position_m: [5.0, 0.58, 15.95], look_at_m: [5.0, 0.45, 15.05]}`。
 *   **为什么改**：角色在 `x=4.756`，而 r2 机位把相机轴放在 `x=5.0` ⇒ 头部投到屏幕 `x≈388`，
 *   正落在**调试 HUD 面板**（`x∈[16,400]`，半透明）后面 ⇒ 面部被面板**冲淡**（实测：
 *   面板后的苍白皮肤被混成 `#dcdad7`，面板外才是真实渲染色 `#61554a`）⇒ 近景失去「可判读」能力。
 *   **怎么改**：只把近景机位**横向平移到角色轴上**（`x=4.756`，与 `npc-006` 放置点同轴）⇒
 *   面部落在画面中心 `x≈720`，完全离开面板；距离（0.95 m）与俯仰角**一字未动**。
 *   宽机位 `INDOOR_WIDE` **未动** ⇒ 与 r2 的宽图逐像素可比。
 */
const INDOOR_CLOSEUP = { position_m: [4.756, 0.58, 15.95], look_at_m: [4.756, 0.45, 15.05] };
/**
 * 3/4 侧向室内机位（N2-r4 新增）：
 *   **为什么加**：r4 的修复项是「性别可读」——长发过肩 / 收腰 / 露腿。纯正面机位里
 *   长发**长度**仍可能被读成「一个框」；3/4 侧向能同时读出「发的长度」「腰身收窄」「下摆以下露腿」。
 *   **怎么取**：角色正面 = **+z**，角色实测落在 `(4.756, 0, 15.0)`（见 `readings.*.npc_position_mm`）。
 *   机位取 `x=+6.9, z=+16.8`（相对角色偏 +x / +z 各约 2.1 / 1.8 m ⇒ 水平偏离正面轴约 48°），
 *   距角色 ≈ 2.7 m（与 `INDOOR_WIDE` 的 2.4 m 同量级 ⇒ 取景大小可比），注视角色躯干中部。
 *   注：首版机位 `[6.7,0.45,16.6]→[4.9,-0.25,15.0]` 实测把**发顶**投到画面 `y=−3.6 px`（顶端被切掉几像素）
 *   ⇒ 已后撤 0.2 m 并把注视点抬高到 `y=−0.10`（角色落回画面内、上下留边）。
 *   **仍是盒内真实视点**：`room-1052` AABB = x∈[2.3,7.3] y∈[-1.5,1.5] z∈[12.5,17.5] ⇒ 机位在盒内；
 *   不调用它 ⇒ 默认取景逐项不变（既有判据 `observation_camera_is_additive_and_default_framing_unchanged` 仍绿）。
 *   `INDOOR_WIDE` / `INDOOR_CLOSEUP` 一字未动（与 r3 的图逐像素可比）。
 */
const INDOOR_SIDE = { position_m: [6.9, 0.35, 16.8], look_at_m: [4.9, -0.1, 15.0] };

const SHOTS = join(OUT, 'shots');
const READBACK = join(OUT, 'readback');
for (const dir of [SHOTS, READBACK]) mkdirSync(dir, { recursive: true });

const executablePath = [
  process.env.PW_CHROMIUM,
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1234',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
].filter(Boolean).find((candidate) => existsSync(candidate));

const browser = await chromium.launch({
  headless: true,
  executablePath,
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'],
});
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const log = { console: [], pageerror: [], bad_responses: [] };
page.on('console', (message) => log.console.push({ type: message.type(), text: message.text() }));
page.on('pageerror', (error) => log.pageerror.push({ text: String(error) }));
page.on('response', (response) => {
  if (response.status() >= 400) log.bad_responses.push({ status: response.status(), url: response.url() });
});

const shots = [];
const shot = async (name, note) => {
  await page.screenshot({ path: join(SHOTS, `${name}.png`) });
  shots.push({ name, file: `spikes/n2-appearance/shots/${name}.png`, note });
};

const readScene = () => ({
  camera: globalThis.__deephealing?.scene?.cameraReport?.() ?? null,
  appearance: globalThis.__deephealing?.scene?.appearanceReport?.() ?? [],
  character: globalThis.__deephealing?.scene?.characterReport?.() ?? [],
  viewport: globalThis.__deephealing?.scene?.viewport?.() ?? null,
  entityIds: globalThis.__deephealing?.entityIds?.() ?? [],
  npc_position_mm: (() => {
    const entities = globalThis.__deephealing?.liveProjection?.()?.entities ?? [];
    const npc = entities.find((entity) => entity.id === 'npc-006');
    return npc?.transform?.pos_mm ?? null;
  })(),
  tick: (() => {
    const projection = globalThis.__deephealing?.liveProjection?.();
    if (projection && Number.isFinite(Number(projection.tick))) return Number(projection.tick);
    return Number(globalThis.__deephealing?.acSnapshot?.()?.tick ?? 0);
  })(),
});

const readings = {};
const record = async (key) => {
  readings[key] = await page.evaluate(readScene);
  const entry = readings[key].appearance.find((item) => item.entity_id === NPC);
  return {
    camera_position: readings[key].camera.position,
    npc_position_mm: readings[key].npc_position_mm,
    npc_source: entry?.source ?? null,
    npc_state: entry?.state_id ?? null,
    npc_parts: entry?.parts.length ?? null,
    degradations: entry?.degradations ?? null,
    tick: readings[key].tick,
  };
};
const setCamera = (view) => page.evaluate(
  (argument) => globalThis.__deephealing.scene.setObservationCamera(argument), view);
const control = (action) => fetch(`${URL_BASE}/control/${action}`, { method: 'POST' })
  .then((response) => response.json()).catch((error) => ({ error: String(error) }));

await page.goto(`${URL_BASE}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => {
  const handle = globalThis.__deephealing;
  return Boolean(handle?.scene) && (handle.entityIds?.() ?? []).length > 0;
}, null, { timeout: MAX_WAIT_MS });
await page.waitForFunction((npc) => {
  const report = globalThis.__deephealing?.scene?.appearanceReport?.() ?? [];
  const entry = report.find((item) => item.entity_id === npc);
  return Boolean(entry) && entry.source === 'pack' && entry.parts.length >= 6;
}, NPC, { timeout: MAX_WAIT_MS });
// **先放行到有 live frame，再冻结世界**：室内取证全程 `pause` ⇒ 角色位置不变；
// 但 `/live/*` 投影需要**至少推进一步**才有帧（tick 0 时投影为空 ⇒ 注入会拿到 0 实体）。
const resumeResult = await control('resume');
await page.waitForFunction(() => {
  const projection = globalThis.__deephealing?.liveProjection?.();
  const entities = projection?.entities ?? [];
  return Number(projection?.tick ?? 0) >= 2 && entities.length > 0;
}, null, { timeout: MAX_WAIT_MS });
const pauseResult = await control('pause');
await page.waitForTimeout(1500);
const frozenProjection = await page.evaluate(() => {
  const projection = globalThis.__deephealing?.liveProjection?.() ?? {};
  return { tick: Number(projection.tick ?? 0), entities: (projection.entities ?? []).length };
});

const summary = {};

/** 冻结世界下把 npc-006 的日程目标显式设成某个实体（唯一变量 ⇒ 两态可比）。 */
const injectNpcTarget = (target, stateName) => page.evaluate(({ npc, target, stateName }) => {
  const projection = globalThis.__deephealing?.liveProjection?.() ?? {};
  const entities = projection.entities ?? projection.state?.entities ?? [];
  if (!Array.isArray(entities) || entities.length === 0) {
    return { error: 'E_EMPTY_PROJECTION (注入被拒绝，避免清空场景)', injected_entities: 0 };
  }
  const injected = entities.map((entity) => (entity.id === npc
    ? { ...entity, schedule: { ...(entity.schedule ?? {}), state: stateName, target_entity: target } }
    : entity));
  globalThis.__deephealing.scene.apply({
    t: 'snapshot', tick: Number(projection.tick ?? 0), state: { entities: injected },
  });
  return { injected_entities: injected.length, target_entity: target, schedule_state: stateName };
}, { npc: NPC, target, stateName });

// ── 显式注入**日常态**（target_entity = room-1052）⇒ 与面具态只差这一个变量
const dailyInjection = await injectNpcTarget('room-1052', 'resting');
if (dailyInjection.error) throw new Error(dailyInjection.error);
await page.waitForTimeout(800);

// ── ① 默认交付取景（**不调用**取证机位）—— 玩家看到的是盒子
await shot('n2-default-wide-daily', '默认交付取景 · 日常态（**玩家看到的是 room-1052 盒，不是人**）');
summary.default_wide_daily = await record('default_wide_daily');

// ── ③ 室内取证机位 · 日常态
await setCamera(INDOOR_WIDE);
await page.waitForTimeout(1200);
await shot('n2-obs-indoor-daily', '室内取证机位（room-1052 内部，距角色 ~2.47 m）· 日常态');
summary.indoor_daily = await record('indoor_daily');

// ── ⑧ 同机位重拍（确定性自证）
await shot('n2-obs-indoor-daily-2', '同一室内机位 / 同一状态**重拍**（确定性自证：应与上一张逐像素相同）');

// ── ⑤ 室内近景 · 日常态
await setCamera(INDOOR_CLOSEUP);
await page.waitForTimeout(1200);
await shot('n2-obs-indoor-closeup-daily', '室内近景（距头部 ~0.95 m）· 日常态');
summary.indoor_closeup_daily = await record('indoor_closeup_daily');

// ── ⑩ 室内 3/4 侧向 · 日常态（N2-r4 新增机位）
await setCamera(INDOOR_SIDE);
await page.waitForTimeout(1200);
await shot('n2-obs-indoor-side-daily', '室内 3/4 侧向（距角色 ~2.5 m，偏离正面轴 ~50°）· 日常态：读「长发过肩长度 + 收腰 + 露腿」');
summary.indoor_side_daily = await record('indoor_side_daily');
// 同机位重拍（确定性自证）
await shot('n2-obs-indoor-side-daily-2', '同一 3/4 侧向机位 / 同一状态**重拍**（确定性自证：应与上一张逐像素相同）');

// ── ④⑥② 面具态（**世界仍冻结 ⇒ 与日常态同位置**，唯一变量 = `target_entity`）
const maskInjection = await injectNpcTarget('kitchen-01', 'working');
if (maskInjection.error) throw new Error(maskInjection.error);
// **N2-r4 修正**：侧向机位是插在近景之后拍的 ⇒ 拍面具态近景前必须**显式切回** `INDOOR_CLOSEUP`，
// 否则「近景 daily ↔ masked」会在两台不同机位之间比（diff 不可归因于形态）。
await setCamera(INDOOR_CLOSEUP);
await page.waitForTimeout(1200);
await shot('n2-obs-indoor-closeup-masked', '室内近景 · 面具态（世界冻结 ⇒ 与近景日常态**同位置**）');
summary.indoor_closeup_masked = await record('indoor_closeup_masked');
await setCamera(INDOOR_WIDE);
await page.waitForTimeout(1200);
await shot('n2-obs-indoor-masked', '室内取证机位 · 面具态（世界冻结 ⇒ 与日常态**同位置**）');
summary.indoor_masked = await record('indoor_masked');
// ── ⑪ 室内 3/4 侧向 · 面具态（与侧向日常态**同位置**，唯一变量 = `target_entity`）
await setCamera(INDOOR_SIDE);
await page.waitForTimeout(1200);
await shot('n2-obs-indoor-side-masked', '室内 3/4 侧向 · 面具态（世界冻结 ⇒ 与侧向日常态**同位置**）');
summary.indoor_side_masked = await record('indoor_side_masked');
await setCamera(null);
await page.waitForTimeout(1200);
await shot('n2-default-wide-masked', '默认交付取景 · 面具态（仍是盒子）');
summary.default_wide_masked = await record('default_wide_masked');
summary.default_camera_restored = await page.evaluate(
  () => globalThis.__deephealing.scene.cameraReport().position);

// ── ⑦ 对照臂：同一室内机位 + `setAppearance(null)` ⇒ 确定性通用人形（**非达标证据**）
await page.evaluate((npc) => {
  const projection = globalThis.__deephealing?.liveProjection?.() ?? {};
  const entities = projection.entities ?? [];
  if (entities.length === 0) return;
  globalThis.__deephealing.scene.apply({
    t: 'snapshot', tick: Number(projection.tick ?? 0),
    state: { entities: entities.map((entity) => (entity.id === npc
      ? { ...entity, schedule: { ...(entity.schedule ?? {}), state: 'resting', target_entity: 'room-1052' } }
      : entity)) },
  });
  globalThis.__deephealing.scene.setAppearance(null);
}, NPC);
await setCamera(INDOOR_WIDE);
await page.waitForTimeout(1200);
await shot('n2-obs-indoor-control-generic', '对照臂：同一室内机位 + setAppearance(null) ⇒ 通用人形（非达标证据）');
summary.control_generic = await record('control_generic');

// ── ⑨ 放行世界：**重载页面**（清掉对照臂的注入）后 resume，驱动到 `tick ≥ 130` 的真实面具态
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => {
  const handle = globalThis.__deephealing;
  return Boolean(handle?.scene) && (handle.entityIds?.() ?? []).length > 0;
}, null, { timeout: MAX_WAIT_MS });
await page.waitForFunction((npc) => {
  const report = globalThis.__deephealing?.scene?.appearanceReport?.() ?? [];
  const entry = report.find((item) => item.entity_id === npc);
  return Boolean(entry) && entry.source === 'pack' && entry.parts.length >= 6;
}, NPC, { timeout: MAX_WAIT_MS });
await setCamera(INDOOR_WIDE);
await control('resume');
let maskRoute = 'equivalent_state_injection (world paused, same position)';
let driven = null;
const maskTrace = [];
const deadline = Date.now() + 120000;
while (Date.now() < deadline) {
  const snapshot = await page.evaluate(readScene);
  const entry = snapshot.appearance.find((item) => item.entity_id === NPC);
  maskTrace.push({ tick: snapshot.tick, state_id: entry?.state_id ?? null, source: entry?.source ?? null });
  if (snapshot.tick >= MASK_TICK_MIN && entry?.state_id === 'masked' && entry.source === 'pack') {
    driven = snapshot;
    break;
  }
  await page.waitForTimeout(2000);
}
if (driven) {
  maskRoute = 'driven_ticks (world resumed)';
  await page.waitForTimeout(1200);
  await shot('n2-obs-indoor-masked-driven', `室内取证机位 · 面具态（**驱动 ≥${MASK_TICK_MIN} tick**，实机日程到 kitchen-01）`);
  summary.indoor_masked_driven = await record('indoor_masked_driven');
}

const jsErrors = {
  console_error: log.console.filter((entry) => entry.type === 'error').length,
  pageerror: log.pageerror.length,
};
const document = {
  tag: 'n2-obs-shots',
  pack: PACK,
  npc: NPC,
  wiring: 'renderer reads the content pack READ-ONLY via ?pack= (world.ts lazy wiring); NOT delivered by the kernel state',
  observation_camera: { indoor_wide: INDOOR_WIDE, indoor_closeup: INDOOR_CLOSEUP, indoor_side: INDOOR_SIDE },
  world_frozen_for_indoor_shots: true,
  resume_result: resumeResult,
  pause_result: pauseResult,
  frozen_projection: frozenProjection,
  mask_injection: maskInjection,
  daily_injection: dailyInjection,
  mask_route_driven_shot: maskRoute,
  mask_trace_tail: maskTrace.slice(-6),
  shots,
  summary,
  readings,
  js_errors: { main_page: { ...jsErrors, total: jsErrors.console_error + jsErrors.pageerror } },
  bad_responses_main: log.bad_responses.slice(0, 10),
};
writeFileSync(join(READBACK, 'n2-obs-shots.json'), `${JSON.stringify(document, null, 2)}\n`);
process.stdout.write(`N2_OBS ${JSON.stringify(summary)}\n`);
process.stdout.write(`N2_OBS_JS_ERRORS ${JSON.stringify(document.js_errors.main_page)}\n`);
process.stdout.write(`N2_OBS_MASK_ROUTE ${maskRoute}\n`);
await browser.close();
