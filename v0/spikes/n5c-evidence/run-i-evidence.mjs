#!/usr/bin/env node
/**
 * 补充机读锚（真浏览器 1440×900）：
 *   - `AC-I-4`：WebGL 不可用 ⇒ **用户可见提示元素** `#webgl-unavailable-notice` 存在 + 文案非空 + 无未捕获异常；
 *   - `AC-I-1` / `AC-I-2`：loader 注入 `null` ⇒ `bindingReport().degradations` 非空、`characterReport()` 结构完整、
 *     回落盒体 `glb_loaded === false`；
 *   - `AC-A-8a` 回落批次：`setAppearance(null)` 后 `appearanceReport()` 的槽位来源；
 *   - `AC-A-3⑤/⑥`、`AC-H-5/H-6`：`buildingReport()` / `structureReport()` / `postfxReport()` / `entityIds()` 原始读数。
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKSPACE = resolve(HERE, '..', '..');
const SOURCE = join(WORKSPACE, '02_source');
const WEB = join(WORKSPACE, '.build', 'web');
const PACK = 'xingfu-xiaoqu-xuqin';
const PORT = 8850;
const OUT = join(HERE, 'runtime', 'i-evidence', 'out');
const READBACK = join(HERE, 'readback');
mkdirSync(OUT, { recursive: true });

const CHROMIUM = [
  process.env.PW_CHROMIUM,
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1234',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
].filter(Boolean).find((candidate) => existsSync(candidate));

const host = spawn('node', [
  join(HERE, 'serve-live.mjs'), '--tag', 'i-evidence', '--port', String(PORT), '--pack', PACK,
  '--out', OUT, '--runtime', join(HERE, 'runtime', 'i-evidence', 'bridge'),
  '--web', WEB, '--source', SOURCE, '--tick-ms', '100', '--snapshot-every', '1', '--seed', '20260921',
  '--run-seconds', '300', '--start-paused', 'false', '--memory-chain',
], { stdio: ['ignore', 'pipe', 'pipe'] });
const killHost = () => { try { host.kill('SIGKILL'); } catch { /* 已退出 */ } };
process.on('exit', killHost);
await new Promise((ready, reject) => {
  const timer = setTimeout(() => reject(new Error('SERVE_READY timeout')), 90000);
  host.stdout.on('data', (chunk) => { if (String(chunk).includes('SERVE_READY')) { clearTimeout(timer); ready(); } });
});

const browser = await chromium.launch({ headless: true, executablePath: CHROMIUM,
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'] });

// ── 正常世界（I-1/I-2/A-3⑤⑥/H-5/H-6）
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(`http://127.0.0.1:${PORT}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 90000 });
await page.waitForTimeout(8000);
const sceneApi = await page.evaluate(() => Object.keys(globalThis.__deephealing.scene ?? {}));
const normal = await page.evaluate(() => {
  const scene = globalThis.__deephealing.scene;
  const call = (name) => { try { return typeof scene[name] === 'function' ? scene[name]() : null; } catch (error) { return { error: String(error) }; } };
  return {
    entity_ids: globalThis.__deephealing.entityIds(),
    binding: call('bindingReport'), characterInstance: call('characterInstanceReport'),
    character: call('characterReport'),
    appearance: call('appearanceReport'), building: call('buildingReport'),
    structure: call('structureReport'), postfx: call('postfxReport'),
    material: call('materialReport'),
    geometry: globalThis.__deephealing.geometry(),
    ac: globalThis.__deephealing.acSnapshot(),
  };
});
// I-1/I-2：注入 `null` loader ⇒ 显式降级 + 回落盒体
const injected = await page.evaluate(() => {
  const scene = globalThis.__deephealing.scene;
  scene.setCharacterLoader(null);
  return { loader_injected: 'null' };
});
await page.waitForTimeout(3000);
const loaderNull = await page.evaluate(() => {
  const scene = globalThis.__deephealing.scene;
  const call = (name) => { try { return typeof scene[name] === 'function' ? scene[name]() : null; } catch (error) { return { error: String(error) }; } };
  const instances = call('characterInstanceReport');
  return {
    binding_degradations: call('bindingReport')?.degradations ?? null,
    instance_count: Array.isArray(instances) ? instances.length : null,
    instances,
    character_count: (() => { const rows = call('characterReport'); return Array.isArray(rows) ? rows.length : null; })(),
    character_fields_complete: (() => {
      const rows = call('characterReport');
      if (!Array.isArray(rows) || rows.length === 0) return false;
      return rows.every((row) => ['entity_id', 'part', 'size', 'local_offset', 'vertex_count'].every((key) => key in row));
    })(),
    visibility: call('characterVisibilityReport'),
  };
});
// A-8a 回落批次：`setAppearance(null)`
await page.evaluate(() => globalThis.__deephealing.scene.setAppearance(null));
await page.waitForTimeout(1200);
const appearanceNull = await page.evaluate(() => {
  const scene = globalThis.__deephealing.scene;
  const call = (name) => { try { return typeof scene[name] === 'function' ? scene[name]() : null; } catch (error) { return { error: String(error) }; } };
  return { appearance: call('appearanceReport'), character: call('characterReport') };
});
await page.close();

// ── I-4：禁 WebGL
const noWebgl = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const noWebglErrors = [];
noWebgl.on('pageerror', (error) => noWebglErrors.push(String(error)));
await noWebgl.addInitScript(() => {
  const original = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function getContext(type, ...rest) {
    if (String(type).includes('webgl')) return null;
    return original.call(this, type, ...rest);
  };
});
await noWebgl.goto(`http://127.0.0.1:${PORT}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
await noWebgl.waitForTimeout(8000);
const noWebglReading = await noWebgl.evaluate(() => {
  const notice = document.getElementById('webgl-unavailable-notice');
  const scene = globalThis.__deephealing?.scene;
  return {
    app_booted: Boolean(globalThis.__deephealing),
    notice_id_present: Boolean(notice),
    notice_text: notice?.textContent?.trim() ?? null,
    notice_display: notice ? getComputedStyle(notice).display : null,
    notice_in_viewport: (() => {
      if (!notice) return null;
      const box = notice.getBoundingClientRect();
      return box.width > 0 && box.height > 0 && box.top >= 0 && box.top <= window.innerHeight;
    })(),
    body_text_len: document.body.innerText.trim().length,
    degradations: (() => { try { return scene?.bindingReport?.()?.degradations ?? null; } catch { return null; } })(),
  };
});
const shot = join(READBACK, 'shots', 'webgl-disabled-notice-1440x900.png');
await noWebgl.screenshot({ path: shot });
await noWebgl.close();
await browser.close();
killHost();

const reading = {
  task: 'i-evidence', at_epoch: Math.floor(Date.now() / 1000),
  scene_api_keys: sceneApi,
  normal_world: normal,
  loader_injected: injected, loader_null: loaderNull,
  appearance_null: appearanceNull,
  webgl_unavailable: { ...noWebglReading, page_errors: noWebglErrors.slice(0, 5), shot },
};
writeFileSync(join(READBACK, 'i-evidence-reading.json'), `${JSON.stringify(reading, null, 2)}\n`);
process.stdout.write(`I_EVIDENCE ${JSON.stringify({
  entities: normal.entity_ids, instances: (normal.characterInstance ?? []).length,
  loader_null_instances: loaderNull.instance_count,
  loader_null_degradations: (loaderNull.binding_degradations ?? []).length,
  notice: noWebglReading.notice_id_present, notice_text: (noWebglReading.notice_text ?? '').slice(0, 30),
  errors: noWebglErrors.length })}\n`);
process.exit(0);
