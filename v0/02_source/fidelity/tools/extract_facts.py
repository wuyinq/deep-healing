#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_facts.py — M5.1 出处表事实抽取器（**L0 全本 = 第一来源**；镜像降级为交叉校验）。

设计依据：`01_architecture_design.md` v3 §3（P-1~P-5）、PM 裁决 `m5-05` §2-A、F-15/F-17/F-19。

两种模式（`--source`）：
  * `--source l0`（**现行口径 = 事实第一来源**）
      `--fulltext <L0 全本路径> --index <L1-fulltext-index.tsv>`
      · 按索引的 `src_line_start/src_line_end` **切片读取**（**不得**自行推算行号）；
      · 章号用 `no`（**真章号 = 出现次序**；校对版 20 处排版错位以 `no` 为准），`labeled_no` 只作记录；
      · **排除第三方插入广告行**（标记 `yeguoyuedu.com`）：在切片阶段过滤，stdout 给「排除行数」读数；
      · 交叉校验读数：切片 CJK 数 vs 索引 `txt_cjk_chars`（取同一批行 ⇒ 偏差应为 0）。
  * `--source mirror`（**降级为交叉校验用途**，保留原行为）
      `--catalog <chapters.tsv>` + 镜像目录页映射（P-1 禁算术外推 / P-2 重试 ≥3 / P-3 ±12% 容差）。

红线（P-4，最高优先）：
  * 本脚本 **不向交付面写任何正文**；候选窗口（每个 ≤ `--window` 个 CJK 字符）只写 `--out`
    （L0 模式默认 `/tmp/m5-facts-r2-5/candidates.jsonl`；镜像模式的页面缓存在 `--out/cache/`）。
  * stdout **只打统计量**（章数 / 行区间 / 排除行数 / 字数交叉校验 / 命中数），**不打正文**。

用法（L0 模式；workdir = 02_source/fidelity/tools 时相对路径见下）：
    python3 extract_facts.py --source l0 --fulltext <L0.txt> --index <L1-fulltext-index.tsv>
        --chapters 1-107,109,180,240 [--terms 楼长,管理者] [--out /tmp/m5-facts-r2-5]

用法（镜像模式）：
    python3 extract_facts.py --catalog <chapters.tsv> --chapters 1-107,109,180
        --terms 楼长,管理者 --out /tmp/m5-facts-<pid> [--retries 3]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

CJK = re.compile(r"[\u4e00-\u9fff]")
DEFAULT_TERMS = [
    "楼长", "管理者", "友善度", "怨念", "诅咒物", "怪谈", "任务", "等级",
    "属性面板", "接入", "强制在线", "黑盒", "中庭", "房号", "号楼", "楼层",
    "徐琴", "韩非", "屠夫之家", "八号", "小八",
]
DEFAULT_DIR_URL = "https://snwxw.com/books/2/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

# 第三方插入广告行的标记（约束 rev2 §「L0 锚点口径」第 4 条）：抽事实时**必须排除**。
AD_MARKERS = ("yeguoyuedu.com",)
L0_DEFAULT_OUT = "/tmp/m5-facts-r2-5"
INDEX_REQUIRED_COLUMNS = ("no", "src_line_start", "src_line_end")


# ---------------------------------------------------------------- fetch (P-2)
def fetch(url: str, retries: int, timeout: int, sleep: float):
    """返回 (html|None, attempts, http_code, bytes, last_reason)。瞬时空响应会重试。"""
    last_reason = ""
    code = "-"
    size = 0
    for attempt in range(1, retries + 1):
        try:
            proc = subprocess.run(
                ["curl", "-sS", "-m", str(timeout), "-A", UA, "-w", "\n%{http_code} %{size_download}", url],
                capture_output=True, text=True,
            )
            body, _, meta = proc.stdout.rpartition("\n")
            parts = meta.split()
            code = parts[0] if parts else "-"
            size = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            if code == "200" and size > 1500:
                return body, attempt, code, size, ""
            last_reason = f"http={code} bytes={size}"
        except Exception as exc:  # noqa: BLE001
            last_reason = f"exc={type(exc).__name__}"
        if attempt < retries:
            time.sleep(sleep)
    return None, retries, code, size, last_reason or "unknown"


