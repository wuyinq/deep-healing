#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fidelity_lint.py — M5.1 出处表事实行 lint（设计 v3 §5.2 的 R1~R7；**R2 = L0 口径 B**）。

用法：
  python3 fidelity/tools/fidelity_lint.py --strict [--root <fidelity 目录>] \\
      [--index refs/original-source/L1-fulltext-index.tsv] [--l0-sha256 <hex>] [--probe]

扫描面（v2 钉死）：**仅** `--root` 下的 `00`~`05` 六册 `.md`，**不递归子目录**；
`tools/**` 与任何非 `.md` 文件不在 lint 面内（由 `redline_scan.py` 与 IP 边界扫描覆盖）。

锚点语法（**v3 = PM 裁决 m5-05 §2-B 冻结，逐字**）：
  `- [<BOOK>-<NN>] <一行事实> || anchor: ch<真章号> <官方章节URL> <YYYY-MM-DD HH:MM:SS> || src: sha256=<L0 sha256 前12位> lines=<src_line_start>-<src_line_end>`
  `- [<BOOK>-<NN>] <一行事实> || anchor: UNVERIFIED || reason: <一句话>`

规则：
  R1 事实行（以 `- [` 开头）必须含 ` || anchor: `；锚点结构残缺（无法解析）同样记 R1
  R2（v3 = L0 口径，PM m5-05 §2-B）非 UNVERIFIED 行**五项同时校验**（全部逐字，不做规范化/模糊匹配）：
     ① 真章号存在于 `--index` 的 `no` 列；
     ② 官方 URL 与该行 `official_url` 逐字相同；
     ③ 首发时间与该行 `first_pub` 逐字相同；
     ④ `src: sha256=` 前缀 == L0 全本 sha256 前 12 位（默认 `9c8b562e94e0`）；
     ⑤ `lines=<a>-<b>` == 该行 `src_line_start-src_line_end`（**行区间只许取自索引**）。
     `cid:` 为可选冗余（与真章号并存不判红；**单独存在而无真章号 ⇒ R2**）；
     **旧语法**（无 ` || src: ` 段）⇒ R2；`src:` 段残缺 / 形式不符 ⇒ R2。
  R3 UNVERIFIED 行必须带 `reason:`
  R4 各册事实行数 ≥ 下界（01≥6 / 02≥10 / 03≥4 / 04≥20 / 05≥1）
  R5 引号内（“”/「」）命中 D-4 规则 ⇒ 违规
  R6 **引号外**连续 CJK 串命中 D-4 规则 ⇒ 违规（**所有行都适用，含事实行** ——
     PM 裁决 m5-07 §一.7：事实行恰好是内容落点，R6 不得留空档）
  R7 事实行不得含「CJK ≥24 且 ≥2 个句末/分句标点」的引号段（= R5 的事实行特化）

D-4 规则（v2 不变）：引号内（或引号外连续 CJK 串）满足**任一** —— (a) CJK ≥ 60；或
(b) CJK ≥ 24 且含 ≥2 个句末/分句标点。用于区分「逐字搬运正文段落」与「技术性短引文」。

输出（v2 钉死）：违规明细**只打 `file:line:rule:长度`，绝不打印命中行文本**；
JSON 摘要给各册事实行数 / UNVERIFIED 数 / 逐规则违规数 / 锚点源路径。

退出码：0 通过 / 1 违规 / 2 用法错误。

**过渡态（M5.1 r2.5 → r1.5 之间）**：六册仍是旧锚点（`ch<N>`，无 `src:` 段）⇒ R2 对真实六册判红，
这是设计内的过渡态（r1.5 换锚后必须转绿）。**不得**为此放宽 R2。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
SENT_PUNCT = "。！？；"
BOOKS = ["00", "01", "02", "03", "04", "05"]
BOUNDS = {"01": 6, "02": 10, "03": 4, "04": 20, "05": 1}
FACT_PREFIX = "- ["
ANCHOR_MARK = " || anchor: "
SRC_MARK = " || src: "

