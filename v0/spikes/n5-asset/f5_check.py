#!/usr/bin/env python3
"""`AC-F-5a/b/c/d/e` 的机器判据：**既有判据面零改动（纯加法）**的自证工具。

运行（workdir = 仓库根；**只读**交付源码；产物写独立输出目录）：

    python3 v0/spikes/n5-asset/f5_check.py --json-out v0/spikes/n5-asset/readback/f5_report.json

判据：
  F-5a  既有判据**名集不变**：`git show <frozen-ref>:…scene_assert.mjs` 的 `^check('…'` 名集
        ⊆ 当前名集，**消失数 == 0**
  F-5b  既有**期望值常量集合只增不减**：`scene_assert.mjs`（JS）与 `verify_specs.sh`（bash）
        两侧**都**用**显式正则**抽取常量字面量（数字 `toFixed(6)` 规范化 + 单/双引号字符串字面量）。
        **口径更正（N5-r2 / B-3）**：本工具**没有**用 AST —— r1 的 docstring 自称「用 TypeScript
        Compiler API、由 `--ast-helper` 子进程执行」，那两句都不成立（`argparse` 只有
        `--json-out` / `--selftest`，实现是 `JS_LITERAL` 正则）。PM C4 的原文是
        「`scene_assert.mjs` 用 AST 字面量集合；`verify_specs.sh` 用显式正则白名单」。
        本轮**如实改写为事实口径**并**上抛**（不假装满足 C4 的 AST 要求，也不悄悄放宽任何东西）：
        正则口径对「模板字面量 / 十六进制 / 科学计数法 / 注释内数字」的抽取与 AST 不同，
        覆盖面**小于** C4 声明；但「既有期望值只增不减」这条**实际由 F-5c 承担**
        （见下方 F-5c 的上下文口径与 §selftest ①②③），F-5b 是**纵深**而非唯一承担者。
  F-5c  **删除行白名单 + 已授权删除登记表**：`git diff --unified=0 <frozen-ref> -- <三个文件>` 的
        每个删除 hunk，其全部 `^-` 行去前缀后必须逐行匹配 ① import（含多行 import 起始/收尾行，
        收尾行以 `,` 或 `}` 结尾）② 注释 ③ 空行；**上下文口径**：该 hunk 必须同时含 `+` 侧 import
        对应行；否则 **FAIL**；其余删除行逐行登记
        （N5-r2 修正：`--- a/<path>` / `+++ b/<path>` 是 diff **文件头**，不是内容行，已显式跳过 ——
          r1 的 `verify_specs.sh` 与 `<frozen-ref>` 逐字节相同 ⇒ 无 hunk，故该解析缺陷当时未暴露。）
        **登记表语义（N5-r3 / REQ-20261011-018）**：白名单三分支之外，`AUTHORIZED_DELETIONS`
        逐条登记**已授权删除**。命中条件 = 删除行 `rstrip()` 后**整行全等** ∧ `file` 相同
        （`rstrip()` 只去**右侧**空白 ⇒ 行首缩进是行身份的一部分）；命中 ⇒ 记入
        `registered_authorized`（**不**入 `problems`，仍留审计）；**未命中 ⇒ 照旧判 FAIL**
        （守卫的牙保留）。登记项在全部 hunk 上一次都没命中 ⇒ 额外记 problem（多登记 = 无效）。
        结构坏（非序列 / 缺字段 / 类型不对 / `authorized_by` 不匹配 / 重复条目）⇒ fail-closed：
        记结构性 problem ⇒ **exit 1**，不得当空登记表放行、不得静默跳过该条。
        ⚠️ **命中 ≠ 判据面未被改动**：被授权的删除**正是判据体行**，本轮只是把它从「未授权删除」
        改判为「**已授权**删除」；「判据面不变」由 **F-5a / F-5b 零问题**承担，**不由**
        `problems == []` 承担。
  F-5d  负对照（在 `/tmp` 副本上做）：① 删一条既有 `check()` ② 改一个期望值
        ③ 整条删一个多行 import ④ 拆一个多行 import（有 `+` 侧对应）⇒ ①②③ **必红**，④ **必须仍绿**
        （N5-r2 新增 ⑤：带 `--- a/` 文件头的纯插入 ⇒ **必须仍绿**，即上面那条解析修正的回归。）
        （N5-r3 新增 ⑥⑦ ⑧ ⑨⑩⑪：registry 的必红/必绿 + fail-closed 退化用例，
         全部用**合成 diff 文本**喂**真实** `parse_hunks` + **真实** `f5c_evaluate`。
         **iter2 r2.1 / Raven M-1**：⑧(a)~(f) 改为**遍历全部 7 条登记行**（每条各跑一组，标签带
         行号 + sha16），并新增 **⑧(g)**（删行 = **非空白前缀 + 登记行** ⇒ 必红）——补上 `endswith`
         一侧的**镜像方向**；原实现只锚 ROW5/ROW7 ⇒ 判别力单向、`endswith` 与「行级特化」两种坏实现裸过。
         **iter2 r2.1 / Raven M-2 ≡ Sentinel F-1**：新增 **⑫**，以 `--json-out` **经真实 `main()`**
         驱动非序列 registry（None / int / 生成器）⇒ 必须 exit 1 ∧ problems ≥ 1 ∧ **审计件仍产出**。）
  F-5e  producer 侧登记（`01d`）的等价性口径：既有判据的**期望值/阈值常量**逐字节不变
        （= F-5b 的「只增不减」在**值**维度上的形态
         —— **承担者更正（N5-r2 / B-6）**：实测由 **F-5c** 承担，`01d §0` 的表述已同步改写）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
FROZEN_REF = "376a9fc4cbac"

FILES = {
    "scene_assert": "v0/02_source/v0_skeleton/web/scripts/scene_assert.mjs",
    "verify_specs": "v0/02_source/verify_specs.sh",
    "verify_asset_provenance": "v0/02_source/v0_skeleton/tools/verify_asset_provenance.py",
}
# F-5c 的**判定文件面**（PM C4 / E-8）；`verify_asset_provenance.py` 是新增件（frozen-ref 下不存在）
F5C_FILE_FACE = [FILES["scene_assert"], FILES["verify_specs"], FILES["verify_asset_provenance"]]

# F-5c 的**已授权删除登记表**（REQ-20261011-018）：每条 = 一次「已授权删除」，**逐条列名**。
#   file          删除行所属文件（必须 ∈ F5C_FILE_FACE）
#   line          删除行 `rstrip()` 后的**完整整行内容**（含行首缩进与行尾 ` \` bash 续行符）
#   authorized_by 授权来源（必须恰为 AUTHORIZED_BY）
#   why           一句话人类说明
# 授权来源：RULING-20261011-016-b §3（r1 的 T1 selfproof 维度扩写 + T2 陈旧文案行）。
# 生成方式：**机械重取**（从本工具自身 `--json-out` 的 `problems` 数组逐行取），
# 每行 sha256 与设计 rev2 §2.3 逐条比对，结果落 `03_artisan_self_test.log` §3。
# 语义：命中 ⇒ 记 `registered_authorized`（不入 problems）；**未命中仍判 FAIL**；
#       一条未命中 ⇒ 额外 problem（多登记 = 无效）—— 陈旧/写错/加宽都会当场红。
AUTHORIZED_BY = "RULING-20261011-016-b §3"

AUTHORIZED_DELETIONS = (
    {"file": 'v0/02_source/verify_specs.sh',
     "line": '  local out raw norm',
     "authorized_by": 'RULING-20261011-016-b §3',
     "why": 'T1 selfproof 三维度：函数体内取退出码/原始输出的局部行被重排'},
    {"file": 'v0/02_source/verify_specs.sh',
     "line": '    OK\\ *)    ok "$label self-proof holds (${norm#OK })" ;;',
     "authorized_by": 'RULING-20261011-016-b §3',
     "why": 'T1 selfproof 三维度：消费退出码的 case 模式行被重排'},
    {"file": 'v0/02_source/verify_specs.sh',
     "line": 'selfproof "schema validator (valid baseline green + 4 invalid red + sampling-legal green)" \\',
     "authorized_by": 'RULING-20261011-016-b §3',
     "why": 'T1 selfproof：schema validator 维度调用行被改写'},
    {"file": 'v0/02_source/verify_specs.sh',
     "line": 'selfproof "AC-10 criteria (revert C1 => single-branch dominance; revert C2+C3 => outdoor collapse)" \\',
     "authorized_by": 'RULING-20261011-016-b §3',
     "why": 'T1 selfproof：AC-10 criteria 维度调用行被改写'},
    {"file": 'v0/02_source/verify_specs.sh',
     "line": 'selfproof "AC-6 identity continuity (positive/negative cases)" \\',
     "authorized_by": 'RULING-20261011-016-b §3',
     "why": 'T1 selfproof：AC-6 identity continuity 维度调用行被改写'},
    {"file": 'v0/02_source/verify_specs.sh',
     "line": 'selfproof "AC-7 admission gate (extra npc / npc without source_facts)" \\',
     "authorized_by": 'RULING-20261011-016-b §3',
     "why": 'T1 selfproof：AC-7 admission gate 维度调用行被改写'},
    {"file": 'v0/02_source/verify_specs.sh',
     "line": '  selfproof "CHR provenance (forged id / UNVERIFIED id)" \\',
     "authorized_by": 'RULING-20261011-016-b §3',
     "why": 'T2 陈旧文案：CHR provenance 调用行被改写'},
)

JS_LITERAL = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])|'([^'\\\n]*)'|\"([^\"\\\n]*)\"")
CHECK_NAME = re.compile(r"^check\('([^']+)'", flags=re.M)

IMPORT_LINE = re.compile(r"^\s*import\b")
IMPORT_TAIL = re.compile(r"^\s*[A-Za-z_$][\w$]*(\s*,\s*[A-Za-z_$][\w$]*)*\s*[,}]?\s*$")
COMMENT_LINE = re.compile(r"^\s*(//|/\*|\*|\*/|#)")


def git_show(ref: str, path: str) -> str | None:
    p = subprocess.run(["git", "-C", str(WS), "show", f"{ref}:{path}"], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def git_diff_u0(ref: str, paths: list[str]) -> str:
    p = subprocess.run(["git", "-C", str(WS), "diff", "--unified=0", ref, "--", *paths],
                       capture_output=True, text=True)
    return p.stdout


def ref_resolvable(ref: str) -> bool:
    """基线提交在**本地**历史里可解析吗（`git rev-parse --verify`）。"""
    p = subprocess.run(["git", "-C", str(WS), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                       capture_output=True, text=True)
    return p.returncode == 0


def baseline_problem(ref: str, resolvable) -> str | None:
    """F-5a/F-5b/F-5c 的**基线可读性**前置（fail-closed）。

    为什么要有它：F-5a/F-5b/F-5c 全部以 `FROZEN_REF` 提交为基线（`git show` / `git diff`）。
    浅克隆（CI 默认 `fetch-depth=1`）里该提交**不存在** ⇒ `git_show` 返回 `None` ⇒ 被判成空串 ⇒
    `frozen=0 current=105 missing=0`：**什么都没比，却报 PASS**（空转通过）。这类「读不到」转绿
    正是门禁最不该有的口子 —— 故在此显式 fail-closed：基线解析不了就记 problem、不许转绿。
    """
    if resolvable(ref):
        return None
    return (f"F-5a/F-5b/F-5c: 基线不可读（FROZEN_REF={ref} 在本仓库不可解析）⇒ fail-closed；"
            f"不得因「没读到」转绿（浅克隆下需 fetch 全 history，见 .github/workflows/verify.yml）")


def js_literals(text: str) -> list[str]:
    out = []
    for m in JS_LITERAL.finditer(text):
        if m.group(1) is not None or m.group(2) is not None:
            out.append(m.group(1) if m.group(1) is not None else m.group(2))
        else:
            out.append(f"{float(m.group(0)):.6f}")
    return sorted(out)


def bash_whitelist_constants(text: str, whitelist: list[str]) -> list[str]:
    """bash 侧：**显式正则白名单**（不做 AST）。抽条件表达式里的数值与字符串字面量。"""
    out = []
    for line in text.split("\n"):
        if any(re.match(w, line) for w in whitelist):
            continue
        for m in re.finditer(r"(?<![\w.])(-?\d+(?:\.\d+)?)(?![\w.])", line):
            out.append(f"{float(m.group(1)):.6f}")
        for m in re.finditer(r"'([^'\\\n]*)'", line):
            out.append(m.group(1))
    return sorted(out)


def parse_hunks(diff_text: str):
    """把 `git diff --unified=0` 切成 hunk：返回 [(path, [lines]), …]。

    N5-r2 修正（真 bug）：r1 把 `--- a/<path>` 文件头也当成 `^-` 删除行 ⇒ 一旦**该文件真的有 hunk**
    （r1 的 `verify_specs.sh` 与 `<frozen-ref>` 逐字节相同 ⇒ 无 hunk，故未暴露）就会误报
    「删除非白名单行」。`--- ` / `+++ ` 是 diff 的**文件头**，不是内容行，必须显式跳过。
    """
    hunks = []
    current = None
    path = None
    for line in diff_text.split("\n"):
        if line.startswith("+++ b/"):
            path = line[6:]
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        if line.startswith("@@"):
            if current is not None:
                hunks.append((path, current))
            current = []
        elif current is not None and (line.startswith("+") or line.startswith("-")):
            current.append(line)
    if current is not None:
        hunks.append((path, current))
    return hunks


def f5c_evaluate(hunks, registry=AUTHORIZED_DELETIONS, complete_face=False):
    """返回 (problems, audit)；`audit` = {registered_deletions, authorized_deletions,
    registry_unused, registry_total}。

    registry = **已授权删除登记表**（`AUTHORIZED_DELETIONS`，默认即真实登记表）：既有白名单三分支
    **先**判（一行不改），走不到白名单的删除行**再**查登记表，命中条件为
    `r.rstrip() == entry["line"] and path == entry["file"]`（**整行全等**；只去右侧空白 ⇒
    行首缩进是行身份的一部分；禁止前缀 / 子串 / `.strip()` / 忽略大小写 / 空白归一化）。
    命中 ⇒ 进 `authorized_deletions`（**不**进 problems）；未命中 ⇒ 照旧进 problems。
    结构坏（非序列 / 缺字段 / 类型不对 / `authorized_by` 不匹配 / 重复条目）⇒ fail-closed：
    记结构性 problem（⇒ exit 1），该条**不**参与命中；不得当空表放行、不得静默跳过。

    `complete_face=True` 表示 `hunks` 是**完整变更面**（`main()` 的真实读数）⇒ 额外判定
    「登记项一次都没命中」并记一条 problem（多登记 = 无效）。合成单-hunk 用例不是变更面
    （它只含一条删除行），若在此判定会把**未被该用例覆盖**的登记项误报成陈旧，故默认 False。
    """
    problems = []
    registered = []
    authorized = []
    registry_unused = []

    # --- registry 结构校验（fail-closed：结构坏 ⇒ 结构性 problem，该条不参与命中）---
    entries = []
    if not isinstance(registry, (tuple, list)):
        problems.append(f"F-5c: AUTHORIZED_DELETIONS 结构非法（非序列）：{type(registry).__name__}")
    else:
        for idx, entry in enumerate(registry):
            bad = None
            if not isinstance(entry, dict):
                bad = f"第 {idx + 1} 条不是映射（{type(entry).__name__}）"
            else:
                for fname in ("file", "line", "authorized_by", "why"):
                    if fname not in entry:
                        bad = f"第 {idx + 1} 条缺字段 {fname!r}"
                        break
                    if not isinstance(entry[fname], str):
                        bad = f"第 {idx + 1} 条字段 {fname!r} 类型不对（{type(entry[fname]).__name__}）"
                        break
                if bad is None and entry["authorized_by"] != AUTHORIZED_BY:
                    bad = f"第 {idx + 1} 条 authorized_by 不匹配：{entry['authorized_by']!r}"
                if bad is None and entry["file"] not in F5C_FILE_FACE:
                    bad = f"第 {idx + 1} 条 file 不在 F5C_FILE_FACE：{entry['file']!r}"
                if bad is None and entry["line"] == "":
                    bad = f"第 {idx + 1} 条 line 为空"
                if bad is None and any(prev == entry for prev in entries):
                    bad = f"第 {idx + 1} 条与前面的登记项完全重复"
            if bad is None:
                entries.append(entry)
            else:
                problems.append(f"F-5c: AUTHORIZED_DELETIONS 结构性缺陷：{bad}")

    hits = [False] * len(entries)
    for path, lines in hunks:
        removed = [l[1:] for l in lines if l.startswith("-")]
        added = [l[1:] for l in lines if l.startswith("+")]
        if not removed:
            continue
        has_plus_import = any(IMPORT_LINE.match(a) or IMPORT_TAIL.match(a) for a in added)
        for r in removed:
            r_stripped = r.rstrip()
            is_import = bool(IMPORT_LINE.match(r_stripped)) or bool(IMPORT_TAIL.match(r_stripped))
            is_comment = bool(COMMENT_LINE.match(r_stripped))
            is_blank = r_stripped == ""
            if is_import:
                # 上下文口径（PM C4）：只有 `^-` 而没有 `+` 侧 import ⇒ 不算白名单
                if not has_plus_import:
                    problems.append(f"F-5c: {path} 删除了 import 行但 hunk 无 `+` 侧 import 对应行：{r_stripped!r}")
                else:
                    registered.append({"file": path, "kind": "import", "line": r_stripped})
            elif is_comment or is_blank:
                registered.append({"file": path, "kind": "comment" if is_comment else "blank", "line": r_stripped})
            else:
                # registry 分支（N5-r3 新增）：**整行全等**匹配，命中即授权、未命中即判红
                hit = None
                for i, entry in enumerate(entries):
                    if r_stripped == entry["line"] and path == entry["file"]:
                        hit = i
                        break
                if hit is None:
                    problems.append(f"F-5c: {path} 删除了**非白名单**行（可能是判据体/期望值）：{r_stripped!r}")
                else:
                    hits[hit] = True
                    authorized.append({"file": path, "line": r_stripped,
                                       "authorized_by": entries[hit]["authorized_by"]})
    if complete_face:
        for i, entry in enumerate(entries):
            if not hits[i]:
                registry_unused.append({"file": entry["file"], "line": entry["line"],
                                        "authorized_by": entry["authorized_by"]})
        if registry_unused:
            problems.append(
                "F-5c: AUTHORIZED_DELETIONS 存在未命中的登记项 "
                f"{len(registry_unused)} 条（多登记 = 无效）：{[e['line'] for e in registry_unused]}"
            )
    audit = {"registered_deletions": registered, "authorized_deletions": authorized,
             "registry_unused": registry_unused,
             "registry_total": len(registry) if isinstance(registry, (tuple, list)) else 0}
    return problems, audit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    problems = []
    registered = []
    authorized = []
    registry_unused = []
    # **iter2 r2.1 / Raven M-2 ≡ Sentinel F-1**：此处**不得**再前置求值 `len(AUTHORIZED_DELETIONS)`
    # （r2 的 `:291`）。registry 为「非序列且无 `__len__`」（`None` / 整数 / 生成器）时它会抛**未捕获**
    # `TypeError`：崩在写报告**之前** ⇒ ① 未按设计 §4.3-6 记结构性 problem ② `--json-out` 审计件不产出
    # ③ `--selftest` 一条用例都不跑。该前置值本来就随后被 `c_audit["registry_total"]` 覆盖（下同），
    # 删掉它 ⇒ 该形态走 `f5c_evaluate()` 的 fail-closed 降级路径（记结构性 problem ⇒ exit 1 ⇒ 审计件仍产出）。

    # --- 基线可读性（fail-closed）---
    # 浅克隆里 FROZEN_REF 不可解析 ⇒ F-5a/F-5b 会拿空基线「空转通过」（frozen=0 missing=0）。
    # 显式堵住这类「读不到就转绿」：基线解析不了 ⇒ 记 problem ⇒ exit 1。
    _baseline = baseline_problem(FROZEN_REF, ref_resolvable)
    if _baseline:
        problems.append(_baseline)

    # --- F-5a ---
    frozen_sa = git_show(FROZEN_REF, FILES["scene_assert"]) or ""
    current_sa = (WS / FILES["scene_assert"]).read_text(encoding="utf-8")
    frozen_names = set(CHECK_NAME.findall(frozen_sa))
    current_names = set(CHECK_NAME.findall(current_sa))
    missing = sorted(frozen_names - current_names)
    if missing:
        problems.append(f"F-5a: 既有判据名消失 {len(missing)} 条：{missing}")

    # --- F-5b ---
    frozen_lit = js_literals(frozen_sa)
    current_lit = js_literals(current_sa)
    from collections import Counter
    fc, cc = Counter(frozen_lit), Counter(current_lit)
    dropped = sorted((fc - cc).elements())
    if dropped:
        problems.append(f"F-5b: scene_assert.mjs 既有常量字面量消失 {len(dropped)} 个（示例 {dropped[:5]}）")

    frozen_vs = git_show(FROZEN_REF, FILES["verify_specs"]) or ""
    current_vs = (WS / FILES["verify_specs"]).read_text(encoding="utf-8")
    whitelist = [r"^\s*#.*$", r"^\s*$", r"^(set|shopt|export|local|readonly|declare)\b", r"^[A-Za-z_][A-Za-z0-9_]*=\("]
    fvb, cvb = Counter(bash_whitelist_constants(frozen_vs, whitelist)), Counter(bash_whitelist_constants(current_vs, whitelist))
    dropped_b = sorted((fvb - cvb).elements())
    if dropped_b:
        problems.append(f"F-5b: verify_specs.sh 既有常量字面量消失 {len(dropped_b)} 个（示例 {dropped_b[:5]}）")

    # --- F-5c ---
    diff_text = git_diff_u0(FROZEN_REF, F5C_FILE_FACE)
    hunks = parse_hunks(diff_text)
    c_problems, c_audit = f5c_evaluate(hunks, complete_face=True)
    registered = c_audit["registered_deletions"]
    authorized = c_audit["authorized_deletions"]
    registry_unused = c_audit["registry_unused"]
    registry_total = c_audit["registry_total"]
    problems.extend(c_problems)

    report = {
        "schema_version": "n5-f5-check/1",
        "frozen_ref": FROZEN_REF,
        "f5a": {"frozen_count": len(frozen_names), "current_count": len(current_names),
                "missing": missing, "added": sorted(current_names - frozen_names)},
        "f5b": {"scene_assert_frozen_literals": len(frozen_lit), "current_literals": len(current_lit),
                "dropped": dropped[:20], "dropped_count": len(dropped),
                "verify_specs_dropped_count": len(dropped_b), "verify_specs_dropped": dropped_b[:20]},
        "f5c": {"diff_hunk_count": len(hunks), "registered_deletions": registered,
                "registered_count": len(registered),
                "authorized_deletions": authorized, "authorized_count": len(authorized),
                "registered_authorized": authorized, "registered_authorized_count": len(authorized),
                "registry_total": registry_total, "registry_unused": registry_unused},
        "problems": problems,
    }

    if args.selftest:
        return selftest(current_sa, current_vs, f5c_evaluate)

    if args.json_out:
        p = Path(args.json_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"f5_check: wrote {p}")
    print(f"f5_check: F-5a frozen={len(frozen_names)} current={len(current_names)} missing={len(missing)}")
    print(f"f5_check: F-5b scene_assert dropped={len(dropped)} / verify_specs dropped={len(dropped_b)}")
    print(f"f5_check: F-5c hunks={len(hunks)} registered_deletions={len(registered)} problems={len(c_problems)}")
    for p in problems:
        print(f"  FAIL  {p}")
    if problems:
        print("f5_check: FAILED")
        return 1
    print("f5_check: OK（纯加法：名集零消失、常量只增不减、删除行在白名单或已授权登记表内）")
    return 0


def selftest(current_sa: str, current_vs: str, f5c_eval) -> int:
    """F-5d：四条负对照（/tmp 副本）+ N5-r3 的 registry 用例（⑥⑦ ⑧ ⑨⑩⑪）+ iter2 r2.1 的 ⑫。

    **iter2 r2.1**：⑧(a)~(g) 对**全部 7 条登记行**各跑一组（Raven M-1：补上「非空白前缀 + 登记行」
    这个**镜像方向**，捕 `endswith` 一类后缀匹配）；⑫ 用 `--json-out` 跑一份 registry 为非序列的
    /tmp 副本的**真实 `main()`**（Raven M-2 ≡ Sentinel F-1）。既有 ①~⑤ 与 ⑥⑦ ⑨⑩⑪ 的期望方向未改。
    """
    cases = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        sa = tmpdir / "scene_assert.mjs"
        # ① 删掉一条既有 check()
        sa.write_text(current_sa.replace("check('character_head_to_body_ratio_measured'", "check('removed_one'"), encoding="utf-8")
        names = set(CHECK_NAME.findall(sa.read_text(encoding="utf-8")))
        cases.append(("① 删一条既有 check ⇒ F-5a 必红", "character_head_to_body_ratio_measured" not in names))
        # ② 改一个期望值
        before = js_literals(current_sa)
        after = js_literals(current_sa.replace("FROZEN_POSITION = [18, 14, 24]", "FROZEN_POSITION = [19, 14, 24]"))
        from collections import Counter
        cases.append(("② 改一个期望值 ⇒ F-5b 必红", bool(Counter(before) - Counter(after))))
        # ③ 整条删一个多行 import（无 `+` 侧对应）⇒ F-5c 必红
        block = "\n".join(current_sa.split("\n")[43:53])
        diff3 = ("+++ b/scene_assert.mjs\n@@ -44,10 +44,0 @@\n"
                 + "\n".join("-" + l for l in block.split("\n")) + "\n")
        p3, _ = f5c_eval(parse_hunks(diff3))
        cases.append(("③ 整条删一个多行 import ⇒ F-5c 必红", bool(p3)))
        # ④ 拆一个多行 import（有 `+` 侧对应）⇒ 必须仍绿
        diff4 = ("+++ b/scene_assert.mjs\n@@ -44,2 +44,2 @@\n"
                 + "-import { existsSync, readFileSync } from 'node:fs';\n"
                 + "-import { fileURLToPath } from 'node:url';\n"
                 + "+import { existsSync, readFileSync } from 'node:fs';\n"
                 + "+import { fileURLToPath } from 'node:url';\n")
        p4, _ = f5c_eval(parse_hunks(diff4))
        cases.append(("④ 重排多行 import（有 `+` 侧）⇒ 必须仍绿", bool(p4)))
        # ⑤ N5-r2 回归：`--- a/<path>` 是 diff **文件头**，不得被当成 `^-` 删除行（纯插入必须仍绿）
        diff5 = ("--- a/scene_assert.mjs\n+++ b/scene_assert.mjs\n@@ -2060,0 +2061,3 @@\n"
                 + "+// 纯加法\n+const x = 1;\n+const y = 2;\n")
        p5, _ = f5c_eval(parse_hunks(diff5))
        cases.append(("⑤ 带 `--- a/` 文件头的纯插入 ⇒ 必须仍绿", bool(p5)))

        # --- N5-r3（REQ-20261011-018）：registry 用例 ---
        # 锚定行取自**真实登记表**（用例锚的就是登记内容；行文本与 sha256 见 03 §3）：
        ROW1 = AUTHORIZED_DELETIONS[0]["line"]   # 设计 §2.3 第 1 行（行首 2 空格，无行尾续行）
        ROW5 = AUTHORIZED_DELETIONS[4]["line"]   # 设计 §2.3 第 5 行（**行首无缩进**）
        REG_FILE = AUTHORIZED_DELETIONS[0]["file"]
        only5 = tuple(e for e in AUTHORIZED_DELETIONS if e["line"] == ROW5)
        no5 = tuple(e for e in AUTHORIZED_DELETIONS if e["line"] != ROW5)
        # iter2 r2.1：原 `ROW7` / `only7` 只被旧 ⑧ 锚点使用；⑧ 已改为**遍历全部 7 行** ⇒ 两个局部量不再需要。

        def _sha16(text: str) -> str:
            """登记行的 sha16（行身份指纹；每个用例标签里打印，便于逐行对账）。"""
            return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

        # 合成 diff：单行删除（路径 = 登记表里的真实文件面）
        d5 = "+++ b/" + REG_FILE + "\n@@ -900,1 +900,0 @@\n-" + ROW5 + "\n"
        d1 = "+++ b/" + REG_FILE + "\n@@ -900,1 +900,0 @@\n-" + ROW1 + "\n"

        # ⑥ 未登记的判据体删除 ⇒ 必红（registry 副本摘掉该条）
        p6, a6 = f5c_eval(parse_hunks(d5), registry=no5)
        cases.append(("⑥ 未登记的判据体删除（合成 diff，锚 ROW5）⇒ 必红",
                      bool(p6) and all(x["line"] != ROW5 for x in a6["authorized_deletions"]), True))
        # ⑦ 登记的删除被消费 ⇒ problems 空 ∧ 三字段齐的审计记录
        p7, a7 = f5c_eval(parse_hunks(d5), registry=only5)
        hit7 = [x for x in a7["authorized_deletions"] if x["line"] == ROW5]
        cases.append(("⑦ 登记的删除被消费（合成 diff，锚 ROW5）⇒ 必须仍绿",
                      not (p7 == [] and len(hit7) == 1
                           and set(hit7[0]) == {"file", "line", "authorized_by"}), False))
        # ⑧(a)~(g) **遍历全部 7 条登记行**（iter2 r2.1 / Raven M-1）：每条行各跑一组。
        # 原实现只锚 ROW5 / ROW7 ⇒ 判别力**单向**且只覆盖 3/7 行：Raven 实测 `endswith` 与
        # 「行级特化」两种实现能过 `--selftest` **且**放行未登记删除（本文件 03 §9.1）。
        # 每组的方向与改前**一字不改**：(a) 允许命中（绿）；(b)~(g) 必红。
        # 本组只用**单条**登记表 `reg = (r_entry,)` ⇒ 命中/未命中都只指向这一行。
        for r_idx, r_entry in enumerate(AUTHORIZED_DELETIONS, start=1):
            row = r_entry["line"]
            tag = f"ROW{r_idx} sha16={_sha16(row)}"
            reg = (r_entry,)

            def _del(deleted: str, path: str = REG_FILE) -> list:
                """被删除的**单行**（合成 diff；路径 = 真实登记文件面）。"""
                return parse_hunks("+++ b/" + path + "\n@@ -900,1 +900,0 @@\n-" + deleted + "\n")

            head = len(row) - len(row.lstrip(" "))
            if head:
                indent_line, indent_tag = row[head:], f"去掉行首 {head} 格缩进"
            else:
                indent_line, indent_tag = "  " + row, "该行本无缩进 ⇒ 加 2 格（同一「行首缩进被改动」方向）"
            mid = len(row) // 2
            longer_line = row[:mid] + "Z" + row[mid:]                      # 行内插 1 字符 ⇒ 更长
            pivot = next(i for i, ch in enumerate(row) if ch.isalpha())
            case_line = row[:pivot] + row[pivot].swapcase() + row[pivot + 1:]  # 大小写改变
            same_len_line = next(row[:mid] + ch + row[mid + 1:] for ch in ("Q", "7", "%")
                                 if ch != row[mid] and ch.lower() != row[mid].lower())
            tail_line = row + " # arg2"                                    # 登记行 + 后附内容
            pre_line = "keep_this_too " + row                              # 非空白前缀 + 登记行（镜像方向）

            for sub, deleted, expect_red, why in (
                ("(a)", row + " ", False, "行尾多 1 空格（rstrip 口径）⇒ 允许命中（绿）"),
                ("(b)", indent_line, True, f"{indent_tag} ⇒ 必红（抓丢缩进 / strip / lstrip）"),
                ("(c)", longer_line, True, "删行比登记行更长（行内插 1 字符）⇒ 必红"),
                ("(d)", same_len_line, True, "等长改 1 字符（非大小写）⇒ 必红"),
                ("(e)", case_line, True, "大小写改变 ⇒ 必红（抓 .lower()）"),
                ("(f)", tail_line, True, "删行 = 登记行 + 后附非空白内容 ⇒ 必红（捕前缀/子串）"),
                ("(g)", pre_line, True, "删行 = 非空白前缀 + 登记行（镜像方向）⇒ 必红（捕 endswith）"),
            ):
                p, a = f5c_eval(_del(deleted), registry=reg)
                hit = any(x["line"] == deleted.rstrip() for x in a["authorized_deletions"])
                # `red` = 「该用例观察到的是**红**」；期望绿的那条取反（回调口径与改前逐字一致）。
                cases.append((f"⑧{sub} {why}（{tag}）",
                              (bool(p) and not hit) if expect_red else (not (p == [] and hit)),
                              expect_red))
        # ⑨ 登记项缺字段 ⇒ fail-closed 必红（结构性 problem ∧ 该条不授权）
        reg9 = [dict(e) for e in AUTHORIZED_DELETIONS]
        del reg9[0]["authorized_by"]
        p9, a9 = f5c_eval(parse_hunks(d1), registry=tuple(reg9))
        cases.append(("⑨ 登记项缺 authorized_by（锚 ROW1）⇒ 结构性 problem ∧ 该条不授权（必红）",
                      any("AUTHORIZED_DELETIONS 结构" in x for x in p9)
                      and not any(x["line"] == ROW1 for x in a9["authorized_deletions"]), True))
        # ⑩ registry 非序列 ⇒ fail-closed 必红（不得当空登记表静默放行）
        for tag, bad_reg in (("None", None), ("dict", {}), ("str", "x")):
            p10, a10 = f5c_eval(parse_hunks(d5), registry=bad_reg)
            cases.append((f"⑩ registry 非序列（{tag}）⇒ 结构性 problem ∧ 不得当空表放行（必红）",
                          any("AUTHORIZED_DELETIONS 结构" in x for x in p10)
                          and a10["authorized_deletions"] == [], True))
        # ⑪① authorized_by 不匹配 ⇒ fail-closed 必红
        reg11a = [dict(e) for e in AUTHORIZED_DELETIONS]
        reg11a[0]["authorized_by"] = "SOME-OTHER-RULING"
        p11a, a11a = f5c_eval(parse_hunks(d1), registry=tuple(reg11a))
        cases.append(("⑪① authorized_by 不匹配（锚 ROW1）⇒ 结构性 problem ∧ 该条不授权（必红）",
                      any("AUTHORIZED_DELETIONS 结构" in x for x in p11a)
                      and not any(x["line"] == ROW1 for x in a11a["authorized_deletions"]), True))
        # ⑪② 完全重复的登记项 ⇒ 至少一条结构性 problem ∧ 不得两条都记命中
        reg11b = tuple(list(AUTHORIZED_DELETIONS) + [dict(AUTHORIZED_DELETIONS[4])])
        p11b, a11b = f5c_eval(parse_hunks(d5), registry=reg11b)
        dup11b = [x for x in a11b["authorized_deletions"] if x["line"] == ROW5]
        cases.append(("⑪② 完全重复的登记项（锚 ROW5，追加一条相同的）⇒ 结构性 problem ∧ 命中 ≤ 1",
                      any("AUTHORIZED_DELETIONS 结构" in x for x in p11b) and len(dup11b) <= 1, True))
        # ⑪③ 登记一条 diff 里不存在的行 ⇒ registry_unused 非空 ⇒ 额外 problem（多登记 = 无效）
        reg11c = tuple(list(only5) + [{"file": REG_FILE, "line": "  this line is deleted nowhere",
                                       "authorized_by": AUTHORIZED_BY, "why": "stale entry"}])
        p11c, a11c = f5c_eval(parse_hunks(d5), registry=reg11c, complete_face=True)
        cases.append(("⑪③ 登记一条 diff 里不存在的行（多登记 = 无效）⇒ problem ∧ registry_unused 非空（必红）",
                      any("未命中的登记项" in x for x in p11c)
                      and len(a11c["registry_unused"]) == 1, True))

        # ⑫ **iter2 r2.1**（Raven M-2 ≡ Sentinel F-1）：**经真实 `main()`** 的 fail-closed 降级路径。
        #    非序列 registry（None / int / 生成器）⇒ 必须 exit 1 ∧ problems ≥ 1 ∧ **审计件仍产出且可解析**。
        #    ⑩ 直接调 `f5c_evaluate` ⇒ 覆盖不到 main() 里**守卫之外**的前置求值：r2 的 `main():291`
        #    `registry_total = len(AUTHORIZED_DELETIONS)` 在该形态下抛未捕获 TypeError，崩在写报告**前**
        #    ⇒ 记不到结构性 problem、审计件不产出、本套用例一条都不跑（Raven 与 Sentinel 双方独立实证）。
        #    做法：把**本文件**复制到临时目录、把 registry 换成该形态（`WS` 钉回真实树 ⇒ 副本仍读真树），
        #    以 `--json-out` 跑该副本的 main()，读**进程退出码** + 审计件。副本与产物都在临时目录，真树零改动。
        main_src = Path(__file__).read_text(encoding="utf-8")
        # 锚点用**拼接**构造：本段自身源码里不得出现这两个字面量，否则 `count() != 1` 会把本段自己数进去。
        ws_anchor = "WS = Path(__file__)" + ".resolve().parents[3]"
        reg_anchor = "AUTHORIZED_DELETIONS" + " = ("
        for shape, slug, expr in (("None", "none", "None"), ("int", "int", "7"),
                                  ("生成器", "generator", "(e for e in ())")):
            bad_src = main_src.replace(ws_anchor, f"WS = Path({str(WS)!r})")
            if bad_src.count(reg_anchor) != 1:
                cases.append((f"⑫ registry 非序列经 main()（{shape}）⇒ 副本构造失败（anchor 命中数 != 1）",
                              False, True))
                continue
            bad_src = bad_src.replace(reg_anchor,
                                      f"AUTHORIZED_DELETIONS = {expr}  # 注入：非序列\n_UNUSED = (")
            copy_py = tmpdir / f"f5_main_{slug}.py"
            copy_py.write_text(bad_src, encoding="utf-8")
            out_json = tmpdir / f"f5_main_{slug}.json"
            proc = subprocess.run([sys.executable, "-B", str(copy_py), "--json-out", str(out_json)],
                                  capture_output=True, text=True, cwd=str(WS))
            n_problems, parseable = None, False
            if out_json.exists():
                try:
                    n_problems = len(json.loads(out_json.read_text(encoding="utf-8"))["problems"])
                    parseable = True
                except (json.JSONDecodeError, KeyError, TypeError):
                    parseable = False
            cases.append((f"⑫ registry 非序列经 main()（{shape}：exit={proc.returncode} / "
                          f"problems={n_problems} / 审计件={'产出且可解析' if parseable else '缺失或不可解析'}）"
                          f"⇒ exit 1 ∧ problems ≥ 1 ∧ 审计件产出（必红 = 满足）",
                          proc.returncode == 1 and parseable and bool(n_problems), True))

        # ⑬ **基线可读性 fail-closed**（浅克隆事故的回归钉）：F-5a/F-5b/F-5c 都以 FROZEN_REF 为基线
        #    （`git show` / `git diff`）。基线不可解析时旧实现拿空基线**空转通过**（`frozen=0 missing=0`）。
        #    本组钉死：不可解析 ⇒ 必报 problem（不见红即失败）；可解析 ⇒ 必须不报（对照另一臂）。
        cases.append(("⑬ 基线不可解析 ⇒ 必报 problem（fail-closed，堵『读不到就转绿』）",
                      baseline_problem("0" * 40, lambda _ref: False) is not None, True))
        cases.append(("⑬′ 基线可解析 ⇒ 必须不报（对照的另一臂）",
                      baseline_problem(FROZEN_REF, lambda _ref: True) is not None, False))

    ok = True
    for case in cases:
        label, red = case[0], case[1]
        expect_red = case[2] if len(case) > 2 else label.startswith(("①", "②", "③"))
        good = (red == expect_red)
        if not good:
            ok = False
        print(f"  selftest {label}: {'RED' if red else 'GREEN'}{'' if good else '  <== 异常！'}")
    print(f"selftest: {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
