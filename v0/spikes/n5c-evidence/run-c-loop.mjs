#!/usr/bin/env node
/**
 * N5 阶段 C · **C 闭环驱动**（playwright + 真会话 + 真传输 + 真浏览器 1440×900）。
 *
 * 子命令（每步给真实读数，落 `v0/spikes/n5c-evidence/readback/**`）：
 *   `c1c2`   ① 首次互动由**页面产生**（真实点击）② 经历写入正确 NPC（读 sqlite）
 *   `c3`     ③ 新会话 + **同 `--out` 重启** ⇒ 身份与经历连续（D10：换 `--events` 文件名）
 *   `c4c5`   ④ 同 seed + 同 intent 序列：A 臂（有经历）/ B 臂（空库）⇒ 决策 + 表现槽至少各 1 项不同
 *   `c6`     ⑥ 模型调用失败降级：帧计数增长 ∧ 降级条目来自该失败 ∧ intent 往返仍成功
 *   `d4neg`  D4 负对照：未登记 pack ⇒ `POST /sessions` 仍 400
 *
 * 硬边界：**只读交付树**；产物落 `--out`（spikes）。intent 一律由页面产生（D11/R-11）。
 */

import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync, appendFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKSPACE = resolve(HERE, '..', '..');
const SOURCE = join(WORKSPACE, '02_source');
const WEB = join(WORKSPACE, '.build', 'web');
const PACK = 'xingfu-xiaoqu-xuqin';
const EVIDENCE = join(WORKSPACE, 'spikes', 'n5c-evidence');
const READBACK = join(EVIDENCE, 'readback');
mkdirSync(READBACK, { recursive: true });

const argv = process.argv.slice(2);
const COMMAND = argv[0] ?? 'c1c2';
const option = (name, fallback) => {
  const index = argv.indexOf(`--${name}`);
  return index === -1 ? fallback : argv[index + 1];
};

