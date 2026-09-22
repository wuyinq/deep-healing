"""内核事件总线（V0 骨架，契约冻结）。

L7 观测层与 L2 传输层**只订阅**，不得写内核状态。订阅者回调必须是非阻塞的；
回调抛异常不得中断 tick（记 metric 后丢弃该订阅者本次投递）。
"""

from __future__ import annotations

from typing import Any, Callable

TOPICS = ("events", "snapshots", "ticks", "metrics")


class KernelBus:
    """只读发布/订阅（订阅者不能回写世界）。"""

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[dict[str, Any]], None]]] = {t: [] for t in TOPICS}

    def subscribe(self, topic: str, fn: Callable[[dict[str, Any]], None]) -> None:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'bus'")

    def publish(self, topic: str, message: dict[str, Any]) -> None:
        """按订阅顺序投递；订阅者异常被隔离，不影响 tick。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'bus'")

    def unsubscribe_all(self) -> None:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'bus'")