def parse_dir_map(html: str, base: str = "https://snwxw.com") -> dict:
    """P-1：从镜像目录页解析 章号 -> URL（按链接文本里的 `第N章`，含中文数字排版）。"""
    mapping = {}
    for href, text in re.findall(r'href="([^"]*?/read/\d+/\d+\.html)"[^>]*>(.*?)</a>', html, re.S):
        title = re.sub(r"<[^>]+>", "", text).strip()
        no = title_chapter_no(title)
        if no is None:
            continue
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = base.rstrip("/") + href
        mapping.setdefault(no, href)
    return mapping


def content_div(html: str) -> str:
    """正文在 div#content（F-15 实测）。返回纯文本（去标签）。"""
    m = re.search(r'<div[^>]*id="content"[^>]*>(.*?)</div>', html, re.S)
    if not m:
        m = re.search(r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>', html, re.S)
    if not m:
        return ""
    seg = m.group(1)
    seg = re.sub(r"<br\s*/?>", "\n", seg)
    seg = re.sub(r"</p>", "\n", seg)
    seg = re.sub(r"<[^>]+>", "", seg)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"),
                    ("&lt;", "<"), ("&gt;", ">")):
        seg = seg.replace(ent, ch)
    return seg


def cjk_count(text: str) -> int:
    return len(CJK.findall(text))


# 索引 `txt_cjk_chars` 的口径（逐字对齐 `refs/original-source/verify_l1_fulltext.py: cjk_len`）：
#   CJK 汉字 + 中文标点（与官方「章节字数」同量级）。交叉校验必须**同口径**才有意义。
INDEX_CJK_PUNCT = "，。！？：；、“”‘’（）《》…—·【】"


def index_cjk_len(text: str) -> int:
    """与索引 `txt_cjk_chars` 同口径的字数（CJK 汉字 + 中文标点）。"""
    return sum(
        1
        for ch in text
        if "\u4e00" <= ch <= "\u9fff"
        or "\u3000" <= ch <= "\u303f"
        or ch in INDEX_CJK_PUNCT
    )


def make_window(text: str, start: int, end: int, cap: int = 24, side: int = 12) -> str:
    """构造以命中为中心的窗口：总 CJK 数 ≤ cap（默认 24）。"""
    left = start
    seen = 0
    while left > 0 and seen < side:
        left -= 1
        if CJK.match(text[left]):
            seen += 1
    right = end
    seen = 0
    while right < len(text) and seen < side:
        if CJK.match(text[right]):
            seen += 1
        right += 1
    win = text[left:right]
    win = re.sub(r"\s+", " ", win).strip()
    # 硬上限：截到 cap 个 CJK 为止
    if cjk_count(win) > cap:
        out = []
        n = 0
        for ch in win:
            if CJK.match(ch):
                n += 1
            out.append(ch)
            if n >= cap:
                break
        win = "".join(out)
    return win


def load_chapters(catalog: str) -> dict:
    rows = {}
    with open(catalog, encoding="utf-8") as fh:
        header = fh.readline().rstrip("\r\n").split("\t")
        for line in fh:
            cols = line.rstrip("\r\n").split("\t")
            if len(cols) < len(header):
                continue
            rec = dict(zip(header, cols))
            rows[rec["cid"]] = rec
            if rec["no"]:
                rows[rec["no"]] = rec
    return rows


def parse_targets(spec: str) -> list:
    """目标章号；支持区间 `1-107` 与 `cid:648165987`（ext 卷空章号章的兜底形式）。"""
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("cid:"):
            out.append(part)
        elif "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def title_chapter_no(title: str):
    """从官方标题取章号（含中文数字排版的第一百八十章）。"""
    m = re.match(r"第(\d+)章", title)
    if m:
        return int(m.group(1))
    m = re.match(r"第([零一二三四五六七八九十百千]+)章", title)
    if not m:
        return None
    digits = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
              "八": 8, "九": 9}
    s = m.group(1)
    total, section, num = 0, 0, 0
    for ch in s:
        if ch in digits:
            num = digits[ch]
        elif ch == "十":
            section += (num or 1) * 10
            num = 0
        elif ch == "百":
            section += (num or 1) * 100
            num = 0
        elif ch == "千":
            section += (num or 1) * 1000
            num = 0
    return total + section + num


