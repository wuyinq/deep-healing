#!/usr/bin/env node
/**
 * AC-D · **隔离窗口**下的逐帧读数（D-2a~e / D-3c / D-3d / D-3e）。
 *
 * 纪律：
 *   - 隔离：跑前用 `ps` 取全机进程快照，确认**无**其它小队测试/探针并发；跑后再取一次。
 *   - 固定条件：1440×900 · DPR 1 · `?pack=xingfu-xiaoqu-xuqin` · tick 100 ms · 探针自带机位。
 *   - D-3d 负对照：把渲染分辨率临时提到 2880×1800（**只经 configExport 可变参数**，不改交付源码）
 *     ⇒ p95 必须变差。
 *   - 产物只写独立输出目录；跑前后对交付树 `02_source/**` 做 sha256 比对（D-3b）。
 */

import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKSPACE = resolve(HERE, '..', '..');
const SOURCE = join(WORKSPACE, '02_source');
const WEB = join(WORKSPACE, '.build', 'web');
const READBACK = join(HERE, 'readback');
const OUT = join(HERE, 'runtime', 'perf-isolated', 'out');
const PORT = 8848;
const DURATION_MS = 30000;
mkdirSync(OUT, { recursive: true });

const CHROMIUM = [
  process.env.PW_CHROMIUM,
  join(homedir(), 'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64',
    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
  join(homedir(), 'Library/Caches/ms-playwright/chromium_headless_shell-1234',
    'chrome-headless-shell-mac-arm64/chrome-headless-shell'),
].filter(Boolean).find((candidate) => existsSync(candidate));

const walk = (root, prefix = '') => readdirSync(join(root, prefix), { withFileTypes: true })
  .flatMap((entry) => (entry.isDirectory()
    ? walk(root, join(prefix, entry.name))
    : [join(prefix, entry.name)]));
const treeHash = (root) => {
  const lines = walk(root).map((file) => createHash('sha256')
    .update(readFileSync(join(root, file))).digest('hex') + '  ' + file).sort();
  return { count: lines.length, sha256: createHash('sha256').update(lines.join('\n')).digest('hex') };
};
// D-3e：隔离窗口证据（`ps` 全机快照）。**"跑前"快照必须在拉起本探针任何进程之前取**——
// 否则会把本探针自己的 host/chrome 子进程误判成「并发小队进程」（实测踩过，过滤会假红）。
const processSnapshot = () => {
  const all = spawnSync('ps', ['-Ao', 'pid,pcpu,command'], { encoding: 'utf8' }).stdout;
  const lines = all.split('\n').filter(Boolean);
  const mine = String(process.pid);
  const squadPattern = /pytest|serve-live|bridge_run|deephealing_kernel|presentation_probe|scene_assert|authority_scan|perf_probe|material_probe|freeze_inputs/;
  const genericPattern = /playwright|chrome|node .*\.mjs|\brg\b/;
  const notMine = (line) => !line.includes(mine);
  const squad = lines.filter((line) => squadPattern.test(line) && notMine(line));
  const external = lines.filter((line) => genericPattern.test(line) && !squadPattern.test(line) && notMine(line));
  const cpu = (line) => Number((line.trim().split(/\s+/)[1] ?? 0));
  return {
    total_processes: lines.length,
    squad_concurrent: squad.slice(0, 10), squad_concurrent_count: squad.length,
    squad_concurrent_active: squad.filter((line) => cpu(line) >= 1.0).map((line) => line.slice(0, 140)),
    squad_concurrent_active_count: squad.filter((line) => cpu(line) >= 1.0).length,
    external_heavy: external.filter((line) => cpu(line) >= 1.0).map((line) => line.slice(0, 140)).slice(0, 10),
    external_heavy_count: external.filter((line) => cpu(line) >= 1.0).length,
    cpu_column_signature: 'ps -Ao pid,pcpu,command ⇒ 第 2 列 = 进程启动至今的平均 CPU%（空闲进程会显示 0.0）',
  };
};
const psBefore = processSnapshot();

const deliveryBefore = treeHash(SOURCE);

const host = spawn('node', [
  join(HERE, 'serve-live.mjs'), '--tag', 'perf-isolated', '--port', String(PORT), '--pack', 'xingfu-xiaoqu-xuqin',
  '--out', OUT, '--runtime', join(HERE, 'runtime', 'perf-isolated', 'bridge'),
  '--web', WEB, '--source', SOURCE, '--tick-ms', '100', '--seed', '20260921',
  '--run-seconds', '180', '--start-paused', 'false',
], { stdio: ['ignore', 'pipe', 'pipe'] });
const killHost = () => { try { host.kill('SIGKILL'); } catch { /* 已退出 */ } };
process.on('exit', killHost);
await new Promise((ready, reject) => {
  const timer = setTimeout(() => reject(new Error('SERVE_READY timeout')), 90000);
  host.stdout.on('data', (chunk) => { if (String(chunk).includes('SERVE_READY')) { clearTimeout(timer); ready(); } });
});

const GPU_MODE = process.env.PW_GPU === 'metal' ? 'metal' : 'swiftshader';
const browser = await chromium.launch({
  headless: true, executablePath: CHROMIUM,
  // 默认 = **软件光栅**（SwiftShader）；`PW_GPU=metal` 改用真 GPU（Metal/ANGLE）以满足 D-1 的固定条件。
  args: GPU_MODE === 'metal'
    ? ['--use-angle=metal', '--ignore-gpu-blocklist', '--enable-gpu-rasterization', '--enable-zero-copy']
    : ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
await page.goto(`http://127.0.0.1:${PORT}/?pack=xingfu-xiaoqu-xuqin`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => Boolean(globalThis.__deephealing), null, { timeout: 90000 });
await page.evaluate(() => globalThis.__deephealing.scene.setObservationCamera(
  { position_m: [5, 0.35, 17.4], look_at_m: [5, -0.2, 15.0] }));
await page.waitForTimeout(5000);   // warmup：D-1 写死 5 s，不计入 30 s

const configExport = await page.evaluate(() => ({
  postfx: globalThis.__deephealing.scene.postfxReport?.() ?? null,
  material: globalThis.__deephealing.scene.materialReport?.() ?? null,
  camera: globalThis.__deephealing.scene.cameraReport?.() ?? null,
}));
const canonical = (value) => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  if (typeof value === 'number') return value.toFixed(6);
  return JSON.stringify(value);
};
const configHash = createHash('sha256').update(canonical(configExport)).digest('hex');

const sample = (durationMs) => page.evaluate(async (ms) => {
  const frames = [];
  const heapStart = performance.memory?.usedJSHeapSize ?? null;
  const start = performance.now();
  let last = start;
  let worst = { ms: 0, at_ms: 0, scene: null };
  await new Promise((done) => {
    const loop = () => {
      const now = performance.now();
      const delta = Number((now - last).toFixed(3));
      frames.push(delta);
      if (delta > worst.ms) {
        worst = { ms: delta, at_ms: Number((now - start).toFixed(1)), scene: 'indoor fixed camera, npcs walking' };
      }
      last = now;
      if (now - start >= ms) { done(); return; }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  });
  const sorted = [...frames].sort((a, b) => a - b);
  const at = (q) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))];
  const heapEnd = performance.memory?.usedJSHeapSize ?? null;
  return {
    frames, count: frames.length, p50_ms: at(0.5), p95_ms: at(0.95), p99_ms: at(0.99),
    max_ms: sorted[sorted.length - 1], worst_frame: worst,
    jank_count: frames.filter((f) => f > 33.4).length,
    jank_pct: Number((frames.filter((f) => f > 33.4).length / frames.length * 100).toFixed(3)),
    heap_start_bytes: heapStart, heap_end_bytes: heapEnd,
    heap_growth_mb: heapStart !== null && heapEnd !== null ? Number(((heapEnd - heapStart) / 1048576).toFixed(2)) : null,
    viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
  };
}, durationMs);

