/**
 * 介入策略执行（`intervention.policy.schema.json` 的运行时对应物）——M3 真实现。
 *
 * 顺序（**冻结**，与 `policy.js` 的旧骨架注释一致）：
 *   forbidden_actions（硬拒） → 目标合法性 → rate_limit → cooldown → impact_budget → 入队
 * 每一次拒绝都必须落 `intent.rejected` 事件（reason_code 取自 `session.protocol.schema.json`
 * 的冻结枚举）；拒绝**不**入队、**不**改世界状态。
 *
 * `DEFAULT_POLICY` 是 `intervention.policy.schema.json` 的**契约实例**（不是第二把尺子）：
 * 它由 `spikes/s12-session/validate-protocol.mjs` 用真 schema 校验（引擎 jsonschema）。
 * `impact_budget.cost_table.delegate_instruction` 与 pack 的 `adaptation_rules[].impact_cost`
 * 同值 ⇒ 「影响成本」在会话预算与任务演进两侧**联动**。
 *
 * 时间来源是**注入**的 `clock()`（默认 `Date.now`）：限流/冷却的判定必须可测、可复现。
 */

export const DEFAULT_POLICY = {
  schema_version: '1.0.0',
  scope: {
    mode: 'participate',
    allowed_kinds: ['delegate_instruction'],
    target_kinds: ['npc', 'prop', 'room', 'zone'],
    max_targets_per_intent: 1,
    instruction_text_max_chars: 1000,
    player_text_policy: 'delimit_and_ignore_instructions',
  },
  rate_limit: {
    window_ms: 10000,
    max_intents: 6,
    per_target_max_intents: 2,
    duplicate_merge_window_ms: 3000,
  },
  cooldown_ms: {
    per_target_ms: 5000,
    global_ms: 1000,
  },
  impact_budget: {
    per_session: 100,
    per_window: 20,
    window_ticks: 3000,
    cost_table: {
      delegate_instruction: 3.0,
    },
    on_exhausted: 'observe_and_drop_queued',
  },
  forbidden_actions: [
    {
      id: 'forbid-trauma-write',
      match: { field: 'kind', prefix: 'rewrite_trauma' },
      reason: '不得直接改写 trauma_flags（治愈向硬约束）',
    },
    {
      id: 'forbid-skip-grade',
      match: { field: 'kind', prefix: 'skip_grade' },
      reason: '不得跳过任务分级',
    },
    {
      id: 'forbid-harmful-content',
      match: { field: 'kind', prefix: 'harm_' },
      reason: '不得产出伤害/猎奇向内容',
    },
  ],
  task_adaptation_guards: {
    max_shifts_per_task: 3,
    require_rule_id: true,
    rollback_to_snapshot_allowed: true,
    hard_constraints: [
      '不得直接改写 npc-001 的 trauma_flags',
      '不得跳过 offered 直接进入 settled',
      '不得产出伤害/猎奇向内容',
    ],
  },
  audit: {
    log_events: ['intent.applied', 'intent.rejected', 'task.state_changed'],
    fields: ['intent_id', 'session_id', 'kind', 'target', 'impact_cost', 'reason_code', 'rule_id'],
    retention_ticks: 3000,
    redact: ['token', 'authorization', 'headers.Authorization'],
    player_text_storage: 'digest_only',
  },
};

function matchForbidden(rule, intent) {
  const match = rule.match || {};
  const value = match.field ? intent[match.field] : undefined;
  if (match.equals !== undefined) return value === match.equals;
  if (match.prefix !== undefined) return typeof value === 'string' && value.startsWith(match.prefix);
  if (match.regex !== undefined) {
    try {
      return new RegExp(match.regex).test(String(value ?? ''));
    } catch {
      return false;
    }
  }
  return false;
}

export class InterventionPolicy {
  constructor(policyDoc = DEFAULT_POLICY, { clock = () => Date.now() } = {}) {
    this.policy = policyDoc;
    this.clock = clock;
    this.windows = new Map(); // session_id -> [{ms, target}]
    this.cooldowns = new Map(); // session_id -> {globalMs, targets: Map}
    this.impact = new Map(); // session_id -> 已消耗影响预算
    // session_id -> Map(intent_id -> {ms, target, pending})：重复 id 合并窗口（R2 / F10 / R3 / G5）
    // `pending` = 该意图**仍在会话队列里**（tick 边界出队 / 降级作废时置 false）。
    // 合并只对「仍在队列」的同 id **同 target** 生效 ⇒ 不会产生「已 ack 为 queued 却永不应用」。
    this.pendingIds = new Map();
  }

