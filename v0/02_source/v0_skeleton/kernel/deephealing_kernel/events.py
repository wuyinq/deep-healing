"""事件日志与哈希链（V0-M1 实现，契约冻结）。

格式（events.schema.json）：JSONL，每行
    {seq, tick, type, actor, payload, prev_hash, hash}
    hash = sha256(prev_hash || canonical_json({seq,tick,type,actor,payload}))
    genesis 的 prev_hash = 64 个 0

不变量：
  - seq 全局单调、无空洞；同一 tick 内按阶段顺序追加；
  - 只追加，不回改历史（回放 = 新内核实例 + 同一日志）；
  - 追加前必须做 secrets 脱敏（Authorization 等）。

M1 实现口径：
  - `redact(payload, redact_fields)` 以 **`redact_fields`（点分路径 + glob）为主判据**，
    键名匹配（authorization / api_key / token，大小写不敏感）只作**补充**（superset）；
    `Authorization` 类键 → `Bearer ***REDACTED***`，其余 → `***REDACTED***`（预审 M2）。
  - payload 在**脱敏后**做一次 canonical_json 往返（`json.loads(canonical_json(x))`），
    使「落盘文本 → 读回 → 复算 hash」逐位一致（浮点 6 位规则在写入前已生效）。
  - `read_all()` 逐条校验：JSON 可解析 / seq 从 0 连续 / prev_hash 链接 / hash 可复算；
    任一项不符即抛 `EventChainError`（fail-closed，携带**首个分歧 tick**）。
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .snapshot import canonical_json, chained_hash, GENESIS_HASH

EVENT_TYPES = (
    "world.init",
    "intent.applied",
    "intent.rejected",
    "npc.action",
    "npc.decision",
    "capability.invoked",
    "capability.fallback",
    "task.state_changed",
    "memory.written",
    "snapshot.taken",
)

# capability.safety.redact_fields 的契约实例（`cassette.schema.json` / capability 清单口径）
DEFAULT_REDACT_FIELDS = ("headers.Authorization", "env.*_API_KEY")
# 补充判据（superset）的**键名等价族**（修复轮 B2 / 预审 R8）：按 `_` / `-` / 空白切词后**整体**等价，
# **不做子串包含** —— 否则 `token_budget` / `authorization_level` / `api_keys_count` / `token-holder`
# 这类**非密钥**字段会被误脱敏（它们都是 world.schema.json 允许的合法键名形态：实体 id pattern
# `^[a-z][a-z0-9_.-]{1,63}$` 允许 `token-holder`）。`redact_fields` 仍是**主**判据。
SUPPLEMENTARY_KEY_FAMILY = frozenset({"authorization", "apikey", "token", "accesstoken", "secret"})
_KEY_WORD_SPLIT_RE = re.compile(r"[_\-\s]+")
AUTHORIZATION_VALUE = "Bearer ***REDACTED***"
REDACTED_VALUE = "***REDACTED***"


class EventChainError(Exception):
    """哈希链校验失败（fail-closed）。携带首个分歧 tick。"""

    code = "E_EVENT_CHAIN"

    def __init__(self, message: str, tick: int | None = None) -> None:
        super().__init__(message)
        self.tick = tick


@dataclass(frozen=True, slots=True)
class Event:
    seq: int
    tick: int
    type: str
    actor: str
    payload: dict
    prev_hash: str
    hash: str

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "tick": self.tick,
            "type": self.type,
            "actor": self.actor,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }

    def body(self) -> dict:
        """进入链公式的 5 字段（**不含** prev_hash / hash）。"""
        return {"seq": self.seq, "tick": self.tick, "type": self.type, "actor": self.actor,
                "payload": self.payload}


def _pattern_parts(pattern: str) -> list[str]:
    parts = [part for part in str(pattern).split(".") if part]
    if parts and parts[0] == "payload":  # `payload.raw_headers.Authorization` 形态
        parts = parts[1:]
    return parts


def _path_matches(path_parts: list[str], pattern_parts: list[str]) -> bool:
    if len(path_parts) != len(pattern_parts):
        return False
    return all(
        fnmatch.fnmatchcase(part.lower(), pattern.lower()) for part, pattern in zip(path_parts, pattern_parts)
    )


def _is_authorization_key(key: str) -> bool:
    return key.lower() == "authorization"


def _normalized_key(key: str) -> str:
    """键名归一化：小写 + 按 `_` / `-` / 空白切词后**拼接**（用于整词等价族匹配，不做子串包含）。"""
    return "".join(_KEY_WORD_SPLIT_RE.split(key.lower()))


def _should_redact(key: str, path_parts: list[str], patterns: list[list[str]]) -> bool:
    if any(_path_matches(path_parts, pattern) for pattern in patterns):
        return True
    return _normalized_key(key) in SUPPLEMENTARY_KEY_FAMILY


def _redact_value(key: str) -> str:
    return AUTHORIZATION_VALUE if _is_authorization_key(key) else REDACTED_VALUE


def _walk(value: Any, path_parts: list[str], patterns: list[list[str]]) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key in value:
            child_path = path_parts + [str(key)]
            if _should_redact(str(key), child_path, patterns):
                result[key] = _redact_value(str(key))
            else:
                result[key] = _walk(value[key], child_path, patterns)
        return result
    if isinstance(value, list):
        return [_walk(item, path_parts, patterns) for item in value]
    return value


def redact(payload: dict[str, Any], redact_fields: list[str]) -> dict[str, Any]:
    """按 capability.safety.redact_fields 脱敏（Authorization 等一律 ***REDACTED***）。

    `redact_fields` 是**主判据**（点分路径 + glob，如 `env.*_API_KEY`）；键名匹配只作补充。
    返回**新**对象，绝不就地修改入参。
    """
    patterns = [_pattern_parts(pattern) for pattern in (redact_fields or [])]
    patterns = [pattern for pattern in patterns if pattern]
    return _walk(payload, [], patterns)


class EventLog:
    """JSONL 事件日志（append-only）。"""

    def __init__(self, path: Path, *, redact_fields: list[str] | None = None) -> None:
        self._path = Path(path)
        self._seq = 0
        self._last_hash = GENESIS_HASH
        self._redact_fields = list(DEFAULT_REDACT_FIELDS if redact_fields is None else redact_fields)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def last_hash(self) -> str:
        """event_chain_hash 的来源。"""
        return self._last_hash

    def append(self, tick: int, type: str, actor: str, payload: dict[str, Any]) -> Event:
        if type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {type!r} (new types require an ADR)")
        safe_payload = json.loads(canonical_json(redact(payload, self._redact_fields)))
        event = Event(
            seq=self._seq,
            tick=int(tick),
            type=type,
            actor=actor,
            payload=safe_payload,
            prev_hash=self._last_hash,
            hash=chained_hash(self._last_hash, {
                "seq": self._seq, "tick": int(tick), "type": type, "actor": actor, "payload": safe_payload,
            }),
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        self._seq += 1
        self._last_hash = event.hash
        return event

    def read_all(self) -> Iterator[Event]:
        """读取并逐条校验 hash 链（断链即抛错）。"""
        expected_seq = 0
        prev_hash = GENESIS_HASH
        if not self._path.is_file():
            raise EventChainError(f"event log not found: {self._path}", tick=None)
        with self._path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    doc = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise EventChainError(f"line {lineno}: unparsable JSON: {exc}", tick=None) from exc
                tick = doc.get("tick")
                if doc.get("seq") != expected_seq:
                    raise EventChainError(
                        f"line {lineno}: seq gap (expected {expected_seq}, got {doc.get('seq')})", tick=tick
                    )
                if doc.get("prev_hash") != prev_hash:
                    raise EventChainError(
                        f"line {lineno}: prev_hash mismatch at tick {tick}", tick=tick
                    )
                body = {key: doc[key] for key in ("seq", "tick", "type", "actor", "payload")}
                recomputed = chained_hash(prev_hash, body)
                if recomputed != doc.get("hash"):
                    raise EventChainError(
                        f"line {lineno}: hash mismatch at tick {tick} "
                        f"(recorded {doc.get('hash')}, recomputed {recomputed})",
                        tick=tick,
                    )
                event = Event(seq=doc["seq"], tick=doc["tick"], type=doc["type"], actor=doc["actor"],
                              payload=doc["payload"], prev_hash=doc["prev_hash"], hash=doc["hash"])
                expected_seq += 1
                prev_hash = event.hash
                yield event


def check_ech_invariants(events: list[Event], checkpoint_dir: Path | None = None) -> list[str]:
    """逐条校验 INVARIANT-ECH-1/2/3（snapshot.schema.json 的 `x-ac2-criterion.ech_invariants`）。

      ECH-2：`payload.event_chain_hash == event.prev_hash`（**事件 payload** 语义 = 该事件之前的链尾）
      ECH-3：`hash_object(payload.rng_digests) == payload.rng_state_digest`
      ECH-1：`checkpoint.event_chain_hash == hash(snapshot.taken 事件, tick == checkpoint.tick)`
             （**检查点字段**语义 = 截至该 tick 的日志末条，含快照事件自身）
    """
    problems: list[str] = []
    snapshot_events: dict[int, Event] = {}
    for event in events:
        if event.type != "snapshot.taken":
            continue
        snapshot_events[event.tick] = event
        payload = event.payload
        if payload.get("event_chain_hash") != event.prev_hash:
            problems.append(
                f"INVARIANT-ECH-2 violated at tick={event.tick}: payload.event_chain_hash="
                f"{payload.get('event_chain_hash')} != prev_hash={event.prev_hash}"
            )
        if "rng_digests" not in payload or "rng_state_digest" not in payload:
            problems.append(f"INVARIANT-ECH-3 unverifiable at tick={event.tick}: rng_digests/rng_state_digest missing")
        else:
            from .snapshot import hash_object  # 局部导入：避免模块级循环
            recomputed = hash_object(payload["rng_digests"])
            if recomputed != payload["rng_state_digest"]:
                problems.append(
                    f"INVARIANT-ECH-3 violated at tick={event.tick}: hash_object(rng_digests)="
                    f"{recomputed} != rng_state_digest={payload['rng_state_digest']}"
                )

    if checkpoint_dir is not None:
        from .snapshot import _load_checkpoint_dir  # 局部导入
        by_tick, errors = _load_checkpoint_dir(Path(checkpoint_dir))
        problems.extend(errors)
        for tick in sorted(by_tick):
            event = snapshot_events.get(tick)
            if event is None:
                problems.append(f"INVARIANT-ECH-1 unverifiable at tick={tick}: no snapshot.taken event in log")
                continue
            recorded = by_tick[tick].get("event_chain_hash")
            if recorded != event.hash:
                problems.append(
                    f"INVARIANT-ECH-1 violated at tick={tick}: checkpoint.event_chain_hash={recorded} "
                    f"!= hash(snapshot.taken event)={event.hash}"
                )
    return problems
