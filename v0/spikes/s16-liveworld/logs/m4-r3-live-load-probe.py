#!/usr/bin/env python3
"""F7（r3）观察者负载探针：0 vs N 个**无间隔外部观察者**下的循环墙钟 / 退出码 / fd 高水位。

用法（workdir 任意，pack 用绝对路径）：
    python3 m4-r3-live-load-probe.py --observers 4 --repeats 3 --ticks 3000 --label postfix

读数口径（写死，防口径漂移）：
  - **观察者是外部进程**（跨进程 socket），不是同进程压测线程 —— 后者不消耗跨进程 fd，
    与缺陷 regime 不同（architect 裁决 §7.2）。
  - **连接 = 阻塞 `socket.connect`**（`socket.create_connection`），**不是** `connect_ex`
    （`connect_ex` 在 `settimeout` 后返回 `EINPROGRESS` 而非 0 ⇒ 假命中；architect 裁决 §6.3）。
    命中判据 = connect 返回成功 **且** 读到合法 HTTP 状态行。
  - **fd 高水位仪表**：跑中每 ~40ms 采样 `lsof -p <pid> | wc -l` 取峰值 ——
    判「机制有没有被激活」不能只看崩不崩（architect 裁决 §7.2 判据 2）。
  - **产物完整性**：运行目录里 `live_state.json` 必须存在且是合法 JSON。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[3] / "02_source" / "v0_skeleton" / "kernel"
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SEED = 20260921


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _nofile_limit() -> int:
    """本进程的 `RLIMIT_NOFILE`（= `ulimit -n`；fd 耗尽判据的分母）。"""
    import resource

    soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    return int(soft)


class Observer:
    """外部观察者：无间隔循环 GET `/live/state`（每次一条新连接 ⇒ 真实 fd 压力）。"""

    def __init__(self, port: int) -> None:
        self.port = int(port)
        self.served_200 = 0
        self.served_503 = 0
        self.served_other = 0
        self.errors = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        request = (b"GET /live/state HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                   b"Connection: close\r\n\r\n")
        while not self.stop.is_set():
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5) as sock:
                    sock.sendall(request)
                    raw = b""
                    while b"\r\n" not in raw:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        raw += chunk
            except (OSError, TimeoutError):
                self.errors += 1
                continue
            line = raw.split(b"\r\n", 1)[0] if raw else b""
            if b" 200" in line:
                self.served_200 += 1
            elif b" 503" in line:
                self.served_503 += 1
            else:
                self.served_other += 1

    def finish(self) -> None:
        self.stop.set()
        self.thread.join(timeout=5)


class FdSampler:
    """廉价仪表：`lsof -p <pid> | wc -l` 峰值。"""

    def __init__(self, pid: int, interval: float = 0.04) -> None:
        self.pid = int(pid)
        self.interval = float(interval)
        self.peak = 0
        self.samples = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        while not self.stop.is_set():
            try:
                out = subprocess.run(["lsof", "-p", str(self.pid)], capture_output=True, text=True)
                if out.returncode == 0:
                    count = len([line for line in out.stdout.splitlines() if line.strip()])
                    self.peak = max(self.peak, count)
                    self.samples += 1
            except OSError:
                pass
            self.stop.wait(self.interval)

    def finish(self) -> None:
        self.stop.set()
        self.thread.join(timeout=5)


def one_arm(*, observers: int, ticks: int, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    port = free_port()
    cmd = [sys.executable, "-m", "deephealing_kernel", "live",
           "--pack", str(PACK_DIR), "--seed", str(SEED), "--out", str(out_dir),
           "--pace", "0", "--ticks", str(ticks), "--snapshot-every", "0",
           "--no-warmup", "--port", str(port)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    started = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            cwd=str(KERNEL_ROOT), env=env)
    sampler = FdSampler(proc.pid)
    sampler.start()
    # 等监听起来（阻塞 connect；refused 就继续试，最多 5s）
    ready_deadline = time.monotonic() + 5.0
    while time.monotonic() < ready_deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except (OSError, TimeoutError):
            time.sleep(0.02)
    clients = [Observer(port) for _ in range(observers)]
    for client in clients:
        client.start()
    stdout, stderr = proc.communicate()
    wall = time.monotonic() - started
    for client in clients:
        client.finish()
    sampler.finish()

    state_path = out_dir / "live_state.json"
    sealed_ok = False
    if state_path.is_file():
        try:
            json.loads(state_path.read_text(encoding="utf-8"))
            sealed_ok = True
        except (OSError, ValueError):
            sealed_ok = False
    return {
        "observers": observers,
        "ticks": ticks,
        "port": port,
        "exit": proc.returncode,
        "loop_wall_s": round(wall, 3),
        "served_200": sum(client.served_200 for client in clients),
        "served_503": sum(client.served_503 for client in clients),
        "served_other": sum(client.served_other for client in clients),
        "connect_errors": sum(client.errors for client in clients),
        "fd_peak": sampler.peak,
        "fd_samples": sampler.samples,
        "live_state_json_ok": sealed_ok,
        "stderr_tail": stderr.strip().splitlines()[-4:],
        "stdout_tail": stdout.strip().splitlines()[-1:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observers", type=int, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--ticks", type=int, default=3000)
    parser.add_argument("--label", default="run")
    parser.add_argument("--root", default="/tmp/m4r3-live-load")
    args = parser.parse_args()

    root = Path(args.root) / args.label / f"obs{args.observers}"
    arms = []
    for index in range(args.repeats):
        arm = one_arm(observers=args.observers, ticks=args.ticks,
                      out_dir=root / f"run{index}")
        arm["repeat"] = index
        arms.append(arm)
        print(json.dumps(arm, ensure_ascii=False, sort_keys=True), flush=True)
    summary = {
        "label": args.label,
        "observers": args.observers,
        "repeats": args.repeats,
        "ulimit_n": _nofile_limit(),
        "exits": [arm["exit"] for arm in arms],
        "walls": [arm["loop_wall_s"] for arm in arms],
        "fd_peaks": [arm["fd_peak"] for arm in arms],
        "all_sealed": all(arm["live_state_json_ok"] for arm in arms),
        "crash_count": sum(1 for arm in arms if arm["exit"] != 0),
    }
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
