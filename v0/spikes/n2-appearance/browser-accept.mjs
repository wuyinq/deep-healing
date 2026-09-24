#!/usr/bin/env node
/**
 * N2 实机验收（spikes/** 脚手架，**非交付面**）：真 Chromium + 真会话层 + 真内核 + 真内容包。
 *
 * 覆盖 REQ-20260924-002 **AC-9**（+ AC-3/AC-4/AC-5 的实机读数）：
 *   ① 桌面 1440×900 截图；② 390px 窄屏截图；③ **面具态**截图；
 *   ④ JS 错误计数（console error + pageerror）—— 必须为 0；
 *   ⑤ 「徐琴可辨识」的**可复核读数**：`__deephealing.scene.characterReport()` 的部件数 /
 *      `appearanceReport()` 的 `source` / `state_id` / 逐部件 `source_hex`（**实机读回**，
 *      不是「代码里有这个函数」）；
 *   ⑥ **对照图**：不注入 appearance（主包 5 个住户 → 确定性通用人形）—— 只作对照，**不当达标证据**。
 *
 * 接线口径（如实声明，写进 `03` / `06`）：因 F-5（内核 state 契约封闭，
 * `world.schema.json` 的 `$defs/entity` 是 `additionalProperties:false`），人物**外形**
 * **不经内核下发**：渲染层按 `?pack=` 对内容包做**只读 GET**（`world.ts` 的惰性接线，
 * 与 `main.ts` 的 `loadNpcDisplayName()` 同一 URL 约定）取装配配置；取不到 ⇒ 通用人形兜底。
 *
 * 用法（workdir `<ws>`）：
 *   node spikes/n2-appearance/browser-accept.mjs --url http://127.0.0.1:8792 --out spikes/n2-appearance
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';

import { chromium } from 'playwright';

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};

const URL_BASE = option('url', 'http://127.0.0.1:8792');
const OUT = resolve(option('out', 'spikes/n2-appearance'));
const PACK = option('pack', 'xingfu-xiaoqu-xuqin');
const CONTROL_PACK = option('control-pack', 'xingfu-xiaoqu');
const NPC = option('npc', 'npc-006');
const MASK_TICK_MIN = Number(option('mask-tick-min', 130));
const MAX_WAIT_MS = Number(option('max-wait-ms', 120000));

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

/** 每个页面一套日志（JS 错误计数按页面分别统计）。 */
function instrument(page) {
  const log = { console: [], pageerror: [], bad_responses: [] };
  page.on('console', (message) => log.console.push({ type: message.type(), text: message.text() }));
  page.on('pageerror', (error) => log.pageerror.push({ text: String(error) }));
  page.on('response', (response) => {
    if (response.status() >= 400) log.bad_responses.push({ status: response.status(), url: response.url() });
  });
  page.on('requestfailed', (request) => {
    log.bad_responses.push({ status: 'failed', url: request.url(), reason: request.failure()?.errorText ?? '' });
  });
  return log;
}

const readScene = () => ({
  handle: Boolean(globalThis.__deephealing?.scene),
  tick: (() => {
    const projection = globalThis.__deephealing?.liveProjection?.();
    if (projection && Number.isFinite(Number(projection.tick))) return Number(projection.tick);
    const snapshot = globalThis.__deephealing?.acSnapshot?.();
    return Number(snapshot?.tick ?? 0);
  })(),
  entityIds: globalThis.__deephealing?.entityIds?.() ?? [],
  appearance: globalThis.__deephealing?.scene?.appearanceReport?.() ?? [],
  character: globalThis.__deephealing?.scene?.characterReport?.() ?? [],
  viewport: globalThis.__deephealing?.scene?.viewport?.() ?? null,
  reading: globalThis.__deephealing?.scene?.reading?.() ?? null,
  seen: (() => {
    const seen = globalThis.__n2_seen ?? [];
    const snapshots = seen.filter((item) => item.t === 'snapshot');
    const byType = {};
    for (const item of seen) byType[item.t] = (byType[item.t] ?? 0) + 1;
    return {
      total: seen.length,
      by_type: byType,
      snapshot_count: snapshots.length,
      snapshot_targets: [...new Set(snapshots.map((item) => item.target))],
      last_snapshot_tick: snapshots.length > 0 ? snapshots[snapshots.length - 1].tick : null,
    };
  })(),
});

