#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""redline_scan.py — M5.1 红线机械判据（设计 v3 §5.7 / **PM 裁决 m5-07 §一** / G7；主判据 = 内容比对）。

规则（v3 + m5-07）：
  ① `l0_verbatim`（**主判据，取代引号形态成为红线第一道**）
     **比对单元 = 文件级连续串**（M5.1 r2.7 / PM 裁决 m5-07 **§1.1 原文**）：目标文件**整个**取
     「仅含 CJK 的归一化串」（去掉标点 / 空白 / 引号 / 数字 / 拉丁字母，**跨行拼接**），
     与**同法归一化的 L0 全本**做逐字比对：文件里出现长度 ≥ `--ngram`（**默认 16**，PM m5-07 §一.2）
     的连续串与 L0 逐字相同 ⇒ 违规。
     **形态无关**：加不加引号、用哪种引号、引号配对错位、是否按标点切句、是否把片段嵌在更长的中文行里，
     **都不影响**命中（堵掉 Raven R-1 的四条绕过路径）。
     **为什么必须文件级**（Raven 风险门禁第二遍 **R-8** 实证）：按行比对时，把任意长的逐字正文
     **拆成每行 15 CJK**（< 下界 16）即可让**三个判据全部隐形**——210 CJK 拆 14 行 ×15 ⇒
     `redline_scan` primary 0 / `fidelity_lint` 0 / `scan_ip_boundary` 0；而同样内容**两行 ×105** ⇒
     命中 105/105。⇒ 按行切段曾是**任意长**逐字正文的通用逃逸面；归一化跨行拼接后，切行不再产生逃逸面
     （负向对照 ① 已固化为单测与自证探针用例）。
     **机械白名单**：命中串若是 `L1-fulltext-index.tsv` 里某章 **`official_title`** 的子串 ⇒ 自动豁免并计数
     （官方标题是元数据不是正文；白名单是**算出来的**，不是手写的 —— m5-07 §一.3）。
  ② `quoted_body`  引号内（“”/「」）命中 D-4 规则 ⇒ 命中（次要规则，保留）
                    D-4 = CJK ≥ 60，或 CJK ≥ 24 且含 ≥2 个句末/分句标点（。！？；）
  ③ `long_cjk_run` 引号**外**连续 CJK 串 ≥ `--long-run`（默认 120）⇒ 记为可疑长串（次要规则）

扫描面（m5-07 §一.5/§一.6；`--profile`）：
  * `delivery`（**默认 = 门禁面**）：`02_source/**` + `docs/**` + 根级 `03_artisan_self_test.log` /
    `V0_M5.sha256` / `0*.md`；**按名排除**（在 `scope` 里显式声明，不得静默）：`refs/**`（源镜像本身）、
    `spikes/**`（参考 fixture）、`.squad_result.txt` 与 `.task-*.out`（**原始子代理转录，改了即篡改证据**）。
  * `workspace`：整个 workspace 根（只排 `.git` / `node_modules` / 二进制资产），作**辅助读数**用。

后缀策略（v3 = Raven R-2）：目录递归扫**所有**文件，只按**二进制 / 资产黑名单**排除
（`*.png/*.jpg/...`）；**未知后缀照样扫**，并把这些文件列进 JSON 的 `unknown_suffix_files[]` 供人复核。

L0 缺件 ⇒ **SKIP + 显式标记**（`E_REDLINE_L0_MISSING`，exit 3），**不得**记 PASS。

输出：逐面打印 `path:line:kind:length`（**绝不打印命中文本**；m5-07 §一.4 的读数格式 = `文件:行:长度`，
`length` = 该行**最长逐字连续片段**的长度）+ JSON 摘要（`scope` / 各面命中数 / 逐规则命中数 / 白名单计数 /
未知后缀文件清单 / L0 归一化读数）。
退出码：`0` = **非白名单 `l0_verbatim` 命中数 = 0**（m5-07 §一.4 的出口判据；次要规则默认只出读数，
`--fail-on-secondary` 可把它们也计入退出码）/ `1` = 有命中 / `2` = 用法错误 /
`3` = SKIP（L0 缺件，显式标记，**不是** PASS）。
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import sys
import tempfile
from array import array
from bisect import bisect_left, bisect_right

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
SENT_PUNCT = "。！？；"

