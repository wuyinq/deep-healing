/**
 * 人物外形装配器（N2 / W2a）—— **纯函数 + 只读解析器**。
 *
 * 数据通路（设计 D1）：内容包 `npcs/*.json` 的 `appearance` 块 → 装配配置 → 渲染。
 * **不经内核 state**：`world.schema.json` 的 `$defs/entity` 是 `additionalProperties:false`
 * （外形随 state 下发属**契约变更**，本轮非目标）。渲染层读内容包只沿用既有先例
 * （`main.ts` 的 `loadNpcDisplayName()` 同一条 URL 约定 `/packs/<packId>/npcs/<id>.json`），
 * 失败 ⇒ `null`，**不伪造**任何具体人物特征。
 *
 * 确定性契约（硬）：
 *   - 本模块**零** `Math.random` / `Date.now` / `new Date` / 迭代顺序依赖；
 *   - 同 `(appearance, context)` ⇒ 逐字段相同的部件表（浮点一律 `round6` 收敛）；
 *   - 部件表与**读法无关**（读法只改光照与材质亮度，见 `lighting.ts`）。
 *
 * 命名（R-09 钉死）：部件名**来自数据**（固定字段名表 `CHARACTER_PART_NAMES`），
 * `"<实体 id>/<部件名>"`；**禁止**下标 / 遍历序号 / `part-3` 这类命名。
 * 例外（R-06 / D3 钉死）：**根 mesh = 躯干**，其 `name` 保持 = **实体 id**
 * （既有 `assemblyReport()` / `structureReport()` 的取数路径零改动）；该部件的
 * `part` 字段仍是 `torso`，`is_root === true`。
 *
 * 颜色锚点（D5）：本文件内**不得**出现任何角色锚点 hex 字面量（猩红瞳 / 艳红唇 /
 * 艳红外衣 / 苍白皮肤）—— 锚点色**只**写在 `npcs/npc-006.json`；本文件只保留
 * **中性色**的通用人形默认值（`NEUTRAL_*`）。
 */

export interface AppearanceField<T> {
  value: T;
  source_facts?: string[];
  design_fill?: boolean;
  design_note?: string;
}

export interface StatePredicate {
  target_entity_in?: string[];
  schedule_state_in?: string[];
  room_id_in?: string[];
  tags_include?: string[];
}

export interface CharacterAppearanceState {
  id: string;
  label: string;
  when?: StatePredicate;
  mask?: boolean;
}

export interface CharacterAppearanceMask {
  color: AppearanceField<string>;
  number: AppearanceField<string>;
  number_label: AppearanceField<string>;
  shape: AppearanceField<string>;
  material: AppearanceField<string>;
}

export interface CharacterAppearance {
  eyes: { color: AppearanceField<string> };
  lips: { color: AppearanceField<string> };
  skin: { color: AppearanceField<string> };
  hair: { color: AppearanceField<string>; length?: AppearanceField<string> };
  garment: { color: AppearanceField<string>; cut?: AppearanceField<string> };
  height_cm: AppearanceField<number>;
  age_look?: AppearanceField<string>;
  build: AppearanceField<string>;
  mask?: CharacterAppearanceMask;
  states: CharacterAppearanceState[];
}

/** 装配上下文：**只读既有 state 字段**（不新增状态字段）。 */
export interface CharacterStateContext {
  entityId: string;
  state?: {
    transform?: { room_id?: string | null };
    schedule?: { state?: string | null; target_entity?: string | null };
    tags?: string[];
  };
}

export interface CharacterPart {
  entity_id: string;
  /** 部件名（来自固定字段名表，**不是**下标）。 */
  part: string;
  /** 场景图里的对象名：根 mesh = 实体 id；其余 = `"<实体 id>/<部件名>"`。 */
  name: string;
  is_root: boolean;
  /** 装配用尺寸（米）。 */
  size: [number, number, number];
  /** 相对**根 mesh** 的局部偏移（米）。 */
  local_offset: [number, number, number];
  /** 来自装配配置（包内 hex）—— **读法无关**。 */
  source_hex: string;
}

/** 部件名固定表（R-09：名字来自数据，禁下标 / 遍历序号）。 */
export const CHARACTER_PART_NAMES: readonly string[] = [
  'head', 'hair', 'torso', 'arm_l', 'arm_r', 'leg_l', 'leg_r', 'coat', 'eyes', 'lips', 'mask',
] as const;

/** 装配顺序（固定；躯干必须是**根**，排第一）。 */
export const CHARACTER_PART_ORDER: readonly string[] = [
  'torso', 'head', 'hair', 'arm_l', 'arm_r', 'leg_l', 'leg_r', 'coat', 'eyes', 'lips', 'mask',
] as const;

/** 身高基准（厘米）：`height_cm` 相对它做**等比**缩放（确定性、无随机）。 */
export const BASE_HEIGHT_CM = 168;

