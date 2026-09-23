"""AC-M3-5 判据：参与影响任务演进（数据驱动 + `max_shifts` 硬上限 + 审计 + 防刷）。

运行（**真跑，非 skip**）：
    cd <workspace>/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 \
        python3 -m pytest tests/test_task_adaptation.py -q -p no:cacheprovider

判据来源：REQ rev3 §4 AC-M3-5；任务书 §6 AC-M3-5；D-14（求值顺序裁决）。

RED 证据（隔离副本，见 spikes/s12-session/logs/）：本文件在「删除 `rules/adaptation.py`
（= 修复前形态）」的整树副本里**收集即失败**（`ModuleNotFoundError`）⇒ 判据有命中能力。
"""

from __future__ import annotations

import json
from pathlib import Path

from deephealing_kernel.events import EventLog
from deephealing_kernel.pack import load_pack
from deephealing_kernel.rules.adaptation import (
    DECISION_GUARD_NO_OP,
    DECISION_MAX_SHIFTS_REACHED,
    DECISION_SHIFT,
    TaskAdaptationEngine,
    order_rules,
    rule_is_guard,
)
from deephealing_kernel.tick import WorldKernel

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SEED = 20260921

# ---------------------------------------------------------------------------- 基线口径
# **M4 判据变更登记（AC-M4-8⑥，必须写进 06 与 V0_SELF_TEST.md）**
# 决策路径由 M1 班表桩（`stub_decide`）切换为「需求 → 效用 → 行为树」（`rules/decision.py`）
# ⇒ `state_hash` / `chain_tail` **必然**改变。这是**预期**，不是回归。
# 旧硬断言（「必须等于旧基线值」）已按 REQ 要求改写为「**确定性自洽**」口径：
#   ① 同 seed 同 tick 数**两次独立运行**逐位相同；
#   ② 无 intent 时 `task.state_changed` / `intent.applied` 计数为 0；
#   ③ 新基线（本轮产出，已登记）作为**回归锚**。
# 历史值（M1/M2 口径，仅存档，**不再作断言**）：
#   M1M2_BASELINE_STATE_HASH_300 = "9a4ae3da0d7cc3f8556d07ae773b8579d80f55a5cf6d4a0fc5594f5d7a66625f"
#   M1M2_BASELINE_CHAIN_TAIL     = "baecca9219a9bbabfc0e46349834438cc0c61ba44fd6315aeda26fb65acfd786"
# 本轮（M4）新基线：seed 20260921 / 300 tick / pack districts/xingfu-xiaoqu
#   变更时刻：epoch 1790130629（2026-09-23 10:30:29 +08:00）
# ---- M5.2 r1 **重登记**（Raven M-1：只允许改这两个常量）------------------------------------
# 旧值（M4 口径，**仅存档，不再作断言**）：
#   M4_BASELINE_STATE_HASH_300 = "0d79e5f349cad67d8ebc623fb7e49a17082e0170d0b5a5c3de62715ea42a2dca"
#   M4_BASELINE_CHAIN_TAIL     = "81669e9685e5dec845d0d5060321c0eba66939063997941c5be5f2e0d97d8cb6"
# 变更原因：M5.2 r1 的三处内核改动（C1 `rest` 同时缓解 `safety` / C2 `explore` 候选移除 `home` /
#   C3 日程边界块）+ 关系（友善度）运行时演进 **改变了行为** ⇒ 属 AC-M4-8⑥ **允许的基线数值漂移**
#   （**不是机制回退**：确定性机制由本测试自身的两条自证独立钉住 —— ① 两次独立运行逐位一致；
#    ③ 换 seed ⇒ 基线必须改变）。
# 独立读数（`/tmp/m52-tools/baseline_hashes.py`，同一命令跑两棵树）：
#   交付树: state_hash=8603dedb… chain_tail=c79003ce… two_runs_bit_identical=true seed_change_alters=true
#   对照树(/tmp/m52-ref, 改前): state_hash=0d79e5f3… chain_tail=81669e96… ⇒ **与旧登记常量逐位相同**
#     ⇒ 旧常量确实来自改前树，漂移可归因于本轮改动。
# 变更时刻：epoch 1790180400 前后（2026-09-24 00:40 +08:00）
M4_BASELINE_STATE_HASH_300 = "8603dedb8cdb4a1799c80c8061c2e056025164a0cf16272a39020a442774c15c"
M4_BASELINE_CHAIN_TAIL = "c79003ce8ef38959ad09270ec20a1206d909cebb45c54d0b27c2b9b2070d8174"


def _kernel(tmp_path: Path, *, snapshot_every: int = 0) -> tuple[object, WorldKernel, EventLog]:
    pack = load_pack(PACK_DIR)
    log = EventLog(tmp_path / "events.jsonl")
    kernel = WorldKernel(
        pack=pack,
        seed=SEED,
        log=log,
        snapshot_every=snapshot_every,
        checkpoint_dir=(tmp_path / "checkpoints") if snapshot_every else None,
    )
    return pack, kernel, log