const shots = [];
async function shot(page, name, note) {
  const file = join(SHOTS, `${name}.png`);
  await page.screenshot({ path: file });
  shots.push({ name, file: `spikes/n2-appearance/shots/${name}.png`, note });
  return file;
}

/** 起步闸门放行（脚手架默认先不推进世界；本脚本在**页面就绪之后**显式 resume）。**只控制是否发 step 命令**。 */
async function resumeWorld() {
  try {
    const response = await fetch(`${URL_BASE}/control/resume`, { method: 'POST' });
    return await response.json();
  } catch (error) {
    return { error: String(error) };
  }
}

// ─────────────────────────────────────────────────────── 主页面（提案包：徐琴）
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const mainLog = instrument(page);
await page.goto(`${URL_BASE}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });

// 等装配完成：句柄在场 + 有实体（世界此时**停在 tick 0**：脚手架默认先不推进）
await page.waitForFunction(() => {
  const handle = globalThis.__deephealing;
  return Boolean(handle?.scene) && (handle.entityIds?.() ?? []).length > 0;
}, null, { timeout: MAX_WAIT_MS });

// 页面就绪后再放行世界（顺序很关键：先放行会让「事件回填 + 首帧 snapshot」互相踩踏）
const resumeResult = await resumeWorld();

// 观测钩子（**只读**）：记录场景**实际收到**的消息类型与 npc-006 的 schedule 目标，
// 用于「面具态到底由哪条路径驱动」的可复核判定（不改任何行为）。
await page.evaluate(() => {
  globalThis.__n2_seen = [];
  const scene = globalThis.__deephealing.scene;
  const original = scene.apply.bind(scene);
  scene.apply = (message) => {
    const entities = message?.state?.entities ?? [];
    const npc = entities.find((entity) => entity.id === 'npc-006');
    globalThis.__n2_seen.push({
      t: message?.t, tick: message?.tick,
      target: npc?.schedule?.target_entity ?? null,
    });
    return original(message);
  };
});

// 等徐琴的外形装配配置**真的**从内容包取到（`source === 'pack'`）—— 而不是 fallback
await page.waitForFunction((npc) => {
  const report = globalThis.__deephealing?.scene?.appearanceReport?.() ?? [];
  const entry = report.find((item) => item.entity_id === npc);
  return Boolean(entry) && entry.source === 'pack' && entry.parts.length >= 6;
}, NPC, { timeout: MAX_WAIT_MS });

await page.waitForTimeout(1500); // 让渲染循环出几帧
const desktop = await page.evaluate(readScene);
await shot(page, 'n2-desktop-1440x900-daily', '桌面 1440×900 · 日常态（徐琴外形来自内容包）');

// ─────────────────────────────────────────────────────── 390px 窄屏
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(1200);
const narrow = await page.evaluate(readScene);
await shot(page, 'n2-narrow-390x844-daily', '390×844 窄屏 · 日常态');

// ─────────────────────────────────────────────────────── 面具态（驱动 ≥120 tick）
await page.setViewportSize({ width: 1440, height: 900 });
let maskRoute = 'driven_ticks';
let masked = null;
const maskTrace = [];
const maskDeadline = Date.now() + 120000;
let maskFound = false;
while (Date.now() < maskDeadline) {
  const snapshot = await page.evaluate(readScene);
  const entry = snapshot.appearance.find((item) => item.entity_id === NPC) ?? null;
  const seen = snapshot.seen;
  maskTrace.push({
    tick: snapshot.tick, entities: snapshot.entityIds.length,
    state_id: entry?.state_id ?? null,
    snapshots_seen: seen.snapshot_count,
    snapshot_targets: seen.snapshot_targets,
  });
  if (snapshot.tick >= MASK_TICK_MIN && entry?.state_id === 'masked' && snapshot.entityIds.length > 0) {
    maskFound = true;
    break;
  }
  await page.waitForTimeout(2000);
}
if (maskFound) {
  await page.waitForTimeout(1200);
  masked = await page.evaluate(readScene);
  await shot(page, 'n2-desktop-1440x900-masked',
    `桌面 1440×900 · 面具态（**驱动 ≥${MASK_TICK_MIN} tick**，实机日程把徐琴带到 kitchen-01）`);
} else {
  // 等价注入该 state（L-16 允许的另一条路）—— 如实记录用的是哪一种
  maskRoute = 'equivalent_state_injection';
  await page.evaluate((npc) => {
    const projection = globalThis.__deephealing?.liveProjection?.() ?? {};
    const entities = projection.entities ?? projection.state?.entities ?? [];
    const injected = entities.map((entity) => (entity.id === npc
      ? { ...entity, schedule: { ...(entity.schedule ?? {}), state: 'working', target_entity: 'kitchen-01' } }
      : entity));
    globalThis.__deephealing.scene.apply({
      t: 'snapshot', tick: Number(projection.tick ?? 0), state: { entities: injected },
    });
  }, NPC);
  await page.waitForTimeout(1200);
  masked = await page.evaluate(readScene);
  await shot(page, 'n2-desktop-1440x900-masked', '桌面 1440×900 · 面具态（等价注入该 state）');
}

// ─────────────────────────────────────────────────────── 对照图（不注入 appearance ⇒ 通用人形）
// 口径：在**同一个**提案包页面上 `setAppearance(null)` ⇒ 装配配置来源记 `'fallback'`，
// 人物退回 `character.ts` 的确定性通用人形。**这是对照，不是达标证据**。
// （不用第二个 pack：那会让渲染层去请求该 pack 里不存在的 npc-006，制造 404 噪声。）
const controlBefore = await page.evaluate(readScene);
await page.evaluate(() => { globalThis.__deephealing.scene.setAppearance(null); });
await page.waitForTimeout(1200);
const control = await page.evaluate(readScene);
await shot(page, 'n2-control-1440x900-generic-humanoid', '对照：同一页面 setAppearance(null) ⇒ 确定性通用人形（非达标证据）');

const jsErrors = (log) => ({
  console_error: log.console.filter((entry) => entry.type === 'error').length,
  pageerror: log.pageerror.length,
  total: log.console.filter((entry) => entry.type === 'error').length + log.pageerror.length,
});

const document = {
  tag: 'n2-appearance',
  pack: PACK,
  control_pack: CONTROL_PACK,
  npc: NPC,
  resume_result: resumeResult,
  wiring: 'renderer reads the content pack READ-ONLY via ?pack= (world.ts lazy wiring); NOT delivered by the kernel state',
  mask_route: maskRoute,
  mask_tick_min: MASK_TICK_MIN,
  mask_trace: maskTrace,
  shots,
  readings: {
    desktop,
    narrow,
    masked,
    control_before: controlBefore,
    control,
  },
  js_errors: {
    main_page: jsErrors(mainLog),
  },
  console_errors_main: mainLog.console.filter((entry) => entry.type === 'error').slice(0, 10),
  pageerrors_main: mainLog.pageerror.slice(0, 10),
  bad_responses_main: mainLog.bad_responses.slice(0, 10),
};
writeFileSync(join(READBACK, 'n2-browser-accept.json'), `${JSON.stringify(document, null, 2)}\n`);

const summary = {
  js_errors_main: document.js_errors.main_page.total,
  desktop_npc006: desktop.appearance.find((entry) => entry.entity_id === NPC)?.source,
  desktop_state: desktop.appearance.find((entry) => entry.entity_id === NPC)?.state_id,
  desktop_parts: desktop.appearance.find((entry) => entry.entity_id === NPC)?.parts.length,
  desktop_entity_count: desktop.entityIds.length,
  desktop_eyes_source_hex: desktop.character.find((part) => part.part === 'eyes')?.source_hex,
  desktop_eyes_material_hex: desktop.character.find((part) => part.part === 'eyes')?.material_hex,
  masked_state: masked?.appearance.find((entry) => entry.entity_id === NPC)?.state_id,
  masked_parts: masked?.appearance.find((entry) => entry.entity_id === NPC)?.parts.length,
  masked_part_names: masked?.appearance.find((entry) => entry.entity_id === NPC)?.parts.map((part) => part.part),
  mask_route: maskRoute,
  control_sources: control.appearance.map((entry) => entry.source),
  control_parts: control.appearance.map((entry) => entry.parts.length),
  shots: shots.map((item) => item.file),
};
process.stdout.write(`N2_ACCEPT ${JSON.stringify(summary)}\n`);
await browser.close();
