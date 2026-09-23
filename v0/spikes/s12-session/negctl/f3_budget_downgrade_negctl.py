#!/usr/bin/env python3
"""F3 判据与负例（R2 / CRITICAL-3 · M3-03）：预算降级**不得静默作废**已 ack 的意图。

判据（对真会话层 + 真桥 + 真内核的原始读数判定，读数由
`spikes/s12-session/scripts/f3-budget-downgrade.mjs` 产出）：
  ① 降级后 `pending_intent_count() == 0`（读 `void_ack.pending_after`，内核直读）；
  ② 每条作废意图有对应事件/ack（会话层 ack 计数 + 内核 `intent.rejected{E_BUDGET_EXHAUSTED}` 计数）；
  ③ 被作废的意图**不得**被应用（`intent.applied` 计数 = 0）；
  ④ **负例**：改回静默作废（会话层不补发 / 内核静默丢队列）⇒ ①② **必须红**。

用法：python3 -B spikes/s12-session/negctl/f3_budget_downgrade_negctl.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WS = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3")
sys.path.insert(0, str(WS / "spikes" / "s13-render" / "negctl"))
import negctl_lib as lib  # noqa: E402

SERVER_REL = "v0_skeleton/session/src/server.js"
TICK_REL = "v0_skeleton/kernel/deephealing_kernel/tick.py"
DRIVER = "spikes/s12-session/scripts/f3-budget-downgrade.mjs"


def checks(readings: dict) -> dict:
    a = readings["scenario_a_session_queue"]
    b = readings["scenario_b_kernel_queue"]
    return {
        # 场景 A：降级时意图还在会话层队列
        "a_mode_downgraded": a["session_mode_after"] == "observe",
        "a_budget_ack_rejected": a["budget_ack"]["status"] == "rejected"
                                 and a["budget_ack"]["reason"] == "E_BUDGET_EXHAUSTED",
        "a_every_queued_intent_has_rejection_ack": a["session_voided_acks"] == 33,
        "a_session_pending_zero": a["session_pending_after"] == 0,
        "a_no_voided_intent_applied": a["kernel_applied_total"] == 0,
        "a_audit_entries_for_every_voided": a["audit_budget_entries"] == 34,
        # 场景 B：降级时意图已在**内核侧**待应用队列
        "b_precondition_33_submitted": b["boundary_submitted"] == 33 and b["queued_acks"] == 33,
        "b_mode_downgraded": b["session_mode_after"] == "observe",
        "b_kernel_pending_zero_after_downgrade": b["kernel_pending_after_void"] == 0,
        "b_every_kernel_intent_voided_with_event": b["kernel_rejected_budget_exhausted"] == 33,
        "b_kernel_voided_ids_complete": b["kernel_voided_count"] == 33,
        "b_session_pending_zero": b["session_pending_after"] == 0,
        "b_no_voided_intent_applied": b["kernel_applied_total"] == 0,
    }


CASES = [
    {"case": "f3_pristine", "expect_all": True, "inject": []},
    {"case": "f3_neg_session_silent_downgrade", "expect_all": False,
     "why": "会话层退回「只改 mode、不补发 ack、不作废内核队列」（R1 的静默作废形态）",
     "inject": [(SERVER_REL,
                 "if (verdict.downgradeToObserve) await this.downgradeToObserve(session);",
                 "if (verdict.downgradeToObserve) session.mode = 'observe';")]},
    {"case": "f3_neg_kernel_silent_drop", "expect_all": False,
     "why": "内核侧退回「静默清空队列、不发 intent.rejected」",
     "inject": [(TICK_REL,
                 '            self._reject_intent(str(item["id"]), str(item.get("session_id", "")), reason_code,\n'
                 '                                "voided on budget downgrade (was queued, never applied)")\n'
                 '            voided.append(str(item["id"]))',
                 '            voided.append(str(item["id"]))')]},
]


def main() -> int:
    before = lib.sha_tree(lib.SRC)
    results = []
    for spec in CASES:
        root = lib.fresh_copy(spec["case"])
        injections = [lib.inject(root / "02_source" / rel, old, new) for rel, old, new in spec["inject"]]
        runtime = root / "rt"
        exit_code, stdout, stderr, secs = lib.run(
            ["node", str(WS / DRIVER), "--source", str(root / "02_source"),
             "--runtime", str(runtime), "--out", str(root / "readings.json")],
            WS, timeout=1200)
        readings = None
        try:
            readings = json.loads(stdout[stdout.index("{"):])
        except Exception:  # noqa: BLE001
            pass
        judged = checks(readings) if readings else {}
        all_ok = bool(judged) and all(judged.values())
        log = lib.write_log(f"negctl-{spec['case']}.log",
                            f"# case {spec['case']}\n# copy {root}\n# injections {injections}\n"
                            f"# driver exit={exit_code} seconds={secs}\n"
                            f"# cmd: node {DRIVER} --source {root}/02_source --runtime {runtime}\n"
                            f"# stderr:\n{stderr}\n# checks:\n{json.dumps(judged, ensure_ascii=False, indent=2)}\n"
                            f"# readings:\n{json.dumps(readings, ensure_ascii=False, indent=2)}\n")
        results.append({"case": spec["case"], "copy": str(root), "injections": injections,
                        "log": str(log), "driver_exit": exit_code, "seconds": secs,
                        "expect_all_checks": spec["expect_all"], "all_checks_pass": all_ok,
                        "ok": all_ok == spec["expect_all"],
                        "verdict": "judged_green" if all_ok else "judged_red",
                        "failed_checks": sorted(key for key, value in judged.items() if not value),
                        "checks": judged,
                        "readings": {k: v for k, v in (readings or {}).items() if k.startswith("scenario")}})
        print(f"[{spec['case']}] all_checks_pass={all_ok} exit={exit_code} "
              f"failed={results[-1]['failed_checks']} ok={results[-1]['ok']}")
    after = lib.sha_tree(lib.SRC)
    summary = {"round": "R2", "item": "F3 budget downgrade void", "cases": results,
               "delivery_face_unchanged": before == after, "delivery_face_sha_tree": before,
               "all_ok": all(r["ok"] for r in results) and before == after}
    path = lib.write_summary("f3-budget-downgrade-summary.json", summary)
    print(f"summary={path} delivery_face_unchanged={before == after} all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