/** 日常态部件数 = 10（不含 mask）；面具态 = 11。均 ≥ 6（AC-3）。 */
export const DAILY_PART_COUNT = 10;
export const MASKED_PART_COUNT = 11;

// --------------------------------------------------------------- 中性色（**不是**角色锚点）
// D5：本文件只许出现**中性色**默认人形色值。刻意让首字符落在 1-7 / d / e / f，
// 使 `#(8|9|a|b|c)[0-9a-f]{5}` 这一「锚点色」静态模式在本文件内**零命中**。
const NEUTRAL_SKIN = '#d8c6ad';
const NEUTRAL_HAIR = '#3a322b';
const NEUTRAL_EYES = '#4b4239';
const NEUTRAL_LIPS = '#7d6a60';
const NEUTRAL_MASK = '#e6e0d5';
/** 通用人形外衣：3 档中性色，按实体 id 的**确定性**摘要择一（同 id ⇒ 同色）。 */
const NEUTRAL_GARMENTS: readonly string[] = ['#6e6455', '#5c5548', '#7a6f63'] as const;

interface PartSpec {
  part: string;
  size: [number, number, number];
  offset: [number, number, number];
  color: 'skin' | 'hair' | 'garment' | 'eyes' | 'lips' | 'mask';
}

/**
 * 部件几何表（米，`BASE_HEIGHT_CM` 基准）。躯干 = 根 mesh。
 *
 * N2-r3 修复轮（**只改本表的 size / offset，不改部件清单、不拆部件**）——
 * 缺陷（architect 实机核验）：r2 的 `hair` 盒 x/y/z 三区间**完整包住** `head` 盒 ⇒
 * 苍白皮肤（面部）在画面上不可见；`eyes`/`lips` 只比 `hair` 前表面凸出 5 mm ⇒ 读作细缝；
 * `mask` 与 `hair` 同宽（0.30）且 `y∈[0.41,0.61]` ⇒ 盖住瞳/唇，读作「整块浅色面罩」。
 * 本轮的几何口径（角色正面 = **+z**；全部由 `scene_assert` 的几何判据机器核验）：
 *   - **面部露出**：`head` 前表面 `z=0.155` **严格大于** `hair` 前表面 `z=0.135`（露 20 mm）；
 *     `hair` 只做「顶盖 + 后脑 + 两侧」——正面不覆盖面部矩形；
 *   - **五官前伸**：`eyes` 前伸 20 mm / `lips` 前伸 17.5 mm（相对面部前表面），
 *     且**均**比 `hair` 前表面凸出 ≥ 15 mm ⇒ 猩红瞳 / 艳红唇在取证图里可判读；
 *   - **长发（设计 B1「过肩、日常松散」）**：`hair` 下缘 `y=0.06`，低于肩线（躯干上缘 `y=0.33`）
 *     270 mm，且前表面（`z=0.135`）在 `coat` 前表面（`z=0.12`）之前 ⇒ 正面可读出「长发垂在胸前」；
 *   - **长款外衣（设计 B6「及膝或过膝」）**：`coat` 下摆 `y=−0.81`，低于膝线 `y=−0.72`，
 *     小腿仍露出 310 mm ⇒ 轮廓上明显长于腿；
 *   - **半张面具（设计 B5）**：`mask` 收窄到 `x=±0.12`（比脸窄 10 mm/侧）、只覆盖**上半脸**
 *     （`y∈[0.485,0.645]`），下缘**高于唇上缘** ⇒ 下半脸的苍白皮肤 + 艳红唇保持可见。
 * 颜色锚点**未动**（本文件仍只有中性色默认值；锚点色只写在 `npcs/npc-006.json`）。
 *
 * N2-r4 修复轮（**仍只改本表的 size / offset**，部件清单/命名/颜色零改动）——
 * 缺陷（architect 实机视觉核验）：r3 的 `hair` 宽 0.36 **小于** `torso` 宽 0.46 ⇒ 头发下部**缩在肩内**
 * （两侧各窄 50 mm）⇒ 画面上读作「头罩 / 头盔」而不是「垂在肩外的长发」；`torso` 0.46 + 臂在 ±0.30
 * （合计 0.73 宽）⇒ 整体读作「方肩无性别立柱」⇒ PM 的 AC-9「能认出性别」不成立。
 * 本轮的几何口径（三条轮廓线索，全部由 `scene_assert` 的几何判据机器核验）：
 *   - **长发披在肩外**：`hair` 宽 **0.58** ＞ `torso` 宽 **0.38**（两侧各宽出 100 mm）⇒ 发帘落在肩外；
 *     下缘 `y=−0.02`（垂到躯干中部以下，低于肩线 350 mm）；前表面仍 `z=0.135` ＜ `head` 前表面 0.155
 *     ⇒ **面部照旧露出**；上沿 `y=0.70` ＞ 头顶 0.64（顶盖仍在场）；
 *   - **收腰 / 窄肩**：`torso` 由 0.46 收窄到 **0.38**（≈ 1.68 m 身高的女性肩宽量级）；
 *     `arm_l`/`arm_r` 由 ±0.30 内收到 **±0.24**、并缩短到 0.40 m（`y∈[−0.12,0.28]`）——
 *     内缘恰好贴住躯干侧面 `x=±0.19`（既不悬空也不穿模），外缘 `±0.29` 与发缘齐平
 *     ⇒ 发以下**立刻**收窄到躯干宽度，轮廓读作「窄肩 + 长发披肩」而不是方肩宽柱；
 *     `coat` 由 0.56 收窄到 **0.38**（与躯干同宽，贴合身体）⇒ 比发窄 200 mm，两侧发帘
 *     落在外衣轮廓**之外**、清晰可读；
 *   - **露出下半身**：`coat` 下摆 `y=−0.81` 仍过膝（膝线 `−0.72`），小腿露出 310 mm，
 *     两条腿之间仍有 50 mm 缝隙 ⇒ 读作「两条腿」，不是一整块柱体。
 * 本轮**不新增设计**：长发过肩 = 设计书 B1 既有 `design_fill`；及膝/过膝长外衣 = B6 既有条款。
 */
