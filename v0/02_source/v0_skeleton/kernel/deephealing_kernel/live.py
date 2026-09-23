"""活的世界 + 只读实时观察通道（V0-M4 新增，设计 §2 D-M4-4 / D-M4-5 / D-M4-6 / D-M4-7 / §4.3）。

本模块只做两件事：

1. **`LiveWorld`**：**自有推进循环**（`advance_loop`）——世界按真实时间自己走，
   **不读观察者数量、不等任何客户端**（D-M4-6：「世界独立于观察者」不是自报字段，是结构）。
   节流**deadline 锚定**（`next = start + n*pace`；`sleep(max(0, next - now))`）并输出 `max_drift_ms`。
2. **`LiveServer`**：stdlib `ThreadingHTTPServer` 上的**只读** HTTP/SSE 观察面（**仅 GET/HEAD**）。

服务边界（P-6 / `R3-RAV-M1` 升 CRITICAL 项的正面处置）：
  - 默认仅本机（`--bind 127.0.0.1`）；跨机必须显式 `--allow-remote`（由 `cli` 在**启动前**判定）；
  - **无任何写世界端点**（没有 `step` / `intent` / `control`）；非 GET/HEAD ⇒ **405** 且**不解析请求体**；
  - 响应路径**零** `os.environ` / `getenv`（本模块不 import `os`），也**零**文件系统访问
    （不 import `pathlib`、不 `open(`）⇒ 路径穿越面在设计层不存在；
  - `Host` 头校验：默认仅 loopback 名（`127.0.0.1` / `localhost` / `::1`），否则 **403**；
    `--allow-remote` 时**额外**放行绑定的具体地址（否则远端连不上）；
  - **不设置** `Access-Control-Allow-Origin`（同源策略即可挡跨源读取）；
  - `X-Content-Type-Options: nosniff`；404/405 的 `detail` 是**固定字面**，不回吐异常原文/绝对路径；
  - SSE 并发上限 `max_observers`（上限进 `/live/health`），超限 ⇒ **503** + 结构化 JSON；
  - **普通 HTTP 观察路径**（`/live/state` `/live/health` `/live/meta`）**两级**并发上限
    （**与 `max_observers` 同源**，上限进 `/live/health`）：
    ① **accept 层**连接准入 `max_http_connections = max(4, 4 × max_observers)`
       （**F7 · r4**：在 `LiveHTTPServer.process_request()` 里、**起线程之前**判；
       超限 ⇒ 不 spawn、尽力回结构化 503 `E_HTTP_QUOTA` 并**立即关连接** ⇒ fd 立刻还回去。
       **为什么必须在 accept 层**：fd 是 `accept()` 那一刻被消耗的，配额若在 handler 里判，
       accept churn（建立即关、高频重连）会在配额生效前就把 fd 吃光）；
    ② **请求级** `max_http_inflight = max(2, 2 × max_observers)`（挡 CPU 放大：
       `state_projection()` 每次请求都重建 `world.to_state()` + 两次哈希）；
    另有空闲读超时 `REQUEST_IDLE_TIMEOUT_S`（挡「已建立并保持」的 keep-alive 连接）。
    超限 ⇒ **503 `E_HTTP_QUOTA`** + 结构化 JSON（**不排队、不静默、不耗 fd**，立即关连接）；
    `daemon_threads=True` + 每连接写超时 + 心跳。
  - **F7 · r5 加固（有界回收的补丁，与上面的并发上限同批）**：
    ① 配额归还点从 handler 的 `finish()` 移到 `LiveHTTPServer.shutdown_request()`
       —— **fd 真正关掉之后**才归还，配额语义 = 「同时打开的 fd 上限」（r4 的归还点早于
       `close_request()`，中间一旦有长阻塞，同时打开的 fd 可远超配额）；
    ② **写路径超时：确认既有 socket 超时已覆盖（r3 更正 · 无代码改动）**。
       r5 曾声称「`setup()` 统一设写超时（r4 只在 SSE 路径设）」，但 `settimeout()` 作用于
       **整个 socket（读写同限）**，而 `setup()` 里的 `self.connection.settimeout(REQUEST_IDLE_TIMEOUT_S)`
       在 r4 之前就存在、取值 5.0 == `WRITE_TIMEOUT_S` ⇒ 写路径**本来就受同一超时约束**，
       「普通端点的 flush 会无界阻塞」这条断言与事实**相反**。该条**未落地也无需落地**：
       r3 起按事实表述（依据：Sentinel MEDIUM-1 + Raven L-1，见 `07_adr.md` ADR-019 的更正段）。
       回退/负对照面：删掉 `setup()` 里那行 `settimeout` ⇒ 连接超时变 `None` ⇒
       `tests/test_m52_f7_fd_accounting.py` 的「连接超时」不变式**必红**；
    ③ `LiveHTTPServer.handle_error()` 覆写：handler 异常**只计数**（`/live/health.handler_errors`
       + `handler_error_kinds`），**不倒 traceback 进 stderr** —— 观察者「连上即断」是预期噪声，
       stdlib 默认实现会把它变成无界 stderr 写（实测单臂 90~127MB），线程串行排在 stderr 锁上，
       handler 完成变慢 ⇒ fd 回收变慢。
       **r3 补可观测性（FIX-6）**：另留**有界**诊断样本（首 `HANDLER_ERROR_SAMPLES_MAX` 条、
       每条 `repr(exc)` 截断到 `HANDLER_ERROR_REPR_MAX` 字符）⇒ `/live/health.handler_errors_last`；
       `finish()` 吞掉的异常另记 `finish_errors` / `finish_error_kinds`（此前「连上即断」的噪声
       从「有痕迹」变成「完全无痕迹」）。
       **为什么不在本模块落文件**：本模块的零文件系统访问是**设计属性**（见上一条：不 import
       `pathlib`、不 `open(` ⇒ 路径穿越面在设计层不存在）；落盘由 `cli` 从**有界内存样本**写出
       （`live_handler_errors.jsonl`，条数与字节双重有界）。

**世界状态的持久化不在这里**（`live_state.json` 由 `cli` 写）：本模块只产出数据。
"""

