"""deterministic_rule provider：确定性规则兜底（V0 骨架）。

要求：**纯函数**（同输入同输出、无随机、无时钟、无网络），必须能通过能力的 output_schema。
它是降级链的终态之一（另一个是 deterministic_stub），保证远端不可用时世界仍能 tick。
"""

from __future__ import annotations


def intent_plan_rule(payload: dict) -> dict:
    """需求加权效用取 argmax；同分时按 action 名字典序取首个（显式确定性 tie-break）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'provider-rule'")


def emotion_appraise_rule(payload: dict) -> dict:
    """情感词典 + 阈值映射到 (valence, arousal, mood_label, importance)。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'provider-rule'")


def memory_reflect_rule(payload: dict) -> dict:
    """按 importance 阈值抽取事实模板，产出 insights/new_facts/summary。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'provider-rule'")


def embed_text_rule(payload: dict) -> dict:
    """字符 n-gram 哈希袋投影到固定维（默认 128）；离线兜底，语义质量不保证。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'provider-rule'")


class DeterministicRuleProvider:
    """把上面的纯函数包装成 provider 适配器。"""

    provider_class = "deterministic_rule"

    def __init__(self, impl_name: str) -> None:
        self._impl_name = impl_name

    def invoke(self, capability: dict, payload: dict, *, timeout_ms: int) -> dict:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'provider-rule'")
