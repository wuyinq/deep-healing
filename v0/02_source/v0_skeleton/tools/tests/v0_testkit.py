"""`scan_fidelity_terms.py` / `scan_ip_boundary.py` 单测的**公共合成工具**（M5.1 r1.6）。

为什么单独成模块（根因）：pytest prepend 导入模式下每个测试目录的 `conftest.py` 都以**裸模块名
`conftest`** 进 `sys.modules` ⇒ `v0_skeleton/tools/tests` 与 `fidelity/tools/tests` 的同名 conftest
在**同一次 pytest 调用**里互相覆盖，测试模块的 `from conftest import …` 会解析到**另一个目录**的
conftest ⇒ collection ERROR。本模块名全局唯一 ⇒ 任何调用形态都解析到本目录的这份实现。

**落盘纪律（Raven C-3 / D-6）**：本目录在 `02_source/**` 内 —— 正是 `scan_ip_boundary.py` 的扫描面。
因此所有长 CJK 合成串、以及 `jump_scare` 命中词，一律**运行时拼接构造**，
落盘源码里不出现任何可命中的引号长段或命中词字面量；否则单测自身就会成为交付树里的命中源。
"""
from __future__ import annotations

# ----------------------------------------------------------------- 合成文本
_SYNTH_PARTS = ("合成", "中文", "串", "用于", "单测", "不取自", "任何", "原著", "正文",
                "且", "不落盘", "仅供", "判据", "自证", "使用")


def synth_cjk(n: int) -> str:
    """运行时拼出**恰好 n 个 CJK**字符（无句末标点）。"""
    out = ""
    i = 0
    while len(out) < n:
        out += _SYNTH_PARTS[i % len(_SYNTH_PARTS)]
        i += 1
    return out[:n]


def synth_sentence(n: int, puncts: int = 0) -> str:
    """n 个 CJK + puncts 个句末标点（标点不计入 CJK 数）。"""
    return synth_cjk(n) + "。" * puncts


def jump_phrase() -> str:
    """运行时拼出 `jump_scare` 命中词（**不逐字落盘**）。"""
    return "".join(("Jump", " ", "Scare"))


def quote(seg: str) -> str:
    return "\u201c" + seg + "\u201d"


def quote_corner(seg: str) -> str:
    return "\u300c" + seg + "\u300d"


def fact_line(code: str, text: str) -> str:
    """出处表事实行（含 lint R1 要求的锚点标记）。"""
    return f"- [{code}] {text} || anchor: UNVERIFIED || reason: 单测合成\n"
