"""deterministic_rule provider：确定性规则兜底（V0-M2 实现，契约冻结）。

要求：**纯函数**（同输入同输出、无随机、无时钟、无网络），必须能通过能力的 output_schema。
它是降级链的终态之一（另一个是 deterministic_stub），保证远端不可用时世界仍能 tick。

**M2 实现口径（设计 §3.1）**：
  - 四个纯函数与 `capabilities/*.capability.json` 的 `impl` 引用**逐字对应**；
  - 四个函数都是**全函数**：对任何 JSON 形状的 `payload` 都不抛异常
    （校验期探针 `tools/verify_capability_binding.py` 会按 `input_schema` 派生**最简输入**
     直接调用，例如 `texts=[]` / `needs={}` / `candidate_actions=[]` / `episodes=[]`）；
  - 浮点一律按固定口径量化（`_q()` 6 位小数），保证同输入同输出、跨进程摘要一致；
  - **无任何毫秒常量**（超时值来自能力契约的声明值，见 `budget.py` / `registry.py`）。
"""

from __future__ import annotations

from typing import Any, Callable

EMBED_DIM = 128

# --------------------------------------------------------------------- 小工具
def _q(value: float) -> float:
    """固定量化口径（6 位小数）——与 canonical_json 的 FLOAT_DIGITS 同口径，保证摘要稳定。"""
    return round(float(value), 6)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _stable_hash(text: str) -> int:
    """跨进程稳定的整数散列（禁用内置 hash()：它按进程加盐）。"""
    import hashlib

    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def _as_texts(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    texts = payload.get("texts")
    if not isinstance(texts, list):
        return []
    return [text if isinstance(text, str) else str(text) for text in texts]


def _bag_vector(text: str) -> list[float]:
    """字符 n-gram（1/2/3）哈希袋投影到固定维，再 L2 归一（全零时保持全零）。"""
    buckets = [0.0] * EMBED_DIM
    grams: list[str] = []
    for size in (1, 2, 3):
        if len(text) < size:
            continue
        grams.extend(text[index:index + size] for index in range(len(text) - size + 1))
    for gram in grams:
        buckets[_stable_hash(gram) % EMBED_DIM] += 1.0
    norm = sum(value * value for value in buckets) ** 0.5
    if norm == 0.0:
        return [_q(0.0)] * EMBED_DIM
    return [_q(value / norm) for value in buckets]


# --------------------------------------------------------------------- 纯函数
def embed_text_rule(payload: dict) -> dict:
    """字符 n-gram 哈希袋投影到固定维（默认 128）；离线兜底，语义质量不保证。"""
    texts = _as_texts(payload)
    return {
        "dim": EMBED_DIM,
        "vectors": [_bag_vector(text) for text in texts],
        "provider_note": "deterministic_rule: char 1/2/3-gram hash bag, L2-normalized (offline fallback)",
    }


_POSITIVE_WORDS = ("开心", "高兴", "温暖", "治愈", "安心", "希望", "喜欢", "谢谢", "陪伴", "顺利", "好转", "微笑")
_NEGATIVE_WORDS = ("难过", "害怕", "疼", "孤单", "生气", "失眠", "焦虑", "疼", "失去", "争吵", "冷", "拒绝")


def _count_words(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for word in words if word in text)


def _mood_label(valence: float, arousal: float) -> str:
    """阈值映射（显式、无随机）：返回 output_schema 枚举内的取值。"""
    if valence >= 0.4:
        return "hopeful" if arousal >= 0.5 else "content"
    if valence <= -0.4:
        return "irritated" if arousal >= 0.5 else "sad"
    if arousal >= 0.5:
        return "anxious"
    return "calm" if arousal >= 0.3 else "numb"


def emotion_appraise_rule(payload: dict) -> dict:
    """情感词典 + 阈值映射到 (valence, arousal, mood_label, importance)。"""
    summary = payload.get("event_summary") if isinstance(payload, dict) else None
    summary = summary if isinstance(summary, str) else ""
    current = payload.get("current_emotion") if isinstance(payload, dict) else None
    current = current if isinstance(current, dict) else {}

    positive = _count_words(summary, _POSITIVE_WORDS)
    negative = _count_words(summary, _NEGATIVE_WORDS)
    total = positive + negative
    delta = 0.0 if total == 0 else (positive - negative) / float(total)

    previous_valence = current.get("valence")
    previous_valence = float(previous_valence) if isinstance(previous_valence, (int, float)) else 0.0
    valence = _clamp(_q(0.6 * previous_valence + 0.4 * delta), -1.0, 1.0)

    exclamations = min(summary.count("!") + summary.count("！"), 3)
    arousal = _clamp(_q(0.2 + 0.15 * total + 0.1 * exclamations), 0.0, 1.0)
    importance = _clamp(_q(0.2 + 0.1 * total + 0.3 * abs(delta) + 0.05 * len(summary) / 10.0), 0.0, 1.0)

    return {
        "valence": valence,
        "arousal": arousal,
        "mood_label": _mood_label(valence, arousal),
        "importance": importance,
    }


_DEFAULT_NEED_WEIGHTS = {
    "physiology": 1.0,
    "safety": 1.0,
    "belonging": 1.0,
    "esteem": 0.8,
    "self_actualization": 0.6,
}
# 动作关键词 → 该动作主要缓解的需求（数据驱动的最小映射；无 if 分支按 NPC 特判）
_ACTION_NEEDS = (
    (("rest", "sleep", "hold", "pause"), ("physiology",)),
    (("eat", "drink", "meal"), ("physiology",)),
    (("flee", "guard", "lock", "safety"), ("safety",)),
    (("talk", "chat", "visit", "greet", "social"), ("belonging",)),
    (("work", "study", "practice", "craft"), ("esteem", "self_actualization")),
    (("walk", "move", "explore", "wander"), ("self_actualization",)),
)


def _needs_pressure(needs: dict, weights: dict) -> dict[str, float]:
    pressure: dict[str, float] = {}
    for name in sorted(weights):
        raw = needs.get(name) if isinstance(needs, dict) else None
        value = float(raw) if isinstance(raw, (int, float)) else 0.0
        pressure[name] = _q(value * float(weights[name]))
    return pressure


def intent_plan_rule(payload: dict) -> dict:
    """需求加权效用取 argmax；同分时按 action 名字典序取首个（显式确定性 tie-break）。"""
    needs = payload.get("needs") if isinstance(payload, dict) else None
    needs = needs if isinstance(needs, dict) else {}
    weights = dict(_DEFAULT_NEED_WEIGHTS)
    custom = payload.get("need_weights") if isinstance(payload, dict) else None
    if isinstance(custom, dict):
        for key in sorted(custom):
            raw = custom[key]
            if isinstance(raw, (int, float)):
                weights[key] = float(raw)
    candidates = payload.get("candidate_actions") if isinstance(payload, dict) else None
    actions = [str(item) for item in candidates] if isinstance(candidates, list) else []

    pressure = _needs_pressure(needs, weights)
    scored: list[tuple[float, str, str]] = []
    for action in actions:
        needs_hit = _ACTION_NEEDS[-1][1]
        for keywords, mapped in _ACTION_NEEDS:
            if any(keyword in action.lower() for keyword in keywords):
                needs_hit = mapped
                break
        score = _q(sum(pressure.get(name, 0.0) for name in needs_hit))
        rationale = _RATIONALE_BY_NEED.get(needs_hit[0], "need_relief")
        scored.append((score, action, rationale))

    if not scored:
        return {"action": "hold", "target_entity": None, "rationale_code": "rest",
                "confidence": 0.0, "duration_ticks": 1}

    # 显式 tie-break：分数降序 → action 名字典序升序
    scored.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_action, rationale = scored[0]
    ceiling = max(score for score, _, _ in scored)
    confidence = 0.0 if ceiling <= 0.0 else _clamp(_q(best_score / ceiling), 0.0, 1.0)
    target = payload.get("npc_id") if isinstance(payload, dict) else None
    return {
        "action": best_action,
        "target_entity": target if isinstance(target, str) and target else None,
        "rationale_code": rationale,
        "confidence": confidence,
        "duration_ticks": 1,
    }


_RATIONALE_BY_NEED = {
    "physiology": "rest",
    "safety": "safety_seek",
    "belonging": "social_contact",
    "esteem": "need_relief",
    "self_actualization": "explore",
}


def memory_reflect_rule(payload: dict) -> dict:
    """按 importance 阈值抽取事实模板，产出 insights/new_facts/summary。"""
    episodes = payload.get("episodes") if isinstance(payload, dict) else None
    episodes = episodes if isinstance(episodes, list) else []
    normalized: list[dict] = []
    for item in episodes:
        if not isinstance(item, dict):
            continue
        tick = item.get("tick")
        kind = item.get("kind")
        summary = item.get("text_summary")
        importance = item.get("importance")
        normalized.append({
            "tick": int(tick) if isinstance(tick, (int, float)) else 0,
            "kind": kind if isinstance(kind, str) else "",
            "text_summary": summary if isinstance(summary, str) else "",
            "importance": float(importance) if isinstance(importance, (int, float)) else 0.0,
        })
    # 显式排序：tick 升序 → kind 升序 → 文本升序（禁止依赖输入顺序）
    normalized.sort(key=lambda item: (item["tick"], item["kind"], item["text_summary"]))

    threshold = 0.6
    insights: list[str] = []
    new_facts: list[dict] = []
    for item in normalized:
        if item["importance"] < threshold:
            continue
        if len(insights) < 8:
            insights.append(f"{item['kind']}@{item['tick']}: {item['text_summary']}"[:500])
        if len(new_facts) < 8:
            new_facts.append({
                "key": f"{item['kind'] or 'episode'}.{item['tick']}",
                "value": item["text_summary"][:500],
                "confidence": _clamp(_q(item["importance"]), 0.0, 1.0),
            })
    total = len(normalized)
    summary = "" if total == 0 else (
        f"episodes={total} insights={len(insights)} facts={len(new_facts)}"
        f" window_ticks={payload.get('window_ticks') if isinstance(payload, dict) else None}"
    )[:1000]
    return {"insights": insights, "new_facts": new_facts, "summary": summary}


# --------------------------------------------------------------------- provider 适配器
RULE_IMPLS: dict[str, Callable[[dict], dict]] = {
    "intent_plan_rule": intent_plan_rule,
    "emotion_appraise_rule": emotion_appraise_rule,
    "memory_reflect_rule": memory_reflect_rule,
    "embed_text_rule": embed_text_rule,
}


class DeterministicRuleProvider:
    """把上面的纯函数包装成 provider 适配器。"""

    provider_class = "deterministic_rule"

    def __init__(self, impl_name: str = "") -> None:
        self._impl_name = impl_name

    def invoke(self, capability: dict, payload: dict, *, timeout_ms: int) -> dict:
        """按能力契约声明的 `impl` 解析纯函数并调用（**超时值不参与计算**：纯函数无 IO）。"""
        impl = _declared_impl(capability) or self._impl_name
        name = impl.rsplit(":", 1)[-1] if impl else ""
        rule = RULE_IMPLS.get(name)
        if rule is None:
            raise LookupError(f"deterministic_rule: unknown impl {impl!r}")
        return rule(payload if isinstance(payload, dict) else {})


def _declared_impl(capability: dict) -> str:
    for provider in capability.get("providers", []) if isinstance(capability, dict) else []:
        if isinstance(provider, dict) and provider.get("class") == "deterministic_rule":
            impl = provider.get("impl")
            return impl if isinstance(impl, str) else ""
    return ""
