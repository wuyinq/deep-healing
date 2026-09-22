"""AC-M1-3：端到端 `run` → 事件日志 → `replay` → `verify`（R5/R6/R7/R21）。

负例（自证可达）：
  R6  朴素整行截断 → verify exit≠0 且打印首个分歧 tick
  R7  篡改一条 payload → verify exit≠0 且打印首个分歧 tick
  R21 伪造日志（截断 + 改写 plan_ticks + 重算整条链 + 删多余检查点）：
      不传锚点 ⇒ exit 0（**声称边界**：只代表「确定性一致」，不代表「未被篡改」）；
      传**原始**链尾锚点 ⇒ exit≠0（anchor_mismatch）——C1 关闭判据。

冻结运行形态：cd <ws>/02_source/v0_skeleton/kernel && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK_REL = "districts/xingfu-xiaoqu"
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SEED = 20260921

from deephealing_kernel import snapshot as snapshot_mod  # noqa: E402

_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "deephealing_kernel", *args],
        capture_output=True, text=True, cwd=str(KERNEL_ROOT), env=_ENV,
    )


def _run(events: Path, ticks: int = 120, snapshot_every: int = 50) -> subprocess.CompletedProcess:
    events.parent.mkdir(parents=True, exist_ok=True)
    return _cli(
        "run", "--pack", PACK_REL, "--seed", str(SEED),
        "--events", str(events), "--snapshot-every", str(snapshot_every), "--ticks", str(ticks),
    )


def _out(proc: subprocess.CompletedProcess) -> str:
    return proc.stdout + proc.stderr


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_lines(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(obj, ensure_ascii=False) + "\n" for obj in lines), encoding="utf-8")


# --------------------------------------------------------------------------- R5
def test_e2e_run_then_verify_ok(tmp_path):
    """run exit 0 → verify exit 0 → replay 产物与 run 检查点逐点三字段一致。"""
    events = tmp_path / "e.jsonl"
    run = _run(events)
    assert run.returncode == 0, _out(run)
    assert events.is_file() and events.stat().st_size > 0

    verify = _cli("verify", "--events", str(events), "--pack", PACK_REL)
    assert verify.returncode == 0, _out(verify)
    assert "chain anchor: not provided" in verify.stdout, verify.stdout

    replay_out = tmp_path / "replay"
    replay = _cli(
        "replay", "--events", str(events), "--pack", PACK_REL,
        "--checkpoint-every", "50", "--out", str(replay_out),
    )
    assert replay.returncode == 0, _out(replay)
    # 修复轮 C9：replay 的检查点落 `<out>/checkpoints/`
    assert snapshot_mod.compare_checkpoints(tmp_path / "checkpoints", replay_out / "checkpoints") == []


# --------------------------------------------------------------------------- R6
def test_verify_detects_truncated_log(tmp_path):
    """朴素整行截断（不重算链）→ verify exit≠0，并打印首个分歧 tick。"""
    events = tmp_path / "e.jsonl"
    assert _run(events).returncode == 0

    lines = _read_lines(events)
    trunc_dir = tmp_path / "trunc"
    trunc_dir.mkdir()
    truncated = trunc_dir / "e.jsonl"
    _write_lines(truncated, lines[:-6])  # 只删尾部若干行，链本身仍连续

    verify = _cli("verify", "--events", str(truncated), "--pack", PACK_REL)
    assert verify.returncode != 0, _out(verify)
    assert re.search(r"truncated log", _out(verify)), _out(verify)
    assert re.search(r"first divergence tick", _out(verify)), _out(verify)


# --------------------------------------------------------------------------- R7
def test_verify_detects_tampered_payload(tmp_path):
    """篡改一条 payload（不重算 hash）→ verify exit≠0 且打印首个分歧 tick。"""
    events = tmp_path / "e.jsonl"
    assert _run(events).returncode == 0

    lines = _read_lines(events)
    index = next(i for i, obj in enumerate(lines) if obj["type"] == "npc.action")
    lines[index]["payload"]["action"] = "tampered_by_test"
    tamper_dir = tmp_path / "tamper"
    tamper_dir.mkdir()
    tampered = tamper_dir / "e.jsonl"
    _write_lines(tampered, lines)

    verify = _cli("verify", "--events", str(tampered), "--pack", PACK_REL)
    assert verify.returncode != 0, _out(verify)
    assert re.search(r"first divergence tick", _out(verify)), _out(verify)
    assert re.search(r"hash mismatch|chain", _out(verify), re.I), _out(verify)


# --------------------------------------------------------------------------- R21
def _forge_log(src_events: Path, dst_dir: Path, keep_max_tick: int) -> tuple[Path, str, str]:
    """构造伪造日志：截断到 keep_max_tick + 改写 world.init.plan_ticks + 按冻结公式重算整条链
    + 同步删除多余检查点（并把保留检查点的 event_chain_hash 改成重算后的链尾）。

    返回 (伪造日志路径, 原始链尾, 伪造链尾)。
    """
    original_lines = _read_lines(src_events)
    original_tail = original_lines[-1]["hash"]

    kept = [obj for obj in original_lines if obj["tick"] <= keep_max_tick]
    for obj in kept:
        if obj["type"] == "world.init":
            obj["payload"]["plan_ticks"] = keep_max_tick

    prev = snapshot_mod.GENESIS_HASH
    for obj in kept:
        # 伪造者必须同步改写快照事件 payload 的 event_chain_hash（= 追加前的链尾，INVARIANT-ECH-2），
        # 否则 ECH-2 会先把这条伪造链判红 —— 那就不构成 C1 所说的「重算整条链」攻击了。
        if obj["type"] == "snapshot.taken":
            obj["payload"]["event_chain_hash"] = prev
        body = {k: obj[k] for k in ("seq", "tick", "type", "actor", "payload")}
        digest = snapshot_mod.chained_hash(prev, body)
        obj["prev_hash"] = prev
        obj["hash"] = digest
        prev = digest
    forged_tail = prev

    dst_dir.mkdir(parents=True, exist_ok=True)
    forged = dst_dir / "e.jsonl"
    _write_lines(forged, kept)

    src_ckpt = src_events.parent / "checkpoints"
    dst_ckpt = dst_dir / "checkpoints"
    if dst_ckpt.exists():
        shutil.rmtree(dst_ckpt)
    dst_ckpt.mkdir(parents=True, exist_ok=True)
    tail_by_tick = {
        obj["payload"]["snapshot_tick"]: obj["hash"]
        for obj in kept
        if obj["type"] == "snapshot.taken"
    }
    for path in sorted(src_ckpt.glob("*.json")):
        tick = int(path.stem)
        if tick > keep_max_tick:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["event_chain_hash"] = tail_by_tick[tick]
        (dst_ckpt / path.name).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
    return forged, original_tail, forged_tail


# --------------------------------------------------------------------------- A1 伪造矩阵
FORGERY_MODES = (
    "truncate_rechain",
    "drop_mid_npc_actions",
    "tamper_mid_payload",
    "drop_snapshot_event",
    "drop_one_and_change_last_actor",
)

# 由**事件流比对**判红的伪造（修复轮 A1 的关闭面）。`truncate_rechain` **不在**此集合：
# 「截断 + 改写 plan_ticks + 重算整链 + 同步改写检查点」产出的是一条**自洽前缀**，重放会**合法地**
# 复现该前缀 ⇒ 事件流比对结构上不可见；它**只能**由链外锚点 `--expected-hash` 关闭（见本文件
# `test_forged_log_matrix` 的断言与 `06` 的 A1 行）。
EVENT_STREAM_CAUGHT = frozenset(FORGERY_MODES) - {"truncate_rechain"}


def _rechain_and_fix_checkpoints(kept: list[dict], src_ckpt: Path, dst_ckpt: Path) -> str:
    """按冻结公式重算整条链，并同步改写 `snapshot.taken` payload 与检查点文件，使伪造**自洽**。

    自洽 = 「日志链 + `snapshot.taken` payload 的 `event_chain_hash` + 检查点文件的
    `event_chain_hash`」三处一起重算 ⇒ ECH-1/2/3 与检查点交叉核对**都不会**报警，
    于是「是否被抓住」只取决于**事件流比对**（归因干净）。
    """
    prev = snapshot_mod.GENESIS_HASH
    for obj in kept:
        if obj["type"] == "snapshot.taken":
            obj["payload"]["event_chain_hash"] = prev
        body = {k: obj[k] for k in ("seq", "tick", "type", "actor", "payload")}
        digest = snapshot_mod.chained_hash(prev, body)
        obj["prev_hash"] = prev
        obj["hash"] = digest
        prev = digest

    if dst_ckpt.exists():
        shutil.rmtree(dst_ckpt)
    dst_ckpt.mkdir(parents=True, exist_ok=True)
    tail_by_tick = {
        obj["payload"]["snapshot_tick"]: obj["hash"]
        for obj in kept
        if obj["type"] == "snapshot.taken"
    }
    for path in sorted(src_ckpt.glob("*.json")):
        tick = int(path.stem)
        if tick not in tail_by_tick:      # 该 tick 的快照事件已被删除 ⇒ 检查点也必须删
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        document["event_chain_hash"] = tail_by_tick[tick]
        (dst_ckpt / path.name).write_text(
            json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
    return prev


def _forge(src_events: Path, dst_dir: Path, mode: str) -> tuple[Path, str, str]:
    """构造 5 类**完全自洽**的伪造日志。返回 (伪造日志, 原始链尾, 伪造链尾)。"""
    original = _read_lines(src_events)
    original_tail = original[-1]["hash"]
    kept = [json.loads(json.dumps(obj)) for obj in original]

    if mode == "truncate_rechain":
        kept = [obj for obj in kept if obj["tick"] <= 100]
        for obj in kept:
            if obj["type"] == "world.init":
                obj["payload"]["plan_ticks"] = 100
    elif mode == "drop_mid_npc_actions":
        positions = [index for index, obj in enumerate(kept) if obj["type"] == "npc.action"]
        for index in sorted(positions[5:20], reverse=True):
            kept.pop(index)
    elif mode == "tamper_mid_payload":
        index = next(i for i, obj in enumerate(kept) if obj["type"] == "npc.action" and obj["tick"] >= 10)
        kept[index]["payload"]["action"] = "hold"
        kept[index]["payload"]["duration_ticks"] = 999
    elif mode == "drop_snapshot_event":
        index = next(i for i, obj in enumerate(kept)
                     if obj["type"] == "snapshot.taken" and obj["tick"] == 150)
        kept.pop(index)
    elif mode == "drop_one_and_change_last_actor":
        positions = [index for index, obj in enumerate(kept) if obj["type"] == "npc.action"]
        kept.pop(positions[len(positions) // 2])
        kept[-1]["actor"] = "attacker"
    else:
        raise AssertionError(f"unknown forgery mode: {mode}")

    for index, obj in enumerate(kept):   # `seq` 允许被重编号（比对不比 seq）
        obj["seq"] = index

    dst_dir.mkdir(parents=True, exist_ok=True)
    forged = dst_dir / "e.jsonl"
    forged_tail = _rechain_and_fix_checkpoints(kept, src_events.parent / "checkpoints", dst_dir / "checkpoints")
    _write_lines(forged, kept)
    return forged, original_tail, forged_tail


def test_forged_log_matrix(tmp_path):
    """修复轮 A1 关闭判据：5 类伪造 × {无锚点, 事件流比对, 有锚点}。

    期望（**逐条如实**，不含修饰）：
      - `drop_mid_npc_actions` / `tamper_mid_payload` / `drop_snapshot_event` /
        `drop_one_and_change_last_actor`：**无锚点也必须 exit≠0**，且归因是 `event_stream:`（新面）；
      - `truncate_rechain`：无锚点仍 exit 0（**自洽前缀，结构上不可见**），**必须**由
        `--expected-hash` 判红 —— 这正是「事件流比对不能替代链外锚点，两者互补」的证据；
      - 未篡改日志必须仍 exit 0（防恒红）。
    """
    events = tmp_path / "e.jsonl"
    assert _run(events, ticks=200, snapshot_every=50).returncode == 0
    baseline = _cli("verify", "--events", str(events), "--pack", PACK_REL)
    assert baseline.returncode == 0, _out(baseline)

    caught_by_stream: list[str] = []
    for mode in FORGERY_MODES:
        forged, original_tail, forged_tail = _forge(events, tmp_path / mode, mode)

        no_anchor = _cli("verify", "--events", str(forged), "--pack", PACK_REL)
        with_anchor = _cli(
            "verify", "--events", str(forged), "--pack", PACK_REL, "--expected-hash", original_tail
        )
        self_anchor = _cli(
            "verify", "--events", str(forged), "--pack", PACK_REL, "--expected-hash", forged_tail
        )

        # 锚点必须对**全部** 5 类伪造判红（含自洽前缀那一类）
        assert with_anchor.returncode != 0, f"{mode}: anchor must catch it"
        assert "anchor_mismatch" in _out(with_anchor), _out(with_anchor)

        if mode in EVENT_STREAM_CAUGHT:
            assert no_anchor.returncode != 0, f"{mode}: event-stream comparison must catch it"
            assert "event_stream:" in _out(no_anchor), _out(no_anchor)
            # 这 4 类的日志与**自身重放**不一致（中段事件被删/改）⇒ 即便传伪造自身链尾也必红，
            # 红的归因是事件流比对而不是锚点（证明锚点不是唯一的检出路径）
            assert self_anchor.returncode != 0, f"{mode}: self-consistent replay must still fail"
            assert "event_stream:" in _out(self_anchor), _out(self_anchor)
            caught_by_stream.append(mode)
        else:
            # 如实断言残余：自洽前缀伪造在无锚点时**仍然**是绿的
            assert no_anchor.returncode == 0, f"{mode}: expected the documented residual (exit 0)"
            # 它是一条**自洽**日志（重放能复现它）⇒ 传它自己的链尾必须 exit 0
            # （证明「锚点比较」不是恒红，也证明该类的唯一检出路径确实是链外锚点）
            assert self_anchor.returncode == 0, f"{mode}: self-anchor must be green\n{_out(self_anchor)}"

    assert sorted(caught_by_stream) == sorted(EVENT_STREAM_CAUGHT), caught_by_stream

    # 未篡改日志 + 正确锚点 ⇒ exit 0（防恒红）
    original_tail = _read_lines(events)[-1]["hash"]
    ok = _cli("verify", "--events", str(events), "--pack", PACK_REL, "--expected-hash", original_tail)
    assert ok.returncode == 0, _out(ok)


def test_event_stream_comparison_excludes_nothing():
    """F2：比对豁免面必须**为空集**——任何 payload 字段（含 `checkpoint_path`）都在比对面内。

    修复轮 1 曾把 `checkpoint_path` 整体剔除，Raven 实证那是一条**被 verify 祝福的篡改通道**
    （末条快照 / 无快照事件的日志可任意改写该字段而 exit 0）。收紧的前提是「该字段在
    run / replay / verify 三条路径上取值恒定」——由 `tick._take_and_write_checkpoint` 保证。
    """
    from deephealing_kernel import cli as cli_mod

    assert cli_mod.EVENT_STREAM_LOCATOR_KEYS == frozenset(), cli_mod.EVENT_STREAM_LOCATOR_KEYS
    assert "NO exempt keys" in cli_mod.CLAIM_BOUNDARY


def _forge_locator(src_events: Path, dst_dir: Path, *, last_only: bool) -> tuple[Path, str, str]:
    """构造 N8/N9：只改 `checkpoint_path` + 重算整链 + 同步改检查点（其余字段一字不动）。"""
    original = _read_lines(src_events)
    original_tail = original[-1]["hash"]
    kept = [json.loads(json.dumps(obj)) for obj in original]

    if last_only:                                     # N8：只改**末条** snapshot.taken
        index = max(i for i, obj in enumerate(kept) if obj["type"] == "snapshot.taken")
    else:                                             # N9：改**任意中段** npc.action
        index = next(i for i, obj in enumerate(kept) if obj["type"] == "npc.action" and obj["tick"] >= 10)
    kept[index]["payload"]["checkpoint_path"] = "../../outside/SMUGGLED.json"

    for position, obj in enumerate(kept):
        obj["seq"] = position
    dst_dir.mkdir(parents=True, exist_ok=True)
    forged = dst_dir / "e.jsonl"
    forged_tail = _rechain_and_fix_checkpoints(kept, src_events.parent / "checkpoints", dst_dir / "checkpoints")
    _write_lines(forged, kept)
    return forged, original_tail, forged_tail


def test_locator_key_tampering_is_caught(tmp_path):
    """F2 关闭判据（Raven R15）：N8 / N9 都必须 exit≠0，归因 `payload_diff:field=checkpoint_path`。

    N8 = 只改**末条** `snapshot.taken.payload.checkpoint_path`（其后无快照事件 ⇒ 修复轮 1 的
    「偶然链耦合」消失，当时 exit 0）；N9 = `--snapshot-every 0`（无任何快照事件）时改**中段**
    `npc.action` 的该字段（当时 exit 0）。
    """
    events = tmp_path / "e.jsonl"
    assert _run(events, ticks=200, snapshot_every=50).returncode == 0
    assert _cli("verify", "--events", str(events), "--pack", PACK_REL).returncode == 0

    forged, original_tail, _ = _forge_locator(events, tmp_path / "n8", last_only=True)
    proc = _cli("verify", "--events", str(forged), "--pack", PACK_REL)
    assert proc.returncode != 0, f"N8（末条定位符）必须判红\n{_out(proc)}"
    assert "payload_diff" in _out(proc) and "field=checkpoint_path" in _out(proc), _out(proc)
    assert "SMUGGLED" in _out(proc), _out(proc)
    anchored = _cli("verify", "--events", str(forged), "--pack", PACK_REL,
                    "--expected-hash", original_tail)
    assert anchored.returncode != 0 and "anchor_mismatch" in _out(anchored)

    # N9：无快照事件的日志（`--snapshot-every 0`）⇒ 中段 npc.action 的定位符
    no_snapshot = tmp_path / "nosnap" / "e.jsonl"
    assert _run(no_snapshot, ticks=60, snapshot_every=0).returncode == 0
    assert _cli("verify", "--events", str(no_snapshot), "--pack", PACK_REL).returncode == 0
    forged9, original_tail9, _ = _forge_locator(no_snapshot, tmp_path / "n9", last_only=False)
    proc9 = _cli("verify", "--events", str(forged9), "--pack", PACK_REL)
    assert proc9.returncode != 0, f"N9（无快照事件时的中段定位符）必须判红\n{_out(proc9)}"
    assert "payload_diff" in _out(proc9) and "field=checkpoint_path" in _out(proc9), _out(proc9)
    anchored9 = _cli("verify", "--events", str(forged9), "--pack", PACK_REL,
                     "--expected-hash", original_tail9)
    assert anchored9.returncode != 0 and "anchor_mismatch" in _out(anchored9)

    # 防恒红：干净日志 + 未篡改的 replay 产物仍必须 exit 0
    assert _cli("verify", "--events", str(events), "--pack", PACK_REL).returncode == 0
    assert _cli("verify", "--events", str(no_snapshot), "--pack", PACK_REL).returncode == 0


def test_verify_problems_are_deduplicated(tmp_path):
    """F6（Sentinel Bug#15）：检查点**集合级**错误在 `problems` 里只出现 1 次，exit 仍 1。"""
    events = tmp_path / "e.jsonl"
    assert _run(events, ticks=6, snapshot_every=3).returncode == 0
    shutil.copy(tmp_path / "checkpoints" / "000006.json", tmp_path / "checkpoints" / "6.json")

    proc = _cli("verify", "--events", str(events), "--pack", PACK_REL)
    assert proc.returncode == 1, _out(proc)
    report = json.loads([line for line in proc.stdout.splitlines() if line.startswith("{")][0])
    problems = report["problems"]
    assert sum("non_canonical_filename:6.json" in item for item in problems) == 1, problems
    assert sum("duplicate_tick:6" in item for item in problems) == 1, problems
    assert len(problems) == len(set(problems)), "problems 不得有逐字重复条目"


