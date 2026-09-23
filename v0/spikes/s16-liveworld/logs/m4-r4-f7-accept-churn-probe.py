#!/usr/bin/env python3
"""F7（r4）accept churn 探针：**4 个无间隔外部观察者、连接建立即关**下的
退出码 / fd 高水位 / 产物完整性。`live` 与 `run --ws-port` 两条路径共用。

regime 与 `.architect-verdict-m4-r3.md` §2.1 **逐字一致**（本轮硬性取证条件）：

  - 观察者 = **外部进程连接**（跨进程 socket），**4 个**，**无间隔**紧循环；
  - **连接建立即关**（`Connection: close`；`--close-mode immediate` 进一步做到「发完就关」）；
  - **默认 `ulimit -n`（4096）** —— 本探针**不**调用 `resource.setrlimit`（那是 r3 探针的错：
    抬掉被考察条件本身）。探针自身同时在途 socket 只有 `--observers` 条 ⇒ 不需要抬。
  - `--pace 0 --ticks 3000`（`live`）/ `--ticks 3000`（`run`）；**n=3**。

读数口径（写死，防口径漂移）：
  - 命中 = **阻塞 `socket.connect`**（`socket.create_connection`）成功 **且** 读到合法状态行；
    **禁止** `connect_ex`（带超时下返回 `EINPROGRESS` ⇒ 假命中）。
  - **fd 高水位仪表**：跑中每 ~40ms `lsof -p <pid> | wc -l` 取峰值 ——
    「机制有没有被激活」不能只看崩不崩（architect 裁决 §7.2 判据 2）。
  - 产物：`live` ⇒ `<out>/live_state.json` 存在且可解析；`run` ⇒ stdout 摘要 JSON 可解析。

用法（workdir 任意）：

    python3 spikes/s16-liveworld/logs/m4-r4-f7-accept-churn-probe.py \
        --path live --observers 4 --repeats 3 --ticks 3000 --label RED

退出码：0 = 全部臂的「关闭判据形态」成立（exit 全 0 / 无 Errno 24 / 无 Fatal / 产物齐）；
       1 = 至少一臂复现了缺陷形态（RED）。
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

DEFAULT_KERNEL_ROOT = Path(__file__).resolve().parents[3] / "02_source" / "v0_skeleton" / "kernel"
SEED = 20260921
#: 判据分母：**默认** `ulimit -n`（`live` 进程继承探针的软限；探针不抬它）
DEFAULT_NOFILE = 4096
#: 单臂上限（防「进程卡死」把探针挂住：超时即 kill，读数照记）
ARM_TIMEOUT_S = 180.0


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def nofile_soft() -> int:
    """本进程 `RLIMIT_NOFILE` 软限（**只读**；本探针任何路径都不写它）。"""
    import resource

    soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    return int(soft)


class Observer:
    """外部观察者：**无间隔**循环「连接 → 发请求 → 关」（churn，不保持连接）。"""

    def __init__(self, port: int, *, close_mode: str, timeout: float = 0.5) -> None:
        self.port = int(port)
        self.close_mode = close_mode
        self.timeout = float(timeout)
        self.attempts = 0
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
            self.attempts += 1
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=self.timeout) as sock:
                    if self.close_mode == "bare":
                        continue          # 建立即关：**不发请求**（最纯粹的 accept churn）
                    if self.close_mode == "arch":
                        # **与 architect 探针逐字一致**（`.architect-verdict-m4-r3.md` §2.1 的 regime）：
                        # HTTP/1.0 + 只读 64 字节即关 ⇒ 服务端写剩余响应体时 EPIPE/ECONNRESET
                        sock.sendall(b"GET /live/state HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
                        head = sock.recv(64)
                        if b" 200" in head.split(b"\r\n", 1)[0]:
                            self.served_200 += 1
                        elif b" 503" in head.split(b"\r\n", 1)[0]:
                            self.served_503 += 1
                        else:
                            self.served_other += 1
                        continue
                    sock.sendall(request)
                    if self.close_mode == "immediate":
                        continue          # 发完即关：不等响应
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
    """廉价仪表：`lsof -p <pid> | wc -l` 峰值（fd 高水位）。"""

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


class ThreadSampler:
    """廉价仪表：`ps -M -p <pid>` 线程数峰值（判断线程是否在 accept churn 下累积）。"""

    def __init__(self, pid: int, interval: float = 0.05) -> None:
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
                out = subprocess.run(["ps", "-M", "-p", str(self.pid)], capture_output=True, text=True)
                if out.returncode == 0:
                    count = max(0, len([line for line in out.stdout.splitlines() if line.strip()]) - 1)
                    self.peak = max(self.peak, count)
                    self.samples += 1
            except OSError:
                pass
            self.stop.wait(self.interval)

    def finish(self) -> None:
        self.stop.set()
        self.thread.join(timeout=5)


def build_cmd(*, path: str, kernel_root: Path, pack_dir: Path, out_dir: Path, port: int,
              ticks: int) -> list[str]:
    if path == "live":
        return [sys.executable, "-m", "deephealing_kernel", "live",
                "--pack", str(pack_dir), "--seed", str(SEED), "--out", str(out_dir),
                "--pace", "0", "--ticks", str(ticks), "--snapshot-every", "0",
                "--no-warmup", "--port", str(port)]
    if path == "run":
        return [sys.executable, "-m", "deephealing_kernel", "run",
                "--pack", str(pack_dir), "--seed", str(SEED), "--ticks", str(ticks),
                "--events", str(out_dir / "events.jsonl"), "--ws-port", str(port)]
    raise ValueError(f"unknown path {path!r}")


def artifact_reading(path: str, out_dir: Path, stdout: str) -> tuple[bool, str | None]:
    """产物判据：`live` ⇒ `live_state.json`；`run` ⇒ stdout 摘要 JSON。"""
    if path == "live":
        state_path = out_dir / "live_state.json"
        if not state_path.is_file():
            return False, "live_state.json 缺失"
        try:
            json.loads(state_path.read_text(encoding="utf-8"))
            return True, None
        except (OSError, ValueError) as exc:
            return False, f"live_state.json 不可解析：{type(exc).__name__}"
    summary = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("{") and '"command"' in stripped:
            try:
                payload = json.loads(stripped)
            except ValueError:
                continue
            if payload.get("command") == "run":
                summary = payload
    if summary is None:
        return False, "run 摘要 JSON 缺失/不可解析"
    return True, None


def one_arm(*, path: str, observers: int, ticks: int, close_mode: str, kernel_root: Path,
            pack_dir: Path, out_dir: Path, stderr_mode: str = "file") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    port = free_port()
    cmd = build_cmd(path=path, kernel_root=kernel_root, pack_dir=pack_dir, out_dir=out_dir,
                    port=port, ticks=ticks)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    started = time.monotonic()
    # **stdout/stderr 落文件**（不是 PIPE）：与 architect 探针同口径，且排除
    # 「stderr 管道写满 ⇒ 线程卡在 stderr 锁」这一探针侧混淆项（见 06 §M4-r4 的机制说明）。
    out_file = (out_dir / "stdout.txt").open("w", encoding="utf-8")
    err_target = (out_dir / "stderr.txt").open("w", encoding="utf-8") if stderr_mode == "file" \
        else subprocess.DEVNULL
    proc = subprocess.Popen(cmd, stdout=out_file, stderr=err_target, text=True,
                            cwd=str(kernel_root), env=env)
    sampler = FdSampler(proc.pid)
    sampler.start()
    threads = ThreadSampler(proc.pid)
    threads.start()

    listen_ready = False
    if port != 0:
        ready_deadline = time.monotonic() + 5.0
        while time.monotonic() < ready_deadline and proc.poll() is None:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    listen_ready = True
                    break
            except (OSError, TimeoutError):
                time.sleep(0.02)

    clients = [Observer(port, close_mode=close_mode) for _ in range(observers)]
    for client in clients:
        client.start()
    timed_out = False
    try:
        proc.wait(timeout=ARM_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        proc.wait(timeout=15)
    wall = time.monotonic() - started
    for client in clients:
        client.finish()
    sampler.finish()
    threads.finish()
    out_file.close()
    if stderr_mode == "file":
        err_target.close()
    stdout = (out_dir / "stdout.txt").read_text(encoding="utf-8", errors="replace")
    stderr = (out_dir / "stderr.txt").read_text(encoding="utf-8", errors="replace") \
        if stderr_mode == "file" else ""

    stderr_lines = [line for line in stderr.splitlines() if line.strip()]
    artifacts_ok, artifact_note = artifact_reading(path, out_dir, stdout)
    return {
        "path": path,
        "observers": observers,
        "ticks": ticks,
        "close_mode": close_mode,
        "port": port,
        "listen_ready": listen_ready,
        "exit": proc.returncode,
        "timed_out": timed_out,
        "wall_s": round(wall, 3),
        "attempts": sum(client.attempts for client in clients),
        "served_200": sum(client.served_200 for client in clients),
        "served_503": sum(client.served_503 for client in clients),
        "served_other": sum(client.served_other for client in clients),
        "connect_errors": sum(client.errors for client in clients),
        "fd_peak": sampler.peak,
        "fd_samples": sampler.samples,
        "thread_peak": threads.peak,
        "thread_samples": threads.samples,
        "artifacts_ok": artifacts_ok,
        "artifact_note": artifact_note,
        "stderr_errno24": any("Errno 24" in line for line in stderr_lines),
        "stderr_toomany": any("Too many open files" in line for line in stderr_lines),
        "stderr_fatal": any("Fatal Python error" in line for line in stderr_lines),
        "stderr_buffered_busy": any("_enter_buffered_busy" in line for line in stderr_lines),
        "stderr_tail": stderr_lines[-4:],
        "stdout_tail": stdout.strip().splitlines()[-1:] if stdout.strip() else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", choices=("live", "run"), default="live")
    parser.add_argument("--observers", type=int, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--ticks", type=int, default=3000)
    parser.add_argument("--close-mode", choices=("after-reply", "immediate", "bare", "arch"),
                        default="after-reply")
    parser.add_argument("--stderr-mode", choices=("file", "devnull"), default="file",
                        help="被测进程的 stderr 去向（devnull = 排除「traceback 写路径」这个混淆项）")
    parser.add_argument("--kernel-root", default=str(DEFAULT_KERNEL_ROOT),
                        help="被测内核目录（默认交付树；可指向**修前副本**做 RED 对照）")
    parser.add_argument("--label", default="run")
    parser.add_argument("--root", default="/tmp/m4r4-f7-accept-churn")
    parser.add_argument("--nofile-expected", type=int, default=DEFAULT_NOFILE,
                        help="判据分母（默认 4096 = 本机默认 ulimit -n）")
    args = parser.parse_args()

    kernel_root = Path(args.kernel_root)
    pack_dir = kernel_root.parent / "districts" / "xingfu-xiaoqu"
    soft = nofile_soft()
    root = Path(args.root) / args.label / f"{args.path}-obs{args.observers}"
    arms = []
    for index in range(args.repeats):
        arm = one_arm(path=args.path, observers=args.observers, ticks=args.ticks,
                      close_mode=args.close_mode, kernel_root=kernel_root, pack_dir=pack_dir,
                      out_dir=root / f"run{index}", stderr_mode=args.stderr_mode)
        arm["repeat"] = index
        arms.append(arm)
        print("ARM " + json.dumps(arm, ensure_ascii=False, sort_keys=True), flush=True)

    red_flags = [arm["exit"] != 0 or arm["stderr_errno24"] or arm["stderr_fatal"]
                 or not arm["artifacts_ok"] for arm in arms]
    summary = {
        "label": args.label,
        "path": args.path,
        "observers": args.observers,
        "repeats": args.repeats,
        "ticks": args.ticks,
        "close_mode": args.close_mode,
        "kernel_root": str(kernel_root),
        "probe_nofile_soft": soft,
        "nofile_expected": args.nofile_expected,
        "probe_nofile_raised": soft != args.nofile_expected,
        "exits": [arm["exit"] for arm in arms],
        "fd_peaks": [arm["fd_peak"] for arm in arms],
        "thread_peaks": [arm["thread_peak"] for arm in arms],
        "fd_peak_pct": [round(100.0 * arm["fd_peak"] / args.nofile_expected, 2) for arm in arms],
        "all_artifacts_ok": all(arm["artifacts_ok"] for arm in arms),
        "errno24_count": sum(1 for arm in arms if arm["stderr_errno24"]),
        "fatal_count": sum(1 for arm in arms if arm["stderr_fatal"]),
        "red_count": sum(1 for flag in red_flags if flag),
        "mechanism_activated": any(arm["fd_peak"] >= args.nofile_expected * 0.5 for arm in arms),
        "verdict": "RED" if any(red_flags) else "GREEN",
    }
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    return 1 if any(red_flags) else 0


if __name__ == "__main__":
    raise SystemExit(main())
