"""三级预算记账（BudgetLedger，V0-M2 实现，契约冻结）。

三级（01 设计 §7.4 / §9.1）：
  - tick 级：每 tick 能力调用数上限；
  - NPC 日级：token / 成本上限（超限走 fallback.on_budget_exhausted）；
  - 会话级：介入影响预算（超限降级为「观察 + 记入待办」）。

记账必须确定性：只累加，不依赖 wall-clock；日界按 constants.day_ticks 划分。

**M2 语义（D-0.9，只钉语义不钉毫秒数）**：
  1. 超 tick 上限 → `fallback.on_budget_exhausted`（`allow_call` 返回 `(False, "per_tick")`）；
  2. 超日 token → **降级到 `deterministic_rule`**（由注册表按 fallback 链执行，
     `allow_call` 返回 `(False, "npc_daily")`）——不是报错、不是静默回填；
  3. `spend_impact` 耗尽 → `(False, 剩余)`，由策略层转 `E_BUDGET_EXHAUSTED`；
  4. 超时 → **确定性降级**（注册表侧；同输入同 seed ⇒ 同降级路径），降级事件进 `journal`；
  5. **本文件零毫秒常量**：能力超时值一律取自 `capabilities/*.capability.json` 的声明值。
"""

from __future__ import annotations

from dataclasses import dataclass, field

EXHAUSTED_REASON = "E_BUDGET_EXHAUSTED"


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
        span = int(self.day_ticks)
        if span <= 0:
            return 0
        return int(tick) // span

    def allow_call(self, tick: int, npc_id: str | None) -> tuple[bool, str | None]:
        """返回 (是否允许, 拒绝原因)；原因 ∈ {per_tick, npc_daily}。"""
        tick = int(tick)
        if self._tick.get(tick, 0) >= int(self.per_tick_calls):
            return False, "per_tick"
        if npc_id:
            entry = self._npc_day.get((str(npc_id), self.day_index(tick)))
            if entry is not None and (entry.tokens_in + entry.tokens_out) >= int(self.per_npc_daily_tokens):
                return False, "npc_daily"
        return True, None

    def record(self, tick: int, npc_id: str | None, tokens_in: int, tokens_out: int, usd: float) -> None:
        tick = int(tick)
        self._tick[tick] = self._tick.get(tick, 0) + 1
        if not npc_id:
            return
        key = (str(npc_id), self.day_index(tick))
        entry = self._npc_day.get(key)
        if entry is None:
            entry = LedgerEntry()
            self._npc_day[key] = entry
        entry.tokens_in += int(tokens_in)
        entry.tokens_out += int(tokens_out)
        entry.calls += 1
        entry.usd = round(entry.usd + float(usd), 6)

    def spend_impact(self, session_id: str, cost: float) -> tuple[bool, float]:
        """返回 (是否成功, 剩余预算)；不足即失败（由策略层转 E_BUDGET_EXHAUSTED）。"""
        session = str(session_id)
        spent = float(self._session_impact.get(session, 0.0))
        remaining = round(float(self.per_session_impact) - spent, 6)
        amount = float(cost)
        if amount > remaining:
            return False, remaining
        self._session_impact[session] = round(spent + amount, 6)
        return True, round(remaining - amount, 6)

    def daily_report(self, tick: int) -> dict:
        """按 npc_id 汇总当日 token/成本（AC-10 成本预算的观测口径）。"""
        day = self.day_index(tick)
        report: dict[str, dict] = {}
        for (npc_id, entry_day) in sorted(self._npc_day):
            if entry_day != day:
                continue
            entry = self._npc_day[(npc_id, entry_day)]
            report[npc_id] = {
                "tokens_in": entry.tokens_in,
                "tokens_out": entry.tokens_out,
                "tokens": entry.tokens_in + entry.tokens_out,
                "calls": entry.calls,
                "usd": entry.usd,
                "limit_tokens": int(self.per_npc_daily_tokens),
            }
        return {"day_index": day, "day_ticks": int(self.day_ticks), "npcs": report,
                "tick_calls": {str(key): self._tick[key] for key in sorted(self._tick)}}

    def degraded_target(self, reason: str | None) -> str:
        """拒绝原因 → 降级目标（语义固定，供策略层/日志使用）。"""
        if reason == "per_tick":
            return "on_budget_exhausted"
        if reason == "npc_daily":
            return "on_budget_exhausted"
        return "on_budget_exhausted"
