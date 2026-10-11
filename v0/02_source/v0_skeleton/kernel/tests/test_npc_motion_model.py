"""REQ-20261011-015 · 目的地承诺层（W1~W3）的**条件性**不变式（新增文件，不改任何既有测试）。

为什么需要这个文件：预审 **C-3** 指出，冻结判据 `test_behaviour_is_distinguishable_by_need_state`
只复算「动作 / 分数 / 分支 / 需求 / 日程态」，**从不读 `target_entity`** ⇒ 它对「去向被班表接管」
**零判别力**。本文件把这件事变成**可判的**，两条：

① **承诺层是条件性的**（不是无条件接管）：
   - 正向：`branch != "flee"` 且该 tick 的日程块**声明了** `target_entity` 且承诺层没有走 `peer`
     例外时 ⇒ `decision.target_entity` **必须**等于该 tick 的块目标；
   - 存在性：**必须存在** tick 使 `target_entity != 块目标`，且这些 tick **全部**落在例外面
     （`branch == "flee"` / `target_source == "peer"` / 该 tick 的块没有 `target_entity`）。
② **动作面与去向面解耦**：**必须存在** tick 使 `target_entity == 块目标` 而
   `chosen_action != 该日程态的规定动作`（`CANDIDATE_ACTIONS[state][0][0]`，数据表口径）
   ⇒ 证明「去哪 = 班表、做什么 = 需求/效用」。

块对齐口径 = **内核实效推进**（`world.seed.json` 的 `schedule.until_tick=60` ⇒ 首块实际只跑 60 tick），
用内核自己的 `rules.decision._next_block` 复算，不另立一份语义（预审 M-5）。
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu-xuqin"
TICKS = 960  # 覆盖到 tick 895~905 的 `pressure_window`（`flee` 例外面）
sys.path.insert(0, str(KERNEL_ROOT))

from deephealing_kernel.events import EventLog  # noqa: E402
from deephealing_kernel.pack import load_pack  # noqa: E402
from deephealing_kernel.rules import decision as decision_mod  # noqa: E402
from deephealing_kernel.tick import WorldKernel  # noqa: E402


def _run_and_collect(tmp_path: Path) -> tuple[list[dict], dict[int, tuple], str]:
    """跑主 pack（xuqin，1 NPC）⇒ （npc.decision 事件列表, {tick: (state, block_target)}, npc_id）。"""
    pack = load_pack(PACK_DIR)
    kernel = WorldKernel(pack=pack, seed=int(pack.world_seed["seed"]),
                         log=EventLog(tmp_path / "events.jsonl"),
                         snapshot_every=0, checkpoint_dir=None)
    npc_ids = [entity.id for entity in kernel.world.query(kind="npc")]
    assert npc_ids, "取证 pack 必须至少有一个 NPC"
    npc_id = npc_ids[0]
    schedule = copy.deepcopy((kernel.world.get(npc_id).components or {}).get("schedule") or {})
    blocks = kernel.world.schedule_index.get(npc_id, [])
    day_ticks = int(kernel.world.constants.get("day_ticks") or 1440)

    # 内核实效块时间线：与 `decide()` 的推进口径逐字一致（复用内核自己的 `_next_block`）
    timeline: dict[int, tuple] = {}
    for tick in range(1, TICKS + 1):
        until_tick = schedule.get("until_tick")
        if until_tick is not None and tick >= int(until_tick):
            advanced = decision_mod._next_block(blocks, int(until_tick))
            if advanced is not None:
                schedule["entry_id"] = advanced.get("entry_id", schedule.get("entry_id"))
                schedule["state"] = advanced["state"]
                schedule["target_entity"] = advanced.get("target_entity")
                schedule["until_tick"] = int(advanced["end_tick"])
            else:
                schedule["until_tick"] = int(until_tick) + day_ticks
        timeline[tick] = (schedule.get("state"), schedule.get("target_entity"))

    kernel.run(TICKS)
    rows = []
    for event in kernel.log.read_all():
        if event.type != "npc.decision":
            continue
        rows.append({"tick": int(event.tick), **dict(event.payload)})
    assert rows, "事件流里没有 npc.decision ⇒ 本文件的判据失去判别力"
    return rows, timeline, npc_id


def _is_exception(payload: dict, block_target: object) -> bool:
    """例外面（承诺层**让路**的三种情形）——判据全部来自数据，无实体 id 特判。"""
    return (str(payload.get("bt_branch")) == "flee"
            or str(payload.get("target_source")) == "peer"
            or block_target is None)


def test_commitment_layer_is_conditional_not_unconditional(tmp_path):
    """① 承诺层**有条件**：非例外面必须等于块目标；且必须真的存在例外面。"""
    rows, timeline, npc_id = _run_and_collect(tmp_path)

    offenders: list[dict] = []
    divergent: list[dict] = []
    for row in rows:
        state, block_target = timeline[row["tick"]]
        if row["target_entity"] != block_target:
            divergent.append({**row, "block_target": block_target, "schedule_state_effective": state})
            if not _is_exception(row, block_target):
                offenders.append({**row, "block_target": block_target})

    assert not offenders, (
        f"承诺层在**非例外面**没有接管（{npc_id}，共 {len(offenders)} 个 tick）："
        f"{offenders[:5]}"
    )
    assert divergent, "承诺层成了**无条件**接管：不存在任何例外面（flee / peer / 块无目标）"
    for row in divergent:
        assert _is_exception(row, row["block_target"]), (
            f"例外面未覆盖 tick={row['tick']}：branch={row['bt_branch']} "
            f"target_source={row['target_source']} 块目标={row['block_target']}"
        )


def test_destination_axis_and_action_axis_are_decoupled(tmp_path):
    """② 去向 = 块目标、动作 = 需求/效用：存在「去向是块目标，动作不是该态规定动作」的 tick。"""
    rows, timeline, npc_id = _run_and_collect(tmp_path)

    decoupled: list[dict] = []
    at_block_target = 0
    for row in rows:
        state, block_target = timeline[row["tick"]]
        if block_target is None or row["target_entity"] != block_target:
            continue
        at_block_target += 1
        prescribed = decision_mod.CANDIDATE_ACTIONS.get(str(state), ())[0][0]
        if str(row["chosen_action"]) != prescribed:
            decoupled.append({"tick": row["tick"], "state": state, "block_target": block_target,
                              "chosen_action": row["chosen_action"], "prescribed": prescribed})

    assert at_block_target, "没有任何 tick 的去向等于块目标 ⇒ 承诺层未落地"
    assert decoupled, (
        f"去向面被班表接管的同时动作面也被接管（{npc_id}，{at_block_target} 个 tick 全部等于规定动作）"
        "⇒ 两轴未解耦"
    )
