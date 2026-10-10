/**
 * S-1 · **资产绑定层**（N5 / B-2）—— 纯数据 + 纯函数，Node 可 import、零 IO、零 WebGL 依赖。
 *
 * 职责边界（REQ §三 S-1）：
 *   - 世界状态负责：身份、位置、行为、关系、记忆、事件（**权威**，本文件不碰）；
 *   - **资产绑定**负责：模型、材质、骨骼、动作及**版本**（本文件）；
 *   - 客户端负责：把这些状态**自然地**表现出来（`presentation.ts` / `character_instance.ts`）。
 *
 * 硬口径：
 *   - `entity_id` 绑定**角色实例**，不再要求它对应一个躯干 `BoxGeometry`（REQ §三 S-1 原文）；
 *   - 绑定表是 `binding_set_sha256`（`AC-E-2d`）与 tag 第三段（`AC-A-2b`）的**唯一**取数面；
 *   - `asset_bundle_sha256`（`AC-E-2a`）与 `binding_set_sha256`（`AC-E-2d`）的口径**逐字**按
 *     `01a §0.6` 的手算样例实现（排序键 / 分隔符 / **无尾换行**）。
 */

/** 一个角色实例的绑定项（`AC-E-2d` 的 `binding_id` / `glb_url` / `asset_version` 三段）。 */
export interface AssetBinding {
  /** 稳定 id（`E-2d` 的第 1 段）。 */
  readonly binding_id: string;
  /** GLB 相对 URL（`assets/...`，第 2 段）—— **盘上真实存在**的交付件。 */
  readonly glb_url: string;
  /** 资产版本（第 3 段）；改 GLB 必须**同时**改版本（否则 tag 段失去意义）。 */
  readonly asset_version: string;
  /** 该绑定挂到哪些实体（`entity_id` 列表；空 = 未分配，走回落盒体）。 */
  readonly entity_ids: readonly string[];
  /** 该角色实例使用的 `SURFACES_EXT` 表面（`AC-I-3g` 的「场景实际使用面」来源之一）。 */
  readonly ext_surfaces: readonly string[];
  /** 该绑定的骨架/动作来源说明（真实否，写清楚，不吹）。 */
  readonly skeleton_note: string;
}

/**
 * **绑定表**（唯一取数面）。
 * `xuqin_default` 是本轮真实接入的 rigged GLB；`npc_generic` 是**回落盒体**绑定
 * （`glb_url = null` 语义由 `has_glb` 表达，见 `bindingReport()` 的 `glb_loaded`）。
 */
export const BINDINGS: readonly AssetBinding[] = [
  {
    binding_id: 'xuqin_default',
    glb_url: 'assets/character/xuqin-body.glb',
    asset_version: '1.0.0',
    entity_ids: ['npc-006'],
    ext_surfaces: ['skin_face', 'skin_hand', 'fabric_cotton_jacket'],
    skeleton_note: '本项目建设期接入的角色资产：AI 图生3D（影眸 Hyper3D Gen-2，经火山方舟 Ark）'
      + '→ 本地绑定 26 骨（含 4 向 × 2 级裙摆骨链）→ 减面 + 2×2K 贴图；1 skin / 26 joints / '
      + '2 animations（Idle / Walk）。**骨架与动画均为真实 GLB 数据**，不是程序化盒体。'
      + '**许可状态未证实**（见 web/assets/provenance.json）。',
  },
  {
    binding_id: 'npc_generic',
    glb_url: 'assets/character/generic-fallback.glb',
    asset_version: '0.0.0',
    entity_ids: [],
    ext_surfaces: [],
    skeleton_note: '**回落绑定**：无 GLB（`glb_url` 只是契约占位，盘上不存在 ⇒ 加载必然失败 ⇒ '
      + '显式回落盒体并记 `degradations`）。用于 `AC-I-2` 的负对照注入面。',
  },
];

export const BINDING_IDS: readonly string[] = BINDINGS.map((b) => b.binding_id);

export function bindingById(id: string): AssetBinding | null {
  return BINDINGS.find((b) => b.binding_id === id) ?? null;
}

/** 实体 → 绑定（`entity_id` 是**角色实例**的标识，不再绑死到某个盒体）。 */
export function bindingForEntity(entityId: string): AssetBinding | null {
  return BINDINGS.find((b) => b.entity_ids.includes(entityId)) ?? null;
}

/** `AC-E-2d` 的哈希输入行（**唯一**派生点；改排序键/分隔符必须改这里）。 */
export function bindingSetLines(): string[] {
  return [...BINDINGS]
    .map((b) => `${b.binding_id}:${b.glb_url}:${b.asset_version}`)
    .sort();
}

/** `AC-E-2a` 的哈希输入行（资产 id : 转换后字节哈希）。 */
export function assetBundleLines(entries: ReadonlyArray<{ asset_id: string; converted_sha256: string }>): string[] {
  return entries
    .map((e) => `${e.asset_id}:${e.converted_sha256}`)
    .sort();
}

/**
 * 绑定报告（`AC-A-2e` / `AC-I-1` / `AC-I-2` 的机读锚）。
 * `glb_loaded` **不是**自报字段：它由 `character_instance.ts` 在**真的**加载回调里置位，
 * 并由外部锚（运行期读回的 GLB 字节哈希，见 `AC-A-2e`）复核。
 */
export interface BindingReport {
  schema_version: string;
  bindings: Array<{
    binding_id: string;
    glb_url: string;
    asset_version: string;
    entity_ids: string[];
    has_glb: boolean;
    ext_surfaces: string[];
    skeleton_note: string;
  }>;
  binding_set_sha256: string | null;
  binding_set_lines: string[];
  degradations: Array<{ code: string; detail: string }>;
}

/** 收集运行期降级（加载失败 / 绑定缺失 / 骨架缺失）。**不抛**。 */
const bindingDegradations: Array<{ code: string; detail: string }> = [];

export function recordBindingDegradation(code: string, detail: string): void {
  bindingDegradations.push({ code, detail });
}

export function bindingDegradationsSnapshot(): Array<{ code: string; detail: string }> {
  return bindingDegradations.map((d) => ({ ...d }));
}

export function clearBindingDegradations(): void {
  bindingDegradations.length = 0;
}

export function bindingReport(): BindingReport {
  return {
    schema_version: 'n5-binding/1',
    bindings: BINDINGS.map((b) => ({
      binding_id: b.binding_id,
      glb_url: b.glb_url,
      asset_version: b.asset_version,
      entity_ids: [...b.entity_ids],
      has_glb: b.glb_url.endsWith('.glb'),
      ext_surfaces: [...b.ext_surfaces],
      skeleton_note: b.skeleton_note,
    })),
    binding_set_sha256: null, // 由 `binding_probe.mjs` 用 WebCrypto/Node crypto 填（浏览器侧不引 crypto 依赖）
    binding_set_lines: bindingSetLines(),
    degradations: bindingDegradationsSnapshot(),
  };
}
