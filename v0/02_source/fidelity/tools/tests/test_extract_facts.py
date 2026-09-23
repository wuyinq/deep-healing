#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_facts 单测。

两组：
  * **L0 模式**（`--source l0`，M5.1 r2.5 / PM 裁决 m5-05 §2-A = 事实第一来源）：
    按索引 `src_line_start/src_line_end` 切片（不得自行推算行号）、广告行排除、交叉校验同口径、
    候选窗口 ≤24 CJK、stdout 只打统计量、候选只落 /tmp（不写正文进 workspace）。
  * **镜像模式**（`--source mirror`，降级为交叉校验用途）：P-1 目录页映射 / P-2 重试 / P-3 ±12% 容差 / P-4。

**不联网**：镜像取页由 monkeypatch 替换。**不写正文**：注入文本为运行时拼接的合成串。
"""
import json
import os
import sys

import pytest

from fidelity_testkit import CATALOG_HEADER, INDEX_HEADER, synth_text

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

import extract_facts as ef  # noqa: E402


class FakeProc:
    def __init__(self, stdout):
        self.stdout = stdout


# =============================================================== 纯函数
@pytest.mark.parametrize("title,expected", [
    ("第109章 徐琴身上的诅咒（第三更）", 109),
    ("第一百八十章 F级管理者任务——巡查教师", 180),
    ("第1章 玩游戏吗", 1),
    ("番外 预告", None),
])
def test_title_chapter_no(title, expected):
    assert ef.title_chapter_no(title) == expected


def test_parse_dir_map_absolutizes_relative_hrefs():
    html = ('<a href="/read/2/240.html">第109章 甲</a>'
            '<a href="https://snwxw.com/read/2/241.html">第110章 乙</a>'
            '<a href="/read/2/242.html">第一百八十章 丙</a>'
            '<a href="/read/2/132.html">开始阅读</a>')
    m = ef.parse_dir_map(html)
    assert m[109] == "https://snwxw.com/read/2/240.html"
    assert m[110] == "https://snwxw.com/read/2/241.html"
    assert m[180] == "https://snwxw.com/read/2/242.html"
    assert len(m) == 3


def test_content_div_extracts_text_without_tags():
    html = '<div class="content" id="content"><p>合成甲</p><p>合成乙</p></div><div>导航</div>'
    text = ef.content_div(html)
    assert "合成甲" in text and "合成乙" in text and "导航" not in text


def test_make_window_caps_cjk_at_24():
    text = "前缀" * 20 + "命中词" + "后缀" * 20
    i = text.index("命中词")
    win = ef.make_window(text, i, i + 3, cap=24)
    assert ef.cjk_count(win) <= 24
    assert "命中词" in win


def test_cjk_count_ignores_non_cjk():
    assert ef.cjk_count("ab12，。！ abc") == 0
    assert ef.cjk_count("合成文本") == 4


def test_index_cjk_len_matches_index_convention():
    """交叉校验必须与索引 `txt_cjk_chars` **同口径**（CJK 汉字 + 中文标点）。"""
    assert ef.index_cjk_len("合成，文本。") == 6
    assert ef.cjk_count("合成，文本。") == 4


# =============================================================== L0 模式：切片与广告行
def _index_file(tmp_path, rows):
    p = tmp_path / "L1-fulltext-index.tsv"
    p.write_text("\n".join([INDEX_HEADER] + rows) + "\n", encoding="utf-8")
    return str(p)


def _index_row(no, start, end, txt_cjk, words=100, labeled=None):
    return (f"{no}\t{labeled or no}\t合成标题{no}\t第{no}章 合成标题{no}\t"
            f"https://example.invalid/chapter/{no}/\t2021-01-0{no} 10:00:00\t"
            f"{words}\t{txt_cjk}\t0.0\t{start}\t{end}")


def test_slice_by_index_uses_index_line_range_only(tmp_path):
    """行区间**只许取自索引**：切片内容必须恰好是 [start, end] 这些行（1-indexed 闭区间）。"""
    lines = [f"L{i}" for i in range(1, 21)]           # L1..L20
    text, excluded = ef.slice_by_index(lines, 5, 8)
    assert text.splitlines() == ["L5", "L6", "L7", "L8"]
    assert excluded == 0
    # 退化 / 越界区间 ⇒ 空切片（不抛异常、不自行外推）
    assert ef.slice_by_index(lines, 0, 3) == ("", 0)
    assert ef.slice_by_index(lines, 8, 5) == ("", 0)


def test_slice_by_index_excludes_ad_lines(tmp_path):
    """第三方插入广告行（`yeguoyuedu.com`）必须在切片阶段被过滤并计数。"""
    lines = ["甲", "乙", "【推广 yeguoyuedu.com 合成】", "丙"]
    text, excluded = ef.slice_by_index(lines, 1, 4)
    assert excluded == 1
    assert "yeguoyuedu" not in text
    assert text.splitlines() == ["甲", "乙", "丙"]


def test_ad_line_numbers_detects_marker():
    lines = ["甲", "【推广 yeguoyuedu.com】", "乙"]
    assert ef.ad_line_numbers(lines) == [2]
    assert ef.ad_line_numbers(["甲", "乙"]) == []


def test_l0_mode_slices_by_index_and_excludes_ads(tmp_path, capsys):
    """端到端（合成 L0 + 合成索引）：命中只来自**索引声明的行**，广告行 0 命中。"""
    rows = [_index_row(1, 2, 5, txt_cjk=0, words=0)]
    index = _index_file(tmp_path, rows)
    fulltext = tmp_path / "l0.txt"
    fulltext.write_text("表头\n合成甲词\n合成乙词\n【推广 yeguoyuedu.com 合成丙词】\n合成丁词\n范围外词\n",
                        encoding="utf-8")
    out = tmp_path / "out"
    rc = ef.main(["--source", "l0", "--fulltext", str(fulltext), "--index", index,
                  "--chapters", "1", "--terms", "合成甲词,合成乙词,合成丙词,合成丁词,范围外词",
                  "--out", str(out)])
    assert rc == 0
    readings = json.loads((out / "readings.json").read_text(encoding="utf-8"))
    stats = readings["stats"]
    assert stats["ad_lines_excluded"] == 1
    assert stats["sliced"] == 1
    hits = {r["term"]: r["hits"] for r in
            [json.loads(l) for l in (out / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]}
    assert set(hits) == {"合成甲词", "合成乙词", "合成丁词"}          # 广告行与范围外行都不得命中
    assert "合成丙词" not in hits and "范围外词" not in hits
    r0 = readings["readings"][0]
    assert (r0["src_line_start"], r0["src_line_end"]) == ("2", "5")
    assert r0["verdict"] == "SLICED_FROM_INDEX"


def test_l0_mode_stdout_carries_stats_only(tmp_path, capsys):
    secret = synth_text(90)
    rows = [_index_row(1, 2, 2, txt_cjk=0, words=0)]
    index = _index_file(tmp_path, rows)
    fulltext = tmp_path / "l0.txt"
    fulltext.write_text("表头\n" + secret + "\n", encoding="utf-8")
    ef.main(["--source", "l0", "--fulltext", str(fulltext), "--index", index,
             "--chapters", "1", "--terms", "合成", "--out", str(tmp_path / "o")])
    out = capsys.readouterr().out
    assert secret not in out
    assert "candidates_path" in out


def test_l0_mode_usage_errors(tmp_path):
    assert ef.main(["--source", "l0", "--chapters", "1"]) == 2                       # 缺 --fulltext
    assert ef.main(["--source", "l0", "--fulltext", str(tmp_path / "x.txt"),
                    "--chapters", "1"]) == 2                                        # 缺 --index
    index = _index_file(tmp_path, [_index_row(1, 2, 2, 0)])
    assert ef.main(["--source", "l0", "--fulltext", str(tmp_path / "missing.txt"),
                    "--index", index, "--chapters", "1"]) == 2
    bad = tmp_path / "bad.tsv"
    bad.write_text("no\ttitle\n1\t甲\n", encoding="utf-8")
    assert ef.main(["--source", "l0", "--fulltext", str(tmp_path / "missing.txt"),
                    "--index", str(bad), "--chapters", "1"]) == 2


def test_l0_mode_cid_token_is_not_an_index_key(tmp_path):
    rows = [_index_row(1, 2, 2, 0)]
    index = _index_file(tmp_path, rows)
    fulltext = tmp_path / "l0.txt"
    fulltext.write_text("表头\n合成词\n", encoding="utf-8")
    out = tmp_path / "o"
    assert ef.main(["--source", "l0", "--fulltext", str(fulltext), "--index", index,
                    "--chapters", "cid:123", "--terms", "合成", "--out", str(out)]) == 0
    readings = json.loads((out / "readings.json").read_text(encoding="utf-8"))
    assert readings["readings"][0]["verdict"] == "NOT_IN_INDEX"
    assert readings["stats"]["not_in_index"] == 1


# =============================================================== L0 模式：真实索引/全本
def test_real_index_and_l0_agree_on_line_range_and_char_count(tmp_path, index_path, l0_path):
    """真实数据交叉校验：切片行区间 == 索引值；同口径字数差 == 0（不自行数行）。"""
    out = tmp_path / "real"
    rc = ef.main(["--source", "l0", "--fulltext", l0_path, "--index", index_path,
                  "--chapters", "180,332", "--terms", "管理者", "--out", str(out)])
    assert rc == 0
    readings = json.loads((out / "readings.json").read_text(encoding="utf-8"))
    by_no = {r["no"]: r for r in readings["readings"]}
    assert (by_no["180"]["src_line_start"], by_no["180"]["src_line_end"]) == ("10395", "10451")
    assert (by_no["332"]["src_line_start"], by_no["332"]["src_line_end"]) == ("19937", "19987")
    assert by_no["332"]["labeled_no"] == "322"          # 错位行：真章号 332 / 标号 322
    for rec in readings["readings"]:
        assert rec["cjk_delta"] == 0, rec
    assert readings["stats"]["cjk_delta_total"] == 0
    for line in (out / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        for win in rec["windows"]:
            assert ef.cjk_count(win) <= 24


def test_real_l0_has_exactly_one_ad_line(tmp_path, index_path, l0_path):
    """真实 L0 的广告行读数：**恰好 1 条**（抽事实时必须排除的那条）。"""
    with open(l0_path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    ad = ef.ad_line_numbers(lines)
    assert len(ad) == 1, ad


# =============================================================== 镜像模式（交叉校验用途）
def test_fetch_retries_transient_empty_response(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, capture_output=True, text=True):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeProc("\n200 16")
        return FakeProc("<html>合成正文</html>\n200 20000")

    monkeypatch.setattr(ef.subprocess, "run", fake_run)
    body, attempts, code, size, reason = ef.fetch("https://x.invalid/a", retries=3, timeout=5, sleep=0)
    assert body is not None
    assert attempts == 2
    assert size == 20000


def test_fetch_gives_up_after_retries(monkeypatch):
    def fake_run(cmd, capture_output=True, text=True):
        return FakeProc("\n200 16")

    monkeypatch.setattr(ef.subprocess, "run", fake_run)
    body, attempts, code, size, reason = ef.fetch("https://x.invalid/a", retries=3, timeout=5, sleep=0)
    assert body is None
    assert attempts == 3
    assert "http=200" in reason


def _write_catalog(tmp_path):
    p = tmp_path / "chapters.tsv"
    rows = [
        "1\t第1章 测试\t632217048\thttps://example.invalid/chapter/632217048/\t2021-01-25 11:03:07\t100\tfree",
        "\t第一百八十章 测试\t648165987\thttps://example.invalid/chapter/648165987/\t2021-04-19 18:49:14\t2208\text",
    ]
    p.write_text("\n".join([CATALOG_HEADER] + rows) + "\n", encoding="utf-8")
    return str(p)


def _dir_html():
    return ('<a href="/read/2/900.html">第1章 测试</a>'
            '<a href="/read/2/901.html">第一百八十章 测试</a>')


def test_mirror_mode_end_to_end_writes_candidates_and_readings(tmp_path, monkeypatch):
    catalog = _write_catalog(tmp_path)
    out = tmp_path / "out"
    pass_text = synth_text(95)
    fail_text = synth_text(40)
    pages = {
        "https://snwxw.com/read/2/900.html": f'<div id="content"><p>{pass_text}</p></div>',
        "https://snwxw.com/read/2/901.html": f'<div id="content"><p>{fail_text}</p></div>',
    }

    def fake_fetch(url, retries, timeout, sleep):
        if url.endswith("/books/2/"):
            return _dir_html(), 1, "200", len(_dir_html()), ""
        html = pages[url]
        return html, 1, "200", len(html), ""

    monkeypatch.setattr(ef, "fetch", fake_fetch)
    rc = ef.main(["--catalog", catalog, "--chapters", "1,cid:648165987",
                  "--terms", "合成", "--out", str(out)])
    assert rc == 0
    readings = json.loads((out / "readings.json").read_text(encoding="utf-8"))
    verdicts = {r["chapter"]: r["verdict"] for r in readings["readings"]}
    assert verdicts["1"] == "PASS"
    assert verdicts["cid:648165987"] == "UNVERIFIED_MIRROR_TOLERANCE"
    assert readings["stats"]["mapped"] == 2
    assert readings["stats"]["pass"] == 1
    lines = [json.loads(l) for l in (out / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines
    for rec in lines:
        assert rec["term"] == "合成"
        for win in rec["windows"]:
            assert ef.cjk_count(win) <= 24


def test_mirror_mode_reports_missing_mirror(tmp_path, monkeypatch):
    catalog = _write_catalog(tmp_path)
    out = tmp_path / "out3"

    def fake_fetch(url, retries, timeout, sleep):
        return '<a href="/read/2/900.html">第1章 测试</a>', 1, "200", 10, ""

    monkeypatch.setattr(ef, "fetch", fake_fetch)
    rc = ef.main(["--catalog", catalog, "--chapters", "cid:648165987", "--terms", "合成", "--out", str(out)])
    assert rc == 0
    readings = json.loads((out / "readings.json").read_text(encoding="utf-8"))
    assert readings["readings"][0]["verdict"] == "UNVERIFIED_NO_MIRROR"
    assert readings["stats"]["no_mirror"] == 1


def test_mirror_mode_dir_fetch_failure_returns_3(tmp_path, monkeypatch):
    catalog = _write_catalog(tmp_path)

    def fake_fetch(url, retries, timeout, sleep):
        return None, 3, "200", 16, "http=200 bytes=16"

    monkeypatch.setattr(ef, "fetch", fake_fetch)
    rc = ef.main(["--catalog", catalog, "--chapters", "1", "--terms", "合成", "--out", str(tmp_path / "o4")])
    assert rc == 3


def test_mirror_mode_requires_catalog(tmp_path):
    assert ef.main(["--chapters", "1"]) == 2
