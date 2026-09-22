"""确定性随机源：单一 seed + 子系统分流（V0-M1 实现，契约冻结）。

规则（01 设计 §4.3）：
  - 全进程唯一 `WorldRng(seed)`；tick 内禁止重新播种；
  - 子系统取流用 `rng.stream("<subsystem>")`，stream 名经哈希派生；**既有 stream 的序列不被扰动**
    （这是「加一个 NPC / 加一个街区不改 **`state_hash`**」的前提）；
  - 禁用全局 random 模块与任何系统熵（time/os.urandom）。

**措辞收窄（修复轮 B5 / 预审 R4）**：上一条**只**保证「既有 stream 的序列与摘要逐位不变」。
世界级 `rng_state_digest` 覆盖**全部已创建 stream**（`digests()` 遍历 `self._streams`，且 stream 是
**惰性创建**的）⇒ 新增子系统会**改变** `rng_state_digest`（`state_hash` 不变）。
因此「加一个街区不改历史哈希」**只**对 `state_hash` 成立：跨版本的**检查点/日志比对**
（含 `verify` 的 `rng_state_digest` 逐点比对）在新增子系统后会失配 —— M2/W4/W5 引入新子系统时
M1 的历史产物不能再当对照基线。要消除该面需把覆盖范围钉死为**显式清单**（属契约变更，需 ADR）。

M1 实现口径（设计 §4.5，逐字对齐）：
  - `stream_key = sha256(f"{seed}:{name}".encode())`；
  - `next_u64()` = `int.from_bytes(sha256(key + counter.to_bytes(8,'big'))[:8], 'big')`，随后 `counter += 1`；
  - `state_digest()` = `sha256(canonical_json({name: stream.digest()} 按 name 升序))`
    —— canonical_json / hash_object 复用 `tools/canonical_json.py`（经 snapshot 转发，单一来源）。
"""

from __future__ import annotations

import hashlib

from .snapshot import hash_object


def stream_key(seed: int, name: str) -> bytes:
    """stream 名经哈希派生（每个子系统一条独立流，互不扰动）。"""
    return hashlib.sha256(f"{seed}:{name}".encode("utf-8")).digest()


class StreamRng:
    """单个子系统的确定性随机流（计数器驱动，无隐式状态共享）。"""

    def __init__(self, key: bytes, counter: int = 0) -> None:
        self._key = key
        self._counter = counter

    def digest(self) -> str:
        """该流的确定性摘要（进 rng_state_digest，用于证明两次回放随机轨迹一致）。"""
        return hashlib.sha256(self._key + self._counter.to_bytes(8, "big")).hexdigest()

    @property
    def counter(self) -> int:
        return self._counter

    def next_u64(self) -> int:
        """推进计数器并返回一个确定性 64 位无符号整数。"""
        material = self._key + self._counter.to_bytes(8, "big")
        self._counter += 1
        return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")

    def uniform(self, low: float, high: float) -> float:
        span = high - low
        return low + (self.next_u64() / float(1 << 64)) * span

    def choice(self, items: list) -> object:
        """按**已显式排序**的 items 取一个元素（禁止依赖容器迭代顺序）。"""
        if not items:
            raise ValueError("choice() on empty sequence")
        return items[self.next_u64() % len(items)]


class WorldRng:
    """世界级随机源：seed → 各子系统 stream。"""

    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._streams: dict[str, StreamRng] = {}

    def stream(self, name: str) -> StreamRng:
        """按名字取（必要时创建）子系统流；同 name 必须返回同一条流。"""
        stream = self._streams.get(name)
        if stream is None:
            stream = StreamRng(stream_key(self._seed, name))
            self._streams[name] = stream
        return stream

    def digests(self) -> dict[str, str]:
        """`{name: stream.digest()}`，按 name 升序 —— 即 snapshot.taken payload 的 `rng_digests`。"""
        return {name: self._streams[name].digest() for name in sorted(self._streams)}

    def state_digest(self) -> str:
        """所有 stream 的 (name, digest) 按 name 排序后的 sha256 —— 即 rng_state_digest。"""
        return hash_object(self.digests())