# 已知文本后缀（**只用于「未知后缀告警」**，不再作为扫描白名单 —— Raven R-2）。
KNOWN_TEXT_SUFFIXES = [
    ".md", ".txt", ".log", ".out", ".tsv", ".csv", ".json", ".jsonl", ".py", ".sh", ".bash",
    ".zsh", ".yaml", ".yml", ".html", ".htm", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".css", ".xml", ".toml", ".ini", ".cfg", ".conf", ".sql", ".rst", ".tex", ".sig", ".lock",
    ".gitignore", ".env", ".po", ".pot", ".properties", ".gradle", ".rs", ".go", ".java", ".rb",
]
# 二进制 / 资产黑名单（R-2）：这些**不扫**（无文本语义），其余后缀一律照扫。
BINARY_SUFFIX_BLACKLIST = [
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tif", ".tiff", ".psd", ".ai",
    ".sqlite", ".sqlite3", ".db", ".pyc", ".pyo", ".pyd", ".so", ".dylib", ".dll", ".a", ".o",
    ".class", ".jar", ".war", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".woff", ".woff2", ".ttf", ".otf",
    ".eot", ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".bin", ".dat", ".exe", ".msi", ".dmg", ".iso", ".img", ".wasm", ".npy", ".npz", ".pkl",
    ".pt", ".onnx", ".h5", ".parquet", ".arrow", ".feather", ".blend", ".fbx", ".obj", ".glb",
    ".gltf", ".ktx", ".ktx2", ".basis", ".dds", ".exr", ".hdr", ".cube",
]
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
             ".ruff_cache", ".venv", "venv", ".idea", ".vscode"}
DEFAULT_NGRAM = 16           # PM m5-07 §一.2：交付面现存命中落在 16/20/21 三档 ⇒ 下界取 16
DEFAULT_LONG_RUN = 120

# 门禁面（m5-07 §一.5）与按名排除清单（m5-07 §一.6；**必须**在 `scope` 里显式声明，不得静默）。
DELIVERY_FACE_DIRS = ("02_source", "docs")
DELIVERY_FACE_FILES = ("03_artisan_self_test.log", "V0_M5.sha256")
DELIVERY_FACE_GLOBS = ("0*.md",)
NAMED_EXCLUDES = ("refs", "spikes", ".squad_result.txt", ".task-*.out")

_HASH_P = 1000003
_HASH_MASK = (1 << 64) - 1
# L0 侧预筛索引缓存：ngram -> (l0_norm 对象, 排序哈希数组)。持有 norm 引用 ⇒ id 不会被回收复用。
_L0_INDEX_CACHE = {}


def cjk_count(text: str) -> int:
    return len(CJK_RE.findall(text))


def normalize_cjk(text: str) -> str:
    """归一化：只保留 CJK（去标点 / 空白 / 引号 / 数字 / 拉丁字母）。"""
    return "".join(CJK_RE.findall(text))


def d4_hit(text: str) -> bool:
    n = cjk_count(text)
    if n >= 60:
        return True
    if n >= 24:
        return sum(text.count(p) for p in SENT_PUNCT) >= 2
    return False


def quoted_segments(line: str):
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
            out.append(line[i + 1:j])
            start = j + 1
    return out


def strip_quoted(line: str) -> str:
    for opener, closer in (("“", "”"), ("「", "」")):
        line = re.sub(re.escape(opener) + r"[^" + re.escape(closer) + r"]*" + re.escape(closer), "", line)
    return line


