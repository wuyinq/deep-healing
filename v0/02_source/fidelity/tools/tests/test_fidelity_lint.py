#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fidelity_lint 单测：R1~R7 逐规则正向 + 负向对照 + `--probe` + 退出码。

M5.1 r2.5（口径层）：**R2 = L0 口径 B**（五项逐字校验：真章号 / URL / 首发时间 / `src: sha256=` 前缀 /
`lines=` 行区间），`cid:` 降为可选冗余；**旧语法判红**。
M5.1 r1.6（收口）：六册换锚后**真实树已转绿** ⇒ ① 真实树断言改为「rc == 0 且 0 违规」；
② 「过渡态只有 R2」这一不变式与 `--probe` 的「红树」用例**改用合成树**（真实树不能再当红树/过渡态）。
每个用例都断言「该红时红、不该红时不红」，证明判据**有牙**（RK-3）。

纪律：用**索引真实行**合成锚点的用例一律传 `index_path`（真实索引）；合成树里不含 ch180/ch332。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fidelity_testkit import anchor_b, src_seg, synth_text

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINT = os.path.join(TOOLS, "fidelity_lint.py")
sys.path.insert(0, TOOLS)

import fidelity_lint as fl  # noqa: E402

REAL_SHA12 = "9c8b562e94e0"


def _run_cli(root, index, extra=()):
    cmd = [sys.executable, LINT, "--strict", "--root", root, "--index", index, *extra]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _rules(root, index):
    lc = fl.Lint(root, index)
    lc.run()
    return {r for (_f, _l, r, _n) in lc.violations}


def _valid_fact(index_rec, sha12=REAL_SHA12, fact="合成事实行"):
    """用**索引真实行**合成一条合法 B 锚点事实行。"""
    a = anchor_b(index_rec["no"], index_rec["official_url"], index_rec["first_pub"])
    s = src_seg(sha12, index_rec["src_line_start"], index_rec["src_line_end"])
    return f"- [STR-01] {fact} || anchor: {a} || src: {s}\n"


# --------------------------------------------------------------- 基线 / 过渡态
def test_real_tree_is_green_after_anchor_upgrade(fidelity_root, index_path):
    """真实六册**换锚后已转绿** ⇒ `rc == 0` 且 `violations_total == 0`（r2.5 的「过渡态全红」断言已过期）。

    判据仍有牙：任何一册回归旧语法（缺 `src:` 段）/ 假锚点 / 正文段，都会让对应规则 > 0 ⇒ `rc == 1` ⇒ 本用例失败。
    """
    rc, out, err = _run_cli(fidelity_root, index_path)
    assert rc == 0, (rc, out, err)
    summary = json.loads(out.strip().splitlines()[-1])
    assert summary["violations_total"] == 0
    for rule in ("R1", "R2", "R3", "R4", "R5", "R6", "R7"):
        assert summary["per_rule"][rule] == 0, rule
    assert summary["anchor_source"].endswith("L1-fulltext-index.tsv")
    assert summary["l0_sha256_12"] == REAL_SHA12


def test_synthetic_old_syntax_tree_is_r2_only(book_tree, mini_index):
    """「旧语法（无 `src:` 段）过渡态 ⇒ **只出 R2**」这一不变式改用**合成树**钉住。

    真实树换锚后已绿（不再是过渡态）⇒ 过渡态读数只能在合成树上取：`mini_index` 的锚点行只有
    `ch<no> + URL + 时间`，没有任何 `src:` 段 ⇒ 恰好 R2，**不得**连带出 R1 / R3~R7。
    """
    header, first_row = Path(mini_index).read_text(encoding="utf-8").splitlines()[:2]
    cols = dict(zip(header.split("\t"), first_row.split("\t")))
    line = (f"- [STR-01] 探针：旧语法（无 src 段） || anchor: "
            f"{anchor_b(cols['no'], cols['official_url'], cols['first_pub'])}\n")
    root = book_tree({"00-source-manifest.md": line})
    assert _rules(root, mini_index) == {"R2"}