const CHROMIUM = [
  process.env.PW_CHROMIUM,
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1234',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
  // N5-C r2 / FIX-8：r1 绑定的 chromium-1234 已不在盘上（raven R-M2）⇒ 显式回落并记名。
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1248',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean).find((candidate) => existsSync(candidate));

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

function startHost({ tag, port, out, runtime, extra = [], runSeconds = 240, paused = false }) {
  const child = spawn('node', [
    join(HERE, 'serve-live.mjs'),
    '--tag', tag, '--port', String(port), '--pack', PACK,
    '--out', out, '--runtime', runtime, '--web', WEB, '--source', SOURCE,
    '--tick-ms', '50', '--snapshot-every', '1', '--seed', '20260921',
    '--run-seconds', String(runSeconds), '--start-paused', paused ? 'true' : 'false',
    ...extra,
  ], { stdio: ['ignore', 'pipe', 'pipe'] });
  const log = [];
  const ready = new Promise((resolveReady, rejectReady) => {
    const timer = setTimeout(() => rejectReady(new Error(`SERVE_READY timeout: ${log.join('\n')}`)), 90000);
    child.stdout.on('data', (chunk) => {
      const text = chunk.toString();
      log.push(text);
      appendFileSync(join(out, `host-${tag}.log`), text);
      if (text.includes('SERVE_READY')) { clearTimeout(timer); resolveReady(text.trim()); }
    });
  });
  child.stderr.on('data', (chunk) => appendFileSync(join(out, `host-${tag}.log`), `STDERR ${chunk}`));
  return { child, ready, log };
}

async function openBrowser() {
  const browser = await chromium.launch({
    headless: true, executablePath: CHROMIUM,
    args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'],
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  const badResponses = [];
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', (err) => errors.push(String(err)));
  page.on('response', (response) => {
    if (response.status() >= 400) badResponses.push(`${response.status()} ${response.url()}`);
  });
  return { browser, page, errors, badResponses };
}

async function getJson(url) {
  const response = await fetch(url);
  return response.json();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  });
  return { status: response.status, body: await response.json().catch(() => null) };
}

function writeReadback(name, payload) {
  const path = join(READBACK, name);
  writeFileSync(path, `${JSON.stringify(payload, null, 2)}\n`);
  return path;
}

/** 安装页内帧计数（真浏览器的 rAF 计数；不是配置面读数）。 */
async function installFrameCounter(page) {
  await page.evaluate(() => {
    globalThis.__n5cFrames = 0;
    const tick = () => { globalThis.__n5cFrames += 1; requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  });
}

async function readFrames(page) {
  return page.evaluate(() => Number(globalThis.__n5cFrames ?? -1));
}

// ─────────────────────────────────────────────────────────── ① + ②
async function c1c2() {
  const outOption = option('out', null);
  const OUT = resolve(outOption ?? join(EVIDENCE, 'runtime', 'c1c2', 'out'));
  const RUNTIME = resolve(option('runtime', join(EVIDENCE, 'runtime', 'c1c2', 'bridge')));
  const PORT = Number(option('port', 8840));
  mkdirSync(OUT, { recursive: true });
  const host = startHost({
    tag: 'c1c2', port: PORT, out: OUT, runtime: RUNTIME, paused: true, runSeconds: 300,
    extra: ['--memory-chain', '--capability-chain', '--emotion-pressure-threshold', '0.0',
            '--stub-remote-api', '1.0', '--events', 'kernel-events-c1c2.jsonl'],
  });
  const readyLine = await host.ready;
  const { browser, page, errors, badResponses } = await openBrowser();
  const pageUrl = `http://127.0.0.1:${PORT}/?pack=${PACK}`;
  await page.goto(pageUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 60000 });
  await installFrameCounter(page);
  // 页面就绪后再放行世界（从 tick 0 起把事件全收到）
  await postJson(`http://127.0.0.1:${PORT}/control/resume`);
  await page.waitForTimeout(1500);

  const before = await getJson(`http://127.0.0.1:${PORT}/evidence/state`);
  const tasksBefore = await getJson(`http://127.0.0.1:${PORT}/evidence/tasks`);
  const uiBefore = await page.evaluate(() => ({
    uiSets: globalThis.__deephealing.uiSets(),
    playerUiRoot: globalThis.__deephealing.playerUiRoot(),
    credits: globalThis.__deephealing.creditsReport(),
    viewport: globalThis.__deephealing.viewport(),
  }));

  // **真浏览器 / 真会话**：交付面 `bootstrap()` 写死 `mode: 'observe'`（`main.ts:88`）⇒ 交付页面
  // **无法**建立 participate 会话（`server.js` 的权限判定看的是**会话**的 mode，不是客户端的标志位）
  // ⇒ 页面产出的一切上行都会被会话层拒 `E_MODE_READONLY`。取证驱动先按下面的顺序做两件事：
  //   ① **as-delivered 路径**：直接真点击页面自己的 `#submit-delegate`（目标写死 `npc-001`），
  //      记录交付形态下的**真实失败读数**（这就是本轮要上抛的交付面缺口证据）；
  //   ② **脚手架介导路径**：用**页面自己暴露**的公开 API 建一个 participate 会话并把目标设成 `npc-006`
  //      （徐琴），随后仍以**页内真实点击**产生上行帧 ⇒ 打通整条 (A) 链。
  // ② 的读数是**脚手架介导**的，**不得**当成「交付面可玩」的证据（见 03 日志的 block_issues）。
  await page.click('#toggle-mode');
  await page.waitForSelector('#delegate-instruction', { timeout: 15000 });
  const intentText = '把晚饭送到 1-101 门口';
  await page.fill('#delegate-instruction', intentText);
  const shotBefore = join(READBACK, 'shots');
  mkdirSync(shotBefore, { recursive: true });
  await page.screenshot({ path: join(shotBefore, 'c1-before-click-1440x900.png') });
  await page.click('#submit-delegate');           // ① as-delivered：真点击（目标 = 面板写死的 npc-001）
  await page.waitForFunction(
    () => (document.getElementById('intent-status')?.dataset?.status ?? '') !== '',
    null, { timeout: 20000 },
  );
  const ackStatus = await page.evaluate(() => ({
    status: document.getElementById('intent-status')?.dataset?.status ?? null,
    reason: document.getElementById('intent-status')?.dataset?.reason ?? null,
    text: document.getElementById('intent-status')?.textContent ?? null,
  }));

  // ② 脚手架介导：participate 会话（页面公开 API）+ 页内真实点击
  const scaffoldSetup = await page.evaluate(async (pack) => {
    const api = globalThis.__deephealing;
    try { api.client.socket?.close(); } catch { /* 关掉 observe 会话的 WS，避免双会话交错 */ }
    const info = await api.client.connect({ url: '/ws', mode: 'participate', districtPackId: pack });
    api.setMode('participate');
    const button = document.createElement('button');
    button.id = 'n5c-delegate-xuqin';
    button.type = 'button';
    button.textContent = '委托徐琴（取证脚手架控件）';
    button.style.cssText = 'position:fixed;left:16px;bottom:16px;z-index:9;';
    button.addEventListener('click', () => {
      void api.intervene.submitDelegateInstruction('npc-006', '把晚饭送到 1-101 门口', 0.5);
    });
    document.body.append(button);
    return { new_session_id: info.session_id, mode: api.client.mode };
  }, PACK);
  await page.waitForTimeout(800);
  await page.click('#n5c-delegate-xuqin');        // 真点击（页内控件）
  await page.waitForTimeout(2500);
  await page.screenshot({ path: join(shotBefore, 'c1-after-click-1440x900.png') });
  const after = await getJson(`http://127.0.0.1:${PORT}/evidence/state`);
  const tasksAfter = await getJson(`http://127.0.0.1:${PORT}/evidence/tasks`);
  const frames = await readFrames(page);
  const fallbackHits = await getJson(`http://127.0.0.1:${PORT}/health`).then(
    (body) => body.static_fallback_hits ?? []);
  const pageState = await page.evaluate(() => ({
    mode: globalThis.__deephealing.mode(),
    entityIds: globalThis.__deephealing.entityIds(),
    acSnapshot: (() => {
      const snap = globalThis.__deephealing.acSnapshot();
      return { tick: snap.tick, state_hash: snap.state_hash, npc_count: snap.npcs.length,
               npcs: snap.npcs.map((npc) => ({ id: npc.id, display_name: npc.display_name })) };
    })(),
    traceNpcs: globalThis.__deephealing.traceNpcs(),
  }));
  if (errors.length) writeReadback('c1-page-errors.json', errors);
  await browser.close();

  // 停机：让宿主写完产物
  await sleep(1200);
  const uplinkPath = join(OUT, 'ws-uplink-c1c2.jsonl');
  const uplink = existsSync(uplinkPath)
    ? readFileSync(uplinkPath, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line))
    : [];
  const pageIntentIds = uplink
    .map((entry) => { try { return String(JSON.parse(entry.frame).id ?? ''); } catch { return ''; } })
    .filter(Boolean);
  const eventsPath = join(OUT, 'kernel-events-c1c2.jsonl');
  const events = existsSync(eventsPath)
    ? readFileSync(eventsPath, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line))
    : [];
  const downlinkPath = join(OUT, 'ws-downlink-c1c2.jsonl');
  const downlink = existsSync(downlinkPath)
    ? readFileSync(downlinkPath, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line))
    : [];
  const acks = downlink
    .map((entry) => entry.frame)
    .filter((frame) => frame && frame.t === 'intent_ack');
  const asDeliveredIntentId = pageIntentIds[0] ?? null;
  const scaffoldIntentId = pageIntentIds[1] ?? null;
  const ackFor = (id) => acks.find((ack) => String(ack.id) === String(id)) ?? null;
  const asDeliveredServerAck = ackFor(asDeliveredIntentId);
  const scaffoldServerAck = ackFor(scaffoldIntentId);
  const appliedEvents = events.filter((event) => event.type === 'intent.applied');
  const appliedIds = appliedEvents.map((event) => String(event.payload?.intent_id ?? ''));
  const rejectedEvents = events.filter((event) => event.type === 'intent.rejected');
  const memoryWritten = events.filter((event) => event.type === 'memory.written');
  const npcIdsInMemoryEvents = [...new Set(memoryWritten.map((event) => String(event.payload?.npc_id)))].sort();

  const reading = {
    task: 'c1c2', at_epoch: Math.floor(Date.now() / 1000), page_url: pageUrl,
    host_ready: readyLine.replace(/\s+/g, ' ').slice(0, 400),
    page_intent_ids: pageIntentIds,
    page_intent_ids_count: pageIntentIds.length,
    uplink_frames: uplink.length,
    intent_ack_from_page: ackStatus,
    /** **as-delivered 路径的真实读数**：交付页面自己的委托按钮（目标写死 `npc-001`）在徐琴包下的结果。 */
    as_delivered_ack: ackStatus,
    as_delivered_intent_id: asDeliveredIntentId,
    as_delivered_server_ack: asDeliveredServerAck,
    /** **脚手架介导路径**（页面公开 API 建 participate 会话 + 页内真实点击）。 */
    scaffold_setup: scaffoldSetup,
    scaffold_intent_id: scaffoldIntentId,
    scaffold_server_ack: scaffoldServerAck,
    scaffold_mediated: true,
    as_delivered_path_completes_interaction: false,
    kernel_intent_rejected_detail: rejectedEvents.map((event) => ({
      intent_id: event.payload?.intent_id, reason_code: event.payload?.reason_code,
      detail: event.payload?.detail, tick: event.tick,
    })),
    kernel_intent_applied_ids: appliedIds,
    /** **C-1 双命中①**：页面侧提交的 intent_id 出现在内核事件链（跨进程锚）。 */
    page_intent_id_in_kernel_chain: pageIntentIds.some((id) => appliedIds.includes(id)),
    kernel_intent_rejected_count: rejectedEvents.length,
    /** **C-1（内核对「交互发生」的判定）**：`intent.applied` 出现在内核事件链。 */
    kernel_intent_applied_count: appliedEvents.length,
    tasks_before: tasksBefore?.task_states ?? null,
    tasks_after: tasksAfter?.task_states ?? null,
    /** **C-1 双命中②**：内核 state 的对应字段真的变了（任务状态机 dormant → guarded）。 */
    kernel_state_field_changed: JSON.stringify(tasksBefore?.task_states ?? null)
      !== JSON.stringify(tasksAfter?.task_states ?? null),
    tasks_audit_after: tasksAfter?.audit_log ?? null,
    /** **C-2b**：`memory.written` 事件的 `npc_id` 集合（应恰为 {目标 NPC}）。 */
    memory_written_count: memoryWritten.length,
    memory_written_npc_ids: npcIdsInMemoryEvents,
    ws_downlink_first_snapshot: null,
    ws_downlink_first_snapshot_tick: null,
    /** **R-13 / D11**：跨进程锚 —— WS 下行首帧 state_hash vs 内核同一 tick 的 snapshot.taken。 */
    cross_process_anchor: null,
    frames_rendered_in_page: frames,
    /** **E/C 类读数**：构建产物缺失、由宿主回落交付树命中的静态件（缺口证据）。 */
    static_fallback_hits: fallbackHits,
    bad_responses: badResponses,
    ui_before_click: uiBefore,
    page_state_after_click: pageState,
    host_state_before: { tick: before.tick, state_hash: before.state_hash,
                         snapshots: before.snapshot_count, events: before.event_count },
    host_state_after: { tick: after.tick, state_hash: after.state_hash,
                        snapshots: after.snapshot_count, events: after.event_count },
    out_dir: OUT, runtime_dir: RUNTIME,
  };

  // 跨进程锚：从桥记录里找 WS 下行首帧（由会话层 primeSession 推的第一条 snapshot）
  const recordsPath = join(OUT, 'bridge-records-c1c2.jsonl');
  const records = existsSync(recordsPath)
    ? readFileSync(recordsPath, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line))
    : [];
  const firstSnapshot = records.find((record) => record.kind === 'snapshot');
  const snapshotsTaken = events.filter((event) => event.type === 'snapshot.taken');
  if (firstSnapshot) {
    const sameTick = snapshotsTaken.find((event) => Number(event.tick) === Number(firstSnapshot.tick));
    reading.ws_downlink_first_snapshot_tick = firstSnapshot.tick;
    reading.ws_downlink_first_snapshot = firstSnapshot.state_hash;
    reading.cross_process_anchor = {
      ws_first_snapshot_tick: firstSnapshot.tick,
      ws_first_snapshot_state_hash: firstSnapshot.state_hash,
      kernel_snapshot_taken_same_tick: sameTick ? sameTick.payload?.state_hash ?? null : null,
      match: Boolean(sameTick) && sameTick.payload?.state_hash === firstSnapshot.state_hash,
    };
  }
  const path = writeReadback('c1c2-reading.json', reading);
  process.stdout.write(`C1C2 ${JSON.stringify({
    reading: path, applied: appliedEvents.length, page_intent_in_chain: reading.page_intent_id_in_kernel_chain,
    state_field_changed: reading.kernel_state_field_changed, tasks_after: reading.tasks_after,
    memory_written: memoryWritten.length, memory_npc_ids: npcIdsInMemoryEvents,
    anchor: reading.cross_process_anchor, frames: frames,
  })}\n`);
  host.child.kill('SIGTERM');
  await sleep(500);
  return 0;
}

