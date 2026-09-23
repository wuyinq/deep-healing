#!/usr/bin/env python3
"""F5′（r3）外部可连判据：`run --ws-port <n>` 运行期间**外部 socket 必须真的连上一次**。

**一条命令复跑**（workdir 任意）：

    python3 spikes/s16-liveworld/logs/m4-r3-wsport-probe.py

两个臂一起跑，exit 0 才算通过：

  - **正向**：`run --ws-port <空闲端口> --ticks 3000` **运行期间**，外部阻塞 `connect` 必须成功
    **且**读到一个合法响应（记状态行）；否则 exit 1。
  - **负向对照**：同一条判据在 `run --ws-port 0`（默认 = 不监听）下**必须红** ——
    0 次连入、全部 refused。**防「恒绿判据」**：如果负向臂也命中，说明探针在自欺。

探针写法（硬性 · architect 裁决 §6.3）：
  用**阻塞 `socket.connect`**（`socket.create_connection`）。**禁止**「先 `settimeout` 再
  `connect_ex`」—— `connect_ex` 在非阻塞/带超时下返回 `EINPROGRESS` 而非 0，会产生**假命中**
  （sentinel 第一版即被它骗过）。命中判据 = connect 成功 **且** 读到合法 HTTP 状态行，两者缺一不可。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[3] / "02_source" / "v0_skeleton" / "kernel"
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SEED = 20260921
REQUEST = b"GET /live/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def one_arm(*, ws_port: int, ticks: int, label: str, out_root: Path) -> dict:
    out_dir = out_root / label
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "deephealing_kernel", "run",
           "--pack", str(PACK_DIR), "--seed", str(SEED), "--ticks", str(ticks),
           "--events", str(out_dir / "events.jsonl"), "--ws-port", str(ws_port)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    started = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            cwd=str(KERNEL_ROOT), env=env)
    hits = 0
    refused = 0
    bad_response = 0
    first_status_line: str | None = None
    first_hit_at_s: float | None = None
    while proc.poll() is None:
        try:
            with socket.create_connection(("127.0.0.1", ws_port), timeout=0.3) as sock:
                sock.sendall(REQUEST)
                raw = b""
                while b"\r\n" not in raw:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    raw += chunk
        except (OSError, TimeoutError):
            refused += 1
            continue
        line = raw.split(b"\r\n", 1)[0].decode("utf-8", "replace")
        if line.startswith("HTTP/") and " 200" in line:
            hits += 1
            if first_status_line is None:
                first_status_line = line
                first_hit_at_s = round(time.monotonic() - started, 4)
        else:
            bad_response += 1
    stdout, stderr = proc.communicate()
    wall = time.monotonic() - started
    self_report = None
    for line in stdout.splitlines():
        if line.startswith("{"):
            try:
                self_report = json.loads(line).get("live_channel")
            except ValueError:
                self_report = None
    return {
        "label": label,
        "ws_port": ws_port,
        "ticks": ticks,
        "exit": proc.returncode,
        "loop_wall_s": round(wall, 3),
        "connect_hits": hits,
        "connect_refused": refused,
        "bad_response": bad_response,
        "first_status_line": first_status_line,
        "first_hit_at_s": first_hit_at_s,
        "run_self_reported_live_channel": self_report,
        "stderr_tail": stderr.strip().splitlines()[-3:],
    }


def main() -> int:
    global KERNEL_ROOT  # noqa: PLW0603 — 探针参数：可指向修前副本以复现 RED
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=3000)
    parser.add_argument("--kernel-root", default=str(KERNEL_ROOT),
                        help="被测内核目录（默认交付树；可指向修前副本做 RED 对照）")
    parser.add_argument("--root", default="/tmp/m4r3-wsport")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    KERNEL_ROOT = Path(args.kernel_root)
    out_root = Path(args.root)
    out_root.mkdir(parents=True, exist_ok=True)

    positive = one_arm(ws_port=free_port(), ticks=args.ticks, label="positive",
                       out_root=out_root)
    negative = one_arm(ws_port=0, ticks=args.ticks, label="negative", out_root=out_root)

    print("POSITIVE " + json.dumps(positive, ensure_ascii=False, sort_keys=True), flush=True)
    print("NEGATIVE " + json.dumps(negative, ensure_ascii=False, sort_keys=True), flush=True)

    failures: list[str] = []
    if positive["exit"] != 0:
        failures.append(f"正向臂 exit={positive['exit']}")
    if positive["connect_hits"] < 1:
        failures.append(f"正向臂 0 次外部连入（refused={positive['connect_refused']}）"
                        "⇒ 声明了一个外部无法观测的监听窗口")
    if not (positive["first_status_line"] or "").startswith("HTTP/"):
        failures.append(f"正向臂未读到合法响应首行：{positive['first_status_line']!r}")
    if negative["connect_hits"] != 0:
        failures.append(f"负向对照臂竟然连入 {negative['connect_hits']} 次 ⇒ 判据是恒绿判据")
    verdict = "PASS" if not failures else "FAIL"
    print(f"VERDICT {verdict} " + json.dumps({"failures": failures}, ensure_ascii=False))
    if not args.quiet:
        print(f"正向：{positive['connect_hits']} 次连入 / {positive['connect_refused']} 次 refused，"
              f"首次命中 {positive['first_hit_at_s']}s（进程墙钟 {positive['loop_wall_s']}s），"
              f"响应首行 {positive['first_status_line']}")
        print(f"负向：{negative['connect_hits']} 次连入 / {negative['connect_refused']} 次 refused")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
