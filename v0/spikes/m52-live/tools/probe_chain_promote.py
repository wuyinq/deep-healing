#!/usr/bin/env python3
"""W11 可行性探针（spikes/** 脚手架，**非交付面**）：验证「库级提升关键经历」能否造出**可观察行动改变**。

两臂唯一变量 = **是否把 runner-up 经历提升到 importance 0.95**（`--inject-at` 那一 tick 之后）；
其余全部相同（同 seed / 同内容包 / 同 tick 数 / 内核记忆写入一律开）。

输出（JSON）：
  - `injection`：被提升的记录（ref / kind / importance before→after / 它引用的**真实事件 seq**）；
  - `signals`：注入臂里 `npc.decision.memory_influence.signals` 的首次出现与 ref；
  - `divergence`：两臂 `npc.action` 序列**首个分叉**（tick / action / target_entity 对照）；
  - `counterexample`：无注入臂里 signals 是否为空（链断）+ 行动是否不同（决策改变）。

用法（workdir `<ws>`）：
    PYTHONDONTWRITEBYTECODE=1 python3 spikes/m52-live/tools/probe_chain_promote.py \
        --source 02_source --runtime spikes/m52-live/runtime/probe-promote \
        --pack xingfu-xiaoqu-xuqin --ticks 120 --inject-at 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import live_scenario  # noqa: E402
from live_driver import _find_memory_record, _promote_target, _source_action_event  # noqa: E402
from live_scenario import Scenario  # noqa: E402

live_scenario.EMIT_ENABLED = False


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M5.2 r2 · W11 因果链可行性（promote 注入）")
    parser.add_argument("--source", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--pack", default="xingfu-xiaoqu-xuqin")
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument("--inject-at", type=int, default=20)
    parser.add_argument("--importance", type=float, default=0.95)
    parser.add_argument("--json", dest="json_path", default=None)
    return parser.parse_args(argv)


def run_arm(args: argparse.Namespace, *, name: str, promote: bool) -> dict:
    scenario = Scenario(source_root=Path(args.source), runtime_dir=Path(args.runtime) / name,
                        pack_name=args.pack, seed=args.seed, snapshot_every=25, memory_writes=True)
    target = scenario.npc_ids[0]
    history: list[dict] = []
    injection = None
    for _ in range(int(args.ticks)):
        fresh = scenario.step(1)
        history.extend(fresh)
        tick = int(scenario.kernel.world.tick)
        if promote and injection is None and tick >= int(args.inject_at):
            chosen = _promote_target(fresh, target)
            record = _find_memory_record(history, target, chosen["runner_up_action"]) if chosen else None
            if chosen is None or record is None:
                injection = {"status": "skipped_no_target", "target_selection": chosen}
            else:
                source = _source_action_event(history, target, record["tick"])
                promoted = scenario.promote_episode(target, record["ref"], float(args.importance),
                                                    [f"event:{source['seq']}" if source else "event:none",
                                                     f"tick:{record['tick']}", "injected:key-experience"])
                injection = {"status": "promoted", "at_tick": tick, "npc_id": target,
                             "ref": record["ref"], "kind_promoted": record["kind"],
                             "importance_at_write": record["importance_at_write"],
                             "importance_after": float(args.importance),
                             "memory_written_event_seq": record["seq"],
                             "source_event": source, "target_selection": chosen,
                             "store_before": promoted["before"], "store_after": promoted["after"]}
    decisions = [event for event in history if event["type"] == "npc.decision"]
    with_signals = [event for event in decisions
                    if (event["payload"].get("memory_influence") or {}).get("signals")]
    actions = [{"tick": int(event["tick"]), "action": event["payload"].get("action"),
                "target_entity": event["payload"].get("target_entity")}
               for event in history if event["type"] == "npc.action"]
    return {
        "name": name, "promote": promote, "ticks": int(args.ticks), "npc_ids": scenario.npc_ids,
        "injection": injection,
        "decisions": len(decisions), "decisions_with_signals": len(with_signals),
        "first_decision_with_signals": ({"tick": int(with_signals[0]["tick"]),
                                         "seq": int(with_signals[0]["seq"]),
                                         "influence": with_signals[0]["payload"].get("memory_influence"),
                                         "chosen_action": with_signals[0]["payload"].get("chosen_action"),
                                         "target_entity": with_signals[0]["payload"].get("target_entity")}
                                        if with_signals else None),
        "actions": actions, "state_hash": scenario.world.state_hash(),
        "event_count": len(history),
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    with_arm = run_arm(args, name="promote", promote=True)
    without_arm = run_arm(args, name="none", promote=False)
    key = lambda arm: [(item["tick"], item["action"], item["target_entity"]) for item in arm["actions"]]
    seq_with, seq_without = key(with_arm), key(without_arm)
    divergence = next(({"tick": a[0], "with": {"action": a[1], "target_entity": a[2]},
                        "without": {"action": b[1], "target_entity": b[2]}}
                       for a, b in zip(seq_with, seq_without) if a != b), None)
    ref = (with_arm["injection"] or {}).get("ref")
    document = {
        "status": "measured", "pack": args.pack, "seed": int(args.seed), "ticks": int(args.ticks),
        "inject_at": int(args.inject_at), "importance": float(args.importance),
        "injection": with_arm["injection"],
        "with_injection": {k: v for k, v in with_arm.items() if k not in ("actions", "injection")},
        "without_injection": {k: v for k, v in without_arm.items() if k not in ("actions", "injection")},
        "signal_ref_equals_promoted_ref": bool(ref is not None and with_arm["first_decision_with_signals"]
                                              and any(f"@ref={ref}" in signal for signal in
                                                      (with_arm["first_decision_with_signals"]["influence"] or {}).get("signals", []))),
        "first_divergence_after_injection": divergence,
        "counterexample_signals_empty_without_injection": without_arm["decisions_with_signals"] == 0,
        "action_sequences_identical": seq_with == seq_without,
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