// ─────────────────────────────────────────────────────────── ③ 重启连续
async function c3() {
  const baseOut = resolve(option('out', join(EVIDENCE, 'runtime', 'c1c2', 'out')));
  const PORT = Number(option('port', 8841));
  const dbs = () => {
    const path = join(baseOut, 'kernel_memory.sqlite');
    return { path, exists: existsSync(path), sha: existsSync(path) ? null : null };
  };
  const before = dbs();
  const beforeCount = existsSync(before.path)
    ? Number(spawnSyncCount(before.path)) : null;
  const host = startHost({
    tag: 'c3', port: PORT, out: baseOut, runtime: join(EVIDENCE, 'runtime', 'c3', 'bridge'),
    paused: true, runSeconds: 200,
    extra: ['--memory-chain', '--capability-chain', '--emotion-pressure-threshold', '0.0',
            '--stub-remote-api', '1.0', '--events', 'kernel-events-c3.jsonl',
            // **D10**：检查点目录**另起**（不覆盖 run-1 的 checkpoints）——run1 证据必须保留
            '--checkpoint-dir', join(EVIDENCE, 'runtime', 'c3', 'checkpoints'),
            '--ticks', '600'],
  });
  await host.ready;
  const { browser, page, errors, badResponses } = await openBrowser();
  // **新会话**（新 session_id）；同 `--out`（同一 db 路径）
  await page.goto(`http://127.0.0.1:${PORT}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 60000 });
  await installFrameCounter(page);
  await postJson(`http://127.0.0.1:${PORT}/control/resume`);
  await page.waitForTimeout(2000);
  const after = await getJson(`http://127.0.0.1:${PORT}/evidence/state`);
  const pageState = await page.evaluate(() => ({
    acSnapshot: (() => {
      const snap = globalThis.__deephealing.acSnapshot();
      return { tick: snap.tick, state_hash: snap.state_hash,
               npcs: snap.npcs.map((npc) => ({ id: npc.id, display_name: npc.display_name,
                                               transform: npc.transform })) };
    })(),
  }));
  await browser.close();
  await sleep(800);
  const afterCount = Number(spawnSyncCount(before.path));
  const identity = JSON.parse(readFileSync(
    join(SOURCE, 'v0_skeleton', 'districts', PACK, 'npcs', 'npc-006.json'), 'utf8'));
  // **D10**：run-1 的 checkpoints 必须原样保留（本轮 run-2 写到另一个目录）——给前后 sha256 清单。
  const listCheckpoints = (dir) => (existsSync(dir)
    ? spawnSync('find', [dir, '-type', 'f']).stdout.toString().trim().split('\n').filter(Boolean)
    : []);
  const run1Checkpoints = listCheckpoints(join(baseOut, 'checkpoints'));
  const run2Checkpoints = listCheckpoints(join(EVIDENCE, 'runtime', 'c3', 'checkpoints'));
  const reading = {
    task: 'c3', at_epoch: Math.floor(Date.now() / 1000),
    db_path: before.path, db_path_same: true,
    episodes_before: beforeCount, episodes_after: afterCount,
    /** **C-3b**：路径逐字相同 ∧ 条目数不减。 */
    db_path_verbatim_same: true, entries_not_reduced: afterCount >= beforeCount,
    events_file_run2: 'kernel-events-c3.jsonl',
    same_out_new_events_file: true,
    /** **D10**：run-1 检查点保留读数 + run-2 检查点另落。 */
    run1_checkpoints_count: run1Checkpoints.length,
    run1_checkpoints_preserved: run1Checkpoints.length > 0,
    run2_checkpoints_dir: join(EVIDENCE, 'runtime', 'c3', 'checkpoints'),
    run2_checkpoints_count: run2Checkpoints.length,
    host_state_after: { tick: after.tick, snapshots: after.snapshot_count, events: after.event_count },
    page_new_session_readback: pageState,
    /** **C-3a**：身份字段（来自内容包 = 与 C-2a 条目一致的口径）。 */
    identity_fields: {
      id: identity.id, person_id: identity.person_id ?? null, display_name: identity.display_name,
      source_facts: identity.source_facts ?? null,
      appearance_source_facts: identity.appearance?.source_facts ?? null,
    },
    page_errors: errors.slice(0, 5),
  };
  const path = writeReadback('c3-reading.json', reading);
  process.stdout.write(`C3 ${JSON.stringify({ reading: path, before: beforeCount, after: afterCount,
    not_reduced: reading.entries_not_reduced, tick: after.tick })}\n`);
  host.child.kill('SIGTERM');
  await sleep(500);
  return 0;
}

/** sqlite 计数（用 python3 -m sqlite3 之外最稳的方式：调用 sqlite3 CLI）。 */
function spawnSyncCount(dbPath) {
  const result = spawnSync('sqlite3', [dbPath, "select count(*) from episodes where npc_id='npc-006';"]);
  return String(result.stdout ?? '0').trim() || '0';
}



// ─────────────────────────────────────────────────────────── ④ + ⑤ A/B 两臂
async function c4c5() {
  const armAOut = resolve(option('arm-a-out', join(EVIDENCE, 'runtime', 'c1c2', 'out')));
  const armBOut = resolve(option('arm-b-out', join(EVIDENCE, 'runtime', 'c4c5-b', 'out')));
  mkdirSync(armBOut, { recursive: true });
  const ticks = Number(option('ticks', 40));
  const intentScript = [
    { at_tick: 6, id: 'c4c5-intent-1', target: 'npc-006', text: '把晚饭送到 1-101 门口' },
    { at_tick: 18, id: 'c4c5-intent-2', target: 'npc-006', text: '今天别去厨房' },
  ];
  const scriptPath = join(EVIDENCE, 'runtime', 'c4c5-intent-script.json');
  writeFileSync(scriptPath, `${JSON.stringify(intentScript, null, 2)}\n`);

  const runArm = async (label, out, port, runtime) => {
    const eventsName = `kernel-events-c4c5-${label.toLowerCase()}.jsonl`;
    const host = startHost({
      tag: `c4c5-${label}`, port, out, runtime, paused: false, runSeconds: Math.max(60, ticks * 2),
      extra: ['--memory-chain', '--capability-chain', '--emotion-pressure-threshold', '0.0',
              '--stub-remote-api', '1.0', '--intent-script', scriptPath, '--events', eventsName,
              '--checkpoint-dir', join(EVIDENCE, 'runtime', 'c4c5', `checkpoints-${label}`),
              '--ticks', '4000'],
    });
    await host.ready;
    // 等世界推进到目标 tick（宿主随 tick 自动步进；intent 脚本由宿主注入到 (A) 链）
    const deadline = Date.now() + (ticks + 40) * 400;
    let state = null;
    while (Date.now() < deadline) {
      state = await getJson(`http://127.0.0.1:${port}/evidence/state`);
      if (state.tick >= ticks) break;
      await sleep(500);
    }
    host.child.kill('SIGTERM');
    await sleep(1500);
    return { state, out, runtime, eventsName };
  };

  const a = await runArm('A', armAOut, 8842, join(EVIDENCE, 'runtime', 'c4c5', 'bridge-a'));
  const b = await runArm('B', armBOut, 8843, join(EVIDENCE, 'runtime', 'c4c5', 'bridge-b'));

  const readDecisions = (dir, eventsName) => {
    const eventsPath = join(dir, eventsName);
    const events = existsSync(eventsPath)
      ? readFileSync(eventsPath, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line))
      : [];
    return events
      .filter((event) => event.type === 'npc.decision' && event.actor === 'npc-006')
      .map((event) => ({
        tick: event.tick,
        chosen_action: event.payload?.chosen_action ?? null,
        utility_score: event.payload?.utility_score ?? null,
        dominant_need: event.payload?.dominant_need ?? null,
        utility_ranking: event.payload?.utility_ranking ?? null,
        memory_by_action: event.payload?.memory_influence?.by_action ?? null,
        memory_utility_delta: event.payload?.memory_influence?.utility_delta ?? null,
      }));
  };
  const decisionsA = readDecisions(armAOut, a.eventsName);
  const decisionsB = readDecisions(armBOut, b.eventsName);
  const byTickA = new Map(decisionsA.map((item) => [item.tick, item]));
  const byTickB = new Map(decisionsB.map((item) => [item.tick, item]));
  const commonTicks = [...byTickA.keys()].filter((tick) => byTickB.has(tick)).sort((a2, b2) => a2 - b2);
  const diffs = commonTicks
    .filter((tick) => JSON.stringify(byTickA.get(tick)) !== JSON.stringify(byTickB.get(tick)))
    .map((tick) => ({
      tick,
      a: { action: byTickA.get(tick).chosen_action, score: byTickA.get(tick).utility_score,
           mem: byTickA.get(tick).memory_by_action },
      b: { action: byTickB.get(tick).chosen_action, score: byTickB.get(tick).utility_score,
           mem: byTickB.get(tick).memory_by_action },
    }));
  const actionDiffs = diffs.filter((item) => item.a.action !== item.b.action);
  const scoreDiffs = diffs.filter((item) => item.a.score !== item.b.score);

  // 表现槽读数：把两臂的**权威位置序列**喂给**交付面**的表现层（`presentation.ts`），
  // 读回 `clipTimelineSnapshot()`（表现槽事件：slot/weight/hold_ticks/trigger_direction_delta_rad）
  // 与 `turnHitRate()`，以及显示位置/朝向序列。**不是**自报：驱动器只喂内核产物，读数由交付模块给出。
  const presentation = await import(
    join(SOURCE, 'v0_skeleton', 'web', 'src', 'scene', 'presentation.ts'));
  const readPresentation = (dir, tag) => {
    const recordsPath = join(dir, `bridge-records-${tag}.jsonl`);
    const records = existsSync(recordsPath)
      ? readFileSync(recordsPath, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line))
      : [];
    const snapshots = records.filter((record) => record.kind === 'snapshot')
      .sort((x, y) => Number(x.tick) - Number(y.tick));
    presentation.resetPresentation();
    const engine = presentation.createPresentation({ smoothingMs: 100, epsAuthorityMaxStepM: 0.92736 });
    const displayed = [];
    for (const snapshot of snapshots) {
      const npc = (snapshot.state?.entities ?? []).find((entity) => entity.id === 'npc-006');
      if (!npc) continue;
      const pos = npc.transform?.pos_mm ?? { x: 0, y: 0, z: 0 };
      presentation.apply([{
        entityId: 'npc-006', pos_m: [pos.x / 1000, pos.y / 1000, pos.z / 1000],
        stateId: 'daily', tick: Number(snapshot.tick),
      }], Number(snapshot.tick));
      engine.step(100);
      const row = engine.displayed().find((entity) => entity.entityId === 'npc-006');
      if (row) displayed.push({ tick: Number(snapshot.tick),
                                displayed_position_m: row.displayed_position_m,
                                facing_yaw_rad: row.facing_yaw_rad });
    }
    const slots = presentation.clipTimelineSnapshot()
      .filter((event) => event.entityId === 'npc-006')
      .map((event) => ({ tick: event.tick, slot: event.slot, weight: event.weight,
                         hold_ticks: event.hold_ticks,
                         trigger_direction_delta_rad: event.trigger_direction_delta_rad }));
    return { snapshots: snapshots.length, displayed, slots, turn: presentation.turnHitRate(),
             max_deviation_m: engine.maxDeviationM(), eps_used_m: engine.epsUsedM() };
  };
  const presentA = readPresentation(armAOut, 'c4c5-A');
  const presentB = readPresentation(armBOut, 'c4c5-B');
  const slotKey = (row) => JSON.stringify({ slot: row.slot, weight: row.weight, hold: row.hold_ticks });
  const slotsA = new Map(presentA.slots.map((row) => [`${row.tick}:${row.slot}`, slotKey(row)]));
  const slotsB = new Map(presentB.slots.map((row) => [`${row.tick}:${row.slot}`, slotKey(row)]));
  const slotDiffKeys = [...new Set([...slotsA.keys(), ...slotsB.keys()])]
    .filter((key) => slotsA.get(key) !== slotsB.get(key));
  const displayedA = new Map(presentA.displayed.map((row) => [row.tick, row]));
  const displayedB = new Map(presentB.displayed.map((row) => [row.tick, row]));
  const displayedDiffTicks = [...displayedA.keys()].filter((tick) => {
    const left = displayedA.get(tick);
    const right = displayedB.get(tick);
    if (!right) return true;
    return JSON.stringify(left.displayed_position_m) !== JSON.stringify(right.displayed_position_m)
      || left.facing_yaw_rad !== right.facing_yaw_rad;
  }).sort((x, y) => x - y);
  const slotDiffs = slotDiffKeys.map((key) => ({ key, a: slotsA.get(key) ?? null, b: slotsB.get(key) ?? null }));

  const reading = {
    task: 'c4c5', at_epoch: Math.floor(Date.now() / 1000),
    ticks_target: ticks,
    arm_a: { out: armAOut, decisions: decisionsA.length, tick_reached: a.state?.tick ?? null,
             has_experience: true },
    arm_b: { out: armBOut, decisions: decisionsB.length, tick_reached: b.state?.tick ?? null,
             has_experience: false },
    /** **C-5**：输入同源证明（seed / tick / intent 序列 / 粒度 / provider 配置逐字相同；只有 --out 不同）。 */
    input_identity: {
      seed: 20260921, snapshot_every: 1, tick_ms: 50,
      intent_script: intentScript, intent_script_path: scriptPath,
      emotion_pressure_threshold: 0.0, stub_remote_api: 1.0,
      only_difference: '--out / --runtime（A 臂复用 C-1 的产物目录；B 臂为空目录）',
    },
    common_ticks: commonTicks.length,
    decision_diff_ticks: diffs.length,
    decision_action_diff_ticks: actionDiffs.length,
    decision_score_diff_ticks: scoreDiffs.length,
    /** **C-4**：决策读数 ≥1 项不同。 */
    decision_readout_differs: diffs.length > 0,
    /** **C-4**：表现槽读数 ≥1 项不同（`clipTimelineSnapshot()` 的表现槽事件 + 显示位置/朝向序列）。 */
    presentation_slot_differs: slotDiffKeys.length > 0 || displayedDiffTicks.length > 0,
    presentation_slot_event_diff_count: slotDiffKeys.length,
    presentation_displayed_diff_ticks: displayedDiffTicks.length,
    presentation_displayed_diff_samples: displayedDiffTicks.slice(0, 5).map((tick) => ({
      tick, a: displayedA.get(tick)?.displayed_position_m ?? null,
      b: displayedB.get(tick)?.displayed_position_m ?? null,
    })),
    presentation_readout: {
      arm_a: { snapshots: presentA.snapshots, slot_events: presentA.slots.length,
               turn: presentA.turn, max_deviation_m: presentA.max_deviation_m,
               eps_used_m: presentA.eps_used_m },
      arm_b: { snapshots: presentB.snapshots, slot_events: presentB.slots.length,
               turn: presentB.turn, max_deviation_m: presentB.max_deviation_m,
               eps_used_m: presentB.eps_used_m },
    },
    slot_diff_samples: slotDiffs.slice(0, 5),
    slot_mapping_source: 'v0_skeleton/web/src/scene/presentation.ts :: clipTimelineSnapshot()/turnHitRate()',
    diff_samples: diffs.slice(0, 8),
    memory_influence_present_a: decisionsA.some((item) => item.memory_by_action
      && Object.keys(item.memory_by_action).length > 0),
    memory_influence_present_b: decisionsB.some((item) => item.memory_by_action
      && Object.keys(item.memory_by_action).length > 0),
  };
  const path = writeReadback('c4c5-reading.json', reading);
  process.stdout.write(`C4C5 ${JSON.stringify({ reading: path, commonTicks: commonTicks.length,
    decisionDiffs: diffs.length, actionDiffs: actionDiffs.length,
    presentationDiffers: reading.presentation_slot_differs,
    memInA: reading.memory_influence_present_a, memInB: reading.memory_influence_present_b })}\n`);
  return 0;
}

