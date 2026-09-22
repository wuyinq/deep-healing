"""内核事件总线（V0-M1 实现，契约冻结）。

L7 观测层与 L2 传输层**只订阅**，不得写内核状态。订阅者回调必须是非阻塞的；
回调抛异常不得中断 tick（记 metric 后丢弃该订阅者本次投递）。

M1 实现口径：
  - 投递严格按**订阅顺序**（list，不是 set/dict 迭代）；
  - 订阅者异常被隔离：记 `metrics["subscriber_errors"]` 后继续投递给下一个订阅者；
  - 未知 topic 一律 fail-closed（`ValueError`），不静默吞掉拼写错误。
"""

from __future__ import annotations

from typing import Any, Callable

TOPICS = ("events", "snapshots", "ticks", "metrics")


class KernelBus:
    """只读发布/订阅（订阅者不能回写世界）。"""

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[dict[str, Any]], None]]] = {t: [] for t in TOPICS}
        self.metrics: dict[str, int] = {"published": 0, "delivered": 0, "subscriber_errors": 0}

    def subscribe(self, topic: str, fn: Callable[[dict[str, Any]], None]) -> None:
        if topic not in self._subs:
            raise ValueError(f"unknown topic: {topic!r} (known: {', '.join(TOPICS)})")
        self._subs[topic].append(fn)

    def publish(self, topic: str, message: dict[str, Any]) -> None:
        """按订阅顺序投递；订阅者异常被隔离，不影响 tick。"""
        if topic not in self._subs:
            raise ValueError(f"unknown topic: {topic!r} (known: {', '.join(TOPICS)})")
        self.metrics["published"] += 1
        for fn in list(self._subs[topic]):  # 显式按订阅顺序；投递期间订阅变更不影响本次
            try:
                fn(message)
            except Exception:  # noqa: BLE001 —— 契约要求：异常隔离，不得中断 tick
                self.metrics["subscriber_errors"] += 1
                continue
            self.metrics["delivered"] += 1

    def unsubscribe_all(self) -> None:
        for topic in TOPICS:
            self._subs[topic] = []
