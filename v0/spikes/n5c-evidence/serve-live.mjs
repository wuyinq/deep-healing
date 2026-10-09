#!/usr/bin/env node
/**
 * N5 阶段 C · **取证宿主**（`v0/spikes/n5c-evidence/**`，**非交付面**）。
 *
 * 装配（全部用交付面的既有实现，**零重写**）：
 *   - **真内核**：`bridge_mem/kernel_bridge_mem.py`（= 冻结桥 + 记忆链/能力链接线，见 `bridge_mem.diff`）；
 *   - **真会话层**：`02_source/v0_skeleton/session/src/server.js` 的 `SessionServer`（原样 import）；
 *   - **真传输**：`ws` WebSocketServer + `POST /sessions`（HTTP）；
 *   - **真渲染层**：`v0/.build/web`（由交付面 `web/**` 经 `vite build` 产出）；
 *   - **只读实时通道**：`/live/*` 由**同一个桥**的快照投影提供（与 (A) 链**同一 tick 空间**，D5）。
 *
 * 本脚手架补三件交付面够不着的事（逐条登记）：
 *   1. 冻结桥不传 `memory_store`/`capability_registry` ⇒ 用 `bridge_mem`（D1）；
 *   2. `server.js:37` 的 `KNOWN_PACKS` 不含徐琴包 ⇒ 宿主写死
 *      `new SessionServer({ kernelClient, knownPacks: new Set([packId]) })`（D4；负对照见 `--pack-unregistered`）；
 *   3. `--snapshot-every N` **同时**作用于桥与 `SessionServer.snapshotEveryTicks`（D5）。
 *
 * 硬边界：交付树一个字节都不写；一切产物落 `--out` / `--runtime`（均在 `v0/spikes/n5c-evidence/**`）。
 * 上行帧落盘（D11/R-11）：WS 收到的每一帧**原样**写 `<out>/ws-uplink.jsonl`（含页面侧提交的 `intent_id`）。
 */

import { spawn } from 'node:child_process';
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, normalize, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

import { WebSocketServer } from 'ws';

import { SessionServer } from '../../02_source/v0_skeleton/session/src/server.js';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const WORKSPACE = join(HERE, '..', '..');
const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};
const flag = (name) => args.includes(`--${name}`);

const WEB = resolve(option('web', join(WORKSPACE, '.build', 'web')));
const SOURCE = resolve(option('source', join(WORKSPACE, '02_source')));
const PACK = option('pack', 'xingfu-xiaoqu-xuqin');
const PORT = Number(option('port', 8790));
const TICK_MS = Number(option('tick-ms', 100));
const SEED = Number(option('seed', 20260921));
// **D5**：一个旋钮同时作用于桥与 SessionServer（生效值进 serve-summary）。
const SNAPSHOT_EVERY = Number(option('snapshot-every', 1));
const TICKS = Number(option('ticks', 100000));
const TAG = option('tag', 'run');
const OUT = resolve(option('out', join(WORKSPACE, 'spikes', 'n5c-evidence', 'readback', TAG)));
const RUNTIME = resolve(option('runtime', join(WORKSPACE, 'spikes', 'n5c-evidence', 'runtime', TAG)));
const MEMORY_CHAIN = flag('memory-chain') || option('memory-chain', 'true') === 'true';
const CAPABILITY_CHAIN = flag('capability-chain') || option('capability-chain', 'true') === 'true';
const REPLAY = flag('replay') || option('replay', 'false') === 'true';
const EMOTION_THRESHOLD = option('emotion-pressure-threshold', '0.0');
const STUB_REMOTE_API = option('stub-remote-api', null);
const EVENTS_NAME = option('events', null);
const INTENT_SCRIPT_ARG = option('intent-script', null);
const REGISTERED_PACKS = option('registered-packs', null);
// 注意：`--start-paused` 只按**取值**解析（`--start-paused false` 必须真的不暂停）——
// 用 `flag()` 会把「出现了这个 token」误当 true（实测踩过）。
const START_PAUSED = option('start-paused', 'true') === 'true';
// `--disable-static-fallback`：**关闭**「产物缺失时回落交付树」的取证回落（A-8a 的「回落盒体」批次
// 与「构建产物只含 vite 产物」的读数的**注入面**）。
const DISABLE_STATIC_FALLBACK = option('disable-static-fallback', 'false') === 'true';
const RUN_SECONDS = Number(option('run-seconds', 600));

