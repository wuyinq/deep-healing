#!/usr/bin/env node
/**
 * F-1 辅助（N2-r2 / spike 专用）：抓 `#scene` 画布与 `#hud` 面板的**布局矩形**。
 * 供像素 diff 脚本判定「差异落在 3D 视口区，而不是只在 HUD 面板内」。
 *
 * 用法：node spikes/n2-appearance/n2-ui-rects.mjs --url http://127.0.0.1:8811 --out spikes/n2-appearance/readback
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
const OUT = resolve(option('out', 'spikes/n2-appearance/readback'));
const PACK = option('pack', 'xingfu-xiaoqu-xuqin');

const executablePath = [
  process.env.PW_CHROMIUM,
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1234',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
].filter(Boolean).find((candidate) => existsSync(candidate));

const browser = await chromium.launch({ headless: true, executablePath,
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
await page.goto(`${URL_BASE}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2500);

const rects = await page.evaluate(() => {
  const rectOf = (id) => {
    const element = document.getElementById(id);
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return { x: Math.round(rect.x), y: Math.round(rect.y),
      width: Math.round(rect.width), height: Math.round(rect.height) };
  };
  return { viewport: { width: window.innerWidth, height: window.innerHeight },
    canvas: rectOf('scene'), hud: rectOf('hud') };
});
mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, 'n2-ui-rects.json'), `${JSON.stringify(rects, null, 2)}\n`);
process.stdout.write(`${JSON.stringify(rects)}\n`);
await browser.close();