# ----------------------------------------------------------------- 文件遍历（R-2）
def suffix_of(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def _is_excluded(path: str, excludes) -> bool:
    """按名排除：精确路径 / 目录前缀 / glob（如 `.task-*.out`）。"""
    for e in excludes:
        if not e:
            continue
        if path == e or path.startswith(e.rstrip("/") + "/"):
            return True
        if fnmatch.fnmatch(path, e) or fnmatch.fnmatch(os.path.basename(path), e):
            return True
    return False


def iter_files(root: str, excludes):
    """递归遍历**所有**非黑名单文件（后缀白名单已废除）；返回 (files, unknown_suffix_files)。"""
    files, unknown = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if _is_excluded(path, excludes):
                continue
            suf = suffix_of(name)
            if suf in BINARY_SUFFIX_BLACKLIST:
                continue
            files.append(path)
            if suf not in KNOWN_TEXT_SUFFIXES:
                unknown.append(path)
    return files, unknown


def delivery_face_targets(ws_root: str) -> list:
    """门禁面（m5-07 §一.5）：`02_source/**` + `docs/**` + 根级日志/生成物/`0*.md` 交付件。"""
    targets = []
    for d in DELIVERY_FACE_DIRS:
        p = os.path.join(ws_root, d)
        if os.path.isdir(p):
            targets.append(p)
    for f in DELIVERY_FACE_FILES:
        p = os.path.join(ws_root, f)
        if os.path.isfile(p):
            targets.append(p)
    for g in DELIVERY_FACE_GLOBS:
        for name in sorted(os.listdir(ws_root)):
            p = os.path.join(ws_root, name)
            if fnmatch.fnmatch(name, g) and os.path.isfile(p):
                targets.append(p)
    return targets


def profile_targets(profile: str, ws_root: str, root, paths) -> tuple:
    """返回 (targets, named_excludes)。`delivery` = 门禁面 + 按名排除；`workspace` = 全根（辅助读数）。"""
    if paths:
        return list(paths), []
    if profile == "delivery":
        return delivery_face_targets(ws_root), [os.path.join(ws_root, e) for e in NAMED_EXCLUDES]
    return [root or ws_root], []


def collect_targets(targets, excludes):
    files, unknown = [], []
    for t in targets:
        if os.path.isdir(t):
            f, u = iter_files(t, excludes)
            files.extend(f)
            unknown.extend(u)
        elif os.path.isfile(t):
            if _is_excluded(t, excludes):
                continue
            files.append(t)
            if suffix_of(t) not in KNOWN_TEXT_SUFFIXES:
                unknown.append(t)
    return files, sorted(set(unknown))


# ----------------------------------------------------------------- 逐行扫描（次要规则）
def scan_file(path: str, long_run: int):
    hits = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.rstrip("\n")
                for seg in quoted_segments(line):
                    if d4_hit(seg):
                        hits.append((path, lineno, "quoted_body", cjk_count(seg)))
                for run in RUN_RE.findall(strip_quoted(line)):
                    if len(run) >= long_run:
                        hits.append((path, lineno, "long_cjk_run", len(run)))
    except (OSError, UnicodeDecodeError):
        pass
    return hits


def cjk_stream_with_offsets(text: str):
    """**文件级**归一化（PM m5-07 §1.1）：返回 `(norm, offs)`。

    * `norm` = 按**文件顺序**把整个文件里的 CJK 字符拼成的**连续串**（跨行、丢标点/空白/引号/数字/拉丁）；
    * `offs[i]` = `norm[i]` 在**原文中的字符下标** —— 这就是「归一化流位置 → 原始行号」的映射基础
      （归一化丢掉了换行符，无法在原文里直接 find 命中串，必须靠这张表反查行号）。
    """
    chars, offs = [], []
    for m in CJK_RE.finditer(text):
        chars.append(m.group())
        offs.append(m.start())
    return "".join(chars), offs


def load_target_stream(path: str, ngram: int):
    """读**整个文件** ⇒ `(norm, offs, newline_positions)`；CJK 不足 `ngram` ⇒ `(None, None, None)`。

    行号反查：`line = bisect_right(newline_positions, offs[start]) + 1`（原文里第 start 个 CJK 落在哪一行）。
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError):
        return None, None, None
    norm, offs = cjk_stream_with_offsets(text)
    if len(norm) < ngram:
        return None, None, None
    newlines = [i for i, ch in enumerate(text) if ch == "\n"]
    return norm, offs, newlines


# ----------------------------------------------------------------- 内容比对（主判据）
def rolling_hashes(seq: str, k: int):
    """滚动哈希：逐位产出 (起始下标, k 长窗口哈希)。"""
    n = len(seq)
    if n < k:
        return
    h = 0
    for ch in seq[:k]:
        h = (h * _HASH_P + ord(ch)) & _HASH_MASK
    yield 0, h
    pk = pow(_HASH_P, k - 1, 1 << 64)
    for i in range(k, n):
        h = ((h - ord(seq[i - k]) * pk) * _HASH_P + ord(seq[i])) & _HASH_MASK
        yield i - k + 1, h


def load_l0_norm(path: str) -> str:
    """L0 全本归一化（按行取 CJK 后拼接；行序不变）。"""
    parts = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            parts.append(normalize_cjk(raw))
    return "".join(parts)


def load_title_norms(index: str):
    """索引里已登记 **`official_title`** 的归一化形式（机械白名单，m5-07 §一.3）。

    白名单只认官方标题（元数据），**不含** `title` 列 —— 任何新增豁免规则都要 PM 签字。
    """
    norms = set()
    if not index or not os.path.isfile(index):
        return norms
    with open(index, encoding="utf-8", errors="replace") as fh:
        header = fh.readline().rstrip("\r\n").split("\t")
        if "official_title" not in header:
            return norms
        col = header.index("official_title")
        for line in fh:
            parts = line.rstrip("\r\n").split("\t")
            if col < len(parts):
                n = normalize_cjk(parts[col])
                if n:
                    norms.add(n)
    return norms


def title_exempt(window: str, title_norms) -> bool:
    """命中串是已登记 **official_title**（归一化）的子串 ⇒ 自动豁免（官方标题是元数据不是正文）。"""
    return any(window in t for t in title_norms)


def build_l0_hash_index(l0_norm: str, ngram: int):
    """L0 侧**预筛**：L0 全本所有 `ngram` 窗口的滚动哈希装进**排序数组**（`array('Q')`，8 B/条）。

    * 内存有界（3.4M CJK ⇒ 约 27 MB），比 `set[int]` 省一个量级；
    * 成员判定 = `bisect_left`（O(log n)），比逐窗口 `in l0_norm` 子串搜索快得多；
    * 哈希**只是预筛**：预筛命中处一律再做精确复核（`_exact_window_hit`）⇒ 64 位碰撞不会 fail-open。
    * 缓存：同一进程内同一 `l0_norm` 对象 + 同一 `ngram` 只建一次（自证探针会多次调用本函数）。
    """
    cached = _L0_INDEX_CACHE.get(ngram)
    if cached is not None and cached[0] is l0_norm:
        return cached[1]
    arr = array("Q", sorted(h for _i, h in rolling_hashes(l0_norm, ngram)))
    _L0_INDEX_CACHE[ngram] = (l0_norm, arr)
    return arr


def _in_hash_index(arr, h: int) -> bool:
    i = bisect_left(arr, h)
    return i < len(arr) and arr[i] == h


def _exact_window_hit(norm: str, k: int, ngram: int, l0_norm: str) -> bool:
    """预筛命中后的**精确**复核：该窗口必须真的逐字出现在 L0 里（哈希碰撞 ⇒ 不得误报）。"""
    return norm[k:k + ngram] in l0_norm


def l0_verbatim_hits(files, l0_norm: str, ngram: int, title_norms):
    """主判据（**文件级**归一化，PM 裁决 m5-07 **§1.1**）：整个文件拼成的连续 CJK 串与 L0 逐字比对。

    返回 `(hits, readings)`；`hits` 每条 = `(path, lineno, "l0_verbatim", run_len)`：

    * **比对单元 = 文件**（不是行）⇒ 把逐字正文切成任意多行都不产生逃逸面（Raven R-8）；
    * `run_len` = 归一化流里**连续命中窗口**聚成的一段（run）的长度；
    * `lineno` = 该 run **起点**在原始文件里的行号（由 `offs` + 换行位置表反查 —— 见 `load_target_stream`）；
    * 命中跨度若是某章 `official_title`（同法归一化）的**子串** ⇒ 机械豁免并计数（`exempt_title_spans`）。
    """
    hits = []
    exempt = 0
    cand_files = 0
    cand_chars = 0
    if len(l0_norm) >= ngram:
        idx = build_l0_hash_index(l0_norm, ngram)
        for path in files:
            norm, offs, newlines = load_target_stream(path, ngram)
            if norm is None:
                continue
            cand_files += 1
            cand_chars += len(norm)
            matched = bytearray(len(norm) - ngram + 1)
            for k, h in rolling_hashes(norm, ngram):
                if _in_hash_index(idx, h) and _exact_window_hit(norm, k, ngram, l0_norm):
                    matched[k] = 1
            k = 0
            while k < len(matched):
                if not matched[k]:
                    k += 1
                    continue
                j = k
                while j < len(matched) and matched[j]:
                    j += 1
                run_len = (j - k) + ngram - 1
                if title_exempt(norm[k:k + run_len], title_norms):
                    exempt += 1
                else:
                    hits.append((path, bisect_right(newlines, offs[k]) + 1, "l0_verbatim", run_len))
                k = j
    readings = {
        "normalization": "file_level",      # 比对单元显式声明（PM m5-07 §1.1；r2.7 由 line_level 改来）
        "l0_cjk_chars": len(l0_norm),
        "ngram": ngram,
        "candidate_files": cand_files,
        "candidate_cjk_chars": cand_chars,
        "exempt_title_spans": exempt,
        "registered_titles": len(title_norms),
    }
    return hits, readings


# ----------------------------------------------------------------- 探针
def _repo_negative_line(root: str, ngram: int):
    """本仓自有的技术性中文行（≥ngram CJK）——负对照：**不得**命中 l0_verbatim。"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(root, "manifest.txt"), os.path.join(root, "02_source", "manifest.txt"),
                  os.path.normpath(os.path.join(here, "..", "..", "manifest.txt"))]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for raw in fh:
                    if len(normalize_cjk(raw)) >= ngram:
                        return path, raw.strip()
        except OSError:
            continue
    return None, None