mkdirSync(OUT, { recursive: true });
mkdirSync(RUNTIME, { recursive: true });

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.hdr': 'image/vnd.radiance',
  '.map': 'application/json', '.glb': 'model/gltf-binary', '.txt': 'text/plain; charset=utf-8',
};

// ─────────────────────────────────────────────────────────── 桥（真内核 + 记忆链/能力链）
const bridgeArgs = [
  '-B', join(HERE, 'bridge_mem', 'kernel_bridge_mem.py'),
  '--kernel-src', join(SOURCE, 'v0_skeleton', 'kernel'),
  '--pack-src', join(SOURCE, 'v0_skeleton', 'districts', PACK),
  '--runtime-dir', RUNTIME,
  '--seed', String(SEED),
  '--snapshot-every', String(SNAPSHOT_EVERY),
  '--ticks', String(TICKS),
  '--out', OUT,
];
if (MEMORY_CHAIN) bridgeArgs.push('--memory-chain');
if (CAPABILITY_CHAIN) bridgeArgs.push('--capability-chain');
if (REPLAY) bridgeArgs.push('--replay');
if (CAPABILITY_CHAIN) bridgeArgs.push('--emotion-pressure-threshold', String(EMOTION_THRESHOLD));
if (STUB_REMOTE_API) bridgeArgs.push('--stub-remote-api', String(STUB_REMOTE_API));
if (EVENTS_NAME) bridgeArgs.push('--events', String(EVENTS_NAME));
const CHECKPOINT_DIR = option('checkpoint-dir', null);
if (CHECKPOINT_DIR) bridgeArgs.push('--checkpoint-dir', String(CHECKPOINT_DIR));
const EVENTS_PATH = join(OUT, EVENTS_NAME ?? 'kernel-events.jsonl');

const child = spawn('python3', bridgeArgs, {
  stdio: ['pipe', 'pipe', 'pipe'], env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
});

const state = {
  meta: null, latestSnapshot: null, latestTickMeta: null,
  kinds: {}, eventCount: 0, snapshotCount: 0, deltaCount: 0, tickMetaCount: 0,
  stepping: !START_PAUSED, driverExited: false,
  intentAcks: [], tasksAck: null, degradationsAck: null,
  uplinkFrames: 0, scriptedIntents: 0, staticFallbackHits: [],
};
const recordsPath = join(OUT, `bridge-records-${TAG}.jsonl`);
const uplinkPath = join(OUT, `ws-uplink-${TAG}.jsonl`);
const downlinkPath = join(OUT, `ws-downlink-${TAG}.jsonl`);
const intentAckWaiters = [];
const voidWaiters = [];
const snapshotWaiters = [];
const extraWaiters = { tasks: [], degradations: [] };

const INTENT_SCRIPT = INTENT_SCRIPT_ARG ? JSON.parse(readFileSync(resolve(INTENT_SCRIPT_ARG), 'utf8')) : null;

