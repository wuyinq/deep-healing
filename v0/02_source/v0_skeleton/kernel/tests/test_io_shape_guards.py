"""P-4 三条 IO 形态关闭项的**仓内回归**（M-1 / M-2 / M-3）—— 四元组判据。

运行：
    cd <workspace>/02_source/v0_skeleton/kernel && \
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_io_shape_guards.py -q -p no:cacheprovider

为什么是四元组（设计 §4.1 / Raven 预审 M-3）：修复前 M-1/M-2 **已经是 exit 1**，
只写「非 0」就是零命中假绿。判据必须区分「崩掉」与「结构化拒绝」：
  ① 非 0 退出  ② 输出含结构化 `^E_` 码  ③ 无 `Traceback`  ④ 无半截日志 / 无越界落盘

**自证反例**在 `.squad_tools/artisan-p4-four-tuple.py revert`：用仓库 HEAD 的**修复前 cli.py**
跑同样三例 ⇒ M-1/M-2 出现 Traceback + 半截日志、M-3 exit 0 且越界落盘（四元组不全中）。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK = "districts/xingfu-xiaoqu"
_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
E_LINE = re.compile(r"(?m)^E_[A-Z_]+")

from deephealing_kernel import cli  # noqa: E402


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "deephealing_kernel", *args],
                          capture_output=True, text=True, cwd=str(KERNEL_ROOT), env=_ENV)


def _four_tuple(proc: subprocess.CompletedProcess, log_path: Path) -> dict:
    combined = proc.stdout + proc.stderr
    return {
        "exit": proc.returncode,
        "nonzero": proc.returncode != 0,
        "structured_E": bool(E_LINE.search(combined)),
        "no_traceback": "Traceback" not in combined,
        "log_absent_or_empty": (not log_path.exists()) or log_path.stat().st_size == 0,
        "log_bytes": log_path.stat().st_size if log_path.exists() else 0,
    }


def _base_log(tmp_path: Path) -> Path:
    base = tmp_path / "base"
    base.mkdir(parents=True, exist_ok=True)
    proc = _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--events", str(base / "e.jsonl"),
                "--snapshot-every", "30", "--ticks", "60")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return base / "e.jsonl"


def _assert_four_tuple(result: dict) -> None:
    assert result["nonzero"], result
    assert result["structured_E"], result
    assert result["no_traceback"], result
    assert result["log_absent_or_empty"], result


# --------------------------------------------------------------------------- M-1
def test_m1_replay_refuses_regular_file_at_checkpoints(tmp_path):
    """`out/checkpoints` 被普通文件占位 ⇒ replay 必须结构化拒绝（原先裸 traceback + 半截日志）。"""
    events = _base_log(tmp_path)
    out = tmp_path / "m1-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "checkpoints").write_text("placeholder\n", encoding="utf-8")
    proc = _cli("replay", "--events", str(events), "--pack", PACK, "--until", "60",
                "--checkpoint-every", "30", "--out", str(out))
    result = _four_tuple(proc, out / "replay.jsonl")
    _assert_four_tuple(result)
    assert "E_EVENTS_EXISTS" in (proc.stdout + proc.stderr)

    # 反向对照：清掉占位文件后同一条命令必须 exit 0（证明拒绝不是恒红）
    (out / "checkpoints").unlink()
    clean = _cli("replay", "--events", str(events), "--pack", PACK, "--until", "60",
                 "--checkpoint-every", "30", "--out", str(out))
    assert clean.returncode == 0, clean.stdout + clean.stderr


# --------------------------------------------------------------------------- M-2
def test_m2_run_refuses_read_only_checkpoints(tmp_path):
    """`out/checkpoints` 只读（chmod 500）⇒ run 必须结构化拒绝（原先到第一个快照 tick 才炸）。"""
    out = tmp_path / "m2-out"
    checkpoints = out / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    os.chmod(checkpoints, 0o500)
    try:
        proc = _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                    "--snapshot-every", "30", "--ticks", "60")
        result = _four_tuple(proc, out / "e.jsonl")
    finally:
        os.chmod(checkpoints, 0o700)
    _assert_four_tuple(result)
    assert "E_OUTPUT_NOT_WRITABLE" in (proc.stdout + proc.stderr)

    # 反向对照：恢复可写后必须 exit 0
    clean = _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                 "--snapshot-every", "30", "--ticks", "60")
    assert clean.returncode == 0, clean.stdout + clean.stderr


# --------------------------------------------------------------------------- M-3
def test_m3_run_refuses_symlinked_checkpoints(tmp_path):
    """`out/checkpoints` 指向 `out` 之外 ⇒ 结构化拒绝 **且 `out/**` 之外零新文件**。"""
    out = tmp_path / "m3-out"
    outside = tmp_path / "Z-outside"
    out.mkdir(parents=True, exist_ok=True)
    outside.mkdir(parents=True, exist_ok=True)
    (out / "checkpoints").symlink_to(outside, target_is_directory=True)

    proc = _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                "--snapshot-every", "30", "--ticks", "60")
    result = _four_tuple(proc, out / "e.jsonl")
    _assert_four_tuple(result)
    assert "E_OUTPUT_SYMLINK_ESCAPE" in (proc.stdout + proc.stderr)
    assert not [path for path in outside.rglob("*") if path.is_file()], "不得越界落盘"

    # 反向对照：把符号链接换成真实目录 ⇒ 必须 exit 0
    (out / "checkpoints").unlink()
    (out / "checkpoints").mkdir()
    clean = _cli("run", "--ws-port", "0", "--pack", PACK, "--seed", "20260921", "--events", str(out / "e.jsonl"),
                 "--snapshot-every", "30", "--ticks", "60")
    assert clean.returncode == 0, clean.stdout + clean.stderr


# --------------------------------------------------------------------------- 单元面
def test_guard_output_dir_reports_reasons(tmp_path):
    """守卫函数本身可达且有牙齿（防止后续重构静默丢掉守卫）。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "out" / "checkpoints"
    link.parent.mkdir()
    link.symlink_to(outside, target_is_directory=True)
    reasons = cli._guard_output_dir(link, label="run")  # noqa: SLF001
    assert any("symlink" in reason for reason in reasons), reasons

    dangling = tmp_path / "out2" / "checkpoints"
    dangling.parent.mkdir()
    dangling.symlink_to(tmp_path / "does-not-exist", target_is_directory=True)
    dangling_reasons = cli._guard_output_dir(dangling, label="run")  # noqa: SLF001
    assert any("DANGLING" in reason for reason in dangling_reasons), dangling_reasons

    readable = tmp_path / "out3" / "checkpoints"
    readable.mkdir(parents=True)
    assert cli._guard_output_dir(readable, label="run") == []  # noqa: SLF001

    # 反向对照：把「逃逸」改成「包内目标」⇒ 不得报 symlink 逃逸
    inside_target = tmp_path / "out3" / "real-checkpoints"
    inside_target.mkdir()
    inside_link = tmp_path / "out3" / "checkpoints-link"
    inside_link.symlink_to(inside_target, target_is_directory=True)
    inside_reasons = cli._guard_output_dir(inside_link, label="run")  # noqa: SLF001
    assert not any("escaping" in reason for reason in inside_reasons), inside_reasons


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
