#!/usr/bin/env python3
"""从 PM 抓取的起点官方书籍页（含完整目录）抽取章节锚点表。

来源页: https://www.qidian.com/book/1025901449  （《我的治愈系游戏》 我会修空调）
抓取方式: Hermes web_extract（纯 HTTP，无登录）
产出: chapters.tsv —— 章号 / 标题 / 章节 URL / 首发时间 / 章节字数 / 是否免费卷
用途: M5 保真事实的来源锚点（每条事实 → 章号 + URL + 首发时间），不复制正文。
"""
import re
import sys
import hashlib
from pathlib import Path

RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/Users/wooyinq/.hermes/profiles/lanova/cache/web/www.qidian.com-39d8cd93ff.md")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).with_name("chapters.tsv")

text = RAW.read_text(encoding="utf-8", errors="replace")

# 目录条目形如:
# - [第46章 五楼](https://www.qidian.com/chapter/1025901449/636054298/ "我的治愈系游戏  第46章 五楼 首发时间：2021-02-16 23:20:34 章节字数：2057")
ENTRY = re.compile(
    r'-\s*\[(?P<label>[^\]]+)\]\((?P<url>https://www\.qidian\.com/chapter/1025901449/(?P<cid>\d+)/)\s*'
    r'"(?P<meta>[^"]*)"\)')

# 卷标记
VOL = re.compile(r'^###\s*(?P<name>.+?)\s*$', re.M)

rows = []
free_until = None
for m in ENTRY.finditer(text):
    label = m.group("label").strip()
    meta = m.group("meta")
    t = re.search(r'首发时间：([0-9\-: ]+)', meta)
    w = re.search(r'章节字数：(\d+)', meta)
    chap = re.match(r'^第(\d+)章', label)
    rows.append({
        "no": chap.group(1) if chap else "",
        "title": label,
        "cid": m.group("cid"),
        "url": m.group("url"),
        "first_pub": (t.group(1).strip() if t else ""),
        "words": (w.group(1) if w else ""),
    })

# 去重（同一 cid 可能被页面重复渲染），保留首次出现顺序
seen, uniq = set(), []
for r in rows:
    if r["cid"] in seen:
        continue
    seen.add(r["cid"])
    uniq.append(r)

# 免费卷边界：从原始文本里找「正文卷·共N章 免费」
free = re.search(r'正文卷·共(\d+)章\s*免费', text)
vip = re.search(r'正文卷·共(\d+)章\s*VIP', text)
free_n = int(free.group(1)) if free else 0

with OUT.open("w", encoding="utf-8") as f:
    f.write("no\ttitle\tcid\turl\tfirst_pub\twords\tvolume\n")
    numbered = [r for r in uniq if r["no"]]
    max_no = max(int(r["no"]) for r in numbered) if numbered else 0
    for r in uniq:
        n = int(r["no"]) if r["no"] else 0
        vol = "free" if (n and n <= free_n) else ("vip" if n else "ext")
        f.write(f'{r["no"]}\t{r["title"]}\t{r["cid"]}\t{r["url"]}\t{r["first_pub"]}\t{r["words"]}\t{vol}\n')

h = hashlib.sha256(RAW.read_bytes()).hexdigest()
print(f"raw_file            = {RAW}")
print(f"raw_sha256          = {h}")
print(f"raw_bytes           = {RAW.stat().st_size}")
print(f"entries_total       = {len(uniq)}")
print(f"entries_numbered    = {len(numbered)}  max_chapter_no = {max_no}")
print(f"free_volume_chapters= {free_n}   vip_volume_chapters = {vip.group(1) if vip else 'n/a'}")
print(f"out                 = {OUT}  lines={len(uniq) + 1}")
print("first3 =", [(r["no"], r["title"]) for r in uniq[:3]])
print("last3  =", [(r["no"], r["title"]) for r in uniq[-3:]])
