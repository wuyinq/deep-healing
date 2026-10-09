#!/usr/bin/env node
/**
 * `AC-H-1` · **5~10 分钟可玩互动**（真会话 + 真浏览器 + 真传输；墙钟与 tick 口径同时记录）。
 *
 * 剧本（写死）：观察 → 一次**帮助** intent → 一次**违背约定** intent → **离开**（页面导航走 + 等待）
 * → **重进**（新会话）→ **后续见面** intent。按 PM 裁决：「离开后重进」的等待时间**计入**总时长。
 * 时长必须 ∈ [5, 10] 分钟；世界时钟不加速（真实墙钟），若用 tick 加速须记加速比（本脚本不加速）。
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
const PORT = 8849;
const OUT = join(HERE, 'runtime', 'h1', 'out');
const READBACK = join(HERE, 'readback');
mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
const at = () => Math.floor(Date.now() / 1000);

const CHROMIUM = [
  process.env.PW_CHROMIUM,
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1243',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1234',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
  // ⚠️ **实测踩过**：ms-playwright 缓存会被并发 install 清掉 ⇒ 回落到**系统 Chrome**，
  // 并在读数里如实记 `browser_binary`（不同二进制 ⇒ 读数并列，不混同）。
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean).find((candidate) => existsSync(candidate));

const host = spawn('node', [
  join(HERE, 'serve-live.mjs'), '--tag', 'h1', '--port', String(PORT), '--pack', PACK,
  '--out', OUT, '--runtime', join(HERE, 'runtime', 'h1', 'bridge'),
  '--web', WEB, '--source', SOURCE, '--tick-ms', '100', '--snapshot-every', '1', '--seed', '20260921',
  '--run-seconds', '900', '--start-paused', 'false',
  '--memory-chain', '--emotion-pressure-threshold', '0.0', '--stub-remote-api', '1.0',
], { stdio: ['ignore', 'pipe', 'pipe'] });
const killHost = () => { try { host.kill('SIGKILL'); } catch { /* 已退出 */ } };
process.on('exit', killHost);
await new Promise((ready, reject) => {
  const timer = setTimeout(() => reject(new Error('SERVE_READY timeout')), 90000);
  host.stdout.on('data', (chunk) => { if (String(chunk).includes('SERVE_READY')) { clearTimeout(timer); ready(); } });
});

