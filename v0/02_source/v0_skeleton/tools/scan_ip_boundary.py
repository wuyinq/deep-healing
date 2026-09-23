#!/usr/bin/env python3
"""IP 边界扫描器（R2 / F12）：把「自研、不引用他人作品」从**声称**变成**可复跑判据**。

背景（Raven M3 观察）：R1 的 IP 扫描探针只存在于 `/tmp`，交付树里**没有判据载体** ——
唯一命中是 `worldview.schema.json` 的 `$comment` **自命中**（它自己写了「零血腥 / 怪物 / Jump Scare」
这条**禁令**）。于是「IP 边界干净」既不可复跑，也分不清「真干净」与「扫描器没命中能力」。

判据形态：
  1. 逐行扫描 `--root`（默认 = 本脚本所在交付树 `02_source`）下的**文本交付物**；
  2. 命中**行级豁免**（`DECLARATION_SITES` 内的**禁令行**，逐条给理由）之外的任何模式 ⇒ 打印命中并 **exit 1**；
     R3 / G4 修正：豁免粒度从「文件 × 模式」降为**行**（同一行必须含禁令词），且扫描器自身改用自排除；
  3. `--probe` **自证模式**：把探针文本注入一个临时树（`/tmp`，**绝不写交付面**）⇒ 必须命中；
     移除后重扫 ⇒ 必须回到基线命中数。三者都成立才 exit 0。
     ⇒ 「零命中」不再是零命中能力的绿命令。

用法（workdir = `02_source`）：
    python3 v0_skeleton/tools/scan_ip_boundary.py --root .
    python3 v0_skeleton/tools/scan_ip_boundary.py --root . --probe

退出码：0 = 干净（或自证成立）；1 = 有未白名单命中 / 自证不成立；2 = 用法错误。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

# 扫描面：交付树里的文本交付物（二进制/生成残渣不扫）
TEXT_SUFFIXES = {".json", ".md", ".txt", ".py", ".js", ".mjs", ".ts", ".sh", ".sql", ".yaml", ".yml", ".html", ".css"}
SKIP_DIRS = {"node_modules", "__pycache__", ".pytest_cache", "dist", ".build", ".venv", "runtime"}

# IP 边界模式（**逐条给名字**，便于归因）
PATTERNS: tuple[tuple[str, str], ...] = (
    ("novel_title_reference", r"《[^》\n]{1,40}》"),
    ("chapter_reference", r"第[一二三四五六七八九十百零〇0-9]{1,4}[章回节]"),
    ("verbatim_quote_marks", r"[“][^”\n]{8,}[”]"),
    ("gore_lexicon", r"血腥|血泊|内脏|尸体|肢解"),
    ("monster_lexicon", r"怪物|异形|鬼影|丧尸"),
    ("jump_scare", r"[Jj]ump\s*[Ss]care|惊吓镜头|突然袭击镜头"),
)

# **白名单的粒度 = 行**（R3 / G4 修正）。
#
# 修复前的形态是「文件 × 模式」整份豁免：`art-bible.md` / `worldview.schema.json` 上**任何**
# 真实越界内容都会被白名单吃掉（Raven r2 R2-M4 实测：往 art-bible 追加一句真越界 ⇒ `exit 0`）。
# 现在两条**同时**成立才豁免：
#   ① 命中落在**声明站点**（下面这张表，逐条给理由）；
#   ② **同一行**里出现禁令词（`零/不得/禁止/…`）—— 即这一行本身就是在**声明禁令**，不是内容。
# 扫描器**自身**不再走白名单，改由 `_iter_text_files` 的**自排除**跳过（判据载体必须包含被检词）。
PROHIBITION_LINE = re.compile(r"零|不得|禁止|禁用|禁令|no\s|not\s|zero")

DECLARATION_SITES: dict[str, str] = {
    "worldview.schema.json":
        "schema 的 $comment 逐字写「零血腥 / 怪物 / Jump Scare」—— 它是**禁令声明**，不是内容",
    "art-bible.md":
        "art-bible 的**禁令行**（只豁免同一行内含禁令词的那一行；其余行照常判红）",
}

PROBE_TEXT = "IP 探针（R2 / F12 自证）：第 3 章 与《某某传》里的怪物一起血腥登场，Jump Scare。"
PROBE_FILENAME = "ip-boundary-probe.txt"

# **自排除**（R3 / G4）：判据载体本身必须逐字包含被检词（否则无从自证命中能力）。
# 用「文件名 + 自身独有标记」识别 —— 这样**副本**里的扫描器（如 `--probe` 的临时树、
# 负例的整树副本）同样被排除，判据不依赖绝对路径。
SCANNER_FILENAME = "scan_ip_boundary.py"
SELF_EXCLUDE_MARKER = "E_IP_BOUNDARY_SELFPROOF"


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
            continue  # **自排除**（R3 / G4）：判据载体必须包含被检词，不走白名单
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def scan(root: Path) -> list[dict]:
    """返回命中列表（每条含 file / line / pattern / text / whitelisted / reason）。

    **行级豁免**（R3 / G4）：只有当命中所在**行**同时满足「在声明站点内」+「该行含禁令词」时才豁免；
    否则一律计入 `unwhitelisted` ⇒ 往 `art-bible.md` 追加一句真越界**必须**判红。
    """
    hits: list[dict] = []
    compiled = [(name, re.compile(pattern)) for name, pattern in PATTERNS]
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root).as_posix()
        site_reason = DECLARATION_SITES.get(rel)
        for number, line in enumerate(text.splitlines(), start=1):
            for name, pattern in compiled:
                if not pattern.search(line):
                    continue
                line_is_declaration = site_reason is not None and PROHIBITION_LINE.search(line) is not None
                reason = (f"{site_reason}；且**同一行**含禁令词 ⇒ 行级豁免" if line_is_declaration else None)
                hits.append({"file": rel, "line": number, "pattern": name,
                             "text": line.strip()[:160], "whitelisted": reason is not None,
                             "reason": reason})
    return hits


def _probe_self_proof(root: Path, baseline: list[dict]) -> dict:
    """自证：临时树注入探针 ⇒ 必命中；移除 ⇒ 回到基线（**不写交付面**）。"""
    tmp = Path(tempfile.mkdtemp(prefix="ip-boundary-probe-"))
    try:
        shutil.copytree(root, tmp / "tree", dirs_exist_ok=False)
        target = tmp / "tree" / PROBE_FILENAME
        target.write_text(PROBE_TEXT + "\n", encoding="utf-8")
        injected = scan(tmp / "tree")
        new_hits = [hit for hit in injected if not any(hit == base for base in baseline)]
        detected = [hit["pattern"] for hit in new_hits if hit["file"] == PROBE_FILENAME]
        target.unlink()
        after_removal = scan(tmp / "tree")
        restored = sorted((hit["file"], hit["line"], hit["pattern"]) for hit in after_removal) \
            == sorted((hit["file"], hit["line"], hit["pattern"]) for hit in baseline)
        return {
            "probe_file": PROBE_FILENAME,
            "probe_patterns_detected": sorted(set(detected)),
            "probe_detected": bool(detected),
            "removed_restores_baseline": restored,
            "baseline_hits": len(baseline),
            "injected_hits": len(injected),
            "tmp_root": str(tmp),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scan_ip_boundary.py")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--probe", action="store_true", help="自证模式：注入探针必须命中，移除后回到基线")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"E_SCAN_USAGE: not a directory: {root}", file=sys.stderr)
        return 2

    hits = scan(root)
    unwhitelisted = [hit for hit in hits if not hit["whitelisted"]]
    report: dict = {
        "root": str(root),
        "patterns": [name for name, _ in PATTERNS],
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
            print(f"E_IP_BOUNDARY: {hit['file']}:{hit['line']} [{hit['pattern']}] {hit['text']}", file=sys.stderr)
        return 1
    if args.probe and not report["self_proof_ok"]:
        print("E_IP_BOUNDARY_SELFPROOF: 探针未被命中或移除后未回到基线（扫描器可能是零命中绿命令）",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
