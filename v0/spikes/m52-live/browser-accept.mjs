#!/usr/bin/env node
/**
 * AC-5 实机驱动（spikes/** 脚手架，**非交付面**）：真 Chromium + 真会话层 + 真内核。
 *
 * 一次运行覆盖：
 *   ① 桌面截图（1440×900）② 390×844 窄屏截图 + **横向溢出读数** ③ 录屏（≥15s）
 *   ④ **reload 回读**（同一世界状态下 reload 前后关键字段 diff == 0）+ 负对照（世界推进 ⇒ diff ≠ 0）
 *   ⑤ W11 因果链回读（`__deephealing.traceFor` + 客户端**实际收到**的原始事件）
 *
 * 全部读数落 `<out>/readback/*.json`（判据性文件，不被生成器按名排除）；截图落 `<out>/shots/`，
 * 录屏落 `<out>/rec/`。**交付面一个字节都不写**。
 *
 * 用法（workdir `<ws>`）：
 *   node spikes/m52-live/browser-accept.mjs --url http://127.0.0.1:8790 --tag with \
 *        --out spikes/m52-live --npc npc-006
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

const URL_BASE = option('url', 'http://127.0.0.1:8790');
const TAG = option('tag', 'with');
const OUT = resolve(option('out', 'spikes/m52-live'));
const NPC = option('npc', 'npc-006');
const PACK = option('pack', 'xingfu-xiaoqu-xuqin');
const PREFIX = option('shot-prefix', '');
const READY_TICK = Number(option('ready-tick', 24));
const MIN_SECONDS = Number(option('min-seconds', 17));
const MAX_WAIT_MS = Number(option('max-wait-ms', 90000));

const SHOTS = join(OUT, 'shots');
const REC = join(OUT, 'rec');
const READBACK = join(OUT, 'readback');
for (const dir of [SHOTS, REC, READBACK]) mkdirSync(dir, { recursive: true });

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

const consoleLines = [];
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: REC, size: { width: 1440, height: 900 } },
});
const page = await context.newPage();
page.on('console', (message) => consoleLines.push({ type: message.type(), text: message.text() }));
page.on('pageerror', (error) => consoleLines.push({ type: 'pageerror', text: String(error) }));
// console 里的 404 只报「有一个 404」，不报 URL ⇒ 必须自己记 URL，否则无法定性（M3 的教训）。
const badResponses = [];
page.on('response', (response) => {
  if (response.status() >= 400) badResponses.push({ status: response.status(), url: response.url() });
});
page.on('requestfailed', (request) => {
  badResponses.push({ status: 'failed', url: request.url(), reason: request.failure()?.errorText ?? '' });
});

const started = Date.now();
await page.goto(`${URL_BASE}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
// 起步闸门：页面装配前世界**不推进**（保证页面从 tick 0 起收到全部事件）⇒ 这里放行。
await page.waitForTimeout(800);
await control('resume');

/** 等客户端装配完成 + 世界钟走到 tick 阈值。 */
async function waitForReady() {
  const deadline = Date.now() + MAX_WAIT_MS;
  while (Date.now() < deadline) {
    const reading = await page.evaluate(() => {
      const app = globalThis.__deephealing;
      if (!app) return null;
      return { tick: app.liveReadout().channelTick ? Number(app.liveReadout().channelTick) : 0,
               npcs: app.traceNpcs().length };
    }).catch(() => null);
    if (reading && reading.npcs > 0 && reading.tick >= READY_TICK) return reading;
    await page.waitForTimeout(400);
  }
  return null;
}

/** 世界步进闸门（脚手架端点；只控制是否继续发 step 命令）。 */
async function control(action) {
  return page.evaluate(async (name) => {
    const response = await fetch(`/control/${name}`, { method: 'POST' });
    return response.json();
  }, action).catch(() => null);
}

async function snapshot() {
  return page.evaluate(() => JSON.parse(JSON.stringify(globalThis.__deephealing.acSnapshot())));
}

/**
 * 等**静止**：pause 只是「不再发 step 命令」，在途的那一条 step 仍会完成 ⇒ 直接抓快照会差 1 tick
 * （实测：before 125 事件 vs after 126）。判据要求「同一世界状态下 reload 前后一致」，
 * 所以这里轮询到 `channel_tick + event_count` **连续 N 次不变**才取读数。
 */
async function waitQuiescent(stableCount = 3, intervalMs = 700) {
  let lastKey = null;
  let stable = 0;
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const current = await snapshot();
    const key = `${current.channel_tick}:${current.event_count}`;
    if (key === lastKey) stable += 1;
    else { stable = 0; lastKey = key; }
    if (stable >= stableCount) return current;
    await page.waitForTimeout(intervalMs);
  }
  return snapshot();
}

