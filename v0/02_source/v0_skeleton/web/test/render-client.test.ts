/**
 * 渲染客户端判据（AC-M3-3）——**真跑，非 skip**。
 *
 * 运行：cd 02_source/v0_skeleton/web && node --test test/render-client.test.ts
 *
 * 三组各自一条用例：
 *   - 乱序 delta **被丢弃**
 *   - observe 会话调 `submitIntent` **本地即拒**
 *   - 同一消息 `apply` 两次**幂等**
 *
 * FU-20260924-007 追加：`build_emits_runtime_assets`（构建层搬运判据 + 负对照）。
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join, resolve as resolvePath } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

import { RenderClient } from '../src/net/client.ts';

function delta(tick: number, seq: number) {
  return { t: 'delta' as const, tick, seq, ops: [{ op: 'set', entity: 'npc-001', component: 'transform', value: {} }] };
}

test('test_out_of_order_delta_is_dropped', () => {
  const client = new RenderClient();
  assert.equal(client.apply(delta(10, 5)), true);
  // 过期 tick：丢弃
  assert.equal(client.apply(delta(9, 99)), false);
  // 同 tick 但 seq 回退：乱序，丢弃
  assert.equal(client.apply(delta(10, 4)), false);
  // 同 tick 更大 seq：接受
  assert.equal(client.apply(delta(10, 6)), true);
  // 更大 tick：接受
  assert.equal(client.apply(delta(11, 1)), true);
});

test('test_observe_session_submit_intent_rejected_locally', async () => {
  const client = new RenderClient();
  client.mode = 'observe';
  const result = await client.submitIntent({ id: 'ui-1', kind: 'delegate_instruction', target: 'npc-001' });
  assert.equal(result.status, 'rejected');
  assert.equal(result.reason, 'E_MODE_READONLY');
  // 未连接时 participate 也不得伪造成功
  client.mode = 'participate';
  const offline = await client.submitIntent({ id: 'ui-2', kind: 'delegate_instruction', target: 'npc-001' });
  assert.equal(offline.reason, 'E_KERNEL_UNAVAILABLE');
});

test('test_apply_is_idempotent_for_the_same_message', () => {
  const client = new RenderClient();
  const message = delta(42, 7);
  assert.equal(client.apply(message), true);
  assert.equal(client.apply(message), false, '同一消息 apply 两次必须幂等（第二次不得再变更状态）');
  assert.equal(client.apply({ ...message }), false, '同一 (tick,seq,t) 的等价消息同样幂等');
  assert.equal(client.appliedKeys.length, 1);
});

test('test_snapshot_then_delta_ordering_is_preserved', () => {
  const client = new RenderClient();
  assert.equal(client.apply({ t: 'snapshot', tick: 50, seq: 1, state: {}, state_hash: 'a'.repeat(64) }), true);
  assert.equal(client.apply(delta(50, 2)), true);
  assert.equal(client.apply(delta(50, 1)), false);
  assert.equal(client.apply(delta(51, 1)), true);
  // 非法消息（缺 tick/seq）不得进入状态机
  assert.equal(client.apply({ t: 'delta', tick: 51, seq: 2, ops: [] } as never), true);
  assert.equal(client.apply({ t: 'delta' } as never), false);
});

// ─────────────────────────────────────────────────────────────────────────────
// FU-007 · **构建层搬运判据**（AC-1 的守卫）：真跑两次 `vite build`
//
// 为什么需要它：`scene_assert.mjs` **不校验构建产物**（它只跑源码树），所以「构建产物里
// 有没有人物资产」此前完全没有自动回归保护 —— 正是本次缺陷（交付构建丢人物资产）逃逸的缺口。
//
// 同一测试内两条臂（都必须真跑，且读数都打印）：
//   正例 = **仓库自身配置**（`vite.config.ts`）构建 ⇒ `assets/character/{xuqin-body.glb,
//          skin-pale-01.jpg}` **必须存在**，且与 `web/assets/character/` 同名文件 **sha256 逐字节相同**；
//   负对照 = **修复前形态**的配置文本（内联字面量写到 /tmp 沙箱）构建 ⇒ 同两个路径 **必须不存在**。
//          —— 负对照保证本判据**不是恒真**：配置一旦退回修复前形态，正例那两条断言会红。
//
// 纪律：构建输出 / 临时配置一律落 `os.tmpdir()` 沙箱；**不在 02_source 内**产生
// `node_modules` / `dist` / `.build`（verify_specs 的残渣判据会红）。
// 生产代码里**没有**任何「测试专用开关」（不许 `if (process.env.FU007_TEST) return`）：
// 本测试只是把 `--outDir` 指到沙箱，走的仍是 `vite build` 本体。

const WEB = resolvePath(dirname(fileURLToPath(import.meta.url)), '..');
const ASSET_ROOT = join(WEB, 'assets');
const REPO_CONFIG = join(WEB, 'vite.config.ts');
const SANDBOX = join(tmpdir(), `fu007-build-guard-${process.pid}`);
const POS_OUT = join(SANDBOX, 'positive-out');
const NEG_OUT = join(SANDBOX, 'negative-out');
const NEG_CONFIG = join(SANDBOX, 'vite.prefix.config.ts');

/** 自 WEB 向上找 vite 的 CLI 入口（依赖装在**工作区根**，不在 02_source 内）。 */
function findViteCli(start: string): string | null {
  let dir = start;
  for (let hop = 0; hop < 8; hop += 1) {
    const candidate = join(dir, 'node_modules', 'vite', 'bin', 'vite.js');
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

const sha256 = (file: string) => createHash('sha256').update(readFileSync(file)).digest('hex');

/** 修复前形态的 `vite.config.ts`（逐字复刻 base `8baa5ae` 的正文；只把 outDir 指到沙箱）。
 *  写成**纯对象**而不是 `defineConfig(...)`：`defineConfig` 只是恒等函数（类型提示用），
 *  而沙箱在 /tmp、解析不到裸 `vite` 依赖 —— 对象形态与修复前语义等价，且不依赖包解析。 */
const PREFIX_CONFIG_TEXT = `export default {
  root: ${JSON.stringify(WEB)},
  server: { port: 5173 },
  build: {
    outDir: ${JSON.stringify(NEG_OUT)},
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: false,
  },
};
`;

const TARGETS = [
  { rel: 'character/xuqin-body.glb' },
  { rel: 'character/skin-pale-01.jpg' },
];

function runViteBuild(configPath: string, outDir: string | null) {
  const cli = findViteCli(WEB);
  assert.ok(cli, `找不到 vite CLI 入口（自 ${WEB} 向上找 node_modules/vite/bin/vite.js）`);
  const args = [cli, 'build', '--config', configPath, '--logLevel', 'warn'];
  if (outDir !== null) args.push('--outDir', outDir, '--emptyOutDir');
  const result = spawnSync(process.execPath, args, { cwd: WEB, encoding: 'utf8', timeout: 180000 });
  return { status: result.status, stdout: result.stdout ?? '', stderr: result.stderr ?? '', args };
}

/** 逐条比对：存在 + sha256 与源一致。 */
function inspect(outDir: string) {
  const rows = TARGETS.map(({ rel }) => {
    const built = join(outDir, 'assets', rel);
    const source = join(ASSET_ROOT, rel);
    const exists = existsSync(built);
    const same = exists && sha256(built) === sha256(source);
    return { rel, built, bytes: exists ? statSync(built).size : 0, exists, sha256_matches_source: same };
  });
  const files = rows.length;
  const found = rows.filter((r) => r.exists && r.sha256_matches_source).length;
  return { rows, files, found, exists_count: rows.filter((r) => r.exists).length };
}

test('build_emits_runtime_assets', () => {
  rmSync(SANDBOX, { recursive: true, force: true });
  mkdirSync(SANDBOX, { recursive: true });
  writeFileSync(NEG_CONFIG, PREFIX_CONFIG_TEXT);

  // ① 正例：仓库自身配置（`vite build` 本体，只是把 outDir 挪到沙箱）
  const positive = runViteBuild(REPO_CONFIG, POS_OUT);
  const posInspect = inspect(POS_OUT);
  process.stdout.write(`[fu007] positive build exit=${positive.status} outDir=${POS_OUT}\n`);
  process.stdout.write(`[fu007] positive files=${posInspect.files} found=${posInspect.found}\n`);
  for (const row of posInspect.rows) {
    process.stdout.write(`[fu007]   ${row.rel} exists=${row.exists} bytes=${row.bytes} sha256_matches_source=${row.sha256_matches_source}\n`);
  }

  // ② 负对照：**修复前形态**的配置（同一次运行内，同一个测试里）
  const negative = runViteBuild(NEG_CONFIG, null);
  const negInspect = inspect(NEG_OUT);
  process.stdout.write(`[fu007] negative(prefix-shape) build exit=${negative.status} outDir=${NEG_OUT}\n`);
  process.stdout.write(`[fu007] negative files=${negInspect.files} found=${negInspect.found} exists=${negInspect.exists_count}\n`);
  for (const row of negInspect.rows) {
    process.stdout.write(`[fu007]   ${row.rel} exists=${row.exists}\n`);
  }
  process.stdout.write(`[fu007] negative_control_evidence=${join(WEB, '..', '..', '..', '03_artisan_self_test.log')}\n`);

  // ③ 断言（判据必须有牙齿：正例真命中、负对照真未命中）
  assert.equal(positive.status, 0, `正例构建必须成功（exit=${positive.status}）\n${positive.stderr}`);
  assert.equal(posInspect.files, TARGETS.length, '被检查的文件清单条数');
  assert.equal(posInspect.found, TARGETS.length,
    `正例：${TARGETS.map((t) => t.rel).join(' / ')} 必须存在且与 web/assets 逐字节相同（found=${posInspect.found}/${posInspect.files}）`);
  assert.ok(posInspect.found > 0, '禁止「零命中绿」：正例必须至少命中一个真实文件');

  assert.equal(negative.status, 0, `负对照构建必须成功（exit=${negative.status}）\n${negative.stderr}`);
  assert.equal(negInspect.exists_count, 0,
    `负对照（修复前形态）不得产出 assets/character/**：实测 exists=${negInspect.exists_count}；`
    + `这条断言保证正例不是恒真（配置退回修复前形态 ⇒ 正例必红）`);
});
