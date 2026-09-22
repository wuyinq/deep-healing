"""确定性随机源：单一 seed + 子系统分流（V0 骨架，契约冻结）。

规则（01 设计 §4.3）：
  - 全进程唯一 `WorldRng(seed)`；tick 内禁止重新播种；
  - 子系统取流用 `rng.stream("<subsystem>")`，stream 名经哈希派生，**新增子系统不得扰动既有 stream 序列**
    （这是「加一个 NPC / 加一个街区不改历史哈希」的前提）；
  - 禁用全局 random 模块与任何系统熵（time/os.urandom）。
"""

from __future__ import annotations

import hashlib


class StreamRng:
    """单个子系统的确定性随机流（计数器驱动，无隐式状态共享）。"""

    def __init__(self, key: bytes, counter: int = 0) -> None:
        self._key = key
        self._counter = counter

    def digest(self) -> str:
        """该流的确定性摘要（进 rng_state_digest，用于证明两次回放随机轨迹一致）。"""
        return hashlib.sha256(self._key + self._counter.to_bytes(8, "big")).hexdigest()

    def next_u64(self) -> int:
        """推进计数器并返回一个确定性 64 位无符号整数。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'rng-streams'")

    def uniform(self, low: float, high: float) -> float:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'rng-streams'")

    def choice(self, items: list) -> object:
        """按**已显式排序**的 items 取一个元素（禁止依赖容器迭代顺序）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'rng-streams'")


class WorldRng:
    """世界级随机源：seed → 各子系统 stream。"""

    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._streams: dict[str, StreamRng] = {}

    def stream(self, name: str) -> StreamRng:
        """按名字取（必要时创建）子系统流；同 name 必须返回同一条流。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'rng-streams'")

    def state_digest(self) -> str:
        """所有 stream 的 (name, digest) 按 name 排序后的 sha256 —— 即 rng_state_digest。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'rng-streams'")
