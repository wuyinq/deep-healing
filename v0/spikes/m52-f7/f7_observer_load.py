#!/usr/bin/env python3
"""F7 观察者负载探针（M5.2 r1 · **沿用 M4 参考探针的 regime，不按散文重建**）。

regime（逐字沿用 `m4-r4-arch-f7-probe-reference.py` / M4 `04_sentinel_test_report.md` §D-12）：
  - **4 个无间隔外部观察者**：每次 `connect` 后发 `GET /live/state HTTP/1.0`、**只读 64 字节即关**、紧循环重连
    （= `close-mode arch`；`immediate` regime 由 `--close-mode immediate` 选：发完请求即关）；
  - **默认 `ulimit -n`**（探针**不**调用 `resource.setrlimit`；读数里显式带 `probe_nofile_raised=false`）；
  - `--pace 0 --ticks 3000`；仪表 = 跑中每 50ms 采样 `lsof -p <pid>` 取峰值。

M-9③ 要求的**区分性机制仪表**（用来区分「配额没兜住」与「配额之外的 fd」）：
  `fd_total_peak` / `fd_tcp_peak` / `thread_peak` / `served_200` / `errno24` / `fatal_python_error` /
  `live_state_ok`（或 `summary_json_ok`）。

判据（**按更严的一侧关**，设计 §10 B-3 / M-9①）：
  `exit` 全 0 · 无 `Errno 24` · 无 `Fatal Python error` · 产物齐 · **`fd_total_peak < 1024`**（**数字阈值**）。

两条路径都要跑（`live` 与 `run --ws-port`）；两种 regime 都要跑（`arch` + `immediate`）。

用法：`python3 <ws>/spikes/m52-f7/f7_observer_load.py [--runs 3] [--modes live,run] [--regimes arch,immediate]`
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.dont_write_bytecode = True

WS = Path(__file__).resolve().parents[2]
KERNEL = WS / "02_source/v0_skeleton/kernel"
PACK = "districts/xingfu-xiaoqu"
OUT = WS / "spikes/m52-f7"
FD_PEAK_LIMIT = 1024
OBSERVERS = 4
SAMPLE_INTERVAL_S = 0.05
#: `hold` regime：每线程保持的连接数 + 刷新间隔（总并发 = observers × HOLD_PER_THREAD）
HOLD_PER_THREAD = 5
HOLD_REFRESH_S = 1.0


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _classify(lsof_output: str) -> tuple[int, int]:
    lines = [line for line in lsof_output.splitlines()[1:] if line.strip()]
    tcp = sum(1 for line in lines if "TCP" in line)
    return len(lines), tcp


def _run_arm(*, mode: str, regime: str, observers: int, tag: str, ticks: int) -> dict:
    outdir = OUT / "runs" / tag
    # 每臂先清空自己的运行产物目录：CLI 对「非空事件日志 + 已有 checkpoint」是 **fail-closed**
    # （`E_EVENTS_EXISTS`：拒绝半清理的树，避免给出误导性的红）。探针必须自己保证干净起点。
    if outdir.exists():
        shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if mode == "live":
        cmd = [sys.executable, "-m", "deephealing_kernel", "live",
               "--pack", PACK, "--seed", "20260921", "--out", str(outdir),
               "--port", str(port), "--pace", "0", "--ticks", str(ticks)]
    else:
        cmd = [sys.executable, "-m", "deephealing_kernel", "run",
               "--pack", PACK, "--seed", "20260921", "--ticks", str(ticks),
               "--ws-port", str(port), "--events", str(outdir / "events.jsonl"),
               "--snapshot-every", "50"]
    stdout_path = OUT / f"{tag}.out"
    stderr_path = OUT / f"{tag}.err"
    process = subprocess.Popen(cmd, cwd=KERNEL, env=env,
                               stdout=open(stdout_path, "w"), stderr=open(stderr_path, "w"))
    stop = threading.Event()
    peak_total = [0]
    peak_tcp = [0]
    peak_thread = [0]
    served = [0]

    def sampler() -> None:
        while not stop.is_set():
            try:
                listing = subprocess.run(["lsof", "-p", str(process.pid)],
                                         capture_output=True, text=True).stdout
                total, tcp = _classify(listing)
                peak_total[0] = max(peak_total[0], total)
                peak_tcp[0] = max(peak_tcp[0], tcp)
                threads = subprocess.run(["ps", "-o", "thcount=", "-p", str(process.pid)],
                                         capture_output=True, text=True).stdout.strip()
                if threads.isdigit():
                    peak_thread[0] = max(peak_thread[0], int(threads))
            except Exception:  # noqa: BLE001 —— 采样失败不得影响被测进程
                pass
            time.sleep(SAMPLE_INTERVAL_S)

    def churn() -> None:
        held: list[socket.socket] = []
        while not stop.is_set():
            try:
                if regime == "hold":
                    # **fd 归属核对用**：把连接**开满并保持**（不读、不关）——
                    # 这正是 M4 文档化的那条通路：「空闲 keep-alive 连接不占在途额度，
                    # 却一直占 1 线程 + 1 fd」。每线程持 HOLD_PER_THREAD 条，
                    # 总并发 = observers × HOLD_PER_THREAD。
                    while len(held) < HOLD_PER_THREAD and not stop.is_set():
                        sock = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                        sock.sendall(b"GET /live/health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
                        sock.recv(64)          # 只读 64 字节：连接**保持打开**
                        held.append(sock)
                        served[0] += 1
                    stop.wait(HOLD_REFRESH_S)
                    continue
                sock = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                sock.sendall(b"GET /live/state HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
                if regime == "arch":
                    sock.recv(64)          # 只读 64 字节即关（参考探针口径）
                served[0] += 1
                sock.close()               # 立即关闭 ⇒ accept churn
            except Exception:  # noqa: BLE001
                time.sleep(0.001)
        for sock in held:
            try:
                sock.close()
            except OSError:
                pass

    threads = [threading.Thread(target=sampler, daemon=True)]
    for _ in range(observers):
        threads.append(threading.Thread(target=churn, daemon=True))
    for thread in threads:
        thread.start()
    started = time.time()
    exit_code = process.wait()
    wall = time.time() - started
    stop.set()
    time.sleep(0.2)
    stderr_text = stderr_path.read_text(errors="replace")
    stdout_text = stdout_path.read_text(errors="replace")
    artifacts = sorted(path.name for path in outdir.glob("*.json"))
    live_state_ok = (outdir / "live_state.json").is_file()
    summary_ok = any(name.endswith("summary.json") for name in artifacts) or '"ticks"' in stdout_text
    artifact_ok = live_state_ok if mode == "live" else summary_ok
    reading = {
        "tag": tag, "mode": mode, "regime": regime, "observers": observers,
        "exit": exit_code, "wall_s": round(wall, 2),
        "fd_total_peak": peak_total[0], "fd_tcp_peak": peak_tcp[0], "thread_peak": peak_thread[0],
        "served_200": served[0],
        "errno24": "Too many open files" in stderr_text,
        "fatal_python_error": "Fatal Python error" in stderr_text,
        "artifact_ok": artifact_ok, "artifacts": artifacts,
        "probe_nofile_raised": False,
        "probe_nofile_soft": resource.getrlimit(resource.RLIMIT_NOFILE)[0],
        "fd_peak_below_limit": peak_total[0] < FD_PEAK_LIMIT,
    }
    reading["pass"] = bool(
        exit_code == 0 and not reading["errno24"] and not reading["fatal_python_error"]
        and artifact_ok and reading["fd_peak_below_limit"]
    )
    return reading


def main() -> int:
    parser = argparse.ArgumentParser(description="F7 observer-load probe (M4 regime)")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--modes", default="live,run")
    parser.add_argument("--regimes", default="arch,immediate")
    parser.add_argument("--ticks", type=int, default=3000)
    parser.add_argument("--observers", type=int, default=OBSERVERS,
                        help="并发 churn 观察者数（M4 参考口径 = 4；fd 归属核对用大并发放大）")
    parser.add_argument("--tag-prefix", default="",
                        help="产物 tag 前缀（把 fd 归属核对与 M4 参考口径的读数分开存）")
    parser.add_argument("--ws", default=None,
                        help="被测工作树（缺省 = 本 spike 所属 workspace）；产物落 <ws>/spikes/m52-f7")
    args = parser.parse_args()

    global KERNEL, OUT
    if args.ws:
        root = Path(args.ws).expanduser().resolve()
        KERNEL = root / "02_source/v0_skeleton/kernel"
        OUT = root / "spikes/m52-f7"

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "runs").mkdir(parents=True, exist_ok=True)
    arms: list[dict] = []
    for regime in args.regimes.split(","):
        for mode in args.modes.split(","):
            for index in range(args.runs):
                arms.append(_run_arm(mode=mode, regime=regime, observers=args.observers,
                                     tag=f"{args.tag_prefix}{mode}-{regime}-run{index}",
                                     ticks=args.ticks))
    document = {
        "regime_reference": "m4-r4-arch-f7-probe-reference.py (M4 §D-12)",
        "kernel_root": str(KERNEL),
        "fd_peak_limit": FD_PEAK_LIMIT,
        "observers": args.observers,
        "arms": arms,
        "all_pass": all(arm["pass"] for arm in arms),
    }
    text = json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True)
    (OUT / f"f7-observer-load{'-' + args.tag_prefix.rstrip('-') if args.tag_prefix else ''}.json"
     ).write_text(text + "\n", encoding="utf-8")
    for arm in arms:
        print(json.dumps({key: arm[key] for key in
                          ("tag", "exit", "fd_total_peak", "fd_tcp_peak", "thread_peak", "served_200",
                           "errno24", "fatal_python_error", "artifact_ok", "pass")},
                         ensure_ascii=False, sort_keys=True))
    print(f"all_pass={document['all_pass']} (fd_total_peak < {FD_PEAK_LIMIT} required)")
    return 0 if document["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