from __future__ import annotations

import errno
import json
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from . import snapshot as snapshot_mod
from . import world_clock

DEFAULT_BIND = "127.0.0.1"
DEFAULT_LIVE_PORT = 8899
#: `run --ws-port` 的默认值：**0 = 不监听**（最小权限；8787 已是会话侧代理端口）
DEFAULT_WS_PORT = 0
MAX_OBSERVERS_DEFAULT = 8
#: **普通 HTTP 观察路径**的并发上限与 `max_observers` 的倍数关系（F7 · r3/r4）：
#: 请求级上限 = `max(2, HTTP_INFLIGHT_PER_OBSERVER × max_observers)`（默认 8 ⇒ 16 条在途请求）；
#: 连接级上限 = `max(4, HTTP_CONN_PER_OBSERVER × max_observers)`（默认 8 ⇒ 32 条连接），
#: **在 accept 层（起线程之前）执行**（r4：fd 是 `accept()` 那一刻被消耗的）。
#: 两者都从 `max_observers` 派生 ⇒ **同源**，不引入第二个互不相干的旋钮。
#: **为什么两级都要**：只挡「在途请求」挡不住**空闲 keep-alive 连接**——它不占在途额度却
#: 一直占着 1 线程 + 1 fd（实测：只加请求级上限时 fd 仍能堆到 3739/4096）；
#: 只挡「连接数」挡不住**单连接高频轮询**的 CPU 放大（每次请求都重建状态投影）。
HTTP_INFLIGHT_PER_OBSERVER = 2
HTTP_CONN_PER_OBSERVER = 4
#: 普通 HTTP 连接的**空闲读超时**：keep-alive 空闲连接不得无限期占着线程 + fd
#: （`BaseHTTPRequestHandler.handle_one_request` 对 `TimeoutError` 是**干净关连接**）。
REQUEST_IDLE_TIMEOUT_S = 5.0
SUBSCRIBER_QUEUE_MAX = 256
WRITE_TIMEOUT_S = 5.0
HEARTBEAT_S = 10.0
#: **有界诊断样本（FIX-6 · r3）**：handler 异常只留**首 N 条**样本（每条 `repr(exc)` 截断），
#: 使「预期噪声」之外的**真缺陷**仍有结构化痕迹，同时不给内存/日志留无界增长面。
HANDLER_ERROR_SAMPLES_MAX = 8
HANDLER_ERROR_REPR_MAX = 200
FINISH_ERROR_KINDS_MAX = 16
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

ERROR_BIND_REFUSED = "E_BIND_REFUSED"
ERROR_ADDRINUSE = "E_ADDRINUSE"
ERROR_METHOD_NOT_ALLOWED = "E_METHOD_NOT_ALLOWED"
ERROR_NOT_FOUND = "E_NOT_FOUND"
ERROR_OBSERVER_QUOTA = "E_OBSERVER_QUOTA"
ERROR_HTTP_QUOTA = "E_HTTP_QUOTA"
ERROR_HOST_FORBIDDEN = "E_HOST_FORBIDDEN"


class BindRefused(Exception):
    """绑定地址非 loopback 且未显式 `--allow-remote`（启动前拒绝，不监听、不留半截产物）。"""

    code = ERROR_BIND_REFUSED


class AddrInUse(Exception):
    """端口被占（结构化失败，**不静默降级**）。"""

    code = ERROR_ADDRINUSE