def test_lower_bounds_met_on_real_tree(fidelity_root, index_path):
    lc = fl.Lint(fidelity_root, index_path)
    lc.run()
    assert lc.books["01-structure-facts.md"]["facts"] >= 6
    assert lc.books["02-mechanism-facts.md"]["facts"] >= 10
    assert lc.books["03-ghost-system.md"]["facts"] >= 4
    assert lc.books["04-name-register.md"]["facts"] >= 20
    assert lc.books["05-character-dossiers.md"]["facts"] >= 1
    assert lc.books["05-character-dossiers.md"]["dossiers"] >= 1


def test_r2_checks_are_five_and_declared(mini_index):
    lc = fl.Lint(os.path.dirname(mini_index), mini_index)
    assert lc.l0_sha12 == REAL_SHA12
    assert fl.DEFAULT_L0_SHA12 == REAL_SHA12
    assert fl.INDEX_REQUIRED_COLUMNS == ("no", "official_url", "first_pub",
                                         "src_line_start", "src_line_end")


# --------------------------------------------------------------- R1
def test_r1_fact_line_without_anchor(book_tree, mini_index):
    root = book_tree({"01-structure-facts.md": "- [STR-01] 探针：无锚点事实行\n"})
    assert "R1" in _rules(root, mini_index)


def test_r1_malformed_anchor(book_tree, mini_index):
    root = book_tree({"01-structure-facts.md": "- [STR-01] 探针：锚点残缺 || anchor: ch7\n"})
    assert "R1" in _rules(root, mini_index)


# --------------------------------------------------------------- R2（合法 B / 五种假锚点）
def test_r2_valid_b_anchor_passes(book_tree, index_path, real_index_rows):
    """合法 B 锚点（用索引真实行合成）⇒ 不判红。"""
    for no in ("180", "332"):
        rec = real_index_rows[no]
        root = book_tree({"00-source-manifest.md": _valid_fact(rec)})
        assert _rules(root, index_path) == set(), no


def test_r2_misaligned_row_uses_true_chapter_no(book_tree, index_path, real_index_rows):
    """真 332 标成 322 的错位行：`ch332` 合法；写成 `ch322`（标号）⇒ 行区间/URL 对不上 ⇒ R2。"""
    rec = real_index_rows["332"]
    assert rec["labeled_no"] == "322"
    ok_root = book_tree({"00-source-manifest.md": _valid_fact(rec)})
    assert _rules(ok_root, index_path) == set()
    misaligned = _valid_fact(rec).replace("anchor: ch332", "anchor: ch322")
    bad_root = book_tree({"00-source-manifest.md": misaligned})
    assert "R2" in _rules(bad_root, index_path)


@pytest.mark.parametrize("mutate", [
    lambda line: line.replace("anchor: ch180", "anchor: ch9999"),                       # ① 不存在的真章号
    lambda line: line.replace("648165987/", "000000000/"),                              # ② 错 URL
    lambda line: line.replace("2021-04-19 18:49:14", "2000-01-01 00:00:00"),            # ③ 错首发时间
    lambda line: line.replace(f"sha256={REAL_SHA12}", "sha256=000000000000"),           # ④ 错 sha 前缀
    lambda line: line.replace("lines=10395-10451", "lines=10395-10452"),                # ⑤ 错行区间
])
def test_r2_five_fake_anchors_fire(book_tree, index_path, real_index_rows, mutate):
    line = mutate(_valid_fact(real_index_rows["180"]))
    root = book_tree({"00-source-manifest.md": line})
    assert "R2" in _rules(root, index_path)


def test_r2_old_syntax_fires(book_tree, index_path, real_index_rows):
    """旧语法（`ch<N>` + URL + 时间，**无** `src:` 段）⇒ R2 判红（六册过渡态的判据来源）。"""
    rec = real_index_rows["180"]
    line = (f"- [STR-01] 探针：旧语法 || anchor: "
            f"{anchor_b(rec['no'], rec['official_url'], rec['first_pub'])}\n")
    root = book_tree({"00-source-manifest.md": line})
    assert _rules(root, index_path) == {"R2"}


def test_r2_cid_only_fires(book_tree, index_path, real_index_rows):
    """只有 `cid:` 而无真章号 ⇒ R2 判红（`cid:` 不得替代真章号）。"""
    rec = real_index_rows["180"]
    line = (f"- [STR-01] 探针：只有 cid || anchor: cid:648165987 "
            f"{rec['official_url']} {rec['first_pub']} || src: "
            f"{src_seg(REAL_SHA12, rec['src_line_start'], rec['src_line_end'])}\n")
    root = book_tree({"00-source-manifest.md": line})
    assert _rules(root, index_path) == {"R2"}


