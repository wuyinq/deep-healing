#!/usr/bin/env python3
"""G5 判据与负例（R3 / Raven r2 R2-M5）：合并窗口不得产生「已 ack 为 queued 却永不应用」。

判据（在 `/tmp/r3-artisan/**` 的隔离副本上真跑 `g5_merge_window_driver.mjs`）：
  ① 阳性：同 id 窗口内**仍在队列** ⇒ 允许合并；**离开队列**后同 id 再提交 ⇒
     `pending_intent_count() ≥ 1` **或** ack ≠ `queued`；同 id **不同 target** 不得合并；
  ② **负例**：把合并条件退回 R2 形态（只看「同 id + 窗口内」，不看 `pending`/`target`）⇒ 判据必须红。

用法：python3 -B spikes/s12-session/negctl/g5_merge_window_negctl.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WS = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3")
sys.path.insert(0, str(WS / "spikes" / "s13-render" / "negctl"))
import negctl_lib as lib  # noqa: E402

DRIVER = WS / "spikes" / "s12-session" / "negctl" / "g5_merge_window_driver.mjs"
POLICY_REL = "v0_skeleton/session/src/policy.js"
MERGE_ANCHOR = ("    if (mergeWindowMs > 0 && previous !== undefined && previous.pending === true\n"
                "        && previous.target === target && nowMs - previous.ms < mergeWindowMs) {")
MERGE_R2 = "    if (mergeWindowMs > 0 && previous !== undefined && nowMs - previous.ms < mergeWindowMs) {"


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
    {"case": "g5_pristine", "inject": None, "expect_exit": 0,
     "why": "阳性：判据成立（离开队列后不再合并；合并键含 target）"},
    {"case": "g5_neg_revert_to_r2_merge", "inject": (POLICY_REL, MERGE_ANCHOR, MERGE_R2), "expect_exit": 1,
     "why": "负例：退回 R2 的「只看同 id + 窗口内」⇒ 已 ack 为 queued 却永不应用 ⇒ 判据必须红"},
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
    summary = {"round": "R3", "item": "G5 merge window (no queued-but-never-applied)", "neg_root": str(lib.NEG_ROOT),
               "cases": results, "delivery_face_unchanged": before == after,
               "delivery_face_sha_tree": before, "all_ok": all(r["ok"] for r in results) and before == after}
    path = lib.write_summary("g5-merge-window-summary.json", summary)
    print(f"summary={path} delivery_face_unchanged={before == after} all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