def _synthetic_negative_line(ngram: int) -> str:
    """**运行时构造**的技术性中文行（≥ngram CJK）—— 负对照用，**不读被测树**。

    `--probe-only`（门禁自证项）走这条：探针的输入不得取自被测对象（PM m5-08 §8.4）。
    断言强度与 `_repo_negative_line` 完全相同：技术性中文行 ⇒ **不得**命中 l0_verbatim。
    """
    line = "".join(["探针技术性中文行", "由运行时拼接构造", "不取自任何原著正文",
                    "也不构成连续命中窗口", "仅用于验证负对照是否成立"])
    while len(normalize_cjk(line)) < ngram:
        line += "补充技术性描述"
    return line


def _probe_scan(tmp: str, name: str, body: str, l0_norm: str, ngram: int, title_norms):
    """在临时树里注入一个探针文件并扫一次 ⇒ `(fired, hits, max_run_len)`；扫完删掉。"""
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body + "\n")
    files, _unk = iter_files(tmp, [])
    hits, _r = l0_verbatim_hits(files, l0_norm, ngram, title_norms)
    os.remove(path)
    fired = any(h[2] == "l0_verbatim" for h in hits)
    return fired, len(hits), max((h[3] for h in hits if h[2] == "l0_verbatim"), default=0)