def test_run_refuses_checkpoints_path_that_is_not_a_directory(tmp_path):
    """F3（Raven R23.2）：`checkpoints` 是**普通文件**时 `run` 必须 fail-closed，无 traceback、无半截日志。"""
    events = tmp_path / "e.jsonl"
    blocker = tmp_path / "checkpoints"
    blocker.write_text("not a directory\n", encoding="utf-8")

    proc = _run(events, ticks=120, snapshot_every=50)
    assert proc.returncode != 0, _out(proc)
    combined = _out(proc)
    assert "E_EVENTS_EXISTS" in combined, combined
    assert "exists but is not a directory" in combined, combined
    assert "Traceback" not in combined, combined          # 不得是未捕获的 FileExistsError
    assert not events.exists() or events.stat().st_size == 0, "不得留下半截日志"
    assert blocker.read_text(encoding="utf-8") == "not a directory\n"   # 不得改动既有文件

    # 反向对照：清掉该文件 ⇒ 同一条命令 exit 0
    blocker.unlink()
    assert _run(events, ticks=50, snapshot_every=50).returncode == 0


def test_event_stream_report_is_capped(tmp_path):
    """修复轮：一处中段删除会让其后每条都失配 ⇒ 明细行必须**有上限**，但**总数**必须真实。"""
    from deephealing_kernel import cli as cli_mod

    events = tmp_path / "e.jsonl"
    assert _run(events, ticks=60, snapshot_every=30).returncode == 0
    forged, original_tail, _ = _forge(events, tmp_path / "cap", "drop_mid_npc_actions")
    proc = _cli("verify", "--events", str(forged), "--pack", PACK_REL)
    assert proc.returncode != 0, _out(proc)

    report = json.loads([line for line in proc.stdout.splitlines() if line.startswith("{")][0])
    total = report["event_stream_divergences"]
    assert total > cli_mod.MAX_DIVERGENCES, total          # 否则本用例不构成「刷屏」场景
    assert report["event_stream_divergences_reported"] == cli_mod.MAX_DIVERGENCES + 1
    assert report["first_divergence_tick"] is not None
    # 明细行数必须有上限（+1 条 truncated_report 汇总）；JSON 报告行与摘要行不算
    detail_lines = [line for line in _out(proc).splitlines() if line.startswith("E_VERIFY: event_stream:")]
    assert len(detail_lines) <= cli_mod.MAX_DIVERGENCES + 1, len(detail_lines)
    assert any("truncated_report" in line and f"total={total}" in line for line in detail_lines), detail_lines[-1:]


