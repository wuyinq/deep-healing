"""M5.2 r1 · F7（fd 归属 + 有界回收）的独立单测 —— 钉 r5 加固的**不变式**。

判据（每条都能被「退回修复前」打红，见 `spikes/m52-f7/` 的 pre-fix 读数）：

  **r5 本轮新增的不变式（在改前树/只退 r5 的副本上必红）**：
  ① **配额归还点晚于 fd 关闭**：`http_connections` 递减必须发生在 `close_request()` **之后**
     —— 退回 r4（在 handler 的 `finish()` 里归还）⇒ 本条必红。
  ② **handler 异常只计数、不写 stderr**：观察者「连上即断」是预期噪声，默认实现会把它变成
     无界 stderr 写（实测单臂 90~127MB）⇒ 退回 stdlib 默认 `handle_error` ⇒ 本条必红。

  **既有不变式（r3 更正：**非本轮新增**，改前树上本来就绿 —— 不得计入「r5 加固」的覆盖）**：
  ③ **churn 之后配额必须回到 0 且峰值不超上限**：accept 层连接配额是 **r4** 引入的
     （「fd 是 `accept()` 那一刻被消耗的」），改前树（r3 形态 + r4）上本条已绿。
  ④ **连接的 socket 超时同时约束读与写**（`settimeout()` 作用于整个 socket）：
     `setup()` 里那行超时**在 r4 之前就存在** ⇒ 改前树上本条已绿。
     r5 曾声称「`setup()` 统一设写超时」是**新增补丁**，实为纯文档改动（Sentinel MEDIUM-1 /
     Raven L-1）⇒ r3 起按事实登记为**既有**不变式。它仍有牙：**删掉** `setup()` 里那行
     `settimeout` ⇒ 连接超时变 `None` ⇒ 本条必红（读数见 `03` 的 M5.2-r3 段 FIX-3）。

  改前树读数（把本文件搬到 r3 形态对照树跑）：**2 failed / 2 passed**，绿的正是 ③④
  ⇒ 「r5 的有效性」只由 ① ② 钉住；fd 天花板另由 **r4 的 accept 配额**兜住。
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
if str(KERNEL_ROOT) not in sys.path:
    sys.path.insert(0, str(KERNEL_ROOT))

from deephealing_kernel import world_clock  # noqa: E402
from deephealing_kernel.events import EventLog  # noqa: E402
from deephealing_kernel.live import (  # noqa: E402
    REQUEST_IDLE_TIMEOUT_S,
    WRITE_TIMEOUT_S,
    LiveHTTPServer,
    LiveServer,
    LiveWorld,
)
from deephealing_kernel.pack import load_pack  # noqa: E402
from deephealing_kernel.tick import WorldKernel  # noqa: E402

WS_ROOT = KERNEL_ROOT.parents[2]
PACK_DIR = WS_ROOT / "02_source/v0_skeleton/districts/xingfu-xiaoqu"
SEED = 20260921


def _build(tmp_path: Path, *, max_observers: int = 8) -> LiveServer:
    out = tmp_path / "f7"
    out.mkdir(parents=True, exist_ok=True)
    pack = load_pack(PACK_DIR)
    kernel = WorldKernel(pack=pack, seed=SEED, log=EventLog(out / "events.jsonl"),
                         snapshot_every=0, checkpoint_dir=None)
    sem = world_clock.derive_clock_semantics(pack)
    world = LiveWorld(kernel, sem=sem, pace_s_per_tick=0.02, warmup=0, max_observers=max_observers)
    return LiveServer(world, bind="127.0.0.1", port=0, allow_remote=False).start()


def test_quota_is_released_after_the_fd_is_closed(tmp_path, monkeypatch):
    """① 归还点必须晚于 `close_request()`。

    做法：包一层 `close_request()` 记录**关闭那一刻**的 `http_connections` 读数。
    若归还早于关闭（r4 形态）⇒ 那一刻读数 = 0 ⇒ 本条红。
    """
    server = _build(tmp_path)
    httpd = server.httpd
    seen: list[int] = []
    original_close = LiveHTTPServer.close_request

    def spy(self, request):
        seen.append(self.server_ref.http_connections)
        return original_close(self, request)

    monkeypatch.setattr(LiveHTTPServer, "close_request", spy)

    assert server.admit_accept() is True
    assert server.http_connections == 1
    left, right = socket.socketpair()
    try:
        httpd.shutdown_request(left)
        # ① 关闭那一刻，配额**尚未**归还（= 1）
        assert seen == [1], f"归还点早于 fd 关闭：close_request 时 http_connections={seen}"
        # ② 关闭之后才归还
        assert server.http_connections == 0
        # ③ fd 真的关掉了（不是只改了计数）
        assert left.fileno() == -1
    finally:
        right.close()
        server.stop()


def test_handler_error_is_counted_and_never_printed(tmp_path, capsys):
    """② handler 异常只计数，**不倒 traceback 进 stderr**。"""
    server = _build(tmp_path)
    httpd = server.httpd
    left, right = socket.socketpair()
    try:
        try:
            raise BrokenPipeError(32, "Broken pipe")
        except BrokenPipeError:
            httpd.handle_error(left, ("127.0.0.1", 12345))
        captured = capsys.readouterr()
        assert captured.err == "", f"handler 异常被写进了 stderr（{len(captured.err)} 字节）"
        assert server.handler_errors == 1
        assert server.handler_error_kinds == {"BrokenPipeError": 1}
        # 结构化可观测：错误类别进 /live/health
        health = server.health()
        assert health["handler_errors"] == 1
        assert health["handler_error_kinds"]["BrokenPipeError"] == 1
    finally:
        left.close()
        right.close()
        server.stop()


def test_churn_leaves_no_quota_leak_and_peak_is_bounded(tmp_path):
    """③ 「连上即断」高频 churn 之后：峰值 ≤ 上限，且配额**回到 0**。"""
    server = _build(tmp_path, max_observers=8)
    port = server.port
    limit = server.max_http_connections
    for _ in range(120):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(2.0)
            sock.connect(("127.0.0.1", port))
        except OSError:
            sock.close()
            continue
        sock.close()          # 连上即断，不读响应（观察者 churn 的最坏形态）

    deadline = time.monotonic() + 10.0
    while server.http_connections > 0 and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        assert server.http_connections_peak <= limit, "峰值超过 accept 层配额"
        assert server.http_connections == 0, (
            f"churn 之后配额泄漏：http_connections={server.http_connections}（配额 {limit}）")
    finally:
        server.stop()


def test_connection_socket_timeout_bounds_the_write_path(tmp_path, monkeypatch):
    """④ **既有不变式（r3 更正：非本轮新增）**：连接的 socket 超时同时约束**读与写**。

    依据（`settimeout()` 作用于整个 socket，读写同限）：`setup()` 里那行
    `settimeout(REQUEST_IDLE_TIMEOUT_S)` 在 r4 之前就存在 ⇒ `finish()` 的 flush **本来就**
    受同一超时约束（r5 声称的「新增写超时补丁」实为纯文档改动，Sentinel MEDIUM-1 / Raven L-1）。

    本条的牙口：**删掉** `setup()` 里那行 `settimeout` ⇒ 超时变 `None` ⇒ 必红
    （读数见 `03` 的 M5.2-r3 段 FIX-3）。另钉一条：读超时与 `WRITE_TIMEOUT_S` **必须同值**，
    否则「写路径已被既有超时覆盖」这条 r3 更正不成立。
    """
    server = _build(tmp_path)
    handler_cls = server.httpd.RequestHandlerClass
    monkeypatch.setattr(handler_cls, "handle", lambda self: None)   # 不真读请求
    left, right = socket.socketpair()
    try:
        handler = handler_cls(left, ("127.0.0.1", 0), server.httpd)
        timeout = handler.connection.gettimeout()
        assert timeout is not None, "连接无 socket 超时 ⇒ 读写都可能无界阻塞"
        assert timeout == REQUEST_IDLE_TIMEOUT_S
        assert REQUEST_IDLE_TIMEOUT_S == WRITE_TIMEOUT_S, (
            "读超时与 WRITE_TIMEOUT_S 不再同值 ⇒ 「写路径已被既有 socket 超时覆盖」不再成立"
            "（ADR-019 的 r3 更正需重述）")
    finally:
        right.close()
        server.stop()


def test_handler_error_diagnostics_are_bounded_and_finish_errors_counted(tmp_path, monkeypatch):
    """⑤（**FIX-6 · r3 新增**）有界诊断样本 + `finish()` 吞异常计数。

    为什么需要（Raven §2.6）：r5 的 `handle_error` 只记类名 + 计数（真缺陷只剩一个数字），
    且 `finish()` 吞掉异常后**完全无痕迹** ⇒ 运维可见性净下降。本条钉住：
      ① 诊断样本**有界**（条数 = `HANDLER_ERROR_SAMPLES_MAX`、每条 `repr` ≤ `HANDLER_ERROR_REPR_MAX`）；
      ② 界本身随 `/live/health.handler_error_diagnostics` 公布（可核验「有界」）；
      ③ `finish()` 吞掉的异常进 `finish_errors` / `finish_error_kinds`。
    """
    from http.server import BaseHTTPRequestHandler

    from deephealing_kernel.live import HANDLER_ERROR_REPR_MAX, HANDLER_ERROR_SAMPLES_MAX

    server = _build(tmp_path)
    httpd = server.httpd
    left, right = socket.socketpair()
    try:
        total = HANDLER_ERROR_SAMPLES_MAX + 12
        for _ in range(total):
            try:
                raise BrokenPipeError(32, "Broken pipe " + "x" * (HANDLER_ERROR_REPR_MAX * 2))
            except BrokenPipeError:
                httpd.handle_error(left, ("127.0.0.1", 12345))
        health = server.health()
        assert health["handler_errors"] == total
        assert len(health["handler_errors_last"]) == HANDLER_ERROR_SAMPLES_MAX, "诊断样本没有界"
        assert all(len(item["repr"]) <= HANDLER_ERROR_REPR_MAX
                   for item in health["handler_errors_last"]), "样本 repr 没有截断"
        assert health["handler_error_diagnostics"]["samples_max"] == HANDLER_ERROR_SAMPLES_MAX
        assert health["handler_error_diagnostics"]["max_bytes"] > 0
        assert health["handler_error_kinds"]["BrokenPipeError"] == total
    finally:
        left.close()
        right.close()

    # `finish()` 吞掉的异常必须留痕（注入：让 `super().finish()` 抛 `BrokenPipeError`）
    handler_cls = server.httpd.RequestHandlerClass
    monkeypatch.setattr(handler_cls, "handle", lambda self: None)
    original_finish = BaseHTTPRequestHandler.finish

    def _boom(self):
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr(BaseHTTPRequestHandler, "finish", _boom)
    sock_left, sock_right = socket.socketpair()
    try:
        handler = handler_cls(sock_left, ("127.0.0.1", 0), server.httpd)
        handler.finish()          # 不得冒泡、不得写 stderr
        health = server.health()
        assert health["finish_errors"] >= 1, "finish() 吞掉异常却没留痕"
        assert health["finish_error_kinds"].get("BrokenPipeError", 0) >= 1
    finally:
        monkeypatch.setattr(BaseHTTPRequestHandler, "finish", original_finish)
        sock_left.close()
        sock_right.close()
        server.stop()
