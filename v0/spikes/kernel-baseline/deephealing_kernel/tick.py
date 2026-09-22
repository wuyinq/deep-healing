"""固定步长 tick 循环与阶段顺序（V0 骨架，契约冻结）。

阶段顺序是**契约的一部分**（01 设计 §3.2）：[1] 输入 → [2] 感知 → [3] 规则层组合/能力调用
→ [4] 执行（唯一写点） → [5] 记账（事件追加） → [6] 快照。

硬约束（AC-2 判据的前提）：
  - dt = 100ms 固定，tick 率 10 Hz；
  - tick 内**禁止** wall-clock / time.time() / 线程完成顺序 / set|dict 迭代顺序 / 网络结果；
  - 异步能力结果只能在 tick 边界之外完成，于**下一 tick** 注入；迟到结果丢弃并记 metric。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

PHASES = (
    "input",
    "perceive",
    "decide",
    "execute",
    "account",
    "snapshot",
)


@dataclass(frozen=True, slots=True)
class TickContext:
    """一个 tick 内的只读上下文（由内核构造，阶段内不得修改）。"""

    tick: int
    dt_ms: int = 100


class TickObserver(Protocol):
    """观测层（L7）与传输层（L2）只订阅，不得写内核状态。"""

    def on_tick(self, ctx: TickContext) -> None: ...


class WorldKernel:
    """世界内核（唯一权威）。

    V0 骨架：接口签名冻结，实现见 08_v0_plan.md。
    """

    def step(self) -> None:
        """推进一个 tick（阶段顺序 = PHASES，不可交换）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'tick-loop'")

    def snapshot(self) -> dict:
        """返回当前快照（须通过 snapshot.schema.json）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'snapshot'")

    def state_hash(self) -> str:
        """sha256(canonical_json(state))。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'snapshot'")

    def run(self, ticks: int) -> None:
        """连续推进 ticks 个 tick（每 tick 边界注入已完成的能力结果）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'tick-loop'")
