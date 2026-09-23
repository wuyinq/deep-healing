#!/usr/bin/env python3
"""会话层 ↔ 内核的**驱动桥**（M3 新增；D-2 / D-8）。

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
    log = EventLog(logs / "kernel-events.jsonl")
    kernel = WorldKernel(
        pack=pack, seed=args.seed, log=log,
        snapshot_every=args.snapshot_every,
        checkpoint_dir=logs / "checkpoints",
        plan_ticks=args.ticks,
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
