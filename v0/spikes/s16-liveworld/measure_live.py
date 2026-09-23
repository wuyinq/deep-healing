#!/usr/bin/env python3
"""M4 活的世界真跑读数（spike；AC-M4-9 ①~⑦ / AC-M4-10 ①②③）。

运行：PYTHONDONTWRITEBYTECODE=1 python3 spikes/s16-liveworld/measure_live.py
产物：`spikes/s16-liveworld/logs/*.json`（原始读数；判定在 `03` / `V0_SELF_TEST.md` 里引用）。

**本脚本不是交付面**（`spikes/**`）；它只调用交付实现，不复制实现。
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
KERNEL = WORKSPACE / "02_source" / "v0_skeleton" / "kernel"
PACK = WORKSPACE / "02_source" / "v0_skeleton" / "districts" / "xingfu-xiaoqu"
LOGS = HERE / "logs"
RUNTIME = HERE / "runtime"
LOGS.mkdir(parents=True, exist_ok=True)
RUNTIME.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(KERNEL))

from deephealing_kernel import world_clock  # noqa: E402
from deephealing_kernel.events import EventLog  # noqa: E402
from deephealing_kernel.live import LiveServer, LiveWorld  # noqa: E402
from deephealing_kernel.pack import load_pack  # noqa: E402
from deephealing_kernel.tick import WorldKernel  # noqa: E402

SEED = 20260921


def write(name: str, payload: dict) -> None:
    path = LOGS / name
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    print(f"wrote {path}", flush=True)


def build(name: str, *, pace: float, warmup: bool, max_observers: int = 8):
    out = RUNTIME / name
    out.mkdir(parents=True, exist_ok=True)
    kernel = WorldKernel(pack=load_pack(PACK), seed=SEED, log=EventLog(out / "events.jsonl"),
                         snapshot_every=0, checkpoint_dir=None)
    sem = world_clock.derive_clock_semantics(load_pack(PACK))
    wall = world_clock.now_utc8()
    warmup_ticks = world_clock.warmup_ticks(wall, sem) if warmup else 0
    if warmup_ticks:
        kernel.run(warmup_ticks)
    world = LiveWorld(kernel, sem=sem, pace_s_per_tick=pace, warmup=warmup_ticks,
                      max_observers=max_observers)
    return kernel, sem, world, wall, warmup_ticks


# ---------------------------------------------------------------------------- ②a 锚定
def anchor() -> None:
    kernel, sem, world, wall, warmup = build("anchor", pace=1.0, warmup=True)
    reading = world.clock()
    wall_minutes = wall.hour * 60 + wall.minute
    reading_minutes = world_clock.clock_minutes(world.tick, sem)
    write("clock-anchor.json", {
        "wall_clock_utc8": wall.strftime("%H:%M:%S"),
        "wall_minutes_into_day": wall_minutes,
        "tick0_minutes": sem["tick0_minutes"],
        "day_ticks": sem["day_ticks"],
        "warmup_formula": f"(({wall_minutes}) - {sem['tick0_minutes']}) mod {sem['day_ticks']}",
        "warmup_ticks": warmup,
        "world_clock_after_fastforward": reading,
        "world_tick": world.tick,
        "delta_minutes": abs(reading_minutes - wall_minutes),
        "criterion": "②a 锚定精度：|世界钟 − 墙上钟| ≤ 1 分钟",
        "passed": abs(reading_minutes - wall_minutes) <= 1,
        "clock_semantics_source": sem["source"],
        "clock_semantics_raw": sem["raw"],
    })


# ---------------------------------------------------------------------------- ③ 节流 1×
def pace_short() -> None:
    kernel, sem, world, wall, warmup = build("pace60", pace=1.0, warmup=True)
    started = time.monotonic()
    before = world.tick
    loop = world.advance_loop(max_ticks=60)
    elapsed = time.monotonic() - started
    delta = world.tick - before
    write("pace-1x-60s.json", {
        "window_real_seconds": round(elapsed, 3),
        "tick_delta": delta,
        "max_drift_ms": loop["max_drift_ms"],
        "clock_before": world_clock.clock_of(before, sem),
        "clock_after": world_clock.clock_of(world.tick, sem),
        "criterion": "③ 1× 档：N=60 真实秒 ⇒ tick 增量 60（容差 ≤1）",
        "passed": abs(delta - 60) <= 1,
    })
    # 负例：去掉节流（pace=0）⇒ 同一判据必须红
    kernel2, sem2, world2, _, _ = build("pace0", pace=0.0, warmup=False)
    started2 = time.monotonic()
    before2 = world2.tick
    world2.advance_loop(max_ticks=60)
    elapsed2 = time.monotonic() - started2
    delta2 = world2.tick - before2
    write("pace-1x-negative-no-throttle.json", {
        "window_real_seconds": round(elapsed2, 3),
        "tick_delta": delta2,
        "abs_delta_minus_seconds": abs(delta2 - elapsed2),
        "criterion": "负例：去掉节流 ⇒ |tick 增量 − 真实秒数| > 1（判据必须红）",
        "passed": abs(delta2 - elapsed2) > 1,
    })


# ---------------------------------------------------------------------------- ②b/②c 长窗口
def pace_long(window: int = 300) -> None:
    kernel, sem, world, wall, warmup = build("pace300", pace=1.0, warmup=True)
    started = time.monotonic()
    before = world.tick
    loop = world.advance_loop(max_ticks=window)
    elapsed = time.monotonic() - started
    delta = world.tick - before
    now = world_clock.now_utc8()
    world_minutes = world_clock.clock_minutes(world.tick, sem)
    wall_minutes = now.hour * 60 + now.minute
    offset = (world_minutes - wall_minutes) % (24 * 60)
    write("pace-1x-300s.json", {
        "window_real_seconds": round(elapsed, 3),
        "tick_delta": delta,
        "abs_delta_minus_seconds": round(abs(delta - elapsed), 6),
        "max_drift_ms": loop["max_drift_ms"],
        "clock_before": world_clock.clock_of(before, sem),
        "clock_after": world_clock.clock_of(world.tick, sem),
        "criterion_2b": "②b 跨 ≥300 真实秒：|tick 增量 − 真实秒数| ≤ 1",
        "passed_2b": abs(delta - elapsed) <= 1.0 and elapsed >= window - 1,
        "criterion_2c": "②c 如实披露：世界钟读数 − 墙上钟读数（1× 档 300 秒约 +295 分钟，**属预期**）",
        "raw_clock_offset_minutes": offset,
        "wall_clock_utc8": now.strftime("%H:%M:%S"),
    })


# ---------------------------------------------------------------------------- ①/⑤ 观察者
def observers() -> None:
    kernel, sem, world, wall, warmup = build("observers", pace=0.02, warmup=False)
    stop = threading.Event()
    thread = threading.Thread(target=lambda: world.advance_loop(stop_event=stop), daemon=True)
    thread.start()
    time.sleep(1.0)

    def snapshot(label: str) -> dict:
        return {"label": label, "tick": world.tick, "clock": world.clock(),
                "observers": world.observers(), "at": time.strftime("%H:%M:%S")}

    server = LiveServer(world, bind="127.0.0.1", port=0, allow_remote=False).start()
    connections = []

    def connect():
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
        conn.request("GET", "/live/stream")
        response = conn.getresponse()
        chunk = response.read(200)
        connections.append(conn)
        return chunk

    with_observers = []
    for _ in range(2):
        connect()
    time.sleep(0.5)
    with_observers.append(snapshot("two_observers_connected"))
    time.sleep(2.0)
    with_observers.append(snapshot("two_observers_after_2s"))

    for conn in connections:
        conn.close()
    time.sleep(0.8)
    zero_observers = [snapshot("all_observers_disconnected")]
    time.sleep(2.0)
    zero_observers.append(snapshot("after_2s_with_zero_observers"))

    stop.set()
    thread.join(timeout=10)
    server.stop()
    write("observer-independence.json", {
        "with_two_observers": with_observers,
        "with_zero_observers": zero_observers,
        "delta_with_two": with_observers[1]["tick"] - with_observers[0]["tick"],
        "delta_with_zero": zero_observers[1]["tick"] - zero_observers[0]["tick"],
        "criterion_1": "① 断开**所有**观察者后世界继续推进（observers == 0 且 tick 增长）",
        "passed_1": zero_observers[1]["tick"] > zero_observers[0]["tick"]
                    and zero_observers[1]["observers"] == 0,
        "criterion_5": "⑤ 观察者独立性：0 个 vs 2 个观察者的同一窗口 tick 增量相同",
        "passed_5": abs((with_observers[1]["tick"] - with_observers[0]["tick"])
                        - (zero_observers[1]["tick"] - zero_observers[0]["tick"])) <= 3,
        "connection_accounting": "连接数由本进程自记账（不信服务端自报）",
    })


# ---------------------------------------------------------------------------- ⑦ 停止/恢复
def resume() -> None:
    out = RUNTIME / "resume"
    out.mkdir(parents=True, exist_ok=True)
    sem = world_clock.derive_clock_semantics(load_pack(PACK))

    kernel = WorldKernel(pack=load_pack(PACK), seed=SEED, log=EventLog(out / "run1.jsonl"),
                         snapshot_every=0, checkpoint_dir=None)
    kernel.run(120)
    state_hash_stop = kernel.state_hash()
    chain_tail_stop = kernel.log.last_hash
    sealed = {"tick": kernel.world.tick, "state_hash": state_hash_stop,
              "event_chain_hash": chain_tail_stop, "seed": SEED,
              "pack_id": "xingfu-xiaoqu", "pack_version": "0.1.0"}
    (out / "live_state.json").write_text(json.dumps(sealed, sort_keys=True) + "\n", encoding="utf-8")

    # 恢复：同 seed + 同 pack + 快进到同一 tick
    resumed = WorldKernel(pack=load_pack(PACK), seed=SEED, log=EventLog(out / "run2.jsonl"),
                          snapshot_every=0, checkpoint_dir=None)
    resumed.run(120)
    write("resume-roundtrip.json", {
        "stopped": sealed,
        "resumed": {"tick": resumed.world.tick, "state_hash": resumed.state_hash(),
                    "event_chain_hash": resumed.log.last_hash},
        "criterion_state": "⑦ 停止前 state_hash == 恢复后同 tick state_hash（逐位相同）",
        "passed_state": resumed.state_hash() == state_hash_stop,
        "honest_boundary": "恢复后事件日志是**新链**（chain_tail 不同）—— 本判据**不**覆盖事件链连续",
        "event_chain_differs": resumed.log.last_hash != chain_tail_stop,
        "clock_after_resume": world_clock.clock_of(resumed.world.tick, sem),
    })


def main() -> int:
    anchor()
    pace_short()
    observers()
    resume()
    pace_long(300)
    print("MEASURE_LIVE_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
