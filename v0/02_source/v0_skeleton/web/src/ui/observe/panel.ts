/**
 * 观察模式 UI（AC-11）——V0 骨架。
 * 世界视图 + 事件流/字幕 + NPC 档案（脱敏）+ 时间轴 scrubber + 指标面板。
 * **无任何写入口**。
 */

export class ObservePanel {
  readonly root: HTMLElement;

  constructor(host: HTMLElement) {
    this.root = host;
  }

  apply(message: { t: string; tick: number; [key: string]: unknown }): void {
    // V0 骨架：tick 显示 / 事件流追加 / 指标更新，实现见 08_v0_plan.md。
  }

  renderEventStream(events: Array<Record<string, unknown>>): void {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-ui-observe")');
  }

  renderTimeline(checkpoints: Array<{ tick: number; state_hash: string }>): void {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-ui-observe")');
  }

  renderMetrics(metrics: { tick: number; ms: number; tokens_est: number; cost_usd: number }): void {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-ui-observe")');
  }

  /** NPC 档案必须脱敏：不显示玩家原文、不显示内部 trauma 原始数值（只显示可公开的标签）。 */
  renderNpcProfile(profile: Record<string, unknown>): void {
    throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-ui-observe")');
  }
}
