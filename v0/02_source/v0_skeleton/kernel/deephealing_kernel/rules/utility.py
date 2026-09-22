"""效用打分器（V0 骨架）。

需求标量 × 内容包权重（npcs/*.json 的 need_weights）× 情境修正 → 候选动作得分。
必须是**纯函数**：同输入同输出，禁止随机、禁止读时钟。
"""

from __future__ import annotations


def score_actions(
    needs: dict[str, float],
    weights: dict[str, float],
    context: dict,
    candidates: list[dict],
) -> list[dict]:
    """返回按 (score desc, action asc) 排序的候选列表（显式排序，保证确定）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'utility'")


def need_pressure(needs: dict[str, float], weights: dict[str, float]) -> float:
    """加权需求压力（用于判断是否值得调用认知能力）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'utility'")
