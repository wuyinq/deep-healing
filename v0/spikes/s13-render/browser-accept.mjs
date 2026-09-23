#!/usr/bin/env node
/**
 * F4 真浏览器验收驱动（R2 / CRITICAL-4）：**真 Chromium + 真会话层 + 真静态服务**。
 *
 * 运行：
 *   node spikes/s13-render/browser-accept.mjs --url http://127.0.0.1:8790 \
 *        --out spikes/s13-render/logs --tag pristine
 *
 * 覆盖：
 *   - 两档视口（桌面 1440×900 / 窄屏 390×844）× 两态读法（surface/underneath）⇒ ≥4 张截图；
 *   - 真交互：连接、切换读法、切换模式、观察面板、尝试干预（填输入 + 点「委托」）；
 *   - **reload 后回读**（模式/读法/tick/事件流条数/会话 id）；
 *   - console 全量采集（逐条落盘，零 error / 零 pageerror 作为判据）；
 *   - AC-M3-4 ①：**真浏览器里枚举 UI 控件清单**（含 `writeControls()` 与文档级控件表）；
 *   - AC-M3-4 ②：写接口被拒的真跑读数（客户端本地拒 + 服务端 WS 上行拒）；
 *   - AC-M3-8③：真浏览器两态几何读数（`geometryFor('surface')` vs `geometryFor('underneath')`）。
 *
 * 输出：`<out>/browser-accept-<tag>.json`（逐条原始读数）+ `<out>/console-<tag>.jsonl`。
 * 判定在 `spikes/s13-render/negctl/f4_browser_negctl.py`（同一套读数上判，负例才可比）。
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
const OUT = resolve(option('out', 'spikes/s13-render/logs'));
const TAG = option('tag', 'pristine');
const HEADFUL = args.includes('--headful');

mkdirSync(OUT, { recursive: true });

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'narrow', width: 390, height: 844 },
];

const browser = await chromium.launch({
  headless: !HEADFUL,
  // 本机缓存的是 chromium-1234（Playwright 1.63 默认找 -1243，未下载）⇒ 显式指向已缓存的可执行文件。
  // 缓存里两个都试：完整 Chromium 优先（WebGL/SwiftShader 支持更完整），其次 headless shell。
  executablePath: [
    process.env.PW_CHROMIUM,
    join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
      'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
    join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1234',
      'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
  ].filter(Boolean).find((candidate) => existsSync(candidate)),
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'],
});

const consoleLines = [];
const pageErrors = [];
const badResponses = [];
const results = { tag: TAG, url: URL_BASE, viewports: [], shots: [] };

for (const viewport of VIEWPORTS) {
  const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } });
  const page = await context.newPage();
  page.on('console', (message) => consoleLines.push({ viewport: viewport.name, type: message.type(), text: message.text() }));
  page.on('pageerror', (error) => pageErrors.push({ viewport: viewport.name, error: String(error) }));
  page.on('response', (response) => {
    if (response.status() >= 400) badResponses.push({ viewport: viewport.name, status: response.status(), url: response.url() });
  });

  const record = { viewport: viewport.name, ...viewport };
  const loadedAt = Date.now();
  await page.goto(`${URL_BASE}/`, { waitUntil: 'load' });
  await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 30000 });
  await page.waitForFunction(() => globalThis.__deephealing.client.sessionId !== '', null, { timeout: 30000 });
  // **首帧补齐判据**（R2 / F4 实测缺陷的回归）：连上后必须很快看得见世界（不再等一个 snapshot 周期）
  await page.waitForFunction(() => globalThis.__deephealing.entityIds().length > 0, null, { timeout: 20000 });
  record.first_frame_ms = Date.now() - loadedAt;
  record.first_frame_entities = await page.evaluate(() => globalThis.__deephealing.entityIds().length);
  await page.waitForTimeout(2500); // 让下行 tick 流真的跑起来
  record.duplicate_id_count = await page.evaluate(() => {
    const ids = [...document.querySelectorAll('[id]')].map((element) => element.id);
    return ids.length - new Set(ids).size;
  });

  record.connected_session = await page.evaluate(() => globalThis.__deephealing.client.sessionId);
  record.mode_initial = await page.evaluate(() => globalThis.__deephealing.mode());
  record.reading_initial = await page.evaluate(() => globalThis.__deephealing.reading());
  record.applied_messages = await page.evaluate(() => globalThis.__deephealing.client.appliedKeys.length);
  record.tick_badge = await page.textContent('#tick');
  record.event_stream_items = await page.evaluate(() => document.querySelectorAll('#event-stream li').length);

  // ---- R3 / G1：画布 / 绘制缓冲 / 视口读数（判据①：canvas 的 getBoundingClientRect 必须随视口变化）
  record.window_metrics = await page.evaluate(() => ({
    innerWidth: window.innerWidth, innerHeight: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio,
  }));
  record.canvas_rect = await page.evaluate(() => {
    const rect = document.getElementById('scene').getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  });
  record.canvas_attributes = await page.evaluate(() => {
    const canvas = document.getElementById('scene');
    return { width: canvas.width, height: canvas.height };
  });
  record.gl_drawing_buffer = await page.evaluate(() => {
    const canvas = document.getElementById('scene');
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
    return gl ? { width: gl.drawingBufferWidth, height: gl.drawingBufferHeight } : null;
  });
  record.scene_viewport = await page.evaluate(() => globalThis.__deephealing.viewport());
  record.hud_rect = await page.evaluate(() => {
    const rect = document.getElementById('hud').getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  });

  // ---- AC-M3-4 ①：真浏览器里枚举 UI 控件清单
  record.observe_panel_write_controls = await page.evaluate(() => globalThis.__deephealing.writeControls());
  record.controls_observe_mode = await page.evaluate(() => {
    const selector = 'button, input, textarea, select, form, [contenteditable="true"], a[href]';
    return [...document.querySelectorAll(selector)].map((element) => ({
      tag: element.tagName.toLowerCase(),
      id: element.id || null,
      type: element.getAttribute('type'),
      text: (element.textContent || '').trim().slice(0, 40),
      visible: Boolean(element.offsetWidth || element.offsetHeight || element.getClientRects().length),
      in_hud: Boolean(document.getElementById('hud')?.contains(element)),
    }));
  });

  // ---- AC-M3-4 ②：写接口被拒（客户端本地拒 + 服务端 WS 上行拒）
  record.client_local_rejection = await page.evaluate(async () => globalThis.__deephealing.client
    .submitIntent({ id: 'browser-local-probe', kind: 'delegate_instruction', target: 'npc-001' }));
  record.server_ws_rejection = await page.evaluate(async () => {
    const created = await fetch('/sessions', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ mode: 'observe', district_pack_id: 'xingfu-xiaoqu', client_version: '0.3.0' }),
    });
    const session = await created.json();
    const socket = new WebSocket(`ws://${location.host}/ws/${session.session_id}`);
    const seen = [];
    await new Promise((resolveOpen, rejectOpen) => { socket.onopen = resolveOpen; socket.onerror = rejectOpen; });
    const ack = await new Promise((resolveAck) => {
      socket.onmessage = (event) => {
        const message = JSON.parse(String(event.data));
        seen.push(message.t);
        if (message.t === 'intent_ack') resolveAck(message);
      };
      socket.send(JSON.stringify({ t: 'intent', id: 'browser-server-probe', kind: 'delegate_instruction', target: 'npc-001' }));
    });
    socket.close();
    return { status: created.status, session_mode: session.mode, first_message_types: seen, ack };
  });

  // ---- 两态读法：真点击切换 + 截图 + 几何读数（表层在 reveal_at_tick **之前**，深层在其**之后**）
  const shots = [];
  const shot = async (reading) => {
    const path = join(OUT, `${TAG}-${viewport.name}-${reading}.png`);
    await page.screenshot({ path });
    shots.push(path);
    results.shots.push(path);
  };
  const revealAtTick = await page.evaluate(() => globalThis.__deephealing.worldview.anomalies[0].reveal_at_tick);
  record.reveal_at_tick = revealAtTick;
  await shot('surface');
  record.surface_tick_at_shot = await page.evaluate(() => Number((document.getElementById('tick').textContent || '').replace(/\D+/g, '')));
  record.surface_anomaly_text = await page.textContent('#anomaly-read');
  await page.waitForFunction((threshold) => Number((document.getElementById('tick').textContent || '').replace(/\D+/g, '')) >= threshold,
    revealAtTick + 5, { timeout: 30000 });
  await page.click('#toggle-reading');
  await page.waitForFunction(() => globalThis.__deephealing.reading() === 'underneath', null, { timeout: 5000 });
  await shot('underneath');
  record.underneath_tick_at_shot = await page.evaluate(() => Number((document.getElementById('tick').textContent || '').replace(/\D+/g, '')));
  record.reading_after_click = await page.evaluate(() => globalThis.__deephealing.reading());
  record.reading_badge_after_click = await page.textContent('#reading-badge');

  record.geometry_surface = await page.evaluate(() => globalThis.__deephealing.scene.geometryFor('surface'));
  record.geometry_underneath = await page.evaluate(() => globalThis.__deephealing.scene.geometryFor('underneath'));
  record.anomaly_read_underneath = await page.textContent('#anomaly-read');
  record.anomaly_dataset = await page.evaluate(() => ({ ...document.getElementById('anomaly-read').dataset }));
  // R3 / G2：**场景图 mesh 层**读数（装配**之后**的真相）—— 经 createScene() 的句柄取数。
  // 注意：跨 tick 时实体世界坐标本来就会变（delta 推进），故跨读法的比较只用
  // `entity_ids` / `shape_digests` / `geometry_digest`（几何量），**不**比 `mesh_positions`。
  record.assembly_underneath = await page.evaluate(() => globalThis.__deephealing.assemblyReport());
  await page.evaluate(() => globalThis.__deephealing.setReading('surface'));
  record.assembly_surface = await page.evaluate(() => globalThis.__deephealing.assemblyReport());
  record.entity_ids = await page.evaluate(() => globalThis.__deephealing.entityIds());

  // ---- 真交互：切到 participate ⇒ 写控件出现；填输入 + 点「委托」
  await page.click('#toggle-mode');
  await page.waitForSelector('#delegate-instruction', { timeout: 10000 });
  record.mode_after_click = await page.evaluate(() => globalThis.__deephealing.mode());
  record.write_controls_participate = await page.evaluate(() => globalThis.__deephealing.writeControls());
  await page.fill('#delegate-instruction', '把晚饭送到 1-101 门口');
  await page.click('#submit-delegate');
  await page.waitForTimeout(1500);
  record.intent_status_text = await page.textContent('#intent-status');
  record.intent_status_dataset = await page.evaluate(() => ({ ...document.getElementById('intent-status').dataset }));

  // ---- reload 后回读
  const tickBeforeReload = await page.evaluate(() => document.querySelector('#tick').textContent);
  await page.reload({ waitUntil: 'load' });
  await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 30000 });
  await page.waitForFunction(() => globalThis.__deephealing.client.appliedKeys.length > 0, null, { timeout: 30000 });
  await page.waitForTimeout(4000);
  record.reload = {
    tick_before: tickBeforeReload,
    tick_after: await page.evaluate(() => document.querySelector('#tick').textContent),
    mode_after: await page.evaluate(() => globalThis.__deephealing.mode()),
    reading_after: await page.evaluate(() => globalThis.__deephealing.reading()),
    session_id_after: await page.evaluate(() => globalThis.__deephealing.client.sessionId),
    event_stream_items_after: await page.evaluate(() => document.querySelectorAll('#event-stream li').length),
    applied_messages_after: await page.evaluate(() => globalThis.__deephealing.client.appliedKeys.length),
  };
  record.observe_panel_write_controls_after_reload = await page.evaluate(() => globalThis.__deephealing.writeControls());
  await shot('after-reload');

  record.shots = shots;
  results.viewports.push(record);
  await context.close();
}

results.console = { total: consoleLines.length, errors: consoleLines.filter((line) => line.type === 'error').length };
results.page_errors = pageErrors;
results.bad_responses = badResponses;
writeFileSync(join(OUT, `console-${TAG}.jsonl`), consoleLines.map((line) => JSON.stringify(line)).join('\n') + '\n');
writeFileSync(join(OUT, `browser-accept-${TAG}.json`), `${JSON.stringify(results, null, 2)}\n`);

await browser.close();
process.stdout.write(`${JSON.stringify({
  tag: TAG, shots: results.shots.length, console_total: results.console.total,
  console_errors: results.console.errors, page_errors: pageErrors.length, bad_responses: badResponses,
  viewports: results.viewports.map((entry) => ({
    viewport: entry.viewport,
    first_frame_ms: entry.first_frame_ms,
    duplicate_ids: entry.duplicate_id_count,
    write_controls: entry.observe_panel_write_controls,
    server_rejection: entry.server_ws_rejection?.ack?.reason,
    intent_status: entry.intent_status_text,
    reload_tick: [entry.reload.tick_before, entry.reload.tick_after],
    entities: entry.entity_ids.length,
  })),
})}\n`);
process.exit(0);
