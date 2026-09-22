"""事件日志与哈希链（V0 骨架，契约冻结）。

格式（events.schema.json）：JSONL，每行
    {seq, tick, type, actor, payload, prev_hash, hash}
    hash = sha256(prev_hash || canonical_json({seq,tick,type,actor,payload}))
    genesis 的 prev_hash = 64 个 0

不变量：
  - seq 全局单调、无空洞；同一 tick 内按阶段顺序追加；
  - 只追加，不回改历史（回放 = 新内核实例 + 同一日志）；
  - 追加前必须做 secrets 脱敏（Authorization 等）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

GENESIS_HASH = "0" * 64
EVENT_TYPES = (
    "world.init",
    "intent.applied",
    "intent.rejected",
    "npc.action",
    "capability.invoked",
    "capability.fallback",
    "task.state_changed",
    "memory.written",
    "snapshot.taken",
)


@dataclass(frozen=True, slots=True)
class Event:
    seq: int
    tick: int
    type: str
    actor: str
    payload: dict
    prev_hash: str
    hash: str


class EventLog:
    """JSONL 事件日志（append-only）。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._seq = 0
        self._last_hash = GENESIS_HASH

    @property
    def last_hash(self) -> str:
        """event_chain_hash 的来源。"""
        return self._last_hash

    def append(self, tick: int, type: str, actor: str, payload: dict[str, Any]) -> Event:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'event-chain'")

    def read_all(self) -> Iterator[Event]:
        """读取并逐条校验 hash 链（断链即抛错）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'replay'")


def redact(payload: dict[str, Any], redact_fields: list[str]) -> dict[str, Any]:
    """按 capability.safety.redact_fields 脱敏（Authorization 等一律 ***REDACTED***）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'event-chain'")
