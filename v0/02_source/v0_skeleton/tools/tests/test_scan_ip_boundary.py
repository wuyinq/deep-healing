"""`scan_ip_boundary.py` 单测（M5.1 r2 / S1~S5 + D-4/D-6；设计 §8 判据对照表）。

覆盖：
  - 模式表收敛（只剩 2 条；5 条已删模式**不得回归**，行为面验证）
  - D-4 双向对照：真正文段落形态（≥60 CJK / ≥24 CJK 且 ≥2 句末标点）⇒ 必红；
    技术性短引文（24 CJK 单句、0 句末标点）⇒ 不红
  - S5 解禁：书名《…》/ 章节号 ⇒ 不红
  - **位置对照（Raven C-2）**：正文段落放进声明站点行内 ⇒ **仍必红**
  - 哨兵（D-6）：声明站点豁免只对 `jump_scare` 生效，且必须**同一行**含 `IP-BOUNDARY-DECLARATION`
  - 后缀面：`.log/.out/.tsv/.csv` 进扫描面
  - `--probe` **逐模式**自证（Raven M-8）+ 坏模式必须被探针抓到
  - 输出面：明细只打 `file:line:pattern:length`，不打命中行文本（Raven C-3）
  - 已知残余面显式声明（Raven L-4：同名文件级自排除）
"""
from __future__ import annotations

from v0_testkit import fact_line, jump_phrase, quote, quote_corner, synth_cjk, synth_sentence

DELETED_PATTERNS = ("gore_lexicon", "monster_lexicon", "novel_title_reference",
                    "chapter_reference", "verbatim_quote_marks")


# ----------------------------------------------------------------- 模式表
def test_pattern_table_is_converged(ipb):
    assert ipb.PATTERN_NAMES == ("jump_scare", "verbatim_body_paragraph")
    assert set(ipb.MATCHERS) == set(ipb.PATTERN_NAMES)
    for name in DELETED_PATTERNS:
        assert name not in ipb.PATTERN_NAMES, f"已删模式不得回归：{name}"
        assert name not in ipb.MATCHERS, f"已删模式不得回归：{name}"


def test_only_jump_scare_is_exemptable(ipb):
    assert ipb.EXEMPTABLE_PATTERN == "jump_scare"
    assert ipb.DECLARATION_SENTINEL == "IP-BOUNDARY-DECLARATION"


def test_d4_thresholds_pinned(ipb):
    assert ipb.D4_LONG_CJK == 60
    assert ipb.D4_MIN_CJK == 24
    assert ipb.SENT_PUNCT == "。！？；"


# ----------------------------------------------------------------- S5 解禁（负向对照）
def test_s5_relaxation_title_chapter_and_short_quote_are_green(ipb, tree):
    """书名 / 章节号 / 技术性短引文（24 CJK 单句、0 句末标点）⇒ 三者都**不得**命中。"""
    root = tree({
        "notes.md": "引用作品名《我的治愈系游戏》与章节号第109章 ch109 均不判红\n",
        "spec.md": "技术性强调：" + quote_corner(synth_sentence(24, 0)) + "\n",
        "other.md": "另一套引号：" + quote(synth_sentence(25, 0)) + "\n",
    })
    assert ipb.scan(root) == []
    assert ipb.main(["--root", str(root)]) == 0


# ----------------------------------------------------------------- D-4 正向对照
def test_long_quoted_paragraph_is_red(ipb, tree):
    root = tree({"a.md": "说明：" + quote(synth_cjk(60)) + "\n"})
    hits = ipb.scan(root)
    assert [h["pattern"] for h in hits] == ["verbatim_body_paragraph"]
    assert hits[0]["length"] == 60
    assert ipb.main(["--root", str(root)]) == 1


def test_two_sentence_quoted_paragraph_is_red(ipb, tree):
    """≥24 CJK 且 ≥2 个句末/分句标点 ⇒ 判红（D-4 的 (b) 支）。"""
    root = tree({"a.md": "说明：" + quote_corner(synth_sentence(24, 2)) + "\n"})
    hits = ipb.scan(root)
    assert [h["pattern"] for h in hits] == ["verbatim_body_paragraph"]


def test_single_punctuation_is_not_enough(ipb, tree):
    """≥24 CJK 但只有 1 个句末标点 ⇒ 不判红（(b) 支的边界）。"""
    root = tree({"a.md": "说明：" + quote(synth_sentence(24, 1)) + "\n"})
    assert ipb.scan(root) == []


