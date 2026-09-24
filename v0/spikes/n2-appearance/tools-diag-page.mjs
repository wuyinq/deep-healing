#!/usr/bin/env node
/** 诊断：加载提案包页面，dump console / __deephealing / 网络失败（spikes 脚手架）。 */
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright';

const URL_BASE = process.argv[2] ?? 'http://127.0.0.1:8799';
const executablePath = [
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1234',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
].find((candidate) => existsSync(candidate));

const browser = await chromium.launch({
  headless: true, executablePath,
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'],
});
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const log = [];
page.on('console', (message) => log.push(`console.${message.type()}: ${message.text()}`));
page.on('pageerror', (error) => log.push(`pageerror: ${String(error)}`));
page.on('response', (response) => { if (response.status() >= 400) log.push(`http ${response.status()} ${response.url()}`); });
page.on('requestfailed', (request) => log.push(`reqfail ${request.url()} ${request.failure()?.errorText}`));
page.on('websocket', (socket) => log.push(`ws ${socket.url()}`));

await page.goto(`${URL_BASE}/?pack=xingfu-xiaoqu-xuqin`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(20000);
const state = await page.evaluate(() => ({
  hasHandle: Boolean(globalThis.__deephealing),
  keys: globalThis.__deephealing ? Object.keys(globalThis.__deephealing) : [],
  entityIds: globalThis.__deephealing?.entityIds?.() ?? null,
  projection: (() => {
    const projection = globalThis.__deephealing?.liveProjection?.();
    return projection ? { tick: projection.tick, entities: (projection.entities ?? []).length, seed: projection.seed } : null;
  })(),
  clientPack: globalThis.__deephealing?.client?.districtPackId ?? null,
  canvas: (() => { const c = document.getElementById('scene'); return c ? { w: c.width, h: c.height, cw: c.clientWidth, ch: c.clientHeight } : null; })(),
}));
process.stdout.write(`${JSON.stringify({ state, log: log.slice(0, 40) }, null, 2)}\n`);
await browser.close();