def test_r2_cid_redundant_coexists_passes(book_tree, index_path, real_index_rows):
    """`cid:` 冗余与真章号并存 ⇒ 不判红。"""
    rec = real_index_rows["180"]
    line = (f"- [STR-01] 探针：cid 冗余 || anchor: "
            f"{anchor_b(rec['no'], rec['official_url'], rec['first_pub'], cid='648165987')} || src: "
            f"{src_seg(REAL_SHA12, rec['src_line_start'], rec['src_line_end'])}\n")
    root = book_tree({"00-source-manifest.md": line})
    assert _rules(root, index_path) == set()


def test_r2_bad_src_segment_fires(book_tree, index_path, real_index_rows):
    """`src:` 段残缺（缺 sha256）⇒ R2。"""
    rec = real_index_rows["180"]
    line = (f"- [STR-01] 探针：src 残缺 || anchor: "
            f"{anchor_b(rec['no'], rec['official_url'], rec['first_pub'])} || src: "
            f"lines={rec['src_line_start']}-{rec['src_line_end']}\n")
    root = book_tree({"00-source-manifest.md": line})
    assert _rules(root, index_path) == {"R2"}


# --------------------------------------------------------------- R3
def test_r3_unverified_without_reason(book_tree, mini_index):
    root = book_tree({"01-structure-facts.md": "- [STR-01] 探针：无理由 || anchor: UNVERIFIED\n"})
    assert "R3" in _rules(root, mini_index)


def test_r3_unverified_with_reason_passes(book_tree, mini_index):
    root = book_tree({"00-source-manifest.md": "- [STR-01] 探针：有理由 || anchor: UNVERIFIED || reason: 样本内 0 命中\n"})
    assert _rules(root, mini_index) == set()


# --------------------------------------------------------------- R4
def test_r4_below_lower_bound(book_tree, mini_index):
    body = "".join(f"- [NAM-{i:02d}] 事实 {i} || anchor: UNVERIFIED || reason: 探针\n" for i in range(1, 4))
    root = book_tree({"04-name-register.md": body})
    assert "R4" in _rules(root, mini_index)


# --------------------------------------------------------------- R5 / R6 / R7
def test_r5_quoted_long_segment(book_tree, mini_index):
    root = book_tree({"01-structure-facts.md": f"说明：注入“{synth_text(60)}”\n"})
    assert "R5" in _rules(root, mini_index)


def test_r5_quoted_24_with_two_sentence_punct(book_tree, mini_index):
    root = book_tree({"01-structure-facts.md": f"说明：注入“{synth_text(24)}。再来一句。”\n"})
    assert "R5" in _rules(root, mini_index)


def test_r5_not_fired_for_short_quote(book_tree, mini_index):
    """技术性短引文形态（24 CJK、句末标点 0，F-18 定标）⇒ 不判红。"""
    root = book_tree({"01-structure-facts.md": f"说明：技术性短引文“{synth_text(24)}”\n"})
    assert "R5" not in _rules(root, mini_index)


def test_r6_unquoted_run(book_tree, mini_index):
    root = book_tree({"01-structure-facts.md": f"说明：引号外长串 {synth_text(60)}\n"})
    assert "R6" in _rules(root, mini_index)


def test_r6_applies_to_fact_lines_too(book_tree, index_path, real_index_rows):
    """PM 裁决 m5-07 §一.7：R6 必须作用于**事实行**（事实行是内容落点，不得留空档）。"""
    rec = real_index_rows["180"]
    line = _valid_fact(rec, fact=f"引号外正文段 {synth_text(60)}")
    root = book_tree({"00-source-manifest.md": line})
    assert "R6" in _rules(root, index_path)


def test_r6_not_fired_inside_quotes(book_tree, mini_index):
    """同样长度放在引号内 ⇒ 只该由 R5 判红，R6 不重复。"""
    root = book_tree({"01-structure-facts.md": f"说明：“{synth_text(60)}”\n"})
    got = _rules(root, mini_index)
    assert "R5" in got and "R6" not in got


