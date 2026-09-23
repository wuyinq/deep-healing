/**
 * s12-session spike：P-8「demo 跑前后交付面**逐字节**不变」的机器判据（D-8①，逐字节）。
 *
 * 运行：node <ws>/spikes/s12-session/zero-residue.mjs
 *
 * 口径（逐条列明，照抄 verify_specs.sh 的 GENERATED_PATTERNS）：
 *   __pycache__ 目录、.pyc、.pytest_cache、.DS_Store、node_modules、.venv、dist、attic-*
 *   **除该集之外全量逐字节相同**。
 *
 * 另：打印桥运行时的 `deephealing_kernel.__file__`（必须在**副本路径**下）。
 * 退出码：0 判据成立；1 判据红。
 */

import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

import { SessionServer } from '../../02_source/v0_skeleton/session/src/server.js';
import { KernelClient } from '../../02_source/v0_skeleton/session/src/upstream.js';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const WORKSPACE = join(HERE, '..', '..');
const SOURCE = join(WORKSPACE, '02_source');
const LOGS = join(HERE, 'logs');
const RUNTIME = join(HERE, 'runtime');
mkdirSync(LOGS, { recursive: true });

const GENERATED = [
  /(^|\/)__pycache__\//, /\.pyc$/, /(^|\/)\.pytest_cache\//, /(^|\/)\.DS_Store$/,
  /(^|\/)node_modules\//, /(^|\/)\.venv\//, /(^|\/)dist\//, /(^|\/)attic-[^/]*\//,
];

function isGenerated(rel) {
  return GENERATED.some((pattern) => pattern.test(rel.split(sep).join('/')));
}

function manifest(root) {
  const entries = new Map();
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      const rel = relative(root, full).split(sep).join('/');
      const info = statSync(full);
      if (info.isDirectory()) {
        walk(full);
        continue;
      }
      if (isGenerated(rel)) continue;
      entries.set(rel, createHash('sha256').update(readFileSync(full)).digest('hex'));
    }
  };
  walk(root);
  return entries;
}

function diff(before, after) {
  const changed = [];
  const added = [];
  const removed = [];
  for (const [path, hash] of before.entries()) {
    if (!after.has(path)) removed.push(path);
    else if (after.get(path) !== hash) changed.push(path);
  }
  for (const path of after.keys()) if (!before.has(path)) added.push(path);
  return { changed: changed.sort(), added: added.sort(), removed: removed.sort() };
}

const before = manifest(SOURCE);
writeFileSync(join(LOGS, 'm3-source-manifest-before.txt'),
  [...before.entries()].sort().map(([path, hash]) => `${hash}  ${path}`).join('\n') + '\n');

const kernelClient = new KernelClient({
  kernelSrc: join(SOURCE, 'v0_skeleton', 'kernel'),
  packSrc: join(SOURCE, 'v0_skeleton', 'districts', 'xingfu-xiaoqu'),
  runtimeDir: RUNTIME,
  seed: 20260921,
  snapshotEvery: 50,
  ticks: 60,
});

const records = [];
const meta = await kernelClient.subscribe([(record) => records.push(record)]);
// 真跑：observe 拒写 + participate 入队（tick 边界应用）
const observeAck = await kernelClient.submitIntent('sess_p8observe', { id: 'p8-obs', kind: 'delegate_instruction', target: 'npc-001' }, { mode: 'observe' });
const participateAck = await kernelClient.submitIntent('sess_p8part', { id: 'p8-part', kind: 'delegate_instruction', target: 'npc-001' }, { mode: 'participate', impactBudgetRemaining: 100 });
for (let index = 0; index < 60; index += 1) await kernelClient.step(1);
await kernelClient.stop();

const after = manifest(SOURCE);
writeFileSync(join(LOGS, 'm3-source-manifest-after.txt'),
  [...after.entries()].sort().map(([path, hash]) => `${hash}  ${path}`).join('\n') + '\n');

const delta = diff(before, after);
const insideCopy = Boolean(meta?.kernel_inside_copy);
const kernelFile = String(meta?.kernel_file ?? '');

const report = {
  source_files_before: before.size,
  source_files_after: after.size,
  changed: delta.changed,
  added: delta.added,
  removed: delta.removed,
  byte_identical: delta.changed.length === 0 && delta.added.length === 0 && delta.removed.length === 0,
  kernel_file: kernelFile,
  kernel_inside_copy: insideCopy,
  kernel_copy: meta?.kernel_copy,
  observe_ack: observeAck,
  participate_ack: participateAck,
  event_kinds: records.filter((record) => record.kind === 'intent_ack').map((record) => `${record.id}:${record.status}:${record.reason ?? ''}`),
};
writeFileSync(join(LOGS, 'p8-zero-residue.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));

const ok = report.byte_identical && insideCopy
  && kernelFile.startsWith(String(meta?.kernel_copy ?? '###'))
  && observeAck.status === 'rejected' && observeAck.reason === 'E_MODE_READONLY'
  && participateAck.status === 'queued';
process.exit(ok ? 0 : 1);
