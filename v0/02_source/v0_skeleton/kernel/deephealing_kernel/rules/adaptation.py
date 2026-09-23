"""任务演进的规则层（AC-M3-5 / D-14，**M3 新增**）。

定位：把内容包 `tasks/*.json` 的 `adaptation_rules` 变成**数据驱动**的行为 —— 玩家介入（`intent.applied`）
命中规则 ⇒ 任务状态机按 `effect.shift_to` 迁移 ⇒ 内核发 `task.state_changed` 事件并留**审计记录**。

数据驱动（硬）：本模块**没有** `if task_id == ...` / `if npc_id == ...` 分支；规则、目标、迁移目标状态
全部来自内容包文档。新增任务只需加数据。

求值顺序（**D-14 裁决，冻结**）：
  1. **守卫规则先求值并短路** —— 带 `effect.no_op: true` 或 `max_shifts == 0` 的规则优先；
     `match.repeat_within_ticks` 命中同样属于守卫命中。
  2. 其余规则按 `adaptation_rules` **数组顺序**。
  3. 一次事件**只应用一条**规则（命中即短路），不得在守卫命中后再应用 `shift_to` 规则。
  理由（Raven 预审 M5）：`rule-001-warmth` 与 `rule-001-repetition-guard` 的 match 谓词**重叠**；
  若按数组顺序先应用 warmth，「防刷」语义（`max_shifts:0` + `no_op`）会被旁路，而判据仍全绿。

`max_shifts` 是**硬上限**：同一 `(task, rule)` 的迁移计数达到 `max_shifts` 后，该规则不再产出迁移
（产出 `max_shifts_reached` 审计，不发 `task.state_changed`）。

世界状态边界（**刻意为之**）：任务状态机**不进** `world.schema.json` 的 `state`。
`world.schema.json` 的 `additionalProperties:false` + `kind` 枚举 + 组件白名单是冻结契约，
新增「任务实体」属内核契约变更（需 ADR）。因此任务状态由内核持有，且**只**由「同一 intent 序列」决定
⇒ 可回放、逐字节一致（AC-M3-6②），而 `state_hash`（世界状态）在无 intent 时**逐位不变**（F-4 红线）。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

# 规则 match 谓词支持的字段（全部可选；未出现的字段 = 不约束）
MATCH_FIELDS = ("event_type", "kind", "target", "repeat_within_ticks")

DECISION_SHIFT = "shift"
DECISION_GUARD_NO_OP = "guard_no_op"
DECISION_MAX_SHIFTS_REACHED = "max_shifts_reached"
DECISION_INVALID_SHIFT = "invalid_shift"
DECISION_NO_CHANGE = "no_change"


@dataclass(frozen=True, slots=True)
class AdaptationAudit:
    """一次规则求值的**审计记录**（写进 `task.state_changed` 事件 payload 或内核审计流水）。"""

    task_id: str
    rule_id: str
    decision: str
    from_state: str
    to_state: str
    reason: str
    impact_cost: float
    shift_index: int
    matched_event: str

    @property
    def is_shift(self) -> bool:
        return self.decision == DECISION_SHIFT

    def to_payload(self) -> dict[str, Any]:
        """审计字段（可安全进事件 payload；无密钥、无玩家原文）。"""
        return {
            "task_id": self.task_id,
            "rule_id": self.rule_id,
            "decision": self.decision,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "impact_cost": self.impact_cost,
            "shift_index": self.shift_index,
            "matched_event": self.matched_event,
        }


def rule_is_guard(rule: dict) -> bool:
    """守卫规则判定：`effect.no_op == true` 或 `max_shifts == 0`（D-14 第 1 条）。"""
    effect = rule.get("effect") or {}
    if bool(effect.get("no_op")):
        return True
    return int(rule.get("max_shifts", 0)) == 0


def order_rules(rules: list[dict]) -> list[dict]:
    """守卫规则优先，其余保持**数组顺序**（稳定排序 ⇒ 确定性）。"""
    return sorted(rules, key=lambda rule: 0 if rule_is_guard(rule) else 1)


def _matches(
    rule: dict,
    *,
    event_type: str,
    kind: str | None,
    target: str | None,
    tick: int,
    last_applied_tick: int | None,
) -> bool:
    match = rule.get("match") or {}
    if match.get("event_type") is not None and str(match["event_type"]) != event_type:
        return False
    if match.get("kind") is not None and str(match["kind"]) != (kind or ""):
        return False
    if match.get("target") is not None and str(match["target"]) != (target or ""):
        return False
    repeat_within = match.get("repeat_within_ticks")
    if repeat_within is not None:
        if last_applied_tick is None:
            return False
        if int(tick) - int(last_applied_tick) > int(repeat_within):
            return False
    return True


class TaskAdaptationEngine:
    """按内容包 `tasks/*.json` 装配的任务演进引擎（无状态机代码分支）。"""

    def __init__(self, tasks: list[dict] | None = None) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        for document in sorted((tasks or []), key=lambda item: str(item.get("id", ""))):
            if not isinstance(document, dict):
                continue
            task_id = str(document.get("id", ""))
            if not task_id:
                continue
            self._tasks[task_id] = {
                "rules": [copy.deepcopy(rule) for rule in (document.get("adaptation_rules") or [])],
                "states": [str(state) for state in (document.get("states") or [])],
                "state": str(document.get("initial_state", "")),
                "shifts": {},          # rule_id -> 已应用次数（max_shifts 硬上限的计数）
                "last_applied": {},    # target -> 最近一次 intent.applied 的 tick（防刷守卫输入）
                "audit": [],           # 只追加的审计流水（顺序确定 ⇒ 可回放）
            }

    # ------------------------------------------------------------------ 只读视图
    def task_ids(self) -> list[str]:
        return sorted(self._tasks)

    def state_of(self, task_id: str) -> str | None:
        entry = self._tasks.get(str(task_id))
        return None if entry is None else str(entry["state"])

    def states_snapshot(self) -> dict[str, str]:
        """任务状态快照（按 task_id 升序；用于确定性比对）。"""
        return {task_id: str(self._tasks[task_id]["state"]) for task_id in sorted(self._tasks)}

    def audit_log(self) -> list[dict]:
        """全量审计流水（按发生顺序）。"""
        return [record.to_payload() for entry in self._tasks.values() for record in entry["audit"]]

    def shift_counts(self, task_id: str) -> dict[str, int]:
        entry = self._tasks.get(str(task_id))
        return {} if entry is None else dict(entry["shifts"])

    # ------------------------------------------------------------------ 求值
    def note_intent_applied(self, *, target: str | None, tick: int) -> None:
        """登记一次已应用的介入（**守卫的输入**）：同一目标重复介入的「重复窗口」由此判定。"""
        for entry in self._tasks.values():
            entry["last_applied"][str(target or "")] = int(tick)

    def evaluate(
        self,
        *,
        event_type: str,
        kind: str | None,
        target: str | None,
        tick: int,
        impact_cost: float = 0.0,
    ) -> list[AdaptationAudit]:
        """对所有任务求值；返回审计记录（一次事件每个任务**至多一条**）。"""
        audits: list[AdaptationAudit] = []
        for task_id in sorted(self._tasks):
            audit = self._evaluate_task(
                task_id, event_type=event_type, kind=kind, target=target, tick=int(tick),
                impact_cost=float(impact_cost),
            )
            if audit is not None:
                audits.append(audit)
        return audits

    def _evaluate_task(
        self,
        task_id: str,
        *,
        event_type: str,
        kind: str | None,
        target: str | None,
        tick: int,
        impact_cost: float,
    ) -> AdaptationAudit | None:
        entry = self._tasks[task_id]
        rules = entry["rules"]
        if not rules:
            return None
        last_applied_tick = entry["last_applied"].get(str(target or ""))
        for rule in order_rules(rules):
            if not _matches(rule, event_type=event_type, kind=kind, target=target, tick=tick,
                            last_applied_tick=last_applied_tick):
                continue
            rule_id = str(rule.get("id", ""))
            effect = rule.get("effect") or {}
            reason = str(effect.get("reason", ""))
            current = str(entry["state"])

            # ---- 守卫命中：短路，**不得**再应用 shift_to 规则 ----
            if rule_is_guard(rule):
                record = AdaptationAudit(
                    task_id=task_id, rule_id=rule_id, decision=DECISION_GUARD_NO_OP,
                    from_state=current, to_state=current, reason=reason,
                    impact_cost=0.0, shift_index=int(entry["shifts"].get(rule_id, 0)),
                    matched_event=event_type,
                )
                entry["audit"].append(record)
                return record

            # ---- shift 规则：max_shifts 硬上限 ----
            max_shifts = int(rule.get("max_shifts", 0))
            used = int(entry["shifts"].get(rule_id, 0))
            if used >= max_shifts:
                record = AdaptationAudit(
                    task_id=task_id, rule_id=rule_id, decision=DECISION_MAX_SHIFTS_REACHED,
                    from_state=current, to_state=current,
                    reason=f"max_shifts={max_shifts} reached for rule {rule_id}",
                    impact_cost=0.0, shift_index=used, matched_event=event_type,
                )
                entry["audit"].append(record)
                return record

            to_state = effect.get("shift_to")
            if to_state is None or str(to_state) not in entry["states"]:
                record = AdaptationAudit(
                    task_id=task_id, rule_id=rule_id, decision=DECISION_INVALID_SHIFT,
                    from_state=current, to_state=current,
                    reason=f"shift_to {to_state!r} not in declared states {entry['states']}",
                    impact_cost=0.0, shift_index=used, matched_event=event_type,
                )
                entry["audit"].append(record)
                return record

            to_state = str(to_state)
            if to_state == current:
                record = AdaptationAudit(
                    task_id=task_id, rule_id=rule_id, decision=DECISION_NO_CHANGE,
                    from_state=current, to_state=current, reason=reason,
                    impact_cost=0.0, shift_index=used, matched_event=event_type,
                )
                entry["audit"].append(record)
                return record

            entry["state"] = to_state
            entry["shifts"][rule_id] = used + 1
            record = AdaptationAudit(
                task_id=task_id, rule_id=rule_id, decision=DECISION_SHIFT,
                from_state=current, to_state=to_state, reason=reason,
                impact_cost=float(rule.get("impact_cost", impact_cost)), shift_index=used + 1,
                matched_event=event_type,
            )
            entry["audit"].append(record)
            return record
        return None
