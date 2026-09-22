"""DeepHealing 世界内核（L3）——V0 骨架包。

状态：**接口骨架**。本包内的函数签名与不变量已按 01 设计冻结，实现属于 V0 实施范围
（见 08_v0_plan.md），本轮架构冻结轮不实现产品代码。

分层不变量（任何实现都不得违反）：
  - 内核是唯一权威：世界状态的唯一写入点是 tick 内「执行阶段」；
  - 内核不得直接对浏览器暴露（一律经 L2 会话传输层）；
  - 内核不得把模型调用散落在业务逻辑：一律经 registry + providers 适配器；
  - tick 内禁止 wall-clock / 无序迭代 / 异步回填 / 共享 RNG 单流。
"""

from __future__ import annotations

__all__ = ["KERNEL_CONTRACT_VERSION"]

# 内核契约版本：内容包 engine_range 必须包含该版本，否则拒绝加载。
KERNEL_CONTRACT_VERSION = "1.0.0"