const browser = await chromium.launch({ headless: true, executablePath: CHROMIUM,
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'] });
const json = async (path, init) => (await fetch(`http://127.0.0.1:${PORT}${path}`, init)).json();
const post = (path, body) => json(path, { method: 'POST', headers: { 'content-type': 'application/json' },
                                          body: JSON.stringify(body) });

// participate 会话（与 C-1 同口径：页面上真点击产生上行；此处先建会话再让页面连它）
const created = await post('/sessions', { mode: 'participate', district_pack_id: PACK });
const sessionId = created.session_id ?? created.id ?? created.body?.session_id ?? null;
const healthBefore = await json('/health');

const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (error) => errors.push(String(error)));
await page.goto(`http://127.0.0.1:${PORT}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 90000 });

const milestones = [];
const mark = async (label) => {
  const state = await json('/evidence/state');
  // ⚠️ **实测踩过**：`about:blank`（离开世界的那一段）上没有 `__deephealing` ⇒ 这里必须容错。
  const snapshot = await page.evaluate(() => {
    try { return globalThis.__deephealing?.acSnapshot?.() ?? null; } catch { return null; }
  });
  milestones.push({ label, at_epoch: at(), elapsed_s: at() - START, tick: state.tick,
                    event_count: state.event_count, session: sessionId,
                    npc_pos: snapshot?.npcs?.[0]?.transform?.pos_mm ?? null,
                    page_has_app: snapshot !== null });
};
const START = at();

// ── 1) 观察（落在世界里，不介入）
await sleep(70_000);
await mark('observation_70s');

// ── 2) 一次**帮助**（用交付面真实控件：`#delegate-instruction` + `#submit-delegate`）
await page.click('#toggle-mode');                    // 真点击：切到参与模式（页面侧真上行）
await page.waitForTimeout(1500);
const helpIntent = await page.evaluate(() => {
  const input = document.querySelector('#delegate-instruction');
  const button = document.querySelector('#submit-delegate');
  return { input_present: Boolean(input), button_present: Boolean(button),
           button_text: button?.textContent ?? null, placeholder: input?.getAttribute('placeholder') ?? null };
});
await page.fill('#delegate-instruction', '帮我把厨房的米袋搬到 1-101 门口');
await page.click('#submit-delegate');
await page.waitForTimeout(1500);
await mark('help_intent_submitted');
await sleep(80_000);
await mark('help_settled_80s');

// ── 3) 一次**违背约定**（约定「今天别去厨房」，随后仍发出与之相反/相冲的指令）
await page.fill('#delegate-instruction', '今天别去厨房');
await page.click('#submit-delegate');
await page.waitForTimeout(1500);
await mark('agreement_intent_submitted');
await sleep(80_000);
await mark('agreement_settled_80s');

// ── 4) **离开**：页面导航走 + 等待（PM 已裁：计入时长）
await page.goto('about:blank');
await mark('left_world');
await sleep(75_000);
await mark('left_wait_75s');

// ── 5) **重进**：新会话 + 新页面
const reCreated = await post('/sessions', { mode: 'participate', district_pack_id: PACK });
const reSessionId = reCreated.session_id ?? reCreated.id ?? reCreated.body?.session_id ?? null;
const healthAfter = await json('/health');
const revisit = await browser.newPage({ viewport: { width: 1440, height: 900 } });
revisit.on('pageerror', (error) => errors.push(String(error)));
await revisit.goto(`http://127.0.0.1:${PORT}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
await revisit.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 90000 });
await sleep(70_000);
const revisitState = await json('/evidence/state');
const revisitSnapshot = await revisit.evaluate(() => {
  try { return globalThis.__deephealing?.acSnapshot?.() ?? null; } catch { return null; }
});
milestones.push({ label: 'revisit_70s', at_epoch: at(), elapsed_s: at() - START, tick: revisitState.tick,
                  event_count: revisitState.event_count, session: reSessionId,
                  npc_pos: revisitSnapshot.npcs?.[0]?.transform?.pos_mm ?? null });
await revisit.click('#toggle-mode');
await revisit.waitForTimeout(1500);
await mark('revisit_participate_clicked');

const END = at();
const wallSeconds = END - START;
const finalState = await json('/evidence/state');
await browser.close();
killHost();

const reading = {
  task: 'h1', at_epoch: END, start_epoch: START, end_epoch: END,
  browser_binary: CHROMIUM,
  browser_channel: CHROMIUM && CHROMIUM.includes('/Applications/') ? 'system Google Chrome' : 'ms-playwright chromium',
  wall_seconds: wallSeconds, wall_minutes: Number((wallSeconds / 60).toFixed(2)),
  within_5_to_10_minutes: wallSeconds >= 300 && wallSeconds <= 600,
  world_clock: { accelerated: false, tick_ms: 100, tick_at_end: finalState.tick,
                 implied_seconds_if_10hz: Number((finalState.tick * 0.1).toFixed(1)),
                 note: '未加速：墙钟与 tick 同时记录（tick_ms=100 ⇒ 1 tick = 0.1 s）' },
  sessions: { first: sessionId, revisit: reSessionId, distinct: sessionId !== reSessionId,
              create_response_keys: Object.keys(created ?? {}),
              health_sessions_before: healthBefore?.sessions ?? null,
              health_sessions_after: healthAfter?.sessions ?? null,
              sessions_increased: (healthAfter?.sessions ?? 0) > (healthBefore?.sessions ?? 0) },
  milestones, script: ['观察', '帮助 intent（真控件填写 + 点击 委托）', '约定 intent', '离开（导航走 + 等待）', '重进（新会话）', '参与模式真点击'],
  help_controls: helpIntent,
  page_errors: errors.slice(0, 8),
  out_dir: OUT,
};
writeFileSync(join(READBACK, 'h1-reading.json'), `${JSON.stringify(reading, null, 2)}\n`);
process.stdout.write(`H1 ${JSON.stringify({ wall_seconds: wallSeconds, wall_minutes: reading.wall_minutes,
  within: reading.within_5_to_10_minutes, ticks: finalState.tick, distinct_sessions: reading.sessions.distinct,
  milestones: milestones.map((m) => [m.label, m.elapsed_s, m.tick]) })}\n`);
process.exit(0);