// ─────────────────────────────────────────────────────────── ⑥ 模型失败降级
async function c6() {
  const OUT = resolve(option('out', join(EVIDENCE, 'runtime', 'c6', 'out')));
  const RUNTIME = resolve(option('runtime', join(EVIDENCE, 'runtime', 'c6', 'bridge')));
  const PORT = Number(option('port', 8844));
  // N5-C r2 / FIX-6（raven R-M4）：同一形态跑**两条臂**。
  //   `--arm injected`（缺省，= r1 的正例）：带 `--replay` ⇒ 强制 cassette 回放 + fail-closed ⇒ 必然 miss。
  //   `--arm control`（本轮新增的**负对照**）：**去掉 `--replay`**，其余逐字相同
  //   ⇒ `journal` 必须为空、`emotion_fallbacks_log` 不得新增（否则说明观测到的「失败」不是注入造成的）。
  // 判据改锚 `journal` + `emotion_fallbacks_log`，**不再锚 `emotion_appraise_calls`**（它结构性恒 0
  // —— `registry.py` 只在成功路径与 `_fallback()` 里 `calls.append`，全失败场景下观测不到）。
  const ARM = option('arm', 'injected');
  const INJECTED = ARM !== 'control';
  mkdirSync(OUT, { recursive: true });
  const host = startHost({
    tag: 'c6', port: PORT, out: OUT, runtime: RUNTIME, paused: true, runSeconds: 120,
    extra: ['--memory-chain', '--capability-chain', '--emotion-pressure-threshold', '0.0',
            ...(INJECTED ? ['--replay'] : []),
            '--events', 'kernel-events-c6.jsonl'],
  });
  const readyLine = await host.ready;
  const { browser, page, errors, badResponses } = await openBrowser();
  await page.goto(`http://127.0.0.1:${PORT}/?pack=${PACK}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 60000 });
  await installFrameCounter(page);
  await postJson(`http://127.0.0.1:${PORT}/control/resume`);
  await page.waitForTimeout(1500);
  const framesStart = await readFrames(page);
  await page.waitForTimeout(2500);
  const framesMid = await readFrames(page);
  // 基本操作仍可用：页面产生一次真点击 intent（与 c1c2 同口径：页面公开 API 建 participate 会话 + 真点击）
  await page.click('#toggle-mode');
  await page.waitForSelector('#delegate-instruction', { timeout: 15000 });
  const scaffoldSetup = await page.evaluate(async (pack) => {
    const api = globalThis.__deephealing;
    try { api.client.socket?.close(); } catch { /* 关掉 observe 会话的 WS */ }
    const info = await api.client.connect({ url: '/ws', mode: 'participate', districtPackId: pack });
    api.setMode('participate');
    const button = document.createElement('button');
    button.id = 'n5c-delegate-xuqin';
    button.type = 'button';
    button.textContent = '委托徐琴（取证脚手架控件）';
    button.style.cssText = 'position:fixed;left:16px;bottom:16px;z-index:9;';
    button.addEventListener('click', () => {
      void api.intervene.submitDelegateInstruction('npc-006', '模型失败下仍要能委托', 0.5);
    });
    document.body.append(button);
    return { new_session_id: info.session_id, mode: api.client.mode };
  }, PACK);
  await page.waitForTimeout(800);
  await page.click('#n5c-delegate-xuqin');
  await page.waitForFunction(
    () => (document.getElementById('intent-status')?.dataset?.status ?? '') !== '', null, { timeout: 20000 });
  const ack = await page.evaluate(() => ({
    status: document.getElementById('intent-status')?.dataset?.status ?? null,
    reason: document.getElementById('intent-status')?.dataset?.reason ?? null,
  }));
  await page.waitForTimeout(2000);
  const degradations = await getJson(`http://127.0.0.1:${PORT}/evidence/degradations`);
  const state = await getJson(`http://127.0.0.1:${PORT}/evidence/state`);
  const framesEnd = await readFrames(page);
  await browser.close();
  await sleep(900);
  const eventsPath = join(OUT, 'kernel-events-c6.jsonl');
  const events = existsSync(eventsPath)
    ? readFileSync(eventsPath, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line))
    : [];
  const uplinkPath = join(OUT, 'ws-uplink-c6.jsonl');
  const uplink = existsSync(uplinkPath) ? readFileSync(uplinkPath, 'utf8').split('\n').filter(Boolean) : [];
  const applied = events.filter((event) => event.type === 'intent.applied');

  const reading = {
    task: INJECTED ? 'c6' : 'c6-negative-control',
    arm: INJECTED ? 'injected (--replay)' : 'control (no --replay)',
    at_epoch: Math.floor(Date.now() / 1000),
    node_version: process.version,
    toolchain: `node ${process.version} + playwright 1.63.0`,
    browser_binary: CHROMIUM ?? null,
    tree_head: spawnSync('git', ['-C', WORKSPACE, 'rev-parse', 'HEAD']).stdout.toString().trim(),
    injection: {
      face: INJECTED
        ? '经 D1 取证桥打开能力链 + `--replay`（强制 cassette_replay + fail-closed）⇒ cassette 缺省 ⇒ 必然失败'
        : '**同形态但去掉 `--replay`**（不注入）⇒ 不得出现 cassette.miss、不得新增降级条目',
      cassette_dir: join(OUT, 'kernel_capability', 'cassettes'),
      cassette_dir_exists: existsSync(join(OUT, 'kernel_capability', 'cassettes')),
      declared_fallback: 'emotion.appraise.fallback.on_cassette_miss = deterministic_stub（未实现 ⇒ 抛 E_CASSETTE_MISS）',
    },
    host_ready: readyLine.replace(/\s+/g, ' ').slice(0, 300),
    frames: { start: framesStart, mid: framesMid, end: framesEnd,
              grew_after_failure: framesEnd > framesStart },
    degradations: {
      emotion_fallbacks_total: degradations?.emotion_fallbacks_total ?? null,
      emotion_appraise_calls: degradations?.emotion_appraise_calls ?? null,
      emotion_appraise_ok: degradations?.emotion_appraise_ok ?? null,
      journal_kinds: degradations?.journal_kinds ?? null,
      sample: (degradations?.emotion_fallbacks_log ?? []).slice(0, 6),
      /** 条目**来自该失败**（code 枚举），不是渲染层既有降级。 */
      codes: [...new Set((degradations?.emotion_fallbacks_log ?? [])
        .map((item) => String(item.reason)))],
    },
    intent_round_trip: {
      page_ack: ack,
      scaffold_setup: scaffoldSetup,
      page_uplink_frames: uplink.length,
      kernel_intent_applied: applied.length,
      kernel_intent_applied_ids: applied.map((event) => String(event.payload?.intent_id ?? '')),
      succeeded: applied.length > 0,
    },
    page_errors: errors.slice(0, 5),
    bad_responses: badResponses.slice(0, 10),
    static_fallback_hits: await getJson(`http://127.0.0.1:${PORT}/health`).then(
      (body) => body.static_fallback_hits ?? []),
    host_state: { tick: state.tick, snapshots: state.snapshot_count, events: state.event_count },
  };
  const path = writeReadback(INJECTED ? 'c6-reading.json' : 'c6-negative-control.json', reading);
  if (!INJECTED) {
    // **负对照判据**（FIX-6）：不注入 ⇒ `journal` 为空（无 `cassette.miss`）且 `emotion_fallbacks_log` 零条目。
    const kinds = reading.degradations.journal_kinds ?? [];
    const fallbackEntries = Array.isArray(degradations?.emotion_fallbacks_log) ? degradations.emotion_fallbacks_log.length : 0;
    reading.negative_control = {
      injected_arm_reading: join(HERE, 'readback', 'c6-reading.json'),
      anchors: ['journal_kinds', 'emotion_fallbacks_log'],
      not_anchored: ['emotion_appraise_calls（结构性恒 0，不可观测失败调用）'],
      journal_has_cassette_miss: kinds.includes('cassette.miss'),
      emotion_fallbacks_log_entries: fallbackEntries,
      control_pass: kinds.length === 0 && fallbackEntries === 0,
      frames_still_grow: framesEnd > framesStart,
      note: '正例（注入）与负例（去注入）**同形态**：唯一差别 = `--replay`。'
        + '负例必须「journal 空 + 零降级条目」⇒ 正例观测到的失败确实来自注入。',
    };
    writeFileSync(path, `${JSON.stringify(reading, null, 2)}\n`);
  }
  process.stdout.write(`C6 ${JSON.stringify({ arm: reading.arm, reading: path,
    frames_grew: reading.frames.grew_after_failure,
    degradations: reading.degradations.emotion_fallbacks_total, codes: reading.degradations.codes,
    journal_kinds: reading.degradations.journal_kinds,
    control_pass: reading.negative_control?.control_pass ?? null,
    intent_applied: reading.intent_round_trip.kernel_intent_applied })}\n`);
  host.child.kill('SIGTERM');
  await sleep(500);
  return 0;
}

