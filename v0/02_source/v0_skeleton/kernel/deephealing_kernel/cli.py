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

`--ws-port` 本轮**接受但不监听**（起服务属 W8）；`--replay` 本轮**接受但无效果**
（能力强制走 cassette_replay 属 W3，本轮无能力调用）——两者都会在 stdout 显式打印，不留白。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from . import KERNEL_CONTRACT_VERSION
from . import snapshot as snapshot_mod
from .events import EventChainError, EventLog, check_ech_invariants
from .pack import PackInvalid, build_portal_edges, load_pack
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
    run.add_argument("--ws-port", type=int, default=8787)
    run.add_argument("--replay", action="store_true", help="回放模式：能力强制走 cassette_replay 且 fail-closed")
    run.add_argument("--ticks", type=int, default=DEFAULT_PLAN_TICKS,
                     help="[加法扩展] 推进的 tick 数上界（默认 300）；冻结命令面本无终止参数")

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

    pack = sub.add_parser("pack", help="内容包工具")
    pack_sub = pack.add_subparsers(dest="pack_command", required=True)
    sign = pack_sub.add_parser("sign", help="重新生成 pack.sig")
    sign.add_argument("dir")

    return parser


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


def _refuse_existing_replay_outputs(out_dir: Path) -> None:
    """`replay` 侧的对称检查（修复轮 C7）：`replay.jsonl` 非空 或 已有检查点 ⇒ 拒绝。"""
    reasons: list[str] = []
    replay_log = out_dir / "replay.jsonl"
    if replay_log.exists() and replay_log.stat().st_size > 0:
        reasons.append(f"non-empty replay log {replay_log}")
    checkpoint_dir = out_dir / "checkpoints"
    if checkpoint_dir.is_dir():
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
    except PackInvalid as exc:
        print(str(exc), file=sys.stderr)
        return 1
    kernel = WorldKernel(
        pack=pack,
        seed=args.seed,
        log=EventLog(events_path),
        snapshot_every=args.snapshot_every,
        checkpoint_dir=checkpoint_dir,
        tick_rate=args.tick_rate,
        plan_ticks=args.ticks,
    )
    kernel.run(args.ticks)
    if args.replay:
        print("note: --replay is a W3 (capability provider) switch; M1 makes no capability calls => no effect")
    print(f"note: --ws-port {args.ws_port} accepted but NOT listened on (serving is W8)")
    print(json.dumps({
        "command": "run", "pack_id": pack.manifest["id"], "seed": kernel.seed,
        "ticks": args.ticks, "snapshot_every": kernel.snapshot_every,
        "events": str(events_path), "checkpoints": str(checkpoint_dir),
        "chain_tail": kernel.log.last_hash if kernel.log is not None else None,
        "event_count": kernel.log._seq if kernel.log is not None else 0,  # noqa: SLF001 (诊断输出)
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
    out = pack_dir / "pack.sig"
    out.write_text(json.dumps(signature, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} entries={len(signature['entries'])}")
    return 0


# --------------------------------------------------------------------------- main
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
    if args.command == "pack":
        if args.pack_command == "sign":
            return cmd_pack_sign(args)
    print(f"E_USAGE: unsupported command '{args.command}'", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
