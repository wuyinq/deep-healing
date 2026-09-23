#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""redline_scan 单测：`l0_verbatim`（主判据）+ 次要规则 + 扫描面/后缀 + `--probe` + 退出码。

证明红线判据**有牙**（RK-1 / G7 / PM 裁决 m5-07 §一），且**不打命中文本**（读数只有 `文件:行:长度`）。

红线纪律：正对照的文本**运行时**从 L0 全本取（只落 pytest 临时目录 `/tmp`，**不落交付面**）；
其余注入一律为运行时拼接的合成串。
"""
import json
import os
import subprocess
import sys

import pytest

from fidelity_testkit import synth_text

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN = os.path.join(TOOLS, "redline_scan.py")
sys.path.insert(0, TOOLS)

import redline_scan as rs  # noqa: E402


def _run_cli(targets, extra=()):
    cmd = [sys.executable, SCAN, *targets, *extra]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _summary(out):
    return json.loads(out.strip().splitlines()[-1])


def _hits(files, l0_norm, ngram=16, title_norms=()):
    return rs.l0_verbatim_hits(files, l0_norm, ngram, set(title_norms))[0]


# --------------------------------------------------------------- 归一化 / D-4
def test_normalize_strips_punctuation_quotes_whitespace():
    assert rs.normalize_cjk("甲，乙。 “丙”\t丁 123ABC") == "甲乙丙丁"


def test_d4_rule_unchanged():
    assert rs.d4_hit(synth_text(60)) is True
    assert rs.d4_hit(synth_text(24) + "。又一句。") is True
    assert rs.d4_hit(synth_text(24)) is False


# --------------------------------------------------------------- l0_verbatim（主判据）
def test_l0_verbatim_fires_on_runtime_l0_excerpt(tmp_path, l0_path):
    """正对照：**运行时**从 L0 取 60 CJK（去标点）注入 ⇒ 必须命中（形态无关）。"""
    l0 = rs.load_l0_norm(l0_path)
    excerpt = l0[len(l0) // 3:len(l0) // 3 + 60]
    punctuated = "，".join(excerpt[i:i + 10] for i in range(0, 60, 10))
    f = tmp_path / "probe.md"
    f.write_text("探针：去标点注入 " + punctuated + "\n", encoding="utf-8")
    hits = _hits([str(f)], l0)
    assert [h[2] for h in hits] == ["l0_verbatim"]
    assert hits[0][3] >= 60          # 最长逐字连续片段（标点已归一化丢弃）


@pytest.mark.parametrize("wrap", [
    lambda t: t,                                  # ① 去引号
    lambda t: "“" + t + "”",                       # ② 登记引号
    lambda t: "『" + t + "』",                      # ③ 未登记引号（旧判据的逃逸面）
    lambda t: "「" + t + "』",                      # ④ 引号配对错位
    lambda t: "，".join(t[i:i + 6] for i in range(0, len(t), 6)),   # ⑤ 按标点切句
])
def test_l0_verbatim_is_form_independent(tmp_path, l0_path, wrap):
    """Raven R-1 的四条绕过路径（+去引号）在内容比对下**一律失效**。"""
    l0 = rs.load_l0_norm(l0_path)
    excerpt = l0[len(l0) // 2:len(l0) // 2 + 40]
    f = tmp_path / "probe.md"
    f.write_text("探针：" + wrap(excerpt) + "\n", encoding="utf-8")
    hits = _hits([str(f)], l0)
    assert hits and hits[0][2] == "l0_verbatim"


def test_l0_verbatim_catches_fragment_embedded_in_longer_line(tmp_path, l0_path):
    """片段嵌在更长的中文行里（前后有本仓自有中文）⇒ 仍必须命中（逐窗口比对）。"""
    l0 = rs.load_l0_norm(l0_path)
    excerpt = l0[len(l0) // 4:len(l0) // 4 + 30]
    f = tmp_path / "probe.md"
    f.write_text("本仓自有的技术性中文说明" + excerpt + "本仓自有的技术性中文说明\n", encoding="utf-8")
    hits = _hits([str(f)], l0)
    assert hits and hits[0][3] >= 30


def test_l0_verbatim_does_not_fire_on_synthetic_text(tmp_path, l0_path):
    """负对照：运行时拼接的合成中文串（≥60 CJK）⇒ 不得命中。"""
    f = tmp_path / "synth.md"
    f.write_text("说明：" + synth_text(80) + "\n", encoding="utf-8")
    assert _hits([str(f)], rs.load_l0_norm(l0_path)) == []


def test_l0_verbatim_ignores_short_runs(tmp_path, l0_path):
    """短于下界的片段（15 CJK）⇒ 不命中（下界 = `--ngram`）。"""
    l0 = rs.load_l0_norm(l0_path)
    f = tmp_path / "short.md"
    f.write_text("说明：" + l0[len(l0) // 3:len(l0) // 3 + 15] + "\n", encoding="utf-8")
    assert _hits([str(f)], l0) == []


def test_l0_verbatim_reports_one_hit_per_run(tmp_path, l0_path):
    """同一段命中聚成一个 run ⇒ 只报一次（读数是 `文件:行:长度`；长度 = run 长度）。"""
    l0 = rs.load_l0_norm(l0_path)
    excerpt = l0[len(l0) // 3:len(l0) // 3 + 80]
    f = tmp_path / "multi.md"
    f.write_text("说明：" + excerpt + "\n", encoding="utf-8")
    hits = _hits([str(f)], l0)
    assert len(hits) == 1 and hits[0][1] == 1 and hits[0][3] >= 80


def test_readings_declare_file_level_normalization(tmp_path, l0_path):
    """读数必须**显式声明比对单元 = 文件级**（PM m5-07 §1.1；按行口径已废）。"""
    l0 = rs.load_l0_norm(l0_path)
    f = tmp_path / "plain.md"
    f.write_text("说明：普通技术性中文说明文字，不含任何原著片段。\n", encoding="utf-8")
    _h, readings = rs.l0_verbatim_hits([str(f)], l0, rs.DEFAULT_NGRAM, set())
    assert readings["normalization"] == "file_level"
    assert readings["candidate_files"] == 1
    assert readings["candidate_cjk_chars"] == len(rs.normalize_cjk(f.read_text(encoding="utf-8")))
    assert "candidate_lines" not in readings


# --------------------------------------------------- ①~⑥ 对照（M5.1 r2.7 核心：按行切段必须红）
def test_min_split_two_short_lines_still_fires(tmp_path, l0_path):
    """①（最小形态）**16 CJK 拆成两行 ×8**（每行都 < 下界）⇒ 必须命中 —— 文件级归一化跨行拼接。

    旧（按行）实现此处 `primary 0`：这正是 Raven R-8 的逃逸面。
    """
    l0 = rs.load_l0_norm(l0_path)
    excerpt = l0[len(l0) // 3:len(l0) // 3 + 16]
    assert len(excerpt) == 16
    f = tmp_path / "split_two.md"
    f.write_text(excerpt[:8] + "\n" + excerpt[8:] + "\n", encoding="utf-8")
    hits = _hits([str(f)], l0)
    assert hits and hits[0][2] == "l0_verbatim"
    assert hits[0][3] == 16


def test_split_into_14_lines_of_15_still_fires(tmp_path, l0_path):
    """①（R-8 实证形态）**210 CJK 拆成 14 行 ×15 CJK** ⇒ 必须命中，run = 210。

    实证读数（Raven 门禁第二遍 R-8）：旧实现下 210 拆 14×15 ⇒ `redline_scan` primary 0、
    `fidelity_lint` 0 违规、`scan_ip_boundary` 0；两行 ×105 ⇒ 命中 105/105。
    """
    l0 = rs.load_l0_norm(l0_path)
    block = l0[len(l0) // 3:len(l0) // 3 + 210]
    assert len(block) == 210
    f = tmp_path / "split_14.md"
    f.write_text("\n".join(block[i:i + 15] for i in range(0, 210, 15)) + "\n", encoding="utf-8")
    hits = _hits([str(f)], l0)
    assert hits and hits[0][2] == "l0_verbatim"
    assert hits[0][3] == 210
    assert hits[0][1] == 1          # run 起点在第 1 行


def test_two_lines_of_105_still_fires(tmp_path, l0_path):
    """② 同内容**两行 ×105**（R-8 的对照臂）⇒ 必须命中，run = 210。"""
    l0 = rs.load_l0_norm(l0_path)
    block = l0[len(l0) // 3:len(l0) // 3 + 210]
    f = tmp_path / "two_lines.md"
    f.write_text(block[:105] + "\n" + block[105:] + "\n", encoding="utf-8")
    hits = _hits([str(f)], l0)
    assert hits and hits[0][3] == 210
    assert hits[0][1] == 1


def test_run_start_line_is_reverse_mapped_from_normalized_stream(tmp_path, l0_path):
    """①的行号口径：归一化流里的命中起点 ⇒ **原始行号**（前面 3 行技术性中文 ⇒ run 起点在第 4 行）。"""
    l0 = rs.load_l0_norm(l0_path)
    excerpt = l0[len(l0) // 2:len(l0) // 2 + 40]
    f = tmp_path / "lines.md"
    f.write_text("第一行技术性说明\n第二行技术性说明\n第三行技术性说明\n" + excerpt + "\n", encoding="utf-8")
    hits = _hits([str(f)], l0)
    assert hits and hits[0][1] == 4


def test_repo_style_chinese_line_does_not_fire(tmp_path, l0_path):
    """④ 本仓自有中文行（≥16 CJK、非原著）⇒ **不得命中**（文件级归一化不得引入误报）。"""
    line = "本仓自有的技术性中文说明用于负对照且不取自任何原著正文"
    assert len(rs.normalize_cjk(line)) >= rs.DEFAULT_NGRAM
    f = tmp_path / "own.md"
    f.write_text(line + "\n", encoding="utf-8")
    assert _hits([str(f)], rs.load_l0_norm(l0_path)) == []


def test_removal_restores_baseline(tmp_path, l0_path):
    """⑥ 移除注入 ⇒ 回基线（同一路径：无文件 0 → 注入 ≥1 → 移除后 0）。"""
    l0 = rs.load_l0_norm(l0_path)
    f = tmp_path / "probe.md"
    assert _hits([str(f)], l0) == []
    f.write_text(l0[len(l0) // 3:len(l0) // 3 + 60] + "\n", encoding="utf-8")
    assert len(_hits([str(f)], l0)) == 1
    f.unlink()
    assert _hits([str(f)], l0) == []


def test_official_title_is_mechanically_exempt(tmp_path, index_path, l0_path):
    """机械白名单：命中串落在 `official_title` 内 ⇒ 自动豁免并计数（PM m5-07 §一.3）。"""
    titles = rs.load_title_norms(index_path)
    assert titles, "索引里必须有 official_title"
    l0 = rs.load_l0_norm(l0_path)
    # 取一个**同时**满足「长度 ≥ 下界」且「确实出现在 L0 里」的官方标题（否则豁免无从触发）
    candidates = sorted((t for t in titles if len(t) >= rs.DEFAULT_NGRAM), key=len, reverse=True)
    assert candidates, "官方标题中应存在 ≥ 下界的条目，否则本用例不成立"
    title = next((t for t in candidates if t in l0), None)
    assert title is not None, "应存在既够长又出现在 L0 里的官方标题"
    f = tmp_path / "title.md"
    f.write_text("说明：引用官方标题 " + title + "\n", encoding="utf-8")
    hits, readings = rs.l0_verbatim_hits([str(f)], l0, rs.DEFAULT_NGRAM, titles)
    assert hits == []
    assert readings["exempt_title_spans"] >= 1
    # 非标题的正文片段**不得**被豁免（豁免不能吞掉正文命中）
    excerpt = l0[len(l0) // 3:len(l0) // 3 + 40]
    assert rs.title_exempt(excerpt, titles) is False


def test_title_substring_is_mechanically_exempt(tmp_path, index_path, l0_path):
    """⑤ 命中跨度是已登记 `official_title` 的**子串**（不是整标题）⇒ 同样机械豁免（m5-07 §一.3）。"""
    titles = rs.load_title_norms(index_path)
    l0 = rs.load_l0_norm(l0_path)
    title = next((t for t in sorted(titles, key=len, reverse=True)
                  if len(t) >= rs.DEFAULT_NGRAM + 4 and t in l0), None)
    assert title is not None, "应存在既够长又出现在 L0 里的官方标题"
    span = title[2:2 + rs.DEFAULT_NGRAM + 2]        # 归一化子串，长度 ≥ 下界（否则无从触发）
    assert rs.title_exempt(span, titles) is True
    f = tmp_path / "title_sub.md"
    f.write_text("说明：引用官方标题的片段 " + span + "\n", encoding="utf-8")
    hits, readings = rs.l0_verbatim_hits([str(f)], l0, rs.DEFAULT_NGRAM, titles)
    assert hits == []
    assert readings["exempt_title_spans"] >= 1


def test_default_ngram_is_16():
    assert rs.DEFAULT_NGRAM == 16


# --------------------------------------------------------------- 扫描面 / 后缀（R-2）
def test_binary_blacklist_skips_assets(tmp_path):
    (tmp_path / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n" + "合成".encode() * 40)
    (tmp_path / "b.pyc").write_bytes(b"\x00\x01\x02")
    files, unknown = rs.iter_files(str(tmp_path), [])
    assert files == [] and unknown == []


def test_unknown_suffix_is_scanned_and_reported(tmp_path):
    """R-2：未知后缀**照样扫**（不再白名单化），并进 `unknown_suffix_files[]`。"""
    (tmp_path / "notes.bak").write_text(f"说明：“{synth_text(60)}”\n", encoding="utf-8")
    files, unknown = rs.iter_files(str(tmp_path), [])
    assert [os.path.basename(f) for f in files] == ["notes.bak"]
    assert [os.path.basename(u) for u in unknown] == ["notes.bak"]


def test_jsonl_gap_suffix_is_now_scanned(tmp_path, l0_path):
    """Raven R-2 的具体空窗：`.jsonl`（抽取器自己的中间产物后缀）过去对目录递归完全隐形 —— 现在必扫。"""
    l0 = rs.load_l0_norm(l0_path)
    (tmp_path / "notes.jsonl").write_text("说明：" + l0[len(l0) // 3:len(l0) // 3 + 40] + "\n",
                                          encoding="utf-8")
    files, _unknown = rs.iter_files(str(tmp_path), [])
    assert [os.path.basename(f) for f in files] == ["notes.jsonl"]
    assert _hits(files, l0), "`.jsonl` 里的逐字片段必须被扫到"


def test_named_excludes_are_declared_in_scope(workspace_root):
    """按名排除（refs / spikes / 转录）必须在 `scope` 里**显式声明**，不得静默（m5-07 §一.6）。"""
    rc, out, err = _run_cli(["--root", workspace_root, "--json-only"])
    scope = _summary(out)["scope"]
    assert scope["profile"] == "delivery"
    named = [os.path.basename(p) for p in scope["named_excludes"]]
    for want in ("refs", "spikes", ".squad_result.txt", ".task-*.out"):
        assert want in named, want
    assert all("02_source" in t or "docs" in t or t.endswith(".md")
               or t.endswith(".log") or t.endswith(".sha256") for t in scope["targets"])


def test_delivery_face_excludes_transcripts_and_mirror(workspace_root):
    files, _unknown = rs.collect_targets(rs.delivery_face_targets(workspace_root),
                                        [os.path.join(workspace_root, e) for e in rs.NAMED_EXCLUDES])
    for f in files:
        assert "/refs/" not in f and "/spikes/" not in f, f
        assert not f.endswith(".squad_result.txt") and ".task-" not in f, f


def test_output_never_prints_hit_text(tmp_path, l0_path):
    l0 = rs.load_l0_norm(l0_path)
    excerpt = l0[len(l0) // 3:len(l0) // 3 + 40]
    (tmp_path / "a.md").write_text("说明：" + excerpt + "\n", encoding="utf-8")
    rc, out, err = _run_cli(["--paths", str(tmp_path)], extra=["--source-l0", l0_path])
    assert rc == 1
    assert excerpt[:20] not in out
    assert ":l0_verbatim:" in out
    assert _summary(out)["exit_basis"] == "unwhitelisted_l0_verbatim==0"


def test_secondary_rule_is_reading_only_by_default(tmp_path, l0_path):
    """次要规则（quoted_body）默认只出读数、不进退出码（PM m5-07 §一.4 的出口判据是内容比对）。"""
    (tmp_path / "a.md").write_text(f"说明：“{synth_text(60)}”\n", encoding="utf-8")
    rc, out, err = _run_cli(["--paths", str(tmp_path)], extra=["--source-l0", l0_path])
    assert rc == 0
    assert _summary(out)["secondary_hits_total"] == 1
    rc2, out2, err2 = _run_cli(["--paths", str(tmp_path)],
                               extra=["--source-l0", l0_path, "--fail-on-secondary"])
    assert rc2 == 1


def test_l0_missing_is_skip_not_pass(tmp_path):
    rc, out, err = _run_cli(["--paths", str(tmp_path)],
                            extra=["--source-l0", str(tmp_path / "missing.txt")])
    assert rc == 3
    assert "E_REDLINE_L0_MISSING" in err
    assert _summary(out)["scope"]["l0_status"] == "skipped_no_l0"


# --------------------------------------------------------------- --probe / 退出码
def test_probe_holds_on_clean_scope(tmp_path, l0_path):
    (tmp_path / "a.md").write_text("说明：普通说明文字，无长段。\n", encoding="utf-8")
    rc, out, err = _run_cli(["--paths", str(tmp_path)], extra=["--source-l0", l0_path, "--probe"])
    assert rc == 0, (rc, out, err)
    payload = _summary(out)
    assert payload["probe_ok"] is True
    cases = {c["case"]: c for c in payload["probe"]}
    assert cases["positive_l0_excerpt_punctuation_stripped"]["fired"] is True
    assert cases["negative_repo_line"]["clean"] is True
    assert cases["title_exemption"]["clean"] is True
    assert cases["back_to_baseline"]["hits"] == 0


def test_probe_covers_line_splitting_escape(tmp_path, l0_path):
    """自证探针必须覆盖 **R-8 的按行切段路径**（否则门禁自证对最危险的那条路径无读数）。"""
    (tmp_path / "a.md").write_text("说明：普通说明文字，无长段。\n", encoding="utf-8")
    rc, out, err = _run_cli(["--paths", str(tmp_path)], extra=["--source-l0", l0_path, "--probe"])
    assert rc == 0, (rc, out, err)
    cases = {c["case"]: c for c in _summary(out)["probe"]}
    core = cases["positive_l0_excerpt_split_15_cjk_per_line"]
    assert core["fired"] is True and core["lines"] == 14 and core["cjk_per_line"] == 15
    assert core["max_run_len"] == 210
    two = cases["positive_l0_excerpt_two_lines_of_105"]
    assert two["fired"] is True and two["max_run_len"] == 210
    variants = cases["positive_form_variants_single_line"]
    assert variants["fired"] is True and all(variants["variants"].values())


def test_probe_returns_1_when_scope_is_red(tmp_path, l0_path):
    """scope 本身红 ⇒ `--probe` 必须非 0（自证不掩盖树状态）。"""
    l0 = rs.load_l0_norm(l0_path)
    (tmp_path / "a.md").write_text("说明：" + l0[len(l0) // 3:len(l0) // 3 + 40] + "\n", encoding="utf-8")
    rc, out, err = _run_cli(["--paths", str(tmp_path)], extra=["--source-l0", l0_path, "--probe"])
    assert rc == 1
    assert _summary(out)["probe_ok"] is True


def test_usage_error_when_no_target():
    proc = subprocess.run([sys.executable, SCAN], capture_output=True, text=True)
    assert proc.returncode == 2


def test_usage_error_when_path_missing():
    proc = subprocess.run([sys.executable, SCAN, "--paths", "/nonexistent-xyz"],
                          capture_output=True, text=True)
    assert proc.returncode == 2
