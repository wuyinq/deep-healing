#!/usr/bin/env node
/** 诊断：世界推进过程中 npc-006 的 schedule / state_id 读数（spikes 脚手架）。 */
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright';

const URL_BASE = process.argv[2] ?? 'http://127.0.0.1:8802';
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
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error)));
page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });

await page.goto(`${URL_BASE}/?pack=xingfu-xiaoqu-xuqin`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => (globalThis.__deephealing?.entityIds?.() ?? []).length > 0, null, { timeout: 60000 });
const projectionShape = await page.evaluate(() => {
  const projection = globalThis.__deephealing.liveProjection() ?? {};
  return { keys: Object.keys(projection), entityKeys: Object.keys((projection.entities ?? [])[0] ?? {}),
           hasState: Boolean(projection.state), stateKeys: Object.keys(projection.state ?? {}) };
});
await fetch(`${URL_BASE}/control/resume`, { method: 'POST' });

const samples = [];
for (let index = 0; index < 12; index += 1) {
  await page.waitForTimeout(5000);
  samples.push(await page.evaluate(() => {
    const projection = globalThis.__deephealing.liveProjection() ?? {};
    const entities = projection.entities ?? projection.state?.entities ?? [];
    const npc = entities.find((entity) => entity.id === 'npc-006') ?? null;
    const report = globalThis.__deephealing.scene.appearanceReport() ?? [];
    const entry = report.find((item) => item.entity_id === 'npc-006');
    return {
      tick: projection.tick,
      target_entity: npc?.schedule?.target_entity ?? null,
      schedule_state: npc?.schedule?.state ?? null,
      state_id: entry?.state_id ?? null,
      parts: entry?.parts.length ?? 0,
      entities: entities.length,
    };
  }));
}
process.stdout.write(`${JSON.stringify({ projectionShape, samples, errors }, null, 2)}\n`);
await browser.close();
