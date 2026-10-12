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

import * as THREE from 'three';

import { RenderClient } from '../src/net/client.ts';
import { createScene } from '../src/scene/world.ts';
import { createCharacterInstance } from '../src/scene/character_instance.ts';
import {
  BINDINGS, bindingForEntity, clearBindingDegradations, bindingDegradationsSnapshot,
} from '../src/scene/asset_binding.ts';
import { ASSET_ENTRIES } from '../src/scene/world.ts';
import {
  ObservePanel, eventMatchesEntity, observeOptionsFor, readPersistedView, restoreDecisionOf, writePersistedView,
} from '../src/ui/observe/panel.ts';
// r2 新增导出用**独立 import 语句**引入（追加式改动：不改写 r1 已落下的任何一行）。
import {
  cameraSourceOf, focusReasonOf, focusReasonsOf, focusSourcesOf, optionTargetCollisions,
  readFocusRows, targetButtonId,
} from '../src/ui/observe/panel.ts';
import { CausalTrace } from '../src/ui/observe/trace.ts';

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

// ─────────────────────────────────────────────────────────────────────────────
// fu010-013 · AC-1（消翻转 / 跨 snapshot 复用）与 AC-2（默认取景可见人物）守卫
//
// 为什么必须在这里而不是只靠 `scene_assert.mjs`：后者的取数路径是**静态**快照（tick 0），
// 跑不出「第二条强制重建」（`setReading()` / 位置变化）。本节的用例**真驱动**多轮 `apply(snapshot)`
// 与 `setReading()`，并对复用键 / 剪枝 / 对焦默认关 / framing 读数各配一条**可判假**的断言与负对照。

const WEB_DIR_FU010 = resolvePath(dirname(fileURLToPath(import.meta.url)), '..');
const TONE_FU010 = (JSON.parse(readFileSync(
  join(WEB_DIR_FU010, '..', 'districts', 'xingfu-xiaoqu', 'worldview.json'), 'utf8')) as { tone: unknown }).tone;

const CANVAS_STUB_FU010 = {
  clientWidth: 1440, clientHeight: 900, width: 0, height: 0, style: {},
  getContext: () => null, addEventListener() {}, removeEventListener() {},
};

const npcEntity = (id: string, xMm: number) => ({ id, kind: 'npc', transform: { pos_mm: { x: xMm, y: 0, z: 0 } } });

/** 假 GLB：一个**已知尺寸**的小盒（0.6 × 1.8 × 0.4，脚底在 y=0）—— 供 AABB 派生与投影读数对表。 */
function knownBodyScene() {
  const root = new THREE.Group();
  root.name = 'fake-glb-known-body';
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.6, 1.8, 0.4), new THREE.MeshBasicMaterial());
  body.position.set(0, 0.9, 0);
  body.name = 'fake-body';
  root.add(body);
  return root;
}

const syncLoader = (scene3: THREE.Object3D) => ({
  load(_url: string, onLoad: (gltf: unknown) => void) { onLoad({ scene: scene3 }); },
});

/** 递归断言：读数里所有 `number` 必须有限（NaN / ±Infinity 一律不许出现）。 */
function assertNoNonFinite(value: unknown, path = '$'): void {
  if (typeof value === 'number') {
    assert.ok(Number.isFinite(value), `${path} 必须是有限数，实测 ${String(value)}`);
    return;
  }
  if (Array.isArray(value)) { value.forEach((item, index) => assertNoNonFinite(item, `${path}[${index}]`)); return; }
  if (value && typeof value === 'object') {
    for (const [key, inner] of Object.entries(value)) assertNoNonFinite(inner, `${path}.${key}`);
  }
}

const newProbe = () => createScene(CANVAS_STUB_FU010 as never, { worldview: TONE_FU010 as never });
const snap = (probe: ReturnType<typeof newProbe>, entities: unknown[], tick: number) =>
  probe.apply({ t: 'snapshot', tick, state: { entities } as never });

const passesAc2 = (row: Record<string, unknown>): boolean => row.fully_in_viewport === true
  && Number(row.height_fraction) >= 0.30 && Number(row.area_fraction) >= 0.05;

test('fu010_ac1_reuse_key_keeps_instance_across_snapshots_and_readings', () => {
  const probe = newProbe();
  snap(probe, [npcEntity('npc-006', 0)], 0);
  const c0 = probe.characterInstanceChurnReport();
  assert.equal(c0.created, 1, '首个 snapshot 必须新建 1 个实例');
  assert.equal(c0.reused, 0);
  assert.equal(c0.disposed, 0);
  assert.equal(c0.glb_load_calls, 0, 'Node 无 loader ⇒ 零 GLB 装载调用');
  assert.equal(c0.last_rebuild_tick, 0);

  // ① 实体集不变 ⇒ 复用（不 dispose、不重载）
  snap(probe, [npcEntity('npc-006', 0)], 1);
  const c1 = probe.characterInstanceChurnReport();
  assert.equal(c1.created, c0.created, '实体集不变 ⇒ created 不得增长');
  assert.equal(c1.disposed, c0.disposed, '实体集不变 ⇒ 不得 dispose');
  assert.equal(c1.reused, c0.reused + 1, '实体集不变 ⇒ reused +1');
  assert.equal(c1.reused_keys.length, 1, '最近一次 rebuild 复用键恰好 1 个');
  const key = c1.reused_keys[0] as string;
  assert.ok(key.startsWith('npc-006|xuqin_default|assets/character/xuqin-body.glb|1.0.0|'),
    `复用键必须由 bindingForEntity 同源派生，实测 ${key}`);
  assert.ok(!key.includes('underneath') && !key.includes('surface'), '复用键**不得**含 reading');

  // ② 读法翻转（第二类强制 rebuild）⇒ 键不含 reading ⇒ 仍复用
  probe.setReading('underneath');
  const c2 = probe.characterInstanceChurnReport();
  assert.equal(c2.created, c0.created, 'setReading 触发的 rebuild 必须复用（键不含 reading）');
  assert.ok(c2.reused > c1.reused, 'setReading 触发的 rebuild 必须计入 reused');

  // ③ 位置变化 ⇒ 只更新变换，不重建
  snap(probe, [npcEntity('npc-006', 1500)], 2);
  const c3 = probe.characterInstanceChurnReport();
  assert.equal(c3.created, c0.created, '位置变化不得重建实例（键不含位置）');
  assert.equal(probe.characterInstanceReport().length, 1);
  assert.equal(c3.last_rebuild_tick, 2);
});

test('fu010_ac1_prune_disposes_removed_entity', () => {
  const probe = newProbe();
  snap(probe, [npcEntity('npc-006', 0)], 0);
  const before = probe.characterInstanceChurnReport();
  snap(probe, [], 1);
  const after = probe.characterInstanceChurnReport();
  assert.equal(after.disposed, before.disposed + 1, '实体消失 ⇒ 必须真 dispose（disposed +1）');
  assert.equal(after.created, before.created, '剪枝不得产生新实例');
  assert.equal(probe.characterInstanceReport().length, 0, '剪枝后角色实例注册表为空');
  const ids = probe.structureReport().objects.map((object) => String((object as { id: unknown }).id));
  assert.ok(!ids.includes('character-instance:npc-006'), '场景图不得残留被剪枝的角色实例节点（幽灵渲染）');
  assert.equal(probe.characterFramingReport().length, 0, 'framing 读数不得残留被剪枝的实例');
});

test('fu010_ac1_rebuild_normalizes_reused_instance_transform', () => {
  const probe = newProbe();
  snap(probe, [npcEntity('npc-006', 0)], 0);
  probe.setReading('surface');
  const first = probe.structureReport();
  probe.renderOnce();                 // 由 renderFrame 施加 displayed 变换
  probe.setReading('underneath');     // 复用实例 + **归一化回基线新建态**（Raven C-5 / 设计 §12.2）
  const second = probe.structureReport();
  assert.equal(second.objects_digest, first.objects_digest,
    '复用后必须把实例 group 变换归一化回基线新建态 ⇒ 两次 structureReport 逐项相同（C-5）');
});

test('fu010_ac2_framing_empty_group_has_no_geometry_and_no_nan', () => {
  const probe = newProbe();
  snap(probe, [npcEntity('npc-006', 0)], 0);
  const rows = probe.characterFramingReport();
  assert.equal(rows.length, 1);
  const row = rows[0] as Record<string, unknown>;
  assert.equal(row.has_geometry, false, 'GLB 未加载（空组）⇒ has_geometry=false');
  assert.equal(row.in_viewport, false);
  assert.equal(row.fully_in_viewport, false);
  assert.equal(row.screen_rect, null);
  assert.equal(row.height_fraction, null);
  assert.equal(row.area_fraction, null);
  assert.equal(row.aabb_min, null);
  assert.equal(row.aabb_max, null);
  assertNoNonFinite(rows, 'framing');
  assert.ok(!JSON.stringify(rows).includes('NaN'), 'JSON 序列化后不得出现 NaN');
  // 负对照（非自指）：把同一条读数篡改成「有几何」⇒ 同一条断言必须判假
  const tampered = rows.map((item) => ({ ...item, has_geometry: true }));
  assert.ok(!tampered.every((item) => item.has_geometry === false), '负对照：篡改 has_geometry ⇒ 原断言判假');
});

test('fu010_ac2_auto_focus_frames_known_body_and_negative_controls', () => {
  const probe = newProbe();
  snap(probe, [npcEntity('npc-006', 0)], 0);
  assert.deepEqual(probe.cameraReport().position, [18, 14, 24], '默认（未开启对焦）⇒ 默认取景常量原样');

  probe.setCharacterLoader(syncLoader(knownBodyScene()));
  assert.equal((probe.characterInstanceReport()[0] as Record<string, unknown>).glb_loaded, true,
    '假 loader 同步回填 ⇒ glb_loaded=true');
  snap(probe, [npcEntity('npc-006', 0)], 1);
  assert.deepEqual(probe.cameraReport().position, [18, 14, 24], '对焦默认关 ⇒ 连续 apply 不改相机');

  const result = probe.setAutoObservationFocus(true);
  assert.equal(result.enabled, true);
  assert.equal(result.applied, 1, '唯一真 GLB 实体 ⇒ 恰好一个对焦机会被施加');
  const focusRows = probe.focusViewReport();
  assert.equal(focusRows.length, 1);
  assert.equal(focusRows[0]?.source, 'aabb');
  assert.equal(focusRows[0]?.entity_id, 'npc-006');

  const row = probe.characterFramingReport()[0] as Record<string, unknown>;
  assert.equal(row.has_geometry, true);
  assert.equal(row.fully_in_viewport, true, `AABB 必须整体入画：${JSON.stringify(row)}`);
  assert.ok(Number(row.height_fraction) >= 0.30, `height_fraction=${String(row.height_fraction)} 必须 ≥ 0.30`);
  assert.ok(Number(row.area_fraction) >= 0.05, `area_fraction=${String(row.area_fraction)} 必须 ≥ 0.05`);
  assertNoNonFinite(row, 'framing');
  const min = row.aabb_min as number[]; const max = row.aabb_max as number[];
  assert.ok(Math.abs((max[1] as number) - (min[1] as number) - 1.8) < 1e-3,
    `GLB 世界 AABB 高应为 1.8 m，实测 ${(max[1] as number) - (min[1] as number)}`);

  // 负对照 ①：对焦关闭 + setObservationCamera(null) ⇒ AC-2 复合判据必须为假
  probe.setAutoObservationFocus(false);
  probe.setObservationCamera(null);
  const def = probe.characterFramingReport()[0] as Record<string, unknown>;
  assert.equal(passesAc2(def), false, `默认取景必须判负：${JSON.stringify(def)}`);

  // 负对照 ②：相机整体移远 10 m ⇒ AC-2 复合判据必须为假，且占高必须真的下降
  const position = row.camera_position as number[];
  const center = [(min[0] as number + (max[0] as number)) / 2,
    (min[1] as number + (max[1] as number)) / 2, (min[2] as number + (max[2] as number)) / 2];
  probe.setObservationCamera({ position_m: [position[0] as number, position[1] as number, (position[2] as number) + 10],
    look_at_m: [center[0] as number, center[1] as number, center[2] as number] });
  const far = probe.characterFramingReport()[0] as Record<string, unknown>;
  assert.equal(passesAc2(far), false, `移远 10 m 后仍达标 ⇒ 读数无牙：${JSON.stringify(far)}`);
  assert.ok(Number(far.height_fraction) < Number(row.height_fraction), '移远后占高必须下降（读数真的受相机影响）');
});