const PART_TABLE: readonly PartSpec[] = [
  { part: 'torso', size: [0.38, 0.66, 0.26], offset: [0, 0, 0], color: 'garment' },
  // N4-r2 / M-4（关闭 Raven N-13 / 预审 R-3）：**真实头身比**在 11 条比例判据的可行域内落地。
  // 目标 = 设计 §D-5 的「头高 ≈ 身高 1/7.5」。实测：`head` 高 h、头顶 = 0.50 + h/2、脚底 = −1.22
  //   ⇒ 全高 = 1.72 + h/2；令 h / (1.72 + h/2) = 1/7.5 ⇒ h = 0.2457。
  // 取 h = **0.245**（宽/深同步收到 0.24 保持头形比例）⇒ 实测头身比 = 0.245 / 1.8425 = **1/7.52**。
  // 可行域逐条核算（**不动任何阈值**）：
  //   · `character_mask_reads_half_face`：`mask.height 0.16 ≤ head.height × 0.7 = 0.1715` ✓（余量 11.5 mm）；
  //     下半脸皮肤带 = mask.bottom_y 0.485 − head.bottom_y 0.3775 = **0.1075 m ≥ 0.08** ✓；
  //   · `character_hair_reads_long`：发顶 0.68 ≥ 头顶 0.6225 ✓；发下缘 −0.02 低于肩线 0.33 共 350 mm ✓；
  //   · `character_face_visible_beyond_hair`：脸前表面 0.145 > 发前表面 0.045（露 **100 mm**）✓；
  //   · `character_realism_geometry_constraints`：颈 y∈[0.31,0.41] 仍跨躯干上缘 0.33 与头下缘 0.3775 ✓；
  //   · 瞳/唇/眉/鼻全部仍落在头盒内（逐项见 `03` §M-4 的实测读数）。
  { part: 'head', size: [0.24, 0.245, 0.24], offset: [0, 0.50, 0.025], color: 'skin' },
  // N4 / W5（路线 a′ 可行域内）：`hair` 由 [0.58,0.72,0.30]@[0,0.34,-0.015] 收为 [0.50,0.70,0.24]@[0,0.33,-0.075]。
  // 根因（实机评图）：原发盒前表面 z=0.135 只比脸前表面 0.155 落后 20 mm ⇒ 正面看是一整块黑碑、
  // 脸是碑上贴的小方块。改为**向后收 60 mm + 减薄 60 mm** ⇒ 脸前表面凸出发前表面 110 mm，脸成为独立体块。
  // 仍在 11 条比例判据可行域内：宽 0.50−躯干 0.38=0.12 ≥0.10、两侧各 0.06 ≥0.04、宽−外衣 0.12 ≥0.06、
  // 下缘 −0.02 ≤0.0 且低于肩线 0.35 ≥0.10、上缘 0.68 ≥ 头顶 0.64（`hairReadsLong` 要求发顶不低于头顶）。
  { part: 'hair', size: [0.50, 0.70, 0.24], offset: [0, 0.33, -0.075], color: 'hair' },
  { part: 'arm_l', size: [0.10, 0.40, 0.14], offset: [-0.24, 0.08, 0], color: 'garment' },
  { part: 'arm_r', size: [0.10, 0.40, 0.14], offset: [0.24, 0.08, 0], color: 'garment' },
  { part: 'leg_l', size: [0.17, 0.80, 0.20], offset: [-0.11, -0.72, 0], color: 'garment' },
  { part: 'leg_r', size: [0.17, 0.80, 0.20], offset: [0.11, -0.72, 0], color: 'garment' },
  { part: 'coat', size: [0.38, 1.12, 0.34], offset: [0, -0.25, -0.05], color: 'garment' },
  { part: 'eyes', size: [0.19, 0.05, 0.03], offset: [0, 0.53, 0.16], color: 'eyes' },
  { part: 'lips', size: [0.11, 0.035, 0.03], offset: [0, 0.43, 0.1575], color: 'lips' },
  { part: 'mask', size: [0.24, 0.16, 0.05], offset: [0, 0.565, 0.17], color: 'mask' },
] as const;