def test_claim_boundary_is_rewritten_for_event_stream_strength(tmp_path):
    """A2：`verify` 输出的 `claim_boundary` 必须按新强度改写，且仍明确「不代表未被篡改」。"""
    path = tmp_path / "e.jsonl"
    assert _run(path).returncode == 0
    proc = _cli("verify", "--events", str(path), "--pack", PACK_REL)
    assert proc.returncode == 0, _out(proc)
    report = json.loads([line for line in proc.stdout.splitlines() if line.startswith("{")][0])
    boundary = report["claim_boundary"]
    assert "event stream agrees with the replay" in boundary
    assert "does NOT mean" in boundary
    assert "--expected-hash" in boundary
    assert report["event_stream_compared"] is True
    assert report["event_stream_divergences"] == 0
    assert report["event_stream_events_logged"] == report["event_stream_events_replayed"]


def test_run_refuses_stale_checkpoints_without_log(tmp_path):
    """C7：删日志、留旧检查点、用更少 `--ticks` 重跑 ⇒ `run` 必须非 0（原先 exit 0 后由 verify 假红）。"""
    events = tmp_path / "e.jsonl"
    assert _run(events, ticks=120, snapshot_every=50).returncode == 0
    assert sorted(path.name for path in (tmp_path / "checkpoints").glob("*.json")) == [
        "000050.json", "000100.json"
    ]

    events.unlink()                       # 只清「一半」：日志删掉，检查点留着
    rerun = _run(events, ticks=50, snapshot_every=50)
    assert rerun.returncode != 0, _out(rerun)
    assert "E_EVENTS_EXISTS" in _out(rerun), _out(rerun)
    assert "checkpoint directory must be explicitly cleared" in _out(rerun), _out(rerun)

    # 反向对照：整棵产物树都清掉 ⇒ 同一条命令 exit 0
    shutil.rmtree(tmp_path / "checkpoints")
    assert _run(events, ticks=50, snapshot_every=50).returncode == 0


