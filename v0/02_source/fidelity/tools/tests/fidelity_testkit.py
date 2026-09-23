#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fidelity 侧单测的**公共常量与合成工具**（M5.1 r1.6）。

为什么单独成模块（根因，不是风格偏好）：pytest 的 prepend 导入模式下，每个测试目录里的
`conftest.py` 都以**裸模块名 `conftest`** 进 `sys.modules` ⇒ `fidelity/tools/tests` 与
`v0_skeleton/tools/tests` 两个同名 conftest 在**同一次 pytest 调用**里互相覆盖，
测试模块的 `from conftest import …` 会解析到**另一个目录**的 conftest ⇒ 3 个 collection ERROR。
本模块名全局唯一 ⇒ 任何调用形态（分目录 / 合并 / 任意顺序）都解析到本目录的这份实现。

纪律：本目录在 `02_source/**` 内（`scan_ip_boundary.py` 的扫描面）⇒ 这里只放**合成**常量与
工具函数，不出现任何原著长段或命中词字面量。
"""
from __future__ import annotations

# B 口径索引表头（`L1-fulltext-index.tsv`；锚点五项的唯一来源）。
INDEX_HEADER = ("no\tlabeled_no\ttitle\tofficial_title\tofficial_url\tfirst_pub\t"
                "official_words\ttxt_cjk_chars\tdeviation_pct\tsrc_line_start\tsrc_line_end")
# 镜像模式（`--source mirror`，交叉校验用途）用的最小 catalog 列。
CATALOG_HEADER = "no\ttitle\tcid\turl\tfirst_pub\twords\tvolume"
# 索引稳定性锚点（**真章号 180 对齐 + 真 332 标成 322 的错位行**；值逐字取自 L1-fulltext-index.tsv）
INDEX_ANCHOR_ROWS = {
    "180": {"labeled_no": "180", "official_url": "https://www.qidian.com/chapter/1025901449/648165987/",
            "first_pub": "2021-04-19 18:49:14", "official_words": "2208", "txt_cjk_chars": "2312",
            "deviation_pct": "4.7", "src_line_start": "10395", "src_line_end": "10451"},
    "332": {"labeled_no": "322", "official_url": "https://www.qidian.com/chapter/1025901449/659544394/",
            "first_pub": "2021-07-02 15:38:24", "official_words": "2215", "txt_cjk_chars": "2300",
            "deviation_pct": "3.8", "src_line_start": "19937", "src_line_end": "19987"},
}
# 最小索引（合成）：一行普通章 + 一行 ext 空章号（真章号仍用 no）
MINI_INDEX_ROWS = [
    "7\t7\t合成第七章\t第7章 合成第七章\thttps://example.invalid/chapter/700000007/"
    "\t2021-01-30 10:00:00\t2100\t2200\t4.8\t100\t160",
    "8\t8\t合成第八章\t第8章 合成第八章\thttps://example.invalid/chapter/700000008/"
    "\t2021-01-31 11:00:00\t2200\t2300\t4.5\t162\t220",
]


def anchor_b(no: str, url: str, ts: str, cid: str = None) -> str:
    """B 口径锚点段（可选尾部 `cid:` 冗余）。"""
    seg = f"ch{no} {url} {ts}"
    return f"{seg} cid:{cid}" if cid else seg


def src_seg(sha12: str, start, end) -> str:
    return f"sha256={sha12} lines={start}-{end}"


def synth_text(n_cjk: int) -> str:
    """运行时拼接的合成中文串（非任何作品正文）。"""
    unit = "合成文本"
    out = []
    while sum(len(x) for x in out) < n_cjk:
        out.append(unit)
    return "".join(out)[:n_cjk]