def _delegate(intent_id: str, target: str = "npc-001", cost: float = 3.0) -> dict:
    return {
        "id": intent_id,
        "session_id": "sess_test01",
        "kind": "delegate_instruction",
        "target": target,
        "impact_cost": cost,
    }


def _types(log: EventLog) -> list[str]:
    return [event.type for event in log.read_all()]


def _events(log: EventLog, event_type: str) -> list:
    return [event for event in log.read_all() if event.type == event_type]


# ---------------------------------------------------------------------------- 1. 数据驱动
def test_adaptation_rules_come_from_pack_data_and_guards_are_ordered_first():
    """规则集与状态集**全部**来自内容包 `tasks/*.json`（无 `if task_id` 分支）。"""
    pack = load_pack(PACK_DIR)
    task = next(item for item in pack.tasks if item["id"] == "task-001")
    rule_ids = [rule["id"] for rule in task["adaptation_rules"]]
    assert rule_ids == ["rule-001-warmth", "rule-001-repetition-guard"]
    warmth = next(rule for rule in task["adaptation_rules"] if rule["id"] == "rule-001-warmth")
    assert warmth["max_shifts"] == 2 and warmth["effect"]["shift_to"] == "offered"

    engine = TaskAdaptationEngine(pack.tasks)
    assert engine.task_ids() == ["task-001", "task-002"]
    assert engine.state_of("task-001") == task["initial_state"] == "dormant"

    ordered = order_rules(task["adaptation_rules"])
    assert [rule["id"] for rule in ordered] == ["rule-001-repetition-guard", "rule-001-warmth"]
    assert rule_is_guard(ordered[0]) and not rule_is_guard(ordered[1])


# ---------------------------------------------------------------------------- 2. tick 边界
def test_participate_intent_shifts_task_state_only_at_tick_boundary(tmp_path):
    """入队 ⇒ 未推进 tick 前**零事件、零状态变更**；推进到 tick 边界才应用。"""
    _, kernel, log = _kernel(tmp_path)
    ack = kernel.submit_intent(_delegate("i-1"))
    assert ack["status"] == "queued"
    assert kernel.pending_intent_count() == 1
    assert kernel.adaptation.state_of("task-001") == "dormant"
    assert _types(log) == ["world.init"]  # 入队本身不落 intent.applied

    kernel.step()
    assert kernel.pending_intent_count() == 0
    applied = _events(log, "intent.applied")
    changed = _events(log, "task.state_changed")
    assert len(applied) == 1 and applied[0].tick == 1
    assert applied[0].actor == "session:sess_test01"
    assert applied[0].payload["applied_tick"] == 1
    assert applied[0].payload["impact_cost"] == 3.0
    assert len(changed) == 1
    payload = changed[0].payload
    assert (payload["task_id"], payload["from_state"], payload["to_state"]) == (
        "task-001", "dormant", "offered",
    )
    assert payload["rule_id"] == "rule-001-warmth"
    assert payload["shift_index"] == 1
    assert payload["caused_by"] == "i-1"
    assert payload["impact_cost"] == 3.0  # 审计记录：与预算联动
    assert kernel.adaptation.state_of("task-001") == "offered"
    audit = kernel.adaptation.audit_log()
    assert audit and audit[0]["decision"] == DECISION_SHIFT and audit[0]["rule_id"] == "rule-001-warmth"


# ---------------------------------------------------------------------------- 3. 防刷（D-14）
def test_repetition_guard_short_circuits_second_intent_on_same_target(tmp_path):
    """D-14 的机器判据：同目标**连续两次** `delegate_instruction` ⇒ 第二次**不得**产生
    `task.state_changed`（守卫规则 `rule-001-repetition-guard` 的 `repeat_within_ticks` 命中即短路）。"""
    _, kernel, log = _kernel(tmp_path)
    kernel.submit_intent(_delegate("i-1"))
    kernel.step()
    kernel.submit_intent(_delegate("i-2"))
    kernel.step()

    assert len(_events(log, "intent.applied")) == 2
    changed = _events(log, "task.state_changed")
    assert len(changed) == 1, "第二次同目标介入必须被守卫短路（不得产生 task.state_changed）"
    assert changed[0].payload["caused_by"] == "i-1"

    decisions = [record["decision"] for record in kernel.adaptation.audit_log()]
    assert decisions == [DECISION_SHIFT, DECISION_GUARD_NO_OP]
    assert kernel.adaptation.state_of("task-001") == "offered"


def test_repetition_guard_expires_outside_repeat_window(tmp_path):
    """`repeat_within_ticks` 是**窗口**而非永久封禁：窗口外守卫不再命中。"""
    _, kernel, log = _kernel(tmp_path)
    kernel.submit_intent(_delegate("i-1"))
    kernel.step()
    for _ in range(301):  # 推进到窗口之外（> 300 tick）
        kernel.step()
    kernel.submit_intent(_delegate("i-2"))
    kernel.step()
    decisions = [record["decision"] for record in kernel.adaptation.audit_log()]
    assert DECISION_GUARD_NO_OP not in decisions[1:]
    # 状态已是 offered ⇒ 窗口外重放 warmth 规则为「无变化」，仍**不**产生新事件
    assert len(_events(log, "task.state_changed")) == 1


