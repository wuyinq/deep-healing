#!/usr/bin/env python3
"""AC-5 实机场景装配（spikes/** 脚手架，**非交付面**）。

职责：把**交付面的真内核 + 真内容包**装成一次可被浏览器观察的运行：
  - 按会话桥的同一口径把 `<02_source>` 复制到 `runtime/02_source`（导入副本 ⇒ 交付面零残渣）；
  - `EventLog` / `MemoryStore` / `WorldKernel` / **内核自带的 `LiveWorld`**（世界钟 / 状态投影
    与 `cli live` 完全同一实现，不自研、不重算）；
  - 逐 tick 输出与 `session/bridge/kernel_bridge.py` **同形的 JSONL 记录**
    （`tick_meta` / `snapshot` / `delta`），**并补上桥没有搬运的 `event` 记录**
    （逐行读内核真实事件日志，原样转发，不改写）。

为什么需要补 `event`：交付面的 `kernel_bridge.py` 虽然文档里声明 `kind` 含 `event`，
但**没有任何 emit 点**（`grep -n '"kind": "event"'` 零命中）⇒ 浏览器收不到内核事件，
REQ §4 AC-5 的「从事件记录追溯原因」在实机上没有数据源。r2 写集**不含** `session/**`
与 `kernel/**` ⇒ 本脚手架只做**只读转发**补齐该通道，并作为 GAP 登记。

**硬边界**：本文件只读交付面；所有运行产物落 `--runtime-dir`（spikes/m52-live/runtime/**）。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

GENERATED_NAMES = ("__pycache__", ".pytest_cache", ".DS_Store", "node_modules", ".venv", "dist", ".build")
EVENT_LAYER_NAMES = {"working": "working", "episodes": "episodic", "facts": "semantic"}


#: 逐 tick 记录是否写 stdout（探针模式关掉；驱动模式必须开）。
EMIT_ENABLED = True


def emit(record: dict) -> None:
    """把一条记录写到 stdout（与桥同一形态：JSONL、ensure_ascii=False、sort_keys）。"""
    if not EMIT_ENABLED:
        return
    sys.stdout.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    sys.stdout.flush()


def copy_source(source_root: Path, runtime_dir: Path) -> dict:
    """镜像 `kernel_bridge.py` 的副本布局：`<runtime>/02_source/**`（去掉生成残渣）。"""
    destination = runtime_dir / "02_source"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source_root, destination, ignore=shutil.ignore_patterns(*GENERATED_NAMES))
    files = sum(1 for path in destination.rglob("*") if path.is_file())
    return {"source_copy": str(destination), "source_files": files}


class Scenario:
    """一次运行场景（真内核 + 真内容包 + 内核自带 LiveWorld）。"""

    def __init__(self, *, source_root: Path, runtime_dir: Path, pack_name: str, seed: int,
                 snapshot_every: int, memory_writes: bool, plan_ticks: int = 100000) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.logs = self.runtime_dir / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.meta = copy_source(Path(source_root), self.runtime_dir)
        kernel_root = self.runtime_dir / "02_source" / "v0_skeleton" / "kernel"
        self.pack_dir = self.runtime_dir / "02_source" / "v0_skeleton" / "districts" / pack_name
        sys.path.insert(0, str(kernel_root))
        sys.dont_write_bytecode = True

        from deephealing_kernel import world_clock  # noqa: E402
        from deephealing_kernel.events import EventLog  # noqa: E402
        from deephealing_kernel.live import LiveWorld  # noqa: E402
        from deephealing_kernel.memory.store import MemoryStore  # noqa: E402
        from deephealing_kernel.pack import load_pack  # noqa: E402
        from deephealing_kernel.tick import WorldKernel  # noqa: E402

        self.pack = load_pack(self.pack_dir)
        self.event_path = self.logs / "kernel-events.jsonl"
        self.log = EventLog(self.event_path)
        self.memory_path = self.logs / "memory.sqlite"
        self.store = MemoryStore(self.memory_path, write_enabled=bool(memory_writes))
        self.store.init_schema()
        self.kernel = WorldKernel(
            pack=self.pack, seed=int(seed), log=self.log, snapshot_every=int(snapshot_every),
            checkpoint_dir=self.logs / "checkpoints", plan_ticks=int(plan_ticks),
            memory_store=self.store,
        )
        self.world = LiveWorld(self.kernel, sem=world_clock.derive_clock_semantics(self.pack),
                               pace_s_per_tick=1.0, warmup=0, max_observers=4)
        self.memory_writes = bool(memory_writes)
        self._offset = 0

    # ------------------------------------------------------------------ 只读读数
    @property
    def npc_ids(self) -> list[str]:
        return sorted(entity.id for entity in self.kernel.world.query(kind="npc"))

    def projection(self) -> dict:
        return self.world.state_projection()

    def bridge_meta(self, *, pack_name: str, seed: int, snapshot_every: int) -> dict:
        return {
            "kind": "bridge_meta", "tick": 0, "seq": 0,
            "source_files": self.meta["source_files"], "source_copy": self.meta["source_copy"],
            "pack_copy": str(self.pack_dir), "seed": int(seed), "snapshot_every": int(snapshot_every),
            "memory_writes": self.memory_writes,
            "pack_id": str(self.pack.manifest.get("id") or self.pack_dir.name),
            "npc_ids": self.npc_ids,
            "scaffold": "spikes/m52-live/tools/live_scenario.py",
            "event_channel_supplied_by": "scaffold（交付面 kernel_bridge.py 无 event emit 点）",
        }

    # ------------------------------------------------------------------ 事件增量
    def drain_events(self) -> list[dict]:
        """读内核事件日志的**新增行**（原样转发，不改写）。"""
        if not self.event_path.exists():
            return []
        with self.event_path.open("r", encoding="utf-8") as handle:
            handle.seek(self._offset)
            lines = handle.readlines()
            self._offset = handle.tell()
        records: list[dict] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    # ------------------------------------------------------------------ 推进
    def step(self, n: int = 1) -> list[dict]:
        """推进 n 个 tick，返回期间新增的内核事件（原样）。"""
        for _ in range(max(0, int(n))):
            self.kernel.step()
            tick = int(self.kernel.world.tick)
            projection = self.world.state_projection()
            emit({"kind": "tick_meta", "tick": tick, "seq": 0, "ms": 0.0,
                  "state_hash": projection["state_hash"],
                  "event_chain_hash": projection["event_chain_hash"]})
            if int(self.kernel.snapshot_every) > 0 and tick % int(self.kernel.snapshot_every) == 0:
                emit({"kind": "snapshot", "tick": tick, "seq": 0, "state": projection["state"],
                      "state_hash": projection["state_hash"]})
            else:
                emit({"kind": "delta", "tick": tick, "seq": 0, "ops": [
                    {"op": "set", "entity": entity.id, "component": "transform",
                     "value": (entity.components.get("transform") or {})}
                    for entity in self.kernel.world.query(kind="npc")
                ]})
            emit({"kind": "live", "tick": tick, "seq": 0, "clock": projection["clock"],
                  "world_day": projection["world_day"], "timezone": projection["timezone"],
                  "state_hash": projection["state_hash"],
                  "event_chain_hash": projection["event_chain_hash"],
                  "observers": self.world.observers(), "state": projection["state"]})
            self.world.notify_subscribers(tick, projection["clock"])
        events = self.drain_events()
        for event in events:
            emit({"kind": "event", "tick": int(event.get("tick", 0)), "seq": 0, "event": event})
        return events

    # ------------------------------------------------------------------ 注入（唯一写库动作）
    def inject_episode(self, npc_id: str, tick: int, kind: str, importance: float,
                       refs: list[str], summary: str) -> int:
        """预置一条「关键经历」（AC-4 口径：注入 = 库里预置；本场景**唯一**的库写入口）。"""
        writer = self.store if self.store.write_enabled else None
        if writer is None:
            raise RuntimeError("inject_episode requires write_enabled memory store")
        return int(writer.append_episode(npc_id, int(tick), str(kind), str(summary),
                                        float(importance), list(refs)))

    def episode_row(self, npc_id: str, ref: int) -> dict | None:
        """读一条 episodes 记录（只读；注入前后各读一次，用于给「before/after」读数）。"""
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT npc_id, tick, kind, importance, refs FROM episodes WHERE npc_id=? AND ref=?",
                (str(npc_id), int(ref)),
            ).fetchone()
        return dict(row) if row is not None else None

    def promote_episode(self, npc_id: str, ref: int, importance: float,
                        extra_refs: list[str]) -> dict:
        """**库级提升**一条**内核自产**经历的权重（AC-4「预置关键经历」的等价注入形态）。

        为什么用「提升已有记录」而不是「新增记录」：`memory.written` 事件只覆盖**内核自产**记录；
        新增一条库外记录会让「记忆」节点在**事件流里没有对应事件**，因果链就断在事件侧。
        提升已有记录 ⇒ 链上四个节点**全部**是内核真实事件（事件 / 记忆 / 决策 / 行动）。

        **有意留下的注入痕迹（如实披露）**：该 `memory.written` 事件 payload 里的 `importance`
        是**写入时刻**的值（≈0.03~0.39），库内当前值被提升到 `importance`（0.95）——两者**不同**，
        正是「这条经历的权重是注入抬起来的」的可核验标记（`inject_result` 里给 before/after）。
        """
        if not self.store.write_enabled:
            raise RuntimeError("promote_episode requires write_enabled memory store")
        before = self.episode_row(npc_id, ref)
        if before is None:
            raise RuntimeError(f"promote_episode: no episode {npc_id}#{ref}")
        existing = json.loads(before.get("refs") or "[]")
        refs = sorted({str(item) for item in list(existing) + list(extra_refs)})
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE episodes SET importance=?, refs=? WHERE npc_id=? AND ref=?",
                (round(float(importance), 6), json.dumps(refs, ensure_ascii=False),
                 str(npc_id), int(ref)),
            )
            connection.commit()
        return {"before": before, "after": self.episode_row(npc_id, ref), "refs": refs}

    def stop(self) -> None:
        try:
            self.world.observers()
        except Exception:  # noqa: BLE001 — 收尾路径不因局部异常扩大影响
            pass
