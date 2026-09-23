#!/usr/bin/env python3
"""G8 判据驱动（内核侧，R3 / Raven r2 R2-M1）：`void_pending_intents` 必须**有归属**。

在**隔离副本**的内核上真跑：
  ① 两个会话各有 1 条待应用意图；
  ② `void_pending_intents(..., 'sess_b')` ⇒ 只作废 `sess_b` 的条目，`sess_a` 的**必须仍在**；
  ③ **无 `session_id`** 的调用 ⇒ 必须**拒**（`ValueError`）且零作废（修复前会作废**所有**会话）；
  ④ 再作废 `sess_a` ⇒ 队列归零。

输出一行 JSON；判据不成立 ⇒ exit 1。用法：python3 -B g8_void_ownership_driver.py <kernel 目录>
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def main() -> int:
    kernel_dir = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(kernel_dir))
    from deephealing_kernel.events import EventLog  # noqa: PLC0415
    from deephealing_kernel.pack import load_pack  # noqa: PLC0415
    from deephealing_kernel.tick import WorldKernel  # noqa: PLC0415

    pack = load_pack(kernel_dir.parent / "districts" / "xingfu-xiaoqu")
    log_dir = Path(tempfile.mkdtemp(prefix="g8-void-ownership-"))
    kernel = WorldKernel(pack=pack, seed=20260921, log=EventLog(log_dir / "kernel-events.jsonl"),
                         snapshot_every=50, checkpoint_dir=log_dir / "checkpoints", plan_ticks=300)

    def submit(intent_id: str, session_id: str):
        return kernel.submit_intent({"id": intent_id, "kind": "delegate_instruction",
                                     "target": "npc-001", "session_id": session_id}, mode="participate")

    ack_a = submit("i-a-1", "sess_a")
    ack_b = submit("i-b-1", "sess_b")
    pending_before = kernel.pending_intent_count()

    voided_b = kernel.void_pending_intents("E_BUDGET_EXHAUSTED", "sess_b")
    pending_after_b = kernel.pending_intent_count()

    refused = None
    try:
        kernel.void_pending_intents("E_BUDGET_EXHAUSTED")  # 无归属 ⇒ 必须拒
    except ValueError as error:
        refused = str(error)[:160]
    pending_after_no_session = kernel.pending_intent_count()

    voided_a = kernel.void_pending_intents("E_BUDGET_EXHAUSTED", "sess_a")
    pending_after_a = kernel.pending_intent_count()

    criterion = (ack_a.get("status") == "queued" and ack_b.get("status") == "queued"
                 and pending_before == 2
                 and voided_b == ["i-b-1"] and pending_after_b == 1
                 and refused is not None and pending_after_no_session == 1
                 and voided_a == ["i-a-1"] and pending_after_a == 0)
    out = {
        "ack_a": ack_a.get("status"), "ack_b": ack_b.get("status"),
        "pending_before": pending_before,
        "voided_sess_b": voided_b, "pending_after_sess_b": pending_after_b,
        "no_session_refused": refused is not None, "refusal": refused,
        "pending_after_no_session_call": pending_after_no_session,
        "voided_sess_a": voided_a, "pending_after_sess_a": pending_after_a,
        "criterion_holds": criterion,
    }
    process_stdout = json.dumps(out, ensure_ascii=False, sort_keys=True)
    sys.stdout.write(process_stdout + "\n")
    return 0 if criterion else 1


if __name__ == "__main__":
    raise SystemExit(main())
