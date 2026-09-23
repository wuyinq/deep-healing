"""`scan_fidelity_terms.py` 单测（M5.1 r2 / 设计 §5.4；r2.5 补 Raven R-3 / R-4）。

覆盖：
  - 词表与下界**钉死**（8 词 / 每词 ≥1，只允许移除，不允许静默改写或降低）
  - register 面：命中必须落在**事实行**上才计数 —— 事实行谓词**与 lint R1 同源**（R-3）：
    行以 `- [` 开头**且**含 ` || anchor: `；含该子串但不以 `- [` 开头的说明行**不计数**
  - 计数面 = **事实文本段**（`- [` 之后、第一个 `||` 之前）；**同一事实行最多计 2 个目标词**（R-4）
  - register 面扫描根 = `fidelity/*.md`（**不递归** ⇒ `fidelity/tools/**` 不在面内；非 `.md` 不在面内）
  - 反向对照：删掉某词的事实行 ⇒ exit 1（判据有牙）
  - pack 面：`enforced:false` + `NOT_ENFORCED_UNTIL_M5_2`，**不参与退出码**（Raven M-6 / RK-4）
  - `--probe`：逐词事实行注入必须计数；R-3 变体（含锚点子串的说明行）不得计数；
    一行词沙拉至多 2 词 +1（R-4）；移除回基线
  - 探针有牙：把事实行谓词打坏 ⇒ 探针必须失败
  - 报告形状：每面 `enforced` 布尔 + 逐词 `命中数 / 下界` + `capped_lines` 读数
"""
from __future__ import annotations

import json

from v0_testkit import fact_line

# 与脚本钉死的词表逐字一致（改这里等于改规格，必须先有 architect 复核）。
# M5.1 r1.6：`任务分级`（L0 全书 0 命中 ⇒ 判据同义反复，Sentinel MED-2）**替换**为
#   `隐藏任务`（L0 172 命中；冻结六册已有事实行命中：MEC-04 / NAM-09）—— 见 03 日志 §M5.1-r1.6 R3。
PINNED_TERMS = ("楼长", "管理者", "友善度", "怨念", "诅咒物", "怪谈", "隐藏任务", "属性面板")


def _books(terms=PINNED_TERMS, extra: str = "") -> dict[str, str]:
    """造一个 register 面达标的最小六册树（每词一条事实行）。"""
    files = {"fidelity/00-source-manifest.md": "# 来源清单\n"}
    for index, term in enumerate(terms, start=1):
        files["fidelity/01-structure-facts.md"] = files.get("fidelity/01-structure-facts.md", "# 结构\n")
        files["fidelity/01-structure-facts.md"] += fact_line(f"STR-{index:02d}", f"合成事实行：{term}")
    if extra:
        files["fidelity/01-structure-facts.md"] += extra
    return files


# ----------------------------------------------------------------- 钉死口径
def test_terms_and_floor_are_pinned(sft):
    assert sft.TERMS == PINNED_TERMS
    assert sft.FLOOR == 1
    assert sft.FACT_MARK == " || anchor: "
    assert sft.FACT_PREFIX == "- ["
    assert sft.MAX_TERMS_PER_LINE == 2


def test_term_table_change_rule_is_removal_only(sft):
    """词表调整规则必须写在脚本可读的形态里：只允许移除 ⇒ 词表是**元组**（不可原地改）。"""
    assert isinstance(sft.TERMS, tuple)
    assert len(sft.TERMS) == 8


# ----------------------------------------------------------------- register 面
def test_register_face_passes_when_every_term_hits_a_fact_line(sft, tree):
    root = tree(_books())
    hits, fact_lines, readings = sft.count_register(root)
    assert set(hits) == set(PINNED_TERMS)
    assert all(hits[term] >= sft.FLOOR for term in PINNED_TERMS)
    assert all(fact_lines[term] >= 1 for term in PINNED_TERMS)
    assert readings["fact_lines_total"] == len(PINNED_TERMS)
    assert sft.main(["--root", str(root), "--face", "register"]) == 0


def test_hits_on_non_fact_lines_do_not_count(sft, tree):
    root = tree(_books(extra="说明文字里出现 楼长 与 管理者，但这一行没有锚点\n"))
    hits, fact_lines, _ = sft.count_register(root)
    assert hits["楼长"] == 1 and fact_lines["楼长"] == 1
    assert hits["管理者"] == 1


