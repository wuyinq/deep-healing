#!/usr/bin/env python3
"""IP 边界扫描器（M5.1 r2 / S1~S5 + D-4/D-6）：把「逐字搬运原著正文段落」从**声称**变成**可复跑判据**。

方向（`pm/CHG-20260923-009` §0 / 设计 v2）：DeepHealing 是《我的治愈系游戏》的**内部 1:1 复刻**，
**原著人物 / 名称 / 情节 / 世界规则是核心依据，不是禁区**。判据从「拦原著内容」翻转为
「要求原著内容命中」—— 反向那一半在 `v0_skeleton/tools/scan_fidelity_terms.py`（机制词必须命中）。

本扫描器只保留**两条**模式（S1~S5 收敛）：
  1. `jump_scare` —— 呈现选择，**不是** IP 约束（S3 保留原样）；
  2. `verbatim_body_paragraph` —— **D-4 规则**：引号内（`“”` 与 `「」` 都算）满足**任一**：
     (a) CJK ≥ 60；或 (b) CJK ≥ 24 且含 ≥2 个句末/分句标点（。！？；）。
     用于区分「逐字搬运正文段落」与「技术性短引文」。
**已删除的模式（不得回归）**：`gore_lexicon` / `monster_lexicon` / `novel_title_reference` /
`chapter_reference` / `verbatim_quote_marks` ⇒ 书名《…》/ 章节号 / 技术性短引文**不再判红**（S5 解禁）。

豁免（D-6，v2 收紧；Raven C-2 两侧对照后修订）：
  - `verbatim_body_paragraph` **不可豁免** —— 内容判据不得被任何白名单吃掉；
  - 声明站点机制**只对 `jump_scare` 生效**，且**同一行**必须含显式哨兵 `IP-BOUNDARY-DECLARATION`
    （取代 v1 的词法判据 `零|不得|禁止|...`：词法判据实测可被「把正文段放进含禁令词的同一行」绕过）；
  - 自排除**只允许判据载体自身**（文件名 `scan_ip_boundary.py` + 标记 `E_IP_BOUNDARY_SELFPROOF`），
    **禁止目录级豁免**（Raven L-4：同名文件级豁免是已知残余面，单测里显式声明）。

`--probe`（Raven M-8 修正）：**逐模式**各注入一条**运行时拼接构造**的探针（不逐字落盘），
要求**每条模式各自**被其对应探针行命中，且移除后回到基线 ⇒ 三者都成立才 exit 0。
⇒ 「零命中」不再是零命中能力的绿命令。

用法（workdir = `02_source`）：
    python3 v0_skeleton/tools/scan_ip_boundary.py --root .
    python3 v0_skeleton/tools/scan_ip_boundary.py --root . --probe

退出码：0 = 干净（或自证成立）；1 = 有未豁免命中 / 自证不成立；2 = 用法错误。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

# 扫描面：交付树里的文本交付物（二进制/生成残渣不扫）。
# v2（Raven 旁路 8 / C-3）：`.log` / `.out` / `.tsv` / `.csv` 也纳入 —— 它们正是自测读数与
# 抽取中间物的形态，旧后缀面让正文落在这些后缀里**完全隐形**。
TEXT_SUFFIXES = {
    ".json", ".md", ".txt", ".py", ".js", ".mjs", ".ts", ".sh", ".sql",
    ".yaml", ".yml", ".html", ".css", ".log", ".out", ".tsv", ".csv",
}
SKIP_DIRS = {"node_modules", "__pycache__", ".pytest_cache", "dist", ".build", ".venv", "runtime"}

# D-4 规则阈值（设计 v2 §5.3 / D-4；F-18 定标）
D4_LONG_CJK = 60      # 引号内 CJK ≥ 60 ⇒ 判红
D4_MIN_CJK = 24       # 引号内 CJK ≥ 24 且 ≥ 2 个句末/分句标点 ⇒ 判红
SENT_PUNCT = "。！？；"
QUOTE_PAIRS = (("\u201c", "\u201d"), ("\u300c", "\u300d"))  # “” 与 「」

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
JUMP_SCARE_RE = re.compile(r"[Jj]ump\s*[Ss]care|惊吓镜头|突然袭击镜头")

# IP 边界模式（**逐条给名字**，便于归因）；模式表只剩 2 条（S1/S2/S5 删除的 5 条不得回归）。
PATTERN_NAMES: tuple[str, ...] = ("jump_scare", "verbatim_body_paragraph")

# **唯一可豁免的模式**（D-6）：内容判据 `verbatim_body_paragraph` 永不进白名单。
EXEMPTABLE_PATTERN = "jump_scare"

# **声明站点**（逐条给理由）。注意：站点本身不再构成豁免 —— 还必须**同一行**含显式哨兵。
DECLARATION_SITES: dict[str, str] = {
    "worldview.schema.json":
        "schema 的 `$comment` 是本项目的**保真度与边界声明**行（不是内容）",
    "art-bible.md":
        "art-bible 的**保真度声明**行（只豁免该行；其余行照常判红）",
}

# **显式哨兵**（取代 v1 的词法判据 PROHIBITION_LINE）：声明行必须逐字含此串。
DECLARATION_SENTINEL = "IP-BOUNDARY-DECLARATION"

PROBE_FILENAME = "ip-boundary-probe.txt"

# **自排除**：判据载体本身必须逐字包含被检词（否则无从自证命中能力）。
# 用「文件名 + 自身独有标记」识别 —— 这样**副本**里的扫描器（如 `--probe` 的临时树、
# 负例的整树副本）同样被排除，判据不依赖绝对路径。
SCANNER_FILENAME = "scan_ip_boundary.py"
SELF_EXCLUDE_MARKER = "E_IP_BOUNDARY_SELFPROOF"

# 探针**词元**（运行时拼接；**不逐字落盘**成可命中形态）
PROBE_BODY_PARTS: tuple[str, ...] = (
    "本探针为", "运行时", "拼接构造", "的合成中文", "长串", "不取自", "任何原著", "正文",
    "仅用于", "验证判据", "是否具备", "命中能力", "且不落盘", "长度需超过", "六十个汉字",
    "否则无法", "触发引号内", "长段规则", "合成内容", "与任何作品", "均无对应",
)
PROBE_JUMP_PARTS: tuple[str, ...] = ("Jump", " ", "Scare")


def _is_scanner_copy(path: Path) -> bool:
    if path.name != SCANNER_FILENAME:
        return False
    try:
        return SELF_EXCLUDE_MARKER in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def _iter_text_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if _is_scanner_copy(path):
            continue  # **自排除**：判据载体必须包含被检词，不走白名单；**不做目录级豁免**
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


# ----------------------------------------------------------------- D-4 规则
def cjk_count(text: str) -> int:
    return len(CJK_RE.findall(text))


def quoted_segments(line: str) -> list[str]:
    """返回行内所有引号段（`“…”` 与 `「…」` 两套）。"""
    out: list[str] = []
    for opener, closer in QUOTE_PAIRS:
        start = 0
        while True:
            i = line.find(opener, start)
            if i < 0:
                break
            j = line.find(closer, i + 1)
            if j < 0:
                break
            out.append(line[i + 1:j])
            start = j + 1
    return out


def d4_hit(segment: str) -> bool:
    """D-4 规则：CJK ≥60，或 CJK ≥24 且 ≥2 个句末/分句标点。"""
    n = cjk_count(segment)
    if n >= D4_LONG_CJK:
        return True
    if n >= D4_MIN_CJK:
        return sum(segment.count(p) for p in SENT_PUNCT) >= 2
    return False


# ----------------------------------------------------------------- 模式匹配器
def _match_jump_scare(line: str) -> list[int]:
    return [m.end() - m.start() for m in JUMP_SCARE_RE.finditer(line)]


def _match_verbatim_body_paragraph(line: str) -> list[int]:
    """返回命中段落的 CJK 长度（逐段判定 D-4）。"""
    return [cjk_count(seg) for seg in quoted_segments(line) if d4_hit(seg)]


MATCHERS = {
    "jump_scare": _match_jump_scare,
    "verbatim_body_paragraph": _match_verbatim_body_paragraph,
}


def scan(root: Path) -> list[dict]:
    """返回命中列表（每条含 file / line / pattern / length / whitelisted / reason）。

    **豁免判定（D-6）**：`whitelisted` 当且仅当 ① 模式是唯一可豁免的 `jump_scare`；
    ② 命中落在声明站点内；③ **同一行**含显式哨兵 `IP-BOUNDARY-DECLARATION`。
    任何 `verbatim_body_paragraph` 命中 ⇒ 一律 `unwhitelisted`（不可豁免）。
    """
    hits: list[dict] = []
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root).as_posix()
        site_reason = DECLARATION_SITES.get(rel)
        for number, line in enumerate(text.splitlines(), start=1):
            for name in PATTERN_NAMES:
                for length in MATCHERS[name](line):
                    exempt = (
                        name == EXEMPTABLE_PATTERN
                        and site_reason is not None
                        and DECLARATION_SENTINEL in line
                    )
                    reason = (
                        f"{site_reason}；且**同一行**含哨兵 `{DECLARATION_SENTINEL}` ⇒ 行级豁免"
                        if exempt else None
                    )
                    hits.append({"file": rel, "line": number, "pattern": name,
                                 "length": length, "whitelisted": exempt, "reason": reason})
    return hits


# ----------------------------------------------------------------- 探针自证
def probe_payload() -> dict[str, str]:
    """逐模式探针：每模式一条**运行时拼接**的探针行（不逐字落盘）。"""
    body = "".join(PROBE_BODY_PARTS)
    if cjk_count(body) < D4_LONG_CJK:  # 构造必须足以触发 D-4 的 (a) 支
        raise AssertionError("probe body too short to trigger D-4")
    return {
        "jump_scare": "".join(PROBE_JUMP_PARTS),
        "verbatim_body_paragraph": "\u201c" + body + "\u201d",
    }


def _probe_self_proof(root: Path, baseline: list[dict]) -> dict:
    """自证：临时树注入**逐模式**探针 ⇒ 每条模式各自命中；移除 ⇒ 回到基线（**不写交付面**）。"""
    tmp = Path(tempfile.mkdtemp(prefix="ip-boundary-probe-"))
    try:
        shutil.copytree(root, tmp / "tree", dirs_exist_ok=False)
        target = tmp / "tree" / PROBE_FILENAME
        payload = probe_payload()
        lines = [payload[name] for name in PATTERN_NAMES]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        injected = scan(tmp / "tree")
        # **逐模式归因**：第 i 条模式必须被探针文件第 i 行命中（M-8：模式无关的自证不算自证）
        per_pattern: dict[str, bool] = {}
        for index, name in enumerate(PATTERN_NAMES, start=1):
            per_pattern[name] = any(
                hit["pattern"] == name and hit["file"] == PROBE_FILENAME and hit["line"] == index
                for hit in injected
            )
        target.unlink()
        after_removal = scan(tmp / "tree")
        restored = sorted((hit["file"], hit["line"], hit["pattern"]) for hit in after_removal) \
            == sorted((hit["file"], hit["line"], hit["pattern"]) for hit in baseline)
        return {
            "probe_file": PROBE_FILENAME,
            "probe_lines": {name: index for index, name in enumerate(PATTERN_NAMES, start=1)},
            "per_pattern_detected": per_pattern,
            "probe_patterns_detected": sorted(n for n, ok in per_pattern.items() if ok),
            "probe_detected": all(per_pattern.values()),
            "removed_restores_baseline": restored,
            "baseline_hits": len(baseline),
            "injected_hits": len(injected),
            "tmp_root": str(tmp),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scan_ip_boundary.py")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--probe", action="store_true", help="自证模式：逐模式注入探针必须命中，移除后回到基线")
    # M5.1 r2.6（PM m5-08 §三.5）：门禁自证项专用入口 —— 只跑探针、**不扫真实树**。
    #   隔离面声明：探针树 = **空的**临时目录（不 copytree 真实 root）⇒ 基线恒 0 命中；
    #   注入 ⇒ 逐模式命中；移除 ⇒ 回 0 ⇒ self_proof_ok 与树状态解耦。
    parser.add_argument("--probe-only", action="store_true",
                        help="只跑逐模式自证探针（隔离空临时树；不扫真实树）")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"E_SCAN_USAGE: not a directory: {root}", file=sys.stderr)
        return 2

    if args.probe_only:
        with tempfile.TemporaryDirectory(prefix="ip-boundary-probe-only-") as isolated:
            proof = _probe_self_proof(Path(isolated), [])
        report = {
            "probe_only": True,
            "probe_tree": "isolated_empty_tempdir",
            "patterns": list(PATTERN_NAMES),
            "self_proof": proof,
            "self_proof_ok": bool(proof["probe_detected"] and proof["removed_restores_baseline"]),
        }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if report["self_proof_ok"] else 1

    hits = scan(root)
    unwhitelisted = [hit for hit in hits if not hit["whitelisted"]]
    report: dict = {
        "root": str(root),
        "patterns": list(PATTERN_NAMES),
        "exemptable_patterns": [EXEMPTABLE_PATTERN],
        "declaration_sentinel": DECLARATION_SENTINEL,
        "d4_rule": {"long_cjk": D4_LONG_CJK, "min_cjk": D4_MIN_CJK, "sent_punct": SENT_PUNCT},
        "text_suffixes": sorted(TEXT_SUFFIXES),
        "total_hits": len(hits),
        "whitelisted_hits": len(hits) - len(unwhitelisted),
        "unwhitelisted_hits": len(unwhitelisted),
        "unwhitelisted": unwhitelisted,
    }
    if args.probe:
        proof = _probe_self_proof(root, hits)
        report["self_proof"] = proof
        report["self_proof_ok"] = bool(proof["probe_detected"] and proof["removed_restores_baseline"])
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))

    if unwhitelisted:
        for hit in unwhitelisted:
            # 只打 `file:line:pattern:length` —— **不打命中行文本**（C-3：判据自身不得把正文抄进交付面）
            print(f"E_IP_BOUNDARY: {hit['file']}:{hit['line']}:{hit['pattern']}:{hit['length']}",
                  file=sys.stderr)
        return 1
    if args.probe and not report["self_proof_ok"]:
        print("E_IP_BOUNDARY_SELFPROOF: 逐模式探针未被全部命中或移除后未回到基线"
              "（扫描器可能是零命中绿命令）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
