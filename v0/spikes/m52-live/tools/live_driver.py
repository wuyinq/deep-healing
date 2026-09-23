#!/usr/bin/env python3
"""AC-5 实机驱动（spikes/** 脚手架，**非交付面**）：stdin 收命令、stdout 吐记录。

与 `session/bridge/kernel_bridge.py` 同形（命令：`{"cmd":"step","n":1}` / `{"cmd":"snapshot"}` /
`{"cmd":"stop"}`；记录：`tick_meta` / `snapshot` / `delta` / `bridge_meta` / `bridge_stop`），
**并补两件桥没有的事**：
  1. `event` 记录 —— 逐 tick 读内核真实事件日志的新增行，原样转发（桥无 emit 点，见 06 的 GAP）；
  2. `live` 记录 —— 内核自带 `LiveWorld` 的只读投影（世界钟 / state_hash / 状态），供 SSE 通道；
  3. `inject_result` —— **注入读数**（`--inject key` 时）：把「关键经历」写进库，并报出它的 ref、
     它引用的**真实事件 seq**、importance（W11 因果链的记忆节点来源）。

用法（workdir `<ws>`）：
    PYTHONDONTWRITEBYTECODE=1 python3 spikes/m52-live/tools/live_driver.py \
        --source 02_source --runtime spikes/m52-live/runtime/live-a \
        --pack xingfu-xiaoqu-xuqin --seed 20260921 --snapshot-every 25 \
        --memory-writes on --inject key --inject-at 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from live_scenario import Scenario, emit  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M5.2 r2 · AC-5 实机驱动（真内核 + 真内容包）")
    parser.add_argument("--source", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--pack", default="xingfu-xiaoqu-xuqin")
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--snapshot-every", type=int, default=25)
    parser.add_argument("--memory-writes", choices=("on", "off"), default="on")
    parser.add_argument("--inject", choices=("none", "promote", "preseed"), default="none")
    parser.add_argument("--inject-at", type=int, default=20)
    parser.add_argument("--inject-kind", default="walk")
    parser.add_argument("--inject-importance", type=float, default=0.95)
    return parser.parse_args(argv)


def _promote_target(events: list[dict], npc_id: str) -> dict | None:
    """选注入对象（**显式规则，可复算**）：取本 tick 该 NPC `npc.decision.utility_ranking`
    的**第二名**动作（runner-up），再回找**最近一条**该动作的 `memory.written`（episodic）记录。

    理由：被提升权重的经历必须是**真做过**的动作（记录来自内核自产），且要能**改变**选择
    （对已选中的动作加权只会强化原选择 ⇒ 取 runner-up）。
    """
    decision = next((event for event in reversed(events)
                     if event["type"] == "npc.decision" and event["actor"] == npc_id), None)
    if decision is None:
        return None
    ranking = decision["payload"].get("utility_ranking") or []
    if len(ranking) < 2:
        return None
    runner_up = str(ranking[1].get("action") or "")
    if not runner_up:
        return None
    return {"decision_tick": int(decision["tick"]), "decision_seq": int(decision["seq"]),
            "chosen_action": decision["payload"].get("chosen_action"),
            "utility_ranking": [{"action": item.get("action"), "score": item.get("score")}
                                for item in ranking],
            "runner_up_action": runner_up}


def _find_memory_record(events: list[dict], npc_id: str, kind: str) -> dict | None:
    """回找**最近一条** `kind` 的 `memory.written`（`layer=episodic`）记录。"""
    for event in reversed(events):
        if event["type"] != "memory.written" or event["actor"] != npc_id:
            continue
        payload = event["payload"]
        if payload.get("layer") != "episodic" or str(payload.get("kind")) != kind:
            continue
        return {"ref": int(payload.get("ref")), "tick": int(event["tick"]),
                "seq": int(event["seq"]), "importance_at_write": payload.get("importance"),
                "kind": kind}
    return None


def _source_action_event(events: list[dict], npc_id: str, tick: int) -> dict | None:
    """该记忆记录所「记得」的那件事：同 tick 的 `npc.action` 事件。"""
    for event in reversed(events):
        if event["type"] == "npc.action" and event["actor"] == npc_id and int(event["tick"]) == int(tick):
            return {"seq": int(event["seq"]), "tick": int(event["tick"]),
                    "action": event["payload"].get("action"),
                    "target_entity": event["payload"].get("target_entity")}
    return None


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    scenario = Scenario(source_root=Path(args.source), runtime_dir=Path(args.runtime),
                        pack_name=args.pack, seed=args.seed, snapshot_every=args.snapshot_every,
                        memory_writes=args.memory_writes == "on")
    emit(scenario.bridge_meta(pack_name=args.pack, seed=args.seed,
                              snapshot_every=args.snapshot_every))
    # **内核构造期事件**（`world.init` 等，tick 0）在第一次 `step` 之前就已落日志；这里**先排空一次**，
    # 否则它们在 backlog 里缺席 ⇒ 页面在 connect 时拿不到，而 reload 后（走 backlog）拿得到
    # ⇒ AC-5④ 的「事件条数」会差 1（实测 121 vs 122）。
    for event in scenario.drain_events():
        emit({"kind": "event", "tick": int(event.get("tick", 0)), "seq": 0, "event": event})
    emit({"kind": "ready", "tick": 0, "seq": 0, "pack": args.pack, "seed": int(args.seed),
          "inject": args.inject, "inject_at": int(args.inject_at),
          "memory_writes": args.memory_writes, "npc_ids": scenario.npc_ids})

    inject_pending = args.inject != "none"
    history: list[dict] = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            command = json.loads(line)
        except json.JSONDecodeError as error:
            emit({"kind": "error", "tick": int(scenario.kernel.world.tick), "seq": 0,
                  "reason": "E_SCHEMA_INVALID", "detail": str(error)})
            continue
        name = str(command.get("cmd", ""))
        if name == "step":
            count = int(command.get("n", 1))
            for _ in range(max(0, count)):
                fresh = scenario.step(1)
                history.extend(fresh)
                if len(history) > 20000:
                    history = history[-10000:]
                tick = int(scenario.kernel.world.tick)
                if inject_pending and tick >= int(args.inject_at):
                    inject_pending = False
                    target = scenario.npc_ids[0]
                    if args.inject == "preseed":
                        ref = scenario.inject_episode(
                            target, tick, str(args.inject_kind), float(args.inject_importance),
                            ["injected:key-experience"], f"injected:key-experience:{args.inject_kind}")
                        emit({"kind": "inject_result", "tick": tick, "seq": 0, "mode": "preseed",
                              "npc_id": target, "ref": ref,
                              "importance": float(args.inject_importance),
                              "note": "库级新增记录（AC-4 口径）；无对应 memory.written 事件"})
                    else:
                        chosen = _promote_target(fresh, target)
                        record = (_find_memory_record(history, target, chosen["runner_up_action"])
                                  if chosen else None)
                        if chosen is None or record is None:
                            emit({"kind": "inject_result", "tick": tick, "seq": 0, "mode": "promote",
                                  "npc_id": target, "status": "skipped_no_target",
                                  "target_selection": chosen,
                                  "note": "本 tick 找不到可提升的 runner-up 经历 ⇒ 未注入（如实报，不伪造）"})
                        else:
                            source = _source_action_event(history, target, record["tick"])
                            promoted = scenario.promote_episode(
                                target, record["ref"], float(args.inject_importance),
                                [f"event:{source['seq']}" if source else "event:none",
                                 f"tick:{record['tick']}", "injected:key-experience"])
                            emit({"kind": "inject_result", "tick": tick, "seq": 0, "mode": "promote",
                                  "npc_id": target, "status": "promoted",
                                  "ref": record["ref"], "layer": "episodic",
                                  "kind_promoted": record["kind"],
                                  "importance_at_write": record["importance_at_write"],
                                  "importance_after": float(args.inject_importance),
                                  "memory_written_event_seq": record["seq"],
                                  "source_event": source, "target_selection": chosen,
                                  "store_before": promoted["before"], "store_after": promoted["after"],
                                  "note": ("库级提升一条**内核自产**经历的权重（AC-4 预置关键经历的等价形态）；"
                                           "事件 payload 里的 importance 是写入时刻的值 ⇒ 与库内当前值**有意不同**，"
                                           "这正是注入的可核验痕迹")})
            continue
        if name == "snapshot":
            projection = scenario.projection()
            emit({"kind": "snapshot", "tick": int(scenario.kernel.world.tick), "seq": 0,
                  "state": projection["state"], "state_hash": projection["state_hash"]})
            continue
        if name == "stop":
            emit({"kind": "bridge_stop", "tick": int(scenario.kernel.world.tick), "seq": 0,
                  "state_hash": scenario.world.state_hash(),
                  "chain_tail": scenario.world.event_chain_hash(),
                  "ticks_done": int(scenario.kernel.ticks_done)})
            return 0
        emit({"kind": "error", "tick": int(scenario.kernel.world.tick), "seq": 0,
              "reason": "E_SCHEMA_INVALID", "detail": f"unknown cmd {name!r}"})
    emit({"kind": "bridge_stop", "tick": int(scenario.kernel.world.tick), "seq": 0,
          "state_hash": scenario.world.state_hash(), "chain_tail": scenario.world.event_chain_hash(),
          "ticks_done": int(scenario.kernel.ticks_done)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
