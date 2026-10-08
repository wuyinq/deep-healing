/**
 * 材质类别表（N5 / S-3，`AC-I-3b/c/d/h/i`）—— **纯数据 + 纯函数**，Node 可 import、零 IO。
 *
 * 为什么需要独立文件：用户 §三.3 要求「统一高粗糙度 / 低金属度 / 禁止镜面」这套**全局限制**
 * 改为**按材质类别配置**，「皮肤、布料、玻璃、金属、木材应有各自合理的响应」。
 * 既有 `materials.ts` 的 `SURFACES`（12 条）是**建筑/场地**表面表，其判据体与期望值
 * 必须**逐字节不变**（R7 / `AC-I-3a`）⇒ 类别能力一律落**新文件 + 新注册表**（`SURFACES_EXT`）。
 *
 * 判据映射（冻结口径 `01a` v4.1）：
 *   - `I-3b` 类别区间 ⊆ 旧口径 `roughness∈[0.6,0.95]` / `metalness∈[0,0.15]`，
 *     或属 `skin`/`glass`/`metal` 并给**冻结理由**；
 *   - `I-3c` 任一类别区间**不得**同时等于两个全局全域（禁 catch-all）；成员数 **≥2**，禁 singleton；
 *   - `I-3d` 每个成员的实测值必须落在其类别声明区间内；
 *   - `I-3h` 本文件「类别表块」的 sha256 必须等于 `assert_inputs.json` 的冻结值；
 *   - `I-3i` 三条定向数值：`skin ⇒ roughness<0.6`；`glass ⇒ (transmission|ior) ∧ roughness≤0.15`；
 *     `metal ⇒ metalness≥0.6`。负对照：`metal` 成员 `metalness` 置 0.04 ⇒ 必红。
 *
 * 数值口径：所有区间端点一律 `toFixed(6)` 可复算（与 `AC-F-5b` 同口径）。
 */

/** 类别 id（REQ §三.3 点名的五类）。**不用 `enum`**（Node 类型剥离不支持）。 */
export type MaterialClassId = 'skin' | 'fabric' | 'glass' | 'metal' | 'wood';

/** 旧口径（`SURFACES` 的区间，见 `materials.ts` 文件头 §4）—— 冻结值，不得放宽。 */
export const LEGACY_ROUGHNESS_RANGE: readonly [number, number] = [0.6, 0.95];
export const LEGACY_METALNESS_RANGE: readonly [number, number] = [0, 0.15];

/** 全局全域（`I-3c` 的「不得等于全域」判据基准）。 */
export const GLOBAL_ROUGHNESS_DOMAIN: readonly [number, number] = [0, 1];
export const GLOBAL_METALNESS_DOMAIN: readonly [number, number] = [0, 1];

export interface MaterialClassDecl {
  readonly id: MaterialClassId;
  /** 人类可读标签（报告用）。 */
  readonly label: string;
  /** **声明区间**（`I-3b`/`I-3d` 的判据面）。 */
  readonly roughness: readonly [number, number];
  readonly metalness: readonly [number, number];
  /** `within_legacy` = 区间 ⊆ 旧口径；`frozen_reason` = 属 skin/glass/metal 且给理由。 */
  readonly containment: 'within_legacy' | 'frozen_reason';
  /** `containment === 'frozen_reason'` 时**必填**（`I-3b` 的冻结理由）。 */
  readonly frozen_reason: string | null;
  /** 该类别在 `SURFACES_EXT` 里的成员 id（**≥2**，`I-3c` 禁 singleton）。 */
  readonly members: readonly string[];
  /** 定向数值判据（`I-3i`）的人类可读形态（机器判据在 `material_class_check.py`）。 */
  readonly directional_rule: string;
  /** 该类的「合理响应」说明（用户 §三.3 的逐类行为）。 */
  readonly response_note: string;
}