/** 内核状态查询适配器（`SessionServer` 用；**只读**，不写世界）。 */
const kernelAdapter = {
  async requestSnapshot() {
    if (state.driverExited) return null;
    return new Promise((resolveSnapshot) => {
      snapshotWaiters.push(resolveSnapshot);
      child.stdin.write(`${JSON.stringify({ cmd: 'snapshot' })}\n`);
      setTimeout(() => resolveSnapshot(null), 5000);
    });
  },
  /** 上行：会话层 → 桥 → 内核入口（`server.js` 的 onTickBoundary 走这条路）。 */
  async submitIntent(sessionId, intent, { mode = 'participate', impactBudgetRemaining } = {}) {
    if (state.driverExited) {
      return { id: intent.id, status: 'rejected', reason: 'E_KERNEL_UNAVAILABLE', detail: 'bridge exited' };
    }
    const ack = new Promise((resolveAck) => intentAckWaiters.push(resolveAck));
    child.stdin.write(`${JSON.stringify({
      cmd: 'intent', mode, intent: { ...intent, session_id: sessionId },
      impact_budget_remaining: impactBudgetRemaining,
    })}\n`);
    return ack;
  },
  async voidPendingIntents(sessionId, reasonCode = 'E_BUDGET_EXHAUSTED') {
    if (state.driverExited) return { voided: [], count: 0, pending_after: null, bridge: 'unavailable' };
    const ack = new Promise((resolveVoid) => voidWaiters.push(resolveVoid));
    const timeout = new Promise((resolveTimeout) => setTimeout(() => resolveTimeout(null), 5000));
    child.stdin.write(`${JSON.stringify({ cmd: 'void_intents', session_id: sessionId, reason_code: reasonCode })}\n`);
    const record = await Promise.race([ack, timeout]);
    if (!record) return { voided: [], count: 0, pending_after: null, bridge: 'timeout' };
    return { ...record, bridge: 'ok' };
  },
};

function askBridge(kind) {
  return new Promise((resolveAsk) => {
    extraWaiters[kind].push(resolveAsk);
    child.stdin.write(`${JSON.stringify({ cmd: kind })}\n`);
    setTimeout(() => resolveAsk(null), 5000);
  });
}

const sessionServer = new SessionServer({
  kernelClient: kernelAdapter,
  snapshotEveryTicks: SNAPSHOT_EVERY,
  // **D4**：徐琴包不在 `server.js` 的 KNOWN_PACKS 白名单内 ⇒ 宿主写死注入（负对照见 `--registered-packs`）。
  knownPacks: new Set(REGISTERED_PACKS ? REGISTERED_PACKS.split(',') : [PACK]),
});

const sockets = new Map();
const reader = createInterface({ input: child.stdout });
const bridgeRecords = [];
reader.on('line', (line) => {
  if (!line.trim()) return;
  let record;
  try {
    record = JSON.parse(line);
  } catch {
    return;
  }
  bridgeRecords.push(record);
  appendFileSync(recordsPath, `${JSON.stringify(record)}\n`);
  const kind = String(record.kind ?? '');
  state.kinds[kind] = (state.kinds[kind] ?? 0) + 1;
  if (kind === 'bridge_meta') {
    state.meta = record;
    process.stdout.write(`BRIDGE_READY ${JSON.stringify({
      memory_chain: record.memory_chain, capability_chain: record.capability_chain,
      out_dir: record.out_dir, snapshot_every: record.snapshot_every,
    })}\n`);
    return;
  }
  if (kind === 'intent_ack') {
    state.intentAcks.push(record);
    const waiter = intentAckWaiters.shift();
    if (waiter) waiter(record);
    return;
  }
  if (kind === 'void_ack') {
    const waiter = voidWaiters.shift();
    if (waiter) waiter(record);
    return;
  }
  if (kind === 'snapshot_ack') {
    const waiter = snapshotWaiters.shift();
    if (waiter) waiter(record);
    return;
  }
  if (kind === 'tasks_ack' || kind === 'degradations_ack') {
    const key = kind === 'tasks_ack' ? 'tasks' : 'degradations';
    if (key === 'tasks') state.tasksAck = record; else state.degradationsAck = record;
    const waiter = extraWaiters[key].shift();
    if (waiter) waiter(record);
    return;
  }
  if (kind === 'snapshot') {
    state.latestSnapshot = record;
    state.snapshotCount += 1;
    // **只读实时通道**（与 (A) 链同一桥 ⇒ 同一 tick 空间）：把快照投影推给 SSE 订阅者。
    // 缺了这一步，页面的 `live.stateProjection()` 会停在连上时的空帧（实测 `acSnapshot().npcs == []`）。
    const payload = livePayload();
    for (const response of liveStreams) {
      response.write(`event: state\ndata: ${JSON.stringify(payload)}\n\n`);
    }
  }
  if (kind === 'tick_meta') {
    state.latestTickMeta = record;
    state.tickMetaCount += 1;
  }
  if (kind === 'delta') state.deltaCount += 1;
  if (kind === 'event') state.eventCount += 1;
  if (['snapshot', 'delta', 'tick_meta', 'event'].includes(kind)) {
    const result = sessionServer.broadcastKernelRecord(record);
    if (!result.ok) process.stdout.write(`BROADCAST_REJECTED ${kind} ${result.reason} ${result.detail}\n`);
    pump();
  }
});
child.stderr.on('data', (chunk) => process.stdout.write(`BRIDGE_STDERR ${String(chunk).trim()}\n`));
child.on('exit', (code) => {
  state.driverExited = true;
  process.stdout.write(`BRIDGE_EXIT code=${code}\n`);
});

