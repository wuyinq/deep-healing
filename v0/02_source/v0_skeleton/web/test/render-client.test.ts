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
