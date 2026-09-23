#!/usr/bin/env node
/**
 * 诊断工具（spikes/** 脚手架）：列出页面加载/重载期间所有 HTTP >= 400 响应与失败请求。
 * 用途：AC-5 的 console 判据要求「零 error」——出现 404 时必须能指名道姓，而不是只记一个数。
 *
 * 用法：node spikes/m52-live/tools/http404-check.mjs <base-url> <pack-id>
 */
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

import { chromium } from 'playwright';

const URL_BASE = process.argv[2] ?? 'http://127.0.0.1:8802';
const PACK = process.argv[3] ?? 'xingfu-xiaoqu-xuqin';
const executablePath = [
  process.env.PW_CHROMIUM,
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
].filter(Boolean).find((candidate) => existsSync(candidate));

const browser = await chromium.launch({
  headless: true, executablePath,
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
page.on('response', (response) => {
  if (response.status() >= 400) process.stdout.write(`HTTP ${response.status()} ${response.url()}\n`);
});
page.on('requestfailed', (request) => {
  process.stdout.write(`FAILED ${request.url()} ${request.failure()?.errorText ?? ''}\n`);
});
await page.goto(`${URL_BASE}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(6000);
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForTimeout(5000);
await browser.close();
process.stdout.write('HTTP404_CHECK_DONE\n');