/** 下行箱 → WebSocket（`SessionServer.broadcast` 只入队，出队要调用方做）。 */
function pump() {
  for (const sessionId of [...sessionServer.sessions.keys()]) {
    const socket = sockets.get(sessionId);
    if (!socket || socket.readyState !== 1) continue;
    for (const message of sessionServer.drainOutbox(sessionId)) socket.send(JSON.stringify(message));
  }
}
setInterval(pump, 50);

// ─────────────────────────────────────────────────────────── HTTP + WS
const liveStreams = new Set();
function sendJson(response, code, body) {
  response.writeHead(code, { 'content-type': 'application/json; charset=utf-8' });
  response.end(JSON.stringify(body));
}
function packFile(...parts) {
  return join(SOURCE, 'v0_skeleton', 'districts', PACK, ...parts);
}

function livePayload() {
  const snapshot = state.latestSnapshot;
  return {
    tick: snapshot?.tick ?? 0,
    clock: null, world_day: null, timezone: null,
    state_hash: snapshot?.state_hash ?? null,
    event_chain_hash: null,
    observers: liveStreams.size, read_only: true,
    state: snapshot?.state ?? null,
    provided_by: 'spikes/n5c-evidence/serve-live.mjs (same bridge as the (A) chain; same tick space)',
  };
}

