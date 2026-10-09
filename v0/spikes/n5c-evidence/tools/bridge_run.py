#!/usr/bin/env python3
"""N5-C 取证脚手架工具：驱动**取证桥**（`bridge_mem/kernel_bridge_mem.py`）跑一段脚本化序列。

用途：
  - 桥的**独立性冒烟**（不依赖 Node 宿主）；
  - 冻结桥 ↔ 取证桥的**语义等价**证明（`tools/bridge_equivalence.py` 用它分别跑两遍）。

用法（示例）：
    python3 tools/bridge_run.py --bridge <path/to/kernel_bridge.py> \
        --runtime-dir /tmp/n5c-eq/A --out /tmp/n5c-eq/A-out \
        --records /tmp/n5c-eq/A-records.jsonl --steps 3 --ticks 4 --intent-target npc-006 \
        [--memory-chain --capability-chain --replay --emotion-threshold 0.0] \
        [--ask-tasks --ask-degradations] [--extra frozen|new]

产物：
  - `--records` 指向的 JSONL（桥 stdout 原样逐行落盘 = 桥的**外部产物**，非宿主自报）；
  - stdout 末行：一行 JSON 摘要（records / kinds / bridge_meta / tasks_ack / degradations_ack）。

**只读交付面**：本工具自己不写交付树；桥按 `--runtime-dir` 复制交付树到 runtime（既有语义）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

WS = Path(__file__).resolve().parents[4]  # <workspace>（tools/ → n5c-evidence/ → spikes/ → v0/ → <ws>）


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", required=True, help="桥脚本路径（冻结桥或取证桥）")
    ap.add_argument("--runtime-dir", required=True)
    ap.add_argument("--out", default=None, help="取证桥的 --out（冻结桥不支持 ⇒ 不传）")
    ap.add_argument("--events", default=None)
    ap.add_argument("--records", required=True)
    ap.add_argument("--source", default=str(WS / "v0/02_source"))
    ap.add_argument("--pack", default="xingfu-xiaoqu-xuqin")
    ap.add_argument("--seed", type=int, default=20260921)
    ap.add_argument("--snapshot-every", type=int, default=1)
    ap.add_argument("--ticks", type=int, default=200, help="intent 之后推进的 tick 数")
    ap.add_argument("--steps", type=int, default=0, help="intent 之前推进的 tick 数")
    ap.add_argument("--intent-target", default=None)
    ap.add_argument("--intent-id", default="bridge-run-intent-1")
    ap.add_argument("--mode", default="participate")
    ap.add_argument("--extra", choices=["frozen", "new"], default="new")
    ap.add_argument("--memory-chain", action="store_true")
    ap.add_argument("--capability-chain", action="store_true")
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--emotion-threshold", type=float, default=None)
    ap.add_argument("--stub-remote-api", type=float, default=None)
    ap.add_argument("--ask-tasks", action="store_true")
    ap.add_argument("--ask-degradations", action="store_true")
    ap.add_argument("--timeout-s", type=float, default=240.0)
    return ap.parse_args()


class Reader(threading.Thread):
    """非阻塞读取桥的 stdout（逐行 JSON）。"""

    def __init__(self, stream) -> None:
        super().__init__(daemon=True)
        self.stream = stream
        self.records: list[dict] = []
        self.done = threading.Event()

    def run(self) -> None:
        for line in self.stream:
            line = line.strip()
            if not line:
                continue
            try:
                self.records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if self.records[-1].get("kind") == "bridge_stop":
                self.done.set()
                return
        self.done.set()

    def wait_kind(self, kind: str, timeout: float) -> dict | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for record in self.records:
                if record.get("kind") == kind:
                    return record
            time.sleep(0.02)
        return None

    def wait_count(self, kind: str, count: int, timeout: float) -> int:
        deadline = time.time() + timeout
        while time.time() < deadline:
            have = sum(1 for record in self.records if record.get("kind") == kind)
            if have >= count:
                return have
            time.sleep(0.02)
        return sum(1 for record in self.records if record.get("kind") == kind)


def main() -> int:
    args = parse_args()
    bridge = Path(args.bridge).resolve()
    runtime = Path(args.runtime_dir).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    records_path = Path(args.records).resolve()
    records_path.parent.mkdir(parents=True, exist_ok=True)

    source = Path(args.source).resolve()
    cmd = [
        sys.executable, "-B", str(bridge),
        "--kernel-src", str(source / "v0_skeleton" / "kernel"),
        "--pack-src", str(source / "v0_skeleton" / "districts" / args.pack),
        "--runtime-dir", str(runtime),
        "--seed", str(args.seed),
        "--snapshot-every", str(args.snapshot_every),
        "--ticks", str(args.ticks + args.steps + 4),
    ]
    if args.extra == "new":
        if args.out:
            cmd += ["--out", str(Path(args.out).resolve())]
        if args.events:
            cmd += ["--events", args.events]
        if args.memory_chain:
            cmd.append("--memory-chain")
        if args.capability_chain:
            cmd.append("--capability-chain")
        if args.replay:
            cmd.append("--replay")
        if args.emotion_threshold is not None:
            cmd += ["--emotion-pressure-threshold", str(args.emotion_threshold)]
        if args.stub_remote_api is not None:
            cmd += ["--stub-remote-api", str(args.stub_remote_api)]

    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
           "HOME": str(Path.home())}
    child = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
    assert child.stdin and child.stdout
    reader = Reader(child.stdout)
    reader.start()

    def send(payload: dict) -> None:
        try:
            child.stdin.write(json.dumps(payload) + "\n")
            child.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass  # 桥已退出 ⇒ 由 stderr / 退出码给出原因（不掩盖）

    send({"cmd": "step", "n": max(1, args.steps)})
    if args.intent_target:
        reader.wait_count("tick_meta", max(1, args.steps), 60.0)
        send({"cmd": "intent", "mode": args.mode,
              "intent": {"id": args.intent_id, "kind": "delegate_instruction",
                         "target": args.intent_target}})
        reader.wait_kind("intent_ack", 60.0)
    send({"cmd": "step", "n": max(1, args.ticks)})
    reader.wait_count("tick_meta", max(1, args.steps) + max(1, args.ticks), args.timeout_s)
    if args.ask_tasks:
        send({"cmd": "tasks"})
        reader.wait_kind("tasks_ack", 30.0)
    if args.ask_degradations:
        send({"cmd": "degradations"})
        reader.wait_kind("degradations_ack", 30.0)
    send({"cmd": "stop"})
    reader.done.wait(60.0)

    try:
        child.stdin.close()
    except BrokenPipeError:
        pass
    try:
        child.wait(timeout=30)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=10)

    records = reader.records
    kinds: dict[str, int] = {}
    for record in records:
        kind = str(record.get("kind"))
        kinds[kind] = kinds.get(kind, 0) + 1

    with records_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def first(kind: str):
        return next((record for record in records if record.get("kind") == kind), None)

    summary = {
        "bridge": str(bridge), "runtime_dir": str(runtime), "extra": args.extra,
        "records": len(records), "kinds": kinds, "records_path": str(records_path),
        "exit_code": child.returncode,
        "bridge_meta": first("bridge_meta"),
        "tasks_ack": first("tasks_ack"),
        "degradations_ack": first("degradations_ack"),
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")
    stderr = child.stderr.read() if child.stderr else ""
    if stderr.strip():
        sys.stderr.write(stderr)
    return 0 if child.returncode in (0, None) else 1


if __name__ == "__main__":
    raise SystemExit(main())
