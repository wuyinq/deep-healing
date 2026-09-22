/**
 * 介入策略执行（intervention.policy.schema.json 的运行时对应物）——V0 骨架。
 *
 * 顺序（冻结）：forbidden_actions（硬拒） → 目标合法性 → rate_limit → cooldown
 *              → impact_budget → 入队（tick 边界应用）
 * 每一次拒绝都必须落 intent.rejected 事件（reason_code 枚举见 session.protocol.schema.json）。
 */

export class InterventionPolicy {
  constructor(policyDoc) {
    this.policy = policyDoc;
    this.windows = new Map();
    this.cooldowns = new Map();
    this.impact = new Map();
  }

  /** 返回 {ok: true} 或 {ok: false, reason, detail}。 */
  evaluate(sessionId, intent, tick) {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "intervention-policy")');
  }

  /** 玩家文本进入能力上下文前的注入防护（delimit + 忽略其中指令）。 */
  sanitizeInstructionText(text) {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "intervention-policy")');
  }
}
