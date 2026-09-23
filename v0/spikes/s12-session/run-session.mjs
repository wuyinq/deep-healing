/**
 * s12-session spike：**真跑**会话层 + Python 驱动桥（内核副本）。
 *
 * 运行：node <ws>/spikes/s12-session/run-session.mjs [--ticks 300] [--port 8787] [--run-seconds 25]
 *
 * 做什么（全部真执行，无桩）：
 *   1. spawn `bridge/kernel_bridge.py`（把内核与 pack 复制到 runtime/ 再导入副本）；
 *   2. 起 HTTP（POST /sessions）+ WS（/ws/{session_id}）+ 静态服务（`.build/web`）；
 *   3. 10Hz tick 循环：tick 边界先把队列里的意图交给内核，再 `step(1)`，把桥搬运的记录广播下去；
 *   4. 日志落 `spikes/s12-session/logs/`（不含 token / 玩家原文）。
 */

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import { WebSocketServer } from 'ws';

import { SessionServer } from '../../02_source/v0_skeleton/session/src/server.js';
import { KernelClient } from '../../02_source/v0_skeleton/session/src/upstream.js';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const WORKSPACE = join(HERE, '..', '..');
const SOURCE = join(WORKSPACE, '02_source');
const WEB_BUILD = join(WORKSPACE, '.build', 'web');
const RUNTIME = join(HERE, 'runtime');

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};
const TICKS = Number(option('ticks', 300));
const PORT = Number(option('port', 8787));
const RUN_SECONDS = Number(option('run-seconds', 25));

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.map': 'application/json',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
};

const kernelClient = new KernelClient({
  kernelSrc: join(SOURCE, 'v0_skeleton', 'kernel'),
  packSrc: join(SOURCE, 'v0_skeleton', 'districts', 'xingfu-xiaoqu'),
  runtimeDir: RUNTIME,
  seed: 20260921,
  snapshotEvery: 50,
  ticks: TICKS,
});

const server = new SessionServer({ kernelClient });
const sockets = new Map();
const bridgeRecords = [];

const meta = await kernelClient.subscribe([(record) => {
  bridgeRecords.push(record);
  server.broadcastKernelRecord(record);
  if (record.kind === 'snapshot' || record.kind === 'delta' || record.kind === 'tick_meta' || record.kind === 'event') {
    for (const [sessionId, socket] of sockets.entries()) {
      for (const message of server.drainOutbox(sessionId)) {
        if (socket.readyState === 1) socket.send(JSON.stringify(message));
      }
    }
  }
}]);

const http = createServer(async (request, response) => {
  const url = new URL(request.url, `http://127.0.0.1:${PORT}`);
  if (request.method === 'POST' && url.pathname === '/sessions') {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    let body = {};
    try {
      body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
    } catch {
      body = {};
    }
    const created = await server.createSession(body);
    response.writeHead(created.status, { 'content-type': 'application/json' });
    response.end(JSON.stringify(created.body));
    return;
  }
  if (url.pathname === '/health') {
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ ok: true, sessions: server.sessions.size, ticks: bridgeRecords.length }));
    return;
  }
  // 静态：`.build/web`
  const relative = url.pathname === '/' ? '/index.html' : url.pathname;
  const target = join(WEB_BUILD, normalize(relative).replace(/^([.]{2}[\\/])+/, ''));
  try {
    const data = await readFile(target);
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
    // 新连接首帧补齐（R2 / F4）：立刻推一次当前快照
    void server.primeSession(match[1]).then(() => {
      for (const message of server.drainOutbox(match[1])) {
        if (ws.readyState === 1) ws.send(JSON.stringify(message));
      }
    });
    ws.on('message', async (data) => {
      const result = await server.onClientMessage(match[1], data.toString());
      for (const message of result.messages) ws.send(JSON.stringify(message));
    });
    ws.on('close', () => sockets.delete(match[1]));
  });
});

await new Promise((resolve) => http.listen(PORT, '127.0.0.1', resolve));

let tick = 0;
let stepMs = 0;
const started = Date.now();
const timer = setInterval(async () => {
  if (tick >= TICKS) return;
  tick += 1;
  await server.onTickBoundary(tick);
  const before = Date.now();
  await kernelClient.step(1);
  stepMs += Date.now() - before;
}, 100);

const deadline = started + RUN_SECONDS * 1000;
while (Date.now() < deadline) {
  await new Promise((resolve) => setTimeout(resolve, 500));
}
clearInterval(timer);
await kernelClient.stop();

const kinds = bridgeRecords.reduce((accumulator, record) => {
  accumulator[record.kind] = (accumulator[record.kind] ?? 0) + 1;
  return accumulator;
}, {});
const rejected = bridgeRecords.filter((record) => record.kind === 'intent_ack' && record.status === 'rejected');

console.log(JSON.stringify({
  bridge_meta: meta,
  ticks_requested: TICKS,
  ticks_reached: tick,
  step_ms_total: stepMs,
  bridge_record_kinds: kinds,
  intent_acks: bridgeRecords.filter((record) => record.kind === 'intent_ack').length,
  intent_acks_rejected: rejected.length,
  intent_rejected_reasons: rejected.map((record) => record.reason),
  ws_sessions: sockets.size,
  http_port: PORT,
}, null, 2));

http.close();
wss.close();
process.exit(0);