def test_r7_fact_line_carrying_body_quote(book_tree, mini_index):
    line = (f"- [STR-01] 探针：事实行内正文段“{synth_text(30)}。第二句。” || anchor: "
            f"UNVERIFIED || reason: 探针\n")
    root = book_tree({"01-structure-facts.md": line})
    assert "R7" in _rules(root, mini_index)


def test_title_and_chapter_reference_not_flagged(book_tree, mini_index):
    """书名 / 章节号可引用 ⇒ 不判红（S5 口径）。"""
    root = book_tree({"00-source-manifest.md": "说明：引用作品名《我的治愈系游戏》与章节号 ch109 均不判红\n"})
    assert _rules(root, mini_index) == set()


# --------------------------------------------------------------- 扫描面与输出
def test_scan_face_is_books_only(book_tree, mini_index):
    """tools/** 与非 .md 文件不在 lint 面内（v2 钉死）。"""
    root = book_tree({"00-source-manifest.md": "- [STR-01] 正常 || anchor: UNVERIFIED || reason: 探针\n",
                      "notes.txt": f"注入“{synth_text(60)}”\n"})
    os.makedirs(os.path.join(root, "tools"), exist_ok=True)
    with open(os.path.join(root, "tools", "x.md"), "w", encoding="utf-8") as fh:
        fh.write(f"注入“{synth_text(60)}”\n")
    assert _rules(root, mini_index) == set()


def test_output_never_prints_hit_text(book_tree, mini_index):
    probe_line = synth_text(60)
    root = book_tree({"01-structure-facts.md": f"说明：“{probe_line}”\n"})
    rc, out, err = _run_cli(root, mini_index)
    assert rc == 1
    assert probe_line not in out
    assert ":R5:" in out


# --------------------------------------------------------------- --probe / 退出码
def test_probe_all_cases_fire_and_back_to_baseline(fidelity_root, index_path):
    rc, out, err = _run_cli(fidelity_root, index_path, extra=["--probe"])
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["probe_ok"] is True
    assert payload["back_to_baseline"] is True
    assert payload["baseline_violations"] == 0
    cases = {c["case"]: c for c in payload["probe"]}
    for name in ("no_anchor", "old_syntax", "cid_only", "fake_chapter", "fake_url", "fake_time",
                 "fake_sha", "fake_lines", "bad_src", "malformed_anchor",
                 "body_in_quote", "body_unquoted", "body_unquoted_in_fact", "body_in_fact"):
        assert cases[name].get("fired") is True, name
    for name in ("valid_b_ok", "cid_redundant_ok", "short_quote_ok", "title_ok"):
        assert cases[name].get("clean") is True, name


def test_probe_returns_1_when_tree_is_red(book_tree, mini_index):
    """树本身红时 `--strict --probe` 仍须非 0 —— 自证**不掩盖**树状态。

    真实树换锚后已绿（不能再用真实树当红树）⇒ 用**合成红树**（缺锚点的 R1 事实行）+ 合成索引。
    """
    root = book_tree({"00-source-manifest.md": "- [STR-01] 探针：无锚点事实行\n"})
    rc, out, err = _run_cli(root, mini_index, extra=["--probe"])
    assert rc == 1, (rc, out, err)
    assert json.loads(out.strip().splitlines()[-1])["probe_ok"] is True


def test_usage_error_on_missing_root(mini_index):
    rc, out, err = _run_cli("/nonexistent-root-xyz", mini_index)
    assert rc == 2


def test_usage_error_on_missing_index(fidelity_root):
    rc, out, err = _run_cli(fidelity_root, "/nonexistent-index.tsv")
    assert rc == 2


def test_usage_error_when_index_lacks_line_columns(fidelity_root, tmp_path):
    """索引缺 `src_line_start` 列 ⇒ fail-closed（exit 2），**不得**静默降级为「不校验行区间」。"""
    bad = tmp_path / "chapters-like.tsv"
    bad.write_text("no\ttitle\tcid\turl\tfirst_pub\twords\tvolume\n"
                   "52\t第52章\t636359097\thttps://example.invalid/x/\t2021-02-19 17:05:44\t2191\tfree\n",
                   encoding="utf-8")
    rc, out, err = _run_cli(fidelity_root, str(bad))
    assert rc == 2
    assert "usage" in err
