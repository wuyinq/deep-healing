"""行为树组装（V0-M2 实现）。

叶子节点 `call_capability(slot, budget)` 是规则层与能力层之间**唯一**的接缝：
叶子只声明槽位与预算，不关心 provider 是远端模型还是确定性规则（AC-13 的抽象边界）。
行为树结构本身由数据（树定义 JSON）驱动，避免写死分支。

**实现口径（M2 明确声明）**：本机**没有** `py_trees`（`import py_trees` → `ModuleNotFoundError`），
而安装新依赖不在本轮授权面（环境无新依赖预算）⇒ 本模块实现一个**极小的数据驱动树求值器**，
节点语义与冻结文档一致：节点返回 `SUCCESS` / `FAILURE` / `RUNNING`。
树定义形态（JSON 可表达，无代码分支）：
    {"type": "sequence", "children": [...]}
    {"type": "selector", "children": [...]}
    {"type": "condition", "key": "<blackboard 键>", "op": ">=", "value": <数值>}
    {"type": "action", "slot": "<能力槽位>", "payload": {...}, "store_as": "<blackboard 键>"}
`payload` 里的 `"$<key>"` 字符串会被替换为 blackboard 取值（数据引用，非硬编码）。
"""

from __future__ import annotations

from typing import Any

from ..providers.cassette import CassetteMiss

SUCCESS = "SUCCESS"
FAILURE = "FAILURE"
RUNNING = "RUNNING"

_OPS = {
    ">=": lambda left, right: left >= right,
    ">": lambda left, right: left > right,
    "<=": lambda left, right: left <= right,
    "<": lambda left, right: left < right,
    "==": lambda left, right: left == right,
}


def build_tree(tree_spec: dict, registry: Any, budget: Any) -> dict:
    """按数据规格构建树；未知槽位在构建期即报错（fail fast）。"""
    if not isinstance(tree_spec, dict):
        raise ValueError("tree spec must be a JSON object")
    kind = str(tree_spec.get("type", ""))
    if kind in ("sequence", "selector"):
        children = tree_spec.get("children")
        if not isinstance(children, list) or not children:
            raise ValueError(f"{kind} node must declare a non-empty children array")
        return {"type": kind, "children": [build_tree(child, registry, budget) for child in children]}
    if kind == "condition":
        operator = str(tree_spec.get("op", ">="))
        if operator not in _OPS:
            raise ValueError(f"unknown condition operator {operator!r}")
        return {
            "type": "condition",
            "key": str(tree_spec.get("key", "")),
            "op": operator,
            "value": tree_spec.get("value"),
        }
    if kind == "action":
        slot = str(tree_spec.get("slot", ""))
        slots = registry.slots() if registry is not None else []
        if slots and slot not in slots:
            raise ValueError(f"action node declares unknown capability slot {slot!r} (known: {slots})")
        return {
            "type": "action",
            "slot": slot,
            "payload": tree_spec.get("payload") or {},
            "store_as": str(tree_spec.get("store_as", slot)),
        }
    raise ValueError(f"unknown node type {kind!r}")


def _resolve_payload(payload: Any, blackboard: dict) -> Any:
    """把 `"$key"` 字符串替换为 blackboard 取值（深拷贝语义，不改原 spec）。"""
    if isinstance(payload, str):
        if payload.startswith("$"):
            return blackboard.get(payload[1:])
        return payload
    if isinstance(payload, dict):
        return {key: _resolve_payload(value, blackboard) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_resolve_payload(item, blackboard) for item in payload]
    return payload


def tick(node: dict, blackboard: dict, budget: Any) -> str:
    """求值一个节点，返回 `SUCCESS` / `FAILURE` / `RUNNING`（确定性；无 wall-clock）。"""
    if not isinstance(node, dict):
        return FAILURE
    kind = node.get("type")
    if kind == "sequence":
        for child in node["children"]:
            status = tick(child, blackboard, budget)
            if status != SUCCESS:
                return status
        return SUCCESS
    if kind == "selector":
        for child in node["children"]:
            status = tick(child, blackboard, budget)
            if status == SUCCESS:
                return SUCCESS
        return FAILURE
    if kind == "condition":
        left = blackboard.get(node["key"])
        if not isinstance(left, (int, float)) or isinstance(left, bool):
            return FAILURE
        right = node.get("value")
        if not isinstance(right, (int, float)) or isinstance(right, bool):
            return FAILURE
        return SUCCESS if _OPS[node["op"]](float(left), float(right)) else FAILURE
    if kind == "action":
        registry = blackboard.get("__registry__")
        payload = _resolve_payload(node["payload"], blackboard)
        try:
            output = call_capability(node["slot"], budget, registry, payload)
        except CassetteMiss as error:
            # **修-2 / R-M2-2**：`--replay` 下的 cassette miss **不得**被 action 节点吞成 FAILURE ——
            # 那会让「fail-closed」退化成「树走了另一条分支」而命令层 exit 0。
            # 原样向上抛（registry 已先记 `cassette.miss` journal），由 CLI 转 exit 1 + 结构化诊断。
            # 方向不变：**不降级、不回填、不静默切远端**。
            blackboard.setdefault("__errors__", []).append(
                {"slot": node["slot"], "error": type(error).__name__, "fail_closed": True}
            )
            raise
        except Exception as error:  # noqa: BLE001 —— 能力失败是**正常分支**，转 FAILURE 交给 selector
            blackboard.setdefault("__errors__", []).append(
                {"slot": node["slot"], "error": type(error).__name__}
            )
            return FAILURE
        blackboard[node["store_as"]] = output
        return SUCCESS
    return FAILURE


def call_capability(slot: str, budget: Any, registry: Any, payload: dict) -> dict:
    """行为树叶子：调用能力槽位并返回结构化结果（唯一模型调用入口）。

    **出口纪律**：`CapabilityRegistry.invoke` 已保证「provider 返回必过 output_schema」，
    不合规即按 `fallback` 链降级并落 `capability.fallback`（**禁止静默回填**）。
    """
    if registry is None:
        raise RuntimeError("no capability registry bound to the blackboard")
    result = registry.invoke(slot, payload, budget=budget)
    if not result.ok:
        raise RuntimeError(f"capability {slot} returned not-ok")
    return dict(result.output)


def run_tree(tree_spec: dict, blackboard: dict, registry: Any, budget: Any) -> dict:
    """构建 + 求值一次（返回状态与 blackboard 快照键，供日志与回放比对）。"""
    compiled = build_tree(tree_spec, registry, budget)
    blackboard["__registry__"] = registry
    status = tick(compiled, blackboard, budget)
    return {
        "status": status,
        "keys": sorted(key for key in blackboard if not key.startswith("__")),
    }
