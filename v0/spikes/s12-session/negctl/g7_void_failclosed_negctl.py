#!/usr/bin/env python3
"""G7 判据与负例（R3 / Raven r2 R2-M6）：桥侧作废失败时不得无条件宣告作废。

判据（在 `/tmp/r3-artisan/**` 的隔离副本上真跑 `g7_void_failclosed_driver.mjs`，注入「桥超时」）：
  ① 阳性：33 条待应用意图**不得**被宣告 `E_BUDGET_EXHAUSTED` 作废；必须给**如实** ack
     （`rejected` + `E_KERNEL_UNAVAILABLE` + `rejected_pending_kernel`）或错误事件；
     会话队列**保留**；落 `downgrade_void_incomplete` 审计；桥侧作废至少重试 1 次；
  ② **负例**：把「作废已确认」判定改成恒真（= 退回无条件宣告）⇒ 判据必须红。

用法：python3 -B spikes/s12-session/negctl/g7_void_failclosed_negctl.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WS = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3")
sys.path.insert(0, str(WS / "spikes" / "s13-render" / "negctl"))
import negctl_lib as lib  # noqa: E402

DRIVER = WS / "spikes" / "s12-session" / "negctl" / "g7_void_failclosed_driver.mjs"
SERVER_REL = "v0_skeleton/session/src/server.js"
CONFIRM_ANCHOR = ("    return Boolean(kernelVoided) && kernelVoided.bridge === 'ok'\n"
                  "      && Number(kernelVoided.pending_after ?? Number.NaN) === 0;")
CONFIRM_ALWAYS = "    return true; // 负例：退回「无条件宣告作废」"


def run_driver(root: Path):
    session_src = root / "02_source" / "v0_skeleton" / "session"
    exit_code, stdout, stderr, secs = lib.run(
        ["node", str(DRIVER), "--session-src", str(session_src)], root, timeout=300)
    reading = {}
    try:
        reading = json.loads([line for line in stdout.splitlines() if line.startswith("{")][0])
    except Exception:  # noqa: BLE001
        pass
    return exit_code, stdout, stderr, secs, reading


CASES = [
    {"case": "g7_pristine", "inject": None, "expect_exit": 0,
     "why": "阳性：桥超时 ⇒ 非作废 ack + 错误事件 + 队列保留 + 审计"},
    {"case": "g7_neg_unconditional_void", "inject": (SERVER_REL, CONFIRM_ANCHOR, CONFIRM_ALWAYS), "expect_exit": 1,
     "why": "负例：作废确认恒真（退回无条件宣告）⇒ 判据必须红"},
]


def main() -> int:
    before = lib.sha_tree(lib.SRC)
    results = []
    for spec in CASES:
        root = lib.fresh_copy(spec["case"])
        injections = []
        if spec["inject"]:
            rel, old, new = spec["inject"]
            injections.append(lib.inject(root / "02_source" / rel, old, new))
        exit_code, stdout, stderr, secs, reading = run_driver(root)
        ok = exit_code == spec["expect_exit"]
        log = lib.write_log(f"negctl-{spec['case']}.log",
                            f"# case {spec['case']}\n# why {spec['why']}\n# copy {root}\n"
                            f"# injections {injections}\n"
                            f"# cmd: node {DRIVER} --session-src {root}/02_source/v0_skeleton/session\n"
                            f"# exit={exit_code} expect_exit={spec['expect_exit']} seconds={secs}\n"
                            f"# stderr:\n{stderr}\n# stdout:\n{stdout}\n")
        results.append({"case": spec["case"], "why": spec["why"], "copy": str(root), "injections": injections,
                        "exit": exit_code, "expect_exit": spec["expect_exit"], "reading": reading,
                        "ok": ok, "verdict": "judged_red" if exit_code else "judged_green", "log": str(log)})
        print(f"[{spec['case']}] exit={exit_code} reading={reading} ok={ok}")
    after = lib.sha_tree(lib.SRC)
    summary = {"round": "R3", "item": "G7 bridge void failure must not declare void", "neg_root": str(lib.NEG_ROOT),
               "cases": results, "delivery_face_unchanged": before == after,
               "delivery_face_sha_tree": before, "all_ok": all(r["ok"] for r in results) and before == after}
    path = lib.write_summary("g7-void-failclosed-summary.json", summary)
    print(f"summary={path} delivery_face_unchanged={before == after} all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
