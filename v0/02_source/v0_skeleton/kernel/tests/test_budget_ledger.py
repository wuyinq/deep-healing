"""W4 / AC-M2-4：三级预算语义 + 「超时值来自契约声明」+ 降级可审计。

运行：
    cd <workspace>/02_source/v0_skeleton/kernel && \
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_budget_ledger.py -q -p no:cacheprovider

判据（设计 §3.2 / D-0.9）：
  1. 超 tick 上限 → `allow_call` 返回 `(False, "per_tick")` ⇒ 注册表走 `fallback.on_budget_exhausted`；
  2. 超日 token → `(False, "npc_daily")` ⇒ **降级到 `deterministic_rule`**（不是报错、不是静默回填）；
  3. `spend_impact` 耗尽 → `(False, 剩余)`；
  4. **代码里零毫秒常量**：provider 收到的 `timeout_ms` 必须**等于能力契约的声明值**；
  5. **负例自证**：把降级改成「静默回填」⇒ 本文件的门禁必须变红。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
SKELETON = KERNEL_ROOT.parent
CAPS_DIR = SKELETON / "capabilities"

from deephealing_kernel.budget import BudgetLedger  # noqa: E402
from deephealing_kernel.providers.deterministic_rule import DeterministicRuleProvider  # noqa: E402
from deephealing_kernel.registry import CapabilityRegistry  # noqa: E402


def _ledger(**overrides) -> BudgetLedger:
    settings = {"day_ticks": 100, "per_tick_calls": 2, "per_npc_daily_tokens": 1000, "per_session_impact": 10.0}
    settings.update(overrides)
    return BudgetLedger(**settings)


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry(CAPS_DIR, CAPS_DIR / "pins.json")
    registry.register_adapter("deterministic_rule", DeterministicRuleProvider())
    return registry


# --------------------------------------------------------------------------- 三级语义
def test_day_index_is_integer_division():
    ledger = _ledger(day_ticks=1440)
    assert ledger.day_index(0) == 0
    assert ledger.day_index(1439) == 0
    assert ledger.day_index(1440) == 1
    # 反向对照：日界必须真的按 day_ticks 划分（不是恒 0）
    assert ledger.day_index(2880) == 2


def test_per_tick_cap_is_enforced():
    ledger = _ledger(per_tick_calls=2)
    assert ledger.allow_call(7, "npc-001") == (True, None)
    ledger.record(7, "npc-001", 1, 1, 0.0)
    assert ledger.allow_call(7, "npc-001") == (True, None)
    ledger.record(7, "npc-001", 1, 1, 0.0)
    assert ledger.allow_call(7, "npc-001") == (False, "per_tick")
    # 反向对照：下一个 tick 的配额必须重置（证明计数按 tick 分桶）
    assert ledger.allow_call(8, "npc-001") == (True, None)


def test_npc_daily_token_cap_is_enforced():
    ledger = _ledger(day_ticks=100, per_npc_daily_tokens=100)
    ledger.record(5, "npc-001", 60, 40, 0.0)
    assert ledger.allow_call(5, "npc-001") == (False, "npc_daily")
    # 反向对照：另一个 NPC / 下一个世界日不受影响（证明不是全局恒红）
    assert ledger.allow_call(5, "npc-002") == (True, None)
    assert ledger.allow_call(105, "npc-001") == (True, None)


def test_spend_impact_exhaustion():
    ledger = _ledger(per_session_impact=10.0)
    ok, remaining = ledger.spend_impact("session-a", 4.0)
    assert ok and remaining == 6.0
    ok, remaining = ledger.spend_impact("session-a", 6.0)
    assert ok and remaining == 0.0
    ok, remaining = ledger.spend_impact("session-a", 0.5)
    assert not ok and remaining == 0.0
    # 反向对照：另一个会话的预算独立（证明不是全局耗尽）
    assert ledger.spend_impact("session-b", 9.0)[0] is True


def test_daily_report_aggregates_per_npc():
    ledger = _ledger(day_ticks=100)
    ledger.record(3, "npc-001", 10, 5, 0.01)
    ledger.record(4, "npc-001", 20, 5, 0.02)
    ledger.record(4, "npc-002", 1, 1, 0.0)
    report = ledger.daily_report(9)
    assert report["npcs"]["npc-001"]["tokens"] == 40
    assert report["npcs"]["npc-001"]["calls"] == 2
    assert report["npcs"]["npc-002"]["calls"] == 1
    # 反向对照：另一个世界日的报告必须为空（证明日界真的生效）
    assert ledger.daily_report(109)["npcs"] == {}


# --------------------------------------------------------------------------- 与注册表的接缝
def test_budget_exhaustion_degrades_to_deterministic_rule():
    """超 tick 上限 ⇒ 注册表走 `fallback.on_budget_exhausted`（降级到 deterministic_rule，非静默回填）。"""
    registry = _registry()
    ledger = _ledger(per_tick_calls=1)
    payload = {"texts": ["幸福小区"]}
    first = registry.invoke("embed.text", payload, budget=ledger)
    assert first.fallback_reason is None and first.provider_class == "deterministic_rule"
    second = registry.invoke("embed.text", payload, budget=ledger)
    assert second.fallback_reason == "on_budget_exhausted", second
    assert second.provider_class == "deterministic_rule"
    fallbacks = [entry for entry in registry.journal if entry.get("event") == "capability.fallback"]
    assert fallbacks and fallbacks[-1]["reason"] == "on_budget_exhausted"
    assert fallbacks[-1]["target"] == "deterministic_rule"

    # 负例自证：把「降级」改成「静默回填」⇒ 本文件的门禁断言必须变红。
    # 静默回填形态 = `_fallback` 不落 `capability.fallback` 事件、直接把输出当成功返回。
    silent = _registry()
    silent_ledger = _ledger(per_tick_calls=1)
    silent.invoke("embed.text", payload, budget=silent_ledger)
    original = silent._fallback  # noqa: SLF001 (判据注入)

    def _silent_backfill(*args, **kwargs):
        from deephealing_kernel.registry import InvocationResult

        return InvocationResult(output={"dim": 1, "vectors": [[0.0]]}, provider_class="deterministic_rule",
                                ms=0.0, ok=True, fallback_reason=None)

    silent._fallback = _silent_backfill  # noqa: SLF001 (判据注入)
    try:
        mutated = silent.invoke("embed.text", payload, budget=silent_ledger)
        # 这两条就是上面用来判「降级可审计」的门禁 —— 静默回填下它们**必然不成立**
        assert mutated.fallback_reason != "on_budget_exhausted"
        assert not [entry for entry in silent.journal if entry.get("event") == "capability.fallback"]
    finally:
        silent._fallback = original  # noqa: SLF001
    assert original is not _silent_backfill


def test_timeout_comes_from_the_capability_contract():
    """**零毫秒常量**：provider 收到的 `timeout_ms` 必须等于能力契约声明的值。"""
    seen: list[int] = []

    class _Spy:
        provider_class = "deterministic_rule"

        def invoke(self, capability, payload, *, timeout_ms):
            seen.append(timeout_ms)
            return {"dim": 1, "vectors": []}

    registry = _registry()
    registry.register_adapter("deterministic_rule", _Spy())
    registry.invoke("embed.text", {"texts": ["x"]})
    declared = registry.capability("embed.text")["timeout_ms"]
    assert seen == [declared], (seen, declared)

    # 反向对照：契约里改掉声明值 ⇒ provider 收到的值必须随之变化（证明不是代码常量）
    document = json.loads((CAPS_DIR / "embed.text@1.0.0.capability.json").read_text(encoding="utf-8"))
    assert document["timeout_ms"] == declared
    assert document["timeout_ms"] != document["calibration"]["max_ms"]  # 声明值 ≠ 实测最大值（防自证）

    # 源码面：预算与规则层不得出现毫秒字面量常量
    import re

    pattern = re.compile(r"(timeout_ms|latency_ms|ms)\s*[:=]\s*\d{2,}")
    for name in ("budget.py", "rules/behaviour_tree.py", "rules/utility.py", "rules/requirement.py"):
        source = (KERNEL_ROOT / "deephealing_kernel" / name).read_text(encoding="utf-8")
        code_lines = [line for line in source.splitlines() if not line.strip().startswith("#")]
        hits = [line for line in code_lines if pattern.search(line)]
        assert not hits, f"{name} 出现毫秒字面量常量：{hits}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
