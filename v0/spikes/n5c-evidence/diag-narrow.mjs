#!/usr/bin/env node
/** 窄屏 390×844 启动失败**根因诊断**（一次性；不进交付面）。 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKSPACE = resolve(HERE, '..', '..');
const PORT = 8852;
const OUT = join(HERE, 'runtime', 'narrow-diag');
mkdirSync(OUT, { recursive: true });

const host = spawn('node', [
  join(HERE, 'serve-live.mjs'), '--tag', 'narrow-diag', '--port', String(PORT), '--pack', 'xingfu-xiaoqu-xuqin',
  '--out', OUT, '--runtime', join(HERE, 'runtime', 'narrow-diag-bridge'),
  '--web', join(WORKSPACE, '.build', 'web'), '--source', join(WORKSPACE, '02_source'),
  '--tick-ms', '50', '--run-seconds', '120', '--start-paused', 'false',
], { stdio: ['ignore', 'pipe', 'pipe'] });
await new Promise((ready, reject) => {
  const timer = setTimeout(() => reject(new Error('SERVE_READY timeout')), 60000);
  host.stdout.on('data', (chunk) => {
    if (String(chunk).includes('SERVE_READY')) { clearTimeout(timer); ready(); }
  });
});

const CHROMIUM = [
  process.env.PW_CHROMIUM,
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1234',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
].filter(Boolean).find((candidate) => existsSync(candidate));

const browser = await chromium.launch({
  headless: true, executablePath: CHROMIUM,
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'],
});
// 复现真实取证顺序：先开 1440×900 主页面（它会跑渲染循环），再开窄屏页
const main = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await main.goto(`http://127.0.0.1:${PORT}/?pack=xingfu-xiaoqu-xuqin`, { waitUntil: 'domcontentloaded' });
let mainBooted = true;
try { await main.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 60000 }); }
catch { mainBooted = false; }
await main.waitForTimeout(5000);
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
const logs = [];
const bad = [];
page.on('console', (msg) => logs.push(`${msg.type()}: ${msg.text()}`));
page.on('pageerror', (error) => logs.push(`pageerror: ${String(error)}`));
page.on('requestfailed', (request) => bad.push(`FAILED ${request.url()} ${request.failure()?.errorText}`));
page.on('response', (response) => { if (response.status() >= 400) bad.push(`${response.status()} ${response.url()}`); });
await page.goto(`http://127.0.0.1:${PORT}/?pack=xingfu-xiaoqu-xuqin`, { waitUntil: 'domcontentloaded' });
let booted = true;
try {
  await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 45000 });
} catch { booted = false; }
await page.waitForTimeout(2000);
const dom = await page.evaluate(() => ({
  title: document.title, body_len: document.body.innerText.trim().length,
  has_scene: Boolean(document.getElementById('scene')),
  has_player_ui: Boolean(document.getElementById('player-ui')),
  has_credits: Boolean(document.getElementById('credits')),
  scroll: { w: document.documentElement.scrollWidth, c: document.documentElement.clientWidth },
}));
writeFileSync(join(HERE, 'readback', 'narrow-diag.json'),
  `${JSON.stringify({ main_booted: mainBooted, booted, dom, logs: logs.slice(-25), bad: bad.slice(0, 25) }, null, 2)}\n`);
process.stdout.write(`NARROW_DIAG ${JSON.stringify({ main_booted: mainBooted, booted, dom, logs: logs.slice(-12), bad: bad.slice(0, 12) })}\n`);
await browser.close();
host.kill('SIGKILL');
process.exit(0);
