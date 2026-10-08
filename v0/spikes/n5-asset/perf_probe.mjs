#!/usr/bin/env node
/**
 * `AC-D-2a~d` 的读数计算器（N5 / 性能探针的**统计面**）。
 *
 * 运行：
 *   node v0/spikes/n5-asset/perf_probe.mjs --frames <raw_frames.json> --out <dir>
 *
 * `raw_frames.json` 形态：`{"frames":[ms,…],"heap_start":<bytes|null>,"heap_end":<bytes|null>,
 *   "viewport":{…},"camera_path":[…],"warmup":N,"note":"…"}`
 * （由取证浏览器会话导出的**原始**逐帧读数；本脚本只做统计，**不**修改交付源码 —— R5）
 *
 * 阈值（`AC-D-2`，**提前声明、事后不得调**）：
 *   D-2a p95 ≤ 33.4 ms · D-2b p99 ≤ 50 ms · D-2c jank（>33.4 ms）≤ 2 % · D-2d heap 增长 ≤ 60 MB
 *   D-2e 相对基线劣化 ≤ 25 % —— **降级路径（U-D2e）**：本轮不判，报告显式写明（无实现前冻结基线）
 */

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const get = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };

const framesPath = get('--frames', `${HERE}/readback/perf_frames.json`);
const OUT = resolve(get('--out', `${HERE}/readback`));

const THRESHOLDS = { p95_ms: 33.4, p99_ms: 50, jank_pct: 2, heap_growth_mb: 60 };

function quantile(sorted, p) {
  if (sorted.length === 0) return null;
  const idx = Math.min(sorted.length - 1, Math.floor(sorted.length * p));
  return sorted[idx];
}

function main() {
  const raw = JSON.parse(readFileSync(framesPath, 'utf8'));
  const frames = raw.frames ?? [];
  const sorted = [...frames].sort((a, b) => a - b);
  const mean = frames.length ? frames.reduce((a, b) => a + b, 0) / frames.length : null;
  const jank = frames.filter((x) => x > THRESHOLDS.p95_ms).length;
  const heapGrowthMb = (raw.heap_start !== null && raw.heap_end !== null && raw.heap_start !== undefined)
    ? (raw.heap_end - raw.heap_start) / 1048576 : null;

  const reading = {
    n_frames: frames.length,
    mean_ms: mean === null ? null : Number(mean.toFixed(3)),
    p50_ms: quantile(sorted, 0.5),
    p95_ms: quantile(sorted, 0.95),
    p99_ms: quantile(sorted, 0.99),
    max_ms: sorted.length ? Number(sorted[sorted.length - 1].toFixed(3)) : null,
    jank_frames: jank,
    jank_pct: frames.length ? Number((100 * jank / frames.length).toFixed(3)) : null,
    heap_growth_mb: heapGrowthMb === null ? null : Number(heapGrowthMb.toFixed(2)),
  };

  const verdict = {
    'D-2a_p95<=33.4': reading.p95_ms !== null && reading.p95_ms <= THRESHOLDS.p95_ms,
    'D-2b_p99<=50': reading.p99_ms !== null && reading.p99_ms <= THRESHOLDS.p99_ms,
    'D-2c_jank<=2%': reading.jank_pct !== null && reading.jank_pct <= THRESHOLDS.jank_pct,
    'D-2d_heap<=60MB': reading.heap_growth_mb !== null && reading.heap_growth_mb <= THRESHOLDS.heap_growth_mb,
  };

  const report = {
    schema_version: 'n5-perf/1',
    generated_by: 'artisan',
    generated_at_epoch: Math.floor(Date.now() / 1000),
    thresholds_predeclared: THRESHOLDS,
    thresholds_caveat: 'D-2e 走**降级路径**（U-D2e）：本报告**不**判相对基线劣化；未事后补采基线充当冻结读数。',
    environment: raw.environment ?? null,
    camera_path: raw.camera_path ?? null,
    warmup: raw.warmup ?? null,
    reading,
    verdict,
    /** **口径偏离（必须显式读）** —— 本读数不是合格的 `AC-D` 冻结读数，理由逐条列出。 */
    scope_deviations: raw.scope_deviations ?? [],
    measurement_caveat: raw.note ?? null,
    all_pass: Object.values(verdict).every(Boolean),
  };

  mkdirSync(OUT, { recursive: true });
  writeFileSync(`${OUT}/perf.json`, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  process.stdout.write(`perf_probe: wrote ${OUT}/perf.json\n`);
  process.stdout.write(`perf_probe: n=${reading.n_frames} p95=${reading.p95_ms}ms p99=${reading.p99_ms}ms `
    + `jank=${reading.jank_pct}% heap=${reading.heap_growth_mb}MB => D-2a..d ${report.all_pass ? 'PASS(参考)' : 'FAIL'}\n`);
  process.exit(0);
}

main();
