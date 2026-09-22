"""`relation.infer` 的实现体（**新增能力的 adapter 样本**，AC-13 的「只加数据 + adapter」证明面）。

本文件位于 `providers/adapters/` ⇒ 属 `kernel_digest.py` 的 **adapter 目录并集豁免面**
（`ADAPTER_DIRS = ("adapters/", "providers/adapters/")`）：新增本能力**不需要**改动
`deephealing_kernel/**` 任何既有文件（差集 `changed == []`）。

契约：`(payload: dict) -> dict`，返回值必须满足
`capabilities/relation.infer@1.0.0.capability.json` 的 `output_schema`。
**纯函数**：无随机、无时钟、无网络、无文件系统写入；浮点按 6 位小数量化。
**全函数**：对任何 JSON 形状的 `payload` 都不抛异常（校验期探针会按 `input_schema`
派生最简输入直接调用：`observations=[]` / `existing_relations={}`）。
"""

from __future__ import annotations

# 观察类型 → 关系强度增量（数据化常量；无 if 分支按 NPC 特判）
KIND_DELTA = {
    "help": 0.6,
    "gift": 0.4,
    "talk": 0.2,
    "avoid": -0.3,
    "conflict": -0.7,
}


def _q(value: float) -> float:
    return round(float(value), 6)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _observations(payload: dict) -> list[dict]:
    raw = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return []
    items: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        subject = entry.get("subject")
        other = entry.get("object")
        kind = entry.get("kind")
        weight = entry.get("weight")
        items.append({
            "subject": subject if isinstance(subject, str) else "",
            "object": other if isinstance(other, str) else "",
            "kind": kind if isinstance(kind, str) else "",
            "weight": float(weight) if isinstance(weight, (int, float)) else 0.0,
        })
    return items


def _prior(payload: dict) -> dict[str, float]:
    raw = payload.get("existing_relations") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return {}
    priors: dict[str, float] = {}
    for key in sorted(raw):
        value = raw[key]
        if isinstance(value, (int, float)):
            priors[str(key)] = float(value)
    return priors


def relation_infer_rule(payload: dict) -> dict:
    """把观察序列聚合成 `entity_id -> affinity`（显式排序 + 显式 tie-break，逐字节可复现）。

    口径：
      - 只统计「对端 = object、且 subject 是本 NPC 或未声明」的观察；
      - `observed = Σ weight × KIND_DELTA[kind]`（未登记 kind 记 0，不猜）；
      - `affinity = clamp(0.5 × prior + 0.5 × observed)`（无 prior 时取 `clamp(observed)`）；
      - 排序键：`affinity` 降序 → `entity_id` 升序（**禁止**依赖 dict/集合迭代序）；
      - `top_partner` = 排序首位且 `affinity > 0`，否则 None；`confidence` = 证据条数饱和函数。
    """
    npc_id = payload.get("npc_id") if isinstance(payload, dict) else None
    npc_id = npc_id if isinstance(npc_id, str) else ""
    observations = _observations(payload)
    priors = _prior(payload)

    observed: dict[str, float] = {}
    counts: dict[str, int] = {}
    for item in observations:
        if not item["object"]:
            continue
        if item["subject"] and npc_id and item["subject"] != npc_id:
            continue
        delta = KIND_DELTA.get(item["kind"], 0.0)
        observed[item["object"]] = observed.get(item["object"], 0.0) + item["weight"] * delta
        counts[item["object"]] = counts.get(item["object"], 0) + 1

    entities = sorted(set(observed) | set(priors))
    relations: list[dict] = []
    for entity_id in entities:
        prior = priors.get(entity_id)
        raw = observed.get(entity_id, 0.0)
        affinity = _clamp(raw, -1.0, 1.0) if prior is None else _clamp(0.5 * prior + 0.5 * raw, -1.0, 1.0)
        relations.append({
            "entity_id": entity_id,
            "affinity": _q(affinity),
            "evidence_count": counts.get(entity_id, 0),
        })

    relations.sort(key=lambda item: (-item["affinity"], item["entity_id"]))
    top = relations[0] if relations and relations[0]["affinity"] > 0 else None
    evidence = sum(counts.values())
    confidence = 0.0 if evidence == 0 else _q(_clamp(evidence / (evidence + 4.0), 0.0, 1.0))
    return {
        "relations": relations,
        "top_partner": top["entity_id"] if top is not None else None,
        "confidence": confidence,
    }
