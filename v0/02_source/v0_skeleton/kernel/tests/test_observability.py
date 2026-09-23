"""W9 观测层判据（AC-M4-2 / AC-8；设计 §2 D-M4-8、§11 D-M4-15①⑥）。

① `replay --out <dir> --checkpoint-every <n>` 的检查点数 == `ticks / snapshot_every`
   —— 用**日志记录的** `snapshot_every`（预审 L6），且比较前有**非空断言**（D-M4-15①）；
   反例：故意传不同的 `--checkpoint-every` ⇒ 该谓词**必须**为假（证明不是恒真）。
② 哈希链自检 **0 断链**；反例：复制日志造一处断链 ⇒ 自检**必须非零**（AC-M4-2④）。
③ 分析**只读**：跑分析前后 `events.jsonl` 的 sha256 与内核 `state_hash` 逐字节不变；
   反例：对副本追加一行 ⇒ 同一比较函数**必须**报变化（证明该判据不是零命中绿）。
④ 四组分析必须带 `sql_equivalent` 口径映射；SQL 文本**不得**含写语句；反例：注入一条 `INSERT`
   ⇒ 该静态检查必须变红。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SEED = 20260921
TOOLS = KERNEL_ROOT / "tools"
ENV = {"PYTHONDONTWRITEBYTECODE": "1"}

sys.path.insert(0, str(KERNEL_ROOT))
sys.path.insert(0, str(TOOLS))

import observability_report as obs  # noqa: E402


def _cli(*args: str) -> subprocess.CompletedProcess:
    import os
    return subprocess.run([sys.executable, "-m", "deephealing_kernel", *args],
                          capture_output=True, text=True, cwd=str(KERNEL_ROOT),
                          env=dict(os.environ, **ENV))


def _run(tmp_path: Path, *, ticks: int = 300, snapshot_every: int = 50) -> Path:
    events = tmp_path / "run" / "events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)
    proc = _cli("run", "--ws-port", "0", "--pack", str(PACK_DIR), "--seed", str(SEED),
                "--events", str(events), "--snapshot-every", str(snapshot_every),
                "--ticks", str(ticks))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return events


def _logged_snapshot_every(events: Path) -> int:
    """从日志的 `world.init` 读**生效的** `snapshot_every`（唯一权威）。"""
    with events.open("r", encoding="utf-8") as handle:
        for line in handle:
            document = json.loads(line)
            if document.get("type") == "world.init":
                return int(document["payload"]["snapshot_every"])
    raise AssertionError("no world.init event in log")


# ---------------------------------------------------------------------------- ① 检查点数
def test_replay_checkpoint_count_matches_logged_snapshot_every(tmp_path):
    events = _run(tmp_path, ticks=300, snapshot_every=50)
    logged = _logged_snapshot_every(events)
    assert logged == 50, f"日志记录的 snapshot_every 应为 50，实测 {logged}"

    out = tmp_path / "ckpt"
    proc = _cli("replay", "--events", str(events), "--pack", str(PACK_DIR),
                "--checkpoint-every", str(logged), "--out", str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["snapshot_every_from_log"] == logged

    checkpoints = sorted((out / "checkpoints").glob("*.json"))
    expected = 300 // logged
    # **非空断言先行**（D-M4-15①：空目录不得被判成「一致」）
    assert checkpoints, "replay 未写出任何检查点 ⇒ 后面的计数断言无意义"
    assert len(checkpoints) == expected, (
        f"检查点数应为 ticks/snapshot_every = 300/{logged} = {expected}，实测 {len(checkpoints)}")
    assert [path.name for path in checkpoints] == [
        f"{tick:06d}.json" for tick in range(logged, 301, logged)]

    # 反例（D-M4-15⑥）：故意传不同的 `--checkpoint-every` ⇒ 同一谓词**必须**为假
    other_out = tmp_path / "ckpt_other"
    proc_other = _cli("replay", "--events", str(events), "--pack", str(PACK_DIR),
                      "--checkpoint-every", "100", "--out", str(other_out))
    assert proc_other.returncode == 0, proc_other.stdout + proc_other.stderr
    other = sorted((other_out / "checkpoints").glob("*.json"))
    assert len(other) == 3, f"传 100 时应写 3 个检查点，实测 {len(other)}"
    assert len(other) != expected, (
        "传不同 --checkpoint-every 后计数仍相同 ⇒ 上面那条判据是恒真判据（零命中绿）")


# ---------------------------------------------------------------------------- ② 哈希链自检
def test_hash_chain_self_check_reports_zero_broken_links(tmp_path):
    events = _run(tmp_path, ticks=60, snapshot_every=30)
    report = obs.analyze(events)
    assert report["hash_chain"]["events"] > 0, "日志为空 ⇒ 自检无意义"
    assert report["hash_chain"]["broken_links"] == 0, report["hash_chain"]["broken_detail"]
    assert report["hash_chain"]["chain_tail"] != "0" * 64


def test_hash_chain_self_check_goes_red_on_an_injected_broken_link(tmp_path):
    """反例：复制日志并人为造一处断链 ⇒ 自检**必须**非零（AC-M4-2④）。"""
    events = _run(tmp_path, ticks=60, snapshot_every=30)
    original = obs.analyze(events)["hash_chain"]["broken_links"]
    assert original == 0

    tampered = tmp_path / "tampered.jsonl"
    lines = events.read_text(encoding="utf-8").splitlines()
    target = json.loads(lines[10])
    target["prev_hash"] = "f" * 64            # 断链：prev_hash 与上一条的 hash 不符
    lines[10] = json.dumps(target, ensure_ascii=False, sort_keys=True)
    tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")

    broken = obs.analyze(tampered)["hash_chain"]["broken_links"]
    assert broken > 0, "人为断链后自检必须报非零（否则②是恒真判据）"


# ---------------------------------------------------------------------------- ③ 只读
def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_analysis_is_read_only(tmp_path):
    """分析前后 `events.jsonl` 逐字节不变，且不产生新文件。"""
    events = _run(tmp_path, ticks=60, snapshot_every=30)
    before = _digest(events)
    listing_before = sorted(path.name for path in events.parent.iterdir())

    report = obs.analyze(events, checkpoint_dir=events.parent / "checkpoints")
    assert report["events_sha256"] == before

    after = _digest(events)
    listing_after = sorted(path.name for path in events.parent.iterdir())
    assert after == before, "分析改动了事件日志 ⇒ 违反只读纪律"
    assert listing_after == listing_before, f"分析产生了新文件：{set(listing_after) ^ set(listing_before)}"

    # 反例（自证）：对副本追加一行 ⇒ 同一个比较必须报变化
    copy = tmp_path / "copy.jsonl"
    copy.write_bytes(events.read_bytes())
    copy_before = _digest(copy)
    with copy.open("a", encoding="utf-8") as handle:
        handle.write('{"seq": 999999}\n')
    assert _digest(copy) != copy_before, "追加后 sha256 必须改变（证明该判据可达）"


def test_analysis_does_not_change_kernel_state_hash(tmp_path):
    """分析不触碰内核状态：同一 seed 的内核在分析前后 `state_hash` 相同。"""
    from deephealing_kernel.events import EventLog
    from deephealing_kernel.pack import load_pack
    from deephealing_kernel.tick import WorldKernel

    events = _run(tmp_path, ticks=60, snapshot_every=30)
    kernel = WorldKernel(pack=load_pack(PACK_DIR), seed=SEED,
                         log=EventLog(tmp_path / "state" / "events.jsonl"),
                         snapshot_every=30, checkpoint_dir=None)
    kernel.run(60)
    before = kernel.state_hash()
    obs.analyze(events)
    assert kernel.state_hash() == before


# ---------------------------------------------------------------------------- ④ SQL 口径映射
def test_report_groups_carry_sql_equivalence_and_sql_has_no_writes(tmp_path):
    events = _run(tmp_path, ticks=60, snapshot_every=30)
    report = obs.analyze(events)
    for key in obs.GROUP_KEYS:
        assert key in report, f"报告缺少分组 {key}"
        assert report[key]["sql_equivalent"], f"分组 {key} 缺少 sql_equivalent 口径映射"

    sql_path = TOOLS / "duckdb_queries.sql"
    assert sql_path.exists(), "REQ §3 点名的 tools/duckdb_queries.sql 必须存在"
    sql_text = sql_path.read_text(encoding="utf-8")

    forbidden = ("insert into", "update ", "delete from", "create table", "copy ", "drop table")
    def write_hits(text: str) -> list[str]:
        lowered = text.lower()
        return [token for token in forbidden
                if any(line.strip().startswith(token) for line in lowered.splitlines())]

    assert write_hits(sql_text) == [], f"SQL 里出现写语句：{write_hits(sql_text)}"
    # 反例（自证）：注入一条 INSERT ⇒ 同一个检查必须变红
    assert write_hits(sql_text + "\nINSERT INTO t VALUES (1);\n") == ["insert into"]
    # 四组在 SQL 文本里可定位
    for marker in ("哈希链自检", "tick 时间线", "事件统计", "NPC 行为分布"):
        assert marker in sql_text, f"SQL 文本缺少分组标记 {marker!r}"


def test_duckdb_availability_is_reported_honestly(tmp_path):
    """duckdb 不可用 ⇒ 必须**如实**登记，而不是把「SQL 文本已写」当「查询已跑」。"""
    events = _run(tmp_path, ticks=30, snapshot_every=30)
    report = obs.analyze(events)
    assert "duckdb_available" in report
    assert isinstance(report["duckdb_available"]["module"], bool)
    if not report["duckdb_available"]["module"]:
        assert report["duckdb_available"]["reason"], "不可用时必须给出原因（不得静默）"
    # 无论 duckdb 是否可用，纯 Python 四组分析都必须真的产出数值
    assert report["event_statistics"]["events"] > 0
    assert report["tick_timeline"]["ticks_observed"] > 0


def test_report_cli_writes_only_the_requested_out_file(tmp_path):
    """CLI 只写 `--out` 指定文件；stdout 模式不落盘。"""
    events = _run(tmp_path, ticks=30, snapshot_every=30)
    out = tmp_path / "report.json"
    proc = subprocess.run([sys.executable, str(TOOLS / "observability_report.py"),
                           "--events", str(events), "--out", str(out)],
                          capture_output=True, text=True, cwd=str(KERNEL_ROOT))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out.exists()
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["read_only"] is True
    assert document["hash_chain"]["broken_links"] == 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