def is_loopback(bind: str) -> bool:
    """绑定地址是否为 loopback（`--allow-remote` 的判定依据）。"""
    return str(bind) in LOOPBACK_HOSTS


# ---------------------------------------------------------------------------- 世界（自有推进）
class LiveWorld:
    """按真实时间自己推进的世界 + 订阅者集合（订阅者只影响**推送**，不影响**推进**）。"""

    def __init__(self, kernel, *, sem: dict, pace_s_per_tick: float = 1.0, warmup: int = 0,
                 max_observers: int = MAX_OBSERVERS_DEFAULT, started_at: float | None = None) -> None:
        self.kernel = kernel
        self.sem = sem
        self.pace_s_per_tick = float(pace_s_per_tick)
        self.warmup = int(warmup)
        self.max_observers = int(max_observers)
        self.started_at = float(started_at if started_at is not None else time.time())
        self.running = False
        self.ticks_advanced = 0
        self.max_drift_ms = 0.0
        self._lock = threading.Lock()
        self._subscribers: dict[int, queue.Queue] = {}
        self._next_token = 0

    # ------------------------------------------------------------------ 只读视图
    @property
    def tick(self) -> int:
        return int(self.kernel.world.tick)

    def clock(self) -> str:
        return world_clock.clock_of(self.tick, self.sem)

    def world_day(self) -> int:
        return world_clock.world_day_of(self.tick, self.sem)

    def state_hash(self) -> str:
        return snapshot_mod.hash_object(self.kernel.world.to_state())

    def event_chain_hash(self) -> str:
        log = self.kernel.log
        return log.last_hash if log is not None else snapshot_mod.GENESIS_HASH

    def observers(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def state_projection(self) -> dict:
        """**当前** tick 的 `world.to_state()` 只读投影 + 派生读数（不重算、不自造）。"""
        state = self.kernel.world.to_state()
        return {
            "tick": self.tick,
            "clock": self.clock(),
            "world_day": self.world_day(),
            "timezone": world_clock.TZ_NAME,
            "state_hash": snapshot_mod.hash_object(state),
            "event_chain_hash": self.event_chain_hash(),
            "observers": self.observers(),
            "read_only": True,
            "state": state,
        }

    # ------------------------------------------------------------------ 订阅
    def subscribe(self) -> int | None:
        """注册一个观察者；达到 `max_observers` ⇒ 返回 `None`（调用方转 503）。"""
        with self._lock:
            if len(self._subscribers) >= self.max_observers:
                return None
            self._next_token += 1
            token = self._next_token
            self._subscribers[token] = queue.Queue(maxsize=SUBSCRIBER_QUEUE_MAX)
            return token

    def unsubscribe(self, token: int) -> None:
        with self._lock:
            self._subscribers.pop(int(token), None)

    def subscriber_queue(self, token: int) -> queue.Queue | None:
        """取某个订阅者的推送队列（`LiveServer` 的 SSE 循环消费；None ⇒ 已注销）。"""
        with self._lock:
            return self._subscribers.get(int(token))

    def notify_subscribers(self, tick: int, clock: str) -> None:
        """每 tick 推「一帧 state + 一帧 clock」（队列满则丢**最旧**，永不阻塞推进循环）。"""
        payload = {
            "tick": int(tick),
            "clock": clock,
            "timezone": world_clock.TZ_NAME,
            "state_hash": self.state_hash(),
            "event_chain_hash": self.event_chain_hash(),
            "state": self.kernel.world.to_state(),
        }
        frame = _sse_frames(payload)
        with self._lock:
            targets = [self._subscribers[token] for token in sorted(self._subscribers)]
        for target in targets:
            try:
                target.put_nowait(frame)
            except queue.Full:
                try:
                    target.get_nowait()          # 丢最旧
                    target.put_nowait(frame)
                except (queue.Empty, queue.Full):
                    pass

    # ------------------------------------------------------------------ 推进
    def advance_loop(self, *, max_ticks: int | None = None, stop_event=None) -> dict:
        """**自有**推进循环：deadline 锚定，1 个 tick = `pace_s_per_tick` 真实秒。

        **不读** `self.observers()`、**不等待**任何客户端（D-M4-6）。
        返回 `{ticks, elapsed_s, max_drift_ms, tick, clock, observers}`。
        """
        started = time.monotonic()
        advanced = 0
        self.running = True
        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    break
                if max_ticks is not None and advanced >= int(max_ticks):
                    break
                advanced += 1
                self.kernel.step()
                self.notify_subscribers(self.tick, self.clock())
                deadline = started + advanced * self.pace_s_per_tick
                delay = deadline - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                drift_ms = abs(time.monotonic() - deadline) * 1000.0
                if drift_ms > self.max_drift_ms:
                    self.max_drift_ms = drift_ms
        finally:
            self.running = False
            self.ticks_advanced += advanced
        return {
            "ticks": advanced,
            "elapsed_s": round(time.monotonic() - started, 6),
            "max_drift_ms": round(self.max_drift_ms, 3),
            "tick": self.tick,
            "clock": self.clock(),
            "observers": self.observers(),
        }

    def seal_state(self) -> dict:
        """封存读数（`cli` 写进 `live_state.json`；本模块**不碰文件系统**）。"""
        return {
            "schema_version": "1.0.0",
            "tick": self.tick,
            "clock": self.clock(),
            "state_hash": self.state_hash(),
            "event_chain_hash": self.event_chain_hash(),
            "running": False,
        }


def _sse_frames(payload: dict) -> bytes:
    """一个 tick 的两帧：`event: state` + `event: clock`。"""
    state = {key: value for key, value in payload.items() if key != "clock"}
    clock = {"tick": payload["tick"], "clock": payload["clock"], "timezone": payload["timezone"]}
    return (
        "event: state\n"
        f"data: {json.dumps(state, ensure_ascii=False, sort_keys=True)}\n\n"
        "event: clock\n"
        f"data: {json.dumps(clock, ensure_ascii=False, sort_keys=True)}\n\n"
    ).encode("utf-8")


# ---------------------------------------------------------------------------- 只读服务
class LiveHTTPServer(ThreadingHTTPServer):
    """`ThreadingHTTPServer` + **accept 层连接准入**（F7 · r4）。

    `ThreadingHTTPServer` 的默认路径是「`accept()`（吃 fd）⇒ 起线程 ⇒ 才轮到 handler」，
    配额若在 handler 里判就**永远慢一步**（r3 的实测形态）。这里覆写 `process_request()`：
    **在起线程之前**做准入，超限 ⇒ 不 spawn、立即关连接 ⇒ fd 与线程**同时**有界。
    """

    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, *, server_ref: "LiveServer",
                 bind_and_activate: bool = True) -> None:
        self.server_ref = server_ref
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)

    def process_request(self, request, client_address) -> None:
        if not self.server_ref.admit_accept():
            self.server_ref.reject_at_accept(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            # 线程起不来（资源耗尽等）⇒ 名额必须还回去，否则配额会被永久占死
            self.server_ref.release_accept()
            try:
                request.close()
            except OSError:
                pass
            raise

    def shutdown_request(self, request) -> None:
        """**F7（r5）：fd 真正关掉之后**才归还 accept 配额。

        r4 把归还点放在 handler 的 `finish()` 里 —— 那时 fd **还开着**（`shutdown_request`
        要等 `process_request_thread` 的 `finally` 才跑）。两者之间一旦有长阻塞
        （实测：`finish()` 的 flush 撞 `BrokenPipeError` ⇒ 往 stderr 写 100MB 级 traceback，
        线程串行排在 stderr 锁上），配额已被归还而 fd 未关 ⇒ **同时打开的 fd 数可以远超配额**。

        把归还点挪到 `close_request()` 之后 ⇒ 配额语义变成「**同时打开的 fd 上限**」，
        与「fd 是 `accept()` 那一刻被消耗的」这条事实对齐。
        """
        try:
            super().shutdown_request(request)
        finally:
            self.server_ref.release_accept()

    def handle_error(self, request, client_address) -> None:
        """**F7（r5）：handler 异常计数，不倒 traceback 进 stderr。**

        stdlib 默认实现会把整段 traceback 写 stderr。观察者频繁「连上即断」时，
        `finish()` 的 flush 撞 `BrokenPipeError` 是**预期噪声**，默认实现却把它变成
        **无界 stderr 写**（实测：单臂 90~127MB）——线程串行排在 stderr 锁上，
        handler 完成变慢 ⇒ fd 回收变慢（r3 的失败形态）。

        这里只计数（`/live/health.handler_errors`），错误类别可观测，但不写 stderr。
        """
        self.server_ref.note_handler_error(request, client_address)


class LiveServer:
    """只读 HTTP/SSE 观察服务（`ThreadingHTTPServer`；daemon 线程，仅存活于本进程运行期）。"""

    def __init__(self, world: LiveWorld, *, bind: str = DEFAULT_BIND, port: int = DEFAULT_LIVE_PORT,
                 allow_remote: bool = False) -> None:
        self.world = world
        self.bind = str(bind)
        self.port = int(port)
        self.allow_remote = bool(allow_remote)
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        # **F7（r3）**：普通 HTTP 观察路径的并发上限（与 `max_observers` 同源）
        self.max_http_inflight = max(2, HTTP_INFLIGHT_PER_OBSERVER * int(world.max_observers))
        self._inflight = threading.BoundedSemaphore(self.max_http_inflight)
        self._inflight_lock = threading.Lock()
        self.http_inflight = 0
        self.http_inflight_peak = 0
        self.http_rejections = 0
        # **F7（r3）**：连接级上限（挡住「空闲 keep-alive 连接」这条不占在途额度的 fd 通路）
        self.max_http_connections = max(4, HTTP_CONN_PER_OBSERVER * int(world.max_observers))
        self._conn_lock = threading.Lock()
        self.http_connections = 0
        self.http_connections_peak = 0
        self.connection_rejections = 0
        # **F7（r5）**：handler 异常计数（替代「倒 traceback 进 stderr」）
        self._error_lock = threading.Lock()
        self.handler_errors = 0
        self.handler_error_kinds: dict[str, int] = {}
        # **FIX-6（r3）**：**有界**诊断样本（首 N 条，`repr(exc)` 截断）⇒ `/live/health.handler_errors_last`
        # 与 `cli` 的有界落盘；以及 `finish()` 吞掉的异常计数（此前完全无痕迹）。
        self.handler_error_samples: list[dict] = []
        self.finish_errors = 0
        self.finish_error_kinds: dict[str, int] = {}

    # ------------------------------------------------------------------ handler 异常记账（F7 · r5 / FIX-6 · r3）
    def note_handler_error(self, request, client_address) -> None:
        """记一次 handler 异常（**不写 stderr**）。类别用异常类名聚合，便于区分
        「观察者断开」（`BrokenPipeError` / `ConnectionResetError`，预期噪声）与真缺陷。

        **FIX-6（r3）**：另留**有界**诊断样本 —— 首 `HANDLER_ERROR_SAMPLES_MAX` 条，
        每条 `repr(exc)` 截断到 `HANDLER_ERROR_REPR_MAX` 字符。界（条数 / 字节）随
        `/live/health.handler_error_diagnostics` 一并公布，便于核验「有界」这件事。
        """
        kind = "unknown"
        exc = sys.exc_info()[1]
        if exc is not None:
            kind = type(exc).__name__
        sample: dict | None = None
        with self._error_lock:
            self.handler_errors += 1
            self.handler_error_kinds[kind] = self.handler_error_kinds.get(kind, 0) + 1
            if len(self.handler_error_samples) < HANDLER_ERROR_SAMPLES_MAX:
                try:
                    address = f"{client_address[0]}:{client_address[1]}"
                except (TypeError, IndexError):
                    address = "unknown"
                detail = "" if exc is None else repr(exc)[:HANDLER_ERROR_REPR_MAX]
                self.handler_error_samples.append(
                    {"seq": self.handler_errors, "kind": kind, "client": address, "repr": detail})
        return None

    def note_finish_error(self, error: BaseException | None) -> None:
        """记一次被 `finish()` 吞掉的异常（**FIX-6 · r3**）：`finish()` 的 flush 撞
        「观察者连上即断」是预期噪声，但吞掉之后**完全无痕迹** ⇒ 这里补计数与类别聚合
        （类别字典上限 `FINISH_ERROR_KINDS_MAX`，超出记入 `other`）。"""
        kind = "unknown" if error is None else type(error).__name__
        with self._error_lock:
            self.finish_errors += 1
            if kind in self.finish_error_kinds or len(self.finish_error_kinds) < FINISH_ERROR_KINDS_MAX:
                self.finish_error_kinds[kind] = self.finish_error_kinds.get(kind, 0) + 1
            else:
                self.finish_error_kinds["other"] = self.finish_error_kinds.get("other", 0) + 1

    # ------------------------------------------------------------------ 普通 HTTP 连接准入（**accept 层**）
    def admit_accept(self) -> bool:
        """**accept 层**连接准入（F7 · r4）：在**起线程之前**判配额。

        为什么必须在这里判（r3 的教训）：r3 的请求级/连接级上限都在 `_dispatch()` 里判，
        那时连接**已经被 `accept()`、fd 已经被消耗**，线程也已经起了 —— 上限能挡「已建立并保持」
        的连接，却挡不住 **accept churn**：只要 handler 线程慢于 accept（实测：线程卡在串行化的
        stderr 锁上写 traceback，10s 写了 11 万行），fd 就在配额判断之前被吃光 ⇒ `Errno 24`
        ⇒ 封存失败 ⇒ daemon 线程活到解释器 finalize ⇒ `_enter_buffered_busy` ⇒ SIGABRT。

        超限 ⇒ `False`：调用方**不 spawn 线程**、立即关连接（fd 立刻还回去）。
        """
        with self._conn_lock:
            if self.http_connections >= self.max_http_connections:
                self.connection_rejections += 1
                return False
            self.http_connections += 1
            if self.http_connections > self.http_connections_peak:
                self.http_connections_peak = self.http_connections
            return True

    def release_accept(self) -> None:
        """一条**已被 accept 准入**的连接结束（handler 的 `finish()` 里对称递减）。"""
        with self._conn_lock:
            if self.http_connections > 0:
                self.http_connections -= 1

    def reject_at_accept(self, request) -> None:
        """accept 层超限 ⇒ **尽力**回一个结构化 503 并**立即关连接**。

        **非阻塞是硬要求**：这段代码跑在 accept 循环里，任何阻塞都会把「拒绝」变成「停服」
        （r3 的失败形态之一就是 accept 循环被拖死）。因此用 `setblocking(False)` + 一次
        `send()`：载荷 ~200B 远小于 socket 发送缓冲，loopback 上一次写完；写不动就静默关。
        结构化语义与 `E_HTTP_QUOTA` 一致（连接被拒的**权威信号**是关连接，计数进 `/live/health`）。
        """
        payload = json.dumps({
            "error": ERROR_HTTP_QUOTA,
            "detail": "connection limit reached at accept",
            "stage": "accept",
            "max_connections": self.max_http_connections,
        }, ensure_ascii=False, sort_keys=True).encode("utf-8")
        head = (
            b"HTTP/1.1 503 Service Unavailable\r\n"
            b"Content-Type: application/json; charset=utf-8\r\n"
            b"X-Content-Type-Options: nosniff\r\n"
            b"Cache-Control: no-store\r\n"
            b"Connection: close\r\n"
            b"Content-Length: " + str(len(payload)).encode("ascii") + b"\r\n\r\n"
        )
        try:
            request.setblocking(False)
            request.send(head + payload)
        except OSError:
            pass
        finally:
            try:
                request.close()
            except OSError:
                pass

    # ------------------------------------------------------------------ 普通 HTTP 并发准入
    def admit_http(self) -> bool:
        """准入一条普通观察请求（**非阻塞**）；超限 ⇒ `False`（调用方转 503，不排队）。"""
        if not self._inflight.acquire(blocking=False):
            with self._inflight_lock:
                self.http_rejections += 1
            return False
        with self._inflight_lock:
            self.http_inflight += 1
            if self.http_inflight > self.http_inflight_peak:
                self.http_inflight_peak = self.http_inflight
        return True

    def release_http(self) -> None:
        with self._inflight_lock:
            self.http_inflight -= 1
        self._inflight.release()

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> "LiveServer":
        """启动监听；端口被占 ⇒ `AddrInUse`（exit 1，不静默降级）。"""
        handler = _make_handler(self)
        try:
            self.httpd = LiveHTTPServer((self.bind, self.port), handler, server_ref=self)
        except OSError as exc:
            if exc.errno in (errno.EADDRINUSE, errno.EACCES):
                raise AddrInUse(
                    f"{ERROR_ADDRINUSE}: cannot bind {self.bind}:{self.port} ({exc.strerror}); "
                    "refusing to silently skip listening"
                ) from exc
            raise
        self.httpd.daemon_threads = True
        self.port = int(self.httpd.server_address[1])
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="live-http", daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self.thread is not None:
            self.thread.join(timeout=WRITE_TIMEOUT_S)
            self.thread = None

    @property
    def listening(self) -> bool:
        return self.httpd is not None

    # ------------------------------------------------------------------ 元数据
    def bind_policy(self) -> dict:
        warning = None
        if self.allow_remote:
            warning = (
                "remote access is ENABLED and the read-only channel has NO authentication: anyone on "
                "the same network can read /live/state and /live/meta (which includes the world seed). "
                "There is no write path, but the information surface is exposed."
            )
        return {
            "bind": self.bind,
            "port": self.port,
            "allow_remote": self.allow_remote,
            "loopback_only": is_loopback(self.bind) and not self.allow_remote,
            "default_bind": DEFAULT_BIND,
            "read_only": True,
            "write_endpoints": [],
            "warning": warning,
        }

    def meta(self) -> dict:
        kernel = self.world.kernel
        pack = kernel.pack
        return {
            "pack_id": pack.manifest["id"] if pack is not None else None,
            "pack_version": pack.manifest["version"] if pack is not None else None,
            "seed": kernel.seed,
            "timezone": world_clock.TZ_NAME,
            "clock_semantics": self.world.sem,
            "pace_s_per_tick": self.world.pace_s_per_tick,
            "tick_semantics": self.world.sem.get("tick_semantics"),
            "warmup_ticks": self.world.warmup,
            "started_at": self.world.started_at,
            "npcs": len(kernel.world.query(kind="npc")),
            "tick": self.world.tick,
            "clock": self.world.clock(),
            "bind_policy": self.bind_policy(),
            "read_only": True,
        }

    def health(self) -> dict:
        return {
            "ok": True,
            "listening": self.listening,
            "bind": self.bind,
            "port": self.port,
            "read_only": True,
            "tick": self.world.tick,
            "clock": self.world.clock(),
            "observers": self.world.observers(),
            "max_observers": self.world.max_observers,
            "max_http_inflight": self.max_http_inflight,
            "http_inflight": self.http_inflight,
            "http_inflight_peak": self.http_inflight_peak,
            "http_rejections": self.http_rejections,
            "max_http_connections": self.max_http_connections,
            "connection_admission": "accept",       # F7（r4）：连接级配额在 accept 层（起线程之前）判
            "http_connections": self.http_connections,
            "http_connections_peak": self.http_connections_peak,
            "connection_rejections": self.connection_rejections,
            "handler_errors": self.handler_errors,
            "handler_error_kinds": dict(sorted(self.handler_error_kinds.items())),
            # **FIX-6（r3）**：有界诊断样本 + 界（条数 / 字节）+ `finish()` 吞异常计数
            "handler_errors_last": list(self.handler_error_samples),
            "handler_error_diagnostics": {
                "samples_max": HANDLER_ERROR_SAMPLES_MAX,
                "repr_max_chars": HANDLER_ERROR_REPR_MAX,
                "samples_kept": len(self.handler_error_samples),
                "max_bytes": HANDLER_ERROR_SAMPLES_MAX * (HANDLER_ERROR_REPR_MAX + 128),
            },
            "finish_errors": self.finish_errors,
            "finish_error_kinds": dict(sorted(self.finish_error_kinds.items())),
            "request_idle_timeout_s": REQUEST_IDLE_TIMEOUT_S,
            "write_timeout_s": WRITE_TIMEOUT_S,
            "pace_s_per_tick": self.world.pace_s_per_tick,
            "running": self.world.running,
        }

    # ------------------------------------------------------------------ Host 校验
    def host_allowed(self, host_header: str | None) -> bool:
        """仅接受 loopback 名（`--allow-remote` 时额外放行绑定的具体地址）。"""
        if not host_header:
            return False
        raw = str(host_header).strip()
        if raw.startswith("["):
            name = raw.split("]", 1)[0][1:]
        else:
            name = raw.rsplit(":", 1)[0] if raw.count(":") == 1 else raw
        allowed = set(LOOPBACK_HOSTS)
        if self.allow_remote and self.bind not in ("0.0.0.0", "::"):
            allowed.add(self.bind)
        return name in allowed


def _make_handler(server_ref: LiveServer):
    """构造请求处理器（闭包持有 `LiveServer`；只读、无文件系统、无 env）。"""

    class LiveHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "deephealing-live"
        sys_version = ""

        # 不打访问日志（避免把请求路径/查询串写进 stderr）
        def log_message(self, *args) -> None:  # noqa: D102
            return

        # -------------------------------------------------------------- 连接生命周期（F7 · r3/r4）
        def setup(self) -> None:
            """连接建立：**socket 超时（读写同限）**。

            连接**计数不在这里**做：F7（r4）把连接准入前移到 `LiveHTTPServer.process_request()`
            （**起线程之前**）—— 在 handler 里计数等于「fd 已经被 accept 吃掉之后才记账」。

            **写超时（r3 更正）**：`settimeout()` 作用于**整个 socket**（读与写同限），
            这里的取值 `REQUEST_IDLE_TIMEOUT_S = 5.0` 与 `WRITE_TIMEOUT_S = 5.0` 相等
            ⇒ 普通端点的 `finish()` flush **本来就**受 5s 约束，不存在「无界阻塞」缺口，
            r5 声称的「统一设写超时」**未落地也无需落地**（Sentinel MEDIUM-1 / Raven L-1；
            见 `07_adr.md` ADR-019 的更正段）。**不要**删掉这行 —— 删掉它超时变 `None`，
            连接生命周期就没有任何界（`tests/test_m52_f7_fd_accounting.py` 有对应不变式）。
            """
            super().setup()
            try:
                self.connection.settimeout(REQUEST_IDLE_TIMEOUT_S)
            except OSError:      # 已关闭 / 不支持 ⇒ 不影响功能
                pass

        def finish(self) -> None:
            """收尾：**容忍对端断开**（观察者连上即断是预期噪声）。

            F7（r5）：归还 accept 配额的动作**已移到 `LiveHTTPServer.shutdown_request()`**
            （fd 真正关掉之后）—— 在这里归还等于「配额已还、fd 未关」，正是 fd 超出配额的那条通路。
            这里只负责把 `finish()` 的 flush 异常吃掉（否则它会冒到 `handle_error`）。

            **FIX-6（r3）**：吞异常**必须留痕** —— 每次吞掉都调 `note_finish_error()`
            （`/live/health.finish_errors` + `finish_error_kinds`），否则「连上即断」这条
            噪声从「有痕迹（stderr）」变成「完全无痕迹」。
            """
            try:
                super().finish()
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError) as error:
                self.close_connection = True
                server_ref.note_finish_error(error)

        # -------------------------------------------------------------- 响应原语
        def _write_headers(self, code: int, content_type: str, length: int, *, close: bool) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            # **显式不设置** Access-Control-Allow-Origin（同源策略即可挡跨源读取）
            if close:
                self.send_header("Connection", "close")
            self.end_headers()

        def _send_json(self, code: int, payload: dict, *, close: bool = False) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self._write_headers(code, "application/json; charset=utf-8", len(body), close=close)
            if self.command != "HEAD":
                self.wfile.write(body)

        def _error(self, code: int, error_code: str, detail: str, **extra) -> None:
            payload = {"error": error_code, "detail": detail}
            payload.update(extra)
            self._send_json(code, payload, close=True)

        # -------------------------------------------------------------- 方法面
        def do_GET(self) -> None:  # noqa: N802
            self._dispatch()

        def do_HEAD(self) -> None:  # noqa: N802
            self._dispatch()

        def _reject_method(self) -> None:
            """非 GET/HEAD ⇒ 405（**不解析请求体**，直接拒绝并关连接）。"""
            self._error(405, ERROR_METHOD_NOT_ALLOWED, "live channel is read-only")

        do_POST = _reject_method      # noqa: N815
        do_PUT = _reject_method       # noqa: N815
        do_PATCH = _reject_method     # noqa: N815
        do_DELETE = _reject_method    # noqa: N815
        do_OPTIONS = _reject_method   # noqa: N815
        do_TRACE = _reject_method     # noqa: N815
        do_CONNECT = _reject_method   # noqa: N815

        # -------------------------------------------------------------- 普通端点的并发准入
        def _guarded(self, produce) -> None:
            """普通观察端点的**并发准入**（F7 · r3）。

            超限 ⇒ **立即**结构化 503（不排队、不静默、不占 fd）。上限同时挡 CPU 放大：
            `state_projection()` 每次请求都重建 `world.to_state()` + 两次哈希，
            只挡 fd 不挡 CPU 仍会被打穿。
            """
            if not server_ref.admit_http():
                self._error(503, ERROR_HTTP_QUOTA, "observation concurrency limit reached",
                            max_inflight=server_ref.max_http_inflight)
                return
            try:
                self._send_json(200, produce())
            finally:
                server_ref.release_http()

        # -------------------------------------------------------------- 路由
        def _dispatch(self) -> None:
            if not server_ref.host_allowed(self.headers.get("Host")):
                self._error(403, ERROR_HOST_FORBIDDEN, "Host header must be a loopback name")
                return
            path = urlsplit(self.path).path
            if len(path) > 1 and path.endswith("/"):
                path = path.rstrip("/")
            if path in ("/live/health", "/live/meta", "/live/state"):
                # **连接级准入已在 accept 层完成**（F7 · r4：`LiveHTTPServer.process_request()`
                # 在起线程之前判，超限的连接根本没进到 handler）⇒ 这里不再重复判，
                # 否则就是「fd 已被消耗之后才记账」的那条老路。
                pass
            if path == "/live/health":
                self._guarded(server_ref.health)
                return
            if path == "/live/meta":
                self._guarded(server_ref.meta)
                return
            if path == "/live/state":
                self._guarded(server_ref.world.state_projection)
                return
            if path == "/live/stream":
                self._stream()
                return
            self._error(404, ERROR_NOT_FOUND, "unknown live endpoint")

        # -------------------------------------------------------------- SSE
        def _stream(self) -> None:
            world = server_ref.world
            token = world.subscribe()
            if token is None:
                self._error(503, ERROR_OBSERVER_QUOTA, "observer limit reached",
                            max_observers=world.max_observers)
                return
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Connection", "close")
                self.end_headers()
                if self.command == "HEAD":
                    return
                self.connection.settimeout(WRITE_TIMEOUT_S)
                # 连入即给**当前**时刻的一帧（不是从 genesis 重放）
                self._write_raw(_sse_frames({
                    "tick": world.tick,
                    "clock": world.clock(),
                    "timezone": world_clock.TZ_NAME,
                    "state_hash": world.state_hash(),
                    "event_chain_hash": world.event_chain_hash(),
                    "state": world.kernel.world.to_state(),
                }))
                target = world.subscriber_queue(token)
                while target is not None:
                    try:
                        frame = target.get(timeout=HEARTBEAT_S)
                    except queue.Empty:
                        self._write_raw(b": heartbeat\n\n")
                        continue
                    self._write_raw(frame)
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                pass
            finally:
                world.unsubscribe(token)
                self.close_connection = True

        def _write_raw(self, data: bytes) -> None:
            self.wfile.write(data)
            self.wfile.flush()

    return LiveHandler
