#!/usr/bin/env python3
"""G8 判据与负例（R3 / Raven r2 R2-M1）：`void_intents` 只能作废**本会话**的待应用意图。

判据（在 `/tmp/r3-artisan/**` 的隔离副本上真跑）：
  ① **内核侧**（`g8_void_ownership_driver.py`）：跨会话作废不牵连他人；**无归属**作废必须被拒；
  ② **桥侧**（真 `kernel_bridge.py` + stdin）：`void_intents` 带别的会话 id ⇒ 只作废那个会话；
     不带 `session_id` ⇒ 必须**拒**（`refused=E_SESSION_UNKNOWN`）且 `pending_after` 不变；
  ③ **负例 A**：把内核的归属校验与过滤退回 R2 形态 ⇒ 无归属调用会作废**所有**会话 ⇒ 判据必须红；
  ④ **负例 B**：把桥的归属校验退回 R2 形态（连同内核一起退）⇒ 桥上的无归属请求作废一切 ⇒ 判据必须红。

用法：python3 -B spikes/s12-session/negctl/g8_void_ownership_negctl.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

WS = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3")
sys.path.insert(0, str(WS / "spikes" / "s13-render" / "negctl"))
import negctl_lib as lib  # noqa: E402

KERNEL_DRIVER = WS / "spikes" / "s12-session" / "negctl" / "g8_void_ownership_driver.py"
TICK_REL = "v0_skeleton/kernel/deephealing_kernel/tick.py"
BRIDGE_REL = "v0_skeleton/session/bridge/kernel_bridge.py"

TICK_GUARD = ('        if not session_id:\n'
              '            raise ValueError(\n'
              '                "E_SESSION_UNKNOWN: void_pending_intents requires an owning session_id "\n'
              '                "(跨会话 / 无归属的作废请求一律拒绝)"\n'
              '            )\n')
TICK_FILTER = '            if item.get("session_id") != session_id:'
TICK_FILTER_R2 = '            if session_id is not None and item.get("session_id") != session_id:'

BRIDGE_GUARD = '            if not isinstance(session_id, str) or not session_id.strip():'
BRIDGE_CALL = '            voided = kernel.void_pending_intents(reason_code, session_id.strip())'
BRIDGE_CALL_R2 = ('            voided = kernel.void_pending_intents(\n'
                  '                reason_code, None if session_id is None else str(session_id))')
BRIDGE_EMIT = '                  "reason": reason_code, "session_id": session_id.strip(),'
BRIDGE_EMIT_R2 = '                  "reason": reason_code, "session_id": session_id,'

NEG_KERNEL_INJECT = [(TICK_REL, TICK_GUARD, "        pass\n"),
                     (TICK_REL, TICK_FILTER, TICK_FILTER_R2)]
NEG_BRIDGE_INJECT = NEG_KERNEL_INJECT + [
    (BRIDGE_REL, BRIDGE_GUARD, "            if False:"),
    (BRIDGE_REL, BRIDGE_CALL, BRIDGE_CALL_R2),
    (BRIDGE_REL, BRIDGE_EMIT, BRIDGE_EMIT_R2),
]


def run_kernel_driver(root: Path):
    kernel_dir = root / "02_source" / "v0_skeleton" / "kernel"
    exit_code, stdout, stderr, secs = lib.run(
        [sys.executable, "-B", str(KERNEL_DRIVER), str(kernel_dir)], root, timeout=300)
    reading = {}
    try:
        reading = json.loads([line for line in stdout.splitlines() if line.startswith("{")][0])
    except Exception:  # noqa: BLE001
        pass
    return exit_code, stdout, stderr, secs, reading


def run_bridge(root: Path):
    """真桥 + stdin：跨会话作废 / 无归属作废。返回 (void_acks, stdout, stderr, exit)。"""
    source = root / "02_source"
    bridge = source / "v0_skeleton" / "session" / "bridge" / "kernel_bridge.py"
    runtime = root / "bridge-runtime"
    commands = [
        {"cmd": "intent", "mode": "participate",
         "intent": {"id": "i-a-1", "kind": "delegate_instruction", "target": "npc-001", "session_id": "sess_a"}},
        {"cmd": "intent", "mode": "participate",
         "intent": {"id": "i-b-1", "kind": "delegate_instruction", "target": "npc-002", "session_id": "sess_b"}},
        {"cmd": "void_intents", "session_id": "sess_b", "reason_code": "E_BUDGET_EXHAUSTED"},
        {"cmd": "void_intents", "reason_code": "E_BUDGET_EXHAUSTED"},
        {"cmd": "void_intents", "session_id": "sess_a", "reason_code": "E_BUDGET_EXHAUSTED"},
        {"cmd": "stop"},
    ]
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [sys.executable, "-B", str(bridge),
         "--kernel-src", str(source / "v0_skeleton" / "kernel"),
         "--pack-src", str(source / "v0_skeleton" / "districts" / "xingfu-xiaoqu"),
         "--runtime-dir", str(runtime), "--seed", "20260921", "--snapshot-every", "50", "--ticks", "300"],
        input="".join(json.dumps(command) + "\n" for command in commands),
        capture_output=True, text=True, env=env, timeout=600, cwd=str(root))
    records = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return [record for record in records if record.get("kind") == "void_ack"], records, proc.stderr, proc.returncode


def bridge_criterion(void_acks):
    """真桥上的三条读数（顺序 = 命令顺序）。"""
    if len(void_acks) != 3:
        return False, {"error": f"expected 3 void_ack, got {len(void_acks)}"}
    cross, no_session, own = void_acks
    ok = (cross.get("voided") == ["i-b-1"] and cross.get("pending_after") == 1
          and no_session.get("voided") == [] and no_session.get("pending_after") == 1
          and no_session.get("refused") == "E_SESSION_UNKNOWN"
          and own.get("voided") == ["i-a-1"] and own.get("pending_after") == 0)
    return ok, {"cross_session": cross, "no_session": no_session, "own_session": own}


CASES = [
    {"case": "g8_pristine_kernel", "inject": [], "kind": "kernel", "expect_exit": 0},
    {"case": "g8_pristine_bridge", "inject": [], "kind": "bridge", "expect_exit": 0},
    {"case": "g8_neg_cross_session_void_kernel", "inject": NEG_KERNEL_INJECT, "kind": "kernel", "expect_exit": 1},
    {"case": "g8_neg_cross_session_void_bridge", "inject": NEG_BRIDGE_INJECT, "kind": "bridge", "expect_exit": 1},
]


def main() -> int:
    before = lib.sha_tree(lib.SRC)
    results = []
    for spec in CASES:
        root = lib.fresh_copy(spec["case"])
        injections = []
        for rel, old, new in spec["inject"]:
            injections.append(lib.inject(root / "02_source" / rel, old, new))
        if spec["kind"] == "kernel":
            exit_code, stdout, stderr, secs, reading = run_kernel_driver(root)
            detail = ""
        else:
            void_acks, records, stderr, exit_code = run_bridge(root)
            ok, reading = bridge_criterion(void_acks)
            exit_code = 0 if ok else 1
            stdout = json.dumps(reading, ensure_ascii=False, indent=2)
            secs = 0.0
            detail = f"records={len(records)}"
        ok = exit_code == spec["expect_exit"]
        log = lib.write_log(f"negctl-{spec['case']}.log",
                            f"# case {spec['case']}\n# kind {spec['kind']}\n# copy {root}\n"
                            f"# injections {injections}\n# {detail}\n"
                            f"# exit={exit_code} expect_exit={spec['expect_exit']} seconds={secs}\n"
                            f"# stderr:\n{stderr}\n# stdout:\n{stdout}\n")
        results.append({"case": spec["case"], "kind": spec["kind"], "copy": str(root), "injections": injections,
                        "exit": exit_code, "expect_exit": spec["expect_exit"], "reading": reading,
                        "ok": ok, "verdict": "judged_red" if exit_code else "judged_green", "log": str(log)})
        print(f"[{spec['case']}] exit={exit_code} ok={ok} reading={json.dumps(reading, ensure_ascii=False)[:220]}")
    after = lib.sha_tree(lib.SRC)
    summary = {"round": "R3", "item": "G8 void_intents session ownership", "neg_root": str(lib.NEG_ROOT),
               "cases": results, "delivery_face_unchanged": before == after,
               "delivery_face_sha_tree": before, "all_ok": all(r["ok"] for r in results) and before == after}
    path = lib.write_summary("g8-void-ownership-summary.json", summary)
    print(f"summary={path} delivery_face_unchanged={before == after} all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
