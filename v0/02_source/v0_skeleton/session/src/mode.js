/**
 * 双模式权限模型（AC-4）——V0 骨架。
 *
 *   observe     : 只读订阅；上行 intent 一律 rejected: E_MODE_READONLY
 *   participate : 只读订阅 + 意图上行（经 intervention.policy 校验后入队，tick 边界应用）
 */

export const MODES = ['observe', 'participate'];

export function assertMode(mode) {
  if (!MODES.includes(mode)) {
    throw new Error('E_SCHEMA_INVALID: unknown session mode');
  }
  return mode;
}

/** 上行权限判定：返回 null 表示允许，否则返回错误码。 */
export function checkUpstream(mode) {
  return mode === 'observe' ? 'E_MODE_READONLY' : null;
}

/** 下行权限判定：两种模式都可只读订阅（V0 无差异）。 */
export function canSubscribe(mode) {
  assertMode(mode);
  return true;
}
