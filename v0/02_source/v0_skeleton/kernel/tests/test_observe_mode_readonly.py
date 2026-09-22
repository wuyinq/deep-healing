"""RED 用例：双模式权限（AC-4）——observe 会话上行 intent 必须被拒。

运行（实现完成后）：
    cd <workspace>/02_source/v0_skeleton/session && npm test
"""

from __future__ import annotations

import pytest


def test_observe_session_intent_rejected_with_readonly_code(tmp_path):
    """observe 会话上行 intent → intent_ack{status:rejected, reason:E_MODE_READONLY}。"""
    pytest.skip("V0 skeleton: pending session transport implementation (see 08_v0_plan.md)")


def test_participate_intent_applied_only_at_tick_boundary(tmp_path):
    """participate 意图只在 tick 边界应用，不得在 tick 中途写世界状态。"""
    pytest.skip("V0 skeleton: pending session transport implementation (see 08_v0_plan.md)")


def test_rate_limit_and_cooldown_enforced(tmp_path):
    """超出 rate_limit / cooldown → E_RATE_LIMITED / E_COOLDOWN，且落 intent.rejected 事件。"""
    pytest.skip("V0 skeleton: pending session transport implementation (see 08_v0_plan.md)")


def test_impact_budget_exhausted_downgrades_to_observe(tmp_path):
    """影响预算耗尽 → 后续介入降级为观察 + 记入待办（E_BUDGET_EXHAUSTED）。"""
    pytest.skip("V0 skeleton: pending session transport implementation (see 08_v0_plan.md)")
