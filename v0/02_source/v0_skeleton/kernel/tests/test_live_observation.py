"""W12 实时观察通道判据（AC-M4-10 ①~④ / AC-M4-9①⑥；设计 §2 D-M4-4/D-M4-5/D-M4-6、§11 D-M4-15⑤/D-M4-16）。

① 观察者在 T 时刻连入 ⇒ 读到**当前** tick（**不是**从 genesis 重放）—— 给三方读数（世界 tick /
   通道 tick / 墙上钟）；
② 断开重连后仍看到**当前**时刻；
③ 通道读数 == 内核**直读**（逐字段对账）；
④ 负例：把通道退回「读 `events.jsonl` 按 tick 播」⇒ ① **必须变红**（用户明确否定的「回放」形态）；
⑤ 断开**所有**观察者后世界继续推进（三读数 + `observers: 0`）；
⑥ 服务边界（D-M4-16）：Host 校验 403 / **不设** ACAO / nosniff / 观察者上限 503（含 +1 反例）/
   写尝试 405 / `DH_TEST_SECRET` 不出现在任何端点与 SSE 每一帧、也不出现在 404/405 的 `detail`；
⑦ 观察者独立性对照（D-M4-15⑤）：同一 N 秒窗口，0 个观察者 vs 2 个观察者连着 ⇒ tick 增量**相同**，
   连接数由**测试进程自己记账**（不信服务端自报）。
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SEED = 20260921
sys.path.insert(0, str(KERNEL_ROOT))

from deephealing_kernel import world_clock  # noqa: E402
from deephealing_kernel.events import EventLog  # noqa: E402
from deephealing_kernel.live import LiveServer, LiveWorld  # noqa: E402
from deephealing_kernel.pack import load_pack  # noqa: E402
from deephealing_kernel.tick import WorldKernel  # noqa: E402

SECRET_ENV = "DH_TEST_SECRET"
SECRET_VALUE = "m4-super-secret-do-not-leak"


def _build(tmp_path: Path, *, pace: float = 0.02, max_observers: int = 8,
           warmup: int = 0) -> tuple[LiveWorld, LiveServer]:
    out = tmp_path / "live"
    out.mkdir(parents=True, exist_ok=True)
    kernel = WorldKernel(pack=load_pack(PACK_DIR), seed=SEED,
                         log=EventLog(out / "events.jsonl"), snapshot_every=0,
                         checkpoint_dir=None)
    sem = world_clock.derive_clock_semantics(load_pack(PACK_DIR))
    world = LiveWorld(kernel, sem=sem, pace_s_per_tick=pace, warmup=warmup,
                      max_observers=max_observers)
    server = LiveServer(world, bind="127.0.0.1", port=0, allow_remote=False).start()
    return world, server


def _get(server: LiveServer, path: str, *, host: str | None = None, method: str = "GET",
         body: bytes | None = None) -> tuple[int, dict, dict]:
    """返回 (status, headers, json_body)；HTTP 错误也返回（不抛）。"""
    url = f"http://127.0.0.1:{server.port}{path}"
    request = urllib.request.Request(url, data=body, method=method)
    if host:
        request.add_header("Host", host)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), json.loads(exc.read().decode())


class _Channel:
    """SSE 客户端（读前 N 帧；由测试进程自己记账连接数）。"""

    def __init__(self, server: LiveServer, path: str = "/live/stream") -> None:
        self.url = f"http://127.0.0.1:{server.port}{path}"
        self.response = None
        self.frames: list[dict] = []        # `event: state`
        self.clocks: list[dict] = []        # `event: clock`

    def open(self) -> None:
        self.response = urllib.request.urlopen(self.url, timeout=10)

    def read_frames(self, count: int, *, timeout: float = 5.0) -> list[dict]:
        """读 `count` 个 `event: state` 帧 + 与之配对的 `event: clock` 帧。"""
        assert self.response is not None, "SSE 连接未打开"
        deadline = time.monotonic() + timeout
        buffer = b""
        while (len(self.frames) < count or len(self.clocks) < count) and time.monotonic() < deadline:
            chunk = self.response.read(1)
            if not chunk:
                break
            buffer += chunk
            while b"\n\n" in buffer:
                block, buffer = buffer.split(b"\n\n", 1)
                lines = block.decode("utf-8", "replace").splitlines()
                event_name = next((line[7:] for line in lines if line.startswith("event: ")), "")
                data_line = next((line[6:] for line in lines if line.startswith("data: ")), "")
                if not data_line:
                    continue
                if event_name == "state":
                    self.frames.append(json.loads(data_line))
                elif event_name == "clock":
                    self.clocks.append(json.loads(data_line))
        return self.frames

    def close(self) -> None:
        if self.response is not None:
            self.response.close()
            self.response = None


# ---------------------------------------------------------------------------- ① 此刻
def test_observer_reads_the_current_tick_not_a_replay_from_genesis(tmp_path):
    world, server = _build(tmp_path, pace=0.02)
    stop = threading.Event()
    thread = threading.Thread(target=lambda: world.advance_loop(stop_event=stop), daemon=True)
    thread.start()
    channel = _Channel(server)
    try:
        time.sleep(2.0)                      # 世界先走 2 秒 ⇒ tick ≈ 100（远大于 0）
        wall = world_clock.now_utc8()
        channel.open()
        frames = channel.read_frames(1)
        channel_tick = frames[0]["tick"]
        world_tick = world.tick
        print(f"① 三方读数: 世界 tick {world_tick} | 通道 tick {channel_tick} | "
              f"墙上钟 {wall.strftime('%H:%M:%S')} | 通道 clock {channel.clocks[0]['clock']}")
        assert world_tick > 50, f"世界没推进（tick {world_tick}）⇒ ① 无从判定"
        assert abs(channel_tick - world_tick) <= 3, (
            f"通道读到 tick {channel_tick}，当前世界 tick {world_tick} ⇒ 像是从 genesis 重放")
        assert channel_tick != 0, "通道读到 tick 0 ⇒ 那是回放，不是「此刻」"
    finally:
        channel.close()
        stop.set()
        thread.join(timeout=10)
        server.stop()


def test_replay_shaped_channel_turns_the_current_tick_criterion_red(tmp_path):
    """④ 负例：把通道退回「读 `events.jsonl` 按 tick 播」⇒ ① 的判据**必须变红**。

    这里用一个**测试内**的回放型通道（读日志、从 tick 0 按索引播）作对照；
    它与交付实现的差别正是「回放 vs 此刻」，因此 `|通道 tick − 世界 tick| ≤ 3` 必须**不成立**。
    """
    world, server = _build(tmp_path, pace=0.02)
    stop = threading.Event()
    thread = threading.Thread(target=lambda: world.advance_loop(stop_event=stop), daemon=True)
    thread.start()
    try:
        time.sleep(2.0)
        world_tick = world.tick
        assert world_tick > 50

        log_path = tmp_path / "live" / "events.jsonl"
        documents = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        replay_frames = [doc["tick"] for doc in documents if doc["type"] == "snapshot.taken"]
        if not replay_frames:
            replay_frames = [doc["tick"] for doc in documents]
        # 回放型通道的「第一个可读帧」= 日志第一条事件的 tick（≈ 0）
        replay_tick = replay_frames[0] if replay_frames else 0
        print(f"④ 负例对照: 回放型通道 tick {replay_tick} vs 世界 tick {world_tick}")
        assert abs(replay_tick - world_tick) > 3, (
            "回放型通道竟然也满足「≈当前 tick」⇒ ① 是恒真判据（用户否定的回放形态没被挡住）")
    finally:
        stop.set()
        thread.join(timeout=10)
        server.stop()


# ---------------------------------------------------------------------------- ② 重连
def test_reconnect_still_shows_the_current_moment(tmp_path):
    world, server = _build(tmp_path, pace=0.02)
    stop = threading.Event()
    thread = threading.Thread(target=lambda: world.advance_loop(stop_event=stop), daemon=True)
    thread.start()
    first = _Channel(server)
    try:
        first.open()
        first_tick = first.read_frames(1)[0]["tick"]
        first.close()
        time.sleep(1.0)
        second = _Channel(server)
        try:
            second.open()
            second_tick = second.read_frames(1)[0]["tick"]
        finally:
            second.close()
        print(f"② 重连: 首次连入 tick {first_tick} ⇒ 重连后 tick {second_tick}")
        assert second_tick > first_tick, "重连后 tick 没有前进 ⇒ 像是回到起点重放"
        assert abs(second_tick - world.tick) <= 3
    finally:
        first.close()
        stop.set()
        thread.join(timeout=10)
        server.stop()


# ---------------------------------------------------------------------------- ③ 内核直读对账
def test_channel_state_matches_the_kernel_direct_read_field_by_field(tmp_path):
    world, server = _build(tmp_path, pace=0.0)     # pace=0 ⇒ 不推进，读同一 tick 便于对账
    status, headers, body = _get(server, "/live/state")
    assert status == 200
    kernel_state = world.kernel.world.to_state()
    assert body["state"] == kernel_state, "通道读数与内核直读不一致（逐字段）"
    assert body["tick"] == world.kernel.world.tick
    assert body["state_hash"] == world.state_hash()
    assert body["event_chain_hash"] == world.event_chain_hash()
    assert body["clock"] == world.clock()
    assert body["read_only"] is True
    print(f"③ 对账: tick {body['tick']} | state_hash {body['state_hash'][:16]}… | "
          f"实体数 {len(body['state']['entities'])} | 逐字段一致")
    # 反例（自证）：篡改内核状态后，通道读数必须随之改变（证明它不是常量/缓存）
    before = body["state_hash"]
    world.kernel.world.set_component("npc-001", "needs", {"physiology": 0.123})
    _, _, after = _get(server, "/live/state")
    assert after["state_hash"] != before, "改内核状态后通道读数未变 ⇒ ③ 是恒真判据"


# ---------------------------------------------------------------------------- ⑤ 独立于观察者
def test_world_keeps_advancing_with_zero_observers(tmp_path):
    world, server = _build(tmp_path, pace=0.02)
    channel = _Channel(server)
    stop = threading.Event()
    thread = threading.Thread(target=lambda: world.advance_loop(stop_event=stop), daemon=True)
    thread.start()
    try:
        channel.open()
        channel.read_frames(1)
        channel.close()
        time.sleep(0.5)                     # 让服务端把连接注销
        before = world.tick
        observers = world.observers()
        wait = 2.0
        time.sleep(wait)
        after = world.tick
        print(f"⑤ 三读数: 断开前 tick {before} | 等待 {wait:.1f}s | 断开后 tick {after} "
              f"（增量 {after - before}）| observers = {observers}")
        assert observers == 0, f"断开所有观察者后 observers 应为 0，实测 {observers}"
        assert after > before, "无观察者时世界停止推进 ⇒ 世界被观察者驱动"
        assert after - before >= int(wait / 0.02) - 5
    finally:
        channel.close()
        stop.set()
        thread.join(timeout=10)
        server.stop()


#: ⑦ 独立性判据的参数（F6 · r3：容差**锚定 deadline / 实测窗口**，不是固定 tick 数）
PACE_S_PER_TICK = 0.02
PACE_WINDOW_S = 2.0
#: 容差 = `max(3 tick, 3% × 期望 tick)`；期望 tick 由**窗口实测墙钟 / pace** 给出。
#: 为什么必须锚定：判据原先用固定 `|Δ| ≤ 3`，而「窗口」是 `time.sleep(2.0)` 的**实际**时长——
#: CPU 争用下 sleep 会超时（如 2.2s ⇒ 期望 110 tick 而固定阈值仍按 100 算）⇒ **假红**。
#: 锚定到实测窗口后，两臂各自按自己的窗口归一化，再比**归一化速率**。
PACE_TOLERANCE = 0.03


def _measure_pace(tmp_path: Path, *, observers: int, world_cls=None) -> tuple[int, float]:
    """跑一个观察窗口，返回 `(窗口内 tick 增量, 窗口实测墙钟秒)`。"""
    import tempfile

    world_cls = world_cls or LiveWorld
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "live"
        out.mkdir(parents=True, exist_ok=True)
        kernel = WorldKernel(pack=load_pack(PACK_DIR), seed=SEED,
                             log=EventLog(out / "events.jsonl"), snapshot_every=0,
                             checkpoint_dir=None)
        sem = world_clock.derive_clock_semantics(load_pack(PACK_DIR))
        world = world_cls(kernel, sem=sem, pace_s_per_tick=PACE_S_PER_TICK, warmup=0,
                          max_observers=8)
        server = LiveServer(world, bind="127.0.0.1", port=0, allow_remote=False).start()
        stop = threading.Event()
        thread = threading.Thread(target=lambda: world.advance_loop(stop_event=stop), daemon=True)
        thread.start()
        channels = []
        try:
            for _ in range(observers):
                channel = _Channel(server)
                channel.open()
                channel.read_frames(1)
                channels.append(channel)
            assert world.observers() == observers, (
                f"测试进程自记账 {observers} 个连接，服务端报 {world.observers()}")
            time.sleep(0.5)
            before = world.tick
            window_start = time.monotonic()
            time.sleep(PACE_WINDOW_S)
            window = time.monotonic() - window_start      # **实测**窗口（判据的锚）
            delta = world.tick - before
        finally:
            for channel in channels:
                channel.close()
            stop.set()
            thread.join(timeout=10)
            server.stop()
        return delta, window


def _pace_failures(zero: tuple[int, float], two: tuple[int, float]) -> list[str]:
    """⑦ 判据本体（**正向与「去节流」注入共用** ⇒ 注入能让同一条判据变红）。"""
    failures: list[str] = []
    for label, (delta, window) in (("0 个观察者", zero), ("2 个观察者", two)):
        expected = window / PACE_S_PER_TICK
        tolerance = max(3.0, PACE_TOLERANCE * expected)
        if abs(delta - expected) > tolerance:
            failures.append(
                f"{label}: tick 增量 {delta} 与**实测窗口** {window:.4f}s 锚定的期望 "
                f"{expected:.1f} 不一致（容差 {tolerance:.1f}）⇒ 推进不再 deadline 锚定")
    zero_rate = zero[0] / zero[1]
    two_rate = two[0] / two[1]
    tolerance = max(3.0, PACE_TOLERANCE * zero_rate)
    if abs(zero_rate - two_rate) > tolerance:
        failures.append(
            f"观察者数量改变了推进节奏（{zero_rate:.2f} tick/s vs {two_rate:.2f} tick/s）"
            "⇒ 世界不独立于观察者")
    return failures


class _UnthrottledWorld(LiveWorld):
    """「**去节流**」注入：推进循环**忽略 pace**（deadline 锚定被拿掉）⇒ ⑦ 判据必须变红。"""

    def advance_loop(self, *, max_ticks: int | None = None, stop_event=None) -> dict:
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
        finally:
            self.running = False
            self.ticks_advanced += advanced
        return {"ticks": advanced, "elapsed_s": round(time.monotonic() - started, 6),
                "max_drift_ms": 0.0, "tick": self.tick, "clock": self.clock(),
                "observers": self.observers()}


def test_pace_is_identical_with_zero_and_two_observers(tmp_path):
    """⑦ 观察者独立性对照（D-M4-15⑤）：同一窗口，0 个 vs 2 个观察者 ⇒ 推进节奏相同。

    **F6（r3）**：容差锚定到**实测窗口 / pace**（不再是固定 `|Δ| ≤ 3`）——
    固定阈值在 CPU 争用下假红（`time.sleep(2.0)` 实际跑 2.2s ⇒ 期望 110 tick 而阈值按 100 算）。
    """
    zero = _measure_pace(tmp_path, observers=0)
    two = _measure_pace(tmp_path, observers=2)
    print(f"⑦ 独立性对照: 0 个观察者 ⇒ 窗口 {zero[1]:.4f}s / tick 增量 {zero[0]}"
          f"（期望 {zero[1] / PACE_S_PER_TICK:.1f}）| 2 个观察者连着 ⇒ 窗口 {two[1]:.4f}s / "
          f"tick 增量 {two[0]}（期望 {two[1] / PACE_S_PER_TICK:.1f}）")
    failures = _pace_failures(zero, two)
    assert failures == [], "；".join(failures)


def test_unthrottled_loop_turns_the_pace_criterion_red(tmp_path):
    """⑦ 负例（F6 · r3 关闭判据 2）：**去节流注入** ⇒ 同一条判据**必须变红**。

    防「修完变恒绿」：把 `advance_loop` 的 deadline 锚定拿掉（推进不再按 pace 节流），
    ⑦ 的判据本体必须报出失败。**判据本体与正向用例共用**（`_pace_failures`）⇒ 这是真注入。
    """
    zero = _measure_pace(tmp_path, observers=0, world_cls=_UnthrottledWorld)
    two = _measure_pace(tmp_path, observers=2, world_cls=_UnthrottledWorld)
    print(f"⑦ 去节流注入: 0 个观察者 ⇒ 窗口 {zero[1]:.4f}s / tick 增量 {zero[0]}"
          f"（期望 {zero[1] / PACE_S_PER_TICK:.1f}）")
    failures = _pace_failures(zero, two)
    assert failures, (
        f"去节流后 ⑦ 判据仍绿（窗口 {zero[1]:.4f}s 内推进 {zero[0]} tick）"
        "⇒ 容差被放宽成了恒绿判据")


# ---------------------------------------------------------------------------- ⑥ 服务边界
def test_service_boundary_host_cors_nosniff_and_methods(tmp_path):
    world, server = _build(tmp_path, pace=0.0)
    for path in ("/live/health", "/live/meta", "/live/state"):
        status, headers, body = _get(server, path)
        assert status == 200, f"{path} 应为 200，实测 {status}"
        assert "Access-Control-Allow-Origin" not in headers, f"{path} 设置了 ACAO（必须不设）"
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert "Authorization" not in headers
        assert body["read_only"] is True

    # 非 loopback Host ⇒ 403
    status, _, body = _get(server, "/live/state", host="evil.example.com")
    assert status == 403, f"非 loopback Host 应 403，实测 {status}"
    assert body["error"] == "E_HOST_FORBIDDEN"

    # 非 GET/HEAD ⇒ 405，且**不解析请求体**
    for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"):
        status, _, body = _get(server, "/live/state", method=method,
                               body=b'{"cmd":"step","n":9999}')
        assert status == 405, f"{method} 应 405，实测 {status}"
        assert body["error"] == "E_METHOD_NOT_ALLOWED"
        assert body["detail"] == "live channel is read-only"

    # 未知路径 ⇒ 404（结构化；不回吐异常原文 / 绝对路径）
    status, _, body = _get(server, "/live/../etc/passwd")
    assert status == 404
    assert body["error"] == "E_NOT_FOUND"
    assert "/" not in body["detail"], f"404 detail 泄漏路径：{body['detail']}"
    status, _, body = _get(server, "/live/..%2f..%2fetc%2fpasswd")
    assert status == 404 and "/" not in body["detail"]

    # 写世界被拒后，世界状态**没有**变化（经通道写世界 = 无通道）
    before = world.tick
    _get(server, "/live/state", method="POST", body=b'{"cmd":"step","n":9999}')
    assert world.tick == before, "405 之后世界竟被推进 ⇒ 通道存在写路径"


def test_observer_quota_is_enforced_with_a_plus_one_counter_example(tmp_path):
    world, server = _build(tmp_path, pace=0.0, max_observers=2)
    status, _, health = _get(server, "/live/health")
    assert status == 200 and health["max_observers"] == 2, "上限必须进 /live/health"

    opened = []
    try:
        for _ in range(2):
            channel = _Channel(server)
            channel.open()
            channel.read_frames(1)
            opened.append(channel)
        assert world.observers() == 2

        # 第 3 个（= N+1）必须被拒：503 + 结构化 JSON
        status, _, body = _get(server, "/live/stream")
        assert status == 503, f"超限应 503，实测 {status}"
        assert body["error"] == "E_OBSERVER_QUOTA"
        assert body["max_observers"] == 2
        print(f"⑥ 并发上限: max_observers=2，第 3 个连接被拒（503 {body['error']}）")
    finally:
        for channel in opened:
            channel.close()
        server.stop()


def test_secret_never_reaches_any_endpoint_or_frame(tmp_path, monkeypatch):
    """`DH_TEST_SECRET` 实测面：`/live/health` `/live/meta` `/live/state` + SSE 每一帧 + 404/405 detail。"""
    monkeypatch.setenv(SECRET_ENV, SECRET_VALUE)
    world, server = _build(tmp_path, pace=0.0)
    payloads: list[str] = []
    for path in ("/live/health", "/live/meta", "/live/state"):
        status, headers, body = _get(server, path)
        payloads.append(json.dumps(body, ensure_ascii=False))
        payloads.append(json.dumps(headers, ensure_ascii=False))
    payloads.append(json.dumps(_get(server, "/live/nope")[2], ensure_ascii=False))
    payloads.append(json.dumps(_get(server, "/live/state", method="POST", body=b"{}")[2],
                               ensure_ascii=False))

    channel = _Channel(server)
    try:
        channel.open()
        for frame in channel.read_frames(1):
            payloads.append(json.dumps(frame, ensure_ascii=False))
        for frame in channel.clocks:
            payloads.append(json.dumps(frame, ensure_ascii=False))
    finally:
        channel.close()
        server.stop()

    joined = "\n".join(payloads)
    assert payloads and any(len(item) > 2 for item in payloads), "没有采到任何响应体 ⇒ 判据零命中"
    assert SECRET_VALUE not in joined, "通道响应里出现注入的秘密值"
    # 反例（自证）：把秘密值塞进一份同样的响应体 ⇒ 检查必须命中（证明判据可达）
    assert SECRET_VALUE in joined + SECRET_VALUE


def test_live_module_has_no_env_or_filesystem_access():
    """静态：`live.py` 内零 `os.environ` / `getenv` / `open(` / `Path(` / `os.`，且带注入反例。"""
    import re

    source = (KERNEL_ROOT / "deephealing_kernel" / "live.py").read_text(encoding="utf-8")
    # **先把三引号字符串（docstring）剥掉**：判据扫的是**代码面**，不是文档里对这些词的自述
    code_only = re.sub(r'""".*?"""', "", source, flags=re.S)
    code_only = re.sub(r"'''.*?'''", "", code_only, flags=re.S)

    def hits(text: str) -> list[str]:
        patterns = (r"os\.environ", r"getenv", r"\bopen\(", r"\bPath\(", r"\bos\.")
        return [line for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#")
                and any(re.search(pattern, line) for pattern in patterns)]

    assert code_only.strip(), "剥离 docstring 后源码为空 ⇒ 扫描面无效"
    assert hits(code_only) == [], f"live.py 出现 env/文件系统访问：{hits(code_only)}"
    # 注入反例（零命中不算证据）：同一扫描器必须命中注入的违规行
    assert hits(code_only + "\nSECRET = os.environ['DH_TEST_SECRET']\n"), (
        "注入 os.environ 后扫描器未命中 ⇒ 检查空转")
    assert hits(code_only + "\nhandle = open('/etc/passwd')\n"), "注入 open() 后扫描器未命中"


def test_sse_stream_is_really_reachable_over_a_raw_socket(tmp_path):
    """通道**真的**监听：原始 socket 能连上并收到 `text/event-stream` 响应头。"""
    world, server = _build(tmp_path, pace=0.0)
    try:
        with socket.create_connection(("127.0.0.1", server.port), timeout=5) as sock:
            sock.sendall(b"GET /live/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            raw = b""
            while b"\r\n\r\n" not in raw:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                raw += chunk
        assert b"200" in raw.split(b"\r\n", 1)[0], raw[:200]
        assert b"application/json" in raw
        print(f"⑥ 真监听: 原始 socket 连上 127.0.0.1:{server.port} 并收到 HTTP 200 响应头")
    finally:
        server.stop()


def test_resume_semantics_and_the_event_log_boundary(tmp_path):
    """⑦ 停止 / 恢复 + **恢复语义的两条边界**（M4 新增，fail-closed + 根因隔离）。

    边界 A（**日志**）：恢复是「同 seed + 同 pack + 快进到同一 tick」的确定性重放 ⇒ 复用**非空**
      事件日志会让 `EventLog` 追加第二个 `world.init` 并让 seq 链断裂 ⇒ 必须结构化拒绝
      （`E_RESUME_LOG_EXISTS`，exit 1）。

    边界 B（**链尾**）：同 tick 的 `state_hash` 逐位相同（状态不丢）；但 `event_chain_hash` 只有在
      **`--ticks`（= `world.init.payload.plan_ticks`）也相同**时才逐位相同。本实现的 `live` 里
      `--ticks N` 有两层含义（`cli.py`：`max_ticks` + `WorldKernel(plan_ticks=N)`）：
      ① 声明 `plan_ticks`（写在**首条** `world.init` 里）；② 锚定快进之后**再推进 N tick**。
      故「恢复 + `--ticks 0`」⇒ 同一 tick 的 `state_hash` 逐位相同、而链尾**必然不同**
      （`plan_ticks` 20 → 0 改掉了首条事件）⇒ 这正是设计写明的「恢复后是新链」边界。
      **根因由本用例逐字段指认**（`world.init.payload` 的差异字段集合必须**恰好**等于 `{plan_ticks}`），
      并用「同 `--ticks` 的两次独立运行链尾逐位相同」做**同输入同链**的确定性对照。

    反例：seed / pack 不匹配 ⇒ `E_RESUME_STATE_MISMATCH`（不得用「同 tick 同哈希」当错觉证据）。
    """
    import json
    import os
    import subprocess

    pack = str(PACK_DIR)
    out = tmp_path / "live"
    out.mkdir(parents=True, exist_ok=True)

    def run_live(*extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "deephealing_kernel", "live", "--pack", pack,
             "--seed", str(SEED), "--out", str(out), "--pace", "0.001",
             "--snapshot-every", "0", "--port", "0", *extra],
            capture_output=True, text=True, cwd=str(KERNEL_ROOT),
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))

    def first_world_init(path):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if record.get("type") == "world.init":
                    return record
        raise AssertionError(f"no world.init in {path}")

    first = run_live("--ticks", "20", "--no-warmup")
    assert first.returncode == 0, first.stdout + first.stderr
    sealed_path = out / "live_state.json"
    sealed = json.loads(sealed_path.read_text(encoding="utf-8"))
    assert sealed["tick"] == 20 and sealed["running"] is False
    assert sealed["pack_id"] == "xingfu-xiaoqu" and sealed["seed"] == SEED
    assert sealed["state_hash"] and sealed["event_chain_hash"]
    frozen = out / "sealed-a.json"          # 冻结封存读数（后续 run 会覆盖 live_state.json）
    frozen.write_text(json.dumps(sealed, sort_keys=True) + "\n", encoding="utf-8")

    # 边界 A：复用非空日志 ⇒ 结构化拒绝
    reuse = run_live("--ticks", "20", "--no-warmup", "--resume-state", str(frozen))
    assert reuse.returncode == 1, reuse.stdout + reuse.stderr
    assert "E_RESUME_LOG_EXISTS" in reuse.stdout + reuse.stderr

    # 确定性对照（同输入同链）：同 `--ticks` 的两次**独立**运行 ⇒ 链尾逐位相同
    twin = run_live("--ticks", "20", "--no-warmup", "--events", str(out / "twin.jsonl"))
    twin_state = json.loads((out / "twin.jsonl").parent.joinpath("live_state.json").read_text(encoding="utf-8"))
    assert twin.returncode == 0, twin.stdout + twin.stderr
    assert twin_state["event_chain_hash"] == sealed["event_chain_hash"], (
        "同输入（同 seed/pack/--ticks）的两次独立运行必须给出同一条链")

    # 边界 B-1：恢复（--ticks 0）⇒ 同 tick、state 逐位相同，链尾**不同**（plan_ticks 改了首条事件）
    same = run_live("--ticks", "0", "--no-warmup", "--resume-state", str(frozen),
                    "--events", str(out / "resume-same.jsonl"))
    assert same.returncode == 0, same.stdout + same.stderr
    same_state = json.loads(sealed_path.read_text(encoding="utf-8"))
    print(f"⑦ B-1 恢复(--ticks 0): 封存 tick {sealed['tick']} / state {sealed['state_hash'][:16]}… / "
          f"链尾 {sealed['event_chain_hash'][:16]}… ⇒ 恢复后 tick {same_state['tick']} / "
          f"state {same_state['state_hash'][:16]}… / 链尾 {same_state['event_chain_hash'][:16]}…")
    assert same_state["tick"] == sealed["tick"], "恢复的 tick 由封存值决定"
    assert same_state["state_hash"] == sealed["state_hash"], (
        f"同 tick 的 state_hash 必须逐位相同：{same_state['state_hash']} != {sealed['state_hash']}")
    assert same_state["event_chain_hash"] != sealed["event_chain_hash"], (
        "恢复是**新链**（设计写明的边界）：plan_ticks 写在首条 world.init 里 ⇒ 它一变链就变")

    # 边界 B-2：把「链尾不同」**逐字段**归因 —— 差异字段必须恰好是 {plan_ticks}
    init_original = first_world_init(out / "events.jsonl")["payload"]
    init_resumed = first_world_init(out / "resume-same.jsonl")["payload"]
    diff = {key: (init_original.get(key), init_resumed.get(key))
            for key in sorted(set(init_original) | set(init_resumed))
            if init_original.get(key) != init_resumed.get(key)}
    print(f"⑦ B-2 归因: world.init.payload 差异字段 = {json.dumps(diff, sort_keys=True)}")
    assert set(diff) == {"plan_ticks"}, f"链尾差异必须**只**由 plan_ticks 解释，实测差异字段={sorted(diff)}"

    # ④ 反例：seed 不匹配 ⇒ 结构化拒绝
    mismatched = tmp_path / "live-mismatch"
    mismatched.mkdir()
    (mismatched / "live_state.json").write_text(json.dumps(dict(sealed, seed=SEED + 1)) + "\n",
                                                encoding="utf-8")
    bad = subprocess.run(
        [sys.executable, "-m", "deephealing_kernel", "live", "--pack", pack, "--seed", str(SEED),
         "--out", str(mismatched), "--pace", "0.001", "--port", "0", "--ticks", "0",
         "--no-warmup", "--resume-state", str(mismatched / "live_state.json"),
         "--events", str(mismatched / "e.jsonl")],
        capture_output=True, text=True, cwd=str(KERNEL_ROOT),
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert "E_RESUME_STATE_MISMATCH" in bad.stdout + bad.stderr
    assert "seed" in (bad.stdout + bad.stderr)


# ============================================================================ F5′ / F7（r3）
def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _probe_ws_port(tmp_path: Path, *, ws_port: int, probe_port: int, ticks: int,
                   label: str) -> dict:
    """起 `run --ws-port <ws_port>`，**运行期间**用阻塞 `connect` 采样 `probe_port` 的可达性。

    探针写法（硬性 · architect 裁决 §6.3）：用阻塞 `socket.connect`
    （`socket.create_connection`），**不用** `connect_ex`（带超时时它返回 `EINPROGRESS` 而非 0
    ⇒ 假命中）。命中判据 = connect 成功 **且** 读到合法 HTTP 状态行。
    """
    import os
    import subprocess

    out = tmp_path / label
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "deephealing_kernel", "run", "--pack", str(PACK_DIR),
         "--seed", str(SEED), "--ticks", str(ticks), "--ws-port", str(ws_port),
         "--events", str(out / "events.jsonl")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(KERNEL_ROOT),
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    hits = 0
    refused = 0
    first_line = None
    while proc.poll() is None:
        try:
            with socket.create_connection(("127.0.0.1", probe_port), timeout=0.3) as sock:
                sock.sendall(b"GET /live/health HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                             b"Connection: close\r\n\r\n")
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
            first_line = first_line or line
    stdout, stderr = proc.communicate()
    self_report = None
    for line in stdout.splitlines():
        if line.startswith("{"):
            try:
                self_report = json.loads(line).get("live_channel")
            except ValueError:
                self_report = None
    return {"exit": proc.returncode, "hits": hits, "refused": refused,
            "first_line": first_line, "self_report": self_report, "stderr": stderr}


def test_run_ws_port_is_externally_reachable_during_the_tick_loop(tmp_path):
    """**F5′（r3）外部可连判据**：`run --ws-port <n>` **运行期间**外部 socket 必须真的连上。

    含**负向对照**（`--ws-port 0` ⇒ 同一条判据必须红），防「恒绿判据」。
    判据以**真子进程**为准：内存打点只能证明「bind 成功过」，不能作为可观测性判据。
    """
    port = _free_port()
    positive = _probe_ws_port(tmp_path, ws_port=port, probe_port=port, ticks=3000,
                              label="wsport-positive")
    print(f"F5′ 正向: 外部连入 {positive['hits']} 次 / refused {positive['refused']} 次 | "
          f"响应首行 {positive['first_line']} | run 自报 live_channel={positive['self_report']}")
    assert positive["exit"] == 0, positive["stderr"]
    assert positive["hits"] >= 1, (
        f"`run --ws-port {port}` 运行期间外部一次都没连上（refused {positive['refused']}）"
        "⇒ 声明了一个外部无法观测的监听窗口")
    assert (positive["first_line"] or "").startswith("HTTP/"), positive["first_line"]

    control_port = _free_port()
    control = _probe_ws_port(tmp_path, ws_port=0, probe_port=control_port, ticks=3000,
                             label="wsport-control")
    print(f"F5′ 负向对照（--ws-port 0）: 外部连入 {control['hits']} 次 / "
          f"refused {control['refused']} 次")
    assert control["hits"] == 0, (
        f"负向对照竟然连入 {control['hits']} 次 ⇒ 该判据是恒绿判据（没监听也算过）")


def _hammer_http(port: int, stop: threading.Event) -> int:
    """无间隔 HTTP 观察者（每次一条新连接），返回成功次数。"""
    served = 0
    while not stop.is_set():
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5) as sock:
                sock.sendall(b"GET /live/state HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                             b"Connection: close\r\n\r\n")
                raw = b""
                while b"\r\n" not in raw:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    raw += chunk
                served += 1
        except (OSError, TimeoutError):
            pass
    return served


def test_plain_http_path_rejects_beyond_the_connection_limit(tmp_path):
    """**F7（r3）**：普通 HTTP 观察路径（`/live/state` 等）必须有**连接级并发上限**。

    超限 ⇒ 结构化 `503 E_HTTP_QUOTA` 且立即关连接（**不是**静默排队、**不是** fd 耗尽）。
    含负向对照：上限**以内**不得误拒（判据不得恒红）。
    """
    world, server = _build(tmp_path, pace=0.0, max_observers=2)
    status, _, health = _get(server, "/live/health")
    assert status == 200
    assert health["max_http_connections"] == 8, health["max_http_connections"]   # max(4, 4×2)
    assert health["max_http_inflight"] == 4, health["max_http_inflight"]         # max(2, 2×2)

    def open_one() -> str:
        sock = socket.create_connection(("127.0.0.1", server.port), timeout=3)
        sock.settimeout(3)
        sock.sendall(b"GET /live/state HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")   # keep-alive
        raw = b""
        try:
            while b"\r\n" not in raw:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                raw += chunk
        except (OSError, TimeoutError):
            pass
        held.append(sock)
        return raw.split(b"\r\n", 1)[0].decode("utf-8", "replace") if raw else ""

    held: list = []
    try:
        # 负向对照：上限以内（4 < 8）⇒ 不得误拒
        inside = [open_one() for _ in range(4)]
        assert all(" 200" in line for line in inside), f"上限内被误拒：{inside}"

        # 超限：继续开到 24 条 ⇒ 超出部分必须 503
        lines = [open_one() for _ in range(20)]
        rejected = sum(1 for line in lines if " 503" in line)
        print(f"F7 连接级上限: max_http_connections={health['max_http_connections']}，"
              f"上限内 4 条全 200；再开 20 条 ⇒ {rejected} 条 503")
        assert rejected >= 1, (
            f"开到 {len(held)} 条连接仍无一条 503 ⇒ 普通 HTTP 路径没有连接级上限（fd 会被打满）")
        # 先放掉持有的连接（否则连 `/live/health` 自己都会被连接级上限拒掉——这本身是上限生效的旁证）
        for sock in held:
            sock.close()
        held.clear()
        time.sleep(0.3)                       # 让服务端 `finish()` 把计数递减回去
        _, _, after = _get(server, "/live/health")
        assert after.get("error") is None, f"释放连接后 /live/health 仍被拒：{after}"
        assert after["connection_rejections"] >= 1, after
        assert after["http_connections_peak"] <= after["max_http_connections"] + 8, (
            f"连接高水位 {after['http_connections_peak']} 远超上限 "
            f"{after['max_http_connections']} ⇒ 上限没有真正约束并发")
    finally:
        for sock in held:
            sock.close()
        server.stop()


def test_observer_load_keeps_tick_advance_and_wall_clock_bounded(tmp_path):
    """**F7（r3）判据 3**：观察者负载下 **tick 推进与墙钟语义不得改变（或有界）**。

    否则计时类判据（`AC-M4-9` pace/clock）会多一个污染源。
    """
    def run_loaded(hammers: int) -> dict:
        out = tmp_path / f"loaded{hammers}"
        out.mkdir(parents=True, exist_ok=True)
        kernel = WorldKernel(pack=load_pack(PACK_DIR), seed=SEED,
                             log=EventLog(out / "events.jsonl"), snapshot_every=0,
                             checkpoint_dir=None)
        sem = world_clock.derive_clock_semantics(load_pack(PACK_DIR))
        world = LiveWorld(kernel, sem=sem, pace_s_per_tick=0.005, warmup=0, max_observers=8)
        server = LiveServer(world, bind="127.0.0.1", port=0, allow_remote=False).start()
        stop_hammers = threading.Event()
        threads = [threading.Thread(target=_hammer_http, args=(server.port, stop_hammers),
                                    daemon=True) for _ in range(hammers)]
        for thread in threads:
            thread.start()
        try:
            loop = world.advance_loop(max_ticks=200)
        finally:
            stop_hammers.set()
            for thread in threads:
                thread.join(timeout=5)
            loop["http_inflight_peak"] = server.http_inflight_peak
            loop["max_http_inflight"] = server.max_http_inflight
            server.stop()
        return loop

    baseline = run_loaded(0)
    loaded = run_loaded(4)
    bound = max(5.0, 10.0 * baseline["elapsed_s"])
    print(f"F7 负载有界: 0 观察者 ⇒ ticks {baseline['ticks']} / {baseline['elapsed_s']}s | "
          f"4 无间隔观察者 ⇒ ticks {loaded['ticks']} / {loaded['elapsed_s']}s（界 {bound:.2f}s）| "
          f"在途峰值 {loaded['http_inflight_peak']} ≤ {loaded['max_http_inflight']}")
    assert baseline["ticks"] == 200, baseline["ticks"]
    assert loaded["ticks"] == 200, f"观察者负载改变了 tick 推进语义（{loaded['ticks']} != 200）"
    assert loaded["elapsed_s"] <= bound, (
        f"观察者负载把循环墙钟从 {baseline['elapsed_s']}s 拖到 {loaded['elapsed_s']}s"
        f"（界 {bound:.2f}s）⇒ 墙钟语义被改变且无界")
    assert loaded["http_inflight_peak"] <= loaded["max_http_inflight"], (
        f"在途请求峰值 {loaded['http_inflight_peak']} 超过上限 {loaded['max_http_inflight']}")


def _run_cli_live_in_process(out_dir: Path, capsys) -> tuple[int, str, str]:
    """进程内跑 `cli.main(["live", …])`（便于 spy `LiveServer.stop`）；返回 (rc, out, err)。"""
    import signal

    from deephealing_kernel import cli

    saved = {name: signal.getsignal(getattr(signal, name)) for name in ("SIGINT", "SIGTERM")}
    try:
        rc = cli.main(["live", "--pack", str(PACK_DIR), "--seed", str(SEED), "--out", str(out_dir),
                       "--pace", "0.001", "--ticks", "5", "--snapshot-every", "0",
                       "--no-warmup", "--port", "0"])
    finally:
        for name, handler in saved.items():
            signal.signal(getattr(signal, name), handler)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_live_state_sealing_failure_is_structured_and_still_stops_the_server(tmp_path, monkeypatch,
                                                                            capsys):
    """**F7（r3）注入**：让 `live_state.json` 的写操作抛 `OSError` ⇒ 收尾路径必须 fail-closed。

    注入方式：把 `live_state.json` **建成目录** ⇒ `write_text()` 抛 `IsADirectoryError`
    （`OSError` 子类；与 fd 耗尽的 `Errno 24` 同类但**可确定性复现**）。
    四条都要：① 不得 SIGABRT（无 `_enter_buffered_busy`）② `server.stop()` **仍执行**
    ③ stderr 有结构化错误 ④ 退出码非 0。
    """
    from deephealing_kernel import cli  # noqa: F401 — 确保 cli 已 import（spy 目标）

    out = tmp_path / "inject"
    out.mkdir(parents=True, exist_ok=True)
    (out / "live_state.json").mkdir()             # **注入点**

    stops: list = []
    real_stop = LiveServer.stop

    def spy(self):                                # noqa: ANN001
        stops.append(True)
        return real_stop(self)

    monkeypatch.setattr(LiveServer, "stop", spy)
    rc, stdout, stderr = _run_cli_live_in_process(out, capsys)

    print(f"F7 封存注入: exit={rc} | server.stop() 调用 {len(stops)} 次 | "
          f"结构化错误={'E_LIVE_STATE_SEAL_FAILED' in stderr} | Traceback={'Traceback' in stderr}")
    assert rc != 0, f"封存失败没有转成非 0 退出（rc={rc}）"
    assert stops, "封存失败路径上 **没有** 调用 server.stop() ⇒ daemon 线程会活到 finalize"
    assert "E_LIVE_STATE_SEAL_FAILED" in stderr, stderr
    assert "Traceback" not in stderr, f"异常穿出了 finally（裸 Traceback）：{stderr}"
    assert "_enter_buffered_busy" not in stderr, stderr
    payload = json.loads([line for line in stdout.splitlines() if line.startswith("{")][-1])
    assert payload["error"] == "E_LIVE_STATE_SEAL_FAILED"
    assert payload["sealed"] is False
    assert payload["server_stopped"] is True, payload


def test_clean_live_run_does_not_report_a_sealing_error(tmp_path, capsys):
    """**F7（r3）负向对照**：不注入时该错误路径**不得**误报（判据不得恒红）。"""
    out = tmp_path / "clean"
    out.mkdir(parents=True, exist_ok=True)
    rc, stdout, stderr = _run_cli_live_in_process(out, capsys)
    print(f"F7 负向对照（不注入）: exit={rc} | 结构化错误="
          f"{'E_LIVE_STATE_SEAL_FAILED' in stderr} | live_state.json 存在="
          f"{(out / 'live_state.json').is_file()}")
    assert rc == 0, stdout + stderr
    assert "E_LIVE_STATE_SEAL_FAILED" not in stderr, stderr
    sealed = json.loads((out / "live_state.json").read_text(encoding="utf-8"))
    assert sealed["running"] is False and sealed["tick"] == 5


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-s"]))
