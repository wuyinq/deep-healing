#!/usr/bin/env node
/**
 * N2 实机验收服务端（spikes/** 脚手架，**非交付面**；沿用 M5.2 r2 的 AC-5 脚手架形状）。
 *
 * 与 `spikes/m52-live/serve.mjs` 的**唯一差别** = 四个路径常量（WEB / OUT / RUNTIME / DRIVER）
 * + 读数文件名 + 本节说明。驱动、会话层、渲染层全部沿用既有实现，**零重写**。
 *
 * 装配（全部用**交付面**的既有实现，不自研替代品）：
 *   - 真内核 + 真内容包：由 `tools/live_driver.py` 驱动（`WorldKernel` + 内核自带 `LiveWorld`）；
 *   - 真会话层：`02_source/v0_skeleton/session/src/server.js` 的 `SessionServer`（原样 import，
 *     **零改动**）——本文件只做「把驱动的记录喂给会话层」的搬运；
 *   - 真渲染层：`spikes/m52-live/build/web`（由交付面 `web/**` 经 `vite build` 产出）；
 *   - 只读实时通道：由驱动侧的 `LiveWorld` 投影提供 `/live/state|health|meta|stream`。
 *
 * 本脚手架**补三件交付面没有/够不着的事**（逐条登记在 `06` 的 GAP / 工具链节）：
 *   1. `kernel_bridge.py` 无 `event` emit 点 ⇒ 驱动逐行转发内核事件日志，喂给会话层；
 *   2. `KNOWN_PACKS` 硬编码（不含徐琴提案包）⇒ 本脚手架显式传入 pack 白名单；
 *   3. **步进闸门**（`/control/pause|resume`）：只控制「是否继续给驱动发 step 命令」，
 *      **不写世界状态** —— AC-5④ 的 reload 回读要的是「同一世界状态下 reload 前后一致」。
 *
 * 硬边界：交付面一个字节都不写；一切产物落 `--out` / `--runtime`（均在 spikes/m52-live/**）。
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

const WEB = resolve(option('web', join(WORKSPACE, 'spikes', 'n2-appearance', 'build', 'web')));
const SOURCE = resolve(option('source', join(WORKSPACE, '02_source')));
const PACK = option('pack', 'xingfu-xiaoqu-xuqin');
const PORT = Number(option('port', 8790));
const RUN_SECONDS = Number(option('run-seconds', 60));
const TICK_MS = Number(option('tick-ms', 250));
const TAG = option('tag', 'run');
const OUT = resolve(option('out', join(WORKSPACE, 'spikes', 'n2-appearance', 'readback')));
const RUNTIME = resolve(option('runtime', join(WORKSPACE, 'spikes', 'n2-appearance', 'runtime', `live-${TAG}`)));
const INJECT = option('inject', 'none');
const INJECT_AT = Number(option('inject-at', 20));
const SEED = Number(option('seed', 20260921));
const SNAPSHOT_EVERY = Number(option('snapshot-every', 25));
const MEMORY_WRITES = option('memory-writes', 'on');
// 驱动沿用 m52-live 的**已实证**实现（本脚手架不重写第二套驱动）
const DRIVER = join(HERE, '..', 'm52-live', 'tools', 'live_driver.py');
const BACKLOG_CAP = Number(option('backlog-cap', 4000));
//: 起步闸门：默认**先不推进**，由浏览器驱动在页面装配完成后 `POST /control/resume`
//: ⇒ 页面从 tick 0 起就收到全部事件（reload 前后的「事件条数」才可比，AC-5④）。
const START_PAUSED = args.includes('--start-paused') || option('start-paused', 'true') === 'true';

mkdirSync(OUT, { recursive: true });
mkdirSync(RUNTIME, { recursive: true });

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.png': 'image/png',
  '.map': 'application/json',
};

// ─────────────────────────────────────────────────────────── 驱动（真内核 + 真内容包）
const child = spawn('python3', [
  '-B', DRIVER,
  '--source', SOURCE, '--runtime', RUNTIME, '--pack', PACK,
  '--seed', String(SEED), '--snapshot-every', String(SNAPSHOT_EVERY),
  '--memory-writes', MEMORY_WRITES, '--inject', INJECT, '--inject-at', String(INJECT_AT),
], { stdio: ['pipe', 'pipe', 'pipe'], env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });

const state = {
  meta: null, latestLive: null, injection: null,
  ticks: [], eventBacklog: [], eventsSent: 0,
  kinds: {}, stepping: !START_PAUSED, stopped: false, driverExited: false,
};
const tickSeriesPath = join(OUT, `tick-series-${TAG}.json`);
const eventsPath = join(OUT, `events-${TAG}.jsonl`);

/** 内核状态查询适配器（会话层 `primeSession` 用；只读）。 */
const kernelAdapter = {
  async requestSnapshot() {
    if (state.driverExited) return null;
    return new Promise((resolveSnapshot) => {
      snapshotWaiters.push(resolveSnapshot);
      child.stdin.write(`${JSON.stringify({ cmd: 'snapshot' })}\n`);
      setTimeout(() => resolveSnapshot(null), 3000);
    });
  },
  async submitIntent() {
    // AC-5 的客户端是 observe 模式（本地即拒）；本脚手架**不**接管参与模式写通道 ⇒ 如实拒绝。
    return { status: 'rejected', reason: 'E_KERNEL_UNAVAILABLE',
             detail: 'AC-5 scaffold: intent channel is not wired (observe-only acceptance)' };
  },
  async voidPendingIntents() {
    return { voided: [], count: 0, pending_after: null, bridge: 'unavailable' };
  },
};
const snapshotWaiters = [];