# L0 全本 sha256（PM 裁决 m5-05 §2-A）与其前 12 位（锚点 `src: sha256=` 的口径值）。
L0_SHA256 = "9c8b562e94e01d2162ea20e185168e846d917367ce42723ba967259bab074bbb"
DEFAULT_L0_SHA12 = L0_SHA256[:12]
# 锚点源 = L1 全本索引（真章号 / 官方 URL / 首发时间 / 行区间 的唯一来源）。
INDEX_NAME = "L1-fulltext-index.tsv"
INDEX_REQUIRED_COLUMNS = ("no", "official_url", "first_pub", "src_line_start", "src_line_end")

# 锚点段（B 口径）：`ch<真章号> <URL> <YYYY-MM-DD HH:MM:SS>`，可选尾部 `cid:<CID>` 冗余。
ANCHOR_SEG_RE = re.compile(
    r"^(?:ch(?P<no>\d+)|cid:(?P<cid>\d+))\s+(?P<url>\S+)\s+"
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:\s+cid:(?P<cid2>\d+))?$")
SRC_RE = re.compile(r"^sha256=([0-9a-fA-F]+)\s+lines=(\d+)-(\d+)$")


# ----------------------------------------------------------------- 基础工具
def cjk_count(text: str) -> int:
    return len(CJK_RE.findall(text))


def d4_hit(text: str) -> bool:
    """D-4 规则：CJK ≥60，或 CJK ≥24 且 ≥2 个句末/分句标点。"""
    n = cjk_count(text)
    if n >= 60:
        return True
    if n >= 24:
        return sum(text.count(p) for p in SENT_PUNCT) >= 2
    return False


def quoted_segments(line: str):
    """返回 [(段文本, 起始列)]，覆盖 “…” 与 「…」 两套引号。"""
    out = []
    for opener, closer in (("“", "”"), ("「", "」")):
        start = 0
        while True:
            i = line.find(opener, start)
            if i < 0:
                break
            j = line.find(closer, i + 1)
            if j < 0:
                break
            out.append((line[i + 1:j], i + 1))
            start = j + 1
    return out


def strip_quoted(line: str) -> str:
    for opener, closer in (("“", "”"), ("「", "」")):
        line = re.sub(re.escape(opener) + r"[^" + re.escape(closer) + r"]*" + re.escape(closer), "", line)
    return line


def load_index(path: str):
    """载入 L1 全本索引：返回 {真章号: 记录}。缺必需列 ⇒ 抛 ValueError（fail-closed）。"""
    by_no = {}
    with open(path, encoding="utf-8") as fh:
        header = fh.readline().rstrip("\r\n").split("\t")
        missing = [c for c in INDEX_REQUIRED_COLUMNS if c not in header]
        if missing:
            raise ValueError(f"index lacks required columns {missing}: {path}")
        for line in fh:
            cols = line.rstrip("\r\n").split("\t")
            if len(cols) < len(header):
                continue
            rec = dict(zip(header, cols))
            if rec["no"]:
                by_no[rec["no"]] = rec
    return by_no


def default_index_path(root: str) -> str:
    return os.path.normpath(os.path.join(root, "..", "..", "refs", "original-source", INDEX_NAME))


