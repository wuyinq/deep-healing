#!/usr/bin/env node
/**
 * M4 真浏览器验收驱动（AC-M4-11 ①②③；AC-M4-10①②）——**真 Chromium + 真会话层 + 真只读实时通道**。
 *
 * 运行：
 *   node spikes/s16-liveworld/browser-accept-live.mjs \
 *        --url http://127.0.0.1:8791 --out spikes/s16-liveworld/logs --tag live
 *
 * 覆盖：
 *   - 两档视口（桌面 1440×900 / 窄屏 390×844）各有截图（落 `logs/*.png`）；
 *   - **实时通道读数**：通道 tick / 世界钟 / 浏览器墙上钟（UTC+8）/ observers / state_hash；
 *   - 真交互：切换读法（真点击）→ 截图；reload 后**回读**（通道 tick 必须前进，不得回 0）；
 *   - console **全量**采集（逐条落 `console-<tag>.jsonl`，不是「无报错」四个字）；
 *   - `listWriteControls()` 在真浏览器里仍必须为空（不得新增写控件）；
 *   - 像素读数（`gl.readPixels`）：HUD 外非背景像素占比 / 非背景像素饱和分布（供氛围判据用）。
 *
 * 输出：`logs/browser-live-<tag>.json` + `logs/console-<tag>.jsonl` + `logs/<tag>-<viewport>-*.png`。
 * 硬边界：本脚本在 `spikes/**`，**不是交付面**；交付面一个字节都不写。
 */

import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';

import { chromium } from 'playwright';

import { pixelStats, syntheticSaturatedStats } from './png_stats.mjs';

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};

const URL_BASE = option('url', 'http://127.0.0.1:8791');
const OUT = resolve(option('out', 'spikes/s16-liveworld/logs'));
const TAG = option('tag', 'live');
const HEADFUL = args.includes('--headful');

mkdirSync(OUT, { recursive: true });

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'narrow', width: 390, height: 844 },
];

const browser = await chromium.launch({
  headless: !HEADFUL,
  executablePath: [
    process.env.PW_CHROMIUM,
    join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
      'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
    join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1234',
      'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
  ].filter(Boolean).find((candidate) => existsSync(candidate)),
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'],
});

const consoleLines = [];
const pageErrors = [];
const badResponses = [];
const results = { tag: TAG, url: URL_BASE, viewports: [], shots: [] };

/** 反例对照（D-M4-10 / AC-M4-11④）：合成一块**全饱和红**缓冲 ⇒ 同一统计器必须报超限。 */

