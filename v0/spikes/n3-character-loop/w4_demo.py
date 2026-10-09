#!/usr/bin/env python3
"""N3 阶段 B/W4：跨日 demo + 对照场景 + 同 seed 复跑（读真内核、真包；不注入、不 promote）。

用法:
  python3 w4_demo.py --root <v0_skeleton> --pack <pack_dir> --spike <spike_dir> --ticks 2880

臂：
  demo-1   交付包（已声明压力窗口）2880 tick，记忆链 + 能力链
  demo-2   同一命令复跑（AC-7 确定性）
  contrast-once   同 seed、**唯一变量 = npc-006.json 的压力声明是否存在**（存在臂）
  contrast-none   同上（缺失臂）—— 包副本落在 spike 目录，不改交付树
  short-none      缺失臂短跑（120 tick），用于「A==B（tick 数不是原因）」
不做任何注入 / promote；内核来自交付树（`--root`）。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def run_arm(root: Path, pack_dir: Path, out_dir: Path, ticks: int, seed: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / "kernel"))
    from deephealing_kernel.budget import BudgetLedger
    from deephealing_kernel.events import EventLog
    from deephealing_kernel.memory.store import MemoryStore
    from deephealing_kernel.pack import load_pack
    from deephealing_kernel.providers.cassette import CassetteReplayProvider, CassetteStore
    from deephealing_kernel.providers.deterministic_rule import DeterministicRuleProvider
    from deephealing_kernel.providers.local_model import LocalModelProvider
    from deephealing_kernel.providers.remote_api import RemoteApiProvider
    from deephealing_kernel.registry import CapabilityRegistry
    from deephealing_kernel.tick import WorldKernel

    pack = load_pack(pack_dir.resolve())
    caps_dir = root / "capabilities"
    store_c = CassetteStore(out_dir / "cassettes")
    registry = CapabilityRegistry(caps_dir, caps_dir / "pins.json", cassette_store=store_c,
                                  clock=time.monotonic, replay_mode=False)
    registry.register_adapter("remote_api", RemoteApiProvider())
    registry.register_adapter("local_model", LocalModelProvider())
    registry.register_adapter("deterministic_rule", DeterministicRuleProvider())
    registry.register_adapter("cassette_replay", CassetteReplayProvider(store_c))
    registry.discover()
    validation = registry.validate()
    memory = MemoryStore(out_dir / "kernel_memory.sqlite", write_enabled=True)
    memory.init_schema()
    events_path = out_dir / "events.jsonl"
    kernel = WorldKernel(
        pack=pack, seed=seed, log=EventLog(events_path), snapshot_every=0,
        memory_store=memory,
        capability_registry=registry,
        budget_ledger=BudgetLedger(day_ticks=1440, per_tick_calls=7, per_npc_daily_tokens=20000),
    )
    started = time.time()
    kernel.run(ticks)
    elapsed = time.time() - started
    calls = [c for c in registry.calls if c.get("slot") == "emotion.appraise"]
    return {
        "arm_dir": str(out_dir),
        "events": str(events_path),
        "ticks": ticks,
        "seed": seed,
        "wall_clock_s": round(elapsed, 3),
        "declarations": kernel.experience_pressures,
        "registry_validation_errors": validation,
        "emotion_appraise_calls": len(calls),
        "emotion_appraise_fallback_calls": sum(1 for c in calls if c.get("fallback_reason")),
        "emotion_fallbacks_total": len(kernel.emotion_fallbacks_log),
        "state_hash": kernel.state_hash(),
        "ticks_done": kernel.ticks_done,
    }


def make_undeclared_copy(root: Path, pack_dir: Path, target: Path) -> Path:
    """把包复制到 spike 目录并**摘掉** `pressure_window`（唯一变量），重签 pack.sig。"""
    sys.path.insert(0, str(root / "tools"))
    import pack_sign
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(pack_dir, target)
    path = target / "npcs" / "npc-006.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    for entry in document["key_events"]:
        entry.pop("pressure_window", None)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pack_sign.write_signature(target, pack_sign.build_signature(target))
    return target


def rows(path: Path) -> list[list]:
    out = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            out.append([event["tick"], event["type"], event["actor"],
                        json.dumps(event["payload"], sort_keys=True)])
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--spike", required=True)
    parser.add_argument("--ticks", type=int, default=2880)
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--json", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    pack_dir = Path(args.pack).resolve()
    spike = Path(args.spike).resolve()
    spike.mkdir(parents=True, exist_ok=True)

    undeclared = make_undeclared_copy(root, pack_dir, spike / "pack-undeclared" / pack_dir.name)

    arms: dict[str, dict] = {}
    plan = [
        ("demo-1", pack_dir, args.ticks),
        ("demo-2", pack_dir, args.ticks),
        ("contrast-on", pack_dir, args.ticks),
        ("contrast-off", undeclared, args.ticks),
        ("short-off", undeclared, 120),
    ]
    for name, pack_path, ticks in plan:
        arms[name] = run_arm(root, pack_path, spike / name, ticks, args.seed)
        print(f"{name}: calls={arms[name]['emotion_appraise_calls']} "
              f"fallbacks={arms[name]['emotion_fallbacks_total']} "
              f"wall={arms[name]['wall_clock_s']}s", flush=True)

    on_rows = rows(Path(arms["contrast-on"]["events"]))
    off_rows = rows(Path(arms["contrast-off"]["events"]))
    first_div = next((index for index, (a, b) in enumerate(zip(on_rows, off_rows)) if a != b), None)
    divergence = {
        "index": first_div,
        "tick": on_rows[first_div][0] if first_div is not None else None,
        "type": on_rows[first_div][1] if first_div is not None else None,
        "on": on_rows[first_div][3] if first_div is not None else None,
        "off": off_rows[first_div][3] if first_div is not None else None,
        "prefix_identical": all(a == b for a, b in zip(on_rows[:first_div or 0], off_rows[:first_div or 0])),
    }
    short_rows = rows(Path(arms["short-off"]["events"]))
    tick_independence = {
        "prefix_identical": short_rows == off_rows[:len(short_rows)],
        "short_rows": len(short_rows),
    }
    determinism = {
        "events_byte_identical": Path(arms["demo-1"]["events"]).read_bytes()
        == Path(arms["demo-2"]["events"]).read_bytes(),
        "state_hash_equal": arms["demo-1"]["state_hash"] == arms["demo-2"]["state_hash"],
        "calls_equal": arms["demo-1"]["emotion_appraise_calls"] == arms["demo-2"]["emotion_appraise_calls"],
    }

    readings = {"arms": arms, "first_divergence": divergence,
                "tick_number_is_not_the_cause": tick_independence,
                "determinism": determinism,
                "undeclared_pack_dir": str(undeclared)}
    Path(args.json).write_text(json.dumps(readings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in readings.items() if k != "arms"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