test('fu010_ac2_auto_focus_stops_applying_in_interactive_camera', () => {
  const probe = newProbe();
  snap(probe, [npcEntity('npc-006', 0)], 0);
  probe.setCharacterLoader(syncLoader(knownBodyScene()));
  probe.setAutoObservationFocus(true);
  assert.notDeepEqual(probe.cameraReport().position, [18, 14, 24],
    '开启对焦后相机必须真的移动（否则「保持不变」那条断言没有牙）');
  probe.renderOnce();   // 逐帧跟随路径
  assert.equal((probe.characterFramingReport()[0] as Record<string, unknown>).fully_in_viewport, true,
    '逐帧跟随（renderOnce）之后仍必须整体入画');

  probe.enterInteractiveCamera();
  const before = probe.cameraReport().position;
  for (let tick = 1; tick <= 5; tick += 1) { snap(probe, [npcEntity('npc-006', tick * 100)], tick); probe.renderOnce(); }
  assert.deepEqual(probe.cameraReport().position, before,
    '进入交互相机后连续 apply + renderOnce ⇒ 相机位置不得被对焦改动');
  const rows = probe.focusViewReport();
  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.source, 'none');
  assert.equal(rows[0]?.reason, 'camera_mode:interactive');
  const report = probe.presentationReport() as { camera?: { camera_mode?: string } };
  assert.equal(report.camera?.camera_mode, 'interactive');
});

// ─────────────────────────────────────────────────────────────────────────────
// r2 修复迭代（MUST-1 / MUST-2 / MUST-3）—— 对应哨兵 MED-1 与侦察官 MEDIUM-1 / LOW-1
//
// MUST-1：AC-2 机位派生式改为**深度感知**（近面基准）。本节的转身姿态用例是它的**确定性 RED**：
//   在 r1 的派生式下（`dV=(h/2)/tan(vfov/2)`，不含 dp）该姿态 `fully_in_viewport=false`
//   （在树副本上实测，见 evidence/r2），本用例即断言之。
// MUST-3：`fully_in_viewport` 增**深度**条件（`|z_ndc|<=1`）——把相机推到 `far` 之外必须判假。
// MUST-2：`dispose()` 之后的**在飞** `onLoad` 必须短路（脱链实例不得持 GLB 资源）。

/** 可指定视口的探针（AC-2 两档：桌面 1440×900、窄屏 390×844）。 */
const newProbeSized = (w: number, h: number) =>
  createScene({ ...CANVAS_STUB_FU010, clientWidth: w, clientHeight: h } as never, { worldview: TONE_FU010 as never });

/**
 * 转身姿态的已知体：x 向 1.141 m / z 向 0.839 m 的盒绕 Y 转 90°
 * ⇒ 世界 AABB 变成 `w=0.839 / dp=1.141`（≥1.04，命中哨兵记录的失败族 dp∈[1.04,1.18]）；
 * 身高 1.5066 m = 真 GLB 实测世界 AABB 高（sentinel/Artisan 证据同源）。
 */
function turnedBodyScene() {
  const root = new THREE.Group();
  root.name = 'fake-glb-turned-body';
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.141, 1.5066, 0.839), new THREE.MeshBasicMaterial());
  body.position.set(0, 0.7533, 0); // 脚底落 y=0
  root.add(body);
  root.rotation.y = Math.PI / 2;
  return root;
}

test('fu010_r2_ac2_deep_aabb_turned_pose_is_fully_in_viewport_both_viewports', () => {
  for (const [w, h] of [[1440, 900], [390, 844]] as const) {
    const probe = newProbeSized(w, h);
    snap(probe, [npcEntity('npc-006', 0)], 0);
    probe.setCharacterLoader(syncLoader(turnedBodyScene()));
    const applied = probe.setAutoObservationFocus(true);
    assert.equal(applied.applied, 1, `${w}×${h}：唯一真 GLB 实体 ⇒ 对焦必须被施加`);
    const row = probe.characterFramingReport()[0] as Record<string, unknown>;
    const min = row.aabb_min as number[];
    const max = row.aabb_max as number[];
    const dp = (max[2] as number) - (min[2] as number);
    assert.ok(dp >= 1.04, `${w}×${h}：转身姿态 AABB 深度必须 ≥ 1.04 m（覆盖 r1 失败族），实测 ${dp}`);
    assert.equal(row.fully_in_viewport, true,
      `${w}×${h}：转身姿态（dp=${dp}）必须整体入画（MUST-1）：${JSON.stringify(row)}`);
    assert.ok(Number(row.height_fraction) >= 0.30,
      `${w}×${h}：height_fraction=${String(row.height_fraction)} 必须 ≥ 0.30`);
    assert.ok(Number(row.area_fraction) >= 0.05,
      `${w}×${h}：area_fraction=${String(row.area_fraction)} 必须 ≥ 0.05`);
    assertNoNonFinite(row, `framing-turned@${w}x${h}`);
  }
});

test('fu010_r2_fully_in_viewport_checks_depth_not_only_xy', () => {
  const probe = newProbe();
  snap(probe, [npcEntity('npc-006', 0)], 0);
  probe.setCharacterLoader(syncLoader(knownBodyScene()));
  probe.setAutoObservationFocus(true);
  const near = probe.characterFramingReport()[0] as Record<string, unknown>;
  assert.equal(near.fully_in_viewport, true, '正常对焦姿态仍必须整体入画（深度检查不得误伤正例）');

  const min = near.aabb_min as number[];
  const max = near.aabb_max as number[];
  const cx = ((min[0] as number) + (max[0] as number)) / 2;
  const cy = ((min[1] as number) + (max[1] as number)) / 2;
  const cz = ((min[2] as number) + (max[2] as number)) / 2;
  const far = Number(probe.cameraReport().far);
  assert.ok(Number.isFinite(far) && far > 0, `相机 far 必须可读，实测 ${far}`);

  // ① 深度：相机沿 +z 推到 `far` 之外 ⇒ x/y 仍在视口内，**只有**深度条件能判假（r1 会「入画假绿」）
  probe.setObservationCamera({ position_m: [cx, cy, cz + far * 1.5], look_at_m: [cx, cy, cz] });
  const beyond = probe.characterFramingReport()[0] as Record<string, unknown>;
  assert.equal(beyond.in_viewport, true, '相机推到 far 之外时横向仍在视口内（否则本负对照不专测深度）');
  assert.equal(beyond.fully_in_viewport, false,
    `超出 far ⇒ 必须判「未整体入画」（MUST-3）：${JSON.stringify(beyond)}`);
  assertNoNonFinite(beyond, 'framing-beyond-far');

  // ② 横向：相机移偏，物体落到水平视锥之外 ⇒ 仍判假（既有 x/y 条件不得被削弱）
  probe.setObservationCamera({ position_m: [cx, cy, cz + 3], look_at_m: [cx + 3, cy, cz] });
  const offAxis = probe.characterFramingReport()[0] as Record<string, unknown>;
  assert.equal(offAxis.fully_in_viewport, false, '物体落到水平视锥外必须判假（x/y 条件未被削弱）');
});

test('fu010_r2_dispose_blocks_inflight_glb_load_callback', () => {
  let pending: ((gltf: unknown) => void) | null = null;
  const deferredLoader = {
    load(_url: string, onLoad: (gltf: unknown) => void) { pending = onLoad; },
  };
  const instance = createCharacterInstance({ entityId: 'npc-006', gltfLoader: deferredLoader as never });
  assert.equal(instance.glbLoaded(), false, '回调未触发前 glb_loaded 必须为 false');
  assert.equal(instance.group.children.length, 0);
  const fire = pending as ((gltf: unknown) => void) | null;
  assert.ok(fire, '可延迟假 loader 必须真的被调用（否则本用例无牙）');

  instance.dispose();                    // 剪枝路径调用的就是这一个方法
  fire({ scene: knownBodyScene() });     // **在飞**回调晚到
  assert.equal(instance.group.children.length, 0,
    'dispose 后晚到的 onLoad 不得把 GLB 挂回已脱链 group（MUST-2）');
  assert.equal(instance.glbLoaded(), false, 'dispose 后晚到的 onLoad 不得把 glb_loaded 置 true');
  const report = instance.report();
  assert.equal(report.glb_loaded, false, 'report() 的 glb_loaded 仍为 false');
  assertNoNonFinite(report, 'character-instance-after-dispose');
});

test('fu010_r2_delta_move_reapplies_focus_so_framing_stays_consistent', () => {
  const probe = newProbe();
  snap(probe, [npcEntity('npc-006', 0)], 0);
  probe.setCharacterLoader(syncLoader(knownBodyScene()));
  probe.setAutoObservationFocus(true);
  const before = probe.characterFramingReport()[0] as Record<string, unknown>;
  assert.equal(before.fully_in_viewport, true, 'snapshot 后必须整体入画');

  // 纯 **delta** 位移（不触发 rebuild/snapshot）：根 mesh 被直接改位置，而实例 group 要到
  // 下一帧 renderFrame 才写回 `displayed − parent` ⇒ 若 delta 分支不重算对焦，此读数的
  // AABB 与相机就**不同源**（窄屏即出现瞬态 `fully_in_viewport=false`）。
  probe.apply({
    t: 'delta', tick: 1,
    ops: [{ op: 'set', entity: 'npc-006', component: 'transform', value: { pos_mm: { x: 5000, y: 0, z: 0 } } }],
  } as never);
  const after = probe.characterFramingReport()[0] as Record<string, unknown>;
  const min = after.aabb_min as number[];
  assert.ok(Number(min[0]) > 4, `delta 后实例世界位置必须真的移动，实测 aabb_min.x=${String(min[0])}`);
  assert.equal(after.fully_in_viewport, true,
    `delta 后相机必须与 AABB 同源（否则窄屏会读到瞬态未入画）：${JSON.stringify(after)}`);
  assertNoNonFinite(after, 'framing-after-delta');
});

