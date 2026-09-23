#!/usr/bin/env python3
"""保真度反向判据（M5.1 r2 / S 新增项 · 设计 v2 §5.4）：原著机制词**必须命中**。

方向（`pm/CHG-20260923-009` §0）：DeepHealing 是《我的治愈系游戏》的**内部 1:1 复刻**，
原著人物 / 名称 / 情节 / 世界规则是**核心依据**。`scan_ip_boundary.py` 管的是「不许逐字搬运正文段落」，
本脚本管的是**另一半**：**原著机制词必须真的落在出处表事实行上** —— 防止世界再次退化成「自研近似」。

两面（D-5，v2 钉死口径；Raven C-4 后修订）：
  - `--face register`（**本轮门禁**，`enforced: true`）
      扫描根 = `<root>/fidelity/*.md`（六册，**不递归**；`fidelity/tools/**` 因此天然不在面内）。
      词表（architect 钉死，8 词）：楼长 / 管理者 / 友善度 / 怨念 / 诅咒物 / 怪谈 / 隐藏任务 / 属性面板
        （r1.6 替换：`任务分级` → `隐藏任务`；原词 L0 0 命中，新词 L0 172 命中 —— 见 `TERMS` 上方注释）。
      下界（architect 钉死）：**每词 ≥ 1 次命中**，且命中必须落在**事实行**上才计数。
      事实行谓词（**与 `fidelity_lint.py` 的 R1 同源** —— Raven R-3）：行以 `- [` 开头**且**含 ` || anchor: `；
      含该子串但不以 `- [` 开头的说明行 / 标题行**不计数**。
      计数面（Raven R-4）：只认**事实文本段**（`- [` 之后、第一个 `||` 之前）里出现的词；
      **同一事实行最多计 2 个目标词**（按词表顺序取前 2），超出不计并在报告里给 `capped_lines` 读数。
  - `--face pack`（**本轮测量，`enforced: false`**）
      扫 `<root>/v0_skeleton/districts/**`，只出读数；标 `NOT_ENFORCED_UNTIL_M5_2`，**不参与退出码**
      （本轮内容未动，F-4 实测 0 命中；把它设成门禁等价于把「内容对齐」提前到本轮）。

词表调整规则（只允许**移除**）：不得静默改词表、不得降低已有词的下界；移除前必须先给出
「该词在可及来源上的命中扫描读数」并逐词登记，由 architect 复核。

`--probe`：**逐词**把词表命中词注入临时树的事实行 ⇒ 该词必须计数；注入**含锚点子串但不以 `- [` 开头**的
说明行 ⇒ **不得**计数（R-3 覆盖该变体）；注入**一行词沙拉** ⇒ 至多 2 词 +1（R-4）；全部移除后必须回基线。

用法（workdir = `02_source`）：
    python3 v0_skeleton/tools/scan_fidelity_terms.py --root . [--face register|pack|all] [--probe]

退出码：0 = 门禁面达标；1 = 未达标；2 = 用法错误。报告逐词给 `命中数 / 下界`。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

# **词表（architect 钉死，8 词）** —— 只允许移除/替换，不允许静默改写或降低下界。
# M5.1 r1.6：`任务分级` **替换**为 `隐藏任务`（Sentinel MED-2 / 03 日志 §M5.1-r1.6 R3）——
#   原词在 L0 全本 **0 命中**（全书 75,596 行 / 归一化 CJK 2,910,231）⇒ 该词上的判据只能被
#   「我们自己写了这个词」满足（同义反复），对「原著机制词必须命中」无牙。
#   新词 L0 命中 **172**（同族候选：`普通任务` 30 / `任务难度` 10 / `任务等级` 6 / `管理者等级` 1）；
#   冻结六册中 `隐藏任务` 已有事实行命中（`02-mechanism-facts.md` MEC-04、`04-name-register.md` NAM-09）
#   ⇒ 替换后 register 面逐词「命中数 / 下界」仍全部达标（8/8）。词表仍为 8 词。
TERMS: tuple[str, ...] = ("楼长", "管理者", "友善度", "怨念", "诅咒物", "怪谈", "隐藏任务", "属性面板")
# **下界（architect 钉死）**：每词 ≥1 次**事实行**命中。
FLOOR = 1

# 事实行谓词（**与 `fidelity_lint.py` 的 R1 同源** —— Raven R-3）：
#   行必须以 `- [` 开头**且**含 ` || anchor: `；含子串但不以 `- [` 开头的说明行不计数。
FACT_PREFIX = "- ["
FACT_MARK = " || anchor: "
# 同一事实行最多计 2 个目标词（Raven R-4：堵「一行词沙拉刷 8 词」）。
MAX_TERMS_PER_LINE = 2

PACK_STATUS = "NOT_ENFORCED_UNTIL_M5_2"
PACK_SUFFIXES = {".json", ".md", ".txt", ".tsv", ".csv", ".yaml", ".yml"}


# ----------------------------------------------------------------- 扫描
def register_files(root: Path) -> list[Path]:
    """register 面扫描根：`<root>/fidelity/*.md` —— **不递归**（`fidelity/tools/**` 不在面内）。"""
    fidelity = root / "fidelity"
    if not fidelity.is_dir():
        return []
    return sorted(p for p in fidelity.glob("*.md") if p.is_file())


def pack_files(root: Path) -> list[Path]:
    """pack 面扫描根：`<root>/v0_skeleton/districts/**`（递归）。"""
    districts = root / "v0_skeleton" / "districts"
    if not districts.is_dir():
        return []
    return sorted(p for p in districts.rglob("*")
                  if p.is_file() and p.suffix.lower() in PACK_SUFFIXES)


def is_fact_line(line: str) -> bool:
    """事实行谓词：**与 lint R1 同源**（`- [` 行首 + 含 ` || anchor: `）。"""
    return line.startswith(FACT_PREFIX) and FACT_MARK in line


def fact_text_segment(line: str) -> str:
    """事实文本段 = `- [` 之后、第一个 `||` 之前（锚点 / mirror 元数据不计入词命中）。"""
    seg = line.split(FACT_PREFIX, 1)[1]
    return seg.split("||", 1)[0]


def count_register(root: Path) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """返回 (逐词命中数, 逐词所属事实行数, 读数)。

    读数含 `fact_lines_total` 与 `capped_lines`（词数 > `MAX_TERMS_PER_LINE` 的事实行数 ⇒
    超出部分**不计**，避免一行词沙拉把 8 词全部刷达标）。
    """
    hits = {term: 0 for term in TERMS}
    fact_lines = {term: 0 for term in TERMS}
    total_fact_lines = 0
    capped_lines = 0
    for path in register_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            if not is_fact_line(line):
                continue
            total_fact_lines += 1
            seg = fact_text_segment(line)
            present = [t for t in TERMS if t in seg]
            if len(present) > MAX_TERMS_PER_LINE:
                capped_lines += 1
            for term in present[:MAX_TERMS_PER_LINE]:
                n = seg.count(term)
                if n:
                    hits[term] += n
                    fact_lines[term] += 1
    readings = {"fact_lines_total": total_fact_lines, "capped_lines": capped_lines,
                "max_terms_per_line": MAX_TERMS_PER_LINE}
    return hits, fact_lines, readings


def count_pack(root: Path) -> dict[str, int]:
    """pack 面只出读数（不做事实行约束 —— 内容包不是出处表）。"""
    hits = {term: 0 for term in TERMS}
    for path in pack_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for term in TERMS:
            hits[term] += text.count(term)
    return hits


def face_report(name: str, enforced: bool, scope: str, hits: dict[str, int],
                fact_lines: dict[str, int] | None = None, extra: dict | None = None) -> dict:
    per_term = {}
    for term in TERMS:
        entry = {"hits": hits[term], "floor": FLOOR}
        if fact_lines is not None:
            entry["fact_lines"] = fact_lines[term]
            entry["pass"] = hits[term] >= FLOOR
        per_term[term] = entry
    report = {
        "face": name,
        "enforced": enforced,
        "scope": scope,
        "terms": list(TERMS),
        "floor": FLOOR,
        "per_term": per_term,
        "hits_total": sum(hits.values()),
    }
    if enforced:
        met = sum(1 for term in TERMS if hits[term] >= FLOOR)
        report["terms_met"] = met
        report["terms_total"] = len(TERMS)
        report["pass"] = met == len(TERMS)
    if extra:
        report.update(extra)
    return report


# ----------------------------------------------------------------- 探针
def _baseline_register(root: Path) -> dict[str, int]:
    hits, _lines, _readings = count_register(root)
    return hits


def run_probe(root: Path) -> int:
    """逐词自证 + R-3/R-4 两条残余面的负向对照。

    ① 注入事实行 ⇒ 该词必须计数；
    ② 注入**含 ` || anchor: ` 子串但不以 `- [` 开头**的说明行 ⇒ **不得**计数（R-3 覆盖该变体）；
    ③ 注入**一行词沙拉**（8 词并列 + 合法锚点）⇒ 至多 2 个词 +1，**不得** 8 词全部达标（R-4）；
    ④ 全部移除 ⇒ 回基线。
    """
    ok = True
    tmp = tempfile.mkdtemp(prefix="fidelity-terms-probe-")
    try:
        books = register_files(root)
        if not books:
            print(f"E_FIDELITY_TERMS_USAGE: no fidelity/*.md under {root}", file=sys.stderr)
            return 2
        tmp_root = Path(tmp) / "root"
        (tmp_root / "fidelity").mkdir(parents=True)
        for path in books:
            shutil.copy(path, tmp_root / "fidelity" / path.name)
        baseline = _baseline_register(tmp_root)
        target = tmp_root / "fidelity" / books[0].name
        original = target.read_text(encoding="utf-8")
        results = []
        for term in TERMS:
            fact_line = f"- [PROBE-01] 探针事实行：{term} || anchor: UNVERIFIED || reason: 探针\n"
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(fact_line)
            after_fact = _baseline_register(tmp_root)
            detected = after_fact[term] > baseline[term]
            # 移除注入 ⇒ 该词单独回基线
            target.write_text(original, encoding="utf-8")
            # 非事实行注入（**含锚点子串、但不以 `- [` 开头**）⇒ 不得计数（R-3）
            note_line = f"探针说明行（含锚点子串、非事实行）：{term} || anchor: 语法示例\n"
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(note_line)
            after_note = _baseline_register(tmp_root)
            note_ignored = after_note[term] == baseline[term]
            target.write_text(original, encoding="utf-8")
            results.append({"term": term, "fact_line_detected": detected,
                            "non_fact_line_ignored": note_ignored})
            ok = ok and detected and note_ignored
        # ③ 词沙拉（R-4 负向对照）：一行 8 词 + 合法锚点 ⇒ 至多 2 个词 +1
        salad = "- [PROBE-02] " + "、".join(TERMS) + " || anchor: UNVERIFIED || reason: 探针词沙拉\n"
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(salad)
        after_salad = _baseline_register(tmp_root)
        salad_terms = [t for t in TERMS if after_salad[t] > baseline[t]]
        salad_capped = len(salad_terms) <= MAX_TERMS_PER_LINE
        results.append({"case": "word_salad_line_capped", "terms_incremented": salad_terms,
                        "max_terms_per_line": MAX_TERMS_PER_LINE, "capped": salad_capped})
        ok = ok and salad_capped
        target.write_text(original, encoding="utf-8")
        back = _baseline_register(tmp_root)
        back_to_baseline = back == baseline
        ok = ok and back_to_baseline
        print(json.dumps({"probe": results, "baseline": baseline, "after_removal": back,
                          "back_to_baseline": back_to_baseline, "probe_ok": ok},
                         ensure_ascii=False, sort_keys=True))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


# ----------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scan_fidelity_terms.py")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--face", choices=("register", "pack", "all"), default="all")
    parser.add_argument("--probe", action="store_true",
                        help="逐词自证：事实行注入必须计数，非事实行注入不得计数，移除后回基线")
    # M5.1 r2.6（PM m5-08 §三.5）：门禁自证项专用入口 —— 只跑探针、**不扫真实树**。
    #   隔离面声明：探针树 = 运行时构造的**合成** `<tmp>/fidelity/*.md`（只含一条合法基线事实行，
    #   不含任何目标词）⇒ probe_ok 与树状态解耦。
    parser.add_argument("--probe-only", action="store_true",
                        help="只跑逐词自证探针（合成临时树；不扫真实树）")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"E_FIDELITY_TERMS_USAGE: not a directory: {root}", file=sys.stderr)
        return 2

    if args.probe_only:
        with tempfile.TemporaryDirectory(prefix="fidelity-terms-probe-only-") as isolated:
            synth = Path(isolated)
            (synth / "fidelity").mkdir(parents=True, exist_ok=True)
            (synth / "fidelity" / "00-source-manifest.md").write_text(
                "- [PROBE-00] 合成基线事实行（不含任何目标词） || anchor: UNVERIFIED || reason: 自证夹具\n",
                encoding="utf-8")
            return run_probe(synth)

    faces: dict[str, dict] = {}
    if args.face in ("register", "all"):
        hits, fact_lines, readings = count_register(root)
        faces["register"] = face_report(
            "register", True, "fidelity/*.md（六册，不递归；fidelity/tools/** 不在面内）",
            hits, fact_lines, extra={"predicate": "fact_line = line.startswith('- [') and ' || anchor: ' in line",
                                     "count_face": "fact_text_segment（'||' 之前）",
                                     **readings})
    if args.face in ("pack", "all"):
        hits = count_pack(root)
        faces["pack"] = face_report(
            "pack", False, "v0_skeleton/districts/**", hits,
            extra={"status": PACK_STATUS,
                   "note": "本轮内容未动（F-4 实测 0 命中）⇒ 只出读数，不参与退出码"})

    report = {
        "root": str(root),
        "terms": list(TERMS),
        "floor": FLOOR,
        "faces": faces,
        "exit_basis": "enforced_faces_only",
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))

    failed = [name for name, face in faces.items() if face["enforced"] and not face.get("pass")]
    if failed:
        for name in failed:
            print(f"E_FIDELITY_TERMS: face={name} 未达标（逐词命中/下界见 JSON）", file=sys.stderr)
        return 1
    if args.probe:
        prc = run_probe(root)
        if prc != 0:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
