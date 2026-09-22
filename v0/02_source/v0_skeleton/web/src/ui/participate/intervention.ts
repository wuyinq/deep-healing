/**
 * 参与模式 UI（AC-4 / AC-11）——V0 骨架。
 * 观察模式全部 + 介入通道面板（委托指令输入 / 影响预算剩余 / 冷却指示 / 被拒原因回显）
 * + 任务状态演进视图（谁因何变化）。
 */

export class InterventionPanel {
  constructor(
    private readonly host: HTMLElement,
    private readonly client: { submitIntent(intent: Record<string, unknown>): Promise<{ status: string; reason?: string }> },
  ) {}

  mount(): void {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-ui-participate")');
  }

  /** 提交委托指令；被拒必须回显 reason（E_MODE_READONLY / E_RATE_LIMITED / E_COOLDOWN / E_BUDGET_EXHAUSTED）。 */
  async submitDelegateInstruction(target: string, text: string, urgency: number): Promise<void> {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-ui-participate")');
  }

  /** 任务演进视图：谁因何变化（task.state_changed 的 caused_by / rule_id）。 */
  renderTaskEvolution(changes: Array<Record<string, unknown>>): void {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-ui-participate")');
  }

  renderBudget(remaining: number, cooldownMs: number): void {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-ui-participate")');
  }
}
