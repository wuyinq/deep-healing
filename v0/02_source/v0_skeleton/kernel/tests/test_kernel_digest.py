"""AC-M1-5：内核源码指纹（W0b）—— 差集判据 + 基线锚点 + 两条强制负例。

覆盖设计 §6 的 R12 / R26：
  R26 基线锚点：**实现前**快照（`spikes/kernel-baseline/`）必须复现 `files=24` /
      `digest=058e9a548be3c2186fc501441c556a27096c9eebfcca78cf4043b9e496697837`（预审 M4）。
  R12 差集判据：`changed == []` 且 `added ⊆ {deephealing_kernel/adapters/**,
      deephealing_kernel/providers/adapters/**}`（并集口径，设计 §4.8）；
      两条强制负例：① 改 `tick.py` 一字节 → `changed` 非空；② 包根新增 `.py` → `added` 越界。

冻结运行形态（两种形态都必须能跑，预审 C2）：
    cd <workspace>/02_source/v0_skeleton/kernel && pytest tests/test_kernel_digest.py -q
    cd <workspace>/02_source/v0_skeleton/kernel && \
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_kernel_digest.py -q -p no:cacheprovider
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[1]
WS_ROOT = KERNEL_ROOT.parents[2]
BASELINE_ROOT = WS_ROOT / "spikes" / "kernel-baseline"

BASELINE_FILES = 24
BASELINE_DIGEST = "058e9a548be3c2186fc501441c556a27096c9eebfcca78cf4043b9e496697837"

_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def _load_tool():
    path = KERNEL_ROOT / "tools" / "kernel_digest.py"
    spec = importlib.util.spec_from_file_location("kernel_digest_under_test", path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()


def _copy_package(dest: Path) -> Path:
    package = dest / "deephealing_kernel"
    if package.exists():
        shutil.rmtree(package)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(KERNEL_ROOT / "deephealing_kernel", package,
                    ignore=shutil.ignore_patterns(".venv", "__pycache__", "tests", "*.pyc"))
    return dest


def _copy_baseline_package(dest: Path) -> Path:
    package = dest / "deephealing_kernel"
    if package.exists():
        shutil.rmtree(package)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASELINE_ROOT / "deephealing_kernel", package,
                    ignore=shutil.ignore_patterns(".venv", "__pycache__", "tests", "*.pyc"))
    return dest


def _flip_byte(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[0] ^= 0x01
    path.write_bytes(bytes(data))


# --------------------------------------------------------------------------- R26
def test_digest_baseline_anchor(tmp_path):
    """实现前基线锚点必须可复现（`files=24` / `058e9a54…`），且改一字节后 digest 必须变。"""
    assert BASELINE_ROOT.is_dir(), f"missing pre-implementation snapshot: {BASELINE_ROOT}"
    result = TOOL.kernel_digest(BASELINE_ROOT)
    assert len(result["files"]) == BASELINE_FILES, sorted(result["files"])
    assert result["digest"] == BASELINE_DIGEST

    # 防「恒等函数」假绿：同一树改一个字节 ⇒ digest 必须变（文件数不变）
    tampered = _copy_baseline_package(tmp_path / "tampered")
    _flip_byte(tampered / "deephealing_kernel" / "tick.py")
    after = TOOL.kernel_digest(tampered)
    assert len(after["files"]) == BASELINE_FILES
    assert after["digest"] != BASELINE_DIGEST
    assert after["files"]["tick.py"] != result["files"]["tick.py"]


# --------------------------------------------------------------------------- R12
def test_kernel_digest_diff_criterion(tmp_path):
    """新增能力（数据 + adapter 文件）⇒ `changed == []` 且 `added` 落在 adapter 目录并集内。

    修复轮 C3：判据 ① 的 `before` 不再是**本仓实树**，而是与 `after` **同源的隔离副本**
    （两棵真实存在的树之间的差集），避免「拿实树比副本」这种半真半假的对照。
    """
    # ① 正例：两棵隔离副本（before 无 adapter 文件 / after 有）⇒ changed 必须为空
    before_root = _copy_package(tmp_path / "before_tree")
    before = TOOL.kernel_digest(before_root)

    ok_root = _copy_package(tmp_path / "new_capability")
    (ok_root / "deephealing_kernel" / "adapters" / "relation_infer.py").write_text(
        "# 新能力的 provider 适配器（隔离副本夹具）\n", encoding="utf-8"
    )
    diff_ok = TOOL.diff_snapshots(before, TOOL.kernel_digest(ok_root))
    ok, reasons = TOOL.criterion_ok(diff_ok)
    assert diff_ok["changed"] == []
    assert diff_ok["added"] == ["adapters/relation_infer.py"]
    assert ok is True, reasons
    assert len(before["files"]) == len(TOOL.kernel_digest(ok_root)["files"]) - 1

    # ② 负例（强制）：改 tick.py 一个字节 ⇒ changed 非空 ⇒ 判据必须失败
    bad_changed = _copy_package(tmp_path / "changed_tick")
    _flip_byte(bad_changed / "deephealing_kernel" / "tick.py")
    diff_changed = TOOL.diff_snapshots(before, TOOL.kernel_digest(bad_changed))
    ok_changed, reasons_changed = TOOL.criterion_ok(diff_changed)
    assert diff_changed["changed"] == ["tick.py"]
    assert ok_changed is False
    assert any("changed is not empty" in reason for reason in reasons_changed)

    # ③ 负例（强制）：deephealing_kernel/ 根新增 .py（adapter 目录之外）⇒ added 越界 ⇒ 判据必须失败
    bad_root = _copy_package(tmp_path / "added_root")
    (bad_root / "deephealing_kernel" / "extra_module.py").write_text("# 包根新增\n", encoding="utf-8")
    diff_root = TOOL.diff_snapshots(before, TOOL.kernel_digest(bad_root))
    ok_root_criterion, reasons_root = TOOL.criterion_ok(diff_root)
    assert diff_root["added"] == ["extra_module.py"]
    assert ok_root_criterion is False
    assert any("outside adapter dirs" in reason for reason in reasons_root)

    # ④ 正例：REQ 字面路径 providers/adapters/ 也必须被并集判据接受
    union_root = _copy_package(tmp_path / "providers_adapters")
    (union_root / "deephealing_kernel" / "providers" / "adapters").mkdir(parents=True, exist_ok=True)
    (union_root / "deephealing_kernel" / "providers" / "adapters" / "x.py").write_text("# 夹具\n", encoding="utf-8")
    diff_union = TOOL.diff_snapshots(before, TOOL.kernel_digest(union_root))
    ok_union, reasons_union = TOOL.criterion_ok(diff_union)
    assert diff_union["added"] == ["providers/adapters/x.py"]
    assert ok_union is True, reasons_union


def test_providers_adapters_dir_is_an_authorized_adapter_face(tmp_path):
    """**T-4 判据口径改写（M2 / W3；登记见 06 与 07_adr.md）**

    改前断言（M1）：`not (…/deephealing_kernel/providers/adapters).exists()`
      —— 原文 docstring 写明「属 **W3 面**，预审 M4 第 5 条」⇒ 这是 **M1 期的里程碑范围约束**。
    改后断言（M2 = W3~W6）：该目录**存在**且**只作 adapter 实现面**（`relation_infer.py` 在位），
      且 `kernel_digest` 的并集判据对它成立、对包根新增仍不成立。
    为什么不是放松判据：约束从「禁止新建该目录（W3 前的范围冻结）」换成
      「该目录存在，且**只有**它（与 `adapters/`）是新增豁免面，包根新增仍必须红」——
      M1 真正要保的性质（新增能力不改既有内核文件）**一字未改**，而且现在有真实文件在守它。
    自证反例：把 `ADAPTER_DIRS` 收窄回 `("adapters/",)`（= 退回「不承认该目录」的形态）⇒
      下面的并集正例必须变红。
    """
    from pathlib import Path as _Path

    adapters = KERNEL_ROOT / "deephealing_kernel" / "providers" / "adapters"
    assert adapters.is_dir(), "M2/W3 授权面：providers/adapters/ 必须存在（设计 §3.1）"
    names = sorted(path.name for path in adapters.glob("*.py"))
    assert "relation_infer.py" in names, names
    assert "__init__.py" in names, names

    # 判据面：该目录属豁免面（新增文件 ⇒ 判据仍成立）；包根新增 ⇒ 判据必须红
    union_root = _copy_package(tmp_path / "providers_adapters_guard")
    (union_root / "deephealing_kernel" / "providers" / "adapters").mkdir(parents=True, exist_ok=True)
    (union_root / "deephealing_kernel" / "providers" / "adapters" / "guard.py").write_text(
        "# 夹具\n", encoding="utf-8")
    before = TOOL.kernel_digest(KERNEL_ROOT)
    diff_union = TOOL.diff_snapshots(before, TOOL.kernel_digest(union_root))
    assert TOOL.criterion_ok(diff_union)[0] is True

    # 自证反例：把 ADAPTER_DIRS 收窄（退回 M1 的「不承认 providers/adapters/」形态）⇒ 并集正例必红
    original = TOOL.ADAPTER_DIRS
    try:
        TOOL.ADAPTER_DIRS = ("adapters/",)
        assert TOOL.criterion_ok(diff_union)[0] is False
    finally:
        TOOL.ADAPTER_DIRS = original


# --------------------------------------------------------------------------- CLI 形态
def test_kernel_digest_cli_runs_standalone():
    """`python3 tools/kernel_digest.py --root .` 必须能独立跑（sys.path[0] = tools/）。"""
    proc = subprocess.run(
        [sys.executable, "tools/kernel_digest.py", "--root", ".", "--json"],
        capture_output=True, text=True, cwd=str(KERNEL_ROOT), env=_ENV,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["files"] >= BASELINE_FILES
    assert len(payload["digest"]) == 64

    # 该脚本不得 `import deephealing_kernel`（否则 sys.path[0]=tools/ 下必 ModuleNotFoundError）
    source = (KERNEL_ROOT / "tools" / "kernel_digest.py").read_text(encoding="utf-8")
    offending = [
        line for line in source.splitlines()
        if re.match(r"^\s*(import|from)\s+deephealing_kernel\b", line)
    ]
    assert offending == [], offending

    selftest = subprocess.run(
        [sys.executable, "tools/kernel_digest.py", "--selftest"],
        capture_output=True, text=True, cwd=str(KERNEL_ROOT), env=_ENV,
    )
    assert selftest.returncode == 0, selftest.stdout + selftest.stderr
