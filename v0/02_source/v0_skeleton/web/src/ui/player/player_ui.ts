/**
 * 玩家界面根（N5 / A4 · `AC-H-2`）—— **硬边界：不得内嵌于 `#hud`**。
 *
 * 用户 §一.6 原文：「HUD 先满足真实交互，并将**玩家界面与开发观察面板分开**」。
 * 既有实现把玩家控件 `#intervention-host` 挂在 `#hud` 内部（`main.ts` 的
 * `document.getElementById('intervention-host') ?? hud` 回退），于是「界面分离」可以**绿而未分离**。
 *
 * 本模块把玩家界面收口到**唯一**根（`#player-ui` → `#intervention-host` 子树）：
 *   - 玩家界面集合 = `#intervention-host` 子树（本根之下）；
 *   - 开发观察面板集合 = `#hud` 子树；
 *   - 两者**元素集合交集必须为空** ⇒ 由 `AC-H-2` 的 playwright 断言核。
 *
 * 取不到根 ⇒ **抛**（`E_PLAYER_UI_ROOT_MISSING`）。**禁止**回退到 `#hud`
 * —— 回退会把「分离」重新变成不可判（正是本轮要堵的口子）。
 */

export const PLAYER_UI_ROOT_ID = 'player-ui';
export const PLAYER_INTERVENTION_HOST_ID = 'intervention-host';
export const DEV_PANEL_ROOT_ID = 'hud';

export interface PlayerUi {
  /** 玩家界面根（`#player-ui`）。 */
  root: HTMLElement;
  /** 玩家控件宿主（`#intervention-host`）；`InterventionPanel` 挂在这里。 */
  interventionHost: HTMLElement;
  /** 该根下的全部元素（`AC-H-2` 的集合读数用；**不含**自身）。 */
  elements(): Element[];
}

/** 取玩家界面根；缺任一节点 ⇒ 抛（**不**回退 `#hud`）。 */
export function createPlayerUi(doc: Document = document): PlayerUi {
  const root = doc.getElementById(PLAYER_UI_ROOT_ID);
  if (!root) throw new Error('E_PLAYER_UI_ROOT_MISSING: #player-ui');
  const interventionHost = doc.getElementById(PLAYER_INTERVENTION_HOST_ID);
  if (!interventionHost) throw new Error(`E_PLAYER_UI_ROOT_MISSING: #${PLAYER_INTERVENTION_HOST_ID}`);
  // 结构性前置：玩家界面根**不得**在 `#hud` 子树内（否则「分离」不成立）。
  const devRoot = doc.getElementById(DEV_PANEL_ROOT_ID);
  if (devRoot && devRoot.contains(root)) {
    throw new Error('E_PLAYER_UI_NOT_SEPARATED: #player-ui 仍在 #hud 子树内');
  }
  if (!root.contains(interventionHost)) {
    throw new Error('E_PLAYER_UI_NOT_SEPARATED: #intervention-host 不在 #player-ui 子树内');
  }
  return {
    root,
    interventionHost,
    elements: () => [...root.querySelectorAll('*')],
  };
}

/** 集合读数（`AC-H-2` 的交集判据的取数面；playwright 侧同样调这个定义）。 */
export function uiSetIntersection(doc: Document = document): { player: string[]; dev: string[]; intersection: string[] } {
  const playerRoot = doc.getElementById(PLAYER_UI_ROOT_ID);
  const devRoot = doc.getElementById(DEV_PANEL_ROOT_ID);
  const ids = (el: Element | null) => (el ? [...el.querySelectorAll('*')].map((n) => n.id).filter(Boolean) : []);
  const player = ids(playerRoot);
  const dev = ids(devRoot);
  const devSet = new Set(dev);
  return { player, dev, intersection: player.filter((id) => devSet.has(id)) };
}
