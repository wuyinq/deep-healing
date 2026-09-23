#!/usr/bin/env python3
"""F7（r3）fd 饱和探针：**把服务进程的 fd 打到 `ulimit -n`**，复现 `Errno 24` + SIGABRT 链。

为什么需要它（与 `m4-r3-live-load-probe.py` 的区别）：
  - `load-probe` 的观察者「一发一收一关」⇒ 服务端线程随连接结束而退出 ⇒ fd 高水位只有 44，
    **机制未被激活**（读数会让人误以为「没这回事」）。
  - 本探针的观察者用 **HTTP/1.1 keep-alive 且不主动关闭**：服务端 `ThreadingHTTPServer`
    每连接一线程、且普通路径**没有读超时** ⇒ 线程阻塞在 `readline` 等下一个请求 ⇒
    连接与线程**同时累积** ⇒ fd 线性逼近上限。这才是 architect 裁决 §6.2 的 regime。

判据（写死）：
  - **RED（修前）**：服务进程 fd 逼近 `ulimit -n` 且封存 `live_state.json` 失败
    （stderr 出现 `Errno 24`）⇒ 进程**非 0 / 被信号打断**，`live_state.json` 缺失。
  - **GREEN（修后）**：服务进程 fd 高水位**远离上限**（并发上限生效 ⇒ 超出部分被 503 拒绝），
    退出码 0，`live_state.json` 合法可读。
  - 连接一律用**阻塞 `socket.connect`**（`socket.create_connection`），不用 `connect_ex`。
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


def _nofile_limit() -> int:
    import resource

    soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    return int(soft)


def raise_nofile(target: int) -> int:
    """把**探针自己**的软限提到 `target`（硬限内）——否则探针先于服务进程耗尽 fd，
    服务进程就永远到不了 `Errno 24`（首轮实测：探针 3287 连接即 EMFILE，服务端只到 3264）。
    **只改探针**，不改被测进程（其 `ulimit -n = 4096` 保持原样，才是被复现的 regime）。"""
    import resource

    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    ceiling = target if hard in (resource.RLIM_INFINITY, -1) else min(target, int(hard))
    if ceiling <= soft:
        return int(soft)
    resource.setrlimit(resource.RLIMIT_NOFILE, (ceiling, hard))
    return int(ceiling)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Holder(threading.Thread):
    """keep-alive 观察者：开连接、发请求、读状态行、**不关**（线程累积 ⇒ fd 累积）。"""

    def __init__(self, port: int, budget: threading.Semaphore, hold: list,
                 deadline: float) -> None:
        super().__init__(daemon=True)
        self.port = int(port)
        self.budget = budget
        self.hold = hold
        self.deadline = deadline
        self.served_200 = 0
        self.served_503 = 0
        self.served_other = 0
        self.open_failures = 0
        self.stopped = threading.Event()

    def run(self) -> None:
        request = b"GET /live/state HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"   # keep-alive（默认）
        while not self.stopped.is_set() and time.monotonic() < self.deadline:
            if not self.budget.acquire(blocking=False):
                break
            try:
                sock = socket.create_connection(("127.0.0.1", self.port), timeout=0.5)
            except (OSError, TimeoutError):
                self.open_failures += 1
                self.budget.release()
                time.sleep(0.01)
                continue
            try:
                sock.sendall(request)
                raw = b""
                while b"\r\n" not in raw:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    raw += chunk
            except (OSError, TimeoutError):
                self.open_failures += 1
                sock.close()
                self.budget.release()
                continue
            line = raw.split(b"\r\n", 1)[0] if raw else b""
            if b" 200" in line:
                self.served_200 += 1
            elif b" 503" in line:
                self.served_503 += 1
            else:
                self.served_other += 1
            self.hold.append(sock)          # **持有**：不 close


class FdSampler(threading.Thread):
    def __init__(self, pid: int, interval: float = 0.05) -> None:
        super().__init__(daemon=True)
        self.pid = int(pid)
        self.interval = float(interval)
        self.peak = 0
        self.samples = 0
        self.stop = threading.Event()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                out = subprocess.run(["lsof", "-p", str(self.pid)], capture_output=True, text=True)
                if out.returncode == 0:
                    self.peak = max(self.peak, len([line for line in out.stdout.splitlines()
                                                    if line.strip()]))
                    self.samples += 1
            except OSError:
                pass
            self.stop.wait(self.interval)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observers", type=int, default=4)
    parser.add_argument("--max-held", type=int, default=4300)
    parser.add_argument("--ticks", type=int, default=200)
    parser.add_argument("--hold-seconds", type=float, default=45.0)
    parser.add_argument("--wait-seconds", type=float, default=150.0)
    parser.add_argument("--label", default="run")
    parser.add_argument("--raise-nofile", type=int, default=0,
                        help="把探针自身软限提到该值（0 = 不动）")
    parser.add_argument("--root", default="/tmp/m4r3-fd-saturation")
    args = parser.parse_args()

    probe_limit = raise_nofile(args.raise_nofile) if args.raise_nofile else _nofile_limit()
    out_dir = Path(args.root) / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    port = free_port()
    limit = 4096          # 被测进程的 ulimit -n（探针不改它）
    cmd = [sys.executable, "-m", "deephealing_kernel", "live",
           "--pack", str(PACK_DIR), "--seed", str(SEED), "--out", str(out_dir),
           "--pace", "0", "--ticks", str(args.ticks), "--snapshot-every", "0",
           "--no-warmup", "--port", str(port)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    started = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            cwd=str(KERNEL_ROOT), env=env)
    sampler = FdSampler(proc.pid)
    sampler.start()

    ready_deadline = time.monotonic() + 5.0
    while time.monotonic() < ready_deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except (OSError, TimeoutError):
            time.sleep(0.02)

    budget = threading.Semaphore(args.max_held)
    hold: list = []
    deadline = time.monotonic() + args.hold_seconds
    holders = [Holder(port, budget, hold, deadline) for _ in range(args.observers)]
    for holder in holders:
        holder.start()
    for holder in holders:
        holder.join(timeout=args.hold_seconds + 10)

    fd_at_saturation = sampler.peak
    try:
        proc.wait(timeout=args.wait_seconds)
        timed_out = False
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        timed_out = True
    wall = time.monotonic() - started
    sampler.stop.set()
    sampler.join(timeout=5)
    for sock in hold:
        try:
            sock.close()
        except OSError:
            pass
    stdout, stderr = proc.stdout.read(), proc.stderr.read()

    state_path = out_dir / "live_state.json"
    sealed_ok = False
    if state_path.is_file():
        try:
            json.loads(state_path.read_text(encoding="utf-8"))
            sealed_ok = True
        except (OSError, ValueError):
            sealed_ok = False
    stderr_lines = [line for line in stderr.splitlines() if line.strip()]
    report = {
        "label": args.label,
        "observers": args.observers,
        "ticks": args.ticks,
        "ulimit_n": limit,
        "probe_nofile": probe_limit,
        "held_connections": len(hold),
        "fd_peak": sampler.peak,
        "fd_at_saturation": fd_at_saturation,
        "fd_peak_vs_limit": round(sampler.peak / limit, 4) if limit else None,
        "fd_samples": sampler.samples,
        "exit": proc.returncode,
        "timed_out": timed_out,
        "loop_wall_s": round(wall, 3),
        "served_200": sum(h.served_200 for h in holders),
        "served_503": sum(h.served_503 for h in holders),
        "served_other": sum(h.served_other for h in holders),
        "open_failures": sum(h.open_failures for h in holders),
        "live_state_json_ok": sealed_ok,
        "stderr_errno24": any("Errno 24" in line for line in stderr_lines),
        "stderr_buffered_busy": any("_enter_buffered_busy" in line for line in stderr_lines),
        "stderr_tail": stderr_lines[-6:],
    }
    print("RESULT " + json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