def test_jump_scare_is_red_outside_declaration_sites(ipb, tree):
    root = tree({"notes.md": "呈现方式：" + jump_phrase() + "\n"})
    hits = ipb.scan(root)
    assert [h["pattern"] for h in hits] == ["jump_scare"]
    assert hits[0]["whitelisted"] is False


# ----------------------------------------------------------------- 位置对照（Raven C-2）
def test_body_paragraph_in_declaration_line_is_still_red(ipb, tree):
    """C-2 的绕过手法：正文段落放进 art-bible.md 的**声明站点行内**（同行含 不得/禁用）⇒ 仍必红。"""
    root = tree({
        "art-bible.md": "禁用高饱和色；不得出现 " + quote(synth_cjk(60)) + "\n",
    })
    hits = ipb.scan(root)
    assert len(hits) == 1
    assert hits[0]["pattern"] == "verbatim_body_paragraph"
    assert hits[0]["whitelisted"] is False
    assert ipb.main(["--root", str(root)]) == 1


def test_body_paragraph_in_schema_comment_is_still_red(ipb, tree):
    root = tree({
        "worldview.schema.json": '{"$comment": "禁用 ' + quote(synth_cjk(60)) + '"}\n',
    })
    hits = ipb.scan(root)
    assert [h["pattern"] for h in hits] == ["verbatim_body_paragraph"]
    assert hits[0]["whitelisted"] is False


def test_body_paragraph_is_not_exemptable_even_with_sentinel(ipb, tree):
    """`verbatim_body_paragraph` **不可豁免** —— 连哨兵 + 声明站点都不豁免（D-6 核心）。"""
    root = tree({
        "art-bible.md": f"禁用；{ipb.DECLARATION_SENTINEL} 不得出现 " + quote(synth_cjk(60)) + "\n",
        "worldview.schema.json": '{"$comment": "' + ipb.DECLARATION_SENTINEL + " " + quote(synth_cjk(60)) + '"}\n',
    })
    hits = ipb.scan(root)
    assert len(hits) == 2
    assert all(h["pattern"] == "verbatim_body_paragraph" for h in hits)
    assert all(h["whitelisted"] is False for h in hits)


# ----------------------------------------------------------------- 哨兵语义（D-6）
def test_jump_scare_whitelisted_only_with_site_and_sentinel(ipb, tree):
    root = tree({
        "worldview.schema.json": '{"$comment": "' + ipb.DECLARATION_SENTINEL + " 不走 " + jump_phrase() + '"}\n',
    })
    hits = ipb.scan(root)
    assert [h["whitelisted"] for h in hits] == [True]
    assert ipb.main(["--root", str(root)]) == 0


def test_jump_scare_not_whitelisted_without_sentinel(ipb, tree):
    """旧词法判据（零/不得/禁止/禁用）**不再**构成豁免 —— 取代为显式哨兵。"""
    root = tree({
        "worldview.schema.json": '{"$comment": "零 不得 禁止 禁用 不走 ' + jump_phrase() + '"}\n',
    })
    hits = ipb.scan(root)
    assert [h["whitelisted"] for h in hits] == [False]
    assert ipb.main(["--root", str(root)]) == 1


def test_jump_scare_not_whitelisted_outside_declaration_sites(ipb, tree):
    root = tree({
        "notes.md": ipb.DECLARATION_SENTINEL + " 不走 " + jump_phrase() + "\n",
    })
    hits = ipb.scan(root)
    assert [h["whitelisted"] for h in hits] == [False]


# ----------------------------------------------------------------- 后缀面（Raven 旁路 8）
def test_text_suffixes_cover_reading_and_intermediate_formats(ipb):
    for suffix in (".log", ".out", ".tsv", ".csv"):
        assert suffix in ipb.TEXT_SUFFIXES


def test_scan_covers_log_out_tsv_csv(ipb, tree):
    root = tree({
        "run.log": "说明：" + quote(synth_cjk(60)) + "\n",
        "probe.out": "说明：" + quote(synth_cjk(60)) + "\n",
        "facts.tsv": "说明：" + quote(synth_cjk(60)) + "\n",
        "rows.csv": "说明：" + quote(synth_cjk(60)) + "\n",
    })
    files = sorted(h["file"] for h in ipb.scan(root))
    assert files == ["facts.tsv", "probe.out", "rows.csv", "run.log"]


