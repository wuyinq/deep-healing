"""效用打分器（V0-M2 实现）。

需求标量 × 内容包权重（npcs/*.json 的 need_weights）× 情境修正 → 候选动作得分。
必须是**纯函数**：同输入同输出，禁止随机、禁止读时钟。

**显式 tie-break（设计 §3.2）**：分数降序 → 需求 id 升序 → 目标 id 升序。
**禁止**依赖 dict / set 迭代顺序；浮点按 6 位小数量化。
"""

from __future__ import annotations

NEEDS = ("physiology", "safety", "belonging", "esteem", "self_actualization")
DEFAULT_WEIGHTS = {
    "physiology": 1.0,
    "safety": 1.0,
    "belonging": 1.0,
    "esteem": 0.8,
    "self_actualization": 0.6,
}


def _q(value: float) -> float:
    return round(float(value), 6)


def _number(value: object, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def need_pressure(needs: dict[str, float], weights: dict[str, float]) -> float:
    """加权需求压力（用于判断是否值得调用认知能力）。"""
    effective = {name: _number(weights.get(name, DEFAULT_WEIGHTS.get(name, 1.0)), 1.0) for name in NEEDS}
    total = 0.0
    for name in NEEDS:
        total += _number(needs.get(name), 0.0) * effective[name]
    return _q(total)


def _score_candidate(candidate: dict, needs: dict, weights: dict, context: dict) -> tuple[float, str, str]:
    need = str(candidate.get("need") or "")
    weight = _number(candidate.get("weight"), 1.0)
    pressure = _number(needs.get(need), 0.0) * _number(weights.get(need, DEFAULT_WEIGHTS.get(need, 1.0)), 1.0)
    score = pressure * weight
    # 情境修正：日程状态命中候选声明的 `when_state` ⇒ 小幅加成（数据驱动，无 if 分支按 NPC 特判）
    when_state = candidate.get("when_state")
    if isinstance(when_state, str) and when_state and when_state == str(context.get("schedule_state", "")):
        score += 0.05
    return _q(score), need, str(candidate.get("target_entity") or "")


def score_actions(
    needs: dict[str, float],
    weights: dict[str, float],
    context: dict,
    candidates: list[dict],
) -> list[dict]:
    """返回按 (score desc, action asc) 排序的候选列表（显式排序，保证确定）。"""
    needs = needs if isinstance(needs, dict) else {}
    weights = weights if isinstance(weights, dict) else {}
    context = context if isinstance(context, dict) else {}
    scored: list[dict] = []
    for candidate in candidates if isinstance(candidates, list) else []:
        if not isinstance(candidate, dict):
            continue
        score, need, target = _score_candidate(candidate, needs, weights, context)
        scored.append({
            "action": str(candidate.get("action") or ""),
            "target_entity": target or None,
            "need": need,
            "score": score,
        })
    # 显式 tie-break：分数降序 → 需求 id 升序 → 目标 id 升序（禁止依赖容器迭代序）
    scored.sort(key=lambda item: (-item["score"], item["need"], item["target_entity"] or ""))
    return scored


def score(candidates: list[dict], context: dict) -> list[dict]:
    """设计 §3.2 命名形态：从 `context` 取 `needs` / `weights` 后转发 `score_actions`。"""
    context = context if isinstance(context, dict) else {}
    return score_actions(context.get("needs") or {}, context.get("weights") or {}, context, candidates)


def select(candidates: list[dict], context: dict) -> dict | None:
    """取打分首位（显式 tie-break 已由 `score` 保证）；空候选返回 None。"""
    ranked = score(candidates, context)
    return ranked[0] if ranked else None
