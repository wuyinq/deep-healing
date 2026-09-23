/**
 * 双模式权限模型（AC-M3-2①）——M3 真实现。
 *
 *   observe     : 只读订阅；**任何**上行 intent 一律 `rejected: E_MODE_READONLY`
 *                 （且必须落 `intent.rejected` 事件 —— 由 `server.js` 经内核入口完成）
 *   participate : 只读订阅 + 意图上行（经 `intervention.policy` 校验后入队，**tick 边界**应用）
 *
 * 硬边界：本模块只做**权限判定**，不持状态、不写世界。模式判定必须发生在**唯一入口**上
 * （`SessionServer.onClientMessage`），不得在任何旁路（录像路径 / 桥 stdin）上被绕过。
 */

export const MODES = ['observe', 'participate'];

export function assertMode(mode) {
  if (!MODES.includes(mode)) {
    throw new Error('E_SCHEMA_INVALID: unknown session mode');
  }
  return mode;
}

/** 上行权限判定：返回 null 表示允许，否则返回**冻结错误码**。 */
export function checkUpstream(mode) {
  assertMode(mode);
  return mode === 'observe' ? 'E_MODE_READONLY' : null;
}

/** 会话是否可写（observe ⇒ false）。任何写路径都必须先过这里。 */
export function isWritable(mode) {
  return checkUpstream(mode) === null;
}

/** 下行权限判定：两种模式都可只读订阅（V0 无差异）。 */
export function canSubscribe(mode) {
  assertMode(mode);
  return true;
}