  remainingBudget(sessionId) {
    const spent = this.impact.get(sessionId) ?? 0;
    return Math.max(0, Number(this.policy.impact_budget.per_session) - spent);
  }

  /** 返回 {ok:true, impactCost} 或 {ok:false, reason, detail, downgradeToObserve?}。 */
  evaluate(sessionId, intent, tick) {
    const nowMs = this.clock();

    // ① forbidden_actions（硬拒，不进入队列）
    for (const rule of this.policy.forbidden_actions) {
      if (matchForbidden(rule, intent)) {
        return { ok: false, reason: 'E_FORBIDDEN_ACTION', detail: `${rule.id}: ${rule.reason}` };
      }
    }

    // ② 目标合法性（V0：必须有 target，且**数量**受 scope.max_targets_per_intent 约束）
    //    R2 / F10：`max_targets_per_intent` 必须有**消费者**（此前只在契约里声明、无人读）。
    const targets = Array.isArray(intent.targets) ? intent.targets : [intent.target];
    const target = targets[0];
    if (typeof target !== 'string' || target.length === 0) {
      return { ok: false, reason: 'E_TARGET_UNKNOWN', detail: 'intent.target is required' };
    }
    const maxTargets = Number(this.policy.scope.max_targets_per_intent ?? 1);
    if (targets.length > maxTargets) {
      return {
        ok: false, reason: 'E_TARGET_UNKNOWN',
        detail: `intent declares ${targets.length} targets > scope.max_targets_per_intent=${maxTargets}`,
      };
    }

    // ②b **重复 id 合并窗口**（R2 / F10；R3 / G5 修正）。
    //     合并的三个必要条件（缺一不可）：
    //       ① 同会话、**同 id**；② 距上次提交 < `duplicate_merge_window_ms`；
    //       ③ **被合并的那一条仍在队列里**（`pending === true`）且 **target 相同**。
    //     为什么必须加 ③（Raven r2 R2-M5）：此前的合并只看「同 id + 窗口内」，
    //     被合并对象**已离开队列**（已被 tick 边界应用 / 已被降级作废）时仍回
    //     `queued + merged`，但队列里没有条目 ⇒ 客户端拿到「已受理」而它永不生效。
    //     现在：离开队列或 target 不同 ⇒ **不合并**，按**新意图**走完整校验并**入队**。
    const mergeWindowMs = Number(this.policy.rate_limit.duplicate_merge_window_ms ?? 0);
    const seenIds = this.pendingIds.get(sessionId) ?? new Map();
    const previous = seenIds.get(String(intent.id ?? ''));
    if (mergeWindowMs > 0 && previous !== undefined && previous.pending === true
        && previous.target === target && nowMs - previous.ms < mergeWindowMs) {
      return {
        ok: true, impactCost: 0, merged: true, mergedInto: String(intent.id),
        detail: `merged: duplicate intent id within duplicate_merge_window_ms=${mergeWindowMs} (target=${target}, still queued)`,
      };
    }

    // ③ rate_limit（滑动窗口；全局 + 每目标）
    const window = this.windows.get(sessionId) ?? [];
    const fresh = window.filter((entry) => nowMs - entry.ms < this.policy.rate_limit.window_ms);
    if (fresh.length >= this.policy.rate_limit.max_intents) {
      this.windows.set(sessionId, fresh);
      return { ok: false, reason: 'E_RATE_LIMITED', detail: `window max_intents=${this.policy.rate_limit.max_intents}` };
    }
    const perTarget = fresh.filter((entry) => entry.target === target).length;
    if (perTarget >= this.policy.rate_limit.per_target_max_intents) {
      this.windows.set(sessionId, fresh);
      return {
        ok: false,
        reason: 'E_RATE_LIMITED',
        detail: `per_target_max_intents=${this.policy.rate_limit.per_target_max_intents} for ${target}`,
      };
    }

    // ④ cooldown（全局 + 每目标）。**初值 = 从未发生过**（-Infinity）：若用 0，
    // 会话建立后的第一毫秒内任何介入都会被误判成「冷却中」。
    const cooldown = this.cooldowns.get(sessionId) ?? { globalMs: Number.NEGATIVE_INFINITY, targets: new Map() };
    if (nowMs - cooldown.globalMs < this.policy.cooldown_ms.global_ms) {
      return { ok: false, reason: 'E_COOLDOWN', detail: `global_ms=${this.policy.cooldown_ms.global_ms}` };
    }
    const targetMs = cooldown.targets.get(target) ?? Number.NEGATIVE_INFINITY;
    if (nowMs - targetMs < this.policy.cooldown_ms.per_target_ms) {
      return {
        ok: false,
        reason: 'E_COOLDOWN',
        detail: `per_target_ms=${this.policy.cooldown_ms.per_target_ms} for ${target}`,
      };
    }

    // ⑤ impact_budget（耗尽 ⇒ 降级为 observe + 记入待办）
    const cost = Number(this.policy.impact_budget.cost_table[intent.kind] ?? 0);
    const remaining = this.remainingBudget(sessionId);
    if (cost > remaining) {
      return {
        ok: false,
        reason: 'E_BUDGET_EXHAUSTED',
        detail: `cost=${cost} remaining=${remaining}`,
        downgradeToObserve: this.policy.impact_budget.on_exhausted === 'observe_and_drop_queued',
      };
    }

    // ⑥ 入队（tick 边界应用）；只有通过全部校验才记账
    fresh.push({ ms: nowMs, target });
    this.windows.set(sessionId, fresh);
    cooldown.globalMs = nowMs;
    cooldown.targets.set(target, nowMs);
    this.cooldowns.set(sessionId, cooldown);
    this.impact.set(sessionId, (this.impact.get(sessionId) ?? 0) + cost);
    // 重复 id 合并窗口的登记点（R2 / F10；R3 / G5：带 target + `pending` 归属）
    seenIds.set(String(intent.id ?? ''), { ms: nowMs, target, pending: true });
    this.pendingIds.set(sessionId, seenIds);
    return { ok: true, impactCost: cost };
  }

