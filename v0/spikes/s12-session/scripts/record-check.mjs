#!/usr/bin/env node
/**
 * F11 真跑读数（R2）：`record:true` 的**最小录像**（只读落 `spikes/s12-session/logs/`，不写世界）。
 *
 * 运行：node spikes/s12-session/scripts/record-check.mjs [--source <02_source 根>]
 *
 * 做什么：
 *   1. 真桥 + 真会话层；建两个会话（一个 `record:true`、一个不开录像）；
 *   2. 两个会话各提交一条意图、推进 3 个 tick；
 *   3. 打印读数：录像文件路径 / 条数 / 类型分布 / 未开录像的会话是否零字节 /
 *      内核事件计数（证明录像**没有**额外写世界）。
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync, createWriteStream } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};
const WS = resolve(join(import.meta.dirname, '..', '..', '..'));
const SOURCE = resolve(option('source', join(WS, '02_source')));
const LOG_DIR = join(WS, 'spikes', 's12-session', 'logs');
const RUNTIME = resolve(option('runtime', join(WS, 'spikes', 's13-render', 'runtime-record')));

const { SessionServer } = await import(pathToFileURL(join(SOURCE, 'v0_skeleton/session/src/server.js')).href);
const { KernelClient } = await import(pathToFileURL(join(SOURCE, 'v0_skeleton/session/src/upstream.js')).href);

mkdirSync(LOG_DIR, { recursive: true });
const streams = new Map();
const recorded = [];
const recorder = {
  open(sessionId) {
    streams.set(sessionId, createWriteStream(join(LOG_DIR, `session-record-${sessionId}.jsonl`), { flags: 'w' }));
  },
  record(sessionId, message) {
    recorded.push({ session_id: sessionId, t: message.t });
    streams.get(sessionId)?.write(`${JSON.stringify(message)}\n`);
  },
};

const kernelClient = new KernelClient({
  kernelSrc: join(SOURCE, 'v0_skeleton/kernel'),
  packSrc: join(SOURCE, 'v0_skeleton/districts', 'xingfu-xiaoqu'),
  runtimeDir: RUNTIME, seed: 20260921, snapshotEvery: 1, ticks: 300,
});
const server = new SessionServer({ kernelClient, recorder });
await kernelClient.subscribe([(record) => server.broadcastKernelRecord(record)]);

const recordedSession = (await server.createSession({
  mode: 'participate', district_pack_id: 'xingfu-xiaoqu', client_version: '0.3.0', record: true,
})).body;
const plainSession = (await server.createSession({
  mode: 'participate', district_pack_id: 'xingfu-xiaoqu', client_version: '0.3.0',
})).body;

for (const [sessionId, intentId] of [[recordedSession.session_id, 'rec-1'], [plainSession.session_id, 'plain-1']]) {
  await server.onClientMessage(sessionId, JSON.stringify({
    t: 'intent', id: intentId, kind: 'delegate_instruction', target: 'npc-001',
  }));
}
for (let tick = 1; tick <= 3; tick += 1) {
  await server.onTickBoundary(tick);
  await kernelClient.step(1);
  await new Promise((resolveWait) => setTimeout(resolveWait, 150));
}
await new Promise((resolveWait) => setTimeout(resolveWait, 300));
for (const stream of streams.values()) stream.end();
await kernelClient.stop();

const recordPath = join(LOG_DIR, `session-record-${recordedSession.session_id}.jsonl`);
const plainPath = join(LOG_DIR, `session-record-${plainSession.session_id}.jsonl`);
const lines = existsSync(recordPath)
  ? readFileSync(recordPath, 'utf8').split('\n').filter((line) => line.trim()).map((line) => JSON.parse(line))
  : [];
const kinds = lines.reduce((accumulator, message) => {
  accumulator[message.t] = (accumulator[message.t] ?? 0) + 1;
  return accumulator;
}, {});
const events = readFileSync(join(RUNTIME, 'logs', 'kernel-events.jsonl'), 'utf8')
  .split('\n').filter((line) => line.trim()).map((line) => JSON.parse(line));
const summary = {
  source: SOURCE,
  recorded_session: recordedSession.session_id,
  plain_session: plainSession.session_id,
  record_file: recordPath,
  record_lines: lines.length,
  record_kinds: kinds,
  record_all_belong_to_recorded_session: recorded.every((item) => item.session_id === recordedSession.session_id),
  plain_session_record_file_exists: existsSync(plainPath),
  kernel_event_count: events.length,
  kernel_event_types: [...new Set(events.map((event) => event.type))].sort(),
  merged_intents: server.mergedIntents,
  voided_intents: server.voidedIntents.length,
};
writeFileSync(join(LOG_DIR, 'record-check-summary.json'), `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
process.exit(0);
