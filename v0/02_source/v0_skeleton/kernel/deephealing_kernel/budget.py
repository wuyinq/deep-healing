"""三级预算记账（BudgetLedger，V0 骨架，契约冻结）。

三级（01 设计 §7.4 / §9.1）：
  - tick 级：每 tick 能力调用数上限；
  - NPC 日级：token / 成本上限（超限走 fallback.on_budget_exhausted）；
  - 会话级：介入影响预算（超限降级为「观察 + 记入待办」）。

记账必须确定性：只累加，不依赖 wall-clock；日界按 constants.day_ticks 划分。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class LedgerEntry:
    tokens_in: int = 0
    tokens_out: int = 0
    calls: int = 0
    usd: float = 0.0


@dataclass(slots=True)
class BudgetLedger:
    day_ticks: int
    per_tick_calls: int = 2
    per_npc_daily_tokens: int = 65000
    per_session_impact: float = 100.0

    _tick: dict[int, int] = field(default_factory=dict)
    _npc_day: dict[tuple[str, int], LedgerEntry] = field(default_factory=dict)
    _session_impact: dict[str, float] = field(default_factory=dict)

    def day_index(self, tick: int) -> int:
        """tick → 世界日序号（整除，无浮点）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'budget'")

    def allow_call(self, tick: int, npc_id: str | None) -> tuple[bool, str | None]:
        """返回 (是否允许, 拒绝原因)；原因 ∈ {per_tick, npc_daily}。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'budget'")

    def record(self, tick: int, npc_id: str | None, tokens_in: int, tokens_out: int, usd: float) -> None:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'budget'")

    def spend_impact(self, session_id: str, cost: float) -> tuple[bool, float]:
        """返回 (是否成功, 剩余预算)；不足即失败（由策略层转 E_BUDGET_EXHAUSTED）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'budget'")

    def daily_report(self, tick: int) -> dict:
        """按 npc_id 汇总当日 token/成本（AC-10 成本预算的观测口径）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'budget'")