const main = await sample(DURATION_MS);
const psAfter = processSnapshot();

// D-3d 负对照：渲染分辨率临时 2880×1800 ⇒ p95 必须变差（不改交付源码）
await page.setViewportSize({ width: 2880, height: 1800 });
await page.waitForTimeout(1500);
const negative = await sample(10000);
await page.setViewportSize({ width: 1440, height: 900 });
await page.waitForTimeout(500);

await browser.close();
killHost();

const deliveryAfter = treeHash(SOURCE);
const reading = {
  task: 'perf-isolated', at_epoch: Math.floor(Date.now() / 1000),
  conditions: {
    viewport: '1440x900', dpr: 1, pack: 'xingfu-xiaoqu-xuqin', tick_ms: 100,
    duration_s: 30, warmup_s: 5, camera: 'probe-owned fixed camera [5,0.35,17.4] -> [5,-0.2,15]',
    config_hash: configHash, gpu_mode: GPU_MODE,
    gpu: GPU_MODE === 'metal' ? 'headless Chromium + ANGLE/Metal（真 GPU）' : 'headless Chromium + SwiftShader（软件光栅）',
    renderer_path: '交付面真实渲染循环',
  },
  thresholds: { 'D-2a_p95_ms': 33.4, 'D-2b_p99_ms': 50, 'D-2c_jank_pct': 2,
                'D-2d_heap_growth_mb': 60, 'D-2e_relative_p95_pct': 25 },
  main, negative_control_2880x1800: negative,
  load_isolation: { ps_before_start: psBefore, ps_after_browser_closed: psAfter,
                    isolated: psBefore.squad_concurrent_active_count === 0 && psAfter.squad_concurrent_active_count === 0,
                    definition: '并发 = **在跑（CPU% ≥ 1.0）** 的本小队测试/探针进程出现在 ps 快照里；跑前快照在本探针拉起任何进程之前取。明知存在的**陈旧空闲**进程（如 14 天前遗留的 deephealing_kernel live，0.0% CPU）按实测列出但不计入。' },
  delivery_tree: { before: deliveryBefore, after: deliveryAfter, unchanged: deliveryBefore.sha256 === deliveryAfter.sha256 },
  hardware: {
    cpu: spawnSync('sysctl', ['-n', 'machdep.cpu.brand_string'], { encoding: 'utf8' }).stdout.trim(),
    mem_bytes: Number(spawnSync('sysctl', ['-n', 'hw.memsize'], { encoding: 'utf8' }).stdout.trim()),
  },
};
writeFileSync(join(READBACK, `perf_report_n5c-${GPU_MODE}.json`), `${JSON.stringify(reading, null, 2)}\n`);
process.stdout.write(`PERF ${JSON.stringify({ p95: main.p95_ms, p99: main.p99_ms, jank_pct: main.jank_pct,
  heap_growth_mb: main.heap_growth_mb, neg_p95: negative.p95_ms, isolated: reading.load_isolation.isolated,
  delivery_unchanged: reading.delivery_tree.unchanged })}\n`);
process.exit(0);
