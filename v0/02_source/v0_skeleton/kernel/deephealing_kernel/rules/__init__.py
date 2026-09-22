"""规则层（L4 组合面）——V0 骨架。

规则层负责「何时调用哪个能力、给多少预算」，能力层负责「产出结构化结果」。
禁止在规则层直接发起 HTTP / SDK 调用：一律经 CapabilityRegistry.invoke。
"""

from __future__ import annotations

__all__ = ["utility", "behaviour_tree"]
