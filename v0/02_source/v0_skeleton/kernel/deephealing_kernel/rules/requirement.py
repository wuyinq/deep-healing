"""需求层（V0-M2 新增，设计 §3.2）。

把 NPC 需求/权重映射为**可比较**的需求记录（纯数据驱动，不硬编码住户）。
纯函数：同输入同输出，禁止随机、禁止读时钟、禁止依赖容器迭代顺序。

与 `utility.py` 的分工：本模块只负责「需求 → 需求记录」的**归一化**（谁更紧迫、缺多少），
打分与 tie-break 在 `utility.py`。
"""

from __future__ import annotations

from dataclasses import dataclass

NEEDS = ("physiology", "safety", "belonging", "esteem", "self_actualization")
DEFAULT_WEIGHTS = {
    "physiology": 1.0,
    "safety": 1.0,
    "belonging": 1.0,
    "esteem": 0.8,
    "self_actualization": 0.6,
}


@dataclass(frozen=True, slots=True)
class Requirement:
    """一条可比较的需求记录（`deficit` 越大越紧迫）。"""

    need_id: str
    level: float
    weight: float
    deficit: float


def _q(value: float) -> float:
    return round(float(value), 6)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _number(value: object, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def evaluate(needs: dict, context: dict) -> list[Requirement]:
    """把 `needs` × `context.weights`（缺省用内容包默认权重）映射为需求记录列表。

    排序键：`deficit` 降序 → `need_id` 升序（显式 tie-break，保证逐字节可复现）。
    `context` 可含 `npc_id` / `tick`（只作上下文透传，不参与计算）。
    """
    needs = needs if isinstance(needs, dict) else {}
    context = context if isinstance(context, dict) else {}
    weights = context.get("weights")
    weights = weights if isinstance(weights, dict) else {}

    records: list[Requirement] = []
    for need_id in NEEDS:
        level = _clamp(_number(needs.get(need_id), 0.0))
        weight = _number(weights.get(need_id, DEFAULT_WEIGHTS.get(need_id, 1.0)), 1.0)
        records.append(Requirement(
            need_id=need_id,
            level=_q(level),
            weight=_q(weight),
            deficit=_q((1.0 - level) * weight),
        ))
    records.sort(key=lambda item: (-item.deficit, item.need_id))
    return records