def run_probe(root, l0_norm: str, ngram: int, title_norms, baseline_hits: int,
              negative_from_tree: bool = True) -> int:
    """正 / 负对照（R-1 要求逐条落读数）。

    ① 正对照（形态无关）：**运行时**从 L0 取一段 CJK，**去标点后**注入 `/tmp` 临时树 ⇒ **必须命中**
       （禁止把任何 L0 正文片段落进 workspace 文件；探针文本一律运行时构造）：
       * `positive_l0_excerpt_punctuation_stripped` —— 60 CJK 去标点（原 R-1 形态面）；
       * **`positive_l0_excerpt_split_15_cjk_per_line`** —— 210 CJK **拆成 14 行 × 15 CJK** ⇒ 必须命中
         （**本轮核心用例**：Raven R-8 实证的「按行切段」逃逸面；文件级归一化后该路径被堵死）；
       * `positive_l0_excerpt_two_lines_of_105` —— 210 CJK 两行 ×105（R-8 的对照臂）⇒ 必须命中；
       * `positive_form_variants_single_line` —— 同内容**加引号 / 换未登记引号 / 按标点切句（单行）**
         三路（原 R-1 三路）⇒ 每路都必须命中。
    ② 负对照：技术性中文行（≥ngram CJK）⇒ **不得命中**。
       `negative_from_tree=True`（历史行为）取本仓 `manifest.txt` 一行；
       `False`（`--probe-only`，门禁自证项）改用**运行时构造**的行 ⇒ **不读被测树**
       （PM m5-08 §三.5：探针自身不读真实树；断言不变：技术性中文行不得命中）。
    ③ 标题豁免：登记标题（归一化）⇒ 不得命中（标题归一化长度 < ngram 时改测豁免函数本身，显式标记）。
    ④ 移除注入 ⇒ 回基线。
    """
    ok = True
    results = []
    tmp = tempfile.mkdtemp(prefix="redline-probe-")
    try:
        # 基线：空临时树
        files, _unk = iter_files(tmp, [])
        base_hits, _r = l0_verbatim_hits(files, l0_norm, ngram, title_norms)
        baseline = len(base_hits)
        ok = ok and baseline == 0

        # ① 正对照 a：从 L0 运行时取 60 CJK（去标点：每 10 字插一个逗号）
        start = len(l0_norm) // 3
        excerpt = l0_norm[start:start + 60]
        assert len(excerpt) == 60
        punctuated = "，".join(excerpt[i:i + 10] for i in range(0, 60, 10))
        pos_fired, n_hits, _run = _probe_scan(tmp, "probe_positive.md",
                                             "探针：去标点注入的片段 " + punctuated, l0_norm, ngram, title_norms)
        results.append({"case": "positive_l0_excerpt_punctuation_stripped", "fired": pos_fired,
                        "hits": n_hits, "excerpt_cjk": 60})
        ok = ok and pos_fired

        # ① 正对照 b（**本轮核心**）：同一段 210 CJK **拆成 14 行 × 15 CJK** ⇒ 必须命中（R-8 逃逸面被堵）
        block = l0_norm[start:start + 210]
        assert len(block) == 210
        split_lines = "\n".join(block[i:i + 15] for i in range(0, 210, 15))
        assert split_lines.count("\n") == 13, "必须是 14 行"
        split_fired, n_hits, run_len = _probe_scan(tmp, "probe_split_15.md", split_lines, l0_norm, ngram, title_norms)
        results.append({"case": "positive_l0_excerpt_split_15_cjk_per_line", "fired": split_fired,
                        "hits": n_hits, "lines": 14, "cjk_per_line": 15, "excerpt_cjk": 210,
                        "max_run_len": run_len})
        ok = ok and split_fired

        # ① 正对照 c：同内容两行 ×105（R-8 的对照臂：旧实现此处命中 105/105）⇒ 必须命中
        two_lines = block[:105] + "\n" + block[105:]
        two_fired, n_hits, run_len = _probe_scan(tmp, "probe_two_lines.md", two_lines, l0_norm, ngram, title_norms)
        results.append({"case": "positive_l0_excerpt_two_lines_of_105", "fired": two_fired,
                        "hits": n_hits, "lines": 2, "cjk_per_line": 105, "max_run_len": run_len})
        ok = ok and two_fired

        # ① 正对照 d：原 R-1 三路形态变体（加引号 / 未登记引号 / 按标点切句，均在**单行**内）
        variants = {
            "registered_quotes": "“" + block[:60] + "”",
            "unregistered_quotes": "『" + block[:60] + "』",
            "sentence_split": "，".join(block[i:i + 6] for i in range(0, 60, 6)),
        }
        variant_fired = {}
        for name, body in variants.items():
            f, _n, _r = _probe_scan(tmp, f"probe_{name}.md", "探针：" + body, l0_norm, ngram, title_norms)
            variant_fired[name] = f
        all_variants = all(variant_fired.values())
        results.append({"case": "positive_form_variants_single_line", "fired": all_variants,
                        "variants": variant_fired})
        ok = ok and all_variants

        # ② 负对照：技术性中文行（≥ngram CJK）不得命中
        if negative_from_tree:
            neg_path, neg_line = _repo_negative_line(root, ngram)
            neg_source = os.path.basename(neg_path) if neg_path else None
        else:
            neg_path, neg_line = None, _synthetic_negative_line(ngram)
            neg_source = "runtime_synthetic"
        if neg_line is None:
            results.append({"case": "negative_repo_line", "skipped": "no_repo_line_with_enough_cjk"})
            ok = False
        else:
            nf = os.path.join(tmp, "probe_negative.md")
            with open(nf, "w", encoding="utf-8") as fh:
                fh.write(neg_line + "\n")
            files, _unk = iter_files(tmp, [])
            hits, _r = l0_verbatim_hits(files, l0_norm, ngram, title_norms)
            neg_clean = not any(h[2] == "l0_verbatim" for h in hits)
            results.append({"case": "negative_repo_line", "clean": neg_clean,
                            "source": neg_source,
                            "normalized_cjk": len(normalize_cjk(neg_line))})
            ok = ok and neg_clean
            os.remove(nf)

        # ③ 标题豁免
        long_titles = [t for t in title_norms if len(t) >= ngram]
        if long_titles:
            tf = os.path.join(tmp, "probe_title.md")
            with open(tf, "w", encoding="utf-8") as fh:
                fh.write("探针：登记标题引用 " + long_titles[0] + "\n")
            files, _unk = iter_files(tmp, [])
            hits, _r = l0_verbatim_hits(files, l0_norm, ngram, title_norms)
            t_clean = not any(h[2] == "l0_verbatim" for h in hits)
            results.append({"case": "title_exemption", "clean": t_clean,
                            "longest_registered_title_cjk": max(len(t) for t in title_norms)})
            ok = ok and t_clean
            os.remove(tf)
        else:
            max_t = max((len(t) for t in title_norms), default=0)
            helper_ok = bool(title_norms) and title_exempt(next(iter(sorted(title_norms))), title_norms)
            results.append({"case": "title_exemption", "clean": helper_ok,
                            "skipped": "max_registered_title_cjk_below_ngram",
                            "max_registered_title_cjk": max_t,
                            "note": "改测豁免函数本身（标题归一化长度 < ngram ⇒ 不存在可命中的候选窗口）"})
            ok = ok and helper_ok

        # ④ 移除注入 ⇒ 回基线
        files, _unk = iter_files(tmp, [])
        back_hits, _r = l0_verbatim_hits(files, l0_norm, ngram, title_norms)
        back_to_baseline = len(back_hits) == baseline
        results.append({"case": "back_to_baseline", "hits": len(back_hits), "baseline": baseline})
        ok = ok and back_to_baseline
        print(json.dumps({"probe": results, "probe_ok": ok,
                          "baseline_hits": baseline_hits, "tmp_baseline_hits": baseline},
                         ensure_ascii=False, sort_keys=True))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