def test_pack_fallback_note_is_printed():
    """C6：`--pack` 回退命中时必须显式打印（避免「路径写错」看起来像成功）。"""
    proc = _cli("validate", "--pack", "districts/xingfu-xiaoqu")
    assert proc.returncode == 0, _out(proc)
    assert "note: --pack resolved via fallback to" in proc.stdout, proc.stdout

    # 反向对照：直接命中（cwd 相对存在）时不打印该 note
    direct = _cli("validate", "--pack", "../districts/xingfu-xiaoqu")
    assert direct.returncode == 0, _out(direct)
    assert "resolved via fallback" not in direct.stdout, direct.stdout


def test_verify_anchor_expected_hash(tmp_path):
    """C1 关闭判据：`--expected-hash` 是链外锚点且 fail-closed；未传锚点时必须明示声称边界。"""
    events = tmp_path / "e.jsonl"
    assert _run(events).returncode == 0
    good = _cli("verify", "--events", str(events), "--pack", PACK_REL)
    assert good.returncode == 0, _out(good)

    forged, original_tail, forged_tail = _forge_log(events, tmp_path / "forged", keep_max_tick=100)

    # ① 未传锚点 ⇒ 伪造日志**允许** exit 0（声称边界：只证明「确定性一致」），但必须打印未提供锚点
    no_anchor = _cli("verify", "--events", str(forged), "--pack", PACK_REL)
    assert no_anchor.returncode == 0, _out(no_anchor)
    assert "chain anchor: not provided" in no_anchor.stdout, no_anchor.stdout

    # ② 传**原始**链尾 ⇒ 必须 exit≠0（anchor_mismatch）——这条才是抗改写判据
    with_anchor = _cli(
        "verify", "--events", str(forged), "--pack", PACK_REL, "--expected-hash", original_tail
    )
    assert with_anchor.returncode != 0, _out(with_anchor)
    assert "anchor_mismatch" in _out(with_anchor), _out(with_anchor)

    # ③ 正向对照：传伪造日志自身的链尾 ⇒ exit 0（证明锚点比较真的在跑，不是恒红）
    self_anchor = _cli(
        "verify", "--events", str(forged), "--pack", PACK_REL, "--expected-hash", forged_tail
    )
    assert self_anchor.returncode == 0, _out(self_anchor)

    # ④ 未篡改日志 + 正确锚点 ⇒ exit 0
    ok_anchor = _cli(
        "verify", "--events", str(events), "--pack", PACK_REL, "--expected-hash", original_tail
    )
    assert ok_anchor.returncode == 0, _out(ok_anchor)