# ---------------------------------------------------------------- L0 模式（第一来源）
def load_index_rows(index: str) -> list:
    """载入 L1 全本索引（保留行序）；缺必需列 ⇒ ValueError（fail-closed）。"""
    rows = []
    with open(index, encoding="utf-8") as fh:
        header = fh.readline().rstrip("\r\n").split("\t")
        missing = [c for c in INDEX_REQUIRED_COLUMNS if c not in header]
        if missing:
            raise ValueError(f"index lacks required columns {missing}: {index}")
        for line in fh:
            cols = line.rstrip("\r\n").split("\t")
            if len(cols) < len(header):
                continue
            rows.append(dict(zip(header, cols)))
    return rows


def ad_line_numbers(lines) -> list:
    """第三方插入广告行的行号（1-indexed）。"""
    return [i + 1 for i, ln in enumerate(lines) if any(m in ln for m in AD_MARKERS)]


def slice_by_index(lines, start, end) -> tuple:
    """按索引 `src_line_start/src_line_end`（1-indexed 闭区间）切片并过滤广告行。

    返回 (正文文本, 排除行数)。**不得**自行推算行号 —— 区间一律由调用方从索引取。
    """
    a, b = int(start), int(end)
    if a < 1 or b < a:
        return "", 0
    kept, excluded = [], 0
    for ln in lines[a - 1:b]:
        if any(m in ln for m in AD_MARKERS):
            excluded += 1
            continue
        kept.append(ln)
    return "\n".join(kept), excluded


