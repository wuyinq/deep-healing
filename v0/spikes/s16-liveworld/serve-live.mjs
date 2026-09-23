#!/usr/bin/env node
/**
 * M4 真浏览器验收的**服务端**（AC-M4-11①②③）：真会话层 + 真桥 + 真静态服务 + **真只读实时通道代理**。
 *
 * 运行：
 *   node spikes/s16-liveworld/serve-live.mjs --web <构建产物> --source <02_source 根> \
 *        --port 8791 --live-port 8899 --run-seconds 45 --emit <下行消息 jsonl> [--runtime <目录>]
 *
 * 与 `spikes/s13-render/serve.mjs`（M3 的验收服务端，**本轮不改**）的差别只有一处：
 *   把 `/live/*` **同源代理**到内核侧只读实时通道（`cli live`，默认 8899）。
 *   为什么必须代理：内核通道**显式不设置** `Access-Control-Allow-Origin`（同源策略挡跨源读取，
 *   D-M4-16），所以浏览器页面只能从**自己的 origin** 访问 `/live/*`。
 *   代理是**验收脚手架**行为，不是产品代码；产品侧的 `/live` 由 vite dev proxy 或反向代理提供。
 *
 * 硬边界：本脚本在 `spikes/**`，**不是交付面**；交付面一个字节都不写。
 */

import { createServer, request as httpRequest } from 'node:http';
import { createWriteStream, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { WebSocketServer } from 'ws';

import { SessionServer } from '../../02_source/v0_skeleton/session/src/server.js';
import { KernelClient } from '../../02_source/v0_skeleton/session/src/upstream.js';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const WORKSPACE = join(HERE, '..', '..');
const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};

const WEB = resolve(option('web', join(WORKSPACE, '.build', 'web')));
const PORT = Number(option('port', 8791));
const LIVE_PORT = Number(option('live-port', 8899));
const RUN_SECONDS = Number(option('run-seconds', 45));
const EMIT = option('emit', join(HERE, 'logs', 'emitted-messages-live.jsonl'));
const RUNTIME = resolve(option('runtime', join(HERE, 'runtime')));
const TICKS = Number(option('ticks', 300));
const TICK_CAP = Number(option('tick-cap', 100000));
const SOURCE = resolve(option('source', join(WORKSPACE, '02_source')));
const SUMMARY_OUT = option('summary', join(HERE, 'logs', 'serve-live-summary.json'));

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.map': 'application/json',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.png': 'image/png',
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
const emitted = [];
let primarySession = null;

const meta = await kernelClient.subscribe([(record) => {
  server.broadcastKernelRecord(record);
  for (const [sessionId, socket] of sockets.entries()) {
    for (const message of server.drainOutbox(sessionId)) {
      if (primarySession === null) primarySession = sessionId;
      if (sessionId === primarySession) emitted.push(message);
      if (socket.readyState === 1) socket.send(JSON.stringify(message));
    }
  }
}]);

/** `/live/*` → 内核只读实时通道的**同源代理**（含 SSE 流式透传）。 */
function proxyLive(request, response, url) {
  const upstream = httpRequest({
    host: '127.0.0.1', port: LIVE_PORT, path: url.pathname + url.search,
    method: request.method, headers: { host: `127.0.0.1:${LIVE_PORT}` },
  }, (upstreamResponse) => {
    response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
    upstreamResponse.pipe(response);
  });
  upstream.on('error', () => {
    response.writeHead(502, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ error: 'E_LIVE_UNAVAILABLE', port: LIVE_PORT }));
  });
  request.pipe(upstream);
}

const http = createServer(async (request, response) => {
  const url = new URL(request.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname.startsWith('/live/')) {
    proxyLive(request, response, url);
    return;
  }
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
    response.end(JSON.stringify({ ok: true, sessions: server.sessions.size, ticks: emitted.length, web: WEB, live_port: LIVE_PORT }));
    return;
  }
  const packMatch = url.pathname.match(/^\/packs\/([A-Za-z0-9_-]{1,64})\/worldview\.json$/);
  if (packMatch) {
    const packFile = join(SOURCE, 'v0_skeleton', 'districts', packMatch[1], 'worldview.json');
    try {
      const data = readFileSync(packFile);
      response.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
      response.end(data);
    } catch {
      response.writeHead(404, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ error: 'E_PACK_INVALID', pack_id: packMatch[1] }));
    }
    return;
  }
  const relative = url.pathname === '/' ? '/index.html' : url.pathname;
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
    void server.primeSession(match[1]).then(() => {
      for (const message of server.drainOutbox(match[1])) {
        if (ws.readyState === 1) ws.send(JSON.stringify(message));
      }
    });
    ws.on('message', async (data) => {
      const result = await server.onClientMessage(match[1], data.toString());
      for (const message of result.messages) {
        if (match[1] === primarySession || primarySession === null) emitted.push(message);
        ws.send(JSON.stringify(message));
      }
    });
    ws.on('close', () => sockets.delete(match[1]));
  });
});

await new Promise((resolveReady) => http.listen(PORT, '127.0.0.1', resolveReady));
process.stdout.write(`SERVE_READY port=${PORT} live_port=${LIVE_PORT} web=${WEB}\n`);

let tick = 0;
const started = Date.now();
const timer = setInterval(async () => {
  if (tick >= TICK_CAP) return;
  tick += 1;
  await server.onTickBoundary(tick);
  await kernelClient.step(1);
}, 100);

const deadline = started + RUN_SECONDS * 1000;
while (Date.now() < deadline) {
  await new Promise((resolveWait) => setTimeout(resolveWait, 500));
}
clearInterval(timer);
await kernelClient.stop();

mkdirSync(dirname(EMIT), { recursive: true });
writeFileSync(EMIT, emitted.map((message) => JSON.stringify(message)).join('\n') + '\n');

const summary = {
  web: WEB, source: SOURCE, runtime: RUNTIME, emit: EMIT,
  port: PORT, live_port: LIVE_PORT, ticks_reached: tick, run_seconds: RUN_SECONDS,
  sessions: server.sessions.size, primary_session: primarySession,
  emitted_total: emitted.length,
  kernel_inside_copy: meta?.kernel_inside_copy,
};
mkdirSync(dirname(SUMMARY_OUT), { recursive: true });
writeFileSync(SUMMARY_OUT, `${JSON.stringify(summary, null, 2)}\n`);
process.stdout.write(`${JSON.stringify(summary)}\n`);
process.exit(0);
