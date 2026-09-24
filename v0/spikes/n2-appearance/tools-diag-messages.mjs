#!/usr/bin/env node
/** 诊断：捕获场景**实际收到**的消息（t/tick/entities/schedule），判定 snapshot 是否带 schedule。 */
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright';

const URL_BASE = process.argv[2] ?? 'http://127.0.0.1:8804';
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
await page.goto(`${URL_BASE}/?pack=xingfu-xiaoqu-xuqin`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => (globalThis.__deephealing?.entityIds?.() ?? []).length > 0, null, { timeout: 60000 });

// 挂钩：记录场景**实际**收到的每条消息的关键字段（只读观测，不改行为）
await page.evaluate(() => {
  globalThis.__n2_seen = [];
  const scene = globalThis.__deephealing.scene;
  const original = scene.apply.bind(scene);
  scene.apply = (message) => {
    const entities = message?.state?.entities ?? [];
    const npc = entities.find((entity) => entity.id === 'npc-006');
    globalThis.__n2_seen.push({
      t: message?.t, tick: message?.tick, seq: message?.seq,
      entities: entities.length,
      target: npc?.schedule?.target_entity ?? null,
      ops: Array.isArray(message?.ops) ? message.ops.length : null,
      op_components: Array.isArray(message?.ops) ? [...new Set(message.ops.map((op) => op.component))] : null,
    });
    return original(message);
  };
});
await fetch(`${URL_BASE}/control/resume`, { method: 'POST' });
await page.waitForTimeout(45000);
const result = await page.evaluate(() => {
  const seen = globalThis.__n2_seen ?? [];
  const byType = {};
  for (const item of seen) byType[item.t] = (byType[item.t] ?? 0) + 1;
  const snapshots = seen.filter((item) => item.t === 'snapshot');
  return {
    total: seen.length, by_type: byType,
    first: seen.slice(0, 4), last: seen.slice(-6),
    snapshot_count: snapshots.length,
    snapshot_targets: [...new Set(snapshots.map((item) => item.target))],
    snapshot_ticks: snapshots.map((item) => item.tick).slice(0, 12),
    current_state_id: (globalThis.__deephealing.scene.appearanceReport() ?? [])
      .find((entry) => entry.entity_id === 'npc-006')?.state_id ?? null,
  };
});
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
await browser.close();
