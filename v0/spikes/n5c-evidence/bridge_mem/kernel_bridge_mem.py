#!/usr/bin/env python3
"""会话层 ↔ 内核的**驱动桥**（M3 新增；D-2 / D-8）。

⚠️ **N5 阶段 C 的取证脚手架副本**（`v0/spikes/n5c-evidence/bridge_mem/kernel_bridge_mem.py`，
**不进交付面**）。相对冻结桥 `session/bridge/kernel_bridge.py` 的差别**只有加法**（见同目录
`bridge_mem.diff`，由 `diff -u` 生成，证明语义只增不改）：
  - 新增 `--out` / `--events` / `--checkpoint-dir`：run 产物（记忆库 / 事件日志 / 检查点）落
    **独立输出目录**，不写交付树；
  - 新增 `--memory-chain`：构造 `MemoryStore(<out>/kernel_memory.sqlite, write_enabled=True)` 并
    传入 `WorldKernel`（**交付面缺口上抛**：冻结桥零记忆接线 ⇒ C-2/C-3/C-4 在真链路上没有通路）；
  - 新增 `--capability-chain` / `--cassette-dir` / `--replay` / `--emotion-pressure-threshold`：
    经内核既有 capability 通道接情绪评估（**C-6 的注入点**：`--replay` 强制 cassette_replay +
    缺省 cassette ⇒ 必然失败）；
  - 新增只读命令 `{"cmd":"tasks"}`：回读**内核持有的任务状态机状态**（C-1 的「读 state，不读日志」）。

形态（冻结）：
  - 启动时把交付树的内核与 pack **复制**到运行目录（`--runtime-dir`），
    `sys.path.insert(0, <kernel-copy>)` 导入**副本** ⇒ 交付面（`02_source/**`）零残渣（P-8）；
  - stdin 读命令（JSON 行）：`{"cmd":"step","n":<int>}` / `{"cmd":"intent",...}` /
    `{"cmd":"void_intents","reason_code":..,"session_id":..}` / `{"cmd":"stop"}`；
    **权限口径（fail-closed，R2）**：`intent` 的 `mode` 必须**显式**给出 `"participate"` 才可写；
    缺失 / 非字符串 / 未知值 ⇒ 一律按只读侧处理，由内核落 `intent.rejected{E_MODE_READONLY}`。
    桥**不**为调用方补一个宽松的缺省值。
  - stdout 写 per-tick JSONL：`{"tick":..,"seq":..,"kind":"snapshot|delta|event|tick_meta|intent_ack",..}`；
  - **零状态自算**：不解释、不改写状态，只搬运；世界写点只有内核的 `step()`。

`--ws-port` 语义（M4 修订，D-M4-4/D-M4-14）：**默认 0 = 不监听**；桥**不提供服务** ——
内核实时只读观察通道由 `cli live`（默认 `--port 8899`）或 `run --ws-port <n>` 提供。
桥与内核之间的通道是 **stdio 管道**（等价双 fd），**无网络可达路径**。

用法：
    python3 kernel_bridge.py --kernel-src <kernel> --pack-src <pack> --runtime-dir <dir> \
        --seed 20260921 --snapshot-every 50 [--ticks 300]
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

GENERATED_NAMES = ("__pycache__", ".pytest_cache", ".DS_Store", "node_modules", ".venv", "dist", ".build")


def _build_chain_extras(args, *, out_dir: Path, pack) -> tuple[dict, dict]:
    """**[N5-C 加法]** 内核链的接线（与 `cli.py::_build_kernel_chain` 同口径，但走**脚手架**）：

    交付面唯一入口是 `cli.py` 的 `--memory-chain` / `--capability-chain`；桥不经过它 ⇒
    C-2/C-3/C-4 在「真会话链」上没有通路（D1 的 CRITICAL 处置）。本函数在**脚手架**里补上该接线：
    两个开关**全 off ⇒ `extra == {}`**（与冻结桥的 `WorldKernel(...)` 实参集合完全相同）。
    """
    extra: dict = {}
    state: dict = {"memory_chain": False, "capability_chain": False}
    if bool(getattr(args, "memory_chain", False)):
        from deephealing_kernel.memory.store import MemoryStore
        store_path = out_dir / "kernel_memory.sqlite"
        store = MemoryStore(store_path, write_enabled=True)
        store.init_schema()
        extra["memory_store"] = store
        state["memory_chain"] = True
        state["memory_store_path"] = str(store_path)
    if bool(getattr(args, "capability_chain", False)):
        from deephealing_kernel.budget import BudgetLedger
        from deephealing_kernel.cli import _build_cognition_registry, _capability_caps
        cassette_root = Path(args.cassette_dir) if getattr(args, "cassette_dir", None) \
            else out_dir / "kernel_capability" / "cassettes"
        registry, _store = _build_cognition_registry(
            out_dir, cassette_root=cassette_root, replay_mode=bool(getattr(args, "replay", False)))
        registry.discover()
        # **[N5-C 脚手架加法 / D3 的「桩 provider」注入面]**：把 `remote_api` 类的适配器换成**桩**
        # （`--stub-remote-api <importance>`）。为什么需要：交付面 emotion.appraise 的 provider 链
        # 按优先级路由到 `remote_api`（缺凭据 ⇒ 立即失败）⇒ 契约声明的 `on_error` 回退到
        # `deterministic_rule`，其 `importance` **上限实测 0.418**，而 `memory/decision.py` 的
        # `MEMORY_SIGNAL_MIN_IMPORTANCE = 0.5` ⇒ **经历对决策的影响在真链路上结构性失效**。
        # 桩 provider 只改「情绪输出」这一个输入，两臂同源 ⇒ 差异仍只来自经历（详见 03 日志）。
        if getattr(args, "stub_remote_api", None) is not None:
            from deephealing_kernel.registry import CapabilityError

            importance = float(args.stub_remote_api)

            class _StubRemoteApi:
                provider_class = "remote_api"

                def invoke(self, capability: dict, payload: dict, *, timeout_ms: int) -> dict:
                    if str(capability.get("id")) != "emotion.appraise":
                        raise CapabilityError("E_PROVIDER_UNRESOLVED", "stub only implements emotion.appraise")
                    return {"valence": 0.0, "arousal": 0.5, "mood_label": "calm", "importance": importance}

            registry.register_adapter("remote_api", _StubRemoteApi())
            state["stub_remote_api_importance"] = importance
        state["registry_validation_errors"] = registry.validate()
        per_tick_calls, daily_tokens = _capability_caps(
            [registry.capability(slot) for slot in registry.slots()])
        ledger = BudgetLedger(day_ticks=int(pack.world_seed["constants"].get("day_ticks", 1440)),
                              per_tick_calls=per_tick_calls, per_npc_daily_tokens=daily_tokens)
        extra["capability_registry"] = registry
        extra["budget_ledger"] = ledger
        state["capability_chain"] = True
        state["cassette_dir"] = str(cassette_root)
        state["replay_mode"] = bool(getattr(args, "replay", False))
        state["registry"] = registry
    if getattr(args, "emotion_pressure_threshold", None) is not None:
        extra["emotion_pressure_threshold"] = float(args.emotion_pressure_threshold)
        state["emotion_pressure_threshold"] = float(args.emotion_pressure_threshold)
    return extra, state


def _copy_tree(source: Path, destination: Path) -> int:
    """复制目录树（忽略生成残渣），返回复制文件数。"""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*GENERATED_NAMES))
    return sum(1 for path in destination.rglob("*") if path.is_file())


def _tree_digest(root: Path) -> str:
    """交付面指纹（逐文件 sha256 汇总；仅用于日志，不是判据）。"""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in GENERATED_NAMES for part in path.parts):
            continue
        if path.suffix == ".pyc":
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("utf-8"))
    return digest.hexdigest()


def emit(record: dict) -> None:
    sys.stdout.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DeepHealing kernel bridge (V0-M3)")
    parser.add_argument("--kernel-src", required=True)
    parser.add_argument("--pack-src", required=True)
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--snapshot-every", type=int, default=50)
    parser.add_argument("--ticks", type=int, default=300)
    # ---- N5-C 取证脚手架加法（默认值 = 与冻结桥逐字节等价的语义：全部 off）----
    parser.add_argument("--out", default=None,
                        help="[N5-C] run 产物目录（kernel_memory.sqlite / kernel-events.jsonl / checkpoints）；"
                             "缺省 = <runtime-dir>/logs（与冻结桥同语义）")
    parser.add_argument("--events", default=None, help="[N5-C] 事件日志文件名/路径；缺省 = <out>/kernel-events.jsonl")
    parser.add_argument("--checkpoint-dir", default=None, help="[N5-C] 检查点目录；缺省 = <out>/checkpoints")
    parser.add_argument("--memory-chain", action="store_true",
                        help="[N5-C/D1] 打开内核记忆链（MemoryStore(<out>/kernel_memory.sqlite)）")
    parser.add_argument("--capability-chain", action="store_true", help="[N5-C/D1] 打开能力链（capability_registry + budget_ledger）")
    parser.add_argument("--cassette-dir", default=None, help="[N5-C/D1] cassette 根（缺省 = <out>/kernel_capability/cassettes）")
    parser.add_argument("--replay", action="store_true", help="[N5-C/D3] 强制 cassette_replay + fail-closed（C-6 注入）")
    parser.add_argument("--emotion-pressure-threshold", type=float, default=None,
                        help="[N5-C/D3] 情绪评估的调用条件（数据参数；缺省 = WorldKernel 默认）")
    parser.add_argument("--stub-remote-api", type=float, default=None,
                        help="[N5-C/D3] 桩 provider：把 `remote_api` 类适配器换成返回固定 importance 的桩"
                             "（脚手架注入面；两臂同源 ⇒ 差异仍只来自经历）")
    parser.add_argument("--ws-port", type=int, default=0,
                        help="0（默认）= 桥不提供服务；内核实时只读通道由 `cli live` / `run --ws-port` 提供")
    args = parser.parse_args(argv)

    runtime = Path(args.runtime_dir).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    # **副本布局必须镜像交付树的相对结构**：内核以 `parents[2]` 定位
    # `<v0_skeleton>/tools/canonical_json.py`、以 `parents[3]` 定位 `<02_source>/district.pack.schema.json`。
    # ⇒ 复制整个 `02_source/`（去掉生成残渣），副本内核/pack 落在同一相对位置。
    kernel_src = Path(args.kernel_src).resolve()
    source_root = kernel_src.parent.parent          # <02_source>
    pack_src = Path(args.pack_src).resolve()
    source_copy = runtime / "02_source"
    kernel_copy = source_copy / "v0_skeleton" / "kernel"
    pack_copy = source_copy / "v0_skeleton" / "districts" / pack_src.name
    logs = runtime / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    # ---- N5-C 加法：run 产物目录（缺省 = logs ⇒ 与冻结桥**同语义**）----
    out_dir = Path(args.out).resolve() if args.out else logs
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = Path(args.events) if args.events else out_dir / "kernel-events.jsonl"
    if not events_path.is_absolute():
        events_path = out_dir / events_path
    checkpoint_dir = Path(args.checkpoint_dir) if args.checkpoint_dir else out_dir / "checkpoints"

    source_files = _copy_tree(source_root, source_copy)
    kernel_files = sum(1 for path in kernel_copy.rglob("*") if path.is_file())
    pack_files = sum(1 for path in pack_copy.rglob("*") if path.is_file())

    # **副本依赖**：导入的是副本，不是交付树（D-8 判据②）
    sys.path.insert(0, str(kernel_copy))
    from deephealing_kernel.events import EventLog  # noqa: E402
    from deephealing_kernel.pack import load_pack  # noqa: E402
    from deephealing_kernel.tick import WorldKernel  # noqa: E402
    import deephealing_kernel  # noqa: E402

    module_file = Path(deephealing_kernel.__file__).resolve()
    inside_copy = str(module_file).startswith(str(kernel_copy.resolve()))

    pack = load_pack(pack_copy)
    log = EventLog(events_path)
    chain_extra, chain_state = _build_chain_extras(args, out_dir=out_dir, pack=pack)
    kernel = WorldKernel(
        pack=pack, seed=args.seed, log=log,
        snapshot_every=args.snapshot_every,
        checkpoint_dir=checkpoint_dir,
        plan_ticks=args.ticks,
        **chain_extra,
    )

    seq = 0
    emit({
        "kind": "bridge_meta", "tick": 0, "seq": seq,
        "kernel_file": str(module_file),
        "kernel_inside_copy": bool(inside_copy),
        "kernel_copy": str(kernel_copy), "pack_copy": str(pack_copy),
        "source_files": source_files,
        "kernel_files": kernel_files, "pack_files": pack_files,
        "kernel_tree_digest": _tree_digest(kernel_copy),
        "ws_port": args.ws_port,
        "bridge_serves_network": False,
        "live_channel_provided_by": "cli live (default --port 8899) / run --ws-port <n>",
        "plan_ticks": args.ticks,
        "snapshot_every": args.snapshot_every,
        # ---- N5-C 加法（读数用；不改既有键的语义）----
        "out_dir": str(out_dir),
        "events_path": str(events_path),
        "checkpoint_dir": str(checkpoint_dir),
        "memory_chain": bool(chain_state.get("memory_chain")),
        "memory_store_path": chain_state.get("memory_store_path"),
        "capability_chain": bool(chain_state.get("capability_chain")),
        "cassette_dir": chain_state.get("cassette_dir"),
        "replay_mode": chain_state.get("replay_mode"),
        "emotion_pressure_threshold": chain_state.get("emotion_pressure_threshold"),
        "registry_validation_errors": chain_state.get("registry_validation_errors"),
        "stub_remote_api_importance": chain_state.get("stub_remote_api_importance"),
        "bridge_variant": "n5c-evidence-scaffold",
    })
    seq += 1

    state_hash_after = None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            command = json.loads(line)
        except json.JSONDecodeError as error:
            emit({"kind": "error", "tick": kernel.world.tick, "seq": seq,
                  "reason": "E_SCHEMA_INVALID", "detail": str(error)})
            seq += 1
            continue
        name = str(command.get("cmd", ""))
        if name == "intent":
            intent = copy.deepcopy(command.get("intent") or {})
            # **fail-closed**（R2 / M3-02）：桥的 stdin 是**第二个权限入口**，`mode` 必须由调用方
            # **显式**声明才可写。缺失 / 非字符串 ⇒ 落只读侧（`!= "participate"`），
            # 由内核入口落 `intent.rejected{E_MODE_READONLY}`。缺省值**不得**落在可写的一侧。
            raw_mode = command.get("mode")
            mode = raw_mode if isinstance(raw_mode, str) else ""
            ack = kernel.submit_intent(intent, mode=mode)
            emit({"kind": "intent_ack", "tick": kernel.world.tick, "seq": seq,
                  "id": ack.get("id"), "status": ack.get("status"),
                  "reason": ack.get("reason"), "detail": ack.get("detail"),
                  "impact_budget_remaining": command.get("impact_budget_remaining")})
            seq += 1
            continue
        if name == "step":
            count = int(command.get("n", 1))
            for _ in range(max(0, count)):
                before_tick = kernel.world.tick
                kernel.step()
                tick = kernel.world.tick
                snapshot = kernel.snapshot()
                emit({"kind": "tick_meta", "tick": tick, "seq": seq, "ms": 0.0,
                      "state_hash": snapshot["state_hash"],
                      "event_chain_hash": snapshot["event_chain_hash"]})
                seq += 1
                if args.snapshot_every > 0 and tick % args.snapshot_every == 0:
                    emit({"kind": "snapshot", "tick": tick, "seq": seq,
                          "state": snapshot["state"], "state_hash": snapshot["state_hash"]})
                    seq += 1
                else:
                    emit({"kind": "delta", "tick": tick, "seq": seq, "ops": [
                        {"op": "set", "entity": entity.id, "component": "transform",
                         "value": (entity.components.get("transform") or {})}
                        for entity in kernel.world.query(kind="npc")
                    ]})
                    seq += 1
                if before_tick >= 0:
                    pass
            state_hash_after = kernel.state_hash()
            continue
        if name == "void_intents":
            # 会话层预算耗尽降级：作废内核侧待应用意图（逐条落 intent.rejected，禁止静默）
            reason_code = str(command.get("reason_code", "E_BUDGET_EXHAUSTED"))
            session_id = command.get("session_id")
            if not isinstance(session_id, str) or not session_id.strip():
                # **归属校验（R3 / G8，fail-closed）**：`session_id` 缺失/空/非字符串的作废请求
                # 会波及**所有**会话的待应用意图 ⇒ 一律拒，**不**作废任何条目、**不**落 intent.rejected。
                emit({"kind": "void_ack", "tick": kernel.world.tick, "seq": seq,
                      "reason": "E_SESSION_UNKNOWN", "voided": [], "count": 0,
                      "pending_after": kernel.pending_intent_count(),
                      "refused": "E_SESSION_UNKNOWN",
                      "detail": "void_intents requires an owning session_id (跨会话作废一律拒绝)"})
                seq += 1
                continue
            voided = kernel.void_pending_intents(reason_code, session_id.strip())
            emit({"kind": "void_ack", "tick": kernel.world.tick, "seq": seq,
                  "reason": reason_code, "session_id": session_id.strip(),
                  "voided": voided, "count": len(voided),
                  "pending_after": kernel.pending_intent_count()})
            seq += 1
            continue
        if name == "snapshot":
            # 新连接**首帧补齐**（R2 / F4 实测：连上后要等一个 snapshot_every 周期才看得见世界）。
            # 只读：不改世界状态、不推进 tick、不发事件（`WorldKernel.snapshot()` 是纯读）。
            current = kernel.snapshot()
            emit({"kind": "snapshot_ack", "tick": kernel.world.tick, "seq": seq,
                  "state": current["state"], "state_hash": current["state_hash"]})
            seq += 1
            continue
        if name == "tasks":
            # **[N5-C 加法] 只读**：回读**内核持有的**任务状态机状态 + 审计流水（C-1 的「读 state，
            # 不读日志」；`adaptation.py` 明文：任务状态由内核持有、刻意不进 `world.schema.json`）。
            # 不写世界、不推进 tick、不发事件。
            emit({"kind": "tasks_ack", "tick": kernel.world.tick, "seq": seq,
                  "task_states": kernel.adaptation.states_snapshot(),
                  "audit_log": kernel.adaptation.audit_log(),
                  "shift_counts": {task_id: kernel.adaptation.shift_counts(task_id)
                                   for task_id in kernel.adaptation.task_ids()}})
            seq += 1
            continue
        if name == "degradations":
            # **[N5-C 加法] 只读**：内核对**能力降级**的结构化读数（C-6 的「条目来自该失败」）。
            registry = getattr(kernel, "capability_registry", None)
            calls = [{"slot": c.get("slot"), "provider_class": c.get("provider_class"),
                      "ok": c.get("ok"), "fallback_reason": c.get("fallback_reason")}
                     for c in (registry.calls if registry is not None else [])]
            emit({"kind": "degradations_ack", "tick": kernel.world.tick, "seq": seq,
                  "emotion_fallbacks_log": list(kernel.emotion_fallbacks_log),
                  "emotion_fallbacks_total": len(kernel.emotion_fallbacks_log),
                  "emotion_appraise_calls": sum(1 for c in calls if c.get("slot") == "emotion.appraise"),
                  "emotion_appraise_ok": sum(1 for c in calls
                                             if c.get("slot") == "emotion.appraise" and c.get("ok")),
                  "calls_with_fallback_reason": [c for c in calls if c.get("fallback_reason")],
                  "journal_kinds": sorted({str(item.get("event")) for item in
                                           (registry.journal if registry is not None else [])})})
            seq += 1
            continue
        if name == "stop":
            emit({"kind": "bridge_stop", "tick": kernel.world.tick, "seq": seq,
                  "state_hash": state_hash_after, "chain_tail": log.last_hash})
            seq += 1
            return 0
        emit({"kind": "error", "tick": kernel.world.tick, "seq": seq,
              "reason": "E_SCHEMA_INVALID", "detail": f"unknown cmd {name!r}"})
        seq += 1
    emit({"kind": "bridge_stop", "tick": kernel.world.tick, "seq": seq,
          "state_hash": state_hash_after, "chain_tail": log.last_hash})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
