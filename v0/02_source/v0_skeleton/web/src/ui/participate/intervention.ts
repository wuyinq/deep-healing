/**
 * 参与模式 UI（AC-M3-2 / AC-M3-5）——M3 真实现。
 *
 * 观察模式全部 + 介入通道面板（委托指令输入 / 影响预算剩余 / 冷却指示 / **被拒原因回显**）
 * + 任务状态演进视图（谁因何变化：`task.state_changed` 的 `caused_by` / `rule_id` / `shift_index`）。
 *
 * 硬边界：本面板**不是**权限判定点 —— 它只是把意图交给 `RenderClient.submitIntent`；
 * 真正的判定在会话层唯一入口与内核入口。observe 模式下本面板**不挂载**写控件。
 */

export class InterventionPanel {
  private input: HTMLInputElement | null = null;
  private button: HTMLButtonElement | null = null;
  private status: HTMLElement | null = null;
  private evolution: HTMLElement | null = null;
  private budget: HTMLElement | null = null;

  constructor(
    private readonly host: HTMLElement,
    private readonly client: {
      submitIntent(intent: Record<string, unknown>): Promise<{ status: string; reason?: string }>;
      mode?: string;
    },
  ) {}

  /** 只有 participate 模式才挂载写控件（观察模式的 UI 树里**不存在**写入口）。 */
  mount(): void {
    if (this.client.mode === 'observe') return;
    if (this.input) return;
    this.input = document.createElement('input');
    this.input.id = 'delegate-instruction';
    this.input.placeholder = '委托一句话（例如：把晚饭送到 1-101 门口）';
    this.button = document.createElement('button');
    this.button.id = 'submit-delegate';
    this.button.type = 'button';
    this.button.textContent = '委托';
    this.button.addEventListener('click', () => {
      void this.submitDelegateInstruction('npc-001', this.input?.value ?? '', 0.5);
    });
    this.status = document.createElement('div');
    this.status.id = 'intent-status';
    this.evolution = document.createElement('div');
    this.evolution.id = 'task-evolution';
    this.budget = document.createElement('div');
    this.budget.id = 'impact-budget';
    this.host.append(this.input, this.button, this.status, this.budget, this.evolution);
  }

  /** 提交委托指令；被拒必须回显 reason（E_MODE_READONLY / E_RATE_LIMITED / E_COOLDOWN / E_BUDGET_EXHAUSTED）。 */
  async submitDelegateInstruction(target: string, text: string, urgency: number): Promise<void> {
    const result = await this.client.submitIntent({
      id: `ui-${Date.now()}`,
      kind: 'delegate_instruction',
      target,
      payload: { instruction_text: text, urgency },
    });
    this.renderAck(result);
  }

  renderAck(result: { status: string; reason?: string }): void {
    if (this.status) {
      this.status.dataset.status = result.status;
      this.status.dataset.reason = result.reason ?? '';
      this.status.textContent = result.reason ? `${result.status}: ${result.reason}` : result.status;
    }
  }

  /** 任务演进视图：谁因何变化（`task.state_changed` 的 caused_by / rule_id / shift_index）。 */
  renderTaskEvolution(changes: Array<Record<string, unknown>>): void {
    if (!this.evolution) return;
    for (const change of changes) {
      const item = document.createElement('div');
      item.className = 'task-change';
      item.dataset.taskId = String(change.task_id ?? '');
      item.dataset.ruleId = String(change.rule_id ?? '');
      item.textContent = `${change.task_id} ${change.from_state} → ${change.to_state} (rule=${change.rule_id} shift=${change.shift_index} by=${change.caused_by})`;
      this.evolution.append(item);
    }
  }

  renderBudget(remaining: number, cooldownMs: number): void {
    if (!this.budget) return;
    this.budget.dataset.remaining = String(remaining);
    this.budget.textContent = `影响预算 ${remaining} · 冷却 ${cooldownMs}ms`;
  }
}