/**
 * 类别表本体。**改动此块即触发 `AC-I-3h` 的 sha256 不符 ⇒ 必红**（判据承担，不是自律）。
 * 成员数一律 ≥2；区间一律不取全局全域。
 */
export const MATERIAL_CLASSES: Readonly<Record<MaterialClassId, MaterialClassDecl>> = {
  skin: {
    id: 'skin',
    label: '皮肤',
    roughness: [0.30, 0.55],
    metalness: [0.0, 0.05],
    containment: 'frozen_reason',
    frozen_reason:
      '皮肤不在旧口径 [0.6,0.95] 内：旧口径是 N4 的**建筑/场地**表面区间，物理上皮肤不可能与砖墙同粗糙。'
      + 'REQ §三.3 明确要求「皮肤…应有各自合理的响应」⇒ 按类别声明 [0.30,0.55]（人体皮肤实测 0.3–0.6，'
      + '此处取下半段以保留次表面感），并以 `I-3i① roughness < 0.6` 定向约束。',
    members: ['skin_face', 'skin_hand'],
    directional_rule: 'skin 类别成员 ⇒ roughness < 0.6',
    response_note:
      '皮肤：低粗糙 + 近零金属度 ⇒ 宽而弱的镜面高光（次表面散射的可负担近似）；'
      + '不参与建筑表面的 `ROUGHNESS_MIN` 下限。',
  },
  fabric: {
    id: 'fabric',
    label: '布料',
    roughness: [0.72, 0.95],
    metalness: [0.0, 0.05],
    containment: 'within_legacy',
    frozen_reason: null,
    members: ['fabric_cotton_jacket', 'fabric_linen_curtain'],
    directional_rule: 'fabric 类别成员 ⇒ 0.72 ≤ roughness ≤ 0.95',
    response_note:
      '布料：高粗糙 + 零金属度 ⇒ 几乎无镜面，仅在掠射角有微弱的绒面回光（sheen 的可负担近似）。'
      + '区间 ⊆ 旧口径，**不需要**豁免 —— 这是 `B-G1` 要的「fabric 与旧口径不冲突」的实测证明。',
  },
  glass: {
    id: 'glass',
    label: '玻璃',
    roughness: [0.03, 0.12],
    metalness: [0.0, 0.02],
    containment: 'frozen_reason',
    frozen_reason:
      '玻璃不在旧口径内：旧口径 `roughness ≥ 0.6` 是「**禁止镜面高光**」时代的产物，'
      + '而玻璃的物理本质就是镜面透射/反射。REQ §三.3 点名要求玻璃有自身响应 ⇒ '
      + '声明 [0.03,0.12]（清玻璃实测 0.02–0.10），并以 `I-3i②` 要求「'
      + '`transmission`/`ior` 读数存在 ∧ roughness ≤ 0.15」（光有低粗糙、没有透射参数 = 假玻璃）。',
    members: ['glass_window_clear', 'glass_bottle'],
    directional_rule: 'glass 类别成员 ⇒ 必须有 transmission/ior 读数 且 roughness ≤ 0.15',
    response_note:
      '玻璃：低粗糙 + transmission + ior ⇒ 真实透射与掠射镜面（`MeshPhysicalMaterial`），'
      + '**不是**旧实现里「半透明 + 复用水泥贴图」的假玻璃。',
  },
  metal: {
    id: 'metal',
    label: '金属',
    roughness: [0.18, 0.45],
    metalness: [0.70, 0.92],
    containment: 'frozen_reason',
    frozen_reason:
      '金属的 `metalness` 不在旧口径 [0,0.15] 内：旧口径来自「**低金属度**」全局限制，'
      + '而金属的物理本质是金属度接近 1。REQ §三.3 点名要求金属有自身响应 ⇒ '
      + '声明 metalness [0.70,0.92]（拉丝/涂装钢实测 0.7–0.95），并以 `I-3i③ metalness ≥ 0.6` 定向约束。',
    members: ['metal_railing', 'metal_door'],
    directional_rule: 'metal 类别成员 ⇒ metalness ≥ 0.6',
    response_note:
      '金属：高金属度 + 中等粗糙 ⇒ 有方向的、带各向异性的镜面拉伸（`anisotropy` 见 `SURFACES_EXT`），'
      + '**不是**旧实现里「metalness ≤ 0.15 的哑光灰」。',
  },
  wood: {
    id: 'wood',
    label: '木材',
    roughness: [0.62, 0.88],
    metalness: [0.0, 0.06],
    containment: 'within_legacy',
    frozen_reason: null,
    members: ['wood_door_frame', 'wood_table_top'],
    directional_rule: 'wood 类别成员 ⇒ 0.62 ≤ roughness ≤ 0.88',
    response_note:
      '木材：中高粗糙 + 零金属度 ⇒ 清漆的宽高光叠加木纹的法线起伏。'
      + '区间 ⊆ 旧口径，**不需要**豁免 —— `B-G1` 的「wood 与旧口径不冲突」由此实测关闭。',
  },
};

