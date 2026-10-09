#!/usr/bin/env python3
"""行为分布读数（AC-4「无经历侧不得多 tick 即被治愈」的证据）。

用法: python3 diversity_stats.py <events.jsonl> [--npc npc-006] [--json out.json]
读数：分支占比（最大占比）、动作种类数、每半程的分支分布、室外目标占比。
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("events")
    parser.add_argument("--npc", default="npc-006")
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    decisions = []
    actions = []
    with open(args.events, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("actor") != args.npc:
                continue
            if event["type"] == "npc.decision":
                decisions.append((int(event["tick"]), (event.get("payload") or {})))
            elif event["type"] == "npc.action":
                actions.append((int(event["tick"]), (event.get("payload") or {})))

    branches = Counter(p.get("bt_branch") for _, p in decisions)
    needs = Counter(p.get("dominant_need") for _, p in decisions)
    chosen = Counter(p.get("chosen_action") for _, p in decisions)
    total = len(decisions) or 1
    half = (max((t for t, _ in decisions), default=0)) // 2
    first = Counter(p.get("bt_branch") for t, p in decisions if t <= half)
    second = Counter(p.get("bt_branch") for t, p in decisions if t > half)
    outdoor = sum(1 for _, p in actions if p.get("target_entity") == "courtyard-01")
    readings = {
        "decisions": len(decisions),
        "actions": len(actions),
        "branch_share_max": round(max(branches.values()) / total, 6) if branches else None,
        "branch_top": branches.most_common(1)[0][0] if branches else None,
        "branch_counts": dict(sorted(branches.items(), key=lambda kv: str(kv[0]))),
        "need_share_max": round(max(needs.values()) / total, 6) if needs else None,
        "need_counts": dict(sorted(needs.items(), key=lambda kv: str(kv[0]))),
        "distinct_actions": len([k for k in chosen if k]),
        "action_counts": dict(sorted(chosen.items(), key=lambda kv: str(kv[0]))),
        "first_half_branch_counts": dict(sorted(first.items(), key=lambda kv: str(kv[0]))),
        "second_half_branch_counts": dict(sorted(second.items(), key=lambda kv: str(kv[0]))),
        "courtyard_target_actions": outdoor,
    }
    text = json.dumps(readings, ensure_ascii=False, indent=2)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
