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
  F-5c  **删除行白名单**：`git diff --unified=0 <frozen-ref> -- <三个文件>` 的每个删除 hunk，
        其全部 `^-` 行去前缀后必须逐行匹配 ① import（含多行 import 起始/收尾行，收尾行以 `,` 或 `}`
        结尾）② 注释 ③ 空行；**上下文口径**：该 hunk 必须同时含 `+` 侧 import 对应行；
        否则 **FAIL**；其余删除行逐行登记
        （N5-r2 修正：`--- a/<path>` / `+++ b/<path>` 是 diff **文件头**，不是内容行，已显式跳过 ——
          r1 的 `verify_specs.sh` 与 `<frozen-ref>` 逐字节相同 ⇒ 无 hunk，故该解析缺陷当时未暴露。）
  F-5d  负对照（在 `/tmp` 副本上做）：① 删一条既有 `check()` ② 改一个期望值
        ③ 整条删一个多行 import ④ 拆一个多行 import（有 `+` 侧对应）⇒ ①②③ **必红**，④ **必须仍绿**
        （N5-r2 新增 ⑤：带 `--- a/` 文件头的纯插入 ⇒ **必须仍绿**，即上面那条解析修正的回归。）
  F-5e  producer 侧登记（`01d`）的等价性口径：既有判据的**期望值/阈值常量**逐字节不变
        （= F-5b 的「只增不减」在**值**维度上的形态
         —— **承担者更正（N5-r2 / B-6）**：实测由 **F-5c** 承担，`01d §0` 的表述已同步改写）
"""

from __future__ import annotations

import argparse
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


def f5c_evaluate(hunks):
    """返回 (problems, registered_deletions)。"""
    problems = []
    registered = []
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
                problems.append(f"F-5c: {path} 删除了**非白名单**行（可能是判据体/期望值）：{r_stripped!r}")
    return problems, registered


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    problems = []
    registered = []

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
    c_problems, registered = f5c_evaluate(hunks)
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
                "registered_count": len(registered)},
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
    print("f5_check: OK（纯加法：名集零消失、常量只增不减、删除行全在白名单内）")
    return 0


def selftest(current_sa: str, current_vs: str, f5c_eval) -> int:
    """F-5d：四条负对照（/tmp 副本）。"""
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

    ok = True
    for label, red in cases:
        expect_red = label.startswith(("①", "②", "③"))
        good = (red == expect_red)
        if not good:
            ok = False
        print(f"  selftest {label}: {'RED' if red else 'GREEN'}{'' if good else '  <== 异常！'}")
    print(f"selftest: {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