export const MATERIAL_CLASS_IDS: readonly MaterialClassId[] = Object.keys(MATERIAL_CLASSES) as MaterialClassId[];

/** `roughness ⊆ [lo,hi]`。 */
export function roughnessWithin(id: MaterialClassId, value: number): boolean {
  const [lo, hi] = MATERIAL_CLASSES[id].roughness;
  return value >= lo && value <= hi;
}

/** `metalness ⊆ [lo,hi]`。 */
export function metalnessWithin(id: MaterialClassId, value: number): boolean {
  const [lo, hi] = MATERIAL_CLASSES[id].metalness;
  return value >= lo && value <= hi;
}

/** 区间是否 ⊆ 旧口径（`I-3b` 的 `within_legacy` 分支）。 */
export function containmentHolds(id: MaterialClassId): boolean {
  const decl = MATERIAL_CLASSES[id];
  if (decl.containment === 'frozen_reason') return decl.frozen_reason !== null && decl.frozen_reason.length > 0;
  return decl.roughness[0] >= LEGACY_ROUGHNESS_RANGE[0] && decl.roughness[1] <= LEGACY_ROUGHNESS_RANGE[1]
    && decl.metalness[0] >= LEGACY_METALNESS_RANGE[0] && decl.metalness[1] <= LEGACY_METALNESS_RANGE[1];
}

/** `I-3c` 的禁 catch-all：区间**不得**同时等于 roughness 与 metalness 的全局全域。 */
export function notCatchAll(id: MaterialClassId): boolean {
  const decl = MATERIAL_CLASSES[id];
  const fullRough = decl.roughness[0] === GLOBAL_ROUGHNESS_DOMAIN[0] && decl.roughness[1] === GLOBAL_ROUGHNESS_DOMAIN[1];
  const fullMetal = decl.metalness[0] === GLOBAL_METALNESS_DOMAIN[0] && decl.metalness[1] === GLOBAL_METALNESS_DOMAIN[1];
  return !(fullRough && fullMetal);
}

/** 类别表读数（`I-3h` 的判据输入；逐项 `toFixed(6)` 可复算）。 */
export function materialClassReport(): Array<Record<string, unknown>> {
  return MATERIAL_CLASS_IDS.map((id) => {
    const decl = MATERIAL_CLASSES[id];
    return {
      id,
      label: decl.label,
      roughness: decl.roughness.map((v) => Number(v.toFixed(6))),
      metalness: decl.metalness.map((v) => Number(v.toFixed(6))),
      containment: decl.containment,
      frozen_reason: decl.frozen_reason,
      members: [...decl.members],
      member_count: decl.members.length,
      directional_rule: decl.directional_rule,
      response_note: decl.response_note,
      within_legacy: containmentHolds(id),
      not_catch_all: notCatchAll(id),
    };
  });
}
