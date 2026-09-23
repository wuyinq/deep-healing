"""tools 层单测公共夹具（M5.1 r2 / AC-2 侧；设计 D-7）。

**落盘纪律（Raven C-3 / D-6）**：本目录在 `02_source/**` 内 —— 正是 `scan_ip_boundary.py` 的扫描面。
因此所有长 CJK 合成串、以及 `jump_scare` 命中词，一律**运行时拼接构造**，
落盘源码里不出现任何可命中的引号长段或命中词字面量；否则单测自身就会成为交付树里的命中源。

M5.1 r1.6 改动：合成工具搬到**唯一模块名**的 `v0_testkit.py`（本文件只留按路径加载器与夹具）——
两个测试目录各有同名 `conftest.py`，同一次 pytest 调用下 `from conftest import …` 会串台（见 testkit 模块头）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1]


def load_tool(module_name: str, filename: str):
    """按路径加载被测脚本（tools 层无包结构，且脚本名不保证是合法模块名）。"""
    spec = importlib.util.spec_from_file_location(module_name, TOOLS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def ipb():
    return load_tool("m5r2_uut_scan_ip_boundary", "scan_ip_boundary.py")


@pytest.fixture(scope="session")
def sft():
    return load_tool("m5r2_uut_scan_fidelity_terms", "scan_fidelity_terms.py")


@pytest.fixture
def tree(tmp_path):
    """把 {相对路径: 内容} 写成临时树；返回树根（临时树在 pytest tmp 目录，不落交付面）。"""
    def build(files: dict[str, str]) -> Path:
        for rel, content in files.items():
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return tmp_path
    return build