# ----------------------------------------------------------------- R-3（事实行谓词与 lint 同源）
def test_r3_anchor_substring_without_fact_prefix_does_not_count(sft, tree):
    """R-3：含 ` || anchor: ` 子串但**不以 `- [` 开头**的说明行 ⇒ 不计数。"""
    root = tree(_books(extra="说明行（非事实行）：楼长 || anchor: 语法示例\n"))
    hits, fact_lines, _ = sft.count_register(root)
    assert hits["楼长"] == 1, "含锚点子串的说明行不得被计入事实行命中"
    assert fact_lines["楼长"] == 1


def test_r3_fact_prefix_without_anchor_does_not_count(sft, tree):
    """反向：以 `- [` 开头但**没有**锚点的行 ⇒ 也不是事实行（与 lint R1 同源）。"""
    root = tree(_books(extra="- [STR-99] 楼长 出现在没有锚点的行里\n"))
    hits, _, _ = sft.count_register(root)
    assert hits["楼长"] == 1


def test_r3_predicate_matches_lint_r1_semantics(sft):
    assert sft.is_fact_line("- [STR-01] 甲 || anchor: UNVERIFIED || reason: 探针") is True
    assert sft.is_fact_line("说明：甲 || anchor: 语法示例") is False
    assert sft.is_fact_line("- [STR-01] 甲（无锚点）") is False


# ----------------------------------------------------------------- R-4（计数面 + 每行 ≤2 词）
def test_r4_count_face_is_fact_text_segment_only(sft, tree):
    """R-4①：只认事实文本段（`- [` 之后、第一个 `||` 之前）—— 锚点/mirror 元数据里的词不计。"""
    root = tree(_books(extra="- [STR-98] 合成事实行（无目标词） || anchor: UNVERIFIED "
                              "|| reason: 探针里出现 属性面板 与 怪谈\n"))
    hits, _, _ = sft.count_register(root)
    assert hits["属性面板"] == 1 and hits["怪谈"] == 1, "锚点/理由段的词不得计数"


def test_r4_word_salad_line_counts_at_most_two_terms(sft, tree):
    """R-4②：一行词沙拉（8 词并列 + 合法锚点）至多计 2 词 ⇒ 不得把 8 词全部刷达标。"""
    salad = "- [STR-97] " + "、".join(PINNED_TERMS) + " || anchor: UNVERIFIED || reason: 探针词沙拉\n"
    root = tree(_books(extra=salad))
    hits, _, readings = sft.count_register(root)
    incremented = [t for t in PINNED_TERMS if hits[t] > 1]
    assert incremented == list(PINNED_TERMS[:2]), incremented
    assert readings["capped_lines"] == 1


def test_r4_salad_alone_cannot_meet_the_floor(sft, tree):
    """词沙拉**单独**不能达标：只有一行沙拉时，其余 6 词仍 0 命中 ⇒ register 面 exit 1。"""
    files = {"fidelity/00-source-manifest.md": "# 来源清单\n",
             "fidelity/01-structure-facts.md":
                 "- [STR-01] " + "、".join(PINNED_TERMS) + " || anchor: UNVERIFIED || reason: 探针\n"}
    root = tree(files)
    assert sft.main(["--root", str(root), "--face", "register"]) == 1


def test_register_face_fails_when_a_term_loses_its_fact_line(sft, tree):
    """反向对照：删掉某词的事实行 ⇒ exit 1（判据有牙，不是恒绿）。"""
    root = tree(_books(terms=tuple(t for t in PINNED_TERMS if t != "属性面板")))
    assert sft.main(["--root", str(root), "--face", "register"]) == 1


def test_register_root_is_non_recursive_top_level_md_only(sft, tree):
    """扫描根 = `fidelity/*.md`：`fidelity/tools/**` 与非 `.md` 都不在面内（Raven C-4）。"""
    root = tree(_books(extra=""))
    nested = root / "fidelity" / "tools"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "note.md").write_text(fact_line("X-01", "嵌套目录：属性面板"), encoding="utf-8")
    (root / "fidelity" / "notes.txt").write_text(fact_line("X-02", "非 md：属性面板"), encoding="utf-8")
    hits, _, _ = sft.count_register(root)
    assert hits["属性面板"] == 1, "嵌套目录 / 非 .md 文件不得计入 register 面"
    assert sft.register_files(root) == [root / "fidelity" / "00-source-manifest.md",
                                        root / "fidelity" / "01-structure-facts.md"]


