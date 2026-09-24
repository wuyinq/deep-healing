#!/usr/bin/env node
/**
 * 面具态**实机驱动**取证（spikes 脚手架）：真 Chromium + 真会话层 + 真内核 + 真内容包。
 *
 * 与 `browser-accept.mjs` 的差别（**为什么单独一个脚本**）：本脚本**不做**每 2s 的
 * `page.evaluate` 轮询（那会把下行箱压向事件洪流、使周期 snapshot 被挤掉 —— 实测该轮
 * `snapshot_count = 0`），而是只在**页面内**等待 `state_id === 'masked'`，事件面更干净。
 *
 * 输出：`readback/n2-driven-mask.json` + `shots/n2-desktop-1440x900-masked-driven.png`。
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
const URL_BASE = option('url', 'http://127.0.0.1:8806');
const OUT = resolve(option('out', 'spikes/n2-appearance'));
const NPC = option('npc', 'npc-006');
const MIN_TICK = Number(option('mask-tick-min', 130));
const MAX_WAIT_MS = Number(option('max-wait-ms', 150000));

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
  headless: true, executablePath,
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'],
});
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const log = { console_error: 0, pageerror: 0, errors: [], bad_responses: [] };
page.on('console', (message) => {
  if (message.type() === 'error') { log.console_error += 1; log.errors.push(message.text()); }
});
page.on('pageerror', (error) => { log.pageerror += 1; log.errors.push(String(error)); });
page.on('response', (response) => {
  if (response.status() >= 400) log.bad_responses.push({ status: response.status(), url: response.url() });
});

await page.goto(`${URL_BASE}/?pack=xingfu-xiaoqu-xuqin`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => (globalThis.__deephealing?.entityIds?.() ?? []).length > 0, null, { timeout: 60000 });

// 观测钩子（只读）：记录场景收到的消息类型与 npc-006 的 schedule 目标
await page.evaluate((npc) => {
  globalThis.__n2_seen = [];
  const scene = globalThis.__deephealing.scene;
  const original = scene.apply.bind(scene);
  scene.apply = (message) => {
    const entities = message?.state?.entities ?? [];
    const target = entities.find((entity) => entity.id === npc)?.schedule?.target_entity ?? null;
    globalThis.__n2_seen.push({ t: message?.t, tick: message?.tick, target });
    return original(message);
  };
}, NPC);

await fetch(`${URL_BASE}/control/resume`, { method: 'POST' });

let found = false;
try {
  await page.waitForFunction(({ npc, minimum }) => {
    const entry = (globalThis.__deephealing?.scene?.appearanceReport?.() ?? [])
      .find((item) => item.entity_id === npc);
    const tick = Number(globalThis.__deephealing?.liveProjection?.()?.tick ?? 0);
    return Boolean(entry) && entry.state_id === 'masked' && tick >= minimum;
  }, { npc: NPC, minimum: MIN_TICK }, { timeout: MAX_WAIT_MS });
  found = true;
} catch {
  found = false;
}
await page.waitForTimeout(1500);

const reading = await page.evaluate((npc) => {
  const report = globalThis.__deephealing.scene.appearanceReport() ?? [];
  const entry = report.find((item) => item.entity_id === npc) ?? null;
  const seen = globalThis.__n2_seen ?? [];
  const snapshots = seen.filter((item) => item.t === 'snapshot');
  const byType = {};
  for (const item of seen) byType[item.t] = (byType[item.t] ?? 0) + 1;
  return {
    tick: Number(globalThis.__deephealing.liveProjection?.()?.tick ?? 0),
    state_id: entry?.state_id ?? null,
    source: entry?.source ?? null,
    part_count: entry?.parts.length ?? 0,
    part_names: (entry?.parts ?? []).map((part) => part.part),
    source_hex: Object.fromEntries((entry?.parts ?? []).map((part) => [part.part, part.source_hex])),
    material_hex: Object.fromEntries((entry?.parts ?? []).map((part) => [part.part, part.material_hex])),
    messages: { total: seen.length, by_type: byType, snapshot_count: snapshots.length,
                snapshot_targets: [...new Set(snapshots.map((item) => item.target))] },
  };
}, NPC);

const shotFile = join(SHOTS, 'n2-desktop-1440x900-masked-driven.png');
await page.screenshot({ path: shotFile });

const document = {
  tag: 'n2-driven-mask',
  pack: 'xingfu-xiaoqu-xuqin',
  npc: NPC,
  mask_tick_min: MIN_TICK,
  reached_masked_without_injection: found,
  reading,
  js_errors: { console_error: log.console_error, pageerror: log.pageerror, total: log.console_error + log.pageerror },
  errors: log.errors.slice(0, 10),
  bad_responses: log.bad_responses.slice(0, 10),
  shot: 'spikes/n2-appearance/shots/n2-desktop-1440x900-masked-driven.png',
};
writeFileSync(join(READBACK, 'n2-driven-mask.json'), `${JSON.stringify(document, null, 2)}\n`);
process.stdout.write(`N2_DRIVEN_MASK ${JSON.stringify({
  reached: found, tick: reading.tick, state_id: reading.state_id, parts: reading.part_count,
  snapshot_targets: reading.messages.snapshot_targets, js_errors: document.js_errors.total,
})}\n`);
await browser.close();