const http = createServer(async (request, response) => {
  const url = new URL(request.url, `http://127.0.0.1:${PORT}`);
  const path = url.pathname;
  if (request.method === 'POST' && path === '/sessions') {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    let body = {};
    try { body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'); } catch { body = {}; }
    const created = await sessionServer.createSession(body);
    sendJson(response, created.status, created.body);
    return;
  }
  if (path === '/health') {
    sendJson(response, 200, {
      ok: true, sessions: sessionServer.sessions.size, pack: PACK, web: WEB,
      ticks: state.tickMetaCount, snapshots: state.snapshotCount, events: state.eventCount,
      stepping: state.stepping, uplink_frames: state.uplinkFrames, kinds: state.kinds,
      static_fallback_hits: [...new Set(state.staticFallbackHits)].sort(),
    });
    return;
  }
  // ── 取证读数（**只读**；不写世界、不推进 tick）
  if (path === '/evidence/state') {
    sendJson(response, 200, {
      tick: state.latestTickMeta?.tick ?? 0,
      state_hash: state.latestSnapshot?.state_hash ?? null,
      event_chain_hash: state.latestTickMeta?.event_chain_hash ?? null,
      snapshot_count: state.snapshotCount, tick_meta_count: state.tickMetaCount,
      delta_count: state.deltaCount, event_count: state.eventCount,
      sessions: sessionServer.sessions.size, stepping: state.stepping,
      uplink_frames: state.uplinkFrames, scripted_intents: state.scriptedIntents,
      intent_acks: state.intentAcks.slice(-20),
      bridge_meta: state.meta,
    });
    return;
  }
  if (path === '/evidence/tasks') { sendJson(response, 200, await askBridge('tasks') ?? {}); return; }
  if (path === '/evidence/degradations') { sendJson(response, 200, await askBridge('degradations') ?? {}); return; }
  if (path === '/evidence/snapshot') {
    const snapshot = await new Promise((resolveSnapshot) => {
      snapshotWaiters.push(resolveSnapshot);
      child.stdin.write(`${JSON.stringify({ cmd: 'snapshot' })}\n`);
      setTimeout(() => resolveSnapshot(null), 5000);
    });
    sendJson(response, 200, snapshot ?? {});
    return;
  }
  if (request.method === 'POST' && path === '/control/intent') {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
    const sessionId = [...sessionServer.sessions.keys()].sort().at(-1);
    if (!sessionId) { sendJson(response, 409, { error: 'E_SESSION_UNKNOWN' }); return; }
    const result = await sessionServer.onClientMessage(sessionId, JSON.stringify(body));
    pump();
    sendJson(response, 200, { session_id: sessionId, messages: result.messages });
    return;
  }
  if (path === '/control/state') {
    sendJson(response, 200, { stepping: state.stepping, tick: state.latestTickMeta?.tick ?? 0,
                              events: state.eventCount, sessions: sessionServer.sessions.size });
    return;
  }
  if (request.method === 'POST' && (path === '/control/pause' || path === '/control/resume')) {
    state.stepping = path === '/control/resume';
    sendJson(response, 200, { stepping: state.stepping, tick: state.latestTickMeta?.tick ?? 0 });
    return;
  }
  // ── 只读实时通道（与 (A) 链**同一桥** ⇒ 同一 tick 空间）
  if (path === '/live/health' || path === '/live/state' || path === '/live/meta') {
    const live = livePayload();
    if (path === '/live/meta') {
      sendJson(response, 200, { pack_id: PACK, seed: SEED, observers: liveStreams.size,
                                max_observers: 8, endpoints: ['/live/health', '/live/state', '/live/stream'],
                                same_tick_space_as_a_chain: true, snapshot_every_ticks: SNAPSHOT_EVERY });
      return;
    }
    if (path === '/live/state') { sendJson(response, 200, live); return; }
    sendJson(response, 200, { listening: true, observers: liveStreams.size, tick: live.tick,
                              handler_errors: 0, http_inflight: liveStreams.size });
    return;
  }
  if (path === '/live/stream') {
    response.writeHead(200, { 'content-type': 'text/event-stream; charset=utf-8',
                              'cache-control': 'no-store', connection: 'keep-alive' });
    liveStreams.add(response);
    response.write(`event: state\ndata: ${JSON.stringify(livePayload())}\n\n`);
    request.on('close', () => liveStreams.delete(response));
    return;
  }
  // ── pack 数据（世界观 / NPC 档案；只读，来自交付面内容包）
  const packMatch = path.match(/^\/packs\/([A-Za-z0-9_-]{1,64})\/(worldview\.json|npcs\/[A-Za-z0-9_-]{1,64}\.json)$/);
  if (packMatch) {
    try {
      const data = readFileSync(join(SOURCE, 'v0_skeleton', 'districts', packMatch[1], packMatch[2]));
      response.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
      response.end(data);
    } catch {
      sendJson(response, 404, { error: 'E_PACK_INVALID', pack_id: packMatch[1], path: packMatch[2] });
    }
    return;
  }
  // ── 静态（**构建产物** `v0/.build/web`；`/assets/**` 由 vite 生成在同名目录下）
  // ⚠️ **取证脚手架的显式回落**：`vite build` **不搬运** `web/assets/**` 里未被 `import` 的静态件
  // （实测：`assets/character/xuqin-body.glb` 只是 `asset_binding.ts` 里的**字符串 URL** ⇒ 产物里
  // 不存在 ⇒ 真浏览器 404 ⇒ 人物回落盒体）。为让 A 类取证拿到**真 GLB**，本宿主在产物缺失时回落到
  // **交付树** `v0/02_source/v0_skeleton/web/**`，并把命中的路径逐条登记（`static-fallback-hits.json`）
  // ⇒ 缺口变成**可读证据**，不是被遮住。**这不构成「构建产物完整」的证据。**
  const relative = path === '/' ? '/index.html' : path;
  const safeRelative = normalize(relative).replace(/^([.]{2}[\\/])+/, '');
  const target = join(WEB, safeRelative);
  try {
    const data = readFileSync(target);
    response.writeHead(200, { 'content-type': MIME[extname(target)] ?? 'application/octet-stream' });
    response.end(data);
  } catch {
    const fallbackTarget = join(SOURCE, 'v0_skeleton', 'web', safeRelative);
    let served = false;
    if (!DISABLE_STATIC_FALLBACK) {
      try {
        const data = readFileSync(fallbackTarget);
        state.staticFallbackHits.push(safeRelative);
        writeFileSync(join(OUT, 'static-fallback-hits.json'),
          `${JSON.stringify({ count: state.staticFallbackHits.length, paths: [...new Set(state.staticFallbackHits)].sort() }, null, 2)}\n`);
        response.writeHead(200, { 'content-type': MIME[extname(fallbackTarget)] ?? 'application/octet-stream' });
        response.end(data);
        served = true;
      } catch { served = false; }
    } else {
      state.staticFallbackHits.push(`DISABLED:${safeRelative}`);
    }
    if (!served) {
      response.writeHead(404, { 'content-type': 'text/plain' });
      response.end('not found');
    }
  }
});

const wss = new WebSocketServer({ noServer: true });
http.on('upgrade', (request, socket, head) => {
  const url = new URL(request.url, `http://127.0.0.1:${PORT}`);
  const match = url.pathname.match(/^\/ws\/([A-Za-z0-9_-]+)$/);
  if (!match) { socket.destroy(); return; }
  wss.handleUpgrade(request, socket, head, (ws) => {
    sockets.set(match[1], ws);
    void sessionServer.primeSession(match[1]).then(() => {
      for (const message of sessionServer.drainOutbox(match[1])) {
        if (ws.readyState === 1) ws.send(JSON.stringify(message));
      }
    });
    ws.on('message', async (data) => {
      // **D11 / R-11**：页面侧上行帧**原样落盘**（外部锚：其 `intent_id` 必须出现在内核事件链）
      const text = data.toString();
      state.uplinkFrames += 1;
      appendFileSync(uplinkPath, `${JSON.stringify({ at_ms: Date.now(), session_id: match[1], frame: text })}\n`);
      const result = await sessionServer.onClientMessage(match[1], text);
      for (const message of result.messages) {
        // **下行帧落盘**（取证读数：会话层的权威回复，含 `intent_ack` 的 rejected 形态）
        appendFileSync(downlinkPath, `${JSON.stringify({ at_ms: Date.now(), session_id: match[1], frame: message })}\n`);
        if (ws.readyState === 1) ws.send(JSON.stringify(message));
      }
      pump();
    });
    ws.on('close', () => sockets.delete(match[1]));
  });
});

await new Promise((ready) => http.listen(PORT, '127.0.0.1', ready));
process.stdout.write(`SERVE_READY port=${PORT} web=${WEB} pack=${PACK} out=${OUT} runtime=${RUNTIME} `
  + `snapshot_every=${SNAPSHOT_EVERY} memory_chain=${MEMORY_CHAIN} capability_chain=${CAPABILITY_CHAIN}\n`);

// ─────────────────────────────────────────────────────────── 步进 + 收尾
const started = Date.now();
let scriptIndex = 0;
let tickBoundaryBusy = false;
const timer = setInterval(async () => {
  if (!state.stepping || state.driverExited || tickBoundaryBusy) return;
  tickBoundaryBusy = true;
  try {
    // **会话层的 tick 边界**：把队列里的意图交给内核入口（`server.js::onTickBoundary`）。
    // 缺了这一步，页面提交的意图永远停在会话队列里（*没有* `intent.applied`）。
    const nextTick = (state.latestTickMeta?.tick ?? 0) + 1;
    await sessionServer.onTickBoundary(nextTick);
    pump();
    child.stdin.write(`${JSON.stringify({ cmd: 'step', n: 1 })}\n`);
    if (INTENT_SCRIPT) {
      const due = INTENT_SCRIPT.filter((item) => Number(item.at_tick) <= state.tickMetaCount);
      while (scriptIndex < due.length) {
        const item = due[scriptIndex];
        const sessionId = [...sessionServer.sessions.keys()].sort().at(-1);
        if (!sessionId) break;
        state.scriptedIntents += 1;
        await sessionServer.onClientMessage(sessionId, JSON.stringify({
          t: 'intent', id: item.id, kind: 'delegate_instruction', target: item.target,
          payload: { instruction_text: item.text ?? '', urgency: 0.5 },
        }));
        pump();
        scriptIndex += 1;
      }
    }
  } catch (error) {
    process.stdout.write(`TICK_BOUNDARY_ERROR ${String(error)}\n`);
  } finally {
    tickBoundaryBusy = false;
  }
}, TICK_MS);

const deadline = started + RUN_SECONDS * 1000;
while (Date.now() < deadline) {
  await new Promise((wait) => setTimeout(wait, 500));
}
clearInterval(timer);
if (!state.driverExited) child.stdin.write(`${JSON.stringify({ cmd: 'stop' })}\n`);
await new Promise((wait) => setTimeout(wait, 800));
if (!state.driverExited) child.kill();
for (const response of liveStreams) {
  try { response.end(); } catch { /* 收尾不因局部异常扩大影响 */ }
}

const summary = {
  tag: TAG, pack: PACK, seed: SEED, port: PORT, web: WEB, source: SOURCE, out: OUT, runtime: RUNTIME,
  tick_ms: TICK_MS, snapshot_every: SNAPSHOT_EVERY, ticks_requested: TICKS,
  events_name: EVENTS_NAME ?? 'kernel-events.jsonl', events_path: EVENTS_PATH,
  memory_chain: MEMORY_CHAIN, capability_chain: CAPABILITY_CHAIN, replay: REPLAY,
  emotion_pressure_threshold: CAPABILITY_CHAIN ? Number(EMOTION_THRESHOLD) : null,
  stub_remote_api: STUB_REMOTE_API,
  ticks_reached: state.latestTickMeta?.tick ?? 0,
  final_state_hash: state.latestSnapshot?.state_hash ?? null,
  snapshots: state.snapshotCount, deltas: state.deltaCount, tick_metas: state.tickMetaCount,
  events: state.eventCount, sessions: sessionServer.sessions.size,
  uplink_frames: state.uplinkFrames, scripted_intents: state.scriptedIntents,
  intent_acks: state.intentAcks.slice(-40),
  driver_kinds: state.kinds, bridge_meta: state.meta,
};
writeFileSync(join(OUT, `serve-summary-${TAG}.json`), `${JSON.stringify(summary, null, 2)}\n`);
process.stdout.write(`SERVE_SUMMARY ${JSON.stringify({ tag: TAG, ticks_reached: summary.ticks_reached,
  snapshots: summary.snapshots, events: summary.events, uplink_frames: summary.uplink_frames,
  final_state_hash: summary.final_state_hash })}\n`);
process.exit(0);
