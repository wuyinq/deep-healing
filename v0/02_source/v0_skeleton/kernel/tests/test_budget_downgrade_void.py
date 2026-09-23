"""预算耗尽降级：内核侧**待应用队列作废**的判据（R2 / M3-03）——**真断言，非 skip**。

运行（真跑）：
    cd <workspace>/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 \
        python3 -m pytest tests/test_budget_downgrade_void.py -q -p no:cacheprovider

契约（`intervention.policy.schema.json` 的 `impact_budget.on_exhausted = 'observe_and_drop_queued'`）：
已 ack 为 `queued` 的意图**不得静默失效**。会话层预算耗尽降级时必须调用
`WorldKernel.void_pending_intents()`，它必须：
  ① 逐条落 `intent.rejected{reason_code=E_BUDGET_EXHAUSTED}`（可审计、可回放）；
  ② 清空被作废条目 ⇒ `pending_intent_count() == 0`（不存在「已 ack 但无声消失」）；
  ③ **不**改世界状态、**不**产生 `intent.applied` / `task.state_changed`；
  ④ 队列为空 ⇒ **零副作用**（不发事件、不动状态）。

RED 证据（隔离副本，见 `spikes/s12-session/logs/f3-*.log`）：把降级改回「静默丢弃队列」后，
本文件的 ①② 断言与 `session/test/session.test.js` 的两条降级用例**必须变红**（已实测）。
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


def _intent(intent_id: str, session_id: str = "sess_budget1", target: str = "npc-001") -> dict:
    return {"id": intent_id, "session_id": session_id, "kind": "delegate_instruction", "target": target}


def _rejected(log: EventLog) -> list:
    return [event for event in log.read_all() if event.type == "intent.rejected"]


def test_void_pending_intents_emits_rejection_per_intent_and_empties_queue(tmp_path):
    """① 逐条落 `intent.rejected{E_BUDGET_EXHAUSTED}`；② 队列清空；③ 世界状态逐位不变。"""
    kernel, log = _kernel(tmp_path)
    for index in range(3):
        assert kernel.submit_intent(_intent(f"i-void-{index}"))["status"] == "queued"
    assert kernel.pending_intent_count() == 3
    before = kernel.state_hash()

    voided = kernel.void_pending_intents("E_BUDGET_EXHAUSTED", "sess_budget1")

    assert voided == ["i-void-0", "i-void-1", "i-void-2"], "按队列顺序逐条作废"
    assert kernel.pending_intent_count() == 0, "作废后内核侧 pending 必须为 0"
    rejected = _rejected(log)
    assert [event.payload["intent_id"] for event in rejected] == voided
    assert {event.payload["reason_code"] for event in rejected} == {"E_BUDGET_EXHAUSTED"}
    assert {event.payload["detail"] for event in rejected} == {"voided on budget downgrade (was queued, never applied)"}
    assert kernel.state_hash() == before, "作废**不得**改动世界状态"

    # 推进若干 tick：被作废的意图**不得**被应用，也不得推进任务状态机
    kernel.run(5)
    types = [event.type for event in log.read_all()]
    assert "intent.applied" not in types
    assert "task.state_changed" not in types
    assert kernel.adaptation.state_of("task-001") == "dormant"
    assert kernel.pending_intent_count() == 0


def test_void_pending_intents_is_session_scoped(tmp_path):
    """只作废**指定会话**的待应用条目；其他会话的条目保留原顺序。"""
    kernel, log = _kernel(tmp_path)
    kernel.submit_intent(_intent("i-a-0", "sess_a"))
    kernel.submit_intent(_intent("i-b-0", "sess_b"))
    kernel.submit_intent(_intent("i-a-1", "sess_a"))
    assert kernel.pending_intent_count() == 3

    assert kernel.void_pending_intents("E_BUDGET_EXHAUSTED", "sess_a") == ["i-a-0", "i-a-1"]
    assert kernel.pending_intent_count() == 1, "其他会话的条目不得被牵连作废"
    assert [event.payload["intent_id"] for event in _rejected(log)] == ["i-a-0", "i-a-1"]

    # sess_b 的条目仍会在 tick 边界被正常应用
    kernel.step()
    applied = [event.payload["intent_id"] for event in log.read_all() if event.type == "intent.applied"]
    assert applied == ["i-b-0"]


def test_void_pending_intents_empty_queue_is_zero_side_effect(tmp_path):
    """④ 队列为空 ⇒ 零副作用（不新增事件、不动状态）；已应用过的意图不受影响。"""
    kernel, log = _kernel(tmp_path)
    kernel.submit_intent(_intent("i-applied-0"))
    kernel.step()
    assert kernel.pending_intent_count() == 0
    events_before = len(list(log.read_all()))
    state_before = kernel.state_hash()

    assert kernel.void_pending_intents("E_BUDGET_EXHAUSTED", "sess_budget1") == []
    assert kernel.pending_intent_count() == 0
    assert len(list(log.read_all())) == events_before, "空队列作废不得发事件"
    assert kernel.state_hash() == state_before
    # 已被应用的意图**不**因作废而回滚
    assert [event.payload["intent_id"] for event in log.read_all() if event.type == "intent.applied"] == ["i-applied-0"]
