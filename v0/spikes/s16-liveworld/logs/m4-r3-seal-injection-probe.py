#!/usr/bin/env python3
"""F7（r3）封存失败注入探针：让 `live_state.json` 的写操作抛 `OSError`，看收尾链是否 fail-closed。

**注入方式（无 monkeypatch，走真 CLI 子进程）**：把 `--out` 目录下的 `live_state.json`
**建成目录** ⇒ `Path.write_text()` 抛 `IsADirectoryError`（`OSError` 子类），
与 architect 裁决 §6.2 的 `Errno 24` 同属 `OSError`，但**可确定性复现**。

用法（一条命令）：

    python3 m4-r3-seal-injection-probe.py                       # 交付树：注入 + 负向对照
    python3 m4-r3-seal-injection-probe.py --kernel-root <修前副本>  # 修前：复现 RED

臂：
  - **inject**：注入 + `--observers N`（默认 4）个 SSE 观察者 —— 让 HTTP daemon 线程在收尾时**活着**，
    这是 `_enter_buffered_busy` ⇒ SIGABRT 的前提。
  - **clean**（负向对照）：不注入 ⇒ **不得**误报（无 `E_LIVE_STATE_SEAL_FAILED`、exit 0、
    `live_state.json` 合法可读）⇒ 判据既不是恒绿也不是恒红。

修后期望（inject 臂）：exit != 0、stderr 有 `E_LIVE_STATE_SEAL_FAILED`、**无** `Traceback`、
**无** `_enter_buffered_busy`、stdout 有机器可读 JSON 且 `server_stopped = true`。
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


class SseObserver(threading.Thread):
    """SSE 观察者：连上 `/live/stream` 并持续读帧 ⇒ 收尾时 daemon 线程仍活着。"""

    def __init__(self, port: int) -> None:
        super().__init__(daemon=True)
        self.port = int(port)
        self.bytes_read = 0
        self.connected = False
        self.stop = threading.Event()

    def run(self) -> None:
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1.0) as sock:
                self.connected = True
                sock.sendall(b"GET /live/stream HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
                sock.settimeout(0.5)
                while not self.stop.is_set():
                    try:
                        chunk = sock.recv(8192)
                    except (OSError, TimeoutError):
                        continue
                    if not chunk:
                        break
                    self.bytes_read += len(chunk)
        except (OSError, TimeoutError):
            pass


def one_arm(*, arm: str, observers: int, ticks: int, pace: float, out_dir: Path) -> dict:
    if out_dir.exists():
        for child in sorted(out_dir.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / "live_state.json"
    injected = arm == "inject"
    if injected:
        state_path.mkdir(parents=True, exist_ok=True)     # **注入**：write_text ⇒ IsADirectoryError
    port = free_port()
    cmd = [sys.executable, "-m", "deephealing_kernel", "live",
           "--pack", str(PACK_DIR), "--seed", str(SEED), "--out", str(out_dir),
           "--pace", str(pace), "--ticks", str(ticks), "--snapshot-every", "0",
           "--no-warmup", "--port", str(port)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            cwd=str(KERNEL_ROOT), env=env)
    ready_deadline = time.monotonic() + 5.0
    while time.monotonic() < ready_deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except (OSError, TimeoutError):
            time.sleep(0.02)
    clients = [SseObserver(port) for _ in range(observers)]
    for client in clients:
        client.start()
    stdout, stderr = proc.communicate(timeout=60)
    for client in clients:
        client.stop.set()
    for client in clients:
        client.join(timeout=2)

    sealed_ok = False
    if state_path.is_file():
        try:
            json.loads(state_path.read_text(encoding="utf-8"))
            sealed_ok = True
        except (OSError, ValueError):
            sealed_ok = False
    payload = None
    for line in stdout.splitlines():
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except ValueError:
                payload = None
    return {
        "arm": arm,
        "observers": observers,
        "exit": proc.returncode,
        "injected": injected,
        "traceback_on_stderr": "Traceback" in stderr,
        "structured_error_on_stderr": "E_LIVE_STATE_SEAL_FAILED" in stderr,
        "buffered_busy": "_enter_buffered_busy" in stderr,
        "too_many_open_files": "Errno 24" in stderr,
        "stdout_json_present": payload is not None,
        "stdout_error_code": None if payload is None else payload.get("error"),
        "server_stopped": None if payload is None else payload.get("server_stopped"),
        "sealed": None if payload is None else payload.get("sealed"),
        "live_state_json_ok": sealed_ok,
        "sse_clients_connected": sum(1 for client in clients if client.connected),
        "stderr_tail": [line for line in stderr.splitlines() if line.strip()][-3:],
    }


def main() -> int:
    global KERNEL_ROOT  # noqa: PLW0603 — 探针参数：可指向修前副本
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel-root", default=str(KERNEL_ROOT))
    parser.add_argument("--observers", type=int, default=4)
    parser.add_argument("--ticks", type=int, default=200)
    parser.add_argument("--pace", type=float, default=0.01,
                        help="秒/世界分钟；默认 200×0.01 = 2s，保证 SSE 观察者在封存时仍活着")
    parser.add_argument("--root", default="/tmp/m4r3-seal-injection")
    args = parser.parse_args()
    KERNEL_ROOT = Path(args.kernel_root)
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    inject = one_arm(arm="inject", observers=args.observers, ticks=args.ticks, pace=args.pace,
                     out_dir=root / "inject")
    clean = one_arm(arm="clean", observers=args.observers, ticks=args.ticks, pace=args.pace,
                    out_dir=root / "clean")
    print("INJECT " + json.dumps(inject, ensure_ascii=False, sort_keys=True), flush=True)
    print("CLEAN " + json.dumps(clean, ensure_ascii=False, sort_keys=True), flush=True)

    failures: list[str] = []
    # ① 注入臂：fail-closed 且可观测
    if inject["exit"] == 0:
        failures.append("注入臂 exit=0 ⇒ 封存失败没有转成非 0 退出")
    if not inject["structured_error_on_stderr"]:
        failures.append("注入臂 stderr 缺结构化错误码 E_LIVE_STATE_SEAL_FAILED")
    if inject["traceback_on_stderr"]:
        failures.append("注入臂 出现裸 Traceback ⇒ 异常穿出了 finally")
    if inject["buffered_busy"]:
        failures.append("注入臂 出现 _enter_buffered_busy ⇒ 进程在 finalize 期崩（SIGABRT 形态）")
    if inject["exit"] == -6:
        failures.append("注入臂 exit=-6（SIGABRT）")
    if inject["server_stopped"] is not True:
        failures.append(f"注入臂 server_stopped={inject['server_stopped']} ⇒ server.stop() 未执行")
    # ② 负向对照：不注入时不得误报
    if clean["exit"] != 0:
        failures.append(f"负向对照臂 exit={clean['exit']} ⇒ 判据恒红")
    if clean["structured_error_on_stderr"]:
        failures.append("负向对照臂误报 E_LIVE_STATE_SEAL_FAILED ⇒ 判据恒红")
    if not clean["live_state_json_ok"]:
        failures.append("负向对照臂 live_state.json 不可读")
    verdict = "PASS" if not failures else "FAIL"
    print(f"VERDICT {verdict} " + json.dumps({"failures": failures}, ensure_ascii=False))
    print(f"注入臂：exit={inject['exit']} | 结构化错误={inject['structured_error_on_stderr']} | "
          f"Traceback={inject['traceback_on_stderr']} | server_stopped={inject['server_stopped']} | "
          f"SSE 观察者已连 {inject['sse_clients_connected']} 个")
    print(f"负向臂：exit={clean['exit']} | 结构化错误={clean['structured_error_on_stderr']} | "
          f"live_state.json 合法={clean['live_state_json_ok']}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
