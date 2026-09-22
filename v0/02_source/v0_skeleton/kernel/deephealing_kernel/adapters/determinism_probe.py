"""确定性探针的参考适配器（纯函数；`run_s7.sh` 的 F2③ 正例用）。

契约：`(payload: dict) -> dict`，返回值必须满足目标能力的 `output_schema`
（G1 收窄后的 `verified_impl` 语义要求「实现存在 + 输出合规 + 同输入同输出」三者齐备）。

本模块**无随机、无时钟、无网络、无文件系统写入**，因此可被校验期反复调用并比对摘要；
`payload` 只做只读访问。
"""
from __future__ import annotations


def pure_rule(payload: dict) -> dict:
    """`intent.plan` 的确定性参考实现：把 `npc_id` 原样映射到 `target_entity`。

    同输入 ⇒ 同输出；不引入任何随机性（这正是确定性闸门要验的性质）。
    """
    npc = payload.get("npc_id") if isinstance(payload, dict) else None
    return {
        "action": "rest",
        "target_entity": npc if isinstance(npc, str) and npc else None,
        "rationale_code": "rest",
        "confidence": 0.0,
    }