for (const viewport of VIEWPORTS) {
  const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } });
  const page = await context.newPage();
  page.on('console', (message) => consoleLines.push({ viewport: viewport.name, type: message.type(), text: message.text() }));
  page.on('pageerror', (error) => pageErrors.push({ viewport: viewport.name, error: String(error) }));
  page.on('response', (response) => {
    if (response.status() >= 400) badResponses.push({ viewport: viewport.name, status: response.status(), url: response.url() });
  });

  const record = { viewport: viewport.name, ...viewport };
  const loadedAt = Date.now();
  await page.goto(`${URL_BASE}/`, { waitUntil: 'load' });
  await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 30000 });
  await page.waitForFunction(() => globalThis.__deephealing.client.sessionId !== '', null, { timeout: 30000 });
  await page.waitForFunction(() => globalThis.__deephealing.entityIds().length > 0, null, { timeout: 20000 });
  record.first_frame_ms = Date.now() - loadedAt;
  record.entities = await page.evaluate(() => globalThis.__deephealing.entityIds().length);

  // ---- 实时通道：等它真的连上并有读数
  await page.waitForFunction(() => globalThis.__deephealing.liveReadout().connected === 'true', null, { timeout: 30000 });
  await page.waitForFunction(() => Number(globalThis.__deephealing.liveReadout().channelTick ?? 0) > 0, null, { timeout: 30000 });
  const liveBefore = await page.evaluate(() => globalThis.__deephealing.liveReadout());
  record.live_readout_at_connect = liveBefore;
  record.live_readout_text = await page.textContent('#live-readout');
  record.live_projection_tick = await page.evaluate(() => globalThis.__deephealing.liveProjection()?.tick ?? null);
  record.live_projection_entities = await page.evaluate(
    () => (globalThis.__deephealing.liveProjection()?.entities ?? []).length);

  // ---- 通道读数必须**继续前进**（不是冻结帧）
  await page.waitForTimeout(2500);
  record.live_readout_after_wait = await page.evaluate(() => globalThis.__deephealing.liveReadout());

  // ---- 只读面：真浏览器里枚举控件（`listWriteControls()` 必须仍为空）
  record.observe_panel_write_controls = await page.evaluate(() => globalThis.__deephealing.writeControls());
  record.controls_observe_mode = await page.evaluate(() => {
    const selector = 'button, input, textarea, select, form, [contenteditable="true"]';
    return [...document.querySelectorAll(selector)].map((element) => ({
      tag: element.tagName.toLowerCase(),
      id: element.id || null,
      text: (element.textContent || '').trim().slice(0, 40),
      in_hud: Boolean(document.getElementById('hud')?.contains(element)),
    }));
  });

  // ---- 像素读数（氛围判据的取数面之一）：**从真实截图解码**（HUD 矩形按 devicePixelRatio 剔除）
  record.device_pixel_ratio = await page.evaluate(() => window.devicePixelRatio);
  const hudRect = await page.evaluate(() => {
    const rect = document.getElementById('hud').getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  });
  record.hud_rect_css = hudRect;
  const exclude = {
    x: Math.max(0, Math.floor(hudRect.x * record.device_pixel_ratio)),
    y: Math.max(0, Math.floor(hudRect.y * record.device_pixel_ratio)),
    width: Math.ceil(hudRect.width * record.device_pixel_ratio),
    height: Math.ceil(hudRect.height * record.device_pixel_ratio),
  };
  record.synthetic_pixel_stats = syntheticSaturatedStats();

  // ---- 真交互：切换读法 ⇒ 截图
  const shot = async (reading) => {
    const path = join(OUT, `${TAG}-${viewport.name}-${reading}.png`);
    await page.screenshot({ path });
    results.shots.push(path);
    return path;
  };
  const surfaceShot = await shot('surface');
  record.pixel_stats = pixelStats(surfaceShot, { exclude });
  record.reading_initial = await page.evaluate(() => globalThis.__deephealing.reading());
  await page.click('#toggle-reading');
  await page.waitForFunction(() => globalThis.__deephealing.reading() === 'underneath', null, { timeout: 5000 });
  record.reading_after_click = await page.evaluate(() => globalThis.__deephealing.reading());
  const underneathShot = await shot('underneath');
  record.pixel_stats_underneath = pixelStats(underneathShot, { exclude });
  await page.click('#toggle-reading');
  await page.waitForFunction(() => globalThis.__deephealing.reading() === 'surface', null, { timeout: 5000 });

  // ---- reload 后回读：通道读数必须回到**当前**时刻（不是 0，也不是「上次的冻结帧」）
  const tickBeforeReload = Number(liveBefore.channelTick ?? 0);
  await page.reload({ waitUntil: 'load' });
  await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 30000 });
  await page.waitForFunction(() => globalThis.__deephealing.liveReadout().connected === 'true', null, { timeout: 30000 });
  await page.waitForFunction(() => Number(globalThis.__deephealing.liveReadout().channelTick ?? 0) > 0, null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  record.reload = {
    channel_tick_before: tickBeforeReload,
    live_readout_after: await page.evaluate(() => globalThis.__deephealing.liveReadout()),
    entities_after: await page.evaluate(() => globalThis.__deephealing.entityIds().length),
    write_controls_after: await page.evaluate(() => globalThis.__deephealing.writeControls()),
  };
  await shot('after-reload');

  results.viewports.push(record);
  await context.close();
}

results.console = { total: consoleLines.length, errors: consoleLines.filter((line) => line.type === 'error').length };
results.page_errors = pageErrors;
results.bad_responses = badResponses;
writeFileSync(join(OUT, `console-${TAG}.jsonl`), `${consoleLines.map((line) => JSON.stringify(line)).join('\n')}\n`);
writeFileSync(join(OUT, `browser-live-${TAG}.json`), `${JSON.stringify(results, null, 2)}\n`);

await browser.close();
process.stdout.write(`${JSON.stringify({
  tag: TAG,
  shots: results.shots.length,
  console_total: results.console.total,
  console_errors: results.console.errors,
  console_sample: consoleLines.slice(0, 6).map((line) => `${line.viewport}/${line.type}: ${line.text}`.slice(0, 120)),
  page_errors: pageErrors.length,
  bad_responses: badResponses,
  viewports: results.viewports.map((entry) => ({
    viewport: entry.viewport,
    channel_tick_at_connect: entry.live_readout_at_connect.channelTick,
    world_clock: entry.live_readout_at_connect.worldClock,
    wall_clock: entry.live_readout_at_connect.wallClock,
    observers: entry.live_readout_at_connect.observers,
    channel_tick_after_wait: entry.live_readout_after_wait.channelTick,
    channel_tick_after_reload: entry.reload.live_readout_after.channelTick,
    write_controls: entry.observe_panel_write_controls,
    non_background_ratio: entry.pixel_stats?.non_background_ratio,
    saturation_max: entry.pixel_stats?.saturation_pct?.max,
  })),
})}\n`);
process.exit(0);