test('fu010_r2_prune_path_disposes_and_late_load_does_not_revive_instance', () => {
  const probe = newProbe();
  let pending: ((gltf: unknown) => void) | null = null;
  probe.setCharacterLoader({ load(_url: string, onLoad: (gltf: unknown) => void) { pending = onLoad; } } as never);
  snap(probe, [npcEntity('npc-006', 0)], 0);
  const fire = pending as ((gltf: unknown) => void) | null;
  assert.ok(fire, '剪枝前必须已启动 GLB 加载（在飞窗口）');

  const before = probe.characterInstanceChurnReport();
  snap(probe, [], 1);                    // 剪枝 ⇒ 世界层真 dispose()
  const after = probe.characterInstanceChurnReport();
  assert.equal(after.disposed, before.disposed + 1, '剪枝必须真 dispose（disposed +1）');
  assert.equal(probe.characterInstanceReport().length, 0);

  fire({ scene: knownBodyScene() });     // 晚到回调：不得复活已剪枝实例
  assert.equal(probe.characterInstanceReport().length, 0, '晚到回调不得复活已剪枝实例');
  assert.equal(probe.characterFramingReport().length, 0, '晚到回调不得让 framing 面出现幽灵行');
  const ids = probe.structureReport().objects.map((object) => String((object as { id: unknown }).id));
  assert.ok(!ids.includes('character-instance:npc-006'), '场景图不得残留被剪枝的角色实例节点');
});

// ─────────────────────────────────────────────────────────────────────────────
// lowfix 微修轮（L-2 / L-3）—— REQ-20260924-010 的 AC-1 / AC-2
//
// L-2：`dispose()` 之后**晚到的失败**（`onError`）必须与成功路径**同口径短路** ——
//   既不写实例局部 `degradations`，也不写模块级降级表；`dispose()` **之前**的失败**照记**。
// L-3：`focusCandidates()` 的「真 GLB」判据从「`glb_url` 非空」升级为
//   「交付资产登记面在册 ∧ `'assets/' + path === glb_url` ∧ 未被 `runtime_excluded`」，
//   并用负对照 A/B/C + GT-1（前向不变式）证明它**既不恒真也不恒假**。
// 夹具一律在**进程内运行时**改写绑定表 + `try/finally` 还原（不改冻结件、不写交付树）。

/** 运行时绑定表夹具：临时改写只读字段，`restore()` 逐字段还原。 */
function bindingFixture() {
  const saved = BINDINGS.map((binding) => ({ entity_ids: [...binding.entity_ids], glb_url: binding.glb_url }));
  return {
    set(index: number, patch: { entity_ids?: string[]; glb_url?: string }) {
      const target = BINDINGS[index] as unknown as { entity_ids: string[]; glb_url: string };
      if (patch.entity_ids !== undefined) target.entity_ids = patch.entity_ids;
      if (patch.glb_url !== undefined) target.glb_url = patch.glb_url;
    },
    restore() {
      BINDINGS.forEach((binding, index) => {
        const target = binding as unknown as { entity_ids: string[]; glb_url: string };
        target.entity_ids = [...(saved[index] as { entity_ids: string[] }).entity_ids];
        target.glb_url = (saved[index] as { glb_url: string }).glb_url;
      });
    },
  };
}

/** 对焦**关**模式读出候选集（`focusViewReport()` 按候选各一条 `reason:'disabled'`）。 */
function focusCandidateIds(probe: ReturnType<typeof newProbe>): string[] {
  probe.setAutoObservationFocus(false);
  return probe.focusViewReport().map((row) => row.entity_id).sort();
}

const failedCodesOf = (report: Record<string, unknown>): string[] =>
  (report.degradations as Array<{ code: string }>).map((row) => row.code);

test('lowfix_ac1_dispose_short_circuits_late_failure_writes', () => {
  // 可**延迟触发** `onError` 的假 loader（构造期只捕获回调，不回调）
  let pendingError: ((error: unknown) => void) | null = null;
  const deferredLoader = {
    load(_url: string, _onLoad: (gltf: unknown) => void, _onProgress?: unknown, onError?: (e: unknown) => void) {
      pendingError = onError ?? null;
    },
  };

  // ① 正对照：未 `dispose()` 的失败**必须照记**（两张表各 +1）—— 防把判据改成恒真
  clearBindingDegradations();
  const live = createCharacterInstance({ entityId: 'npc-006', gltfLoader: deferredLoader as never });
  const liveBefore = (live.report().degradations as unknown[]).length;
  const fireLive = pendingError as ((error: unknown) => void) | null;
  assert.ok(fireLive, '可延迟假 loader 必须真的被调用（否则本用例无牙）');
  fireLive(new Error('pre-dispose'));
  assert.equal((live.report().degradations as unknown[]).length, liveBefore + 1, 'dispose 之前的失败必须照记（实例局部）');
  assert.equal(bindingDegradationsSnapshot().length, 1, 'dispose 之前的失败必须照记（模块级降级表）');
  assert.ok(failedCodesOf(live.report()).includes('E_GLB_LOAD_FAILED'),
    `失败码必须仍为 E_GLB_LOAD_FAILED：${JSON.stringify(failedCodesOf(live.report()))}`);

  // ② 判据：`dispose()` 之后晚到的 `onError` ⇒ 两张表 **delta 0**
  clearBindingDegradations();
  pendingError = null;
  const pruned = createCharacterInstance({ entityId: 'npc-006', gltfLoader: deferredLoader as never });
  const firePruned = pendingError as ((error: unknown) => void) | null;
  assert.ok(firePruned, '剪枝路径的 loader 同样必须被调用');
  const localBefore = (pruned.report().degradations as unknown[]).length;
  pruned.dispose();
  clearBindingDegradations();
  const moduleBefore = bindingDegradationsSnapshot().length;
  firePruned(new Error('post-dispose-1'));
  firePruned(new Error('post-dispose-2'));
  assert.equal((pruned.report().degradations as unknown[]).length, localBefore, 'dispose 之后晚到的失败不得写实例局部 degradations');
  assert.equal(bindingDegradationsSnapshot().length, moduleBefore,
    'dispose 之后晚到的失败不得写模块级降级表（bindingDegradationsSnapshot 长度不变）');
  assert.equal(moduleBefore, 0);
  assert.equal(pruned.group.children.length, 0, '既有 r2 语义保持：脱链 group 不挂 GLB');
  assert.equal(pruned.glbLoaded(), false);
  assert.equal(pruned.report().glb_loaded, false);
  assertNoNonFinite(pruned.report(), 'character-instance-after-dispose-failure');
});

test('lowfix_ac1_dispose_short_circuit_does_not_swallow_pre_dispose_failures', () => {
  // 与上一条配对：短路**不得过宽** —— `dispose()` 之前的失败码必须真的在账
  clearBindingDegradations();
  let pendingError: ((error: unknown) => void) | null = null;
  const deferredLoader = {
    load(_url: string, _onLoad: (gltf: unknown) => void, _onProgress?: unknown, onError?: (e: unknown) => void) {
      pendingError = onError ?? null;
    },
  };
  const instance = createCharacterInstance({ entityId: 'npc-006', gltfLoader: deferredLoader as never });
  (pendingError as ((error: unknown) => void) | null)?.(new Error('pre'));
  instance.dispose();
  (pendingError as ((error: unknown) => void) | null)?.(new Error('post'));

  assert.deepEqual(failedCodesOf(instance.report()), ['E_GLB_LOAD_FAILED'],
    'dispose 之前的失败必须留在实例账上，且晚到的那次不得追加');
  assert.deepEqual(bindingDegradationsSnapshot().map((row) => row.code), ['E_GLB_LOAD_FAILED'],
    '模块级降级表必须恰有一条（dispose 之前的那次）');
  clearBindingDegradations();

  // 外层 `catch` 分支：构造期同步抛错必须照记。
  // ⚠️ 该分支在 `dispose()` 之后**结构上不可达**（`gltfLoader.load(...)` 只在构造期调用一次，
  // 且在 `createCharacterInstance()` 返回前已完成 —— 见设计 §2.3）⇒ 此处只取它的**可执行形态**
  // = 构造期读数，**不谎称**已构造「dispose 之后 catch 仍执行」的场景。
  const throwing = createCharacterInstance({
    entityId: 'npc-006', gltfLoader: { load() { throw new Error('sync'); } } as never,
  });
  assert.deepEqual(failedCodesOf(throwing.report()), ['E_GLB_LOAD_THREW']);
  assert.deepEqual(bindingDegradationsSnapshot().map((row) => row.code), ['E_GLB_LOAD_THREW']);
  clearBindingDegradations();
});

test('lowfix_ac2_placeholder_binding_is_not_a_focus_target_and_real_glb_is', () => {
  const fixture = bindingFixture();
  const probe = newProbe();
  try {
    // ── 夹具 A：把占位/回落绑定 `npc_generic`（盘上无 `generic-fallback.glb`）挂上 `npc-009`
    fixture.set(1, { entity_ids: ['npc-009'] });
    snap(probe, [npcEntity('npc-006', 0), npcEntity('npc-009', 100)], 0);
    const instances = probe.characterInstanceReport().map((row) => String(row.entity_id)).sort();
    assert.ok(instances.includes('npc-009'),
      `夹具必须让 npc-009 真在 characterInstanceReport() 里（否则「不含」可能因无关原因恒真）：${JSON.stringify(instances)}`);
    assert.equal(bindingForEntity('npc-009')?.binding_id, 'npc_generic');

    // 旧判据读数（证明夹具生效 + 旧判据确有缺陷）：占位绑定的 `glb_url` 非空 ⇒ 旧判据含它
    assert.equal(Boolean(bindingForEntity('npc-009')?.glb_url), true,
      '旧判据 `Boolean(bindingForEntity(id)?.glb_url)` 必须为 true（占位绑定有非空 glb_url）');
    const candidatesA = focusCandidateIds(probe);
    assert.ok(!candidatesA.includes('npc-009'),
      `占位/回落绑定不得成为对焦目标（负对照 A）：实测候选 ${JSON.stringify(candidatesA)}`);
    assert.ok(candidatesA.includes('npc-006'), '同日真 GLB 实体 npc-006 必须仍在候选里');

    // ── 夹具 B：真 GLB 绑定 `xuqin_default` 挂上 `npc-009` —— **同一份场景快照**，只换夹具
    fixture.set(1, { entity_ids: [] });
    fixture.set(0, { entity_ids: ['npc-006', 'npc-009'] });
    assert.equal(Boolean(bindingForEntity('npc-009')?.glb_url), true);
    assert.equal(bindingForEntity('npc-009')?.binding_id, 'xuqin_default');
    const candidatesB = focusCandidateIds(probe);
    assert.ok(candidatesB.includes('npc-009'),
      `真 GLB 绑定必须进候选（证明新判据不恒假）：实测候选 ${JSON.stringify(candidatesB)}`);
    assert.equal(probe.characterInstanceReport().length, instances.length, 'B 臂必须复用同一次场景快照（不重拍）');

    // ── 夹具 C（v2）：`binding_ref` 在册但 `path` 与 `glb_url` **不一致** ⇒ 新判据判假
    fixture.set(0, { entity_ids: ['npc-006'], glb_url: 'assets/character/xuqin-body-ALT.glb' });
    assert.equal(Boolean(bindingForEntity('npc-006')?.glb_url), true,
      '旧判据对 path 不一致的合成分回仍读 true（本臂专测新判据）');
    const candidatesC = focusCandidateIds(probe);
    assert.ok(!candidatesC.includes('npc-006'),
      `binding_ref 在册但 path 不一致 ⇒ 必须判假（负对照 C）：实测候选 ${JSON.stringify(candidatesC)}`);
  } finally {
    fixture.restore();
  }
  assert.equal(bindingForEntity('npc-009'), null, '夹具必须完全还原（防泄漏到后续用例）');
  assert.equal(BINDINGS[0].glb_url, 'assets/character/xuqin-body.glb', '夹具必须还原 glb_url');
  assert.deepEqual([...BINDINGS[0].entity_ids], ['npc-006']);
  assert.deepEqual([...BINDINGS[1].entity_ids], []);
});