async function overflowReadings() {
  return page.evaluate(() => {
    const measure = (element) => element === null ? null : {
      scrollWidth: element.scrollWidth, clientWidth: element.clientWidth,
      overflowX: element.scrollWidth - element.clientWidth,
    };
    const hud = document.getElementById('hud');
    const trace = document.getElementById('causal-trace');
    const rect = hud ? hud.getBoundingClientRect() : null;
    return {
      innerWidth: window.innerWidth, innerHeight: window.innerHeight,
      documentElement: measure(document.documentElement),
      body: measure(document.body),
      hud: measure(hud),
      causal_trace: measure(trace),
      hud_rect: rect ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height } : null,
      hud_visible: Boolean(hud && rect && rect.width > 0 && rect.height > 0
        && rect.right <= window.innerWidth + 0.5 && rect.bottom <= window.innerHeight + 0.5),
      hud_text_head: hud ? (hud.innerText || '').slice(0, 400) : null,
      trace_text: trace ? (trace.innerText || '').slice(0, 800) : null,
      write_controls: globalThis.__deephealing.writeControls(),
      viewport: globalThis.__deephealing.viewport(),
    };
  });
}

// ── ① 桌面（1440×900）
const ready = await waitForReady();
const desktopOverflow = await overflowReadings();
await page.screenshot({ path: join(SHOTS, `${PREFIX}desktop-1440x900.png`) });
const desktopShotMs = Date.now() - started;

// ── ② 窄屏（390×844）
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(1200);
const narrowOverflow = await overflowReadings();
await page.screenshot({ path: join(SHOTS, `${PREFIX}narrow-390x844.png`) });
const narrowShotMs = Date.now() - started;
const chainAtNarrow = await page.evaluate((npc) => ({
  chain: JSON.parse(JSON.stringify(globalThis.__deephealing.traceFor(npc))),
  npcs: globalThis.__deephealing.traceNpcs(),
}), NPC);

// ── ④ reload 回读（**先冻结世界步进 + 等静止** ⇒ 同一世界状态下的前后对照）
await control('pause');
const before = await waitQuiescent();
const chainBefore = await page.evaluate((npc) => ({
  chain: JSON.parse(JSON.stringify(globalThis.__deephealing.traceFor(npc))),
  npcs: globalThis.__deephealing.traceNpcs(),
}), NPC);
writeFileSync(join(READBACK, `before-${TAG}.json`), `${JSON.stringify(before, null, 2)}\n`);

await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2000);
const after = await waitQuiescent();
const chainAfter = await page.evaluate((npc) => ({
  chain: JSON.parse(JSON.stringify(globalThis.__deephealing.traceFor(npc))),
  npcs: globalThis.__deephealing.traceNpcs(),
  events: globalThis.__deephealing.receivedEvents().slice(-2500),
}), NPC);
writeFileSync(join(READBACK, `after-${TAG}.json`), `${JSON.stringify(after, null, 2)}\n`);

// ── ④b 负对照：世界**推进** ⇒ 回读必须**不再相等**（判据有牙）
await control('resume');
const resumeTick = after.tick;
const advanceDeadline = Date.now() + 20000;
let advanced = await snapshot();
while (Date.now() < advanceDeadline && advanced.tick <= resumeTick) {
  await page.waitForTimeout(400);
  advanced = await snapshot();
}
await control('pause');
advanced = await waitQuiescent();
writeFileSync(join(READBACK, `after-advanced-${TAG}.json`), `${JSON.stringify(advanced, null, 2)}\n`);

// ── 保持录屏时长（≥ min-seconds）
const remaining = MIN_SECONDS * 1000 - (Date.now() - started);
if (remaining > 0) await page.waitForTimeout(remaining);

const video = page.video();
const videoPath = video ? await video.path() : null;
await context.close();
await browser.close();

const document = {
  tag: TAG, url: URL_BASE, npc: NPC, executable_path: executablePath,
  ready, shots: {
    desktop: `spikes/m52-live/shots/${PREFIX}desktop-1440x900.png`,
    narrow: `spikes/m52-live/shots/${PREFIX}narrow-390x844.png`,
  },
  shot_timing_ms: { desktop: desktopShotMs, narrow: narrowShotMs, total: Date.now() - started },
  recording_seconds_requested: MIN_SECONDS,
  video_path: videoPath,
  overflow: { desktop: desktopOverflow, narrow: narrowOverflow },
  chain_at_narrow: chainAtNarrow,
  chain_before_reload: chainBefore,
  chain_after_reload: chainAfter,
  reload_readback: { before_file: `spikes/m52-live/readback/before-${TAG}.json`,
                     after_file: `spikes/m52-live/readback/after-${TAG}.json`,
                     advanced_file: `spikes/m52-live/readback/after-advanced-${TAG}.json` },
  console_total: consoleLines.length,
  console_errors: consoleLines.filter((line) => line.type === 'error'),
  page_errors: consoleLines.filter((line) => line.type === 'pageerror'),
  bad_responses: badResponses,
};
writeFileSync(join(READBACK, `chain-${TAG}.json`), `${JSON.stringify(document, null, 2)}\n`);
writeFileSync(join(READBACK, `console-${TAG}.jsonl`),
  `${consoleLines.map((line) => JSON.stringify(line)).join('\n')}\n`);
process.stdout.write(`BROWSER_DONE tag=${TAG} video=${videoPath} console=${consoleLines.length} `
  + `errors=${document.console_errors.length} pageerrors=${document.page_errors.length}\n`);
process.exit(0);
