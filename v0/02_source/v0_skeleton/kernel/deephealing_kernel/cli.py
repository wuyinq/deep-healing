"""内核 CLI（V0-M1 实现，接口冻结）。

冻结的命令面（01 设计 §4.6）：

    python -m deephealing_kernel run --pack <dir> --seed <int> --tick-rate 10 \\
        --events <path> --snapshot-every 50 --ws-port <int> [--ticks N] [--replay]
    python -m deephealing_kernel replay --events <path> --pack <dir> --until <tick> \\
        --checkpoint-every 50 --out <path> [--dump-divergence]
    python -m deephealing_kernel verify --events <path> --pack <dir> [--expected-hash <hex>]
    python -m deephealing_kernel validate --pack <dir>
    python -m deephealing_kernel pack sign <dir>

退出码约定：
    0 成功；1 校验失败（E_PACK_INVALID / 哈希分歧 / 链断 / 截断 / 锚点不符 / cassette miss）；2 用法错误。

两处**加法扩展**（不改既有参数语义、不放松任何检查；设计 §4.6 / 上抛项 3）：
  - `run --ticks N`（默认 300）：冻结命令面没有终止上界，而 AC-M1-3 要求该命令自行 exit 0。
  - `verify --expected-hash <hex>`：实现为**链外锚点**且 fail-closed（预审 C1）。

**`verify` 的声称（修复轮 A1/A2 重写；强度上调、边界不变）**：
不传 `--expected-hash` 时的 `exit 0` 现在代表三件事同时成立 ——
  ① 哈希链自洽（`seq` 连续 / `prev_hash` 链接 / `hash` 可复算）；
  ② 检查点与一次**独立重放**逐点一致（`state_hash` / `rng_state_digest` / `event_chain_hash`）；
  ③ **日志的事件流与重放的语义序列一致**（逐条比 `(tick, type, actor)` + `payload`，`seq` 允许被重编号）
     —— 见 `_compare_event_streams()`。
**仍不**代表「日志未被篡改」：无密钥哈希链不是真实性保证（`cassette.format.md` 的
`FROZEN-CASSETTE-INTEGRITY-1`），且重放与 `run` **共用** `WorldKernel.step` 与 `canonical_json`（自比对）。
**抗改写必须传 `--expected-hash`**（链外锚点）——两者互补，缺一不可。

`--ws-port <n>` 本轮**真的监听**同一个**只读**实时观察端点（`live.py`）；
**`--ws-port 0`（默认）= 不监听**（最小权限；8787 已是会话侧代理端口）。
`--replay` 本轮**接受但无效果**（能力强制走 cassette_replay 属 W3，本轮无能力调用）——会在 stdout 显式打印，不留白。

`live` 子命令（M4 新增）是**活的世界**：内核侧自有 UTC+8 世界钟（相位从内容包派生）+
真实节流（1× = 1 真实秒 = 1 世界分钟）+ 只读观察通道（默认 `--port 8899`，`--ws-port` 为别名）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path

from . import KERNEL_CONTRACT_VERSION
from . import live as live_mod
from . import snapshot as snapshot_mod
from . import world_clock
from .events import EventChainError, EventLog, check_ech_invariants
from .live import (
    DEFAULT_BIND,
    DEFAULT_LIVE_PORT,
    DEFAULT_WS_PORT,
    HANDLER_ERROR_REPR_MAX,
    HANDLER_ERROR_SAMPLES_MAX,
    MAX_OBSERVERS_DEFAULT,
    AddrInUse,
    BindRefused,
    LiveServer,
    LiveWorld,
    is_loopback,
)
from .pack import PackInvalid, build_portal_edges, load_pack
from .providers.cassette import CassetteMiss, CassetteTampered
from .registry import CapabilityError
from .rules.decision import candidate_actions
from .snapshot import _load_checkpoint_dir, check_checkpoint_integrity, write_checkpoint
from .tick import DEFAULT_PLAN_TICKS, WorldKernel

V0_SKELETON = Path(__file__).resolve().parents[2]
PACK_SIGN_TOOL = V0_SKELETON / "tools" / "pack_sign.py"

# 事件流比对时**排除**的 payload 键（修复轮 A1）：它们是**运行期产物定位符**，取值取决于
# 「日志/检查点落在哪个目录」，与「世界语义」无关（日志被移动/复制后必然不同）。
# 集合被显式钉死，并由 `test_event_stream_comparison_excludes_only_locators` 断言，
# 防止后续静默扩大「比对豁免面」。
# 事件流比对的**豁免面**（修复轮 2 / F2 / Raven R15）：**空集**。
#
# 修复轮曾把 `checkpoint_path` 整体剔除（当作「运行期定位符」）。Raven 实证这留了一条
# **被 verify 祝福的篡改通道**：中段改 payload 之所以仍能被抓住，靠的是「其后 `snapshot.taken`
# 的 `event_chain_hash` 不在豁免面里」这一处**偶然的链耦合**；末条事件之后没有快照事件 ⇒ 耦合消失：
#   - N8：只改**末条** `snapshot.taken.payload.checkpoint_path` + 重算整链 + 同步改检查点 ⇒ 无锚点 exit 0；
#   - N9：`--snapshot-every 0`（无任何快照事件）时改**任意中段** `npc.action` 的 `checkpoint_path` ⇒ exit 0。
#
# 收紧为空集的前提是「该字段在 run / replay / verify 三条路径上**取值恒定**」——由
# `tick._take_and_write_checkpoint` 保证：恒为 `checkpoints/{tick:06d}.json`（不含目录前缀）。
# 于是：干净日志两侧逐位相同 ⇒ 仍 exit 0；任何一侧被改写 ⇒ `payload_diff` ⇒ exit 1。
# 该集合由 `test_event_stream_comparison_excludes_nothing` 钉死，防止后续静默重新扩大。
EVENT_STREAM_LOCATOR_KEYS = frozenset()
# 事件流比对**明细行的上报上限**（修复轮）：一处中段删除会让其后每一条都失配，明细全打会刷屏
# （实测 300 tick 的日志可产出 3.5k 行）。只上报前 N 条 + 一条 `truncated_report` 汇总，
# **总数与首个分歧 tick 不受影响**（`verify` 报告里的 `event_stream_divergences` 是**真实总数**，
# `event_stream_divergences_reported` 才是明细行数）。
MAX_DIVERGENCES = 25

# **负例自证专用钩子（修-2 / R-M2-2）**：置 1 时复现**修复前**形态 —— `CassetteMiss` 被
# 行为树的 action 节点吞成 FAILURE、`fail_closed_events` 从汇总里抹掉 ⇒ `--replay` 下 miss
# 回到「exit 0 假绿」。**仅供** `tests/test_cassette_miss_cli.py::test_negative_control_*` 使用；
# 生产路径**不得**设置该环境变量（否则 fail-closed 语义被绕过，属判据放松）。
_NEGATIVE_HIDE_CASSETTE_MISS = "DH_NEGATIVE_HIDE_CASSETTE_MISS"


def resolve_pack_dir(value: str) -> Path:
    """解析 `--pack`：① cwd 相对路径；② `<v0_skeleton>/<value>`（**加法**路径解析规则）。

    为什么需要：冻结命令面（设计 §4.6 / REQ §4 AC-M1-3）在 workdir = `.../v0_skeleton/kernel`
    下写 `--pack districts/xingfu-xiaoqu`，而内容包实际位于 `.../v0_skeleton/districts/xingfu-xiaoqu`
    —— 不复制内容包、不改冻结文件的前提下，用这条**只读**回退把两者接起来。
    它**不放松任何校验**：解析到的目录仍要过完整的 `load_pack` 校验链；解析失败一律报用法错误。
    回退命中时**显式打印**（修复轮 C6 / 预审 R12），避免「路径写错」看起来像成功。
    """
    direct = Path(value)
    if direct.is_dir():
        return direct
    fallback = V0_SKELETON / value
    if fallback.is_dir():
        print(f"note: --pack resolved via fallback to {fallback.resolve()}")
        return fallback
    return direct  # 交给 load_pack 报 E_PACK_INVALID（保留原路径以便定位）


def _load_pack_sign_tool():
    """复用冻结的 `tools/pack_sign.py`（单一实现，避免 `pack sign` 与 `verify_pack.py` 漂移）。"""
    spec = importlib.util.spec_from_file_location("deephealing_pack_sign", PACK_SIGN_TOOL)
    if spec is None or spec.loader is None:
        raise PackInvalid(f"cannot load pack sign tool from {PACK_SIGN_TOOL}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deephealing-kernel")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="启动世界（唯一权威进程）")
    run.add_argument("--pack", required=True)
    run.add_argument("--seed", type=int, default=None, help="缺省则用 pack 内 world.seed.json 的 seed")
    run.add_argument("--tick-rate", type=int, default=10)
    run.add_argument("--events", required=True)
    run.add_argument("--snapshot-every", type=int, default=50)
    run.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT,
                     help="只读实时观察端点端口；**0（默认）= 不监听**；显式给端口则真监听（daemon 线程，进程存活期）")
    run.add_argument("--replay", action="store_true", help="回放模式：能力强制走 cassette_replay 且 fail-closed")
    run.add_argument("--ticks", type=int, default=DEFAULT_PLAN_TICKS,
                     help="[加法扩展] 推进的 tick 数上界（默认值见 tick.DEFAULT_PLAN_TICKS）；冻结命令面本无终止参数")
    run.add_argument("--cognition", action="store_true",
                     help="[M2/W3~W6] 认知层驱动入口（**形态定死**，设计 §3.4b(2)）："
                          "tick 循环之后跑一次认知循环，产物落 <out>/cognition/**（不写世界状态）")
    run.add_argument("--memory", action="store_true",
                     help="[M2/W5] 打开**认知层自己的** MemoryStore 写入（<out>/cognition/memory.sqlite；"
                          "默认关闭 ⇒ 零写入，设计 §3.4b(5)）。**注意**：它**不是**内核 tick 的记忆链"
                          "（那条是 `--memory-chain`）—— 打开它不会让 `memory.written` 出现在事件清单里")
    run.add_argument("--memory-chain", action="store_true",
                     help="[M5.2 r3 / FIX-1] 打开**内核 tick** 的记忆链（AC-3 断链①②）：构造 "
                          "MemoryStore(<out>/kernel_memory.sqlite, write_enabled=True) 并传入 WorldKernel "
                          "⇒ 事件清单出现 memory.written（默认 **off** ⇒ 构造参数与改前逐字节一致）")
    run.add_argument("--capability-chain", action="store_true",
                     help="[M5.2 r3 / FIX-1] 打开**内核 tick** 的能力链（AC-3 断链④）：构造 CapabilityRegistry "
                          "+ BudgetLedger 并传入 WorldKernel ⇒ emotion.appraise 经既有 capability 通道"
                          "（预算 / provider 路由 / output_schema / fallback / journal）；默认 **off**")
    run.add_argument("--emotion-pressure-threshold", type=float, default=None,
                     help="[M5.2 r3 / FIX-1] 情绪评估的**调用条件**（该 NPC 主导需求缺口 >= 该值才调 "
                          "emotion.appraise）；缺省 = WorldKernel 默认（URGENCY_THRESHOLD=0.6）。"
                          "实测需求缺口 ~0.06 ⇒ 要让能力链真被调用需显式调低（例 0.0）")
    run.add_argument("--cassette-dir", default=None,
                     help="[M2/W3] cassette 根目录（默认 `<out>/cognition/cassettes`）；"
                          "`--replay` 时用它指向已录制的 cassette，miss ⇒ E_CASSETTE_MISS（fail-closed）")

    replay = sub.add_parser("replay", help="从 genesis 重放事件日志")
    replay.add_argument("--events", required=True)
    replay.add_argument("--pack", required=True)
    replay.add_argument("--until", type=int, default=None)
    replay.add_argument("--checkpoint-every", type=int, default=50)
    replay.add_argument("--out", required=True)
    replay.add_argument("--dump-divergence", action="store_true")

    verify = sub.add_parser("verify", help="重放并逐检查点比对 state_hash")
    verify.add_argument("--events", required=True)
    verify.add_argument("--pack", required=True)
    verify.add_argument("--expected-hash", default=None,
                        help="链外锚点：run 产出的链尾 hash；不符即 fail-closed（anchor_mismatch）")

    validate = sub.add_parser("validate", help="校验内容包（pack.sig + 数据 schema）")
    validate.add_argument("--pack", required=True)

    live = sub.add_parser("live", help="[M4] 活的世界：自有 UTC+8 世界钟 + 真实节流 + 只读实时观察通道")
    live.add_argument("--pack", required=True)
    live.add_argument("--seed", type=int, default=None)
    live.add_argument("--events", default=None, help="事件日志路径（缺省 = <out>/events.jsonl）")
    live.add_argument("--out", required=True, help="运行产物目录（事件日志 / 检查点 / live_state.json）")
    live.add_argument("--port", type=int, default=DEFAULT_LIVE_PORT,
                      help="只读观察通道端口（默认 8899）")
    live.add_argument("--ws-port", type=int, default=None,
                      help="`--port` 的别名（字面判据「--ws-port 真的监听」直接可验）")
    live.add_argument("--bind", default=DEFAULT_BIND, help="绑定地址（默认仅本机 127.0.0.1）")
    live.add_argument("--allow-remote", action="store_true",
                      help="允许绑定非 loopback 地址（**无鉴权**，信息面扩大，显式开关）")
    live.add_argument("--pace", type=float, default=1.0,
                      help="节流档：每个世界 tick 的真实秒数（1× = 1 真实秒 = 1 世界分钟）")
    live.add_argument("--ticks", type=int, default=None, help="推进 tick 数上界（缺省 = 不限，靠信号停止）")
    live.add_argument("--days", type=float, default=None, help="按世界日数换算的 tick 上界（与 --ticks 取先到者）")
    live.add_argument("--snapshot-every", type=int, default=50)
    live.add_argument("--resume-tick", type=int, default=None, help="快进复原到该 tick 后继续节流推进")
    live.add_argument("--resume-state", default=None, help="从 live_state.json 复原（校验 tick/seed/pack 一致）")
    live.add_argument("--no-warmup", action="store_true", help="不做「快进到当前 UTC+8 时刻」的启动锚定")
    live.add_argument("--max-observers", type=int, default=MAX_OBSERVERS_DEFAULT,
                      help="SSE 并发观察者上限（超限 ⇒ 503）")
    live.add_argument("--memory-chain", action="store_true",
                      help="[M5.2 r3 / FIX-1] 同 `run --memory-chain`：内核 tick 的记忆链（MemoryStore ⇒ "
                           "memory.written 事件；默认 off ⇒ 与改前逐字节一致）")
    live.add_argument("--capability-chain", action="store_true",
                      help="[M5.2 r3 / FIX-1] 同 `run --capability-chain`：内核 tick 的能力链"
                           "（CapabilityRegistry + BudgetLedger ⇒ emotion.appraise；默认 off）")
    live.add_argument("--emotion-pressure-threshold", type=float, default=None,
                      help="[M5.2 r3 / FIX-1] 情绪评估的调用条件（同 `run`；缺省 = 0.6）")

    pack = sub.add_parser("pack", help="内容包工具")
    pack_sub = pack.add_subparsers(dest="pack_command", required=True)
    sign = pack_sub.add_parser("sign", help="重新生成 pack.sig")
    sign.add_argument("dir")

    return parser


def _writable_reason(path: Path) -> str | None:
    """**可写性探测**（P-4 / M-2）：返回拒绝原因或 None。

    为什么需要：只读目录（`chmod 500`）能通过「存在性 + 非空 + 是目录」三条守卫，
    直到**第一个快照 tick** 才 `PermissionError` —— 裸 traceback + 半截日志（Raven 实测 252 行）。
    探测点取「最近的已存在祖先目录」（`checkpoints/` 尚未创建时，要写的是它的父目录）。
    """
    target = path
    while not target.exists():
        if target.parent == target:
            break
        target = target.parent
    if not target.exists():
        return f"no existing ancestor directory for {path}"
    if not target.is_dir():
        return f"{target} exists but is not a directory"
    if not os.access(target, os.W_OK):
        return f"{target} is not writable (os.access(W_OK) is false)"
    return None


def _guard_output_dir(checkpoint_dir: Path, *, label: str) -> list[str]:
    """输出面形态守卫（P-4 / M-2 + M-3）：返回拒绝原因列表（空 = 通过）。

    **M-3（符号链接逃逸）**：`checkpoints` 是**指向 `out/**` 之外的符号链接目录**时，
    `write_checkpoint` 的 `mkdir(exist_ok=True)` 会静默成功，字节落到 `out/**` 之外
    （Raven 实测：`Z-outside/` 下 2 个检查点）。悬空符号链接同样拒收
    （`exists()` 为假 ⇒ 后续 `mkdir` 抛 `FileExistsError` 裸 traceback）。
    包**内**目标的符号链接（指向 `out/` 之内）仍合法 —— 与 `pack.py` 同一口径。

    **M-2（可写性）**：最近祖先目录不可写 ⇒ fail-closed，不等到第一个快照 tick 才炸。
    """
    reasons: list[str] = []
    parent = checkpoint_dir.parent
    if checkpoint_dir.is_symlink():
        resolved = checkpoint_dir.resolve()
        if not checkpoint_dir.exists():
            reasons.append(
                f"{label} checkpoints path {checkpoint_dir} is a DANGLING symlink to {resolved}"
            )
        elif not resolved.is_relative_to(parent.resolve()):
            reasons.append(
                f"{label} checkpoints path {checkpoint_dir} is a symlink escaping the run-artifact "
                f"directory: resolves to {resolved} which is outside {parent.resolve()}"
            )
    writable = _writable_reason(checkpoint_dir)
    if writable is not None:
        reasons.append(f"{label} checkpoints path is not writable: {writable}")
    return reasons


def _refuse_existing_run_outputs(log_path: Path, checkpoint_dir: Path) -> None:
    """fail-closed：目标**日志非空** 或 **检查点目录已有文件** 时都**拒绝**启动。

    理由：事件日志是 append-only 的**证据**。
      - 静默追加 ⇒ 同一文件里出现第二条 `seq=0` 的链（链校验必红，但现场已被污染）；
      - 静默截断 ⇒ 销毁既有证据（且与「不回改历史」冲突）。

    **对称性（修复轮 C7 / 预审 R9）**：原先只检查日志 ⇒「删掉 `e.jsonl`、保留旧检查点、用更少
    `--ticks` 重跑」会留下**多余的旧检查点**，`verify` 随即报 `checkpoint tick=N has no matching
    snapshot.taken event` —— 那是**残留产物**导致的**假红**，看起来像内核坏了。
    现在日志与检查点**都必须**显式清空。
    """
    reasons: list[str] = []
    if log_path.exists() and log_path.stat().st_size > 0:
        reasons.append(f"non-empty event log {log_path}")
    # 修复轮 2 / F3 / Raven R23.2：判定从 `is_dir()` 改为 `exists()` —— 该路径**存在但不是目录**
    # （普通文件 / 符号链接指向文件）时，`is_dir()` 为假 ⇒ 原先不触发 fail-closed，
    # 运行到第一个快照 tick 时 `write_checkpoint` 抛**未捕获的** `FileExistsError`（裸 traceback），
    # 并留下**半截日志**（Raven 实测 252 事件 / 含一条 `snapshot.taken@50` 但对应检查点从未写出）。
    if checkpoint_dir.exists():
        if not checkpoint_dir.is_dir():
            reasons.append(f"{checkpoint_dir} exists but is not a directory")
        else:
            stale = sorted(path.name for path in checkpoint_dir.glob("*.json"))
            if stale:
                reasons.append(
                    f"existing checkpoints in {checkpoint_dir} ({len(stale)}: {', '.join(stale[:6])}...)"
                )
    if reasons:
        raise PackInvalid(
            "E_EVENTS_EXISTS: refusing to run: " + "; ".join(reasons)
            + " — BOTH the event log and the checkpoint directory must be explicitly cleared "
              "before re-running (out/** is a run-artifact directory; a half-cleaned tree yields a "
              "misleading red from `verify`)"
        )


def _refuse_unusable_output_dir(checkpoint_dir: Path, *, label: str) -> None:
    """输出面形态 fail-closed（P-4 / M-2 + M-3）。

    与「已存在产物」是**两个不同的拒绝面**，因此给**不同的结构化码**（四元组判据要 `^E_` 行）：
      - `E_OUTPUT_SYMLINK_ESCAPE`：`checkpoints` 是指向 run-artifact 目录之外的符号链接
        （或悬空符号链接）⇒ 拒收，**不产生任何 `out/**` 之外的新文件**；
      - `E_OUTPUT_NOT_WRITABLE`：最近祖先目录不可写 ⇒ 拒收，**不留下半截日志**。
    两者都在 `WorldKernel` / `EventLog` 构造**之前**抛出 ⇒ 不写事件日志、不写检查点。
    """
    reasons = _guard_output_dir(checkpoint_dir, label=label)
    if not reasons:
        return
    code = "E_OUTPUT_SYMLINK_ESCAPE" if any("symlink" in reason for reason in reasons) \
        else "E_OUTPUT_NOT_WRITABLE"
    raise PackInvalid(
        f"{code}: refusing to {label}: " + "; ".join(reasons)
        + " — the run-artifact directory must be a writable real directory inside the output tree"
    )


def _refuse_existing_replay_outputs(out_dir: Path) -> None:
    """`replay` 侧的对称检查（修复轮 C7）：`replay.jsonl` 非空 或 已有检查点 ⇒ 拒绝。

    **P-4 / M-1 对齐（M2）**：判定从 `is_dir()` 改为 `exists()`，与 run 侧（修复轮 2 / F3）
    逐字对齐。`checkpoints` 路径**存在但不是目录**（普通文件占位）时 `is_dir()` 为假 ⇒
    原先不触发 fail-closed，运行到第一个快照 tick 才 `FileExistsError`（裸 traceback +
    252 行半截 `replay.jsonl`）。四元组判据：① 非 0 ② 结构化 `E_` 码 ③ 无 `Traceback`
    ④ 无半截 `replay.jsonl`。
    """
    reasons: list[str] = []
    replay_log = out_dir / "replay.jsonl"
    if replay_log.exists() and replay_log.stat().st_size > 0:
        reasons.append(f"non-empty replay log {replay_log}")
    checkpoint_dir = out_dir / "checkpoints"
    if checkpoint_dir.exists():
        if not checkpoint_dir.is_dir():
            reasons.append(f"{checkpoint_dir} exists but is not a directory")
        else:
            stale = sorted(path.name for path in checkpoint_dir.glob("*.json"))
            if stale:
                reasons.append(
                    f"existing checkpoints in {checkpoint_dir} ({len(stale)}: {', '.join(stale[:6])}...)"
                )
    if reasons:
        raise PackInvalid(
            "E_EVENTS_EXISTS: refusing to replay: " + "; ".join(reasons)
            + " — BOTH the replay log and the checkpoint directory must be explicitly cleared"
        )


# --------------------------------------------------- 内核链入口（M5.2 r3 / FIX-1 · R-C1）
def _build_kernel_chain(args, *, out_dir: Path, pack) -> tuple[dict, dict]:
    """**交付 CLI 的内核链入口**（AC-3 断链①②④ 在交付形态下的唯一可执行路径）。

    为什么需要（Raven R-C1 = CRITICAL）：`tick.py` 实现了接线（`memory_store` /
    `capability_registry` / `budget_ledger` 三个构造参数 + `_write_memory()` / `_appraise_emotions()`），
    但 r2 之前**交付面没有任何入口传值** —— `cli.py` 的 `WorldKernel(...)` 构造都不传 ⇒
    交付命令的事件清单里永远没有 `memory.written`，`emotion.appraise` 也永远零调用
    （唯一传值点全在测试/脚手架里）。

    契约（**默认 off ⇒ 构造参数与改前逐字节一致**，回归护栏见 `03` 的 M5.2-r3 段 ②）：
      - `--memory-chain`：构造内核侧 `MemoryStore(<out>/kernel_memory.sqlite, write_enabled=True)`
        并传入 `memory_store` ⇒ `step()` 的 [5] 段写库并 emit `memory.written`；
      - `--capability-chain`：构造 `CapabilityRegistry`（数据驱动发现 + 四类 adapter）与
        `BudgetLedger` 并传入 ⇒ `emotion.appraise` 走既有 capability 通道
        （预算闸门 / provider 路由 / output_schema / fallback / journal 全部复用）；
      - `--emotion-pressure-threshold`：情绪评估的**调用条件**（该 NPC 主导需求缺口 >= 该值），
        缺省 = `WorldKernel` 默认（`URGENCY_THRESHOLD = 0.6`）。实测需求缺口 ~0.06 ⇒
        要让能力链**真的被调用**必须显式调低（这是数据参数，不是按 NPC 特判）。

    返回 `(WorldKernel 的额外关键字参数, 结构化读数容器)`；**两个开关都 off 时 `extra == {}`**
    ⇒ `WorldKernel(...)` 的实参集合与改前完全相同。
    """
    extra: dict = {}
    state: dict = {"memory_chain": False, "capability_chain": False}
    if bool(getattr(args, "memory_chain", False)):
        from .memory.store import MemoryStore
        store_path = out_dir / "kernel_memory.sqlite"
        store = MemoryStore(store_path, write_enabled=True)
        store.init_schema()
        extra["memory_store"] = store
        state["memory_chain"] = True
        state["memory_store_path"] = str(store_path)
        state["memory_store"] = store
    if bool(getattr(args, "capability_chain", False)):
        from .budget import BudgetLedger
        registry, _unused = _build_cognition_registry(
            out_dir, cassette_root=out_dir / "kernel_capability" / "cassettes",
            replay_mode=bool(getattr(args, "replay", False)))
        registry.discover()
        state["registry_validation_errors"] = registry.validate()
        per_tick_calls, daily_tokens = _capability_caps(
            [registry.capability(slot) for slot in registry.slots()])
        ledger = BudgetLedger(day_ticks=int(pack.world_seed["constants"].get("day_ticks", 1440)),
                              per_tick_calls=per_tick_calls, per_npc_daily_tokens=daily_tokens)
        extra["capability_registry"] = registry
        extra["budget_ledger"] = ledger
        state["capability_chain"] = True
        state["registry"] = registry
    threshold = getattr(args, "emotion_pressure_threshold", None)
    if threshold is not None:
        extra["emotion_pressure_threshold"] = float(threshold)
        state["emotion_pressure_threshold"] = float(threshold)
    return extra, state


def _kernel_chain_readings(kernel, state: dict, events_path: Path) -> dict:
    """内核链的**结构化读数**（FIX-1 关闭判据 ①③ 的落点）。

    只报盘上/内存里**真实存在**的读数：`memory.written` 按 `layer` 计数、`fetch_episodes` 读回条数、
    `emotion.appraise` 的调用/成功/降级。**不伪造情绪结果** —— 降级一律落 `emotion_fallbacks`。
    """
    readings: dict = {
        "memory_chain": bool(state.get("memory_chain")),
        "capability_chain": bool(state.get("capability_chain")),
        "emotion_pressure_threshold": state.get("emotion_pressure_threshold"),
        "registry_validation_errors": state.get("registry_validation_errors"),
    }
    if state.get("memory_chain"):
        by_layer: dict = {}
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "memory.written":
                layer = str((event.get("payload") or {}).get("layer"))
                by_layer[layer] = by_layer.get(layer, 0) + 1
        store = state.get("memory_store")
        episodes: dict = {}
        if store is not None:
            for entity in kernel.world.query(kind="npc"):
                episodes[entity.id] = len(store.fetch_episodes(entity.id))
        readings["memory_store_path"] = state.get("memory_store_path")
        readings["memory_written_by_layer"] = dict(sorted(by_layer.items()))
        readings["memory_written_total"] = sum(by_layer.values())
        readings["store_write_count"] = None if store is None else int(store.write_count)
        readings["episodes_readback"] = episodes
    registry = state.get("registry")
    if state.get("capability_chain") and registry is not None:
        calls = [call for call in registry.calls if call.get("slot") == "emotion.appraise"]
        readings["emotion_appraise_calls"] = len(calls)
        readings["emotion_appraise_ok"] = sum(1 for call in calls if call.get("ok"))
        readings["emotion_fallbacks_total"] = len(kernel.emotion_fallbacks_log)
        readings["emotion_fallbacks"] = list(kernel.emotion_fallbacks_log)
        readings["emotion_results_npcs_last_tick"] = sorted(kernel.emotion_results)
        readings["capability_journal_kinds"] = sorted(
            {str(item.get("event")) for item in registry.journal})
    return readings


# --------------------------------------------------------------------------- run
def cmd_run(args) -> int:
    try:
        pack = load_pack(resolve_pack_dir(args.pack))
    except PackInvalid as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    events_path = Path(args.events)
    checkpoint_dir = events_path.parent / "checkpoints"
    try:
        _refuse_existing_run_outputs(events_path, checkpoint_dir)
        _refuse_unusable_output_dir(checkpoint_dir, label="run")
    except PackInvalid as exc:
        print(str(exc), file=sys.stderr)
        return 1
    # **FIX-1（r3）· 内核链入口**：默认 off ⇒ `chain_extra == {}` ⇒ 构造实参与改前逐字节一致。
    chain_extra, chain_state = _build_kernel_chain(args, out_dir=events_path.parent, pack=pack)
    kernel = WorldKernel(
        pack=pack,
        seed=args.seed,
        log=EventLog(events_path),
        snapshot_every=args.snapshot_every,
        checkpoint_dir=checkpoint_dir,
        tick_rate=args.tick_rate,
        plan_ticks=args.ticks,
        **chain_extra,
    )
    # **F5′（r3）· 只读观察通道必须在 tick 循环之前启动**
    #
    # 旧顺序（`kernel.run()` 在 `_start_live_listener()` **之前**）⇒ 监听只在整轮 tick 跑完之后才
    # bind，随即打印 JSON 并返回、进程退出：真子进程下外部可连窗口不可观测（上界 ≈ 22µs，
    # 78,898 次阻塞 connect 采样 0 命中），而 `live_channel.listening` 仍自报 `true`
    # 并被 `AC-M4-9④` 当证据引用。**问题不是「没监听」，是「声明了一个外部无法观测的窗口，
    # 却把它当可用观察面」** ⇒ 修行为，不改措辞。
    #
    # 设计依据：`01_m4_design.md` D-M4-4 原文 =「显式给端口时**真的监听并服务同一只读端点**」
    # ⇒ 这是实现**自己已冻结的设计**，不是改契约。
    # 副作用（登记 C-18）：顺序前移后，「时钟语义派生失败」会在**写产物之前** fail-closed
    # （旧顺序先把 `events.jsonl` / `checkpoints` 写完再 `exit 1`，留半截产物）——
    # 与 `_refuse_unusable_output_dir` 的「不留下半截日志」同向，**更** fail-closed。
    # `--ws-port 0`（默认）不进该分支 ⇒ 21 处既有用例零影响。
    live_channel = None
    if int(args.ws_port) != 0:
        try:
            live_world, live_server = _start_live_listener(
                kernel, pack, port=int(args.ws_port), bind=DEFAULT_BIND, allow_remote=False)
        except world_clock.ClockSemanticsError as exc:
            print(f"{exc.code}: {exc}", file=sys.stderr)
            return 1
        except AddrInUse as exc:
            print(str(exc), file=sys.stderr)
            return 1
        live_channel = {
            "listening": live_server.listening,
            "bind": live_server.bind,
            "port": live_server.port,
            "read_only": True,
            "endpoints": ["/live/health", "/live/meta", "/live/state", "/live/stream"],
            "note": "read-only observation channel; there is no write endpoint",
        }
        _LIVE_CHANNELS.append(live_server)
    stopped_channels: list = []
    try:
        kernel.run(args.ticks)
    finally:
        # **F7（r3）**：观察面现在整段 tick 循环都活着 ⇒ 循环一结束就**显式 stop()**，
        # 不让 HTTP daemon 线程活到解释器 finalize（那是 `_enter_buffered_busy` ⇒ SIGABRT 的成因）。
        # **FIX-6（r3）**：stop() 返回已停通道 ⇒ 停稳之后取有界诊断样本落盘。
        stopped_channels = _stop_live_channels()
    live_diagnostics = _write_live_diagnostics(events_path.parent, stopped_channels)
    cognition_report = None
    if args.cognition:
        cognition_report = _run_cognition(
            pack, kernel, out_dir=events_path.parent, replay_mode=bool(args.replay),
            memory_writes=bool(args.memory),
            cassette_dir=Path(args.cassette_dir) if args.cassette_dir else None)
        # **修-2 / R-M2-2 + 修-6 / R2-M2（收口轮）**：`--replay` 下 cassette **miss** 与**篡改**
        # 必须**同等命令层可见**（exit ≠ 0 + 结构化诊断），否则「只看 exit 的自动化验收」会把
        # fail-closed 读成绿。方向保持不变：**不降级、不回填、不静默切远端**。
        misses = int(cognition_report.get("fail_closed_events", 0))
        chain_errors = list(cognition_report.get("cassette_chain_errors") or [])
        tampered = int(cognition_report.get("cassette_tampered_events", 0))
        # **负例自证专用钩子（修-6 / R2-M2）**：置 1 时复现**修复前**形态 —— 篡改只记
        # `cassette_chain_errors` 嵌套字段、不算失败 ⇒ 命令层 exit 0（R2-M2 的缺陷形态）。
        # **仅供** `tests/test_cassette_tamper_cli.py::test_negative_control_*` 使用；生产不得设置。
        if os.environ.get("DH_NEGATIVE_TAMPER_AS_WARNING") == "1":
            tampered = 0
            chain_errors = []
        if misses or tampered or chain_errors:
            if tampered or chain_errors:
                print(
                    f"E_CASSETTE_TAMPERED: replay mode detected {tampered or len(chain_errors)} "
                    "tampered cassette record(s) (chain hash mismatch); the cognition loop is "
                    "fail-closed on tampering (no fallback, no remote switch). "
                    "Re-record the cassettes from a trusted run.",
                    file=sys.stderr,
                )
            if misses:
                print(
                    f"E_CASSETTE_MISS: replay mode had {misses} cassette miss(es); "
                    "the cognition loop is fail-closed on miss (no fallback, no remote switch). "
                    "Record the cassettes first (run without --replay) or point --cassette-dir at them.",
                    file=sys.stderr,
                )
            print(json.dumps({
                "command": "run", "pack_id": pack.manifest["id"], "seed": kernel.seed,
                "ticks": args.ticks, "cassette_misses": misses,
                "cassette_tampered": tampered or len(chain_errors),
                "cassette_chain_errors": chain_errors,
                "fail_closed": True,
                "cognition_artifacts": cognition_report.get("artifacts"),
            }, ensure_ascii=False, sort_keys=True))
            return 1
    if args.replay:
        print("note: --replay forces the cognition layer onto cassette_replay (fail-closed on miss); "
              "M1's tick path makes no capability calls => no effect there")
    kernel_chain = None
    if chain_state.get("memory_chain") or chain_state.get("capability_chain"):
        kernel_chain = _kernel_chain_readings(kernel, chain_state, events_path)
    print(json.dumps({
        "command": "run", "pack_id": pack.manifest["id"], "seed": kernel.seed,
        "ticks": args.ticks, "snapshot_every": kernel.snapshot_every,
        "events": str(events_path), "checkpoints": str(checkpoint_dir),
        "live_channel": live_channel,
        "kernel_chain": kernel_chain,
        "live_diagnostics": live_diagnostics,
        "chain_tail": kernel.log.last_hash if kernel.log is not None else None,
        "event_count": kernel.log._seq if kernel.log is not None else 0,  # noqa: SLF001 (诊断输出)
        "cognition": None if cognition_report is None else {
            "slots": cognition_report["registry"]["slots"],
            "validation_errors": cognition_report["registry"]["validation_errors"],
            "events": cognition_report["cognition_events"],
            "fallback_counts": cognition_report["fallback_counts"],
            "local_model_available": cognition_report["local_model_available"],
            "memory_write_count": cognition_report["memory"]["write_count"],
            "artifacts": cognition_report["artifacts"],
            "state_hash_after_cognition": cognition_report["world_state_hash_after_cognition"],
        },
    }, ensure_ascii=False, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- replay
def _world_init(parsed: list) -> dict:
    for event in parsed:
        if event.type == "world.init":
            return event.payload
    raise EventChainError("no world.init event in log", tick=None)


def cmd_replay(args) -> int:
    try:
        pack = load_pack(resolve_pack_dir(args.pack))
    except PackInvalid as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    events_path = Path(args.events)
    try:
        parsed = list(EventLog(events_path).read_all())
    except EventChainError as exc:
        print(f"E_EVENT_CHAIN: {exc}", file=sys.stderr)
        return 1
    try:
        init = _world_init(parsed)
    except EventChainError as exc:
        print(f"E_EVENT_CHAIN: {exc}", file=sys.stderr)
        return 1

    seed = int(init["seed"])
    plan_ticks = int(init["plan_ticks"])
    recorded_every = int(init["snapshot_every"])   # 预审 L6：一律以日志记录的**生效值**为准
    until = int(args.until) if args.until is not None else plan_ticks
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        _refuse_existing_replay_outputs(out_dir)
        _refuse_unusable_output_dir(out_dir / "checkpoints", label="replay")
    except PackInvalid as exc:
        print(str(exc), file=sys.stderr)
        return 1

    # 回放日志：与 run 逐条同构 ⇒ 链尾逐 tick 一致（run ↔ replay 的 event_chain_hash 可比）
    kernel = WorldKernel(
        pack=pack, seed=seed, log=EventLog(out_dir / "replay.jsonl"),
        snapshot_every=recorded_every, checkpoint_dir=None, plan_ticks=plan_ticks,
    )
    # 检查点写进 `<out>/checkpoints/`（修复轮 C9）：使 `snapshot.taken.payload.checkpoint_path`
    # （以日志目录为基准的 `checkpoints/{tick:06d}.json`）在 replay 产物里也**指向真实存在的文件**。
    checkpoint_dir = out_dir / "checkpoints"
    written: list[str] = []
    for tick in range(1, until + 1):
        kernel.step()
        snapshot = kernel.last_snapshot
        if snapshot is None or snapshot.tick != tick:
            continue
        if args.checkpoint_every > 0 and tick % args.checkpoint_every != 0:
            continue
        written.append(str(write_checkpoint(snapshot, checkpoint_dir)))
    if args.dump_divergence:
        print(json.dumps({"dump_divergence": True, "note": "见 verify/compare_checkpoints 的分歧协议"}, ensure_ascii=False))
    print(json.dumps({
        "command": "replay", "seed": seed, "until": until,
        "snapshot_every_from_log": recorded_every, "checkpoint_every": args.checkpoint_every,
        "checkpoints_written": len(written), "out": str(out_dir),
        "chain_tail": kernel.log.last_hash if kernel.log is not None else None,
    }, ensure_ascii=False, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- verify
def _compare_event_streams(logged: list, replayed: list) -> tuple[list[str], int | None, int]:
    """**事件流比对**（修复轮 A1 / 预审 R1）：把重放产生的事件流与日志逐条比**语义序列**。

    为什么需要：`verify` 原先只比对 `snapshot.taken` 事件的三个哈希 ⇒ **中段事件**
    （`npc.action` 等非快照事件）**从不与重放比对**，于是「删除/改写中段事件 + 重算整条链
    + 同步改写检查点」的伪造在不传锚点时 `exit 0`（Raven 实证 F2~F5）。

    口径：
      - 比 `(tick, type, actor)` **语义序列**（`seq` 允许被重编号 ⇒ 不比 `seq`、不比 `prev_hash`/`hash`）；
      - **并**逐条比 `payload`（`EVENT_STREAM_LOCATOR_KEYS` 里的**运行期定位符**除外，
        其取值取决于日志/检查点落在哪个目录，与「世界语义」无关）；
      - 任何多余 / 缺失 / 改写即记 divergence，并给出**首个分歧 tick**。

    **强度边界（不得读成已完全加固）**：重放与 `run` **共用** `WorldKernel.step` 与 `canonical_json`
    ⇒ 对**共享实现**的系统性缺陷不可见；且它**挡不住**「截断 + 改写 `plan_ticks` + 重算整链」这类
    **自洽前缀**伪造（重放合法地复现该前缀）—— 那一类**只能**由链外锚点 `--expected-hash` 关闭。
    两者互补，缺一不可（修复轮 A2 声称）。
    """
    divergences: list[str] = []
    first: int | None = None
    total = 0

    def bump(tick: int | None) -> None:
        nonlocal first
        if tick is not None and (first is None or tick < first):
            first = tick

    def record(line: str) -> None:
        """记一条 divergence：**上限 `MAX_DIVERGENCES`**（防日志被后续连锁失配刷屏），总数照实累加。"""
        nonlocal total
        total += 1
        if len(divergences) < MAX_DIVERGENCES:
            divergences.append(line)

    for index in range(max(len(logged), len(replayed))):
        if index >= len(replayed):
            event = logged[index]
            record(f"event_stream:extra_in_log:index={index} tick={event.tick} type={event.type}")
            bump(event.tick)
            continue
        if index >= len(logged):
            event = replayed[index]
            record(f"event_stream:missing_in_log:index={index} tick={event.tick} type={event.type}")
            bump(event.tick)
            continue
        left, right = logged[index], replayed[index]
        if (left.tick, left.type, left.actor) != (right.tick, right.type, right.actor):
            record(
                f"event_stream:mismatch:index={index} "
                f"logged=(tick={left.tick},type={left.type},actor={left.actor}) "
                f"replayed=(tick={right.tick},type={right.type},actor={right.actor})"
            )
            bump(min(left.tick, right.tick))
            continue
        left_payload = {k: v for k, v in left.payload.items() if k not in EVENT_STREAM_LOCATOR_KEYS}
        right_payload = {k: v for k, v in right.payload.items() if k not in EVENT_STREAM_LOCATOR_KEYS}
        if left_payload != right_payload:
            for field in sorted(set(left_payload) | set(right_payload)):
                if left_payload.get(field) != right_payload.get(field):
                    record(
                        f"event_stream:payload_diff:index={index} tick={left.tick} type={left.type} "
                        f"field={field} logged={left_payload.get(field)!r} "
                        f"replayed={right_payload.get(field)!r}"
                    )
            bump(left.tick)

    if total > len(divergences):
        divergences.append(
            f"event_stream:truncated_report:shown={len(divergences)} total={total} "
            f"（首个分歧 tick={first}；后续失配是同一处删除/改写引起的连锁，已折叠）"
        )
    return divergences, first, total


CLAIM_BOUNDARY = (
    "exit 0 WITHOUT --expected-hash means: (1) the hash chain is self-consistent; "
    "(2) the checkpoints agree with an independent replay on state_hash/rng_state_digest/event_chain_hash; "
    "(3) the log's event stream agrees with the replay's semantic sequence "
    "(tick/type/actor + payload — the payload comparison has NO exempt keys, "
    "EVENT_STREAM_LOCATOR_KEYS is empty, so every payload field including checkpoint_path is compared). "
    "It does NOT mean 'the log was not tampered with' — a keyless hash chain is not a truth guarantee "
    "(cassette.format.md FROZEN-CASSETTE-INTEGRITY-1), and the replay shares WorldKernel.step and "
    "canonical_json with run (self-comparison). Tamper resistance REQUIRES --expected-hash (off-chain anchor)."
)


def cmd_verify(args) -> int:
    events_path = Path(args.events)
    try:
        pack = load_pack(resolve_pack_dir(args.pack))
    except PackInvalid as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1

    # 2) 读日志并校验链
    try:
        parsed = list(EventLog(events_path).read_all())
    except EventChainError as exc:
        print(f"E_EVENT_CHAIN: {exc}", file=sys.stderr)
        print(f"verify: FAIL (first divergence tick = {exc.tick})")
        return 1
    if not parsed:
        print("verify: FAIL (empty event log)", file=sys.stderr)
        return 1
    try:
        init = _world_init(parsed)
    except EventChainError as exc:
        print(f"E_EVENT_CHAIN: {exc}", file=sys.stderr)
        return 1

    seed = int(init["seed"])
    plan_ticks = int(init["plan_ticks"])
    recorded_every = int(init["snapshot_every"])
    max_tick = max(event.tick for event in parsed)
    snapshot_events = {event.tick: event for event in parsed if event.type == "snapshot.taken"}

    problems: list[str] = []
    first_divergence: int | None = None

    def note(problem: str, tick: int | None) -> None:
        """记一条 problem：**按文本去重**（修复轮 2 / F6 / Sentinel Bug#15），保持首次出现顺序。

        为什么：`_load_checkpoint_dir` 被**三个**调用点各自调用（`cli` 的 `set_errors`、
        `snapshot.check_checkpoint_integrity`、`events.check_ech_invariants` 的 ECH-1）⇒
        检查点**集合级**错误（`non_canonical_filename` / `duplicate_tick`）会在 `problems` 里
        出现 **3 次**。退出码与 `first_divergence_tick` 不受影响，但 `problems` 是**机器可读输出**，
        重复条目会让下游「按条数统计问题」的实现得到 3 倍数字。
        去重**只折叠逐字相同的条目**（不同 tick / 不同文件的诊断仍各自保留），不吞任何信息。
        """
        nonlocal first_divergence
        if problem not in problems:
            problems.append(problem)
        if tick is not None and (first_divergence is None or tick < first_divergence):
            first_divergence = tick

    # 3) 重放：同一 seed + pack 的新内核实例从 genesis 逐 tick 推进（强制 run ↔ replay 比对）
    #    同时**产出事件流**并与日志逐条比对语义序列（修复轮 A1）
    stream_divergences: list[str] = []
    stream_first: int | None = None
    with tempfile.TemporaryDirectory(prefix="dh_verify_stream_") as stream_dir:
        replayed_log = EventLog(Path(stream_dir) / "replay.jsonl")
        kernel = WorldKernel(
            pack=pack, seed=seed, log=replayed_log, snapshot_every=recorded_every, plan_ticks=plan_ticks,
        )
        for tick in range(1, max_tick + 1):
            kernel.step()
            event = snapshot_events.get(tick)
            if event is None:
                continue
            current_state = kernel.state_hash()
            current_rng = snapshot_mod.hash_object(kernel.rng.digests())
            if event.payload.get("state_hash") != current_state:
                note(f"state_hash divergence at tick={tick} (log={event.payload.get('state_hash')} "
                     f"replay={current_state})", tick)
            if event.payload.get("rng_state_digest") != current_rng:
                note(f"rng_state_digest divergence at tick={tick}", tick)
        replayed_events = list(replayed_log.read_all())
    stream_divergences, stream_first, stream_total = _compare_event_streams(parsed, replayed_events)
    for divergence in stream_divergences:
        note(divergence, stream_first)

    # 4) INVARIANT-ECH-1/2/3
    checkpoint_dir = events_path.parent / "checkpoints"
    has_checkpoints = checkpoint_dir.is_dir()
    for problem in check_ech_invariants(parsed, checkpoint_dir if has_checkpoints else None):
        note(problem, None)

    # 5) 朴素整行截断：日志最大 tick 必须等于 world.init 记录的 plan_ticks
    if max_tick != plan_ticks:
        note(f"truncated log: max_tick={max_tick} != plan_ticks={plan_ticks}", max_tick + 1)

    # 6) 检查点集合交叉核对 + 独立完整性断言（预审 M3）
    if has_checkpoints:
        by_tick, set_errors = _load_checkpoint_dir(checkpoint_dir)
        for problem in set_errors:
            note(problem, None)
        for problem in check_checkpoint_integrity(checkpoint_dir):
            note(problem, None)
        for tick in sorted(by_tick):
            event = snapshot_events.get(tick)
            if event is None:
                note(f"checkpoint tick={tick} has no matching snapshot.taken event", tick)
                continue
            for field in ("state_hash", "rng_state_digest", "event_chain_hash"):
                recorded = by_tick[tick].get(field)
                expected = event.hash if field == "event_chain_hash" else event.payload.get(field)
                if recorded != expected:
                    note(f"checkpoint {field} mismatch at tick={tick} (file={recorded} log={expected})", tick)

    # 7) 链外锚点（预审 C1，fail-closed，三态语义）
    log_tail = parsed[-1].hash
    if args.expected_hash is None:
        print("chain anchor: not provided")
    elif log_tail != args.expected_hash:
        note(f"anchor_mismatch: log tail={log_tail} expected={args.expected_hash}", max_tick)

    report = {
        "command": "verify", "pack_id": pack.manifest["id"], "seed": seed,
        "events": str(events_path), "event_count": len(parsed), "max_tick": max_tick,
        "plan_ticks": plan_ticks, "snapshot_every_from_log": recorded_every,
        "snapshots": len(snapshot_events), "checkpoints_present": has_checkpoints,
        "expected_hash_provided": args.expected_hash is not None, "log_tail": log_tail,
        "event_stream_compared": True,
        "event_stream_events_logged": len(parsed), "event_stream_events_replayed": len(replayed_events),
        "event_stream_divergences": stream_total,
        "event_stream_divergences_reported": len(stream_divergences),
        "problems": problems, "first_divergence_tick": first_divergence,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if problems:
        for problem in problems:
            print(f"E_VERIFY: {problem}", file=sys.stderr)
        print(f"verify: FAIL (first divergence tick = {first_divergence})")
        return 1
    print("verify: OK (chain self-consistent; per-checkpoint state_hash/rng_state_digest/"
          "event_chain_hash agree; INVARIANT-ECH-1/2/3 hold; event stream matches replay)")
    return 0


# --------------------------------------------------------------------------- validate / pack sign
def cmd_validate(args) -> int:
    try:
        pack = load_pack(resolve_pack_dir(args.pack))
    except PackInvalid as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    edges = build_portal_edges({pack.manifest["id"]: pack})
    inactive = [edge["id"] for edge in edges if edge["status"] == "inactive"]
    print(json.dumps({
        "command": "validate", "pack_id": pack.manifest["id"], "version": pack.manifest["version"],
        "engine_range": pack.manifest["engine_range"], "kernel_contract": KERNEL_CONTRACT_VERSION,
        "entities": len(pack.world_seed["entities"]), "npcs": len(pack.npcs),
        "buildings": len(pack.buildings), "tasks": len(pack.tasks), "schedules": len(pack.schedules),
        "portal_edges": len(edges), "inactive_portals": inactive,
        "weather_declared_and_dropped": "weather" in pack.world_seed,
    }, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_pack_sign(args) -> int:
    tool = _load_pack_sign_tool()
    pack_dir = Path(args.dir).resolve()
    try:
        signature = tool.build_signature(pack_dir)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1
    # 写侧唯一写入点（P-5）：`tools/pack_sign.py::write_signature` 内含 pack.sig 符号链接守卫，
    # 避免 `kernel pack sign` 与工具脚本各写一份（原先 CLI 侧直接 write_text ⇒ 会跟随链接改写包外文件）。
    try:
        out = tool.write_signature(pack_dir, signature)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"wrote {out} entries={len(signature['entries'])}")
    return 0


# --------------------------------------------------------------------------- 认知层（W3~W6）
# 树定义是**数据**（JSON 可表达，无代码分支）；同时落盘到 `<out>/cognition/tree.spec.json` 供审计。
COGNITION_TREE_SPEC = {
    "type": "selector",
    "children": [
        {
            "type": "sequence",
            "children": [
                {"type": "condition", "key": "needs_pressure", "op": ">=", "value": 0.30},
                {"type": "action", "slot": "intent.plan",
                 "payload": {"npc_id": "$npc_id", "tick": "$tick", "needs": "$needs",
                             "schedule_state": "$schedule_state", "candidate_actions": "$candidate_actions"},
                 "store_as": "plan"},
                {"type": "action", "slot": "emotion.appraise",
                 "payload": {"npc_id": "$npc_id", "tick": "$tick",
                             "event_summary": "$event_summary", "current_emotion": "$current_emotion"},
                 "store_as": "emotion"},
                {"type": "action", "slot": "relation.infer",
                 "payload": {"npc_id": "$npc_id", "tick": "$tick", "observations": "$observations",
                             "existing_relations": "$existing_relations"},
                 "store_as": "relations"},
            ],
        },
        {
            "type": "action", "slot": "emotion.appraise",
            "payload": {"npc_id": "$npc_id", "tick": "$tick",
                        "event_summary": "$event_summary", "current_emotion": "$current_emotion"},
            "store_as": "emotion",
        },
    ],
}
COGNITION_SLOTS = ("intent.plan", "emotion.appraise", "relation.infer", "embed.text")


def _capability_caps(capabilities: list[dict]) -> tuple[int, int]:
    """从能力契约的 `budget` 块派生预算上限（**数据驱动**，不硬编码数值）。

    tick 级上限 = 各能力**自声明** `budget.per_tick_calls` 之和
    （`BudgetLedger` 的 tick 级计数是全局的，因此把「每个能力各自的 tick 配额」求和
     才是与契约等价的账本口径；不做任何调参放大）。
    日级上限 = 各能力 `budget.per_npc_daily_tokens` 的**最小值**（最紧的那条约束生效）。
    """
    per_tick = [int(item["budget"]["per_tick_calls"]) for item in capabilities
                if isinstance(item.get("budget"), dict) and isinstance(item["budget"].get("per_tick_calls"), int)]
    daily = [int(item["budget"]["per_npc_daily_tokens"]) for item in capabilities
             if isinstance(item.get("budget"), dict) and isinstance(item["budget"].get("per_npc_daily_tokens"), int)]
    return (sum(per_tick) if per_tick else 2, min(daily) if daily else 65000)


def _candidate_actions(state: str) -> list[dict]:
    """日程状态 → 候选动作。

    **唯一权威已迁到 `rules/decision.py`**（`candidate_actions`）：本函数只是**导入别名**，
    避免「决策层与认知旁路各持一份表」的漂移（设计 §4.1）。
    """
    return candidate_actions(state)


def _build_cognition_registry(out_dir: Path, *, cassette_root: Path, replay_mode: bool = False) -> tuple[object, dict]:
    """装配 W3 注册表 + 四类 provider 适配器（返回 (registry, store)）。"""
    from .budget import BudgetLedger
    from .providers.cassette import CassetteReplayProvider, CassetteStore
    from .providers.deterministic_rule import DeterministicRuleProvider
    from .providers.local_model import LocalModelProvider
    from .providers.remote_api import RemoteApiProvider
    from .registry import CapabilityRegistry

    capabilities_dir = V0_SKELETON / "capabilities"
    store = CassetteStore(cassette_root)
    registry = CapabilityRegistry(capabilities_dir, capabilities_dir / "pins.json",
                                  cassette_store=store, clock=time.monotonic,
                                  replay_mode=bool(replay_mode))
    registry.register_adapter("remote_api", RemoteApiProvider())
    registry.register_adapter("local_model", LocalModelProvider())
    registry.register_adapter("deterministic_rule", DeterministicRuleProvider())
    registry.register_adapter("cassette_replay", CassetteReplayProvider(store))
    return registry, {"store": store, "budget_class": BudgetLedger}


def _run_cognition(pack, kernel, *, out_dir: Path, replay_mode: bool, memory_writes: bool,
                   cassette_dir: Path | None = None) -> dict:
    """认知层驱动（`kernel run --cognition` 的实现体）。

    **确定性边界（设计 §3.4b）**：本函数在 tick 循环**之外**运行；
    不调用 `WorldKernel.step`、不写 `world`、不取 `WorldRng` 的任何 stream
    ⇒ 默认路径的 `state_hash` / `chain_tail` 与不带 `--cognition` 时**逐位相同**。
    认知层产物一律落 `<out>/cognition/**`（**不写** run 的 `out/**` 主树）。
    """
    from .budget import BudgetLedger
    from .memory import retrieve as memory_retrieve
    from .memory.store import MemoryStore
    from .rules import behaviour_tree, requirement, utility

    cognition_dir = out_dir / "cognition"
    cognition_dir.mkdir(parents=True, exist_ok=True)
    (cognition_dir / "tree.spec.json").write_text(
        json.dumps(COGNITION_TREE_SPEC, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    registry, extra = _build_cognition_registry(
        out_dir, cassette_root=Path(cassette_dir) if cassette_dir is not None else cognition_dir / "cassettes",
        replay_mode=bool(replay_mode))
    registry.discover()
    validation_errors = registry.validate()

    documents = [registry.capability(slot) for slot in registry.slots()]
    per_tick_calls, daily_tokens = _capability_caps(documents)
    budget = BudgetLedger(day_ticks=int(pack.world_seed["constants"].get("day_ticks", 1440)),
                          per_tick_calls=per_tick_calls, per_npc_daily_tokens=daily_tokens)
    memory = MemoryStore(cognition_dir / "memory.sqlite", write_enabled=memory_writes)
    memory.init_schema()

    journal_path = cognition_dir / "cognition.jsonl"
    journal_path.write_text("", encoding="utf-8")
    npcs = kernel.world.query(kind="npc")
    seq = 0
    provider_counts: dict[str, int] = {}
    fallback_counts: dict[str, int] = {}
    fail_closed_events: list[dict] = []
    retrieval_digests: list[str] = []
    decisions: list[dict] = []

    def emit(record: dict) -> None:
        nonlocal seq
        seq += 1
        record["seq"] = seq
        with journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    for index, entity in enumerate(kernel.world.query(kind="npc")):
        components = entity.components
        needs = components.get("needs") or {}
        schedule = components.get("schedule") or {}
        state = str(schedule.get("state", "idle"))
        emotion = components.get("emotion") or {}
        relations = components.get("relations") or {}
        # 认知层按**每 tick 一个 NPC** 调度（tick 级预算按 tick 计；同一 tick 挤 5 个 NPC 会
        # 全部撞上 per_tick 上限而退化为降级 —— 那不是判据，是调度口径）。
        tick = max(1, int(kernel.world.tick) - (len(npcs) - 1 - index))
        blackboard = {
            "npc_id": entity.id,
            "tick": tick,
            "needs": needs,
            "needs_pressure": utility.need_pressure(needs, {}),
            "schedule_state": state,
            "candidate_actions": _candidate_actions(state),
            "event_summary": f"tick={tick} state={state} npc={entity.id}",
            "current_emotion": emotion,
            "observations": [{"subject": entity.id, "object": other, "kind": "talk",
                              "weight": float(relations[other])}
                             for other in sorted(relations) if isinstance(relations[other], (int, float))],
            "existing_relations": {key: relations[key] for key in sorted(relations)
                                   if isinstance(relations[key], (int, float))},
        }
        requirements = requirement.evaluate(needs, {"weights": {}, "npc_id": entity.id, "tick": tick})
        scored = utility.score_actions(needs, {}, {"schedule_state": state},
                                       [{"action": item["action"], "need": item["need"]} for item in
                                        blackboard["candidate_actions"]])
        calls_before = len(registry.calls)
        journal_before = len(registry.journal)
        hide_misses = os.environ.get(_NEGATIVE_HIDE_CASSETTE_MISS) == "1"
        try:
            outcome = behaviour_tree.run_tree(COGNITION_TREE_SPEC, blackboard, registry, budget)
        except (ValueError, CapabilityError) as error:
            # 树定义/槽位解析失败也是**结构化**失败（不得裸 traceback）
            emit({"event": "cognition.tree_error", "npc_id": entity.id, "tick": tick,
                  "error": type(error).__name__, "detail": str(error)[:200]})
            outcome = {"status": behaviour_tree.FAILURE, "keys": sorted(blackboard)}
        except CassetteMiss as error:
            # **修-2 / R-M2-2**：`--replay` 下的 cassette miss **不得**被吞 —— 结构化落 journal + 汇总，
            # 由 `cmd_run` 转成 exit 1 + `E_CASSETTE_MISS` 诊断（fail-closed，不降级、不切远端）。
            emit({"event": "cognition.tree_error", "npc_id": entity.id, "tick": tick,
                  "error": type(error).__name__, "detail": str(error)[:200], "fail_closed": True})
            outcome = {"status": behaviour_tree.FAILURE, "keys": sorted(blackboard)}
        except CassetteTampered as error:
            # **修-6 / R2-M2（收口轮）**：cassette **篡改**（链哈希失配）与 miss **同等可见** ——
            # 被篡改的回放源不得被树吞成 `on_error` 降级而命令层 exit 0。结构化落 journal + 汇总，
            # 由 `cmd_run` 转成 exit 1 + `E_CASSETTE_TAMPERED` 诊断（零回填、零远端切换）。
            emit({"event": "cognition.tree_error", "npc_id": entity.id, "tick": tick,
                  "error": type(error).__name__, "detail": str(error)[:200], "fail_closed": True})
            outcome = {"status": behaviour_tree.FAILURE, "keys": sorted(blackboard)}
        except Exception as error:  # noqa: BLE001 —— 其他未预期异常也要结构化（不得裸 traceback）
            emit({"event": "cognition.tree_error", "npc_id": entity.id, "tick": tick,
                  "error": type(error).__name__, "detail": str(error)[:200]})
            outcome = {"status": behaviour_tree.FAILURE, "keys": sorted(blackboard)}
        for entry in registry.journal[journal_before:]:
            if entry.get("event") == "capability.fallback":
                fallback_counts[entry.get("reason", "?")] = fallback_counts.get(entry.get("reason", "?"), 0) + 1
            if entry.get("event") == "cassette.miss" and not hide_misses:
                fail_closed_events.append(entry)
        for call in registry.calls[calls_before:]:
            emit({"event": "capability.call", "npc_id": entity.id, "tick": tick, **call})
        emit({
            "event": "cognition.cycle", "npc_id": entity.id, "tick": tick,
            "tree_status": outcome["status"], "blackboard_keys": outcome["keys"],
            "top_requirement": {"need_id": requirements[0].need_id, "deficit": requirements[0].deficit},
            "selected_action": scored[0]["action"] if scored else None,
            "plan": blackboard.get("plan"), "emotion": blackboard.get("emotion"),
            "relations": blackboard.get("relations"),
        })
        if outcome["status"] != behaviour_tree.SUCCESS:
            emit({"event": "cognition.degraded", "npc_id": entity.id, "tick": tick,
                  "errors": blackboard.get("__errors__", [])})

        if memory_writes and isinstance(blackboard.get("emotion"), dict):
            summary = f"{entity.id}@{tick} {state}"
            embedding_output = registry.invoke("embed.text", {"texts": [summary]}, budget=budget)
            vector = (embedding_output.output.get("vectors") or [[]])[0]
            ref = memory.remember("episodes", {
                "npc_id": entity.id, "tick": tick, "kind": "cognition",
                "text_summary": summary, "importance": float(blackboard["emotion"].get("importance", 0.0)),
                "refs": [f"tick:{tick}"], "embedding": vector,
            })
            memory.remember("working", {"npc_id": entity.id, "tick": tick, "kind": "cognition",
                                        "text_summary": summary})
            top = memory_retrieve.retrieve(memory, entity.id, vector, top_k=8)
            retrieval_digests.append(memory_retrieve.digest(top))
            emit({"event": "memory.write", "npc_id": entity.id, "tick": tick, "episode_ref": ref,
                  "retrieval_digest": retrieval_digests[-1], "top_k": len(top)})
        decisions.append({"npc_id": entity.id, "status": outcome["status"],
                          "action": scored[0]["action"] if scored else None})

    # 每一类 provider 的调用计数（从能力契约的数据派生，顺序确定）
    for slot in registry.slots():
        for provider in registry.capability(slot).get("providers", []):
            provider_counts[str(provider.get("class"))] = provider_counts.get(str(provider.get("class")), 0) + 1

    local_available = None
    for provider_class, adapter in sorted(registry._adapters.items()):  # noqa: SLF001 (诊断输出)
        if provider_class == "local_model" and hasattr(adapter, "available"):
            local_available = bool(adapter.available())

    chain_errors = extra["store"].verify_chain()
    report = {
        "command": "run --cognition",
        "registry": {"slots": registry.slots(), "validation_errors": validation_errors,
                     "provider_class_counts": provider_counts},
        "budget": {"per_tick_calls": per_tick_calls, "per_npc_daily_tokens": daily_tokens,
                   "daily_report": budget.daily_report(int(kernel.world.tick))},
        "memory": {"writes_enabled": memory_writes, "write_count": memory.write_count,
                   "retrieval_digests": retrieval_digests},
        "fallback_counts": fallback_counts,
        "registry_journal": registry.journal,
        "fail_closed_events": len(fail_closed_events),
        "degraded_reasons": sorted({str(entry.get("slot", "?")) for entry in fail_closed_events}),
        # **修-6 / R2-M2（收口轮）**：篡改计数提到 summary **顶层**（= journal 里 CassetteTampered
        # 事件数），不得只埋在嵌套字段里；`cassette_chain_errors` 仍保留明细。
        "cassette_tampered_events": sum(
            1 for entry in registry.journal
            if entry.get("event") in ("cassette.tampered", "provider.error")
            and entry.get("error") == "CassetteTampered"
        ),
        "local_model_available": local_available,
        "cassette_chain_errors": chain_errors,
        "cognition_events": seq,
        "decisions": decisions,
        "world_state_hash_after_cognition": kernel.state_hash(),
        "artifacts": {
            "dir": str(cognition_dir), "journal": str(journal_path),
            "tree_spec": str(cognition_dir / "tree.spec.json"),
            "cassettes": str(cognition_dir / "cassettes"),
            "memory_db": str(cognition_dir / "memory.sqlite"),
        },
        "claim_boundary": (
            "cognition artifacts live under <out>/cognition/** only; snapshot.state is untouched "
            "(no provider output / memory content / budget counters); the world rng streams are not "
            "consumed here, so state_hash and chain_tail are identical with and without --cognition"
        ),
    }
    (cognition_dir / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


# --------------------------------------------------------------------------- main
# --------------------------------------------------------------------------- live（M4）
#: 本进程内已启动的只读观察通道（`run --ws-port <n>` 用；进程退出即随 daemon 线程消失）
_LIVE_CHANNELS: list = []


def _stop_live_channels() -> list:
    """停掉本进程已启动的只读观察通道（**幂等**），返回**已停**的通道列表。

    **F7（r3）**：`server.stop()`（`shutdown()` + `server_close()` + 线程 join）必须**显式执行**——
    让 HTTP daemon 线程活到解释器 finalize，会在 finalize 期争用 `stderr` 锁 ⇒
    `Fatal Python error: _enter_buffered_busy` ⇒ **SIGABRT**。
    单条通道停失败**不得**跳过其余通道（收尾路径不因局部异常而扩大影响）。

    **FIX-6（r3）**：返回值供 `_write_live_diagnostics()` 在**停稳之后**取有界诊断样本
    （停之前取会漏掉收尾期间的 handler 异常）。
    """
    stopped: list = []
    while _LIVE_CHANNELS:
        server = _LIVE_CHANNELS.pop()
        try:
            server.stop()
        except Exception as exc:  # noqa: BLE001 — 收尾路径：记录并继续停其余通道，不上抛
            print(f"E_LIVE_STOP_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        stopped.append(server)
    return stopped


def _write_live_diagnostics(out_dir: Path, servers: list) -> dict | None:
    """把观察通道的**有界**诊断落一个**有界**文件（FIX-6 · r3；无异常 ⇒ 返回 None，不产残渣）。

    界（逐条给出）：条数 ≤ `HANDLER_ERROR_SAMPLES_MAX`（8）、每条 `repr` ≤
    `HANDLER_ERROR_REPR_MAX`（200）字符、文件 ≤ `max_samples × (repr_max + 128)` 字节
    ⇒ 单文件硬上限 ≈ 2.6KB（不是「大概很小」，是可算的上界）。
    `finish()` 吞掉的异常只落**计数**（`finish_errors` / `finish_error_kinds`），不落原文。
    """
    samples = [item for server in servers for item in getattr(server, "handler_error_samples", [])]
    finish_errors = sum(int(getattr(server, "finish_errors", 0)) for server in servers)
    finish_kinds: dict = {}
    for server in servers:
        for kind, count in (getattr(server, "finish_error_kinds", {}) or {}).items():
            finish_kinds[kind] = finish_kinds.get(kind, 0) + int(count)
    if not samples and not finish_errors:
        return None
    target = out_dir / "live_handler_errors.jsonl"
    lines = [json.dumps(item, ensure_ascii=False, sort_keys=True)
             for item in samples[:HANDLER_ERROR_SAMPLES_MAX]]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {
        "path": str(target),
        "samples_kept": len(lines),
        "bytes": target.stat().st_size,
        "bytes_bound": HANDLER_ERROR_SAMPLES_MAX * (HANDLER_ERROR_REPR_MAX + 128),
        "finish_errors": finish_errors,
        "finish_error_kinds": dict(sorted(finish_kinds.items())),
    }


class _StopFlag:
    """最小停止标志（`advance_loop(stop_event=...)` 只需要 `is_set()`）。"""

    __slots__ = ("_flag",)

    def __init__(self) -> None:
        self._flag = False

    def set(self) -> None:
        self._flag = True

    def is_set(self) -> bool:
        return self._flag


def _start_live_listener(kernel, pack, *, port: int, bind: str = DEFAULT_BIND,
                         allow_remote: bool = False, pace: float = 1.0, warmup: int = 0,
                         max_observers: int = MAX_OBSERVERS_DEFAULT):
    """装配并启动只读观察通道（`run` 与 `live` 共用同一实现）。

    世界钟语义从内容包派生（fail-closed：派生失败 ⇒ `ClockSemanticsError` 上抛，调用方转非 0 退出）。
    """
    sem = world_clock.derive_clock_semantics(pack)
    world = LiveWorld(kernel, sem=sem, pace_s_per_tick=pace, warmup=warmup,
                      max_observers=max_observers)
    server = LiveServer(world, bind=bind, port=port, allow_remote=allow_remote)
    server.start()
    return world, server


def _resume_payload(path: Path) -> dict:
    """读 `live_state.json`（不存在 / 非法 JSON ⇒ 结构化拒绝）。"""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PackInvalid(f"E_RESUME_STATE_INVALID: no such state file: {Path(path).name}")
    except (OSError, ValueError):
        raise PackInvalid("E_RESUME_STATE_INVALID: state file is not readable JSON")
    if not isinstance(document, dict):
        raise PackInvalid("E_RESUME_STATE_INVALID: state file must contain a JSON object")
    return document


def cmd_live(args) -> int:
    """活的世界：启动快进到当前 UTC+8 时刻 ⇒ 按真实时间推进 ⇒ 只读通道可观察。"""
    try:
        pack = load_pack(resolve_pack_dir(args.pack))
    except PackInvalid as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1

    # ① 服务边界：非 loopback 绑定必须显式 --allow-remote（**启动前**拒，不监听、不留半截产物）
    bind = str(args.bind)
    if not is_loopback(bind) and not args.allow_remote:
        print(
            f"E_BIND_REFUSED: refusing to bind {bind!r} without --allow-remote "
            "(the live channel is loopback-only by default; nothing was started)",
            file=sys.stderr,
        )
        return 2

    port = int(args.ws_port) if args.ws_port is not None else int(args.port)

    try:
        sem = world_clock.derive_clock_semantics(pack)
    except world_clock.ClockSemanticsError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = Path(args.events) if args.events else out_dir / "events.jsonl"
    checkpoint_dir = events_path.parent / "checkpoints"
    try:
        _refuse_unusable_output_dir(checkpoint_dir, label="live")
    except PackInvalid as exc:
        print(str(exc), file=sys.stderr)
        return 1

    seed = int(args.seed) if args.seed is not None else int(pack.world_seed.get("seed", 0))

    # ② 恢复语义（D-M4-18）：`live_state.json` 记 tick + seed + pack_id + pack_version，
    #    与当前 pack/seed 不匹配 ⇒ **结构化拒绝**（不得用「同 tick 同哈希」当跨 seed 的错觉证据）
    resume_tick = args.resume_tick
    if args.resume_state:
        try:
            sealed = _resume_payload(Path(args.resume_state))
        except PackInvalid as exc:
            print(str(exc), file=sys.stderr)
            return 1
        mismatches = []
        if int(sealed.get("seed", -1)) != seed:
            mismatches.append(f"seed {sealed.get('seed')} != {seed}")
        if sealed.get("pack_id") != pack.manifest["id"]:
            mismatches.append(f"pack_id {sealed.get('pack_id')!r} != {pack.manifest['id']!r}")
        if sealed.get("pack_version") != pack.manifest["version"]:
            mismatches.append(
                f"pack_version {sealed.get('pack_version')!r} != {pack.manifest['version']!r}")
        if mismatches:
            print("E_RESUME_STATE_MISMATCH: " + "; ".join(mismatches), file=sys.stderr)
            return 1
        resume_tick = int(sealed.get("tick", 0))

    # **恢复语义的日志边界（M4 新增，fail-closed）**：恢复是「同 seed + 同 pack + 快进到同一 tick」的
    # **确定性重放** ⇒ 若复用**已有**的事件日志，`EventLog` 会**追加**（第二个 `world.init` + seq 重复）
    # ⇒ 日志立刻不可核验。故：要恢复就必须指向一个**新的 / 空的**事件日志，否则结构化拒绝。
    if (args.resume_state or args.resume_tick is not None) and events_path.exists() \
            and events_path.stat().st_size > 0:
        print(
            f"E_RESUME_LOG_EXISTS: refusing to resume into a non-empty event log ({events_path.name}); "
            "resume re-plays from genesis, so reusing the log would append a second world.init and "
            "duplicate the seq chain. Point --events at a fresh path (the old log stays intact).",
            file=sys.stderr,
        )
        return 1

    # **FIX-1（r3）· 内核链入口（live 路径）**：默认 off ⇒ `chain_extra == {}`（与改前逐字节一致）。
    chain_extra, chain_state = _build_kernel_chain(args, out_dir=out_dir, pack=pack)
    kernel = WorldKernel(
        pack=pack, seed=seed, log=EventLog(events_path),
        snapshot_every=args.snapshot_every, checkpoint_dir=checkpoint_dir,
        plan_ticks=int(args.ticks) if args.ticks is not None else DEFAULT_PLAN_TICKS,
        **chain_extra,
    )
    if chain_state.get("memory_chain") or chain_state.get("capability_chain"):
        print("kernel chain: "
              f"memory={chain_state.get('memory_chain')} "
              f"(store={chain_state.get('memory_store_path')}) | "
              f"capability={chain_state.get('capability_chain')} "
              f"(emotion_pressure_threshold="
              f"{chain_state.get('emotion_pressure_threshold', 'default(0.6)')})")

    # ③ 启动锚定：快进到「此刻」（算式与实数都打印）
    wall = world_clock.now_utc8()
    warmup = 0 if args.no_warmup else world_clock.warmup_ticks(wall, sem)
    anchor_tick = int(resume_tick) if resume_tick is not None else warmup
    wall_minutes = wall.hour * 60 + wall.minute
    print(
        f"anchor: UTC+8 wall clock {wall.strftime('%H:%M')} ({wall_minutes} min into the day) | "
        f"warmup = (({wall_minutes}) - {sem['tick0_minutes']}) mod {sem['day_ticks']} = {warmup} ticks"
        + (f" | resume-tick override = {anchor_tick} ticks" if resume_tick is not None else "")
    )
    if anchor_tick > 0:
        kernel.run(anchor_tick)
    print(
        f"world clock after fast-forward: {world_clock.clock_of(kernel.world.tick, sem)} "
        f"(tick {kernel.world.tick}) | tick0 = "
        f"{sem['tick0_minutes'] // 60:02d}:{sem['tick0_minutes'] % 60:02d} | "
        f"pace = {args.pace} real-second(s) per world-minute"
    )

    # ④ 服务（只读；端口被占 ⇒ E_ADDRINUSE exit 1，不静默降级）
    live_world = LiveWorld(kernel, sem=sem, pace_s_per_tick=float(args.pace), warmup=warmup,
                           max_observers=int(args.max_observers))
    server = LiveServer(live_world, bind=bind, port=port, allow_remote=bool(args.allow_remote))
    try:
        server.start()
    except AddrInUse as exc:
        print(str(exc), file=sys.stderr)
        return 1

    policy = server.bind_policy()
    print(f"live channel: http://{server.bind}:{server.port} (read-only; "
          f"{'remote access ENABLED' if args.allow_remote else 'loopback only'})")
    if policy["warning"]:
        print(f"WARNING: {policy['warning']}")

    max_ticks = None
    if args.ticks is not None:
        max_ticks = int(args.ticks)
    if args.days is not None:
        day_ticks = int(sem["day_ticks"])
        by_days = int(float(args.days) * day_ticks)
        max_ticks = by_days if max_ticks is None else min(max_ticks, by_days)

    stop_flag = _StopFlag()

    def _request_stop(signum, _frame) -> None:
        print(f"signal {signum}: sealing the world after this tick", file=sys.stderr)
        stop_flag.set()

    for signal_name in ("SIGINT", "SIGTERM"):
        handler = getattr(signal, signal_name, None)
        if handler is not None:
            try:
                signal.signal(handler, _request_stop)
            except (ValueError, OSError):  # 非主线程 ⇒ 跳过（不影响功能）
                pass

    state_path = out_dir / "live_state.json"
    sealed: dict = {}
    seal_error: OSError | None = None
    try:
        loop = live_world.advance_loop(max_ticks=max_ticks, stop_event=stop_flag)
    finally:
        # **F7（r3）· 封存路径必须 fail-closed 且可观测**
        #
        # 旧形态：封存段**无 try/except**，且 `server.stop()` 排在 `write_text()` **之后**
        # ⇒ 写 `live_state.json` 抛 `OSError`（观察者负载打满 fd ⇒ `Errno 24`）时：
        # 摘要不打印、`server.stop()` **被跳过**、HTTP daemon 线程不停 ⇒ 解释器 finalize 期
        # 争用 stderr 锁 ⇒ `Fatal Python error: _enter_buffered_busy` ⇒ **SIGABRT**。
        # **因果方向：daemon 线程未停是果，跳过 `stop()` 是因。**
        # 修法：封存异常转**结构化错误**（非 0 退出 + stderr 一行诊断 + stdout 一行 JSON），
        # 且 `server.stop()` 放进**内层 finally** ⇒ 它在**任何**封存失败路径上都仍被执行
        # （内层 finally 对 OSError 之外的异常同样生效，异常随后按原样上抛）。
        try:
            sealed = live_world.seal_state()
            sealed.update({
                "seed": kernel.seed,
                "pack_id": pack.manifest["id"],
                "pack_version": pack.manifest["version"],
                "pace_s_per_tick": float(args.pace),
                "events": str(events_path),
            })
            state_path.write_text(json.dumps(sealed, ensure_ascii=False, sort_keys=True) + "\n",
                                  encoding="utf-8")
        except OSError as exc:
            seal_error = exc
        finally:
            server.stop()

    # **FIX-6（r3）**：停稳之后落有界诊断（无异常 ⇒ None，不产残渣文件）。
    live_diagnostics = _write_live_diagnostics(out_dir, [server])

    if seal_error is not None:
        detail = getattr(seal_error, "strerror", None) or str(seal_error)
        print(f"E_LIVE_STATE_SEAL_FAILED: cannot write {state_path.name}: "
              f"{type(seal_error).__name__}: {detail}", file=sys.stderr)
        print(json.dumps({
            "command": "live",
            "pack_id": pack.manifest["id"],
            "seed": kernel.seed,
            "bind": server.bind,
            "port": server.port,
            "sealed": False,
            # **派生读数**（不是字面 True）：`stop()` 正常执行会把这两个字段置 None
            "server_stopped": server.httpd is None and server.thread is None,
            "live_state": str(state_path),
            "error": "E_LIVE_STATE_SEAL_FAILED",
            "detail": f"{type(seal_error).__name__}: {detail}",
            "live_diagnostics": live_diagnostics,
            "read_only": True,
        }, ensure_ascii=False, sort_keys=True))
        return 1

    print(json.dumps({
        "command": "live",
        "pack_id": pack.manifest["id"],
        "seed": kernel.seed,
        "bind": server.bind,
        "port": server.port,
        "bind_policy": policy,
        "clock_semantics": sem,
        "warmup_ticks": warmup,
        "pace_s_per_tick": float(args.pace),
        "loop": loop,
        "state_hash": sealed["state_hash"],
        "event_chain_hash": sealed["event_chain_hash"],
        "live_state": str(state_path),
        "events": str(events_path),
        "live_diagnostics": live_diagnostics,
        "read_only": True,
    }, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "replay":
        return cmd_replay(args)
    if args.command == "verify":
        return cmd_verify(args)
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "live":
        return cmd_live(args)
    if args.command == "pack":
        if args.pack_command == "sign":
            return cmd_pack_sign(args)
    print(f"E_USAGE: unsupported command '{args.command}'", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
