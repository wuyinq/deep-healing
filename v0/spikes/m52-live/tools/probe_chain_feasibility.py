#!/usr/bin/env python3
"""可行性探针（spikes/** 脚手架，**非交付面**）：先把「因果链在真内核里到底长什么样」量出来。

要回答的三个问题（**先量再设计，不臆测**）：
  ① 内核自产 `memory.written` 的 importance 落在哪 —— 是否 >= `MEMORY_SIGNAL_MIN_IMPORTANCE`(0.5)
     ⇒ 内核自产经历**会不会**进入 `memory_influence` 的信号窗口；
  ② 预置一条「关键经历」（注入）后，`npc.decision.memory_influence.signals` 是否真的引用它
     （形如 `episode:<kind>@ref=<R>`）；
  ③ 注入与不注入两条臂的**可观察行动**（`npc.action` 的 action / target_entity）在哪个 tick 首次分叉。

用法（workdir `<ws>`）：
    PYTHONDONTWRITEBYTECODE=1 python3 spikes/m52-live/tools/probe_chain_feasibility.py \
        --source 02_source --runtime spikes/m52-live/runtime/probe --pack xingfu-xiaoqu-xuqin --ticks 240
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import live_scenario  # noqa: E402
from live_scenario import Scenario  # noqa: E402

live_scenario.EMIT_ENABLED = False  # 探针只输出最终 JSON，不吐逐 tick 记录

INJECT_KIND = "walk"
INJECT_IMPORTANCE = 0.95


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M5.2 r2 · AC-5/W11 因果链可行性探针")
    parser.add_argument("--source", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--pack", default="xingfu-xiaoqu-xuqin")
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--ticks", type=int, default=240)
    parser.add_argument("--snapshot-every", type=int, default=25)
    parser.add_argument("--json", dest="json_path", default=None)
    return parser.parse_args(argv)


def run_arm(args: argparse.Namespace, *, name: str, inject: bool) -> dict:
    scenario = Scenario(source_root=Path(args.source), runtime_dir=Path(args.runtime) / name,
                        pack_name=args.pack, seed=args.seed, snapshot_every=args.snapshot_every,
                        memory_writes=True)
    injected_ref = None
    if inject:
        target = scenario.npc_ids[0]
        injected_ref = scenario.inject_episode(target, 0, INJECT_KIND, INJECT_IMPORTANCE,
                                               ["injected:key-experience"],
                                               f"injected:key-experience:{INJECT_KIND}")
    events: list[dict] = []
    for _ in range(int(args.ticks)):
        events.extend(scenario.step(1))

    written = [event for event in events if event["type"] == "memory.written"]
    decisions = [event for event in events if event["type"] == "npc.decision"]
    actions = [event for event in events if event["type"] == "npc.action"]
    importance = Counter(round(float(event["payload"].get("importance") or 0.0), 4) for event in written)
    deficits = [float(event["payload"].get("dominant_deficit") or 0.0) for event in decisions]
    with_signals = [event for event in decisions
                    if (event["payload"].get("memory_influence") or {}).get("signals")]
    signal_refs = Counter()
    for event in with_signals:
        for signal in (event["payload"].get("memory_influence") or {}).get("signals") or []:
            signal_refs[str(signal)] += 1
    return {
        "name": name, "injected_ref": injected_ref, "ticks": int(args.ticks),
        "npc_ids": scenario.npc_ids,
        "memory_written_count": len(written),
        "memory_written_importance_histogram": dict(sorted(importance.items())),
        "memory_written_refs_head": [event["payload"].get("ref") for event in written[:6]],
        "memory_written_ge_0_5": sum(1 for event in written
                                     if float(event["payload"].get("importance") or 0.0) >= 0.5),
        "decision_count": len(decisions),
        "decisions_with_signals": len(with_signals),
        "first_decision_with_signals": (with_signals[0] if with_signals else None),
        "signal_histogram": dict(sorted(signal_refs.items())),
        "dominant_deficit_min": min(deficits) if deficits else None,
        "dominant_deficit_max": max(deficits) if deficits else None,
        "action_sequence": [{"tick": int(event["tick"]), "npc_id": event["actor"],
                             "action": event["payload"].get("action"),
                             "target_entity": event["payload"].get("target_entity")}
                            for event in actions],
        "state_hash": scenario.world.state_hash(),
        "event_count": len(events),
        "event_type_histogram": dict(sorted(Counter(event["type"] for event in events).items())),
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    arm_with = run_arm(args, name="with_injection", inject=True)
    arm_without = run_arm(args, name="without_injection", inject=False)
    seq_with = [(item["tick"], item["action"], item["target_entity"]) for item in arm_with["action_sequence"]]
    seq_without = [(item["tick"], item["action"], item["target_entity"]) for item in arm_without["action_sequence"]]
    divergence = next((item for item, other in zip(seq_with, seq_without) if item != other), None)
    injected_ref = arm_with["injected_ref"]
    document = {
        "status": "measured", "pack": args.pack, "seed": int(args.seed), "ticks": int(args.ticks),
        "inject_kind": INJECT_KIND, "inject_importance": INJECT_IMPORTANCE,
        "injected_ref": injected_ref,
        "injected_ref_seen_in_signals": any(f"@ref={injected_ref}" in key for key in arm_with["signal_histogram"]),
        "first_action_divergence": divergence,
        "action_sequences_identical": seq_with == seq_without,
        "arms": {"with_injection": arm_with, "without_injection": arm_without},
        "scope": {"source": str(Path(args.source).resolve()), "runtime": str(Path(args.runtime).resolve())},
    }
    text = json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True)
    sys.stdout.write(text + "\n")
    if args.json_path:
        target = Path(args.json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
