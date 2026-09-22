"""固定步长 tick 循环与阶段顺序（V0-M1 实现，契约冻结）。

阶段顺序是**契约的一部分**（01 设计 §3.2）：[1] 输入 → [2] 感知 → [3] 规则层组合/能力调用
→ [4] 执行（唯一写点） → [5] 记账（事件追加） → [6] 快照。

硬约束（AC-2 判据的前提）：
  - dt = 100ms 固定，tick 率 10 Hz；
  - tick 内**禁止** wall-clock / time.time() / 线程完成顺序 / set|dict 迭代顺序 / 网络结果；
  - 异步能力结果只能在 tick 边界之外完成，于**下一 tick** 注入；迟到结果丢弃并记 metric。

M1 允许的最小运行时行为（设计 §3 第 90 行，属 W1/W2，**不属 W4**）：
  `decide` 阶段用**确定性桩系统**驱动 NPC（`decision_source="deterministic_stub"`），只做三件事：
    ① 日程 `until_tick` 边界推进（块取自内容包 schedules，**数据驱动**，无 `if npc_id` 分支）；
    ② 按整数毫米朝 `target_entity` 走一步（上限 `STEP_MM`，到点不越界）；
    ③ 从 `rng.stream("npc.<id>.move")` 取一个确定性整数抖动。
  **禁止**引入效用打分 / 行为树 / 预算 / 能力调用（那些是 W4/W3）。

意图协议（decide → execute 的唯一通道；`needs_delta` 供 W4 使用，M1 桩不产出）：
    {"npc_id", "action", "target_entity", "move_delta_mm", "jitter_mm",
     "needs_delta", "schedule", "moved", "schedule_changed"}
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .bus import KernelBus
from .ecs import Entity, World
from .events import EventLog
from .pack import DistrictPack
from .rng import WorldRng
from . import snapshot as snapshot_mod

PHASES = (
    "input",
    "perceive",
    "decide",
    "execute",
    "account",
    "snapshot",
)

STEP_MM = 500          # 每 tick 最大位移（整数毫米）
JITTER_MM = 100        # 抖动幅度（整数毫米，来自 rng.stream("npc.<id>.move")）
DEFAULT_PLAN_TICKS = 300


@dataclass(frozen=True, slots=True)
class TickContext:
    """一个 tick 内的只读上下文（由内核构造，阶段内不得修改）。"""

    tick: int
    dt_ms: int = 100


class TickObserver(Protocol):
    """观测层（L7）与传输层（L2）只订阅，不得写内核状态。"""

    def on_tick(self, ctx: TickContext) -> None: ...


def build_schedule_index(pack: DistrictPack | None) -> dict[str, list[dict]]:
    """`npc_id -> 日程块列表`（数据驱动：块全部来自内容包 `schedules/*.json`）。"""
    index: dict[str, list[dict]] = {}
    if pack is None:
        return index
    for schedule in pack.schedules:
        for entry_key in sorted(schedule.get("entries", {})):
            entry = schedule["entries"][entry_key]
            npc_id = entry.get("npc_id")
            if not npc_id:
                continue
            blocks = []
            for block in entry.get("blocks", []):
                item = dict(block)
                item["entry_id"] = entry_key
                blocks.append(item)
            index[npc_id] = blocks
    return index


def _next_block(blocks: list[dict], current_until_tick: int) -> dict | None:
    """取「start_tick 严格大于当前 until_tick」中最小的一块（无则 None）。顺序由数据决定，非代码分支。"""
    candidates = [block for block in blocks if int(block.get("start_tick", 0)) > current_until_tick]
    if not candidates:
        return None
    return min(candidates, key=lambda block: (int(block["start_tick"]), str(block.get("state", ""))))


def _step_towards(entity: Entity, target: Entity, rng: WorldRng) -> tuple[dict, int]:
    """朝 target_entity 走一步（整数毫米）+ 从该 NPC 自己的 stream 取确定性抖动。"""
    source = (entity.components.get("transform") or {}).get("pos_mm") or {}
    destination = (target.components.get("transform") or {}).get("pos_mm") or {}
    delta = {axis: int(destination.get(axis, 0)) - int(source.get(axis, 0)) for axis in ("x", "y", "z")}
    if not any(delta.values()):
        return {"x": 0, "y": 0, "z": 0}, 0
    step: dict[str, int] = {}
    for axis in ("x", "y", "z"):
        distance = delta[axis]
        if distance == 0:
            step[axis] = 0
        else:
            magnitude = min(abs(distance), STEP_MM)
            step[axis] = magnitude if distance > 0 else -magnitude
    stream = rng.stream(f"npc.{entity.id}.move")
    jitter = int(stream.next_u64() % (2 * JITTER_MM + 1)) - JITTER_MM
    return step, jitter


def stub_decide(world: World, rng: WorldRng, tick: int, ctx: TickContext) -> list[dict]:
    """确定性桩决策系统（M1）。遍历 `world.query(kind="npc")`（已按 id 升序）。"""
    intents: list[dict] = []
    day_ticks = int(world.constants.get("day_ticks", 1440))
    for entity in world.query(kind="npc"):
        schedule = copy.deepcopy(entity.components.get("schedule") or {})
        schedule_changed = False

        # ① 日程 until_tick 边界推进
        until_tick = schedule.get("until_tick")
        if until_tick is not None and tick >= int(until_tick):
            blocks = world.schedule_index.get(entity.id, [])
            advanced = _next_block(blocks, int(until_tick))
            if advanced is not None:
                schedule["entry_id"] = advanced.get("entry_id", schedule.get("entry_id"))
                schedule["state"] = advanced["state"]
                schedule["target_entity"] = advanced.get("target_entity")
                schedule["until_tick"] = int(advanced["end_tick"])
            else:
                # 日程表走完：推到下一个世界日（确定性回绕，不崩、不新增状态类型）
                schedule["until_tick"] = int(until_tick) + day_ticks
            schedule_changed = True

        # ② 朝 target_entity 走一步 + 确定性抖动
        target_entity = schedule.get("target_entity")
        move_delta = {"x": 0, "y": 0, "z": 0}
        jitter = 0
        if target_entity:
            target = world.get(target_entity)
            if target is not None:
                move_delta, jitter = _step_towards(entity, target, rng)
        moved = any(move_delta.values()) or jitter != 0

        intents.append({
            "npc_id": entity.id,
            "action": "move" if moved else "hold",
            "target_entity": target_entity,
            "move_delta_mm": move_delta,
            "jitter_mm": jitter,
            "needs_delta": None,
            "schedule": schedule if schedule_changed else None,
            "moved": moved,
            "schedule_changed": schedule_changed,
        })
    return intents


class WorldKernel:
    """世界内核（唯一权威）。

    构造参数全部可选，但 `run`/`replay`/`verify` 都会显式传入 pack 与 seed。
    """

    def __init__(
        self,
        pack: DistrictPack | None = None,
        seed: int | None = None,
        log: EventLog | None = None,
        snapshot_every: int | None = None,
        checkpoint_dir: Path | None = None,
        bus: KernelBus | None = None,
        tick_rate: int = 10,
        plan_ticks: int = DEFAULT_PLAN_TICKS,
    ) -> None:
        world_seed = pack.world_seed if pack is not None else {}
        constants = world_seed.get("constants", {})
        self.pack = pack
        self.seed = int(seed if seed is not None else world_seed.get("seed", 0))
        self.log = log
        self.tick_rate = int(tick_rate)
        self.plan_ticks = int(plan_ticks)
        self.snapshot_every = int(
            snapshot_every if snapshot_every is not None else constants.get("snapshot_every_ticks", 50)
        )
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir is not None else None
        self.bus = bus if bus is not None else KernelBus()
        self.rng = WorldRng(self.seed)
        self.world = World(seed=self.seed, constants=constants)
        self.world.schedule_index = build_schedule_index(pack)
        self.ticks_done = 0
        self.last_snapshot: snapshot_mod.Snapshot | None = None
        if pack is not None:
            self._load_seed_entities(pack)
            self._emit_world_init(pack)

    # ------------------------------------------------------------------ 初始化
    def _load_seed_entities(self, pack: DistrictPack) -> None:
        for document in pack.world_seed["entities"]:
            item = copy.deepcopy(document)
            entity_id = item.pop("id")
            kind = item.pop("kind")
            self.world.spawn(Entity(id=entity_id, kind=kind, components=item))

    def _emit_world_init(self, pack: DistrictPack) -> None:
        if self.log is None:
            return
        self.log.append(0, "world.init", "world", {
            "pack_id": pack.manifest["id"],
            "pack_version": pack.manifest["version"],
            "seed": self.seed,
            "entity_count": len(self.world.query()),
            "constants_digest": snapshot_mod.hash_object(pack.world_seed["constants"]),
            # 附加字段（events.schema.json 允许）：plan_ticks 供 verify 检朴素截断；
            # snapshot_every 记**生效值**（预审 L6：verify 一律以记录值为准）
            "plan_ticks": self.plan_ticks,
            "snapshot_every": self.snapshot_every,
        })

    # ------------------------------------------------------------------ tick
    def step(self) -> None:
        """推进一个 tick（阶段顺序 = PHASES，不可交换）。"""
        next_tick = self.world.tick + 1
        ctx = TickContext(tick=next_tick, dt_ms=int(self.world.constants.get("dt_ms", 100)))

        # [1] 输入：tick 边界注入已完成的能力结果（M1 无能力调用 ⇒ 空队列）
        inbound: list[dict] = []
        # [2] 感知：构造确定性感知视图（M1 无外部输入 ⇒ 仅 tick 与实体计数）
        perception = {"tick": ctx.tick, "entity_count": len(self.world.query())}
        self.bus.publish("metrics", {"perception": perception, "inbound": len(inbound)})

        # [3] 决策（确定性桩）
        intents = stub_decide(self.world, self.rng, ctx.tick, ctx)
        self.world.stage_intents(intents)

        # [4] 执行（**唯一写点**）
        self.world.tick = ctx.tick
        for system in self.world.systems():
            system(self.world)

        # [5] 记账
        if self.log is not None:
            for intent in intents:
                if not (intent["moved"] or intent["schedule_changed"]):
                    continue
                self.log.append(ctx.tick, "npc.action", intent["npc_id"], {
                    "npc_id": intent["npc_id"],
                    "action": intent["action"],
                    "decision_source": "deterministic_stub",
                    "target_entity": intent["target_entity"],
                    "duration_ticks": 1,
                })
        self.bus.publish("ticks", {"tick": ctx.tick, "dt_ms": ctx.dt_ms})

        # [6] 快照（每 snapshot_every 个 tick）
        if self.snapshot_every > 0 and ctx.tick % self.snapshot_every == 0:
            self._take_and_write_checkpoint()
        self.ticks_done += 1

    def _take_and_write_checkpoint(self) -> snapshot_mod.Snapshot:
        """写入顺序**冻结**：先 `append(snapshot.taken)` → 再取链尾写检查点（INVARIANT-ECH-1）。"""
        tick = self.world.tick
        state = self.world.to_state()
        rng_digests = self.rng.digests()
        rng_state_digest = snapshot_mod.hash_object(rng_digests)
        state_digest = snapshot_mod.hash_object(state)
        # `checkpoint_path` = 该 tick 检查点的**实际写入路径**，以**事件日志所在目录**为基准的相对路径
        # （修复轮 C9 / 预审 R13）。语义（本轮钉死）：
        #   - `run` 与 `replay` 都把检查点写在**各自日志目录**下的 `checkpoints/`（`cli` 侧保证）
        #     ⇒ 该字段在两侧产物里都指向**真实存在**的文件；
        #   - 它**不含目录** ⇒ run / replay / verify 三条路径的链尾逐 tick 一致
        #     （修复轮 A1 的事件流比对依赖这一点：若写成绝对路径，同一条日志换个目录就会假红）。
        checkpoint_path = f"checkpoints/{tick:06d}.json"
        if self.log is not None:
            self.log.append(tick, "snapshot.taken", "kernel", {
                "snapshot_tick": tick,
                "state_hash": state_digest,
                # ECH-2：**事件 payload** 的 event_chain_hash = 该事件之前的链尾（= 本事件的 prev_hash）
                "event_chain_hash": self.log.last_hash,
                "rng_state_digest": rng_state_digest,
                # ECH-3：payload.rng_digests 是 state_digest() 输入的规范序列化
                "rng_digests": rng_digests,
                "checkpoint_path": checkpoint_path,
            })
        chain_tail = self.log.last_hash if self.log is not None else snapshot_mod.GENESIS_HASH
        snapshot = snapshot_mod.take_snapshot(state, tick, chain_tail, rng_state_digest)
        self.last_snapshot = snapshot
        if self.checkpoint_dir is not None:
            path = snapshot_mod.write_checkpoint(snapshot, self.checkpoint_dir)
            self.bus.publish("snapshots", {"tick": tick, "path": str(path)})
        return snapshot

    def snapshot(self) -> dict:
        """返回当前快照（须通过 snapshot.schema.json）。"""
        state = self.world.to_state()
        return {
            "tick": self.world.tick,
            "state": state,
            "state_hash": snapshot_mod.hash_object(state),
            "event_chain_hash": self.log.last_hash if self.log is not None else snapshot_mod.GENESIS_HASH,
            "rng_state_digest": snapshot_mod.hash_object(self.rng.digests()),
        }

    def state_hash(self) -> str:
        """sha256(canonical_json(state))。"""
        return snapshot_mod.hash_object(self.world.to_state())

    def run(self, ticks: int) -> None:
        """连续推进 ticks 个 tick（每 tick 边界注入已完成的能力结果）。"""
        for _ in range(int(ticks)):
            self.step()