# ----------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="M5.1 红线扫描（l0_verbatim 内容比对 + 引号形态 + 长串）")
    ap.add_argument("--root", default=None, help="workspace 根（--profile delivery 时用于定位门禁面）")
    ap.add_argument("--paths", default=None, help="显式文件或目录列表（逗号分隔；给了就忽略 --profile）")
    ap.add_argument("--profile", choices=("delivery", "workspace"), default="delivery",
                    help="delivery = 门禁面（m5-07 §一.5）+ 按名排除；workspace = 整个 workspace 根（辅助读数）")
    ap.add_argument("--source-l0", default=None, help="L0 全本路径（l0_verbatim 主判据的来源）")
    ap.add_argument("--index", default=None, help="L1 全本索引（official_title 机械白名单来源）")
    ap.add_argument("--ngram", type=int, default=DEFAULT_NGRAM, help="l0_verbatim 的 CJK 串下界（默认 16）")
    ap.add_argument("--long-run", type=int, default=DEFAULT_LONG_RUN)
    ap.add_argument("--exclude", default=None, help="额外按名排除（逗号分隔；会在 scope 里登记）")
    ap.add_argument("--probe", action="store_true")
    # M5.1 r2.6（PM m5-08 §三.5）：门禁自证项专用入口 —— 只跑探针，**不扫真实树**。
    #   历史调用点靠 `--paths "$WS_ROOT/docs"` 挑一个「恰好干净」的 scope 来规避树状态
    #   ⇒ 那是脆弱耦合。本入口把隔离写进工具自身：探针只在 tempfile 临时树上跑，
    #   负对照行**运行时构造**（不读被测树）⇒ 判定字段 probe_ok 与树状态解耦。
    ap.add_argument("--probe-only", action="store_true",
                    help="只跑自证探针（临时树 + 运行时构造的负对照行；不扫真实树）")
    ap.add_argument("--fail-on-secondary", action="store_true",
                    help="把次要规则（quoted_body / long_cjk_run）也计入退出码（默认只按 PM m5-07 §一.4 "
                         "的出口判据：非白名单 l0_verbatim 命中数 = 0）")
    ap.add_argument("--json-only", action="store_true", help="只打 JSON 摘要，不打逐条命中")
    args = ap.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))          # {ws}/02_source/fidelity/tools
    ws_default = os.path.normpath(os.path.join(here, "..", "..", ".."))   # {ws}
    ws_root = os.path.abspath(args.root) if args.root else ws_default
    l0 = args.source_l0 or os.path.normpath(os.path.join(ws_root, "..", "..", "sources", "deephealing",
                                                         "《我的治愈系游戏》（校对版全本+番外）.txt"))
    index = args.index or os.path.normpath(os.path.join(ws_root, "refs", "original-source",
                                                        "L1-fulltext-index.tsv"))

    explicit_paths = [p for p in (args.paths or "").split(",") if p.strip()]
    if not args.root and not explicit_paths:
        print("usage: need --root <dir> or --paths <list>", file=sys.stderr)
        return 2
    targets, named_excludes = profile_targets(args.profile, ws_root, args.root, explicit_paths)
    extra_excludes = [os.path.abspath(p) if os.path.isabs(p) else os.path.join(ws_root, p)
                      for p in (args.exclude or "").split(",") if p.strip()]
    excludes = named_excludes + extra_excludes
    if not targets and not explicit_paths:
        print("usage: need --root <dir> or --paths <list>", file=sys.stderr)
        return 2
    for t in targets:
        if not os.path.exists(t):
            print(f"usage: path not found: {t}", file=sys.stderr)
            return 2

    l0_status, l0_norm, readings = "ok", "", {}
    if not os.path.isfile(l0):
        l0_status = "skipped_no_l0"
        print(f"E_REDLINE_L0_MISSING: {l0}", file=sys.stderr)

    if args.probe_only:
        # 隔离面声明：本分支不 collect_targets、不扫 root 下任何文件（探针自建临时树）。
        if l0_status != "ok":
            print("SKIP: --probe-only 需要 L0 全本", file=sys.stderr)
            return 3
        return run_probe(None, load_l0_norm(l0), args.ngram, load_title_norms(index), 0,
                         negative_from_tree=False)

    files, unknown = collect_targets(targets, excludes)
    hits = []
    for path in files:
        hits.extend(scan_file(path, args.long_run))
    title_norms = set()
    if l0_status == "ok":
        l0_norm = load_l0_norm(l0)
        title_norms = load_title_norms(index)
        v_hits, readings = l0_verbatim_hits(files, l0_norm, args.ngram, title_norms)
        hits.extend(v_hits)

    if not args.json_only:
        for path, lineno, kind, length in sorted(hits):
            print(f"{path}:{lineno}:{kind}:{length}")
    kinds = ("l0_verbatim", "quoted_body", "long_cjk_run")
    by_kind = {k: sum(1 for h in hits if h[2] == k) for k in kinds}
    primary = by_kind["l0_verbatim"]
    secondary = by_kind["quoted_body"] + by_kind["long_cjk_run"]
    summary = {
        "scope": {
            "profile": args.profile if not explicit_paths else "paths",
            "root": ws_root,
            "targets": targets,
            "named_excludes": excludes,
            "suffix_policy": "binary/asset blacklist + unknown-suffix warning (R-2)",
            "ngram": args.ngram,
            "l0_path": l0,
            "l0_status": l0_status,
            "index": index,
        },
        "files_scanned": len(files),
        "unknown_suffix_files": unknown,
        "long_run": args.long_run,
        "l0_verbatim_readings": readings,
        "hits_total": len(hits),
        "hits_by_kind": by_kind,
        "primary_hits_total": primary,
        "secondary_hits_total": secondary,
        "exit_basis": ("unwhitelisted_l0_verbatim==0 (+ secondary)" if args.fail_on_secondary
                       else "unwhitelisted_l0_verbatim==0"),
        "hits_by_target": {t: sum(1 for h in hits if h[0].startswith(t)) for t in targets},
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))

    if l0_status != "ok":
        # SKIP + 显式标记：不得记 PASS
        print("SKIP: redline l0_verbatim 未执行（L0 缺件）；本项**不是** PASS", file=sys.stderr)
        return 3
    rc = 0 if (primary == 0 and (secondary == 0 or not args.fail_on_secondary)) else 1
    if args.probe:
        prc = run_probe(ws_root, l0_norm, args.ngram, title_norms, len(hits))
        return 0 if (rc == 0 and prc == 0) else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