const sessionServer = new SessionServer({
  kernelClient: kernelAdapter,
  snapshotEveryTicks: SNAPSHOT_EVERY,
  // KNOWN_PACKS 硬编码（交付面 `server.js:37`，不含徐琴提案包）⇒ 脚手架显式放行本次 pack。
  knownPacks: new Set([PACK, 'xingfu-xiaoqu', 'xingfu-xiaoqu-north']),
});

const sockets = new Map();
const reader = createInterface({ input: child.stdout });
reader.on('line', (line) => {
  if (!line.trim()) return;
  let record;
  try {
    record = JSON.parse(line);
  } catch {
    return;
  }
  const kind = String(record.kind ?? '');
  state.kinds[kind] = (state.kinds[kind] ?? 0) + 1;
  if (kind === 'bridge_meta' || kind === 'ready') {
    state.meta = { ...(state.meta ?? {}), [kind]: record };
    process.stdout.write(`DRIVER_READY ${JSON.stringify(record)}\n`);
    return;
  }
  if (kind === 'inject_result') {
    state.injection = record;
    process.stdout.write(`INJECTION ${JSON.stringify(record)}\n`);
    return;
  }
  if (kind === 'snapshot_ack') {
    const waiter = snapshotWaiters.shift();
    if (waiter) waiter(record);
    return;
  }
  if (kind === 'live') {
    state.latestLive = record;
    const tick = Number(record.tick ?? 0);
    const entry = { tick, state_hash: record.state_hash, event_chain_hash: record.event_chain_hash,
                    clock: record.clock, world_day: record.world_day };
    state.ticks.push(entry);
    for (const response of liveStreams) {
      response.write(`event: state\ndata: ${JSON.stringify({
        tick, clock: record.clock, world_day: record.world_day, timezone: record.timezone,
        state_hash: record.state_hash, event_chain_hash: record.event_chain_hash,
        observers: liveStreams.length, read_only: true, state: record.state,
      })}\n\n`);
      response.write(`event: clock\ndata: ${JSON.stringify({
        tick, clock: record.clock, timezone: record.timezone,
      })}\n\n`);
    }
    return;
  }
  if (kind === 'event') {
    state.eventBacklog.push(record.event);
    appendFileSync(eventsPath, `${JSON.stringify(record.event)}\n`);
  }
  if (['snapshot', 'delta', 'tick_meta', 'event'].includes(kind)) {
    const result = sessionServer.broadcastKernelRecord(record);
    if (!result.ok) process.stdout.write(`BROADCAST_REJECTED ${kind} ${result.reason} ${result.detail}\n`);
    pump();
  }
});

/**
 * 下行箱 → WebSocket（**必需**：`SessionServer.broadcast` 只入队，出队要调用方做）。
 * 缺了它，会话层每条消息只堆在下行箱里（到上限丢最旧），页面永远停在最初几 tick。
 */
function pump() {
  for (const sessionId of [...sessionServer.sessions.keys()]) {
    const socket = sockets.get(sessionId);
    if (!socket || socket.readyState !== 1) continue;
    for (const message of sessionServer.drainOutbox(sessionId)) socket.send(JSON.stringify(message));
  }
}
setInterval(pump, 100);
child.stderr.on('data', (chunk) => {
  process.stdout.write(`DRIVER_STDERR ${String(chunk).trim()}\n`);
});
child.on('exit', (code) => {
  state.driverExited = true;
  process.stdout.write(`DRIVER_EXIT code=${code}\n`);
});

// ─────────────────────────────────────────────────────────── HTTP + WS
const liveStreams = new Set();