def test_verify_rejects_wrong_pack_and_bad_usage(tmp_path):
    """用法/环境负例：不存在的 pack → 非 0；未知子命令 → 2（用法错误）。"""
    events = tmp_path / "e.jsonl"
    assert _run(events).returncode == 0

    missing = _cli("verify", "--events", str(events), "--pack", "districts/does-not-exist")
    assert missing.returncode != 0, _out(missing)

    usage = _cli("not-a-command")
    assert usage.returncode == 2, _out(usage)


def test_run_refuses_nonempty_event_log(tmp_path):
    """fail-closed：目标日志非空时 `run` 必须拒绝，不得静默追加。

    静默追加会让同一文件里出现第二条 `seq=0` 的链（现场被污染）；静默截断会销毁既有证据。
    重跑必须显式清空输出目录。
    """
    events = tmp_path / "e.jsonl"
    assert _run(events, ticks=10, snapshot_every=5).returncode == 0
    size_before = events.stat().st_size
    assert size_before > 0

    second = _run(events, ticks=10, snapshot_every=5)
    assert second.returncode != 0, _out(second)
    assert "E_EVENTS_EXISTS" in _out(second), _out(second)
    assert events.stat().st_size == size_before, "拒绝启动不得改动既有日志"

    # 反向对照：干净目录下同一条命令必须 exit 0
    assert _run(tmp_path / "fresh" / "e.jsonl", ticks=10, snapshot_every=5).returncode == 0

    # replay 同理：非空 replay.jsonl ⇒ 拒绝
    out_dir = tmp_path / "replay_out"
    assert _cli("replay", "--events", str(events), "--pack", PACK_REL,
                "--checkpoint-every", "5", "--out", str(out_dir)).returncode == 0
    again = _cli("replay", "--events", str(events), "--pack", PACK_REL,
                 "--checkpoint-every", "5", "--out", str(out_dir))
    assert again.returncode != 0, _out(again)
    assert "E_EVENTS_EXISTS" in _out(again), _out(again)
