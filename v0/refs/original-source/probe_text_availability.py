#!/usr/bin/env python3
"""M5 来源可用性 + 完整性校验探针（PM 侧，只读）。

结论级输出三行：
  [A] 官方目录锚点：起点官方书籍页 -> 章号 / 标题 / URL / 首发时间 / 字数（已由 extract_catalog.py 落盘）
  [B] 正文读取路径：公开镜像 少年文学网，正文在 div.content；章号->URL 映射从镜像自身目录页解析（**不做算术外推**，
      实测镜像存在跳页：ch46->177 / ch148->279 偏移 131，而 331 页是第199章，偏移 132）
  [C] 完整性校验：镜像正文 CJK 字数 vs 官方「章节字数」元数据，容差内 ⇒ 可作内部事实抽取的二级来源；
      超容差 ⇒ 该章标 UNVERIFIED。

不把正文写进任何产物（只写统计量），符合 CHG-20260923-004 §4 可翻项 2。
"""
import re
import subprocess
import sys
from pathlib import Path

TSV = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/"
           "REQ-20260923-001-deephealing-m5-original-fidelity/refs/original-source/chapters.tsv")
CATALOG = "https://snwxw.com/books/2/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TOL = 0.12
SAMPLE = (1, 46, 148, 199, 46 + 0)

official = {}
for line in TSV.read_text(encoding="utf-8").splitlines()[1:]:
    f = line.split("\t")
    if f[0].isdigit():
        official[int(f[0])] = {"title": f[1], "words": int(f[5]) if f[5] else 0}


def curl(url: str) -> str:
    return subprocess.run(["curl", "-sS", "-m", "30", "-A", UA, url],
                          capture_output=True, text=True).stdout


def mirror_map() -> dict:
    """从镜像目录页解析 章号 -> 章节页 URL。"""
    html = curl(CATALOG)
    out = {}
    for href, label in re.findall(r'href="(/read/2/\d+\.html)"[^>]*>([^<]+)<', html):
        m = re.match(r"第\s*(\d+)\s*章", label)
        if m:
            out.setdefault(int(m.group(1)), "https://snwxw.com" + href)
    return out


def content_text(html: str) -> str:
    m = re.search(r'(?is)<div[^>]*class="content"[^>]*>(.*?)</div>', html)
    if not m:
        return ""
    body = m.group(1)
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", body)
    body = re.sub(r"(?is)<br\s*/?>|</p>", "\n", body)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    return re.sub(r"[ \t\r\f\v]+", " ", body)


print(f"[A] 官方目录锚点：{len(official)} 章（章号/标题/URL/首发时间/字数），来源 {TSV.name}")
mm = mirror_map()
print(f"[B] 镜像目录解析：{len(mm)} 章 -> URL（样本 ch46={mm.get(46)}，ch199={mm.get(199)}）")
if not mm:
    print("    目录页解析为空 —— 取正文路径不可用，标 GAP")
    sys.exit(2)

print("[C] 完整性校验（镜像正文 CJK 字数 vs 官方章节字数，容差 ±12%）")
ok = 0
for n in sorted(set(SAMPLE)):
    url = mm.get(n)
    if not url:
        print(f"    ch{n}: 镜像目录无此章 -> GAP")
        continue
    txt = content_text(curl(url))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", txt))
    exp = official.get(n, {}).get("words", 0)
    dev = (cjk - exp) / exp if exp else None
    good = bool(exp) and dev is not None and abs(dev) <= TOL
    ok += good
    print(f"    ch{n:>4} {official.get(n,{}).get('title','')[:22]:<24} "
          f"官方{exp:>5} 镜像{cjk:>5} 偏差{(dev or 0):+.1%} -> {'PASS' if good else 'FAIL'}")
print(f"\n通过 {ok}/{len(set(SAMPLE))}")
sys.exit(0 if ok == len(set(SAMPLE)) else 1)