  /**
   * **出队登记**（R3 / G5）：意图离开会话队列（tick 边界应用 / 降级作废）时调用。
   * 只有 `pending === true` 的同 id **同 target** 才允许合并 ⇒ 本方法是「已受理」这句话的
   * 前提条件维护点。调用方：`server.js` 的 `onTickBoundary` 与 `downgradeToObserve`。
   */
  markIntentLeavesQueue(sessionId, intentId) {
    const seenIds = this.pendingIds.get(sessionId);
    if (!seenIds) return false;
    const entry = seenIds.get(String(intentId ?? ''));
    if (!entry) return false;
    entry.pending = false;
    return true;
  }

  /** 仍在队列里的（合并窗口内的）意图数 —— 判据用（G5：`pending_intent_count() ≥ 1` 或 ack ≠ queued）。 */
  pendingMergeCount(sessionId) {
    const seenIds = this.pendingIds.get(sessionId);
    if (!seenIds) return 0;
    let count = 0;
    for (const entry of seenIds.values()) if (entry.pending === true) count += 1;
    return count;
  }

  /** 玩家文本进入能力上下文前的注入防护（delimit + 忽略其中指令）。 */
  sanitizeInstructionText(text) {
    if (typeof text !== 'string') return '';
    const max = Number(this.policy.scope.instruction_text_max_chars ?? 1000);
    // 去掉控制字符（含换行/转义），再按契约截断；**不做**语义改写（文本是玩家可控输入，只做隔离与限长）
    const cleaned = text.replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, max);
    return `<<PLAYER_TEXT_NOT_INSTRUCTIONS>>${cleaned}<<END_PLAYER_TEXT>>`;
  }

  /** 玩家原文**只留 digest**（`audit.player_text_storage = digest_only`）。 */
  static digest(text) {
    const cleaned = String(text ?? '');
    let hash = 0x811c9dc5;
    for (let index = 0; index < cleaned.length; index += 1) {
      hash ^= cleaned.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16).padStart(8, '0').repeat(8);
  }
}