const HEX_RE = /^#[0-9a-f]{6}$/;

/** 浮点收敛到 6 位小数（消除尾差噪声，同时保留任何真实差异）。 */
function round6(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function fieldValue<T>(field: AppearanceField<T> | undefined, fallback: T): T {
  if (!field || field.value === undefined || field.value === null) return fallback;
  return field.value;
}

function colorFieldValue(field: AppearanceField<string> | undefined, fallback: string): string {
  const value = fieldValue(field, fallback);
  return typeof value === 'string' && HEX_RE.test(value) ? value : fallback;
}

/** 实体 id 的确定性摘要（FNV-1a 32；**不是**随机、不依赖遍历顺序）。 */
function stableIdHash(value: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

/**
 * **确定性通用人形**（兜底）：包内没有 `appearance`（或缺字段）时使用。
 * 全部字段标 `design_fill: true`（**不是**原著事实）；颜色取中性色，**不含**任何角色锚点。
 */
export function defaultAppearanceFor(entityId: string): CharacterAppearance {
  const garment = NEUTRAL_GARMENTS[stableIdHash(entityId) % NEUTRAL_GARMENTS.length] as string;
  const design = (value: string | number): { value: string | number; design_fill: true } =>
    ({ value, design_fill: true });
  return {
    eyes: { color: design(NEUTRAL_EYES) as AppearanceField<string> },
    lips: { color: design(NEUTRAL_LIPS) as AppearanceField<string> },
    skin: { color: design(NEUTRAL_SKIN) as AppearanceField<string> },
    hair: { color: design(NEUTRAL_HAIR) as AppearanceField<string>, length: design('shoulder') as AppearanceField<string> },
    garment: { color: design(garment) as AppearanceField<string>, cut: design('long-coat') as AppearanceField<string> },
    height_cm: design(BASE_HEIGHT_CM) as AppearanceField<number>,
    age_look: design('adult') as AppearanceField<string>,
    build: design('average') as AppearanceField<string>,
    states: [{ id: 'daily', label: '日常态' }],
  };
}

/** 谓词命中：只读既有 state 字段；提供多个键时**全部**必须命中（AND）。 */
export function matchesStatePredicate(predicate: StatePredicate | undefined, context: CharacterStateContext | undefined): boolean {
  if (!predicate) return false;
  const state = context?.state ?? {};
  const targetEntity = state.schedule?.target_entity;
  const scheduleState = state.schedule?.state;
  const roomId = state.transform?.room_id;
  const tags = Array.isArray(state.tags) ? state.tags : [];
  if (predicate.target_entity_in) {
    // R-13：target_entity 的类型是 `string | null`；null / 缺字段 ⇒ 不命中。
    if (typeof targetEntity !== 'string' || !predicate.target_entity_in.includes(targetEntity)) return false;
  }
  if (predicate.schedule_state_in) {
    if (typeof scheduleState !== 'string' || !predicate.schedule_state_in.includes(scheduleState)) return false;
  }
  if (predicate.room_id_in) {
    if (typeof roomId !== 'string' || !predicate.room_id_in.includes(roomId)) return false;
  }
  if (predicate.tags_include) {
    if (!predicate.tags_include.every((tag) => tags.includes(tag))) return false;
  }
  return true;
}

/**
 * 形态判定（D2）—— **纯函数、确定性、无时间源**。
 * 规则：按 `states` 数组顺序取**第一个** `when` 命中项；都不命中 ⇒ 无 `when` 的默认态；
 * 再没有 ⇒ 字面量 `'daily'`。`states: []` / 缺 `states` / `schedule.target_entity === null`
 * ⇒ `'daily'`（**显式返回，不抛异常**，R-13）。
 */
export function resolveStateId(appearance: CharacterAppearance | null | undefined, context: CharacterStateContext | undefined): string {
  const states = Array.isArray(appearance?.states) ? appearance?.states ?? [] : [];
  for (const entry of states) {
    if (!entry || !entry.when) continue;
    if (matchesStatePredicate(entry.when, context)) return entry.id;
  }
  const fallback = states.find((entry) => entry && !entry.when);
  if (fallback) return fallback.id;
  return 'daily';
}

/** 该形态是否使用面具部件（需要 `states[].mask` 与 `appearance.mask` **同时**在场）。 */
export function stateUsesMask(appearance: CharacterAppearance | null | undefined, stateId: string): boolean {
  if (!appearance?.mask) return false;
  const states = Array.isArray(appearance.states) ? appearance.states : [];
  const entry = states.find((item) => item && item.id === stateId);
  return Boolean(entry?.mask);
}

/**
 * N2-r2 / F-3：面具数据缺失时的**显式降级**读数（结构化，可观测；**不抛异常**）。
 *
 * 契约：`states` 声明某形态 `mask: true`，而 `appearance.mask` **不在场** ⇒ 该形态
 * 没有可渲染的面具数据。此前表现为「谓词命中 masked、装配出无面具的部件集」这种
 * 半降级状态（且校验器/判据侧会抛未捕获异常）。现在**显式**降级：生效形态回到
 * `daily`，并给出结构化告警 `E_MASK_DATA_MISSING`（由 `appearanceReport()` 暴露）。
 */
export interface MaskDegradation {
  /** 谓词命中的形态（可能是 `masked`）。 */
  requested_state_id: string;
  /** 实际生效的形态（降级后 = `daily`）。 */
  effective_state_id: string;
  degraded: boolean;
  code: string | null;
  detail: string | null;
}

export function resolveMaskDegradation(
  appearance: CharacterAppearance | null | undefined,
  context: CharacterStateContext,
): MaskDegradation {
  const resolved = appearance ?? defaultAppearanceFor(context.entityId);
  const requested = resolveStateId(resolved, context);
  const states = Array.isArray(resolved.states) ? resolved.states : [];
  const entry = states.find((item) => item && item.id === requested);
  const declaresMask = Boolean(entry?.mask);
  const hasMaskData = Boolean(resolved.mask);
  if (declaresMask && !hasMaskData) {
    return {
      requested_state_id: requested,
      effective_state_id: 'daily',
      degraded: true,
      code: 'E_MASK_DATA_MISSING',
      detail: `state '${requested}' declares mask:true but appearance.mask is absent`
        + ' ⇒ explicit degradation to daily (no unmasked "masked" state is rendered)',
    };
  }
  return {
    requested_state_id: requested,
    effective_state_id: requested,
    degraded: false,
    code: null,
    detail: null,
  };
}

function colorForPart(spec: PartSpec, appearance: CharacterAppearance): string {
  switch (spec.color) {
    case 'skin': return colorFieldValue(appearance.skin?.color, NEUTRAL_SKIN);
    case 'hair': return colorFieldValue(appearance.hair?.color, NEUTRAL_HAIR);
    case 'eyes': return colorFieldValue(appearance.eyes?.color, NEUTRAL_EYES);
    case 'lips': return colorFieldValue(appearance.lips?.color, NEUTRAL_LIPS);
    case 'mask': return colorFieldValue(appearance.mask?.color, NEUTRAL_MASK);
    case 'garment':
    default: return colorFieldValue(appearance.garment?.color, NEUTRAL_GARMENTS[0] as string);
  }
}

/**
 * **纯函数装配器**：无 IO / 无时间 / 无随机；同输入 ⇒ 同输出。
 * `appearance === null` ⇒ 使用 `defaultAppearanceFor(entityId)`（确定性通用人形兜底）。
 */
export function buildCharacterParts(
  appearance: CharacterAppearance | null | undefined,
  context: CharacterStateContext,
): CharacterPart[] {
  const resolved = appearance ?? defaultAppearanceFor(context.entityId);
  // N2-r2 / F-3：形态判定走**显式降级**路径（`states[].mask=true` 而 `appearance.mask`
  // 缺失 ⇒ 生效形态 = daily，并给出结构化告警；**不**渲染无面具的「面具态」、**不**抛异常）。
  const stateId = resolveMaskDegradation(resolved, context).effective_state_id;
  const masked = stateUsesMask(resolved, stateId);
  const rawHeight = fieldValue(resolved.height_cm, BASE_HEIGHT_CM);
  const heightCm = isFiniteNumber(rawHeight) ? Math.min(250, Math.max(60, rawHeight)) : BASE_HEIGHT_CM;
  const scale = heightCm / BASE_HEIGHT_CM;

  const parts: CharacterPart[] = [];
  for (const name of CHARACTER_PART_ORDER) {
    if (name === 'mask' && !masked) continue;
    const spec = PART_TABLE.find((item) => item.part === name);
    if (!spec) continue;
    parts.push({
      entity_id: context.entityId,
      part: spec.part,
      name: spec.part === 'torso' ? context.entityId : `${context.entityId}/${spec.part}`,
      is_root: spec.part === 'torso',
      size: [round6(spec.size[0] * scale), round6(spec.size[1] * scale), round6(spec.size[2] * scale)],
      local_offset: [round6(spec.offset[0] * scale), round6(spec.offset[1] * scale), round6(spec.offset[2] * scale)],
      source_hex: colorForPart(spec, resolved),
    });
  }
  return parts;
}

/** 该实体本帧使用的形态 id（供 `appearanceReport()` 用；与装配同一条判定路径）。 */
export function stateIdFor(appearance: CharacterAppearance | null | undefined, context: CharacterStateContext): string {
  // N2-r2 / F-3：与 `buildCharacterParts` **同一条**降级路径 ⇒ 报告的 `state_id`
  // 与实际装配出的部件集**不会分叉**（此前会报 `masked` 而部件集是 daily）。
  return resolveMaskDegradation(appearance ?? defaultAppearanceFor(context.entityId), context).effective_state_id;
}

/**
 * **只读**外形解析（D1）：`/packs/<packId>/npcs/<npcId>.json`（与 `main.ts` 同一条 URL 约定）。
 * 失败 / 缺 `appearance` / 结构不合法 ⇒ **跳过**（不写入、不伪造）；返回的 Map 只含**真的取到**的条目。
 */
export async function resolveAppearanceTable(input: {
  packId: string;
  npcIds: string[];
  fetchImpl?: typeof fetch;
}): Promise<Map<string, CharacterAppearance>> {
  const table = new Map<string, CharacterAppearance>();
  const fetchImpl = input.fetchImpl ?? (typeof fetch === 'function' ? fetch : undefined);
  if (!fetchImpl) return table;
  for (const npcId of input.npcIds) {
    try {
      const response = await fetchImpl(`/packs/${input.packId}/npcs/${npcId}.json`);
      if (!response || !response.ok) continue;
      const document = (await response.json()) as { appearance?: unknown };
      const appearance = normalizeAppearance(document?.appearance);
      if (appearance) table.set(npcId, appearance);
    } catch {
      // 只读 GET 失败 ⇒ 该实体退回确定性通用人形；**不伪造**具体人物特征
    }
  }
  return table;
}

/** 由**已解析的文档**构造装配表（判据 / 宿主注入用；确定性、零 IO）。 */
export function appearanceTableFromDocuments(
  records: Array<{ npc_id: string; appearance?: unknown }>,
): Map<string, CharacterAppearance> {
  const table = new Map<string, CharacterAppearance>();
  for (const record of records) {
    const appearance = normalizeAppearance(record?.appearance);
    if (appearance) table.set(record.npc_id, appearance);
  }
  return table;
}

/** 结构门：缺 `eyes.color.value` / `height_cm.value` 等必需项 ⇒ `null`（**不补造**）。 */
export function normalizeAppearance(input: unknown): CharacterAppearance | null {
  if (!input || typeof input !== 'object') return null;
  const document = input as Record<string, unknown>;
  const colorOf = (holder: unknown): AppearanceField<string> | undefined => {
    if (!holder || typeof holder !== 'object') return undefined;
    const color = (holder as Record<string, unknown>).color;
    if (!color || typeof color !== 'object') return undefined;
    const value = (color as Record<string, unknown>).value;
    if (typeof value !== 'string' || !HEX_RE.test(value)) return undefined;
    return color as AppearanceField<string>;
  };
  const eyes = colorOf(document.eyes);
  const lips = colorOf(document.lips);
  const skin = colorOf(document.skin);
  const hair = colorOf(document.hair);
  const garment = colorOf(document.garment);
  const height = document.height_cm as AppearanceField<number> | undefined;
  const build = document.build as AppearanceField<string> | undefined;
  if (!eyes || !lips || !skin || !hair || !garment) return null;
  if (!height || !isFiniteNumber(height.value)) return null;
  if (!build || typeof build.value !== 'string') return null;
  const states = Array.isArray(document.states) ? (document.states as CharacterAppearanceState[]) : [];
  const mask = document.mask && typeof document.mask === 'object'
    ? (document.mask as CharacterAppearanceMask) : undefined;
  return {
    eyes: { color: eyes },
    lips: { color: lips },
    skin: { color: skin },
    hair: { color: hair, length: (document.hair as { length?: AppearanceField<string> })?.length },
    garment: { color: garment, cut: (document.garment as { cut?: AppearanceField<string> })?.cut },
    height_cm: height,
    age_look: document.age_look as AppearanceField<string> | undefined,
    build,
    mask,
    states,
  };
}

// ================================================================== N4 / W5：写实解剖部件面
/**
 * **N4 写实解剖部件**（AC-5 的「≥12 部件，含手/脚/发/衣/面部」）。
 *
 * 关键纪律（Raven 预审 R-1，`[实证]`）：N2 契约部件面**逐字冻结** ——
 * `CHARACTER_PART_NAMES` / `PART_TABLE` / `buildCharacterParts()` / `DAILY_PART_COUNT` /
 * `MASKED_PART_COUNT` 一行未改；N4 部件走**独立装配函数** + `world.ts` 的**独立映射**
 * （`detailPartMeshes`），**不进** `partMeshes`。
 * 为什么：`character_parts_fingerprints_recomputable` 比较「装配函数产物」与「mesh 读层回」两侧，
 * 一旦往 `partMeshes` 加部件再靠过滤回 N2 名单，两侧必然不同集 ⇒ 既有判据必红。
 *
 * 几何口径（与 `PART_TABLE` 同一坐标系；角色正面 = **+z**；躯干 = 根 mesh）：
 *   - `neck` 落在**躯干上缘与头下缘之间**（头身分段可读，且不是「头直接坐在肩上」）；
 *   - `hand_l`/`hand_r` 接在**臂的下端**（前臂末端），不再读作「齐腕截断的圆柱」；
 *   - `foot_l`/`foot_r` 接在**腿的下端且低于外衣下摆**（脚落地可读）；
 *   - `nose`/`brow_l`/`brow_r`/`ear_l`/`ear_r` 是**面部特征**（几何表达，REQ 明确
 *     `xuqin-face-01.png` 是正面参考图、不可直接贴 ⇒ 面部特征一律几何 + 材质色）。
 * 全部尺寸/偏移按 `height_cm / BASE_HEIGHT_CM` **等比**缩放（与 N2 同口径，确定性、无随机）。
 */
export const N4_PART_NAMES: readonly string[] = [
  'neck', 'hand_l', 'hand_r', 'foot_l', 'foot_r', 'nose', 'brow_l', 'brow_r', 'ear_l', 'ear_r',
] as const;

/** N4 部件装配顺序（固定；确定性，无遍历顺序依赖）。 */
export const N4_PART_ORDER: readonly string[] = [
  'neck', 'hand_l', 'hand_r', 'foot_l', 'foot_r', 'nose', 'brow_l', 'brow_r', 'ear_l', 'ear_r',
  'pupil_l', 'pupil_r',
] as const;

const DETAIL_TABLE: readonly PartSpec[] = [
  // 颈：躯干上缘 y=0.33 / 头下缘 y=0.34 ⇒ 颈盒 y∈[0.31,0.41] 跨在两段之间
  { part: 'neck', size: [0.14, 0.10, 0.14], offset: [0, 0.36, 0.005], color: 'skin' },
  // 手：臂盒 y∈[−0.12,0.28] ⇒ 手盒上缘贴臂下端 y=−0.12，整体在臂中心之下
  { part: 'hand_l', size: [0.09, 0.14, 0.11], offset: [-0.24, -0.19, 0], color: 'skin' },
  { part: 'hand_r', size: [0.09, 0.14, 0.11], offset: [0.24, -0.19, 0], color: 'skin' },
  // 脚（N4-r2 / M-8 关闭 Sentinel B-10）：原实现 `color='garment'` 与腿/外衣**同色**且仅高 0.10 m
  // ⇒ 画面里读不出「脚」（独立读图判「腿底直接截断落地」）。
  // 第一版只改色锚点（`hair` 近黑）**不够**：近黑 × 红色皮革贴图 = 暗红，与腿的暗红在**亮度上几乎同值**
  // （实测像素：腿 (48,18,20) vs 脚底 (15,2,2)，差别只在亮度渐变 ⇒ 读作「腿往下变暗」而不是「鞋」）。
  // ⇒ 本轮两处一起改：
  //   ① **前伸成鞋头**：深 0.20→0.34、前移到 z=0.10 ⇒ 鞋尖比腿**多伸出 0.17 m**，靠**轮廓**就能读出「鞋」；
  //   ② **去掉红色皮革贴图**（从 `CHARACTER_PART_SURFACE` 移除）⇒ 材质回落到 `healingMaterial(hex)`
  //      的**纯色**中性近黑，不再是「暗红」。
  // 几何约束（`feetAtLegEndsBelowHem`，容差 20 mm）：腿底 −1.12、脚顶 −1.165+0.055=**−1.11**
  //   ⇒ |−1.11 −(−1.12)| = 0.01 ≤ 0.02 ✓；脚底 **−1.22** = `WORLD_FLOOR_Y`（正好踩在世界地面上）。
  { part: 'foot_l', size: [0.17, 0.11, 0.34], offset: [-0.11, -1.165, 0.10], color: 'hair' },
  { part: 'foot_r', size: [0.17, 0.11, 0.34], offset: [0.11, -1.165, 0.10], color: 'hair' },
  // 面部：鼻在瞳/唇之间并前伸（N4-r2 / M-8 关闭 Sentinel B-2：原鼻盒 y∈[0.43,0.52] 与唇盒
  //   y∈[0.4125,0.4475] **几何相交**、且鼻在前 ⇒ 嘴中央被肤色块切出缺口。现鼻盒 y∈[0.45,0.505]，
  //   与唇（上缘 0.4475）**留 2.5 mm 间隙**、与瞳（下缘 0.505）**恰好相接不相交**。）
  // N4-r3 / R3-6：M-8 只保证了「不相交」，**没保证「贴住脸」** —— 原 z∈[0.16,0.21] 整段在头盒
  //   前表面（z=0.145）**之外**，且 y 与 `eyes`（y∈[0.505,0.555]）、与 `lips`（y 上缘 0.4475）
  //   都不重叠 ⇒ 鼻盒**悬空**（与任何主体盒 AABB 交集为零）。现把 z 收回到 `z∈[0.13,0.18]`：
  //   与头盒重叠 15 mm（贴住脸），仍前伸 35 mm。M-8 的「不切唇」结论不变（y 间隙仍是 2.5 mm）。
  { part: 'nose', size: [0.05, 0.055, 0.05], offset: [0, 0.4775, 0.155], color: 'skin' },
  // N4-r3 / R3-6：眉原 z∈[0.158,0.178]、y∈[0.574,0.596] —— y 与 `eyes`（上缘 0.555）不重叠、
  //   z 在头盒之外 ⇒ 同样**悬空**。现 z 收回到 `z∈[0.14,0.16]`（与头盒重叠 5 mm、前伸 15 mm）。
  { part: 'brow_l', size: [0.08, 0.022, 0.02], offset: [-0.06, 0.585, 0.15], color: 'hair' },
  { part: 'brow_r', size: [0.08, 0.022, 0.02], offset: [0.06, 0.585, 0.15], color: 'hair' },
  // 耳（N4-r2 / M-8 关闭 Sentinel B-1）：原耳盒 x∈[±0.14±0.0175]、z∈[−0.03,0.03] 被 `hair`
  //   盒（x∈[−0.25,0.25]、y∈[−0.02,0.68]、z∈[−0.195,0.045]）**逐轴完全包含** ⇒ 任何机位都看不见，
  //   12 个 N4 部件里这 2 个对画面**零贡献**。r2 把耳**前移到 z=0.09**（z∈[0.06,0.12] > 发前表面
  //   0.045）⇒ 逃出发盒 AABB —— 但**跑过头了**：x 留在 ±0.145 ⇒ 内侧面 −0.1275 落在头盒侧面
  //   （−0.12）**之外**，与头盒 AABB **交集为零** ⇒ 耳**悬浮在头旁**（R3-6 点名的新缺陷）。
  //   现把 x 收回到 ±0.125：内侧面 −0.1075 **进入头盒 12.5 mm**（贴住头），外侧面 −0.1425 仍外露
  //   22.5 mm；z 保持 0.09（仍逃出发盒 ⇒ 可见）。「逃出发盒」与「贴住头」两个条件同时成立。
  { part: 'ear_l', size: [0.035, 0.10, 0.06], offset: [-0.125, 0.49, 0.09], color: 'skin' },
  { part: 'ear_r', size: [0.035, 0.10, 0.06], offset: [0.125, 0.49, 0.09], color: 'skin' },
  // 瞳：`eyes` 盒（N2 冻结）x∈[−0.095,0.095]、前表面 z=0.175 ⇒ 瞳贴在其正前方（z∈[0.173,0.181]），
  // 间距 0.045 落在两眼眶位置。颜色借 `hair` 锚点：内容包只提供 skin/hair/garment/eyes/lips/mask
  // 六个锚点，**没有独立虹膜锚点** ⇒ 用「发色（本包近黑）」作瞳孔色，瞳色本体仍由 pack 的 `eyes` 锚点承载。
  { part: 'pupil_l', size: [0.028, 0.028, 0.008], offset: [-0.045, 0.53, 0.177], color: 'hair' },
  { part: 'pupil_r', size: [0.028, 0.028, 0.008], offset: [0.045, 0.53, 0.177], color: 'hair' },
] as const;

/**
 * **N4 写实解剖部件装配器**（纯函数；与 `buildCharacterParts()` 同一确定性口径）。
 * `appearance === null` ⇒ 使用 `defaultAppearanceFor(entityId)`（确定性通用人形兜底）。
 * 与读法**无关**（读法只改光照与材质亮度）。
 */
export function buildCharacterDetailParts(
  appearance: CharacterAppearance | null | undefined,
  context: CharacterStateContext,
): CharacterPart[] {
  const resolved = appearance ?? defaultAppearanceFor(context.entityId);
  const rawHeight = fieldValue(resolved.height_cm, BASE_HEIGHT_CM);
  const heightCm = isFiniteNumber(rawHeight) ? Math.min(250, Math.max(60, rawHeight)) : BASE_HEIGHT_CM;
  const scale = heightCm / BASE_HEIGHT_CM;
  const parts: CharacterPart[] = [];
  for (const name of N4_PART_ORDER) {
    const spec = DETAIL_TABLE.find((item) => item.part === name);
    if (!spec) continue;
    parts.push({
      entity_id: context.entityId,
      part: spec.part,
      name: `${context.entityId}/${spec.part}`,
      is_root: false,
      size: [round6(spec.size[0] * scale), round6(spec.size[1] * scale), round6(spec.size[2] * scale)],
      local_offset: [round6(spec.offset[0] * scale), round6(spec.offset[1] * scale), round6(spec.offset[2] * scale)],
      source_hex: colorForPart(spec, resolved),
    });
  }
  return parts;
}
