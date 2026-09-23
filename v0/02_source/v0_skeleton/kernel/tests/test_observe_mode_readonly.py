"""双模式权限的内核侧判据（AC-M3-2 / AC-M3-4 的内核承重面）——**真断言，非 skip**。

运行（**真跑，非 skip**）：
    cd <workspace>/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 \
        python3 -m pytest tests/test_observe_mode_readonly.py -q -p no:cacheprovider

分工（**如实声明**，避免「把会话层判据冒名成内核判据」）：
  - 限流 / 冷却 / 影响预算的**计数**属会话层（`session/src/policy.js`，判据在 `session/test/session.test.js`）；
  - 本文件断言的是**内核侧唯一入口的 fail-closed 契约**：`WorldKernel.submit_intent()` 是玩家意图的
    **唯一入口**，任何被拒路径都必须 ①落 `intent.rejected` 事件 ②不入队 ③**不改世界状态**
    （`state_hash` 逐位不变）。observe 会话**永远**走 `E_MODE_READONLY`。

RED 证据（隔离副本，见 spikes/s12-session/logs/）：把 `submit_intent()` 的 observe 分支改成
「静默接受」后，`test_observe_session_intent_rejected_with_readonly_code` 与
`test_impact_budget_exhausted_downgrades_to_observe` **必须变红**（已实测）。
"""

from __future__ import annotations

from pathlib import Path

from deephealing_kernel.events import EventLog
from deephealing_kernel.pack import load_pack
from deephealing_kernel.tick import WorldKernel

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SEED = 20260921


def _kernel(tmp_path: Path) -> tuple[WorldKernel, EventLog]:
    pack = load_pack(PACK_DIR)
    log = EventLog(tmp_path / "events.jsonl")
    kernel = WorldKernel(pack=pack, seed=SEED, log=log, snapshot_every=0, checkpoint_dir=None)
    return kernel, log


def _rejected(log: EventLog) -> list:
    return [event for event in log.read_all() if event.type == "intent.rejected"]


def _intent(intent_id: str, *, kind: str = "delegate_instruction", target: str = "npc-001") -> dict:
    return {"id": intent_id, "session_id": "sess_observe1", "kind": kind, "target": target}


def test_observe_session_intent_rejected_with_readonly_code(tmp_path):
    """observe 会话上行 intent → 一律 `E_MODE_READONLY`，落 `intent.rejected`，世界状态逐位不变。"""
    kernel, log = _kernel(tmp_path)
    before = kernel.state_hash()
    ack = kernel.submit_intent(_intent("i-obs-1"), mode="observe")
    assert ack["status"] == "rejected"
    assert ack["reason"] == "E_MODE_READONLY"
    assert kernel.pending_intent_count() == 0, "observe 的意图**不得**入队"

    rejected = _rejected(log)
    assert len(rejected) == 1
    assert rejected[0].payload["reason_code"] == "E_MODE_READONLY"
    assert rejected[0].payload["intent_id"] == "i-obs-1"
    assert rejected[0].actor == "session:sess_observe1"

    # 推进若干 tick 后：世界状态与「无任何 intent」的默认跑**逐位一致**，且没有任何应用/迁移事件
    kernel.run(20)
    types = [event.type for event in log.read_all()]
    assert "intent.applied" not in types
    assert "task.state_changed" not in types
    assert kernel.adaptation.state_of("task-001") == "dormant"
    assert kernel.state_hash() != before  # 世界在 tick（默认跑），但**不因 observe 意图**而变
    kernel_ref, log_ref = _kernel(tmp_path / "ref")
    kernel_ref.run(20)
    assert kernel_ref.state_hash() == kernel.state_hash()
    assert [event.type for event in log_ref.read_all() if event.type == "intent.rejected"] == []


def test_participate_intent_applied_only_at_tick_boundary(tmp_path):
    """participate 意图**只在 tick 边界**应用：tick 中途提交 ⇒ 世界状态不变、无应用事件。"""
    kernel, log = _kernel(tmp_path)
    kernel.run(3)
    snapshot_before = kernel.state_hash()
    ack = kernel.submit_intent(_intent("i-part-1"))
    assert ack["status"] == "queued"
    # tick 边界之前：零副作用
    assert kernel.state_hash() == snapshot_before
    assert kernel.world.tick == 3
    assert [event.type for event in log.read_all() if event.type == "intent.applied"] == []

    kernel.step()
    applied = [event for event in log.read_all() if event.type == "intent.applied"]
    assert len(applied) == 1
    assert applied[0].tick == 4, "应用发生在**下一个** tick 边界"
    assert applied[0].payload["applied_tick"] == 4
    assert kernel.pending_intent_count() == 0


def test_rate_limit_and_cooldown_enforced(tmp_path):
    """内核侧 fail-closed 面：被拒路径**一律**落事件、不入队、不改状态（拒绝码取自冻结枚举）。

    会话层的限流/冷却**计数**由 `session/test/session.test.js::test_rate_limit_and_cooldown_enforced`
    真跑断言；此处断言内核入口对**每一类非法意图**的确定性拒绝与「零写入」。
    """
    kernel, log = _kernel(tmp_path)
    before = kernel.state_hash()

    cases = [
        (_intent("i-ghost", kind="ghost_hand"), "E_SCHEMA_INVALID"),
        (_intent("i-avatar", kind="avatar"), "E_SCHEMA_INVALID"),
        (_intent("i-unknown-target", target="npc-999"), "E_TARGET_UNKNOWN"),
        (_intent("i-empty-target", target=""), "E_SCHEMA_INVALID"),
    ]
    for intent, expected in cases:
        ack = kernel.submit_intent(intent, mode="participate")
        assert ack["status"] == "rejected", f"{intent['id']} 必须被拒"
        assert ack["reason"] == expected, f"{intent['id']} 的拒绝码必须是 {expected}"

    rejected = _rejected(log)
    assert [event.payload["reason_code"] for event in rejected] == [expected for _, expected in cases]
    assert kernel.pending_intent_count() == 0
    assert kernel.state_hash() == before, "被拒的意图**不得**改动世界状态"
    assert [event.type for event in log.read_all() if event.type == "intent.applied"] == []


def test_impact_budget_exhausted_downgrades_to_observe(tmp_path):
    """预算耗尽 ⇒ 会话层降级为 observe；降级后的意图必须走内核的 `E_MODE_READONLY` 路径。

    会话层的预算计数与降级动作由 `session/test/session.test.js` 真跑断言；此处断言
    **降级之后**的意图在内核唯一入口上**必然被拒且零写入**（这是「降级真的生效」的承重面）。
    """
    kernel, log = _kernel(tmp_path)
    # 正常 participate 意图：入队成功
    assert kernel.submit_intent(_intent("i-budget-ok"))["status"] == "queued"
    kernel.step()
    assert kernel.adaptation.state_of("task-001") == "offered"

    before = kernel.state_hash()
    # 预算耗尽 ⇒ 会话层把模式降级为 observe ⇒ 同一入口上必须被拒
    ack = kernel.submit_intent(_intent("i-budget-exhausted"), mode="observe")
    assert ack["status"] == "rejected" and ack["reason"] == "E_MODE_READONLY"
    kernel.run(5)
    assert kernel.adaptation.state_of("task-001") == "offered", "降级后的意图**不得**推进任务状态"
    assert kernel.pending_intent_count() == 0
    reasons = [event.payload["reason_code"] for event in _rejected(log)]
    assert reasons == ["E_MODE_READONLY"]
    assert before != kernel.state_hash()  # 世界继续 tick
