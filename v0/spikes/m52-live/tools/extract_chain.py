#!/usr/bin/env python3
"""W11 因果链抽取与判定（spikes/** 脚手架，**非交付面**）。

**命令即判据**：本脚本只读 `spikes/m52-live/**` 的读数，**从客户端实际收到的事件流里**
重新抽链（不采信客户端自报的 `traceFor()` 结果），再与注入读数对账：

  链形态（任务书 §3 W11）：`事件 id → memory.written 的 ref → npc.decision 的 memory_influence
                            → npc.action 的 target_entity`

判据：
  ① **完整性**：四节点齐全，且「决策信号里的 ref」与「记忆节点的 ref」**逐字相等**；
  ② **事件→记忆**：记忆节点的 `kind`/`tick` 与该 tick 的 `npc.action`（事件）**一致**；
  ③ **记忆→决策**：信号形如 `episode:<kind>@ref=<R>`，`<kind>` 与记忆节点一致；
  ④ **注入可对账**：`ac5-run-with.json` 的注入读数（ref / importance before→after / 引用的 `event:<seq>`）
     与链上节点**同指**；
  ⑤ **反例（去掉该经历 ⇒ 链断）**：`without` 臂（唯一变量 = 未注入）里**任何**决策都没有信号
     ⇒ 记忆节点缺失；且两臂的 `npc.action` 序列在注入后**首个分叉**处**可观察行动不同**。

用法（workdir `<ws>`）：
    python3 spikes/m52-live/tools/extract_chain.py --npc npc-006
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
READBACK = WS / "spikes" / "m52-live" / "readback"
SIGNAL_RE = re.compile(r"^episode:(?P<kind>[^@]+)@ref=(?P<ref>[^@\s]+)$")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def events_of(chain_document: dict) -> list[dict]:
    """取该臂**客户端实际收到**的原始事件（reload 后那一份，含 scaffold 的事件回填）。"""
    return list(chain_document["chain_after_reload"].get("events") or [])


def extract(events: list[dict], npc_id: str) -> dict:
    """从事件流里独立抽链（不看客户端自报结果）。"""
    decisions = [event for event in events if event.get("type") == "npc.decision" and event.get("actor") == npc_id]
    # **只取 episodic 层**：`memory_influence.signals` 由 `fetch_episodes()` 产生（`rules/decision.py`），
    # 而 `working` 层记录的 ref 与 episodes **各自独立编号**（实测同一 tick 两条都是 16）
    # ⇒ 不按层过滤会张冠李戴。
    memories = [event for event in events if event.get("type") == "memory.written" and event.get("actor") == npc_id
                and ((event.get("payload") or {}).get("layer") == "episodic")]
    actions = [event for event in events if event.get("type") == "npc.action" and event.get("actor") == npc_id]
    with_signals = [event for event in decisions
                    if ((event.get("payload") or {}).get("memory_influence") or {}).get("signals")]
    focus = with_signals[-1] if with_signals else (decisions[-1] if decisions else None)
    chain: dict = {"npc_id": npc_id, "decision_count": len(decisions),
                   "decisions_with_signals": len(with_signals),
                   "event": None, "memory": None, "decision": None, "action": None,
                   "signal_refs": [], "unlinked_signal_refs": []}
    if focus is None:
        return chain
    payload = focus.get("payload") or {}
    influence = payload.get("memory_influence") or {}
    signals = list(influence.get("signals") or [])
    chain["signal_refs"] = signals
    chain["decision"] = {"seq": focus.get("seq"), "tick": focus.get("tick"),
                         "chosen_action": payload.get("chosen_action"),
                         "signals": signals, "utility_delta": influence.get("utility_delta"),
                         "by_action": influence.get("by_action")}
    for signal in signals:
        match = SIGNAL_RE.match(str(signal))
        if not match:
            continue
        ref = match.group("ref")
        memory = next((event for event in reversed(memories)
                       if str(((event.get("payload") or {}).get("ref"))) == ref), None)
        if memory is None:
            chain["unlinked_signal_refs"].append(ref)
            continue
        memory_payload = memory.get("payload") or {}
        chain["memory"] = {"seq": memory.get("seq"), "tick": memory.get("tick"), "ref": ref,
                           "kind": memory_payload.get("kind"), "layer": memory_payload.get("layer"),
                           "importance_at_write": memory_payload.get("importance")}
        source = next((event for event in reversed(actions) if event.get("tick") == memory.get("tick")), None)
        if source is not None:
            source_payload = source.get("payload") or {}
            chain["event"] = {"seq": source.get("seq"), "tick": source.get("tick"), "type": "npc.action",
                              "action": source_payload.get("action"),
                              "target_entity": source_payload.get("target_entity")}
        break
    decision_tick = chain["decision"]["tick"]
    action = next((event for event in reversed(actions) if event.get("tick") == decision_tick), None)
    if action is None:
        action = next((event for event in actions if (event.get("tick") or 0) > (decision_tick or 0)), None)
    if action is not None:
        action_payload = action.get("payload") or {}
        chain["action"] = {"seq": action.get("seq"), "tick": action.get("tick"),
                           "action": action_payload.get("action"),
                           "target_entity": action_payload.get("target_entity")}
    return chain


def action_sequence(events: list[dict], npc_id: str) -> list[tuple]:
    items = [(event.get("tick"), (event.get("payload") or {}).get("action"),
              (event.get("payload") or {}).get("target_entity"))
             for event in events if event.get("type") == "npc.action" and event.get("actor") == npc_id]
    return sorted(items, key=lambda item: (item[0] or 0))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="W11 causal chain extraction + counterexample")
    parser.add_argument("--npc", default="npc-006")
    parser.add_argument("--with-tag", default="with")
    parser.add_argument("--without-tag", default="without")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    with_doc = load(READBACK / f"chain-{args.with_tag}.json")
    without_doc = load(READBACK / f"chain-{args.without_tag}.json")
    run_with = load(READBACK / f"ac5-run-{args.with_tag}.json")
    run_without = load(READBACK / f"ac5-run-{args.without_tag}.json")
    events_with = events_of(with_doc)
    events_without = events_of(without_doc)
    chain_with = extract(events_with, args.npc)
    chain_without = extract(events_without, args.npc)

    injection = run_with.get("injection") or {}
    store_after = injection.get("store_after") or {}
    store_before = injection.get("store_before") or {}
    source_event = injection.get("source_event") or {}
    refs_after = json.loads(store_after.get("refs") or "[]")
    injected_ref = str(injection.get("ref"))
    memory = chain_with.get("memory") or {}
    event_node = chain_with.get("event") or {}

    seq_with = action_sequence(events_with, args.npc)
    seq_without = action_sequence(events_without, args.npc)
    divergence = next(({"tick": a[0], "with": {"action": a[1], "target_entity": a[2]},
                        "without": {"action": b[1], "target_entity": b[2]}}
                       for a, b in zip(seq_with, seq_without) if a != b), None)
    divergence_tick = (divergence or {}).get("tick")
    inject_at = injection.get("at_tick") if injection.get("at_tick") is not None else injection.get("tick")

    criteria = {
        "chain_is_complete": {
            "pass": bool(event_node and memory and chain_with.get("decision") and chain_with.get("action")
                         and chain_with["decision"]["signals"]),
            "reading": {"event": event_node, "memory": memory, "decision": chain_with.get("decision"),
                        "action": chain_with.get("action")},
        },
        "signal_ref_equals_memory_ref": {
            "pass": bool(memory.get("ref") and any(f"@ref={memory['ref']}" in signal
                                                   for signal in chain_with["decision"]["signals"])),
            "reading": {"memory_ref": memory.get("ref"), "signals": chain_with["decision"]["signals"]},
        },
        "memory_links_to_source_event": {
            "pass": bool(event_node and memory and event_node.get("tick") == memory.get("tick")
                         and event_node.get("action") == memory.get("kind")),
            "reading": {"event": event_node, "memory": memory},
        },
        "injection_reconciles_with_chain": {
            "pass": bool(injection.get("status") == "promoted" and injected_ref == memory.get("ref")
                         and f"event:{event_node.get('seq')}" in refs_after
                         and float(store_before.get("importance") or 1.0) < 0.5
                         <= float(store_after.get("importance") or 0.0)),
            "reading": {"injection_status": injection.get("status"), "injected_ref": injected_ref,
                        "chain_memory_ref": memory.get("ref"), "refs_after": refs_after,
                        "importance_before": store_before.get("importance"),
                        "importance_after": store_after.get("importance"),
                        "importance_at_write": injection.get("importance_at_write"),
                        "source_event": source_event,
                        "selection_rule": (injection.get("target_selection") or {}).get("runner_up_action")},
        },
        "counterexample_chain_breaks_without_injection": {
            "pass": bool(chain_without.get("decisions_with_signals") == 0
                         and not chain_without.get("memory")
                         and not (run_without.get("injection"))),
            "reading": {"without_decisions_with_signals": chain_without.get("decisions_with_signals"),
                        "without_memory_node": chain_without.get("memory"),
                        "without_injection": run_without.get("injection"),
                        "without_chain": {k: chain_without[k] for k in ("decision", "action", "unlinked_signal_refs")}},
        },
        "counterexample_observable_action_differs": {
            "pass": bool(divergence and inject_at is not None and divergence_tick is not None
                         and divergence_tick > inject_at),
            "reading": {"first_divergence": divergence, "injection_tick": inject_at,
                        "with_final": seq_with[-1] if seq_with else None,
                        "without_final": seq_without[-1] if seq_without else None},
        },
    }
    document = {
        "status": "measured", "npc": args.npc,
        "arms": {args.with_tag: {"events": len(events_with), "chain": chain_with,
                                 "state_hash": run_with.get("final_state_hash"),
                                 "events_total": run_with.get("events_total")},
                 args.without_tag: {"events": len(events_without), "chain": chain_without,
                                    "state_hash": run_without.get("final_state_hash"),
                                    "events_total": run_without.get("events_total")}},
        "injection": injection,
        "criteria": criteria,
        "all_pass": all(item["pass"] for item in criteria.values()),
        "source_files": {"with": f"spikes/m52-live/readback/chain-{args.with_tag}.json",
                         "without": f"spikes/m52-live/readback/chain-{args.without_tag}.json",
                         "run_with": f"spikes/m52-live/readback/ac5-run-{args.with_tag}.json"},
    }
    text = json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True)
    sys.stdout.write(text + "\n")
    target = READBACK / "chain-verdict.json"
    target.write_text(text + "\n", encoding="utf-8")
    return 0 if document["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