def test_binary_and_generated_dirs_are_skipped(ipb, tree):
    root = tree({
        "a.bin": "说明：" + quote(synth_cjk(60)) + "\n",
        "__pycache__/b.py": "说明：" + quote(synth_cjk(60)) + "\n",
    })
    assert ipb.scan(root) == []


# ----------------------------------------------------------------- 自排除（已知残余面，Raven L-4）
def test_self_exclusion_is_file_level_only_and_declared(ipb, tree):
    """**已知残余面（显式声明）**：自排除粒度 = 「文件名 + 自身独有标记」，
    因此「名为 scan_ip_boundary.py 且含标记」的**任意副本**被整体跳过。
    本测试把该面写死：① 带标记的同名文件被排除；② 不带标记的同名文件照常扫描；
    ③ **目录**不构成豁免（放在子目录里的越界文件仍判红）。"""
    body = "说明：" + quote(synth_cjk(60)) + "\n"
    root = tree({
        "scan_ip_boundary.py": f"# {ipb.SELF_EXCLUDE_MARKER}\n" + body,
        "other/scan_ip_boundary.py": body,
        "notes.md": body,
    })
    files = sorted(h["file"] for h in ipb.scan(root))
    assert files == ["notes.md", "other/scan_ip_boundary.py"]
    assert "scan_ip_boundary.py" not in files


# ----------------------------------------------------------------- 探针自证（Raven M-8）
def test_probe_self_proof_is_per_pattern(ipb, tree):
    root = tree({"notes.md": "干净\n"})
    proof = ipb._probe_self_proof(root, ipb.scan(root))
    assert proof["per_pattern_detected"] == {"jump_scare": True, "verbatim_body_paragraph": True}
    assert proof["probe_detected"] is True
    assert proof["removed_restores_baseline"] is True


def test_probe_fails_when_one_pattern_is_broken(ipb, tree, monkeypatch):
    """**M-8 的反例**：任一模式失效 ⇒ 自证必须失败（「模式无关」的自证不算自证）。"""
    root = tree({"notes.md": "干净\n"})
    monkeypatch.setitem(ipb.MATCHERS, "verbatim_body_paragraph", lambda line: [])
    proof = ipb._probe_self_proof(root, ipb.scan(root))
    assert proof["per_pattern_detected"]["verbatim_body_paragraph"] is False
    assert proof["probe_detected"] is False


def test_probe_cli_exit_zero_and_no_residue(ipb, tree):
    root = tree({"notes.md": "干净\n"})
    assert ipb.main(["--root", str(root), "--probe"]) == 0
    assert not (root / ipb.PROBE_FILENAME).exists(), "探针文件不得落在被扫的树里"


def test_probe_detects_injected_body_paragraph_in_temp_tree(ipb, tree):
    """探针文本必须真的能触发 D-4 —— 构造长度不足即自证失败（防止探针退化）。"""
    payload = ipb.probe_payload()
    assert len(ipb.CJK_RE.findall(payload["verbatim_body_paragraph"])) >= ipb.D4_LONG_CJK
    assert ipb._match_verbatim_body_paragraph(payload["verbatim_body_paragraph"])


# ----------------------------------------------------------------- 输出面（Raven C-3）
def test_output_never_prints_hit_line_text(ipb, tree, capsys):
    marker = "UNIQUEHITMARKER7F3A"
    root = tree({"notes.md": f"{marker} 说明：" + quote(synth_cjk(60)) + "\n"})
    assert ipb.main(["--root", str(root)]) == 1
    captured = capsys.readouterr()
    assert marker not in captured.out
    assert marker not in captured.err
    assert "verbatim_body_paragraph" in captured.err


def test_report_shape(ipb, tree):
    root = tree({"notes.md": "说明：" + quote(synth_cjk(60)) + "\n"})
    hits = ipb.scan(root)
    assert hits[0].keys() >= {"file", "line", "pattern", "length", "whitelisted", "reason"}


# ----------------------------------------------------------------- CLI
def test_usage_error_exit_2(ipb, tmp_path):
    assert ipb.main(["--root", str(tmp_path / "nope")]) == 2


def test_fact_line_shape_helper_is_not_scanned_as_paragraph(ipb, tree):
    """事实行（含锚点）本身不是 IP 命中源 —— 单测夹具的锚点语法不得自带命中。"""
    root = tree({"01-structure-facts.md": fact_line("STR-01", "合成事实行")})
    assert ipb.scan(root) == []