function sendJson(response, code, body) {
  const text = JSON.stringify(body);
  response.writeHead(code, { 'content-type': 'application/json; charset=utf-8' });
  response.end(text);
}

function packFile(...parts) {
  return join(SOURCE, 'v0_skeleton', 'districts', PACK, ...parts);
}

const http = createServer(async (request, response) => {
  const url = new URL(request.url, `http://127.0.0.1:${PORT}`);
  const path = url.pathname;
  if (request.method === 'POST' && path === '/sessions') {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    let body = {};
    try {
      body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
    } catch {
      body = {};
    }
    const created = await sessionServer.createSession(body);
    sendJson(response, created.status, created.body);
    return;
  }
  if (path === '/health') {
    sendJson(response, 200, { ok: true, sessions: sessionServer.sessions.size, ticks: state.ticks.length,
                              events: state.eventBacklog.length, web: WEB, pack: PACK,
                              stepping: state.stepping, kinds: state.kinds });
    return;
  }
  // ── 只读实时通道（内核 LiveWorld 的投影；与 `cli live` 同一实现）
  if (path === '/live/health' || path === '/live/state' || path === '/live/meta') {
    if (!state.latestLive) {
      sendJson(response, 503, { error: 'E_KERNEL_UNAVAILABLE', detail: 'no live frame yet' });
      return;
    }
    const live = state.latestLive;
    if (path === '/live/state') {
      sendJson(response, 200, { tick: live.tick, clock: live.clock, world_day: live.world_day,
                                timezone: live.timezone, state_hash: live.state_hash,
                                event_chain_hash: live.event_chain_hash, observers: liveStreams.size,
                                read_only: true, state: live.state });
      return;
    }
    if (path === '/live/meta') {
      sendJson(response, 200, { pack_id: PACK, seed: SEED, pace_s_per_tick: 1.0,
                                observers: liveStreams.size, max_observers: 4,
                                endpoints: ['/live/health', '/live/meta', '/live/state', '/live/stream'],
                                provided_by: 'spikes/n2-appearance/serve.mjs (LiveWorld projection)' });
      return;
    }
    sendJson(response, 200, { listening: true, observers: liveStreams.size, max_observers: 4,
                              tick: live.tick, clock: live.clock, handler_errors: 0,
                              http_inflight: liveStreams.size });
    return;
  }
  if (path === '/live/stream') {
    response.writeHead(200, { 'content-type': 'text/event-stream; charset=utf-8',
                              'cache-control': 'no-store', connection: 'keep-alive' });
    liveStreams.add(response);
    if (state.latestLive) {
      const live = state.latestLive;
      response.write(`event: state\ndata: ${JSON.stringify({
        tick: live.tick, clock: live.clock, world_day: live.world_day, timezone: live.timezone,
        state_hash: live.state_hash, event_chain_hash: live.event_chain_hash,
        observers: liveStreams.size, read_only: true, state: live.state,
      })}\n\n`);
      response.write(`event: clock\ndata: ${JSON.stringify({
        tick: live.tick, clock: live.clock, timezone: live.timezone,
      })}\n\n`);
    }
    request.on('close', () => liveStreams.delete(response));
    return;
  }
  // ── 步进闸门（**只控制是否发 step 命令**，不写世界状态）
  if (path === '/control/state') {
    sendJson(response, 200, { stepping: state.stepping, tick: state.ticks.at(-1)?.tick ?? 0,
                              events: state.eventBacklog.length, injection: state.injection });
    return;
  }
  if (request.method === 'POST' && (path === '/control/pause' || path === '/control/resume')) {
    state.stepping = path === '/control/resume';
    sendJson(response, 200, { stepping: state.stepping, tick: state.ticks.at(-1)?.tick ?? 0 });
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
  // ── 静态（构建产物）
  const relative = path === '/' ? '/index.html' : path;
  const target = join(WEB, normalize(relative).replace(/^([.]{2}[\\/])+/, ''));
  try {
    const data = readFileSync(target);
    response.writeHead(200, { 'content-type': MIME[extname(target)] ?? 'application/octet-stream' });
    response.end(data);
  } catch {
    response.writeHead(404, { 'content-type': 'text/plain' });
    response.end('not found');
  }
});

const wss = new WebSocketServer({ noServer: true });
http.on('upgrade', (request, socket, head) => {
  const url = new URL(request.url, `http://127.0.0.1:${PORT}`);
  const match = url.pathname.match(/^\/ws\/([A-Za-z0-9_-]+)$/);
  if (!match) {
    socket.destroy();
    return;
  }
  wss.handleUpgrade(request, socket, head, (ws) => {
    sockets.set(match[1], ws);
    // **事件回填**（脚手架）：把已产生的事件按 tick 升序直接发给**本连接**，
    // 使 reload 前后客户端「事件条数 / 追溯链」可比（会话层自身不重放事件）。
    // N2 修正（`--backlog-cap 0` = **关闭回填**）：回填事件带**当前 tick**，会把渲染客户端的
    // `(tick, seq)` 水位推到最新 ⇒ 随后 `primeSession` 的**首个 snapshot 因 seq 更小而被打成
    // 乱序丢弃**，页面永远拿不到初始实体（实测：`entityIds()==[]` 而投影有 5 实体）。
    // N2 的 AC-9 不需要事件回放 ⇒ 关闭回填，读数更干净。
    const backlog = BACKLOG_CAP > 0 ? state.eventBacklog.slice(-BACKLOG_CAP) : [];
    for (const event of backlog) {
      if (ws.readyState === 1) {
        ws.send(JSON.stringify({ t: 'event', tick: Number(event.tick ?? 0), seq: Number(event.seq ?? 0), event }));
        state.eventsSent += 1;
      }
    }
    void sessionServer.primeSession(match[1]).then(() => {
      for (const message of sessionServer.drainOutbox(match[1])) {
        if (ws.readyState === 1) ws.send(JSON.stringify(message));
      }
    });
    ws.on('message', async (data) => {
      const result = await sessionServer.onClientMessage(match[1], data.toString());
      for (const message of result.messages) if (ws.readyState === 1) ws.send(JSON.stringify(message));
    });
    ws.on('close', () => sockets.delete(match[1]));
  });
});

await new Promise((ready) => http.listen(PORT, '127.0.0.1', ready));
process.stdout.write(`SERVE_READY port=${PORT} web=${WEB} pack=${PACK} runtime=${RUNTIME}\n`);

// ─────────────────────────────────────────────────────────── 步进 + 收尾
const started = Date.now();
const timer = setInterval(() => {
  if (!state.stepping || state.driverExited) return;
  child.stdin.write(`${JSON.stringify({ cmd: 'step', n: 1 })}\n`);
}, TICK_MS);

const deadline = started + RUN_SECONDS * 1000;
while (Date.now() < deadline) {
  await new Promise((wait) => setTimeout(wait, 500));
}
clearInterval(timer);
if (!state.driverExited) child.stdin.write(`${JSON.stringify({ cmd: 'stop' })}\n`);
await new Promise((wait) => setTimeout(wait, 600));
if (!state.driverExited) child.kill();
for (const response of liveStreams) {
  try {
    response.end();
  } catch {
    /* 收尾路径不因局部异常扩大影响 */
  }
}

const summary = {
  tag: TAG, pack: PACK, seed: SEED, port: PORT, web: WEB, source: SOURCE, runtime: RUNTIME,
  run_seconds: RUN_SECONDS, tick_ms: TICK_MS,
  ticks_reached: state.ticks.at(-1)?.tick ?? 0,
  final_state_hash: state.ticks.at(-1)?.state_hash ?? null,
  final_event_chain_hash: state.ticks.at(-1)?.event_chain_hash ?? null,
  events_total: state.eventBacklog.length, events_backfilled: state.eventsSent,
  driver_kinds: state.kinds, sessions: sessionServer.sessions.size,
  injection: state.injection, driver_meta: state.meta,
};
writeFileSync(join(OUT, `serve-summary-${TAG}.json`), `${JSON.stringify(summary, null, 2)}\n`);
writeFileSync(tickSeriesPath, `${JSON.stringify(state.ticks, null, 2)}\n`);
// **判据性读数**落在这个**不被生成器按名排除**的文件里（`serve-summary-*.json` 会被排除 ⇒
// 只当过程日志用）：注入读数 + 世界末端读数 + 驱动记录计数。
writeFileSync(join(OUT, `n2-run-${TAG}.json`), `${JSON.stringify({
  tag: TAG, pack: PACK, seed: SEED, run_seconds: RUN_SECONDS, tick_ms: TICK_MS,
  ticks_reached: summary.ticks_reached,
  final_state_hash: summary.final_state_hash,
  final_event_chain_hash: summary.final_event_chain_hash,
  events_total: summary.events_total, events_backfilled: summary.events_backfilled,
  driver_kinds: summary.driver_kinds,
  injection: state.injection,
  tick_series_file: `spikes/n2-appearance/readback/tick-series-${TAG}.json`,
  events_file: `spikes/n2-appearance/readback/events-${TAG}.jsonl`,
  web_bundle: WEB, driver: DRIVER, source: SOURCE,
}, null, 2)}\n`);
process.stdout.write(`${JSON.stringify(summary)}\n`);
process.exit(0);
