"""收口轮 / 修-6（R2-M2）：cassette **篡改**记录必须与 miss **同等命令层可见**。

来源：Raven 对抗复验 R2-M2（MEDIUM）。修-2 只把 `CassetteMiss` 提为命令层可见；
单条 cassette 记录被改 `output` ⇒ 链哈希失配 ⇒ `summary.cassette_chain_errors` 有明细、
journal 有 `provider.error(CassetteTampered)` + `capability.fallback(on_error)`，
但 **exit 0**、树 5/5 SUCCESS ⇒ 「被篡改的回放源」在命令层同样读成绿。

关闭判据（任务书 §1 修-6，五条）：
  ① 篡改单条记录 ⇒ exit ≠ 0 + 结构化 `E_CASSETTE_TAMPERED`（无 traceback）+ summary 顶层计数 ≥1；
  ② 回归：cassette 齐全且未篡改 ⇒ exit 0；
  ③ 回归：miss 形态仍 exit ≠ 0（修-2 不回退）；
  ④ 负例自证：把篡改检测退回「只记 summary 不算失败」⇒ 判据 ① 变红；
  ⑤ 方向不变：篡改时**零**回填、**零**远端切换（journal 可见）。

运行：
    cd <workspace>/02_source/v0_skeleton/kernel && \
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_cassette_tamper_cli.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK = "districts/xingfu-xiaoqu"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

E_TAMPERED = re.compile(r"(?m)^E_CASSETTE_TAMPERED\b")


def _cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "deephealing_kernel", *args],
                          capture_output=True, text=True, cwd=str(KERNEL_ROOT), env=env or ENV)


def _record_cassettes(tmp_path: Path) -> tuple[Path, Path]:
    """录制一轮（含 `--memory` ⇒ `embed.text` 也被 rule 录制）⇒ 得到「齐全」的 cassette 目录。"""
    record_dir = tmp_path / "record"
    cassettes = tmp_path / "cassettes"
    record_dir.mkdir(parents=True, exist_ok=True)
    cassettes.mkdir(parents=True, exist_ok=True)
    proc = _cli("run", "--pack", PACK, "--seed", "20260921", "--events", str(record_dir / "e.jsonl"),
                "--snapshot-every", "50", "--ticks", "60", "--cognition", "--memory",
                "--cassette-dir", str(cassettes))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return cassettes, record_dir


def _corrupt_one_record(cassettes: Path) -> Path:
    """篡改**第一条** cassette 记录的 `output` 字段（⇒ 记录自校验 hash 失配）。

    保留 JSON 结构合法性 —— 只改语义字段，让「链校验」这个判据去抓它（而不是 json.loads 先炸）。
    """
    target = sorted(cassettes.glob("*.jsonl"))[0]
    lines = target.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    output = first.get("output")
    if isinstance(output, dict) and output:
        key = sorted(output)[0]
        if isinstance(output[key], (int, float)) and not isinstance(output[key], bool):
            output[key] = output[key] + 1.0
        else:
            output[key] = "TAMPERED_BY_TEST"
    else:
        first["output"] = {"tampered_by_test": True}
    lines[0] = json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _summary(out: Path) -> dict:
    return json.loads((out / "cognition" / "summary.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- ① 篡改 ⇒ 命令层可见
def test_tampered_cassette_is_visible_at_command_layer(tmp_path):
    cassettes, _ = _record_cassettes(tmp_path)
    corrupted = _corrupt_one_record(cassettes)
    out = tmp_path / "tamper-out"
    proc = _cli("run", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                "--snapshot-every", "50", "--ticks", "60", "--cognition", "--memory", "--replay",
                "--cassette-dir", str(cassettes))
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, (
        f"被篡改的回放源必须在命令层可见（exit ≠ 0），got {proc.returncode}; combined tail: {combined[-400:]}"
    )
    assert E_TAMPERED.search(combined), f"must print structured E_CASSETTE_TAMPERED; got: {combined[-400:]}"
    assert "Traceback" not in combined, combined[-800:]
    summary = _summary(out)
    # ② 顶层独立计数（不得只埋在嵌套字段里）
    assert isinstance(summary.get("cassette_tampered_events"), int) and summary["cassette_tampered_events"] >= 1
    assert summary.get("cassette_chain_errors"), "chain mismatch detail must be present"
    # ⑤ 方向不变：零回填、零远端切换
    tampered_journal = [entry for entry in summary.get("registry_journal", [])
                        if entry.get("event") == "cassette.tampered"]
    assert tampered_journal, "journal must carry an explicit cassette.tampered event"
    assert all(entry.get("fail_closed") is True for entry in tampered_journal)
    assert summary["fallback_counts"].get("on_error", 0) + summary["fallback_counts"].get("on_timeout", 0) <= \
        summary["cognition_events"], "fallback 只能来自被篡改的那次调用（不得放大）"


def test_tamper_count_matches_journal(tmp_path):
    cassettes, _ = _record_cassettes(tmp_path)
    _corrupt_one_record(cassettes)
    out = tmp_path / "tamper-count"
    proc = _cli("run", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                "--snapshot-every", "50", "--ticks", "60", "--cognition", "--memory", "--replay",
                "--cassette-dir", str(cassettes))
    assert proc.returncode != 0
    summary = _summary(out)
    journal_tampered = [entry for entry in summary.get("registry_journal", [])
                        if entry.get("event") == "cassette.tampered"]
    assert summary["cassette_tampered_events"] == len(journal_tampered) >= 1


# --------------------------------------------------------------------------- ② 回归：干净回放 ⇒ exit 0
def test_clean_replay_stays_green(tmp_path):
    cassettes, _ = _record_cassettes(tmp_path)
    out = tmp_path / "clean-out"
    proc = _cli("run", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                "--snapshot-every", "50", "--ticks", "60", "--cognition", "--memory", "--replay",
                "--cassette-dir", str(cassettes))
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"干净回放必须 exit 0，got {proc.returncode}: {combined[-500:]}"
    assert not E_TAMPERED.search(combined)
    summary = _summary(out)
    assert summary["cassette_tampered_events"] == 0
    assert summary["cassette_chain_errors"] == []
    assert summary["fail_closed_events"] == 0


# --------------------------------------------------------------------------- ③ 回归：miss 仍 exit ≠ 0
def test_miss_regression_unchanged(tmp_path):
    empty = tmp_path / "empty-cassettes"
    empty.mkdir(parents=True, exist_ok=True)
    out = tmp_path / "miss-out"
    proc = _cli("run", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                "--snapshot-every", "50", "--ticks", "100", "--cognition", "--replay",
                "--cassette-dir", str(empty))
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, "修-2 不得回退：miss 仍必须 exit ≠ 0"
    assert re.search(r"(?m)^E_CASSETTE_MISS\b", combined), combined[-400:]
    assert "Traceback" not in combined


# --------------------------------------------------------------------------- ④ 负例自证
def test_negative_control_tamper_treated_as_warning_makes_criterion_1_red(tmp_path):
    """把篡改检测退回「只记 summary 不算失败」⇒ 判据 ① 变红（exit 回到 0、E_ 诊断消失）。

    这正是 R2-M2 的缺陷形态：篡改只留在 `cassette_chain_errors` 嵌套字段里，命令层 exit 0。
    通过**测试钩子** `DH_NEGATIVE_TAMPER_AS_WARNING=1` 复现（修-2 的 miss 钩子不得回退，
    故篡改信号用独立钩子，边界声明见 06 修-8）。
    """
    assert "DH_NEGATIVE_TAMPER_AS_WARNING" in (KERNEL_ROOT / "deephealing_kernel" / "cli.py").read_text(
        encoding="utf-8"), "测试钩子缺失：cli 必须暴露 DH_NEGATIVE_TAMPER_AS_WARNING 供负例自证使用"
    cassettes, _ = _record_cassettes(tmp_path)
    _corrupt_one_record(cassettes)
    out = tmp_path / "neg-out"
    env = dict(ENV, DH_NEGATIVE_TAMPER_AS_WARNING="1")
    proc = _cli("run", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                "--snapshot-every", "50", "--ticks", "60", "--cognition", "--memory", "--replay",
                "--cassette-dir", str(cassettes), env=env)
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"退回形态：篡改只记不算失败 ⇒ exit 回到 0（判据 ① 变红），got {proc.returncode}"
    assert not E_TAMPERED.search(combined), "退回形态：结构化诊断消失（判据 ① 变红）"
    # 而磁盘上的证据仍在：chain error 明细 + journal 篡改事件（信息不丢，只是不再 fail-closed）
    summary = _summary(out)
    assert summary.get("cassette_chain_errors"), "退回形态下 chain error 明细仍应留痕"
    journal_tampered = [entry for entry in summary.get("registry_journal", [])
                        if entry.get("event") == "cassette.tampered"]
    assert journal_tampered, "退回形态下 journal 仍记录篡改（证明确实发生了篡改）"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