# ----------------------------------------------------------------- lint 核心
class Lint:
    def __init__(self, root: str, index: str, l0_sha12: str = DEFAULT_L0_SHA12):
        self.root = root
        self.index_path = index
        self.by_no = load_index(index)
        self.l0_sha12 = l0_sha12
        self.violations = []          # (file, line, rule, length)
        self.books = {}               # book -> {"facts":n,"unverified":n,"dossiers":n}
        self.per_rule = {r: 0 for r in ("R1", "R2", "R3", "R4", "R5", "R6", "R7")}

    def flag(self, path, lineno, rule, length=0):
        self.violations.append((os.path.basename(path), lineno, rule, length))
        self.per_rule[rule] += 1

    def parse_anchor(self, line: str) -> dict:
        """解析锚点段 + `src:` 段。

        kind ∈ {ch, cid_only, old_syntax, bad_src, unverified, malformed}
          ch         = 真章号 + URL + 时间（+ 可选 `cid:` 冗余），且 `src:` 段形式正确
          cid_only   = 只有 `cid:` 而无真章号 ⇒ R2
          old_syntax = 真章号 + URL + 时间，但**无** `src:` 段 ⇒ R2（六册在 r1.5 前的过渡态）
          bad_src    = 有 `src:` 段但形式不符 ⇒ R2
          malformed  = 锚点结构本身残缺 ⇒ R1
        """
        out = {"kind": "malformed", "no": None, "url": None, "ts": None,
               "cid": None, "sha": None, "lines": None}
        seg = line.split(ANCHOR_MARK, 1)[1].split(" || ", 1)[0].strip()
        if seg == "UNVERIFIED":
            out["kind"] = "unverified"
            return out
        m = ANCHOR_SEG_RE.match(seg)
        if not m:
            return out
        out["url"], out["ts"] = m.group("url"), m.group("ts")
        out["cid"] = m.group("cid2")
        if m.group("no") is None:                 # 只有 `cid:` 而无真章号 ⇒ R2
            out["kind"] = "cid_only"
            out["cid"] = m.group("cid")
            return out
        out["kind"] = "ch"
        out["no"] = m.group("no")
        if SRC_MARK not in line:                  # 旧语法（无 `src:` 段）⇒ R2
            out["kind"] = "old_syntax"
            return out
        sseg = line.split(SRC_MARK, 1)[1].split(" || ", 1)[0].strip()
        sm = SRC_RE.match(sseg)
        if not sm:                                # `src:` 段残缺 / 形式不符 ⇒ R2
            out["kind"] = "bad_src"
            return out
        out["sha"] = sm.group(1)
        out["lines"] = (sm.group(2), sm.group(3))
        return out

    def check_r2(self, path, lineno, a: dict):
        """五项逐字校验；任一不符即 R2。"""
        if a["kind"] in ("cid_only", "old_syntax", "bad_src"):
            self.flag(path, lineno, "R2")
            return
        rec = self.by_no.get(a["no"])
        if rec is None:                                   # ① 真章号存在
            self.flag(path, lineno, "R2")
            return
        if a["url"] != rec["official_url"]:               # ② URL 逐字
            self.flag(path, lineno, "R2")
            return
        if a["ts"] != rec["first_pub"]:                   # ③ 首发时间逐字
            self.flag(path, lineno, "R2")
            return
        if a["sha"] != self.l0_sha12:                     # ④ L0 sha256 前缀
            self.flag(path, lineno, "R2")
            return
        if a["lines"] != (rec["src_line_start"], rec["src_line_end"]):   # ⑤ 行区间取自索引
            self.flag(path, lineno, "R2")

    def scan_file(self, path: str, book: str):
        stats = {"facts": 0, "unverified": 0, "dossiers": 0}
        with open(path, encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.rstrip("\n")
                if line.startswith("## "):
                    stats["dossiers"] += 1
                is_fact = line.startswith(FACT_PREFIX)
                if is_fact:
                    stats["facts"] += 1
                    if ANCHOR_MARK not in line:
                        self.flag(path, lineno, "R1")
                    else:
                        a = self.parse_anchor(line)
                        if a["kind"] == "unverified":
                            stats["unverified"] += 1
                            if "reason:" not in line:
                                self.flag(path, lineno, "R3")
                        elif a["kind"] == "malformed":
                            self.flag(path, lineno, "R1")
                        else:
                            self.check_r2(path, lineno, a)
                # R5（引号内 D-4）/ R7（事实行特化）/ R6（引号外连续 CJK 串）**对所有行生效**
                # —— PM 裁决 m5-07 §一.7：事实行恰好是内容落点，R6 不得留空档。
                for seg, _col in quoted_segments(line):
                    if d4_hit(seg):
                        self.flag(path, lineno, "R5", cjk_count(seg))
                    if is_fact and cjk_count(seg) >= 24 and sum(seg.count(p) for p in SENT_PUNCT) >= 2:
                        self.flag(path, lineno, "R7", cjk_count(seg))
                for run in RUN_RE.findall(strip_quoted(line)):
                    if d4_hit(run):
                        self.flag(path, lineno, "R6", len(run))
        return stats

    def run(self) -> int:
        found = False
        for book in BOOKS:
            for name in sorted(os.listdir(self.root)):
                if not name.endswith(".md") or not name.startswith(book):
                    continue
                p = os.path.join(self.root, name)
                if not os.path.isfile(p):
                    continue
                found = True
                self.books[name] = self.scan_file(p, book)
                bound = BOUNDS.get(book)
                if bound is not None and self.books[name]["facts"] < bound:
                    self.violations.append((name, 0, "R4", self.books[name]["facts"]))
                    self.per_rule["R4"] += 1
        if not found:
            print("usage: no 00~05 *.md found under --root", file=sys.stderr)
            return 2
        return 0


# ----------------------------------------------------------------- 输出
def emit(lint: Lint, strict: bool):
    for fname, lineno, rule, length in sorted(lint.violations):
        print(f"{fname}:{lineno}:{rule}:{length}")
    summary = {
        "books": lint.books,
        "per_rule": lint.per_rule,
        "violations_total": len(lint.violations),
        "strict": strict,
        "anchor_source": lint.index_path,
        "l0_sha256_12": lint.l0_sha12,
        "r2_checks": ["chapter_no_in_index", "official_url_verbatim",
                      "first_pub_verbatim", "l0_sha256_prefix", "src_line_range_from_index"],
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if not lint.violations else 1


# ----------------------------------------------------------------- 探针
PROBE_PARTS = ["本段为", "探针运行时", "拼接构造的", "合成中文长串", "不取自任何",
               "原著正文", "仅用于验证", "判据是否具备", "命中能力", "且不落盘",
               "长度必须超过", "六十个汉字", "否则无法触发", "引号内长段", "与引号外",
               "连续汉字串", "这两条规则", "合成内容", "与任何作品", "均无对应关系"]


def probe_text() -> str:
    """运行时拼接的合成长串（非原著正文，≥60 CJK 且无句末标点）。"""
    return "".join(PROBE_PARTS)


def short_quote_text() -> str:
    """技术性短引文形态：24 CJK、句末标点 0（F-18 定标形态）。"""
    return "".join(["技术性", "短引文", "二十四", "汉字", "无句末", "标点", "形态", "样例"])


def _probe_tree(tmp: str, row: dict, body: str) -> str:
    """合成探针树：只含一册 `00`（无下界）与一行事实 ⇒ 规则集完全由该行决定。"""
    os.makedirs(tmp, exist_ok=True)
    with open(os.path.join(tmp, "00-source-manifest.md"), "w", encoding="utf-8") as fh:
        fh.write(body)
    return tmp


def run_probe(index: str, l0_sha12: str) -> int:
    """B 口径四态 + 假锚点五连 + 旧语法 / cid 两态的**逐条**自证。

    每个用例在**合成树**上跑（基线 = 合法 B 锚点行、0 违规）⇒ 命中规则集**恰好**等于预期，
    不受真实六册过渡态（旧锚点全红）影响。全部移除后必须回基线。
    """
    ok = True
    by_no = load_index(index)
    nos = sorted(by_no, key=lambda s: int(s))
    if not nos:
        print("usage: index has no rows", file=sys.stderr)
        return 2
    row = by_no[nos[0]]
    valid_anchor = f"ch{row['no']} {row['official_url']} {row['first_pub']}"
    valid_src = f"sha256={l0_sha12} lines={row['src_line_start']}-{row['src_line_end']}"
    valid_line = f"{FACT_PREFIX}STR-01] 探针：合法 B 锚点 || anchor: {valid_anchor} || src: {valid_src}\n"
    missing_no = str(max(int(n) for n in nos) + 9999)
    a, b = int(row["src_line_start"]), int(row["src_line_end"])
    cases = [
        ("no_anchor", f"{FACT_PREFIX}STR-02] 探针：无锚点事实行\n", {"R1"}),
        ("old_syntax", f"{FACT_PREFIX}STR-03] 探针：旧语法（无 src 段） || anchor: {valid_anchor}\n", {"R2"}),
        ("cid_only", f"{FACT_PREFIX}STR-04] 探针：只有 cid 无真章号 || anchor: cid:648165987 {row['official_url']} {row['first_pub']}\n", {"R2"}),
        ("fake_chapter", f"{FACT_PREFIX}STR-05] 探针：不存在的真章号 || anchor: ch{missing_no} {row['official_url']} {row['first_pub']} || src: {valid_src}\n", {"R2"}),
        ("fake_url", f"{FACT_PREFIX}STR-06] 探针：错 URL || anchor: ch{row['no']} {row['official_url']}0 {row['first_pub']} || src: {valid_src}\n", {"R2"}),
        ("fake_time", f"{FACT_PREFIX}STR-07] 探针：错首发时间 || anchor: ch{row['no']} {row['official_url']} 2000-01-01 00:00:00 || src: {valid_src}\n", {"R2"}),
        ("fake_sha", f"{FACT_PREFIX}STR-08] 探针：错 sha 前缀 || anchor: {valid_anchor} || src: sha256=000000000000 lines={a}-{b}\n", {"R2"}),
        ("fake_lines", f"{FACT_PREFIX}STR-09] 探针：错行区间 || anchor: {valid_anchor} || src: sha256={l0_sha12} lines={a + 1}-{b + 1}\n", {"R2"}),
        ("bad_src", f"{FACT_PREFIX}STR-10] 探针：src 段残缺 || anchor: {valid_anchor} || src: lines={a}-{b}\n", {"R2"}),
        ("malformed_anchor", f"{FACT_PREFIX}STR-11] 探针：锚点残缺 || anchor: ch{row['no']}\n", {"R1"}),
        ("body_in_quote", f"探针：非事实行内的合成长段“{probe_text()}”\n", {"R5"}),
        ("body_unquoted", f"探针：非事实行内引号外合成长串 {probe_text()}\n", {"R6"}),
        ("body_unquoted_in_fact", f"{FACT_PREFIX}STR-13] 探针：事实行内引号外正文段 {probe_text()} || anchor: {valid_anchor} || src: {valid_src}\n", {"R6"}),
        ("body_in_fact", f"{FACT_PREFIX}STR-12] 探针：事实行内正文段“{probe_text()}。另起一句。” || anchor: {valid_anchor} || src: {valid_src}\n", {"R5", "R7"}),
    ]
    negatives = [
        ("valid_b_ok", valid_line, {"R1", "R2", "R3", "R5", "R6", "R7"}),
        ("cid_redundant_ok", f"{FACT_PREFIX}STR-01] 探针：cid 冗余并存 || anchor: {valid_anchor} cid:648165987 || src: {valid_src}\n", {"R1", "R2", "R5", "R6", "R7"}),
        ("short_quote_ok", f"探针：技术性短引文“{short_quote_text()}”不应判红\n", {"R5", "R6", "R7"}),
        ("title_ok", "探针：引用作品名《我的治愈系游戏》与章节号 ch109 不应判红\n", {"R5", "R6", "R7"}),
    ]
    tmp_root = tempfile.mkdtemp(prefix="fidelity-lint-probe-")
    try:
        results = []
        # 基线：合成树只有合法 B 锚点行 ⇒ 0 违规
        _probe_tree(tmp_root, row, valid_line)
        base = Lint(tmp_root, index, l0_sha12)
        base.run()
        baseline_n = len(base.violations)
        ok = ok and baseline_n == 0
        for name, body, expect in cases:
            _probe_tree(tmp_root, row, body)
            lc = Lint(tmp_root, index, l0_sha12)
            lc.run()
            got = {r for (_f, _l, r, _n) in lc.violations}
            hit = got == expect
            results.append({"case": name, "expect": sorted(expect), "got": sorted(got), "fired": hit})
            ok = ok and hit
        for name, body, must_absent in negatives:
            _probe_tree(tmp_root, row, body)
            lc = Lint(tmp_root, index, l0_sha12)
            lc.run()
            got = {r for (_f, _l, r, _n) in lc.violations}
            clean = not (got & must_absent)
            results.append({"case": name, "expect_absent": sorted(must_absent), "got": sorted(got), "clean": clean})
            ok = ok and clean
        # 全部移除后必须回基线
        _probe_tree(tmp_root, row, valid_line)
        back = Lint(tmp_root, index, l0_sha12)
        back.run()
        back_to_baseline = len(back.violations) == baseline_n == 0
        ok = ok and back_to_baseline
        print(json.dumps({"probe": results, "baseline_violations": baseline_n,
                          "back_to_baseline": back_to_baseline, "probe_ok": ok,
                          "probe_anchor_row": {"no": row["no"], "src_line_start": row["src_line_start"],
                                               "src_line_end": row["src_line_end"]}},
                         ensure_ascii=False, sort_keys=True))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return 0 if ok else 1


# ----------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="M5.1 出处表事实行 lint（R1~R7；R2 = L0 口径 B）")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--probe", action="store_true")
    # M5.1 r2.6（PM m5-08 §三.1/.5）：门禁**自证项**专用入口 —— 只跑探针、**不扫真实树**，
    #   使「自证好不好」与「树干不干净」彻底解耦（退出码不再把两者合成一个红）。
    #   隔离面声明：本分支只读 `--index` / `--l0-sha256`（判据的输入参数）与 tempfile 合成树，
    #   一次都不读 `--root` 下的册 ⇒ probe_ok 与树状态无关（§3 负对照① 的正面证据）。
    ap.add_argument("--probe-only", action="store_true",
                    help="只跑自证探针（合成树；不扫真实树）⇒ 判定字段 probe_ok 与树状态无关")
    ap.add_argument("--root", default=None)
    ap.add_argument("--index", default=None, help="L1 全本索引（B 口径锚点唯一来源）")
    ap.add_argument("--catalog", default=None, help="（别名，向后兼容）等同于 --index")
    ap.add_argument("--l0-sha256", default=None, help="L0 全本 sha256（只取前 12 位比较）")
    args = ap.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))
    root = args.root or os.path.dirname(here)
    index = args.index or args.catalog or default_index_path(root)
    l0_sha12 = (args.l0_sha256 or DEFAULT_L0_SHA12)[:12]
    if not os.path.isdir(root):
        print(f"usage: --root not a directory: {root}", file=sys.stderr)
        return 2
    if not os.path.isfile(index):
        print(f"usage: --index not found: {index}", file=sys.stderr)
        return 2
    if args.probe_only:
        # 隔离面（PM m5-08 §三.5 / §8.4）：只跑探针，**不构造 Lint(root)**、不读任何册。
        return run_probe(index, l0_sha12)
    try:
        lc = Lint(root, index, l0_sha12)
    except ValueError as exc:
        print(f"usage: {exc}", file=sys.stderr)
        return 2
    rc = lc.run()
    if rc == 2:
        return 2
    rc = emit(lc, args.strict)
    if args.probe:
        prc = run_probe(index, l0_sha12)
        return 0 if (rc == 0 and prc == 0) else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
