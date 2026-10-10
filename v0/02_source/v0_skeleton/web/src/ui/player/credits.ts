/**
 * 分发可见面 · 署名（credits）—— N5 阶段 C / `AC-G` G-1（PM 裁决 `.pm_ruling-n5b-block-issues.md` §1 第 3 条）。
 *
 * 为什么必须在这里（**分发可见面**）：
 *   署名 / 限制说明的义务**随分发发生** —— `provenance.json` 里的登记只是**来源登记**，
 *   分发物（页面 / 构建产物）本身必须**带着**它。因此本模块把必须标注的条目渲染进
 *   **玩家界面根**（`#player-ui`，与 `#hud` 开发观察面板分离）⇒ 随页可见，并随构建产物携带。
 *
 * 当前条目 = 徐琴角色资产（`xuqin_body_3dgen_24k`）：AI 图生3D，**许可状态：未证实**
 *   （`license = "unknown"` + `license_url = null`）⇒ 除署名外**必须**同时带商用限制说明
 *   （`notice`），且**不得**被读作「许可已证实 / 已获授权」。
 *
 * 硬边界：
 *   - **不是**新表面 / 不改任何既有 DOM 结构（只在 `#player-ui` 内**新增**一个节点）；
 *   - 不写任何 assets URL / 不联网；条目是**声明**，其真实性由 `scene_assert.mjs` 的
 *     `credits_attribution_matches_provenance`（与 `web/assets/provenance.json` 逐字比对）
 *     与真浏览器读数各自承担。
 *
 * ⚠️ 本模块**不**自证「已对用户可见」：可见性由真浏览器（playwright，1440×900 / 390×844）读数给出。
 */

/** 署名条目的**权威来源**（逐字比对的对方；`provenance.json` 是唯一来源登记面）。 */
export const CREDITS_SOURCE_OF_TRUTH = 'web/assets/provenance.json';

/** 署名面在页面里的 DOM id（playwright 取数键）。 */
export const CREDITS_ID = 'credits';

/**
 * 徐琴角色资产的署名串 —— **逐字**取自 `web/assets/provenance.json` 的
 * `assets[asset_id=xuqin_body_3dgen_24k].attribution`（机械抽取，非手抄）。
 *
 * 为什么写成顶层字面量而不是 `import provenance from '../../assets/provenance.json'`：
 *   ① 分发物的字节锚需要它**在构建产物里**（Vite 会把字面量原样放进 JS chunk）；
 *   ② 判据只接受「字面量」或「被属性引用的**顶层** `const` 字面量」两种形态；
 *   ③ 与来源登记面的**一致性**由判据 `credits_attribution_matches_provenance` 承担
 *      （读 `provenance.json` 逐字比对 + 负对照），而不是靠 import 的隐式耦合。
 */
export const XUQIN_ATTRIBUTION = '徐琴角色 GLB：AI 图生3D（火山方舟 Ark / 影眸 Hyper3D Gen-2，model hyper3d-gen2-260112）→ 本地 Blender 26 骨绑定 + 24k 减面 + 2K 贴图。许可状态：未证实';

/**
 * 商用限制说明 —— 与冻结判据 `scene_assert.mjs` 的 `RESTRICTION_NOTICE` **逐字**一致
 * （机械抽取，非手抄）。`license = "unknown"` + 供应商条款义务 ⇒ 该说明与署名**同时**必需。
 */
export const RESTRICTION_NOTICE = '商用分发前须取得供应商（影眸科技 / 火山引擎方舟）书面许可';

export interface CreditsEntry {
  /** `provenance.json` 的 `asset_id`（可读别名）。 */
  asset_id: string;
  /** 许可枚举（与 `provenance.json` 的 `license` 逐字一致）。 */
  license: string;
  /** 许可 URL；**未知许可为 `null`**（不得用空串冒充）。 */
  license_url: string | null;
  /** 署名串（**逐字**与 `provenance.json` 的 `attribution` 一致）。 */
  attribution: string;
  /** 商用限制说明（纯加法字段；缺它 = 失实，判据的 `notice` 合取项会红）。 */
  notice?: string;
}