test('lowfix_ac2_today_world_candidates_are_unchanged', () => {
  const probe = newProbe();
  snap(probe, [npcEntity('npc-006', 0)], 0);
  assert.equal(Boolean(bindingForEntity('npc-006')?.glb_url), true, '今日世界旧判据读数（行为逐项不变的对照面）');
  assert.deepEqual(focusCandidateIds(probe), ['npc-006'],
    '今日世界候选集必须恰为 [npc-006]（升级判据不得改变既有行为）');

  // 注入已知体位的假 loader ⇒ 唯一候选必须仍被**真的**施加对焦（既有 AC-2 行为逐项不变）
  probe.setCharacterLoader(syncLoader(knownBodyScene()));
  assert.equal(probe.characterInstanceReport()[0]?.glb_loaded, true, '假 loader 同步回填 ⇒ glb_loaded=true');
  assert.equal(probe.setAutoObservationFocus(true).applied, 1, '真 GLB 实体在册 ⇒ 唯一候选仍会被施加对焦');
  const rows = probe.focusViewReport();
  assert.equal(rows.length, 1, '候选恰 1 个 ⇒ 恰 1 条对焦记录');
  assert.equal(rows[0]?.entity_id, 'npc-006');
  assert.equal(rows[0]?.source, 'aabb', '候选在册且几何非空 ⇒ 必须真的按 AABB 派生（不得退化为 source:none）');
  assert.equal(probe.characterFramingReport()[0]?.fully_in_viewport, true, '既有取景结论不得被本轮改动影响');
  probe.setAutoObservationFocus(false);
});

test('lowfix_ac2_forward_invariant_mounted_glb_bindings_are_registered', () => {
  /** 与 `focusCandidates()` 同一条判据表达式（作用在**交付树导出的**登记面 `ASSET_ENTRIES` 上）。 */
  const inRegistry = (
    entries: readonly Record<string, unknown>[],
    binding: { binding_id: string; glb_url: string },
  ) => entries.some((entry) => entry.binding_ref === `binding:${binding.binding_id}`
    && typeof entry.path === 'string'
    && `assets/${entry.path}` === binding.glb_url
    && !entry.runtime_excluded);

  const mounted = BINDINGS.filter((binding) => binding.entity_ids.length > 0 && binding.glb_url.endsWith('.glb'));
  assert.ok(mounted.length >= 1, '今日世界必须至少有一个「已挂载 ∧ 真 GLB」绑定（否则本不变式无牙）');
  for (const binding of mounted) {
    assert.ok(inRegistry(ASSET_ENTRIES, binding),
      `已挂载的真 GLB 绑定必须在交付登记面在册且 path 双侧一致：${binding.binding_id} / ${binding.glb_url}`);
  }

  // 负对照 ①：合成「已挂载但未在册」的绑定 ⇒ 同一表达式必须判假
  assert.equal(inRegistry(ASSET_ENTRIES, { binding_id: 'shadow_default', glb_url: 'assets/character/shadow.glb' }), false,
    '未在册的合成绑定必须判假（本判据有牙）');
  // 负对照 ②：在册但 `path` 不一致 ⇒ 判假（v2 的合取项真的参与）
  assert.equal(inRegistry(ASSET_ENTRIES, { binding_id: 'xuqin_default', glb_url: 'assets/character/xuqin-body-ALT.glb' }), false,
    'path 不一致的合成绑定必须判假');
  // 正对照：今日真绑定 ⇒ 判真
  assert.equal(inRegistry(ASSET_ENTRIES, { binding_id: 'xuqin_default', glb_url: 'assets/character/xuqin-body.glb' }), true);
  // fail-closed：登记面为空（等价于 `assets` 缺失/非数组 ⇒ `ASSET_ENTRIES = []`）⇒ 判假且不抛
  assert.equal(inRegistry([], { binding_id: 'xuqin_default', glb_url: 'assets/character/xuqin-body.glb' }), false);
});

// ═════════════════════════════════════════════════════════════════════════════
// REQ-20261012-001 · 观察面板 v2：T1 折叠 / T2 观察对象可切换 / 写入口加严 / 回读面
//
// 本环境**没有** jsdom / happy-dom（`node_modules` 内无该类包）⇒ 自带最小 DOM stub。
// stub 只实现被测代码真正用到的 API（`createElement` / `querySelector(All)` / `dataset` /
// `classList` / `textContent` / `append` / `setAttribute` / `addEventListener`），
// **不做**浏览器语义仿真：真实布局（高度 / 溢出）与 console 判据由**真浏览器面**负责
// （`<ws>/evidence/artisan/browser/`），本文件只判"逻辑与登记面"。
// ═════════════════════════════════════════════════════════════════════════════

interface StubElement {
  tagName: string; id: string; type: string; className: string; textContent: string;
  dataset: Record<string, string>; attributes: Map<string, string>;
  children: StubElement[]; parentNode: StubElement | null;
  // r2（MUST-3）：shadow root / 子文档 的承载字段
  shadowRoot: StubElement | null; contentDocument: StubElement | null;
  attachShadow(init?: { mode?: string }): StubElement;
  mode?: string; host?: StubElement | null;
  classList: { add(...n: string[]): void; remove(...n: string[]): void; contains(n: string): boolean; toggle(n: string, force?: boolean): boolean };
  append(...nodes: StubElement[]): void; remove(): void;
  setAttribute(name: string, value: string): void; getAttribute(name: string): string | null;
  addEventListener(type: string, handler: () => void): void; click(): void;
  matches(selector: string): boolean; querySelector(selector: string): StubElement | null;
  querySelectorAll(selector: string): StubElement[];
  getBoundingClientRect(): { height: number; width: number };
}

