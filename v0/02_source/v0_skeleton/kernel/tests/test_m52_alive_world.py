"""M5.2 r1 · 「让世界先活起来」三处内核改动（C1/C2/C3）的独立单测。

依据：`/Users/wooyinq/.hermes/profiles/lanova/pm_business/REQ-20260923-002-...md` §2
+ `.pm_ruling-m5-10-m52-scope-and-verified-changes.md` §二（**三处已验证候选改动**）
+ `01_architecture_design.md` §5.1（冻结接口）/ §11（v2 修订节）。

三处都在 `rules/decision.py`，逐条：
  - **C1** `_needs_delta()`：`rest`（回家休息）**同时**缓解 `safety`（家 = 安全）。
    原实现 `safety` **只由 `flee` 缓解** ⇒ 长期主导（实测 97.54% 决策 dominant_need=safety）。
  - **C2** `_resolve_target()`：`explore` 候选**移除 `home`**。
    原实现把 `home` 塞进候选并取「最近」⇒「探索」= 待在家。
  - **C3** `_next_block()`：日程推进用**包含当前 tick 的块**。
    原 `start_tick > until_tick`（严格大于）**跳过边界块**。

本文件对**未改动内核**必须**全红**（改前 RED），改动后**全绿**（改后 GREEN）；
两次读数都记在 `03_artisan_self_test.log` 的 M5.2 段。
"""

from __future__ import annotations

import sys
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KERNEL_ROOT))

from deephealing_kernel.ecs import Entity, World  # noqa: E402
from deephealing_kernel.rules import decision as decision_mod  # noqa: E402

FLAT_NEEDS = {"physiology": 0.5, "safety": 0.5, "belonging": 0.5, "esteem": 0.5,
              "self_actualization": 0.5}


# ------------------------------------------------------------------ C1 · rest 缓解 safety
def test_c1_rest_also_relieves_safety():
    """C1：`_needs_delta("rest", needs)` 的返回字典**含 `safety` 键且值 < 0**。"""
    delta = decision_mod._needs_delta("rest", FLAT_NEEDS)
    assert delta is not None, "rest 对非空 needs 必须产出增量字典"
    assert "safety" in delta, "C1 未落地：rest 的增量字典里没有 safety 键"
    assert delta["safety"] < 0, (
        f"C1 未落地：rest 未缓解 safety（实测 delta['safety']={delta['safety']}，期望 < 0）"
    )


def test_c1_rest_still_relieves_physiology_and_others_still_buildup():
    """C1 的**不变式**：`rest` 仍缓解 `physiology`；未缓解的需求仍**累积**（不得顺手改成全缓解）。"""
    delta = decision_mod._needs_delta("rest", FLAT_NEEDS)
    assert delta["physiology"] < 0, "C1 副作用：rest 不再缓解 physiology"
    assert delta["esteem"] > 0 and delta["belonging"] > 0, (
        "C1 副作用：rest 不得缓解与它无关的需求（esteem/belonging 必须仍累积）"
    )


# ------------------------------------------------------------------ C2 · explore 候选不含 home
def _explore_world() -> tuple[World, Entity, dict]:
    """家（room-101）**比**街区门户更近 ⇒ 旧实现必选家，新实现必选非家候选。"""
    world = World(seed=1, constants={})
    world.spawn(Entity(id="room-101", kind="room", components={
        "transform": {"pos_mm": {"x": 0, "y": 0, "z": 0}}, "tags": ["home"]}))
    world.spawn(Entity(id="courtyard-01", kind="building", components={
        "transform": {"pos_mm": {"x": 40000, "y": 0, "z": 40000}}, "tags": ["courtyard"]}))
    npc = Entity(id="npc-001", kind="npc", components={
        "transform": {"pos_mm": {"x": 100, "y": 0, "z": 100}}})
    world.spawn(npc)
    profile = {"home_entity": "room-101"}
    return world, npc, profile


def test_c2_explore_never_targets_home_even_when_home_is_nearest():
    """C2：`explore` 的候选集**不含** `home_entity` ⇒ 即便家在最近处也不得选它。"""
    world, npc, profile = _explore_world()
    schedule = {"target_entity": None, "state": "moving"}
    target = decision_mod._resolve_target("walk", "explore", npc, world, profile, schedule)
    assert target != "room-101", (
        f"C2 未落地：explore 把「家」当成了候选（实测 target={target!r}，家=room-101）"
    )
    assert target == "courtyard-01", f"C2：explore 应落到非家候选 courtyard-01，实测 {target!r}"


def test_c2_restore_and_flee_still_target_home():
    """C2 的**不变式**：`restore` / `flee` 仍以家为目标（只动 explore 的候选集）。"""
    world, npc, profile = _explore_world()
    schedule = {"target_entity": None, "state": "resting"}
    assert decision_mod._resolve_target("rest", "restore", npc, world, profile, schedule) == "room-101"
    assert decision_mod._resolve_target("flee", "flee", npc, world, profile, schedule) == "room-101"


# ------------------------------------------------------------------ C3 · 边界块
BOUNDARY_BLOCKS = [
    {"start_tick": 0, "end_tick": 30, "state": "idle"},
    {"start_tick": 30, "end_tick": 60, "state": "working"},
    {"start_tick": 60, "end_tick": 90, "state": "resting"},
]


def test_c3_boundary_block_is_selected_not_skipped():
    """C3：`tick == until_tick` 时必须返回**包含当前 tick 的块**（start_tick == until_tick），
    而不是下一块。"""
    block = decision_mod._next_block(BOUNDARY_BLOCKS, 30)
    assert block is not None, "C3：边界块必须被选中，不得返回 None"
    assert block["state"] == "working", (
        f"C3 未落地：边界块被跳过（实测 state={block['state']!r}，期望 'working'）"
    )


def test_c3_interior_until_tick_still_advances_to_next_block():
    """C3 的**不变式**：块内部的 `until_tick`（如 15）仍推进到下一块，不得原地踏步。"""
    block = decision_mod._next_block(BOUNDARY_BLOCKS, 15)
    assert block is not None and block["state"] == "working", (
        f"C3 副作用：块内推进被破坏（实测 {block!r}）"
    )