# ---------------------------------------------------------------------------- 4. max_shifts 硬上限
def test_max_shifts_is_a_hard_cap(tmp_path):
    """`max_shifts` 是**硬上限**：达到上限后该规则不再产出迁移。

    用**测试自带的数据文档**驱动（数据驱动、非代码分支）：A 规则 `max_shifts:2` 迁移 s0→s1，
    B 规则把状态重置回 s0 ⇒ 第三次 A 命中时必须被 `max_shifts` 拦住。
    """
    document = {
        "id": "task-synthetic",
        "initial_state": "s0",
        "states": ["s0", "s1"],
        "adaptation_rules": [
            {
                "id": "rule-a",
                "match": {"event_type": "intent.applied", "kind": "delegate_instruction", "target": "npc-001"},
                "effect": {"shift_to": "s1", "reason": "合成：推进"},
                "max_shifts": 2,
                "impact_cost": 1.5,
            },
            {
                "id": "rule-b",
                "match": {"event_type": "intent.applied", "kind": "delegate_instruction", "target": "npc-003"},
                "effect": {"shift_to": "s0", "reason": "合成：重置"},
                "max_shifts": 9,
                "impact_cost": 0.0,
            },
        ],
    }
    engine = TaskAdaptationEngine([document])

    def fire(target: str, tick: int) -> list:
        engine.note_intent_applied(target=target, tick=tick)
        return engine.evaluate(event_type="intent.applied", kind="delegate_instruction",
                               target=target, tick=tick)

    shifts = []
    for index, target in enumerate(["npc-001", "npc-003", "npc-001", "npc-003", "npc-001"]):
        for audit in fire(target, index + 1):
            if audit.rule_id == "rule-a" and audit.is_shift:
                shifts.append(audit)
    assert len(shifts) == 2, f"rule-a 的迁移次数必须被 max_shifts=2 钉住，实测 {len(shifts)}"
    assert [audit.shift_index for audit in shifts] == [1, 2]
    assert engine.state_of("task-synthetic") == "s0"
    last = engine.audit_log()[-1]
    assert last["decision"] == DECISION_MAX_SHIFTS_REACHED and last["rule_id"] == "rule-a"


# ---------------------------------------------------------------------------- 5. 无 intent 基线
def test_default_run_without_intents_is_bit_identical(tmp_path):
    """AC-M3-5 末条 / AC-M3-6 + **M4 口径改写**：无 intent 的默认跑必须
    「**确定性自洽**」（两次独立运行逐位相同）且与**本轮新基线**一致。

    判据变更登记见文件头：旧值（`9a4ae3da…` / `baecca92…`）**不再作断言**，
    只作为历史存档；本轮新基线由 M4 产出并登记。
    """
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    results = []
    for out_dir in (first_dir, second_dir):
        _, kernel, log = _kernel(out_dir, snapshot_every=50)
        kernel.run(300)
        checkpoints = sorted((out_dir / "checkpoints").glob("*.json"))
        assert [path.name for path in checkpoints] == [
            "000050.json", "000100.json", "000150.json", "000200.json", "000250.json", "000300.json",
        ]
        last = json.loads(checkpoints[-1].read_text(encoding="utf-8"))
        assert last["tick"] == 300
        assert _types(log).count("task.state_changed") == 0
        assert _types(log).count("intent.applied") == 0
        results.append((last["state_hash"], log.last_hash))

    # ① 确定性自洽：两次独立运行逐位相同（判据**机制**，与基线数值无关）
    assert results[0][0] == results[1][0], f"两次运行的 state_hash 不一致：{results}"
    assert results[0][1] == results[1][1], f"两次运行的 chain_tail 不一致：{results}"
    # ② 本轮新基线（M4 产出，已登记）作为回归锚
    assert results[0][0] == M4_BASELINE_STATE_HASH_300, (
        f"M4 基线漂移：state_hash {results[0][0]} != 登记的 {M4_BASELINE_STATE_HASH_300}")
    assert results[0][1] == M4_BASELINE_CHAIN_TAIL, (
        f"M4 基线漂移：chain_tail {results[0][1]} != 登记的 {M4_BASELINE_CHAIN_TAIL}")
    # ③ 反例（自证）：换 seed ⇒ 基线必须改变（否则②是恒真判据）
    other_dir = tmp_path / "other"
    other_log = EventLog(other_dir / "events.jsonl")
    other = WorldKernel(pack=load_pack(PACK_DIR), seed=SEED + 1, log=other_log,
                        snapshot_every=50, checkpoint_dir=other_dir / "checkpoints")
    other.run(300)
    assert (other.state_hash(), other_log.last_hash) != results[0], (
        "换 seed 后基线必须改变 ⇒ 证明②不是恒真判据")
