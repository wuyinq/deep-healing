"""修复轮 2 / 修-2（R-M2-2）：`--replay` 下 cassette miss 必须**命令层可见**。

修复前（architect 独立复现 `/tmp/arch-m2-r2b`）：`run --cognition --replay --cassette-dir <空>`
⇒ **EXIT 0**、控制台无 `E_CASSETTE_MISS`、`summary.fallback_counts == {}`、无 fail-closed 计数
⇒ 「只看 exit 的自动化验收」把 fail-closed 读成绿，与设计 §3.4b(4) 字面不一致。

关闭判据（任务书 §1 修-2，四条）：
  ① 复跑 ⇒ exit ≠ 0 且 stderr 有结构化 `E_CASSETTE_MISS`（无 `Traceback`）；
  ② `summary.json` 含 `fail_closed_events` 计数且值 = 实际 miss 数（`degraded_reasons` 同时可见）；
  ③ **负例自证**：把 miss 的 exit 退回 0 ⇒ 判据 ① 变红（monkeypatch 演示）；
  ④ **回归**：正常回放（cassette 齐全）⇒ exit 0（不得把正常路径判红）。
方向不变：**不降级、不回填、不静默切远端**。

运行：
    cd <workspace>/02_source/v0_skeleton/kernel && \
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_cassette_miss_cli.py -q -p no:cacheprovider
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
PACK = "districts/xingfu-xiaoqu"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

E_MISS = re.compile(r"(?m)^E_CASSETTE_MISS\b")


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "deephealing_kernel", *args],
                          capture_output=True, text=True, cwd=str(KERNEL_ROOT), env=ENV)


def _record_cassettes(tmp_path: Path) -> Path:
    """先**录制**一轮（真实调用 + rule 录制源），得到一个「齐全」的 cassette 目录。"""
    record_dir = tmp_path / "record"
    cassettes = tmp_path / "cassettes"
    record_dir.mkdir(parents=True, exist_ok=True)
    cassettes.mkdir(parents=True, exist_ok=True)
    proc = _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--events", str(record_dir / "e.jsonl"),
                "--snapshot-every", "50", "--ticks", "60", "--cognition", "--memory",
                "--cassette-dir", str(cassettes))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert any(cassettes.glob("*.jsonl")), "record run must produce cassettes"
    return cassettes


def _empty_cassette_dir(tmp_path: Path) -> Path:
    empty = tmp_path / "empty-cassettes"
    empty.mkdir(parents=True, exist_ok=True)
    return empty


# --------------------------------------------------------------------------- ① ② miss ⇒ fail-closed 可见
def test_replay_with_missing_cassettes_fails_closed_at_command_layer(tmp_path):
    empty = _empty_cassette_dir(tmp_path)
    out = tmp_path / "miss-out"
    proc = _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                "--snapshot-every", "50", "--ticks", "100", "--cognition", "--replay",
                "--cassette-dir", str(empty))
    combined = proc.stdout + proc.stderr
    # ① exit ≠ 0 + 结构化 E_ 诊断（无 Traceback）
    assert proc.returncode != 0, f"replay miss must be visible at exit code, got {proc.returncode}"
    assert E_MISS.search(combined), "stderr/stdout must carry a structured E_CASSETTE_MISS line"
    assert "Traceback" not in combined, combined[-800:]
    # ② summary.json 含 fail-closed 计数且值 = 实际 miss 数
    summary_path = out / "cognition" / "summary.json"
    assert summary_path.is_file(), "summary.json must exist even when fail-closed"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert isinstance(summary.get("fail_closed_events"), int) and summary["fail_closed_events"] > 0
    # miss 的槽数由**树的执行路径**决定（第一分支在 intent.plan 处中断 ⇒ emotion.appraise 走
    # 第二分支再 miss；relation.infer 不再被调）——计数口径以 journal 为准（见下一条用例）。
    assert summary.get("degraded_reasons") == ["intent.plan"]
    # 方向不变：**没有** fallback、**没有** capability.call（不切远端、不回填）
    assert summary["fallback_counts"] == {}, summary["fallback_counts"]
    journal = (out / "cognition" / "cognition.jsonl").read_text(encoding="utf-8")
    assert '"capability.call"' not in journal, "miss ⇒ 不得有任何 provider 调用（包括降级调用）"


def test_summary_fail_closed_count_matches_journal(tmp_path):
    """`fail_closed_events` 必须等于 journal 里 `cassette.miss` 条数（不是拍脑袋的 1）。"""
    empty = _empty_cassette_dir(tmp_path)
    out = tmp_path / "miss-out-2"
    proc = _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                "--snapshot-every", "50", "--ticks", "100", "--cognition", "--replay",
                "--cassette-dir", str(empty))
    assert proc.returncode != 0
    summary = json.loads((out / "cognition" / "summary.json").read_text(encoding="utf-8"))
    miss_entries = [entry for entry in summary.get("registry_journal", [])
                    if entry.get("event") == "cassette.miss"]
    assert summary["fail_closed_events"] == len(miss_entries) > 0


# --------------------------------------------------------------------------- ③ 负例自证
def test_negative_control_exit_zero_makes_criterion_red(tmp_path, monkeypatch):
    """把 miss 的 exit 退回 0 ⇒ 判据 ①（exit ≠ 0 且有 E_ 诊断）变红。

    退回形态用「把 `_run_cognition` 的报告改成 `fail_closed_events=0` 且**吞掉** `CassetteMiss`
    （让行为树把 miss 当普通 FAILURE）」= 完整复现修复前的两条行为（这正是「exit 0 假绿」的根因）。
    monkeypatch 必须在**子进程**可见 ⇒ 用环境变量开关（`DH_NEGATIVE_HIDE_CASSETTE_MISS=1`）
    在 `cli._run_cognition` 内部的**测试钩子**上生效。
    """
    from deephealing_kernel import cli as cli_mod

    assert hasattr(cli_mod, "_NEGATIVE_HIDE_CASSETTE_MISS"), (
        "测试钩子缺失：cli 必须暴露 _NEGATIVE_HIDE_CASSETTE_MISS 供负例自证使用"
    )
    empty = _empty_cassette_dir(tmp_path)
    out = tmp_path / "neg-out"
    env = dict(ENV, DH_NEGATIVE_HIDE_CASSETTE_MISS="1")
    proc = subprocess.run(
        [sys.executable, "-m", "deephealing_kernel", "run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921",
         "--events", str(out / "e.jsonl"), "--snapshot-every", "50", "--ticks", "100",
         "--cognition", "--replay", "--cassette-dir", str(empty)],
        capture_output=True, text=True, cwd=str(KERNEL_ROOT), env=env,
    )
    combined = proc.stdout + proc.stderr
    # 判据 ① 在退回形态下**两条都不成立**（这正是「假绿」）
    assert proc.returncode == 0, f"退回形态：miss 被吞 ⇒ exit 回到 0（判据 ① 的『非 0』变红），got {proc.returncode}"
    assert not E_MISS.search(combined), "退回形态：结构化诊断消失（判据 ① 的『有 E_ 码』变红）"
    # 而磁盘上的 journal 仍然记录了 miss（信息不丢，只是不再 fail-closed —— 这就是缺陷形态）
    summary = json.loads((out / "cognition" / "summary.json").read_text(encoding="utf-8"))
    miss_entries = [entry for entry in summary.get("registry_journal", [])
                    if entry.get("event") == "cassette.miss"]
    assert len(miss_entries) > 0, "退回形态下 registry_journal 仍记录 miss（证明确实发生了 miss）"


# --------------------------------------------------------------------------- ④ 回归：正常回放 ⇒ exit 0
def test_normal_replay_with_complete_cassettes_stays_green(tmp_path):
    cassettes = _record_cassettes(tmp_path)
    out = tmp_path / "ok-out"
    proc = _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                "--snapshot-every", "50", "--ticks", "60", "--cognition", "--memory", "--replay",
                "--cassette-dir", str(cassettes))
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"正常回放必须 exit 0，got {proc.returncode}: {combined[-600:]}"
    assert not E_MISS.search(combined)
    summary = json.loads((out / "cognition" / "summary.json").read_text(encoding="utf-8"))
    assert summary["fail_closed_events"] == 0
    calls = [line for line in (out / "cognition" / "cognition.jsonl").read_text(encoding="utf-8").splitlines()
             if '"capability.call"' in line]
    assert len(calls) == 15, f"正常回放应有 15 次能力调用（5 NPC × 3 槽位），got {len(calls)}"
    # 回放路径 0 次远端：全部 provider == cassette_replay
    providers = [json.loads(line)["provider"] for line in calls]
    assert set(providers) == {"cassette_replay"}, set(providers)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
