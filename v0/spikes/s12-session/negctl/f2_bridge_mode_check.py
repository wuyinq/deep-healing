#!/usr/bin/env python3
"""F2 判据：桥的 `mode` 缺省必须 **fail-closed**（R2 / CRITICAL-2 · M3-02）。

判据（真跑，全部在整树副本里）：
  ① 不传 `mode` 的 intent ⇒ `intent_ack{status:"rejected",reason:"E_MODE_READONLY"}`，
     内核事件流有 `intent.rejected{E_MODE_READONLY}` 且**无** `intent.applied`；
  ② 显式 `mode:"participate"` ⇒ 正常 `queued` 并在 tick 边界 `intent.applied`；
  ③ 非字符串 / 未知 mode ⇒ 同样拒（不得被静默当成可写）；
  ④ **负例**：把缺省值改回可写一侧 ⇒ ① **必须红**。

用法：python3 -B spikes/s12-session/negctl/f2_bridge_mode_check.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

WS = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3")
sys.path.insert(0, str(WS / "spikes" / "s13-render" / "negctl"))
import negctl_lib as lib  # noqa: E402

BRIDGE_REL = "v0_skeleton/session/bridge/kernel_bridge.py"

COMMANDS = [
    {"cmd": "intent", "intent": {"id": "no-mode", "kind": "delegate_instruction", "target": "npc-001"}},
    {"cmd": "intent", "mode": "observe", "intent": {"id": "explicit-observe", "kind": "delegate_instruction", "target": "npc-002"}},
    {"cmd": "intent", "mode": 7, "intent": {"id": "non-string-mode", "kind": "delegate_instruction", "target": "npc-003"}},
    {"cmd": "intent", "mode": "readonly", "intent": {"id": "bogus-mode", "kind": "delegate_instruction", "target": "npc-004"}},
    {"cmd": "intent", "mode": "participate", "intent": {"id": "explicit-participate", "kind": "delegate_instruction", "target": "npc-005"}},
    {"cmd": "step", "n": 2},
    {"cmd": "stop"},
]


def drive(copy_root: Path, tag: str):
    skel = copy_root / "02_source" / "v0_skeleton"
    runtime = copy_root / f"rt-{tag}"
    cmd = [sys.executable, "-B", str(skel / "session" / "bridge" / "kernel_bridge.py"),
           "--kernel-src", str(skel / "kernel"), "--pack-src", str(skel / "districts" / "xingfu-xiaoqu"),
           "--runtime-dir", str(runtime), "--seed", "20260921", "--snapshot-every", "50", "--ticks", "300"]
    proc = subprocess.run(cmd, input="".join(json.dumps(c) + "\n" for c in COMMANDS),
                          capture_output=True, text=True, timeout=900,
                          env={"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1"})
    records = [json.loads(line) for line in proc.stdout.splitlines() if line.strip().startswith("{")]
    events = []
    log = runtime / "logs" / "kernel-events.jsonl"
    if log.exists():
        events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    return proc, records, events, runtime


def judge(proc, records, events) -> dict:
    acks = {r.get("id"): r for r in records if r.get("kind") == "intent_ack"}
    rejected = [e for e in events if e.get("type") == "intent.rejected"]
    applied = [e for e in events if e.get("type") == "intent.applied"]
    rejected_ids = {(e.get("payload") or {}).get("intent_id"): (e.get("payload") or {}).get("reason_code")
                    for e in rejected}
    applied_ids = [(e.get("payload") or {}).get("intent_id") for e in applied]
    checks = {
        "no_mode_rejected_readonly": acks.get("no-mode", {}).get("status") == "rejected"
                                     and acks.get("no-mode", {}).get("reason") == "E_MODE_READONLY",
        "no_mode_has_rejected_event": rejected_ids.get("no-mode") == "E_MODE_READONLY",
        "no_mode_has_no_applied_event": "no-mode" not in applied_ids,
        "explicit_observe_rejected": acks.get("explicit-observe", {}).get("status") == "rejected"
                                     and acks.get("explicit-observe", {}).get("reason") == "E_MODE_READONLY",
        "non_string_mode_rejected": acks.get("non-string-mode", {}).get("status") == "rejected"
                                    and acks.get("non-string-mode", {}).get("reason") == "E_MODE_READONLY",
        "bogus_mode_rejected": acks.get("bogus-mode", {}).get("status") == "rejected"
                               and acks.get("bogus-mode", {}).get("reason") == "E_MODE_READONLY",
        "explicit_participate_queued": acks.get("explicit-participate", {}).get("status") == "queued",
        "explicit_participate_applied": "explicit-participate" in applied_ids,
    }
    return {"checks": checks, "exit": proc.returncode, "acks": acks,
            "intent_rejected_events": len(rejected), "intent_applied_events": len(applied),
            "rejected_reason_codes": rejected_ids, "applied_ids": applied_ids,
            "bridge_meta": next((r for r in records if r.get("kind") == "bridge_meta"), {})}


CASES = [
    {"case": "f2_pristine", "expect_all": True, "inject": []},
    {"case": "f2_neg_default_participate", "expect_all": False,
     "inject": [(BRIDGE_REL, 'mode = raw_mode if isinstance(raw_mode, str) else ""',
                 'mode = raw_mode if isinstance(raw_mode, str) else "participate"')]},
    {"case": "f2_neg_original_shape", "expect_all": False,
     "inject": [(BRIDGE_REL, 'raw_mode = command.get("mode")\n            mode = raw_mode if isinstance(raw_mode, str) else ""',
                 'mode = str(command.get("mode", "participate"))')]},
]


def main() -> int:
    before = lib.sha_tree(lib.SRC)
    results = []
    for spec in CASES:
        root = lib.fresh_copy(spec["case"])
        injections = [lib.inject(root / "02_source" / rel, old, new) for rel, old, new in spec["inject"]]
        proc, records, events, runtime = drive(root, spec["case"])
        judged = judge(proc, records, events)
        all_ok = all(judged["checks"].values())
        log = lib.write_log(f"negctl-{spec['case']}.log",
                            f"# case {spec['case']}\n# copy {root}\n# injections {injections}\n"
                            f"# bridge exit={proc.returncode}\n# stderr:\n{proc.stderr}\n"
                            f"# checks:\n{json.dumps(judged['checks'], ensure_ascii=False, indent=2)}\n"
                            f"# acks:\n{json.dumps(judged['acks'], ensure_ascii=False, indent=2)}\n"
                            f"# rejected_reason_codes: {json.dumps(judged['rejected_reason_codes'], ensure_ascii=False)}\n"
                            f"# applied_ids: {judged['applied_ids']}\n"
                            f"# intent.rejected={judged['intent_rejected_events']} intent.applied={judged['intent_applied_events']}\n")
        results.append({"case": spec["case"], "copy": str(root), "injections": injections, "log": str(log),
                        "expect_all_checks": spec["expect_all"], "all_checks_pass": all_ok,
                        "ok": all_ok == spec["expect_all"],
                        "verdict": "judged_green" if all_ok else "judged_red", **judged})
        print(f"[{spec['case']}] all_checks_pass={all_ok} exit={judged['exit']} "
              f"rejected_events={judged['intent_rejected_events']} applied={judged['applied_ids']} ok={all_ok == spec['expect_all']}")
    after = lib.sha_tree(lib.SRC)
    summary = {"round": "R2", "item": "F2 bridge mode fail-closed", "cases": results,
               "delivery_face_unchanged": before == after, "delivery_face_sha_tree": before,
               "all_ok": all(r["ok"] for r in results) and before == after}
    path = lib.write_summary("f2-bridge-mode-summary.json", summary)
    print(f"summary={path} delivery_face_unchanged={before == after} all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
