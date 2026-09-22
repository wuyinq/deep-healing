"""记忆层（L6）——V0 骨架。

三层：working（环形缓冲）/ episodic（sqlite 事件索引）/ semantic（反思产出的稳定事实）。
范式借鉴 generative_agents 的记忆流与反思（Apache-2.0，仅范式，不集成其运行时）。
边界：记忆层不得绕过 schema 写世界状态；记忆只影响认知输入与规则层打分。
"""

from __future__ import annotations

__all__ = ["store", "retrieve"]