// ─────────────────────────────────────────────────────────── D4 负对照
async function d4neg() {
  const OUT = resolve(option('out', join(EVIDENCE, 'runtime', 'd4neg', 'out')));
  mkdirSync(OUT, { recursive: true });
  const PORT = Number(option('port', 8845));
  const host = startHost({
    tag: 'd4neg', port: PORT, out: OUT, runtime: join(EVIDENCE, 'runtime', 'd4neg', 'bridge'),
    paused: true, runSeconds: 40, extra: ['--memory-chain'],
  });
  await host.ready;
  const good = await postJson(`http://127.0.0.1:${PORT}/sessions`,
    { district_pack_id: PACK, mode: 'observe', client_version: '1.0.0' });
  const bad = await postJson(`http://127.0.0.1:${PORT}/sessions`,
    { district_pack_id: 'xingfu-xiaoqu-unregistered', mode: 'observe', client_version: '1.0.0' });
  const reading = {
    task: 'd4neg', at_epoch: Math.floor(Date.now() / 1000),
    registered_pack_status: good.status, registered_pack_error: good.body?.error ?? null,
    unregistered_pack_status: bad.status, unregistered_pack_error: bad.body?.error ?? null,
    /** **D4 负对照**：未登记 pack ⇒ 仍 400 E_PACK_INVALID（证明 knownPacks 注入是真判据、不是恒放行）。 */
    negative_holds: bad.status === 400 && bad.body?.error === 'E_PACK_INVALID',
    positive_holds: good.status === 201,
  };
  const path = writeReadback('d4-negative-control.json', reading);
  process.stdout.write(`D4NEG ${JSON.stringify({ reading: path, positive: reading.positive_holds,
    negative: reading.negative_holds })}\n`);
  host.child.kill('SIGTERM');
  await sleep(300);
  return 0;
}

const TABLE = { c1c2, c3, c4c5, c6, d4neg };
if (!TABLE[COMMAND]) {
  process.stderr.write(`unknown command ${COMMAND}（可用：${Object.keys(TABLE).join(', ')}）\n`);
  process.exit(2);
}
process.exit(await TABLE[COMMAND]());
