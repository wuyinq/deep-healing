#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""conftest.py — M5.1 tools 层单测的公共夹具（AC-1 侧：fidelity/tools/tests/**）。

纪律：
  * 单测**不联网**：所有取页路径由 monkeypatch 替换（`extract_facts.fetch`）。
  * 单测**不写正文**：注入用的长段一律为**运行时拼接的合成串**，与任何作品无关；
    唯一例外是 `l0_verbatim` 的**正对照** —— 它**运行时**从 L0 全本取一段（不落盘、不进交付面）。
  * 夹具只建临时树（pytest tmp_path），不触碰真实 workspace 产物。

M5.1 r2.5（口径层）改动：锚点源从 `chapters.tsv` 换成 **`L1-fulltext-index.tsv`**（PM 裁决 m5-05 §2-B），
故夹具提供 `index_rows` / `mini_index`（B 口径：含 `src_line_start`/`src_line_end`）与 `anchor_b()`。

M5.1 r1.6 改动：常量与合成工具搬到**唯一模块名**的 `fidelity_testkit.py`（本文件只留夹具）——
两个测试目录各有同名 `conftest.py`，同一次 pytest 调用下 `from conftest import …` 会串台（见 testkit 模块头）。
"""
import os
import sys

import pytest

from fidelity_testkit import CATALOG_HEADER, INDEX_ANCHOR_ROWS, INDEX_HEADER, MINI_INDEX_ROWS

HERE = os.path.dirname(os.path.abspath(__file__))          # .../fidelity/tools/tests
TOOLS = os.path.dirname(HERE)                              # .../fidelity/tools
FIDELITY = os.path.dirname(TOOLS)                          # .../fidelity
WORKSPACE = os.path.dirname(os.path.dirname(FIDELITY))     # {ws}
sys.path.insert(0, TOOLS)

# L1 全本索引（B 口径锚点唯一来源）与 L0 全本（内容比对主判据的来源）。
INDEX_PATH = os.path.join(WORKSPACE, "refs", "original-source", "L1-fulltext-index.tsv")
L0_PATH = os.path.normpath(os.path.join(WORKSPACE, "..", "..", "sources", "deephealing",
                                       "《我的治愈系游戏》（校对版全本+番外）.txt"))

@pytest.fixture(scope="session")
def fidelity_root():
    return FIDELITY


@pytest.fixture(scope="session")
def workspace_root():
    return WORKSPACE


@pytest.fixture(scope="session")
def index_path():
    """真实 L1 全本索引（只读）。"""
    return INDEX_PATH


@pytest.fixture(scope="session")
def l0_path():
    """真实 L0 全本（只读）；缺件 ⇒ 显式 skip（不静默造数据）。"""
    if not os.path.isfile(L0_PATH):
        pytest.skip(f"L0 fulltext not present: {L0_PATH}")
    return L0_PATH


@pytest.fixture(scope="session")
def real_index_rows(index_path):
    """按 `INDEX_ANCHOR_ROWS` 的键取**索引真实行**（并核对与稳定性锚点逐字一致）。"""
    rows = {}
    with open(index_path, encoding="utf-8") as fh:
        header = fh.readline().rstrip("\r\n").split("\t")
        for line in fh:
            cols = line.rstrip("\r\n").split("\t")
            if len(cols) < len(header):
                continue
            rec = dict(zip(header, cols))
            if rec["no"] in INDEX_ANCHOR_ROWS:
                rows[rec["no"]] = rec
    for no, expect in INDEX_ANCHOR_ROWS.items():
        assert no in rows, f"index row {no} missing"
        for key, value in expect.items():
            assert rows[no][key] == value, f"index drift: no={no} {key}={rows[no][key]!r} != {value!r}"
    return rows


@pytest.fixture
def mini_index(tmp_path):
    """写一份最小索引（B 口径），供 lint 用例使用（不依赖真实索引的取值）。"""
    p = tmp_path / "L1-fulltext-index.tsv"
    p.write_text("\n".join([INDEX_HEADER] + MINI_INDEX_ROWS) + "\n", encoding="utf-8")
    return str(p)


@pytest.fixture
def book_tree(tmp_path):
    """返回 builder：造一个只含指定册内容的临时 fidelity 树。"""
    def _build(files: dict):
        root = tmp_path / "fidelity"
        root.mkdir(exist_ok=True)
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
        return str(root)
    return _build
