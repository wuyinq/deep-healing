"""行为树组装（py_trees，V0 骨架）。

叶子节点 `call_capability(slot, budget)` 是规则层与能力层之间**唯一**的接缝：
叶子只声明槽位与预算，不关心 provider 是远端模型还是确定性规则（AC-13 的抽象边界）。
行为树结构本身由数据（效用配置 / 树定义 JSON）驱动，避免写死分支。
"""

from __future__ import annotations

from typing import Any


def build_tree(tree_spec: dict, registry: Any, budget: Any) -> Any:
    """按数据规格构建 py_trees 树；未知槽位在构建期即报错（fail fast）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'behaviour-tree'")


def call_capability(slot: str, budget: Any, registry: Any, payload: dict) -> dict:
    """行为树叶子：调用能力槽位并返回结构化结果（唯一模型调用入口）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'behaviour-tree'")