def l0_mode(args) -> int:
    if not args.fulltext:
        print("usage: --source l0 requires --fulltext <L0 全本路径>", file=sys.stderr)
        return 2
    if not args.index:
        print("usage: --source l0 requires --index <L1-fulltext-index.tsv>", file=sys.stderr)
        return 2
    if not os.path.isfile(args.fulltext):
        print(f"usage: --fulltext not found: {args.fulltext}", file=sys.stderr)
        return 2
    if not os.path.isfile(args.index):
        print(f"usage: --index not found: {args.index}", file=sys.stderr)
        return 2
    try:
        rows = load_index_rows(args.index)
    except ValueError as exc:
        print(f"usage: {exc}", file=sys.stderr)
        return 2

    by_no = {r["no"]: r for r in rows if r.get("no")}
    with open(args.fulltext, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    ad_lines = ad_line_numbers(lines)

    out_dir = args.out or L0_DEFAULT_OUT
    os.makedirs(out_dir, exist_ok=True)
    cand_path = os.path.join(out_dir, "candidates.jsonl")
    terms = [t for t in args.terms.split(",") if t]
    targets = parse_targets(args.chapters)
    t0 = time.time()

    stats = {"source": "l0", "fulltext": args.fulltext, "index": args.index,
             "l0_lines": len(lines), "index_rows": len(rows),
             "ad_marker_lines_in_l0": ad_lines, "ad_lines_excluded": 0,
             "chapters_requested": len(targets), "sliced": 0, "not_in_index": 0,
             "cjk_delta_total": 0, "hits_by_term": {t: 0 for t in terms}}
    readings = []
    with open(cand_path, "w", encoding="utf-8") as cand:
        for token in targets:
            label = str(token)
            if label.startswith("cid:"):
                stats["not_in_index"] += 1
                readings.append({"chapter": label, "verdict": "NOT_IN_INDEX",
                                 "note": "L0 模式无 cid 列：真章号用 no"})
                continue
            rec = by_no.get(label)
            if rec is None:
                stats["not_in_index"] += 1
                readings.append({"chapter": label, "verdict": "NOT_IN_INDEX"})
                continue
            text, excluded = slice_by_index(lines, rec["src_line_start"], rec["src_line_end"])
            stats["sliced"] += 1
            stats["ad_lines_excluded"] += excluded
            cjk = cjk_count(text)
            idx_style = index_cjk_len(text)
            idx_cjk = int(rec["txt_cjk_chars"]) if rec.get("txt_cjk_chars", "").isdigit() else 0
            official_words = int(rec["official_words"]) if rec.get("official_words", "").isdigit() else 0
            stats["cjk_delta_total"] += abs(idx_style - idx_cjk)
            readings.append({"chapter": label, "no": rec["no"], "labeled_no": rec.get("labeled_no"),
                             "src_line_start": rec["src_line_start"], "src_line_end": rec["src_line_end"],
                             "l0_slice_cjk": cjk, "l0_slice_index_style": idx_style,
                             "index_txt_cjk_chars": idx_cjk,
                             "cjk_delta": idx_style - idx_cjk, "official_words": official_words,
                             "index_deviation_pct": rec.get("deviation_pct"),
                             "ad_lines_excluded": excluded, "verdict": "SLICED_FROM_INDEX"})
            for term in terms:
                wins = []
                hits = 0
                for m in re.finditer(re.escape(term), text):
                    hits += 1
                    if len(wins) < args.max_windows:
                        w = make_window(text, m.start(), m.end(), cap=args.window)
                        if w and w not in wins:
                            wins.append(w)
                if hits:
                    stats["hits_by_term"][term] += hits
                    cand.write(json.dumps({"chapter": label, "term": term, "hits": hits,
                                           "windows": wins, "verdict": "SLICED_FROM_INDEX"},
                                          ensure_ascii=False) + "\n")

    with open(os.path.join(out_dir, "readings.json"), "w", encoding="utf-8") as fh:
        json.dump({"readings": readings, "stats": stats}, fh, ensure_ascii=False, indent=1)
    stats["elapsed_s"] = round(time.time() - t0, 1)
    stats["candidates_path"] = cand_path
    stats["readings_path"] = os.path.join(out_dir, "readings.json")
    stats["candidates_entries"] = sum(1 for _ in open(cand_path, encoding="utf-8"))
    print(json.dumps({"stats": stats}, ensure_ascii=False))
    print("per_chapter: " + " ".join(
        f"{r['chapter']}={r.get('l0_slice_index_style', '-')}/{r.get('index_txt_cjk_chars', '-')}/"
        f"{r.get('cjk_delta', '-')}/{r['verdict']}" for r in readings))
    return 0


# ---------------------------------------------------------------- 镜像模式（交叉校验用途）
def mirror_mode(args) -> int:
    if not args.catalog:
        print("usage: --source mirror requires --catalog <chapters.tsv>", file=sys.stderr)
        return 2
    out_dir = args.out or f"/tmp/m5-facts-{os.getpid()}"
    cache = os.path.join(out_dir, "cache")
    os.makedirs(cache, exist_ok=True)
    terms = [t for t in args.terms.split(",") if t]

    t0 = time.time()
    html, attempts, code, size, reason = fetch(args.dir_url, args.retries, args.timeout, args.sleep)
    if html is None:
        print(json.dumps({"error": "dir_fetch_failed", "reason": reason, "attempts": attempts}, ensure_ascii=False))
        return 3
    dir_path = os.path.join(cache, "dir.html")
    with open(dir_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    mapping = parse_dir_map(html)
    print(json.dumps({"dir_url": args.dir_url, "dir_bytes": size, "dir_attempts": attempts,
                      "mapped_chapters": len(mapping),
                      "max_mapped_no": max(mapping) if mapping else 0}, ensure_ascii=False))

    catalog = load_chapters(args.catalog)
    targets = parse_targets(args.chapters)
    readings = []
    cand_path = os.path.join(out_dir, "candidates.jsonl")
    stats = {"chapters_requested": len(targets), "mapped": 0, "no_mirror": 0, "fetch_fail": 0,
             "pass": 0, "tolerance_fail": 0, "retry_pages": 0, "attempts_total": 0,
             "hits_by_term": {t: 0 for t in terms}}

    with open(cand_path, "w", encoding="utf-8") as cand:
        for token in targets:
            if isinstance(token, str) and token.startswith("cid:"):
                rec = catalog.get(token[4:])
                label = token
            else:
                rec = catalog.get(str(token))
                label = str(token)
            if rec is None:
                readings.append({"chapter": label, "verdict": "NOT_IN_CATALOG"})
                continue
            official_words = int(rec["words"]) if rec["words"].isdigit() else 0
            mirror_no = title_chapter_no(rec["title"])
            url = mapping.get(mirror_no) if mirror_no else None
            if not url:
                stats["no_mirror"] += 1
                readings.append({"chapter": label, "cid": rec["cid"], "mirror_url": None,
                                 "official_words": official_words, "verdict": "UNVERIFIED_NO_MIRROR"})
                continue
            stats["mapped"] += 1
            cached = os.path.join(cache, f"{label.replace(':', '_')}.html")
            if os.path.exists(cached):
                page = open(cached, encoding="utf-8", errors="replace").read()
                page_attempts, page_code, page_bytes, page_reason = 1, "200", len(page.encode()), "cache"
            else:
                page, page_attempts, page_code, page_bytes, page_reason = fetch(url, args.retries, args.timeout, args.sleep)
                if page is not None:
                    with open(cached, "w", encoding="utf-8") as fh:
                        fh.write(page)
                time.sleep(args.sleep)
            stats["attempts_total"] += page_attempts
            if page_attempts > 1:
                stats["retry_pages"] += 1
            if page is None:
                stats["fetch_fail"] += 1
                readings.append({"chapter": label, "cid": rec["cid"], "mirror_url": url,
                                 "attempts": page_attempts, "official_words": official_words,
                                 "verdict": "UNVERIFIED_FETCH_FAIL", "reason": page_reason})
                continue
            text = content_div(page)
            cjk = cjk_count(text)
            dev = round((cjk - official_words) / official_words * 100, 1) if official_words else 0.0
            verdict = "PASS" if abs(dev) <= 12.0 else "UNVERIFIED_MIRROR_TOLERANCE"
            stats["pass" if verdict == "PASS" else "tolerance_fail"] += 1
            readings.append({"chapter": label, "cid": rec["cid"], "mirror_url": url,
                             "attempts": page_attempts, "http": page_code, "bytes": page_bytes,
                             "mirror_cjk": cjk, "official_words": official_words,
                             "deviation_pct": dev, "verdict": verdict})
            for term in terms:
                wins = []
                hits = 0
                for m in re.finditer(re.escape(term), text):
                    hits += 1
                    if len(wins) < args.max_windows:
                        w = make_window(text, m.start(), m.end(), cap=args.window)
                        if w and w not in wins:
                            wins.append(w)
                if hits:
                    stats["hits_by_term"][term] += hits
                    cand.write(json.dumps({"chapter": label, "term": term, "hits": hits,
                                           "windows": wins, "verdict": verdict}, ensure_ascii=False) + "\n")

    with open(os.path.join(out_dir, "readings.json"), "w", encoding="utf-8") as fh:
        json.dump({"readings": readings, "stats": stats}, fh, ensure_ascii=False, indent=1)

    stats["elapsed_s"] = round(time.time() - t0, 1)
    stats["candidates_path"] = cand_path
    stats["readings_path"] = os.path.join(out_dir, "readings.json")
    print(json.dumps({"stats": stats}, ensure_ascii=False))
    print("per_chapter: " + " ".join(
        f"{r['chapter']}={r.get('mirror_cjk','-')}/{r.get('official_words','-')}/{r.get('deviation_pct','-')}/{r['verdict']}"
        for r in readings))
    return 0


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="M5.1 事实抽取（候选窗口只落 /tmp）")
    ap.add_argument("--source", choices=("mirror", "l0"), default="mirror",
                    help="l0 = L0 全本（第一来源）；mirror = L2 镜像（交叉校验用途）")
    ap.add_argument("--fulltext", default=None, help="L0 全本路径（--source l0 必填）")
    ap.add_argument("--index", default=None, help="L1-fulltext-index.tsv（--source l0 必填）")
    ap.add_argument("--catalog", default=None, help="chapters.tsv（--source mirror 必填）")
    ap.add_argument("--chapters", required=True, help="目标真章号，如 1-107,109,180,240")
    ap.add_argument("--terms", default=",".join(DEFAULT_TERMS))
    ap.add_argument("--out", default=None,
                    help="候选输出目录（l0 默认 /tmp/m5-facts-r2-5；mirror 默认 /tmp/m5-facts-<pid>）")
    ap.add_argument("--dir-url", default=DEFAULT_DIR_URL)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--window", type=int, default=24, help="每个窗口的 CJK 上限")
    ap.add_argument("--max-windows", type=int, default=6, help="每章每词最多窗口数")
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args(argv)

    if args.source == "l0":
        return l0_mode(args)
    return mirror_mode(args)


if __name__ == "__main__":
    raise SystemExit(main())