/**
 * 必须署名的条目表（当前 = `provenance.json` 里**承担署名 / 标注义务**的条目）。
 * 无署名义务的条目**不在此表**，也不得因此被读成「已署名」。
 */
export const CREDITS_ENTRIES: readonly CreditsEntry[] = Object.freeze([
  {
    asset_id: 'xuqin_body_3dgen_24k',
    license: 'unknown',
    license_url: null,
    attribution: XUQIN_ATTRIBUTION,
    notice: RESTRICTION_NOTICE,
  },
]);

export interface CreditsReport {
  id: string;
  mounted: boolean;
  text: string;
  attribution: string;
  notice: string;
  entries: number;
  source_of_truth: string;
  /** 真浏览器读回（Node 侧为 null；不伪造）。 */
  rect: { x: number; y: number; width: number; height: number } | null;
  display: string | null;
  visibility: string | null;
  /** 是否落在当前视口内（真浏览器读数）。 */
  within_viewport: boolean | null;
}

/** 渲染一条条目（纯 DOM，无框架、无网络）：署名与限制说明**两个 span 都进 `#credits` 子树**。 */
function renderEntry(doc: Document, entry: CreditsEntry): HTMLElement {
  const line = doc.createElement('div');
  line.className = 'credits-entry';
  line.dataset.assetId = entry.asset_id;
  line.dataset.license = entry.license;
  const text = doc.createElement('span');
  text.className = 'credits-attribution';
  text.textContent = entry.attribution;
  line.append(text);
  const notice = doc.createElement('span');
  notice.className = 'credits-notice';
  notice.textContent = entry.notice ?? '';
  line.append(notice);
  return line;
}

/**
 * 把署名挂进**玩家界面根**（`#player-ui`）。
 *
 * 取不到根 ⇒ **抛**（`E_CREDITS_ROOT_MISSING`）—— 与 `player_ui.ts` 同向：
 * 不回退到别处，避免「签不上却又绿」。已存在同 id 节点 ⇒ 复用（幂等，不重复插入）。
 */
export function mountCredits(doc: Document = document): { element: HTMLElement; entries: readonly CreditsEntry[] } {
  const root = doc.getElementById('player-ui');
  if (!root) throw new Error('E_CREDITS_ROOT_MISSING: #player-ui');
  let element = doc.getElementById(CREDITS_ID);
  if (!element) {
    element = doc.createElement('div');
    element.id = CREDITS_ID;
    element.className = 'credits';
    element.setAttribute('role', 'contentinfo');
    element.setAttribute('aria-label', '素材署名');
    const title = doc.createElement('div');
    title.className = 'credits-title';
    title.textContent = '素材署名';
    element.append(title);
    root.append(element);
  }
  for (const entry of CREDITS_ENTRIES) element.append(renderEntry(doc, entry));
  return { element, entries: CREDITS_ENTRIES };
}

/** 页内读数（真浏览器断言与 `__deephealing.creditsReport()` 共用同一个取数定义）。 */
export function creditsReport(doc: Document = document): CreditsReport {
  const element = doc.getElementById(CREDITS_ID);
  const text = element?.textContent ?? '';
  const window_ = doc.defaultView;
  let rect: CreditsReport['rect'] = null;
  let display: string | null = null;
  let visibility: string | null = null;
  let within: boolean | null = null;
  if (element && window_) {
    const box = element.getBoundingClientRect();
    const style = window_.getComputedStyle(element);
    display = style.display;
    visibility = style.visibility;
    rect = { x: box.x, y: box.y, width: box.width, height: box.height };
    within = box.width > 0 && box.height > 0 && box.x >= 0 && box.y >= 0
      && box.x + box.width <= window_.innerWidth && box.y + box.height <= window_.innerHeight;
  }
  return {
    id: CREDITS_ID,
    mounted: element !== null,
    text,
    attribution: XUQIN_ATTRIBUTION,
    notice: RESTRICTION_NOTICE,
    entries: CREDITS_ENTRIES.length,
    source_of_truth: CREDITS_SOURCE_OF_TRUTH,
    rect,
    display,
    visibility,
    within_viewport: within,
  };
}
