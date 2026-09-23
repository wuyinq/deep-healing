#!/usr/bin/env node
/**
 * F4 真浏览器验收的**服务端**（R2）：真会话层 + 真桥 + 真静态服务（`.build/web`）。
 *
 * 运行：
 *   node spikes/s13-render/serve.mjs --web <构建产物目录> --source <02_source 根> \
 *        --port 8790 --run-seconds 45 --emit <下行消息 jsonl> [--runtime <桥运行目录>]
 *
 * 与 `spikes/s12-session/run-session.mjs` 的差别（F4 需要）：
 *   - 静态根可指向**任意构建产物**（负例要服务「注入了写控件的构建」）；
 *   - 把**真下行流**（snapshot/delta/event/tick_meta/intent_ack）逐条写到 `--emit`（裸消息，
 *     不含 session_id，便于用 `session.protocol.schema.json` 逐条校验）；
 *   - 到点后打印一行 JSON 摘要（READY / DONE 由调用方 grep）。
 *
 * 硬边界：本脚本是**验收脚手架**（spikes/**），不是交付面；交付面一个字节都不写。
 */

import { createServer } from 'node:http';
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
const PORT = Number(option('port', 8790));
const RUN_SECONDS = Number(option('run-seconds', 45));
const EMIT = option('emit', join(WORKSPACE, 'spikes', 's12-session', 'logs', 'emitted-messages.jsonl'));
const RUNTIME = resolve(option('runtime', join(HERE, 'runtime')));
const TICKS = Number(option('ticks', 300));
const TICK_CAP = Number(option('tick-cap', 100000)); // 浏览器验收要跑满 run-seconds ⇒ 不按 plan_ticks 停
const SOURCE = resolve(option('source', join(WORKSPACE, '02_source')));
const SUMMARY_OUT = option('summary', join(HERE, 'logs', 'serve-summary.json'));

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.map': 'application/json',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.png': 'image/png',
};

/** **只读录像**（R2 / F11）：`createSession({record:true})` 的下行消息落 `spikes/s12-session/logs/`。 */
function makeRecorder() {
  const recordDir = join(WORKSPACE, 'spikes', 's12-session', 'logs');
  const streams = new Map();
  return {
    open(sessionId) {
      mkdirSync(recordDir, { recursive: true });
      streams.set(sessionId, createWriteStream(join(recordDir, `session-record-${sessionId}.jsonl`), { flags: 'w' }));
    },
    record(sessionId, message) {
      streams.get(sessionId)?.write(`${JSON.stringify(message)}\n`);
    },
    close() {
      for (const stream of streams.values()) stream.end();
    },
  };
}

const kernelClient = new KernelClient({
  kernelSrc: join(SOURCE, 'v0_skeleton', 'kernel'),
  packSrc: join(SOURCE, 'v0_skeleton', 'districts', 'xingfu-xiaoqu'),
  runtimeDir: RUNTIME,
  seed: 20260921,
  snapshotEvery: 50,
  ticks: TICKS,
});

const server = new SessionServer({ kernelClient, recorder: makeRecorder() });
const sockets = new Map(); // session_id -> ws
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
    response.end(JSON.stringify({ ok: true, sessions: server.sessions.size, ticks: emitted.length, web: WEB }));
    return;
  }
  // **pack 世界观**（R2 / F13）：渲染层按会话 `district_pack_id` 取 `/packs/<id>/worldview.json`，
  // 由宿主从 `districts/<id>/worldview.json` 提供 ⇒ tone 数值全树只有一处定义点。
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
    // 新连接首帧补齐（R2 / F4）：立刻推一次当前快照，避免「连上后空场景等一个 snapshot 周期」
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
process.stdout.write(`SERVE_READY port=${PORT} web=${WEB} source=${SOURCE}\n`);

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

const kinds = emitted.reduce((accumulator, message) => {
  accumulator[message.t] = (accumulator[message.t] ?? 0) + 1;
  return accumulator;
}, {});
const npcIds = new Set();
for (const message of emitted) {
  if (message.t !== 'delta') continue;
  for (const op of message.ops ?? []) npcIds.add(op.entity);
}
const summary = {
  web: WEB, source: SOURCE, runtime: RUNTIME, emit: EMIT,
  port: PORT, ticks_reached: tick, run_seconds: RUN_SECONDS,
  sessions: server.sessions.size, primary_session: primarySession,
  emitted_total: emitted.length, emitted_kinds: kinds,
  delta_entities: [...npcIds].sort(),
  max_tick_in_stream: emitted.reduce((max, message) => Math.max(max, Number(message.tick ?? 0)), 0),
  kernel_inside_copy: meta?.kernel_inside_copy,
  voided_intents: server.voidedIntents,
  bridge_meta_source_files: meta?.source_files,
};
mkdirSync(dirname(SUMMARY_OUT), { recursive: true });
writeFileSync(SUMMARY_OUT, `${JSON.stringify(summary, null, 2)}\n`);
process.stdout.write(`${JSON.stringify(summary)}\n`);
process.exit(0);
