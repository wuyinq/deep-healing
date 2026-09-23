#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L1 权威正文校验器（PM 侧工具，可复跑）

用途：把船长提供的《我的治愈系游戏》（校对版全本+番外）.txt 与官方目录
（`chapters.tsv`，起点 1030 章元数据）做**逐章对齐与完整性校验**，产出：

  1. `L1-fulltext-index.tsv` —— 章号 → 标题 → 官方 URL → 首发时间 → 官方字数
     → 正文字数 → 偏差 → 正文在源文件中的行区间（**只有锚点与读数，无正文**）。
  2. 控制台读数 + `L1-fulltext-verification.json`。

红线：本脚本**不输出任何小说正文**，只输出标题、数字与行偏移。
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHAPTERS_TSV = HERE / "chapters.tsv"
SOURCE_TXT = Path(
    "/Users/wooyinq/.hermes/profiles/lanova/sources/deephealing/"
    "《我的治愈系游戏》（校对版全本+番外）.txt"
)
INDEX_OUT = HERE / "L1-fulltext-index.tsv"
READINGS_OUT = HERE / "L1-fulltext-verification.json"

HEADING = re.compile(r"^第(\d+)章\s*(.*)$")
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def cjk_len(text: str) -> int:
    """中文字数口径：CJK 汉字 + 中文标点（与官方「章节字数」同量级）。"""
    return sum(
        1
        for ch in text
        if "\u4e00" <= ch <= "\u9fff"
        or "\u3000" <= ch <= "\u303f"
        or ch in "，。！？：；、“”‘’（）《》…—·【】"
    )


def official_chapters() -> dict[int, dict[str, str]]:
    rows = list(csv.DictReader(CHAPTERS_TSV.open(encoding="utf-8"), delimiter="\t"))
    out: dict[int, dict[str, str]] = {}
    for row in rows:
        m = re.match(r"^第(\d+)章", row["title"].strip())
        if m:
            out[int(m.group(1))] = row
        elif row["title"].startswith("第一百八十章"):
            # 官方目录里第 180 章用中文数字排版，被抽取器归到 ext 卷
            out[180] = row
    return out


def load_source() -> tuple[str, str, list[str]]:
    raw = SOURCE_TXT.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    return sha, text, text.split("\n")


def main() -> int:
    if not SOURCE_TXT.exists():
        print(f"FATAL: 源文件不存在: {SOURCE_TXT}", file=sys.stderr)
        return 2
    sha, text, lines = load_source()
    official = official_chapters()

    headings: list[dict] = []
    for i, line in enumerate(lines):
        s = line.strip().strip("\u3000")
        m = HEADING.match(s)
        if m:
            headings.append({"line": i, "labeled": int(m.group(1)), "title": m.group(2).strip()})

    # 校对版存在 3 处章号排版错位（真序号 = 出现次序），以出现次序为「真章号」
    for j, h in enumerate(headings):
        h["no"] = j + 1

    typos = [(h["no"], h["labeled"], h["title"]) for h in headings if h["no"] != h["labeled"]]

    index_rows: list[dict] = []
    deviations: list[float] = []
    exact = suffix = other = 0
    others: list[tuple] = []

    for j, h in enumerate(headings):
        start = h["line"] + 1
        end = headings[j + 1]["line"] if j + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start:end])
        # 源文件里被插入过 1 条第三方推广行，不计入字数
        body = re.sub(r"^【[^\n]*yeguoyuedu\.com[^\n]*】$", "", body, flags=re.M)
        n_chars = cjk_len(body)
        o = official.get(h["no"], {})
        words = int(o["words"]) if o.get("words", "").isdigit() else 0
        dev = round((n_chars - words) / words * 100, 1) if words >= 500 else None
        if dev is not None:
            deviations.append(dev)
        o_title = re.sub(r"^第\d+章\s*", "", o.get("title", "")).strip()
        if o_title and o_title == h["title"]:
            exact += 1
        elif o_title and o_title.startswith(h["title"]):
            suffix += 1
        elif o_title:
            other += 1
            others.append((h["no"], h["title"], o_title))
        index_rows.append(
            {
                "no": h["no"],
                "labeled_no": h["labeled"],
                "title": h["title"],
                "official_title": o.get("title", ""),
                "official_url": o.get("url", ""),
                "first_pub": o.get("first_pub", ""),
                "official_words": words,
                "txt_cjk_chars": n_chars,
                "deviation_pct": "" if dev is None else dev,
                "src_line_start": start + 1,
                "src_line_end": end,
            }
        )

    with INDEX_OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(index_rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(index_rows)

    out_of_band = [r for r in index_rows if r["deviation_pct"] != "" and abs(r["deviation_pct"]) > 12]
    readings = {
        "source_path": str(SOURCE_TXT),
        "source_sha256": sha,
        "source_bytes": SOURCE_TXT.stat().st_size,
        "source_chars": len(text),
        "official_chapters_numbered": len(official),
        "txt_chapter_headings": len(headings),
        "txt_chapter_range": [headings[0]["no"], headings[-1]["no"]],
        "coverage_vs_official": f"{len(headings)}/{len(official)}",
        "numbering_typos": len(typos),
        "numbering_typo_rows": typos,
        "title_alignment": {"exact": exact, "suffix_only": suffix, "other": other},
        "title_other_rows": others,
        "fidelity_compared_chapters": len(deviations),
        "fidelity_median_pct": round(statistics.median(deviations), 1),
        "fidelity_min_pct": min(deviations),
        "fidelity_max_pct": max(deviations),
        "fidelity_out_of_band_12pct": len(out_of_band),
        "fidelity_out_of_band_rows": [(r["no"], r["official_words"], r["txt_cjk_chars"], r["deviation_pct"]) for r in out_of_band],
        "has_extra_chapter_beyond_1000": "番外" in text.split("（全书完）")[-1],
    }
    READINGS_OUT.write_text(json.dumps(readings, ensure_ascii=False, indent=1), encoding="utf-8")

    print("=== L1 权威正文校验 ===")
    print(f"源文件 sha256 : {sha}")
    print(f"字节 / 字符   : {readings['source_bytes']} / {readings['source_chars']}")
    print(f"覆盖          : {readings['coverage_vs_official']}（章号 {readings['txt_chapter_range'][0]}~{readings['txt_chapter_range'][1]}）")
    print(f"章号排版错位  : {len(typos)} 处")
    print(f"标题对齐      : exact={exact} suffix-only={suffix} other={other}")
    print(f"完整性偏差    : 中位 {readings['fidelity_median_pct']}% 区间 [{readings['fidelity_min_pct']}%, {readings['fidelity_max_pct']}%]，超 ±12% 的章 {len(out_of_band)} 条")
    print(f"索引          : {INDEX_OUT.name}（{len(index_rows)} 行，只含锚点与读数，无正文）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
