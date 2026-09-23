#!/usr/bin/env python3
"""诊断：cognition 树走了哪条分支 / 录了哪些 cassette —— 交付树 vs 参考树。"""
import json
import os
import subprocess
import sys
from pathlib import Path

TREES = {
    "delivery": Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260923-002-deephealing-m5-2-character-loop"),
    "reference": Path("/tmp/m52-ref"),
}
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

for name, ws in TREES.items():
    kernel = ws / "02_source/v0_skeleton/kernel"
    out = Path(f"/tmp/m52-notes/diag-cog-{name}")
    cas = out / "cas"
    cas.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "deephealing_kernel", "run", "--ws-port", "0",
         "--pack", "districts/xingfu-xiaoqu", "--seed", "20260921", "--ticks", "100",
         "--cognition", "--events", str(out / "events.jsonl"), "--cassette-dir", str(cas)],
        capture_output=True, text=True, cwd=str(kernel), env=ENV)
    journal = out / "cognition" / "cognition.jsonl"
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line.strip()]
    slots = [record.get("slot") for record in records if record.get("event") == "capability.call"]
    summary_path = out / "cognition" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    print(json.dumps({
        "tree": name,
        "exit": proc.returncode,
        "cassette_files": sorted(path.name for path in cas.glob("*.jsonl")),
        "capability_calls": len(slots),
        "slot_order": slots[:9],
        "needs_pressure_seen": [record.get("needs_pressure") for record in records
                                if record.get("event") == "cognition.decision"][:5],
        "fallback_counts": summary.get("fallback_counts"),
        "journal_events": sorted({record.get("event") for record in records}),
    }, ensure_ascii=False, sort_keys=True))
