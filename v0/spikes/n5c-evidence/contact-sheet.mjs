#!/usr/bin/env node
/**
 * AC-A-2a · 把 `motion-sheet-<tag>-f1..f8.png`（**真浏览器逐帧产出**）拼成一张联系表
 * `motion-sheet-<tag>.png`（4×2 网格）。拼版本身由**真浏览器**渲染。
 *
 * N5-C r2 / FIX-2 修复（对应 sentinel M-① 与 raven M-③ 的同一读数）：
 *   r1 的缺陷：用 `page.setContent(...)` 建页面 ⇒ 文档源 = `about:blank`，
 *   其中内嵌的 `<img src="file://…">` 被 Chromium **拒绝加载**（非 `file:` 文档不得加载 `file://` 子资源），
 *   且只等 600 ms 就截图 ⇒ 输出 8 格全是「破图占位符」的空壳（17,303 B）。
 *   现在：① 把版式写成**真 HTML 文件**并用 `page.goto(pathToFileURL(html))` 打开（文档源 = `file:`）；
 *         ② 截图前**等待 `img.complete ∧ naturalWidth > 0`**；
 *         ③ 逐格核对**实际解码尺寸**，任一格未解码 ⇒ 非零退出（失败要响，不静默产空壳）。
 */
import { existsSync, mkdirSync, readdirSync, writeFileSync, copyFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKSPACE = resolve(HERE, '..', '..');
const READBACK = join(HERE, 'readback');
const READBACK_SHOTS = join(READBACK, 'shots');
const FROZEN_SHOTS = join(WORKSPACE, 'spikes', 'n5-asset', 'shots');
const HTML_DIR = join(HERE, 'runtime', 'contact-sheet');
const TAG = process.argv[2];
if (!TAG) { process.stderr.write('usage: node contact-sheet.mjs <tag>\n'); process.exit(2); }

const frames = readdirSync(READBACK_SHOTS)
  .filter((file) => file.startsWith(`motion-sheet-${TAG}-f`) && file.endsWith('.png'))
  .sort((left, right) => Number(left.match(/-f(\d+)\.png$/)[1]) - Number(right.match(/-f(\d+)\.png$/)[1]));
if (frames.length !== 8) { process.stderr.write(`expected 8 frames, got ${frames.length}\n`); process.exit(1); }

const CHROMIUM = [
  process.env.PW_CHROMIUM,
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1248',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean).find((candidate) => existsSync(candidate));

const cells = frames.map((file) => `<figure><img src="${pathToFileURL(join(READBACK_SHOTS, file)).href}">`
  + `<figcaption>${file.match(/-f(\d+)\.png$/)[1]}</figcaption></figure>`).join('');
mkdirSync(HTML_DIR, { recursive: true });
const htmlFile = join(HTML_DIR, `contact-sheet-${TAG}.html`);
writeFileSync(htmlFile, `<!doctype html><meta charset="utf-8"><style>
  html,body{margin:0;background:#111;color:#ddd;font:12px -apple-system,sans-serif}
  .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;padding:4px}
  figure{margin:0}img{width:100%;display:block}figcaption{padding:2px 4px}
  h1{font-size:13px;margin:6px 8px;font-weight:500}
</style><h1>motion-sheet · ${TAG} · 8 帧（真浏览器 1440×900 逐帧）</h1>
<div class="grid">${cells}</div>`);

const browser = await chromium.launch({ headless: true, executablePath: CHROMIUM,
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader'] });
// 视口 2880×1800 ⇒ 4 列网格每格 ~716 px 宽（= 原帧 1440×900 的一半）⇒ 每格像素可判读，
// 产物落在 MB 量级（r1 的 17 KB 空壳就是这个视口 + about:blank 加载失败共同造成的）。
const page = await browser.newPage({ viewport: { width: 2880, height: 1800 } });
await page.goto(pathToFileURL(htmlFile).href, { waitUntil: 'load' });
await page.waitForFunction(() => [...document.images].every((img) => img.complete && img.naturalWidth > 0),
  null, { timeout: 30000 });
const decoded = await page.evaluate(() => [...document.images].map((img) => ({
  src: img.currentSrc.split('/').pop(), natural_width: img.naturalWidth, natural_height: img.naturalHeight,
  rendered_width: Math.round(img.getBoundingClientRect().width),
})));
const out = join(READBACK_SHOTS, `motion-sheet-${TAG}.png`);
await page.screenshot({ path: out, fullPage: true });
copyFileSync(out, join(FROZEN_SHOTS, `motion-sheet-${TAG}.png`));
await browser.close();

const bytes = (await import('node:fs')).statSync(out).size;
const allDecoded = decoded.length === 8 && decoded.every((cell) => cell.natural_width > 0);
const readout = {
  task: 'contact-sheet', at_epoch: Math.floor(Date.now() / 1000), n: decoded.length,
  tag: TAG, html_document_source: pathToFileURL(htmlFile).href,
  node_version: process.version,
  browser_binary: CHROMIUM ?? null,
  tree_head: spawnSync('git', ['-C', WORKSPACE, 'rev-parse', 'HEAD']).stdout.toString().trim(),
  cells: decoded, contact_sheet_path: out, contact_sheet_bytes: bytes,
  all_cells_decoded: allDecoded,
};
writeFileSync(join(READBACK, `contact-sheet-${TAG}.json`), `${JSON.stringify(readout, null, 2)}\n`);
process.stdout.write(`CONTACT_SHEET ${JSON.stringify({ out, frames: frames.length, bytes,
  all_cells_decoded: allDecoded, node: process.version })}\n`);
process.exit(allDecoded && bytes >= 1000000 ? 0 : 1);