def test_register_face_missing_fidelity_dir_is_empty_not_crash(sft, tree):
    root = tree({"notes.md": "空树\n"})
    hits, _, _ = sft.count_register(root)
    assert set(hits.values()) == {0}


# ----------------------------------------------------------------- pack 面
def test_pack_face_is_measured_but_not_enforced(sft, tree):
    files = _books()
    files["v0_skeleton/districts/xingfu-xiaoqu/pack.json"] = '{"note": "管理者 友善度"}\n'
    root = tree(files)
    report = sft.count_pack(root)
    assert report["管理者"] == 1
    assert sft.main(["--root", str(root), "--face", "pack"]) == 0
    assert sft.main(["--root", str(root), "--face", "all"]) == 0


def test_pack_face_reports_status_and_enforced_false(sft, tree, capsys):
    root = tree(_books())
    assert sft.main(["--root", str(root), "--face", "all"]) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[0])
    assert report["faces"]["pack"]["enforced"] is False
    assert report["faces"]["pack"]["status"] == "NOT_ENFORCED_UNTIL_M5_2"
    assert report["faces"]["register"]["enforced"] is True
    assert report["exit_basis"] == "enforced_faces_only"


def test_pack_face_cannot_rescue_a_failing_register_face(sft, tree):
    """RK-4：pack 面（未启用）不得把 register 面的红刷成绿。"""
    files = _books(terms=tuple(t for t in PINNED_TERMS if t != "怪谈"))
    files["v0_skeleton/districts/xf/pack.json"] = '{"note": "怪谈 怪谈 怪谈"}\n'
    root = tree(files)
    assert sft.main(["--root", str(root), "--face", "all"]) == 1


# ----------------------------------------------------------------- 报告形状
def test_report_shape_has_enforced_and_per_term_floor(sft, tree, capsys):
    root = tree(_books())
    assert sft.main(["--root", str(root), "--face", "all"]) == 0
    report = json.loads(capsys.readouterr().out.splitlines()[0])
    for name, face in report["faces"].items():
        assert isinstance(face["enforced"], bool), name
        for term, entry in face["per_term"].items():
            assert "hits" in entry and entry["floor"] == sft.FLOOR
    reg = report["faces"]["register"]
    assert reg["terms_total"] == 8 and reg["terms_met"] == 8
    assert reg["max_terms_per_line"] == 2 and "capped_lines" in reg


# ----------------------------------------------------------------- 探针
def test_probe_is_per_term_and_restores_baseline(sft, tree):
    root = tree(_books())
    assert sft.main(["--root", str(root), "--face", "register", "--probe"]) == 0


def test_probe_covers_r3_variant_and_r4_salad(sft, tree, capsys):
    """探针必须覆盖 R-3（含锚点子串的说明行）与 R-4（词沙拉至多 2 词）两条残余面。"""
    root = tree(_books())
    assert sft.run_probe(root) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["probe_ok"] is True
    assert all(c["non_fact_line_ignored"] for c in payload["probe"] if "term" in c)
    salad = [c for c in payload["probe"] if c.get("case") == "word_salad_line_capped"]
    assert salad and salad[0]["capped"] is True
    assert len(salad[0]["terms_incremented"]) <= sft.MAX_TERMS_PER_LINE


def test_probe_has_teeth_when_fact_line_predicate_breaks(sft, tree, monkeypatch):
    """把「只数事实行」的谓词打坏 ⇒ 探针必须失败（否则探针是恒真的绿命令）。"""
    root = tree(_books())
    monkeypatch.setattr(sft, "FACT_MARK", "\u0000-never-matches")
    assert sft.run_probe(root) == 1


def test_probe_requires_fidelity_dir(sft, tree):
    root = tree({"notes.md": "空树\n"})
    assert sft.run_probe(root) == 2


# ----------------------------------------------------------------- CLI
def test_usage_error_exit_2(sft, tmp_path):
    assert sft.main(["--root", str(tmp_path / "nope")]) == 2