function parseSimpleSelector(selector: string): {
  tag: string | null; id: string | null; classes: string[]; attrs: Array<{ name: string; value: string | null }>;
} {
  const out: { tag: string | null; id: string | null; classes: string[]; attrs: Array<{ name: string; value: string | null }> }
    = { tag: null, id: null, classes: [], attrs: [] };
  let rest = selector.trim();
  const attrRe = /\[([^\]]+)\]/g;
  let match: RegExpExecArray | null;
  while ((match = attrRe.exec(rest)) !== null) {
    const raw = match[1] ?? '';
    const eq = raw.indexOf('=');
    out.attrs.push(eq === -1
      ? { name: raw.trim(), value: null }
      : { name: raw.slice(0, eq).trim(), value: raw.slice(eq + 1).trim().replace(/^["']|["']$/g, '') });
  }
  rest = rest.replace(attrRe, '');
  const idMatch = /#([A-Za-z0-9_-]+)/.exec(rest);
  if (idMatch) out.id = idMatch[1] ?? null;
  rest = rest.replace(/#[A-Za-z0-9_-]+/g, '');
  out.classes = (rest.match(/\.[A-Za-z0-9_-]+/g) ?? []).map((item) => item.slice(1));
  rest = rest.replace(/\.[A-Za-z0-9_-]+/g, '');
  if (rest.trim()) out.tag = rest.trim().toUpperCase();
  return out;
}

function createStubElement(tagName: string): StubElement {
  const node: StubElement = {
    tagName: tagName.toUpperCase(), id: '', type: '', className: '', textContent: '',
    dataset: {}, attributes: new Map(), children: [], parentNode: null,
    // r2（MUST-3）：**刻意不进 `children`** —— 复现「宿主元素的 `querySelectorAll` 看不见 shadow/子文档内部」
    shadowRoot: null, contentDocument: null,
    attachShadow(init?: { mode?: string }) {
      const root = stubElement('#shadow-root');
      root.mode = init?.mode ?? 'open';
      root.host = node;
      node.shadowRoot = root;
      return root;
    },
    classList: {
      add(...names: string[]) {
        const set = new Set(node.className.split(/\s+/).filter(Boolean));
        for (const name of names) set.add(name);
        node.className = [...set].join(' ');
      },
      remove(...names: string[]) {
        const set = new Set(node.className.split(/\s+/).filter(Boolean));
        for (const name of names) set.delete(name);
        node.className = [...set].join(' ');
      },
      contains(name: string) { return node.className.split(/\s+/).filter(Boolean).includes(name); },
      toggle(name: string, force?: boolean) {
        const want = force === undefined ? !this.contains(name) : Boolean(force);
        if (want) this.add(name); else this.remove(name);
        return want;
      },
    },
    append(...nodes: StubElement[]) {
      for (const child of nodes) {
        if (child.parentNode) child.remove();
        child.parentNode = node;
        node.children.push(child);
      }
    },
    remove() {
      const parent = node.parentNode;
      if (!parent) return;
      const index = parent.children.indexOf(node);
      if (index >= 0) parent.children.splice(index, 1);
      node.parentNode = null;
    },
    setAttribute(name: string, value: string) {
      const text = String(value);
      node.attributes.set(name, text);
      if (name === 'id') node.id = text;
      else if (name === 'class') node.className = text;
      else if (name === 'type') node.type = text;
    },
    getAttribute(name: string) {
      if (node.attributes.has(name)) return node.attributes.get(name) ?? null;
      if (name === 'type') return node.type === '' ? null : node.type;
      if (name === 'id') return node.id === '' ? null : node.id;
      if (name === 'class') return node.className === '' ? null : node.className;
      return null;
    },
    addEventListener(type: string, handler: () => void) {
      void type;
      handlers.get(node)!.push(handler);
    },
    click() { for (const handler of [...(handlers.get(node) ?? [])]) handler(); },
    matches(selector: string) {
      const simple = parseSimpleSelector(selector);
      if (simple.tag && node.tagName !== simple.tag) return false;
      if (simple.id && node.id !== simple.id) return false;
      for (const cls of simple.classes) if (!node.className.split(/\s+/).includes(cls)) return false;
      for (const attr of simple.attrs) {
        const value = node.getAttribute(attr.name);
        if (value === null) return false;
        if (attr.value !== null && value !== attr.value) return false;
      }
      return true;
    },
    querySelectorAll(selector: string) {
      const parts = selector.split(',').map((item) => item.trim()).filter(Boolean);
      const out: StubElement[] = [];
      const walk = (current: StubElement) => {
        for (const child of current.children) {
          if (parts.some((part) => child.matches(part))) out.push(child);
          walk(child);
        }
      };
      walk(node);
      return out;
    },
    querySelector(selector: string) { return node.querySelectorAll(selector)[0] ?? null; },
    getBoundingClientRect() { return { height: 0, width: 0 }; },
  };
  return node;
}

/** stub 的 click 处理器表（按元素对象存；不进 `dataset`，避免污染读数）。 */
const handlers = new WeakMap<StubElement, Array<() => void>>();

function stubElement(tagName: string): StubElement {
  const node = createStubElement(tagName);
  handlers.set(node, []);
  // r2：`createStubElement` 的选择器解析把 `*` 当标签名 ⇒ 这里**追加**（不改写 r1 已落下的行）
  // 一个只影响本 stub 的通用选择器通道，使 `querySelectorAll('*')` 可用于 MUST-3 的下钻断言。
  const rawQuerySelectorAll = node.querySelectorAll.bind(node);
  node.querySelectorAll = (selector: string) => {
    const parts = selector.split(',').map((item) => item.trim()).filter(Boolean);
    if (parts.length > 0 && parts.every((part) => part === '*')) {
      const out: StubElement[] = [];
      const walk = (current: StubElement) => {
        for (const child of current.children) { out.push(child); walk(child); }
      };
      walk(node);
      return out;
    }
    return rawQuerySelectorAll(selector);
  };
  node.querySelector = (selector: string) => node.querySelectorAll(selector)[0] ?? null;
  return node;
}

/** 剥掉注释（源码级静态判据必须先剥注释，否则注释里的示例串会被误判）。 */
function stripSourceComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
}

/** 子树节点数（含自身）；不依赖选择器语义 ⇒ 判「不增删节点」时不受 stub 的 selector 能力限制。 */
function descendantCount(node: StubElement): number {
  return 1 + node.children.reduce((sum, child) => sum + descendantCount(child), 0);
}

function createStubHud(): StubElement {
  const body = stubElement('body');
  const hud = stubElement('div');
  hud.id = 'hud';
  const appendTo = (parent: StubElement, tag: string, id: string, text?: string) => {
    const el = stubElement(tag);
    el.id = id;
    if (text !== undefined) el.textContent = text;
    parent.append(el);
    return el;
  };
  const head = stubElement('div');
  head.id = 'hud-head';
  hud.append(head);
  appendTo(head, 'div', 'mode-badge', 'observe');
  appendTo(head, 'div', 'reading-badge', 'surface');
  const collapse = appendTo(head, 'button', 'observe-collapse-toggle', '折叠');
  collapse.type = 'button';
  appendTo(hud, 'div', 'observe-targets');
  appendTo(hud, 'div', 'tick', 'tick 0');
  appendTo(hud, 'div', 'causal-trace', 'causal trace: waiting for events');
  const controls = stubElement('div');
  controls.id = 'controls';
  for (const [id, text] of [['toggle-reading', '切换读法'], ['toggle-mode', '切换模式']] as const) {
    const button = stubElement('button');
    button.id = id;
    button.type = 'button';
    button.textContent = text;
    controls.append(button);
  }
  hud.append(controls);
  body.append(hud);
  (globalThis as { __stubBody?: StubElement }).__stubBody = body;
  return hud;
}

/** 在受控的 `globalThis.document` 下跑一段（结束后还原，避免泄漏到其它用例）。 */
function withStubDom<T>(run: (hud: StubElement) => T): T {
  const globals = globalThis as { document?: unknown };
  const previous = globals.document;
  const body = stubElement('body');
  const documentStub = {
    createElement: (tag: string) => stubElement(tag),
    getElementById: (id: string) => body.querySelector(`#${id}`),
    querySelector: (selector: string) => body.querySelector(selector),
    querySelectorAll: (selector: string) => body.querySelectorAll(selector),
    documentElement: stubElement('html'),
    body,
    // r2（MUST-3）：`document.designMode`（默认 `'off'`；用例显式置 `'on'`）
    designMode: 'off',
  };
  globals.document = documentStub;
  (documentStub.documentElement as StubElement).append(body);
  try {
    return run(createStubHud());
  } finally {
    if (previous === undefined) delete globals.document; else globals.document = previous;
  }
}

test('req20261012_t1_collapse_switches_class_and_dataset_without_touching_nodes', () => {
  withStubDom((hud) => {
    const panel = new ObservePanel(hud as never);
    const before = descendantCount(hud);
    assert.equal(panel.isCollapsed(), false, '默认必须是**展开**（与现状一致）');
    assert.equal(hud.dataset.collapsed, 'false');
    assert.equal(hud.querySelector('#observe-collapse-toggle')?.textContent, '折叠');

    panel.setCollapsed(true);
    assert.equal(panel.isCollapsed(), true);
    assert.equal(hud.classList.contains('collapsed'), true, '折叠态必须落 `#hud.collapsed`（CSS 钩子）');
    assert.equal(hud.dataset.collapsed, 'true');
    assert.equal(hud.querySelector('#observe-collapse-toggle')?.textContent, '展开');

    // 可反复：再展开一次必须逐项复原
    panel.setCollapsed(false);
    assert.equal(hud.classList.contains('collapsed'), false);
    assert.equal(hud.dataset.collapsed, 'false');
    assert.equal(panel.isCollapsed(), false);

    // **不增删节点**（`#tick` / `#causal-trace` 等被 `adopt()` 按 id 复用，移除会打断取数路径）
    assert.equal(descendantCount(hud), before, '折叠/展开不得增删任何节点');
    assert.ok(hud.querySelector('#tick') !== null && hud.querySelector('#causal-trace') !== null);
    assert.ok(hud.querySelector('#observe-targets') !== null && hud.querySelector('#hud-head') !== null);
  });
});

test('req20261012_t2_object_list_is_derived_deduped_and_registered_by_reference', () => {
  // 派生规则：overview 恒在首位 → npcIds() 升序 → anomalies[].at_entity 按 worldview 顺序，保序去重。
  const options = observeOptionsFor(
    { anomalies: [{ at_entity: 'entity-beta' }, { at_entity: 'entity-alpha' }, { at_entity: 'entity-beta' }] },
    ['npc-zulu', 'npc-alpha', 'npc-alpha'],
  );
  assert.deepEqual(options, [
    { kind: 'overview', target: 'overview', label: '总览' },
    { kind: 'npc', target: 'npc-alpha', label: 'npc-alpha' },
    { kind: 'npc', target: 'npc-zulu', label: 'npc-zulu' },
    { kind: 'entity', target: 'entity-beta', label: 'entity-beta' },
    { kind: 'entity', target: 'entity-alpha', label: 'entity-alpha' },
  ], '清单必须运行时派生 + 保序去重');

  // **非硬编码**的牙齿：换一组完全不同的输入 ⇒ 必须给出完全不同的清单
  const other = observeOptionsFor({ anomalies: [{ at_entity: 'room-x' }] }, ['npc-b', 'npc-a']);
  assert.deepEqual(other.map((option) => option.target), ['overview', 'npc-a', 'npc-b', 'room-x']);
  assert.deepEqual(observeOptionsFor({}, []).map((option) => option.target), ['overview'],
    '无 NPC / 无异常时只剩总览（不得补造）');
  assert.deepEqual(observeOptionsFor({ anomalies: [{ at_entity: '' }, {}] }, []).map((option) => option.target),
    ['overview'], '空 / 缺失 at_entity 必须跳过');

  withStubDom((hud) => {
    const picked: Array<{ kind: string; target: string }> = [];
    const panel = new ObservePanel(hud as never, { onSelect: (next) => picked.push({ kind: next.kind, target: next.target }) });
    panel.renderTargets(options, { kind: 'overview', target: 'overview' });

    const buttons = hud.querySelector('#observe-targets')!.querySelectorAll('button');
    assert.equal(buttons.length, options.length, '每个对象一个只读视图控件');
    assert.deepEqual(buttons.map((button) => button.id),
      ['observe-target-overview', 'observe-target-npc-alpha', 'observe-target-npc-zulu',
        'observe-target-entity-beta', 'observe-target-entity-alpha']);
    for (const button of buttons) {
      assert.equal(button.type, 'button');
      assert.equal(button.dataset.viewControl, 'read-only');
      assert.equal(button.getAttribute('aria-pressed'), String(button.dataset.target === 'overview'));
    }
    assert.equal(buttons[1]?.textContent, 'npc-alpha', '渲染必须走 textContent');

    // M-10：签名不变 ⇒ **不重建**（节点对象同一性可判）
    panel.renderTargets(options, { kind: 'overview', target: 'overview' });
    assert.equal(hud.querySelector('#observe-targets')!.querySelectorAll('button')[1], buttons[1],
      '派生清单签名未变时不得重建（重建会丢焦点）');

    // 点击 ⇒ 回调带出所选对象
    buttons[3]?.click();
    assert.deepEqual(picked, [{ kind: 'entity', target: 'entity-beta' }]);

    // 清单变化 ⇒ 重建，且只清理**上一次由本 panel 创建**的引用
    panel.renderTargets([{ kind: 'overview', target: 'overview', label: '总览' }], { kind: 'overview', target: 'overview' });
    assert.equal(hud.querySelector('#observe-targets')!.querySelectorAll('button').length, 1);

    // 静态口径：渲染不得用 innerHTML（**先剥注释**，否则注释里提到 innerHTML 会误判）
    const stripComments = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
    const panelSource = stripComments(readFileSync(join(WEB, 'src/ui/observe/panel.ts'), 'utf8'));
    assert.equal(/\.innerHTML|innerHTML\s*=/.test(panelSource), false, 'panel.ts 不得用 innerHTML 渲染');
    assert.equal(panel.listWriteControls().length, 0, '面板自己渲染的控件必须登记为只读视图控件');
  });
});

test('req20261012_write_control_registry_rejects_duplicated_ids_and_contenteditable_variants', () => {
  withStubDom((hud) => {
    const panel = new ObservePanel(hud as never);
    panel.renderTargets(observeOptionsFor({ anomalies: [{ at_entity: 'room-probe-01' }] }, []),
      { kind: 'overview', target: 'overview' });
    assert.deepEqual(panel.listWriteControls(), [], '基线：面板自身（含折叠按钮与对象按钮）零写控件');

    const probe = (tag: string, id: string | null, attrs: Record<string, string> = {}) => {
      const el = stubElement(tag);
      if (id !== null) el.id = id;
      for (const [name, value] of Object.entries(attrs)) el.setAttribute(name, value);
      hud.append(el);
      return el;
    };
    const check = (label: string, el: StubElement, expected: string) => {
      const hits = panel.listWriteControls();
      assert.ok(hits.includes(expected), `${label}：必须命中（实测 ${JSON.stringify(hits)}）`);
      el.remove();
      assert.deepEqual(panel.listWriteControls(), [], `${label}：移除后必须复原为空`);
    };

    // T1：全新 id 的 button（证明判据**有牙**，不是恒空）
    check('T1 全新 id button', probe('button', 'brand-new-write-control'), 'button#brand-new-write-control');
    // T3（预审 M-3 实证逃逸）：复制一个**白名单 id** 的第二个 button —— 按 id 字符串放行会逃逸
    check('T3 复制白名单 id', probe('button', 'toggle-mode'), 'button#toggle-mode');
    // T3b：复制**面板自己创建**的对象按钮 id
    check('T3b 复制对象按钮 id', probe('button', 'observe-target-room-probe-01'), 'button#observe-target-room-probe-01');
    // T4 / T5（预审 M-11 实证逃逸）：`[contenteditable=true]` 会漏判这两个值
    check('T4 contenteditable=""', probe('div', null, { contenteditable: '' }), '[contenteditable]');
    check('T5 contenteditable="plaintext-only"', probe('div', null, { contenteditable: 'plaintext-only' }), '[contenteditable]');
    // T7：既有形态
    check('T7 input[type=text]', probe('input', null, { type: 'text' }), 'input');

    // T6：作用域 —— `#hud` **之外**的控件不在本判据作用域内（L-5 边界声明，不是"通过"）
    const outside = stubElement('input');
    outside.setAttribute('type', 'text');
    (globalThis as { __stubBody?: StubElement }).__stubBody?.append(outside);
    assert.deepEqual(panel.listWriteControls(), [], '作用域 = #hud：面板子树的声明面不得因树外控件而变');
    outside.remove();

    // 加严后的放行判据必须是**元素引用**，不是 id 字符串（源码级读出）
    const panelSource = stripSourceComments(readFileSync(join(WEB, 'src/ui/observe/panel.ts'), 'utf8')).replace(/\s+/g, ' ');
    assert.ok(/viewControlRefs = new Set<Element>\(\)/.test(panelSource),
      '允许集合必须是 Set<Element>（按元素引用，不按 id 字符串）');
    assert.ok(panelSource.includes('[contenteditable]'), 'WRITE_CONTROL_SELECTORS 必须含 [contenteditable]');
    assert.equal(panelSource.includes('[contenteditable=true]'), false,
      '不得回退成 [contenteditable=true]（会漏判 contenteditable=""）');
  });
});

test('req20261012_anomaly_reads_filter_only_when_a_filter_is_passed', () => {
  withStubDom((hud) => {
    const panel = new ObservePanel(hud as never);
    const el = hud.querySelector('#anomaly-read')!;
    const worldview = {
      anomalies: [
        { id: 'anom-a', at_entity: 'entity-alpha', surface_read: 's-a', underneath_read: 'u-a', reveal_at_tick: 5 },
        { id: 'anom-b', at_entity: 'entity-beta', surface_read: 's-b', underneath_read: 'u-b', reveal_at_tick: 5 },
      ],
    };
    // 不传 filter ⇒ 与今天**逐字相同**（两行、同一格式；既有调用点零改动）
    panel.renderAnomalyReads(worldview, 10, 'surface');
    assert.equal(String(el.textContent),
      'anom-a@entity-alpha surface t=10 revealed=true: s-a\nanom-b@entity-beta surface t=10 revealed=true: s-b');
    assert.equal(el.dataset.reading, 'surface');
    assert.equal(el.dataset.tick, '10');
    assert.equal(el.dataset.entityFilter, '', '不过滤是**显式读数**（空串），不是被省略');

    // 传 filter ⇒ 只渲该实体那一条
    panel.renderAnomalyReads(worldview, 10, 'underneath', { entity: 'entity-beta' });
    assert.equal(String(el.textContent), 'anom-b@entity-beta underneath t=10 revealed=true: u-b');
    assert.equal(el.dataset.entityFilter, 'entity-beta');

    // 未 reveal 的实体照样只给 surface（既有两态语义不受过滤影响）
    panel.renderAnomalyReads(worldview, 4, 'underneath', { entity: 'entity-alpha' });
    assert.equal(String(el.textContent), 'anom-a@entity-alpha surface t=4 revealed=false: s-a');

    // 切回不过滤 ⇒ 复原两行
    panel.renderAnomalyReads(worldview, 10, 'surface');
    assert.equal(String(el.textContent).split('\n').length, 2);
  });
});

test('req20261012_event_stream_entity_filter_has_explicit_empty_states', () => {
  withStubDom((hud) => {
    const panel = new ObservePanel(hud as never);
    const stream = hud.querySelector('#event-stream')!;
    const events = [
      { seq: 1, tick: 10, type: 'npc.action', actor: 'npc-probe-1', payload: { action: 'move', target_entity: 'room-probe-01' } },
      { seq: 2, tick: 11, type: 'npc.action', actor: 'npc-probe-1', payload: { action: 'rest', target_entity: null } },
      { seq: 3, tick: 12, type: 'world.init', actor: 'world', payload: { pack_id: 'probe-pack' } },
    ];
    // 字段依据（events.schema.json）：顶层 actor + payload.target_entity（房间/物件只可能出现在后者）
    assert.equal(eventMatchesEntity(events[0] as never, 'room-probe-01'), true);
    assert.equal(eventMatchesEntity(events[1] as never, 'npc-probe-1'), true);
    assert.equal(eventMatchesEntity(events[2] as never, 'room-probe-01'), false);

    // 空缓冲 + 实体过滤 ⇒ **显式**空态（不得让"没有事件"与"没有匹配"混为一谈）
    panel.setEventFilter({ entity: 'room-probe-01' });
    const empty = stream.querySelectorAll('li');
    assert.equal(empty.length, 1);
    assert.equal(empty[0]?.dataset.emptyState, 'empty');
    // r3 / SHOULD-7：可见文本**中性**（不得对用户断言因果）+ 原因改由机器可读字段承载
    assert.equal(empty[0]?.textContent, '暂无事件');
    assert.equal(stream.dataset.emptyReason, 'no-event-records-received');

    panel.renderEventStream(events as never);
    const matched = stream.querySelectorAll('li');
    assert.equal(matched.length, 1, '只保留匹配该实体的事件（不伪造、不补造）');
    assert.equal(matched[0]?.textContent, 't10 npc.action');
    assert.equal(stream.dataset.filterEntity, 'room-probe-01');

    // 目标实体已消失 ⇒ 语义不同的**另一个**空态
    panel.setEventFilter({ entity: 'room-probe-99' });
    const noMatch = stream.querySelectorAll('li');
    assert.equal(noMatch.length, 1);
    assert.equal(noMatch[0]?.dataset.emptyState, 'no-match-for-entity');
    assert.ok(noMatch[0]?.textContent?.includes('room-probe-99'));
    assert.equal(stream.dataset.emptyReason, 'no-event-matches-entity-filter');

    // 清掉过滤 ⇒ 三条全回来（append 路径与重建路径必须同结果）
    panel.setEventFilter(null);
    assert.equal(stream.querySelectorAll('li').length, 3);
    assert.equal(panel.eventStreamFilter().entity, null);
    assert.equal(panel.eventsSeen, 3);
  });
});

test('req20261012_trace_entity_scope_is_an_explicit_empty_state', () => {
  withStubDom((hud) => {
    const trace = new CausalTrace(hud as never);
    const el = hud.querySelector('#causal-trace')!;
    trace.renderEntityScope('room-probe-01');
    assert.equal(el.dataset.scope, 'entity');
    assert.equal(el.dataset.entity, 'room-probe-01');
    assert.equal(el.dataset.npcId, '', '实体态不得残留 npcId');
    assert.ok(el.textContent?.includes('无 NPC 链'), '必须如实标注"该实体无 NPC 链"');

    // 切回人物链 ⇒ scope 与 entity 必须同步（不留误导性残留）
    trace.render('npc-probe-1');
    assert.equal(el.dataset.scope, 'npc');
    assert.equal(el.dataset.npcId, 'npc-probe-1');
    assert.equal(el.dataset.entity, undefined);

    trace.render(null);
    assert.equal(el.dataset.scope, 'none');
  });
});

test('req20261012_restore_decisions_are_distinguishable', () => {
  const options = observeOptionsFor({ anomalies: [{ at_entity: 'room-probe-01' }] }, ['npc-probe-alpha']);
  // 命中
  assert.deepEqual(restoreDecisionOf({ collapsed: true, kind: 'entity', target: 'room-probe-01' }, options, true),
    { reason: 'ok', selection: { kind: 'entity', target: 'room-probe-01' } });
  // 目标已消失（该 kind 的候选面**非空**）
  assert.deepEqual(restoreDecisionOf({ collapsed: true, kind: 'entity', target: 'room-probe-99' }, options, true),
    { reason: 'fallback:target-not-in-options', selection: { kind: 'overview', target: 'overview' } });
  // 抢跑：启动那一刻该 kind 的候选面**为空**（NPC 事件还没到）
  assert.deepEqual(restoreDecisionOf({ collapsed: false, kind: 'npc', target: 'npc-probe-alpha' },
    observeOptionsFor({ anomalies: [] }, []), true),
  { reason: 'fallback:empty-options-at-boot', selection: { kind: 'overview', target: 'overview' } });
  // 没有记录 / 存储不可用
  assert.equal(restoreDecisionOf(null, options, true).reason, 'none');
  assert.equal(restoreDecisionOf(null, options, false).reason, 'unavailable');
  assert.equal(restoreDecisionOf(null, options, false).selection.target, 'overview');
});

test('req20261012_persisted_view_roundtrip_and_damaged_storage_never_throws', () => {
  const globals = globalThis as { sessionStorage?: unknown };
  const previous = globals.sessionStorage;
  const store = new Map<string, string>();
  try {
    globals.sessionStorage = {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, value); },
    };
    assert.equal(readPersistedView().view, null, '空存储 ⇒ 没有可恢复的视图');
    assert.equal(readPersistedView().persisted, true);
    assert.equal(writePersistedView({ collapsed: true, kind: 'entity', target: 'room-probe-01' }), true);
    assert.deepEqual(readPersistedView(), {
      view: { collapsed: true, kind: 'entity', target: 'room-probe-01' }, persisted: true,
    });

    // 损坏 / 非 JSON / 字段类型不符 ⇒ 「无视图」且**不抛**
    const key = [...store.keys()][0] as string;
    store.set(key, '{not json');
    assert.deepEqual(readPersistedView(), { view: null, persisted: true });
    store.set(key, JSON.stringify({ collapsed: 'yes', kind: 'entity', target: 'room-probe-01' }));
    assert.deepEqual(readPersistedView(), { view: null, persisted: true });
    store.set(key, JSON.stringify({ collapsed: true, kind: 'bogus-kind', target: 'room-probe-01' }));
    assert.deepEqual(readPersistedView(), { view: null, persisted: true });
    store.set(key, 'x'.repeat(200000));
    assert.deepEqual(readPersistedView(), { view: null, persisted: true });

    // 存储抛错 ⇒ persisted:false（**不得抛**）
    globals.sessionStorage = {
      getItem() { throw new Error('blocked'); },
      setItem() { throw new Error('blocked'); },
    };
    assert.deepEqual(readPersistedView(), { view: null, persisted: false });
    assert.equal(writePersistedView({ collapsed: false, kind: 'overview', target: 'overview' }), false);

    // 完全没有 sessionStorage（Node / 隐私模式）⇒ persisted:false
    delete globals.sessionStorage;
    assert.deepEqual(readPersistedView(), { view: null, persisted: false });
    assert.equal(writePersistedView({ collapsed: false, kind: 'overview', target: 'overview' }), false);
  } finally {
    if (previous === undefined) delete globals.sessionStorage; else globals.sessionStorage = previous;
  }
});

test('req20261012_ac4_positive_control_registered_glb_still_yields_aabb_source', () => {
  // 设计 §9.2 的**正对照**：证明「全为 source:'none'」不是**结构恒真**——
  // 构造合成 npc-006 + 在册真 GLB 绑定 ⇒ `setAutoObservationFocus(true)` 后必须出现 `source:'aabb'`。
  const fixture = bindingFixture();
  const probe = newProbe();
  try {
    fixture.set(0, { entity_ids: ['npc-006'], glb_url: 'assets/character/xuqin-body.glb' });
    const binding = BINDINGS[0];
    assert.ok(binding && binding.glb_url.endsWith('.glb'), '夹具必须落在真 GLB 绑定上');
    assert.ok(ASSET_ENTRIES.some((entry) => entry.binding_ref === `binding:${binding.binding_id}`),
      '该绑定必须在交付登记面在册');

    snap(probe, [npcEntity('npc-006', 0)], 0);
    probe.setCharacterLoader(syncLoader(knownBodyScene()));
    assert.equal(probe.characterInstanceReport()[0]?.glb_loaded, true, '假 loader 必须同步回填 GLB');

    assert.equal(probe.setAutoObservationFocus(true).enabled, true);
    const on = probe.focusViewReport();
    assert.ok(on.length > 0, `正对照：在册真 GLB 候选 ⇒ 读数必须非空，实测 ${JSON.stringify(on)}`);
    assert.ok(on.some((row) => row.source === 'aabb'),
      `正对照：必须出现 source:'aabb'（不得结构性恒 none），实测 ${JSON.stringify(on)}`);

    // AC-4③ 的「非空真」依据：**关闭态**下每个候选仍各有一条记录（reason:'disabled'）
    // ⇒ `focus_report_length === 0` 真的推出「无在册真 GLB 候选」，与"按选择不施加"可区分。
    probe.setAutoObservationFocus(false);
    const off = probe.focusViewReport();
    assert.ok(off.length > 0, '关闭态下候选仍逐条记录 ⇒ length 是候选数的忠实读数');
    assert.ok(off.every((row) => row.source === 'none' && row.reason === 'disabled'),
      '关闭态必须全 source:none + reason:disabled');
  } finally {
    fixture.restore();
  }
  assert.equal(bindingForEntity('npc-006')?.glb_url, 'assets/character/xuqin-body.glb', '夹具必须完全还原');
});

// ═════════════════════════════════════════════════════════════════════════════
// r2 修复轮新增判据（MUST-1 / MUST-2 / MUST-3 / MUST-4）
//
// 追加式：本段只**新增**用例与 helper，不改写 r1 已落下的任何一行（`git diff --unified=0`
// 的 `^-` 行数必须为 0）。三条 MUST 的关闭判据都要求 RED（改前）与 GREEN（改后）两份真跑读数；
// 本文件里的断言对应 GREEN，RED 读数在 `<ws>/evidence/artisan/r2/`。
// ═════════════════════════════════════════════════════════════════════════════

test('req20261012_r2_camera_source_keeps_three_states_and_never_masks_unreadable', () => {
  // ── MUST-4 ①：有候选 + autofocus 关 ⇒ reason='selection-suppressed-autofocus' 且 camera_source='none'
  const fixture = bindingFixture();
  const probe = newProbe();
  let offTriple;
  try {
    fixture.set(0, { entity_ids: ['npc-006'], glb_url: 'assets/character/xuqin-body.glb' });
    snap(probe, [npcEntity('npc-006', 0)], 0);
    probe.setCharacterLoader(syncLoader(knownBodyScene()));
    const off = { autofocus: probe.setAutoObservationFocus(false).enabled, rows: readFocusRows(probe) };
    assert.ok((off.rows?.length ?? 0) > 0,
      `有候选 ⇒ 读数必须非空（否则本用例退化成空真），实测 ${JSON.stringify(off.rows)}`);
    offTriple = {
      autofocus_enabled: off.autofocus,
      camera_source: cameraSourceOf(off.rows),
      focus_reason: focusReasonOf(off.rows, off.autofocus),
    };
    assert.deepEqual(offTriple,
      { autofocus_enabled: false, camera_source: 'none', focus_reason: 'selection-suppressed-autofocus' },
      'AC-4 的「按选择不施加」必须与「本来没候选」用**不同** reason 区分');

    // 对照臂：同一候选、autofocus 开 ⇒ 真的按 AABB 施加（证明上一条不是恒真）
    const on = { autofocus: probe.setAutoObservationFocus(true).enabled, rows: readFocusRows(probe) };
    assert.deepEqual(
      { autofocus_enabled: on.autofocus, camera_source: cameraSourceOf(on.rows), focus_reason: focusReasonOf(on.rows, on.autofocus) },
      { autofocus_enabled: true, camera_source: 'aabb', focus_reason: 'autofocus-evaluated' });
  } finally {
    fixture.restore();
  }

  // ── MUST-4 ②：无候选 + autofocus 开 ⇒ reason='no-registered-real-glb-candidate'
  const bare = newProbe();
  snap(bare, [npcEntity('npc-001', 0)], 0); // `npc-001` 无在册真 GLB 绑定 ⇒ 候选面为空
  const bareOn = { autofocus: bare.setAutoObservationFocus(true).enabled, rows: readFocusRows(bare) };
  assert.equal(bareOn.rows?.length, 0, '无候选 ⇒ 读到了空数组（不是读不到）');
  assert.equal(focusReasonOf(bareOn.rows, bareOn.autofocus), 'no-registered-real-glb-candidate');
  assert.equal(cameraSourceOf(bareOn.rows), 'none', '读到了空 ⇒ 「确实没有相机源」');
  assert.notEqual(focusReasonOf(bareOn.rows, bareOn.autofocus), offTriple.focus_reason,
    '两个 reason 必须是**两个不同的值**（设计 §9.2）');

  // ── MUST-4 ③ / MUST-1：读不到 ⇒ camera_source='unknown'（与「确实是 none」不同）
  const broken = newProbe();
  const patchReader = (value: unknown) => {
    (broken as unknown as { focusViewReport: unknown }).focusViewReport = value;
  };
  patchReader(() => { throw new Error('probe: unreadable'); });
  const unreadable = readFocusRows(broken);
  assert.equal(unreadable, null, '抛错必须读成「读不到」而不是「空」');
  assert.equal(cameraSourceOf(unreadable), 'unknown', 'MUST-1：读不到不得折叠成 none');
  assert.notEqual(cameraSourceOf(unreadable), 'none');
  assert.equal(focusReasonOf(unreadable, true), 'unreadable');
  assert.equal(focusSourcesOf(unreadable), null, '三态：读不到必须给 null（不是 []）');
  assert.equal(focusReasonsOf(unreadable), null, '三态：读不到必须给 null（不是 []）');
  patchReader(() => ({ not: 'an array' }));
  assert.equal(cameraSourceOf(readFocusRows(broken)), 'unknown', '返回非数组同样属「读不到」');
  patchReader(undefined);
  assert.equal(cameraSourceOf(readFocusRows(broken)), 'unknown', '缺方法同样属「读不到」');
  assert.equal(cameraSourceOf(readFocusRows(null)), 'unknown', '读者缺失同样属「读不到」');
  // 三态互不相同（不得把 null 与 [] 折成同一个输出）
  assert.notEqual(cameraSourceOf(null), cameraSourceOf([]));
  assert.notEqual(focusReasonOf(null, true), focusReasonOf([], true));
  // 读到非 `aabb|none` 的取值 ⇒ 也判 'unknown'（不猜）
  assert.equal(cameraSourceOf([{ entity_id: 'probe', applied: false, source: 'weird' } as never]), 'unknown');
  // 正对照：读到了 aabb ⇒ 'aabb'（证明 'unknown' 不是唯一可能值）
  assert.equal(cameraSourceOf([{ entity_id: 'probe', applied: true, source: 'aabb' } as never]), 'aabb');
});

test('req20261012_r2_cross_kind_targets_are_listed_not_silently_dropped', () => {
  // ── MUST-2 夹具 A：`at_entity` 与某个 NPC id 同名 ⇒ 实体选项必须仍在（不得静默消失）
  const sameName = observeOptionsFor({ anomalies: [{ at_entity: 'npc-probe-alpha' }] }, ['npc-probe-alpha']);
  assert.deepEqual(sameName.map((option) => `${option.kind}:${option.target}`),
    ['overview:overview', 'npc:npc-probe-alpha', 'entity:npc-probe-alpha'],
    '跨 kind 同 target 必须**都**列出（去重键 = (kind,target) 二元组）');
  assert.deepEqual(optionTargetCollisions(sameName), ['npc-probe-alpha'], '撞名必须**显式披露**（不静默）');

  // ── MUST-2 夹具 B：`at_entity === 'overview'` ⇒ 实体选项必须仍在，且总览仍在
  const asOverview = observeOptionsFor({ anomalies: [{ at_entity: 'overview' }] }, []);
  assert.deepEqual(asOverview.map((option) => `${option.kind}:${option.target}`), ['overview:overview', 'entity:overview']);
  assert.deepEqual(optionTargetCollisions(asOverview), ['overview']);

  // 回归：同 kind 内的重复仍保序去重（不得因修跨 kind 而退化）
  assert.deepEqual(
    observeOptionsFor({ anomalies: [{ at_entity: 'room-x' }, { at_entity: 'room-x' }] }, ['npc-a', 'npc-a'])
      .map((option) => `${option.kind}:${option.target}`),
    ['overview:overview', 'npc:npc-a', 'entity:room-x']);
  assert.deepEqual(optionTargetCollisions(observeOptionsFor({ anomalies: [{ at_entity: 'room-x' }] }, ['npc-a'])), []);

  // ── 真 DOM：跨 kind 同名 ⇒ id 必须**唯一**且两个都可点，点击后选中正确的 kind
  withStubDom((hud) => {
    const picked: Array<{ kind: string; target: string }> = [];
    const panel = new ObservePanel(hud as never, { onSelect: (next) => picked.push({ kind: next.kind, target: next.target }) });
    panel.renderTargets(sameName, { kind: 'overview', target: 'overview' });
    const buttons = hud.querySelector('#observe-targets')!.querySelectorAll('button');
    const ids = buttons.map((button) => button.id);
    assert.equal(new Set(ids).size, ids.length, `同 id 多按钮必须消除，实测 ${JSON.stringify(ids)}`);
    // 无冲突者沿用 r1 既有 id；撞名者对**后出现**的那个改用带 kind 的限定名消歧
    assert.deepEqual(ids, ['observe-target-overview', 'observe-target-npc-probe-alpha', 'observe-target-entity-npc-probe-alpha']);
    const entityButton = buttons.find((button) => button.dataset.kind === 'entity');
    const npcButton = buttons.find((button) => button.dataset.kind === 'npc');
    assert.ok(entityButton && npcButton, '同名 NPC 与实体都必须有按钮');
    entityButton.click();
    assert.deepEqual(picked, [{ kind: 'entity', target: 'npc-probe-alpha' }], '点实体按钮必须选中 entity（不得串到 npc）');
    npcButton.click();
    assert.deepEqual(picked, [{ kind: 'entity', target: 'npc-probe-alpha' }, { kind: 'npc', target: 'npc-probe-alpha' }]);
    assert.deepEqual(panel.listWriteControls(), [], '新增的按钮仍必须登记为只读视图控件');
  });

  // ── SHOULD-6 / R-4：slug 非单射（`room-101` vs `room.101`）⇒ id 必须仍唯一
  withStubDom((hud) => {
    const panel = new ObservePanel(hud as never);
    panel.renderTargets([
      { kind: 'overview', target: 'overview', label: '总览' },
      { kind: 'entity', target: 'room-101', label: 'room-101' },
      { kind: 'entity', target: 'room.101', label: 'room.101' },
    ], { kind: 'overview', target: 'overview' });
    const ids = hud.querySelector('#observe-targets')!.querySelectorAll('button').map((button) => button.id);
    assert.deepEqual(ids,
      ['observe-target-overview', 'observe-target-room-101', 'observe-target-entity-room-101'],
      '同 kind slug 撞名必须消歧，且 id 里带 kind 可自辨');
    assert.equal(new Set(ids).size, ids.length);
    // `targetButtonId` 是这条规则的唯一实现点（避免"测试替实现"）
    assert.equal(targetButtonId({ kind: 'entity', target: 'room-101', label: '' },
      new Set<string>(['observe-target-room-101'])), 'observe-target-entity-room-101');
    assert.equal(targetButtonId({ kind: 'npc', target: 'room-101', label: '' },
      new Set<string>(['observe-target-room-101', 'observe-target-entity-room-101'])),
    'observe-target-npc-room-101');
    assert.equal(targetButtonId({ kind: 'npc', target: 'room-101', label: '' },
      new Set<string>(['observe-target-room-101', 'observe-target-npc-room-101'])), 'observe-target-npc-room-101-2');
    assert.equal(targetButtonId({ kind: 'overview', target: 'overview', label: '总览' }, new Set<string>()),
      'observe-target-overview');
  });
});

test('req20261012_r2_scan_covers_shadow_root_iframe_and_design_mode_without_false_positives', () => {
  withStubDom((hud) => {
    const panel = new ObservePanel(hud as never);
    assert.deepEqual(panel.listWriteControls(), [], '基线仍必须为空（面板自身零写控件）');

    // ── ① 开放 shadow root（挂在 `#hud` 内）：Raven B5
    const host = stubElement('div');
    host.id = 'r2-shadow-host';
    hud.append(host);
    const shadow = host.attachShadow({ mode: 'open' });
    const shadowButton = stubElement('button');
    shadowButton.id = 'r2-shadow-write';
    shadowButton.type = 'button';
    shadow.append(shadowButton);
    assert.ok(panel.listWriteControls().some((hit) => hit.includes('r2-shadow-write')),
      `开放 shadow root 内的 button 必须命中，实测 ${JSON.stringify(panel.listWriteControls())}`);
    shadowButton.remove();
    assert.deepEqual(panel.listWriteControls(), [], '清理后必须复原为空');
    // 负对照：shadow 内只有普通 div ⇒ 不得命中（不得为了变红而误判）
    const plainInShadow = stubElement('div');
    plainInShadow.textContent = 'not a write control';
    shadow.append(plainInShadow);
    assert.deepEqual(panel.listWriteControls(), [], 'shadow 内普通节点不得被判红');
    host.remove();

    // ── ② 同源 iframe（`contentDocument` 内 form + input）：Raven B6
    const frame = stubElement('iframe');
    frame.id = 'r2-frame';
    hud.append(frame);
    const subDocument = stubElement('#document');
    const subBody = stubElement('body');
    subDocument.append(subBody);
    frame.contentDocument = subDocument;
    const subInput = stubElement('input');
    subInput.setAttribute('type', 'text');
    subBody.append(subInput);
    const iframeHits = panel.listWriteControls();
    assert.ok(iframeHits.includes('input'), `同源 iframe 内的 input 必须命中，实测 ${JSON.stringify(iframeHits)}`);
    subInput.remove();
    assert.equal(panel.listWriteControls().includes('input'), false, '清理后不得残留');
    // 负对照：iframe 内只有普通 div ⇒ 不得命中
    const plainInFrame = stubElement('div');
    plainInFrame.textContent = 'x';
    subBody.append(plainInFrame);
    assert.deepEqual(panel.listWriteControls(), [], 'iframe 内普通节点不得被判红');
    frame.remove();

    // ── ③ `document.designMode = 'on'`（整页可编辑、零 `contenteditable` 属性）：Raven B7
    (globalThis.document as unknown as { designMode?: string }).designMode = 'on';
    const designHits = panel.listWriteControls();
    assert.ok(designHits.includes('document:designMode=on'),
      `designMode='on' 必须判红并给出显式原因，实测 ${JSON.stringify(designHits)}`);
    (globalThis.document as unknown as { designMode?: string }).designMode = 'off';
    assert.deepEqual(panel.listWriteControls(), [], "designMode 复位后必须回到空");

    // ── 负对照：普通 div 不得命中（判据只加枚举深度，不放宽放行）
    const plain = stubElement('div');
    plain.id = 'r2-plain';
    plain.textContent = 'x';
    hud.append(plain);
    assert.deepEqual(panel.listWriteControls(), [], '普通 div 不得命中');
    plain.remove();

    // ── r1 已关闭项回归（M-3 / M-11 判据不得退化）
    const duplicate = stubElement('button');
    duplicate.id = 'toggle-mode';
    duplicate.type = 'button';
    hud.append(duplicate);
    assert.ok(panel.listWriteControls().includes('button#toggle-mode'), 'M-3：复制白名单 id 仍必须命中');
    duplicate.remove();
    const editable = stubElement('div');
    editable.setAttribute('contenteditable', '');
    hud.append(editable);
    assert.ok(panel.listWriteControls().includes('[contenteditable]'), 'M-11：contenteditable="" 仍必须命中');
    editable.remove();
    assert.deepEqual(panel.listWriteControls(), [], '全部清理后必须复原为空');
  });
});

// ═════════════════════════════════════════════════════════════════════════════
// r3 收口轮新增判据（R3-1 / R3-2）
//
// 追加式：只**新增**用例；对 r1 段落的那一处改写见 `03` 的 r3 节「被改写的断言」清单。
// ═════════════════════════════════════════════════════════════════════════════

test('req20261012_r3_scope_root_own_shadow_root_is_scanned', () => {
  withStubDom((hud) => {
    const panel = new ObservePanel(hud as never);
    assert.deepEqual(panel.listWriteControls(), [], '基线仍必须为空');

    // 作用域根 `#hud` **自身**挂 open shadow root（Raven R2-1 / §16.4.3-N1 的形态）
    const shadow = hud.attachShadow({ mode: 'open' });
    assert.notEqual(hud.shadowRoot, null, 'shadow root 必须可读（open）');

    // ① shadow 内 button ⇒ 必须命中
    const button = stubElement('button');
    button.id = 'r3-root-shadow-button';
    button.type = 'button';
    shadow.append(button);
    assert.ok(panel.listWriteControls().some((hit) => hit.includes('r3-root-shadow-button')),
      `作用域根自身 shadow root 内的 button 必须命中，实测 ${JSON.stringify(panel.listWriteControls())}`);
    button.remove();
    assert.deepEqual(panel.listWriteControls(), [], '清理后必须复原为空');

    // ② shadow 内 input / contenteditable ⇒ 同样命中
    const input = stubElement('input');
    input.setAttribute('type', 'text');
    shadow.append(input);
    assert.ok(panel.listWriteControls().includes('input'), 'root shadow 内的 input 必须命中');
    input.remove();
    const editable = stubElement('div');
    editable.setAttribute('contenteditable', '');
    shadow.append(editable);
    assert.ok(panel.listWriteControls().includes('[contenteditable]'), 'root shadow 内的 contenteditable 必须命中');
    editable.remove();

    // ③ 负对照 A：shadow 内只有普通 div ⇒ 不得命中（不得为了变红而误判）
    const plain = stubElement('div');
    plain.id = 'r3-root-shadow-plain';
    plain.textContent = 'not a write control';
    shadow.append(plain);
    assert.deepEqual(panel.listWriteControls(), [], 'root shadow 内普通节点不得被判红');
    plain.remove();

    // ④ 负对照 B：普通链接 / role=button / tabindex 节点 ⇒ 不得命中
    const link = stubElement('a');
    link.setAttribute('href', '#x');
    const roleButton = stubElement('span');
    roleButton.setAttribute('role', 'button');
    const focusable = stubElement('div');
    focusable.setAttribute('tabindex', '0');
    shadow.append(link, roleButton, focusable);
    assert.deepEqual(panel.listWriteControls(), [], '非写形状节点不得被判红');
    link.remove(); roleButton.remove(); focusable.remove();

    // ⑤ 嵌套：shadow ⊆ iframe ⊆ shadow（root shadow 内 iframe 的子文档里再挂 shadow）
    const frame = stubElement('iframe');
    frame.id = 'r3-root-shadow-frame';
    shadow.append(frame);
    const subDocument = stubElement('#document');
    const subBody = stubElement('body');
    subDocument.append(subBody);
    frame.contentDocument = subDocument;
    const nestedHost = stubElement('div');
    subBody.append(nestedHost);
    const nestedShadow = nestedHost.attachShadow({ mode: 'open' });
    const nestedButton = stubElement('button');
    nestedButton.id = 'r3-nested-shadow-button';
    nestedButton.type = 'button';
    nestedShadow.append(nestedButton);
    assert.ok(panel.listWriteControls().some((hit) => hit.includes('r3-nested-shadow-button')),
      `嵌套 shadow ⊆ iframe ⊆ shadow 内的 button 必须命中，实测 ${JSON.stringify(panel.listWriteControls())}`);
    nestedButton.remove();
    assert.deepEqual(panel.listWriteControls(), [], '嵌套清理后必须复原为空');
    frame.remove();

    // ⑥ 回归：`#hud` 的 light DOM 注入仍命中（证明下钻只加深度、没换判据）
    const lightWrite = stubElement('button');
    lightWrite.id = 'r3-hud-light-write';
    lightWrite.type = 'button';
    hud.append(lightWrite);
    assert.ok(panel.listWriteControls().includes('button#r3-hud-light-write'), 'light DOM 注入仍必须命中');
    lightWrite.remove();
    assert.deepEqual(panel.listWriteControls(), [], '最终必须复原为空');
  });
});

test('req20261012_r3_event_stream_empty_text_is_neutral_reason_is_machine_readable', () => {
  withStubDom((hud) => {
    const panel = new ObservePanel(hud as never);
    const stream = hud.querySelector('#event-stream')!;
    const textOf = () => stream.querySelectorAll('li').map((item) => String(item.textContent)).join('\n');

    // ① 零事件 ⇒ 可见文本中性（**不得**断言因果）+ 原因在 dataset
    panel.setEventFilter({ entity: 'room-probe-01' });
    assert.equal(textOf(), '暂无事件', '可见文本必须为中性表述');
    assert.equal(/事件通道|未下发|event 记录/.test(textOf()), false, '可见文本不得断言缺失原因');
    assert.equal(stream.dataset.emptyReason, 'no-event-records-received', '原因必须可从机器可读字段取出');

    // ② 有事件但无匹配 ⇒ 另一个语义不同的空态（原因值也不同）
    panel.renderEventStream([
      { seq: 1, tick: 10, type: 'npc.action', actor: 'npc-probe-1', payload: { action: 'move', target_entity: 'room-probe-01' } },
    ] as never);
    panel.setEventFilter({ entity: 'room-probe-99' });
    assert.equal(stream.dataset.emptyReason, 'no-event-matches-entity-filter');
    assert.notEqual(stream.dataset.emptyReason, 'no-event-records-received', '两种空态的 reason 必须可区分');

    // ③ 有匹配 ⇒ 不再有空态，`emptyReason` 必须被清掉（不留误导性残留）
    panel.setEventFilter({ entity: 'room-probe-01' });
    assert.equal(stream.dataset.emptyReason, undefined, '有匹配时不得残留 emptyReason');
    assert.equal(textOf(), 't10 npc.action');

    // ④ 清空过滤后仍有事件 ⇒ 仍无空态
    panel.setEventFilter(null);
    assert.equal(stream.dataset.emptyReason, undefined);
  });
});
