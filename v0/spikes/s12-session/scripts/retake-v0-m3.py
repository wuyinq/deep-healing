#!/usr/bin/env python3
"""R2 / 收尾：重取 `V0_M3.sha256`（采集面与排除项**逐字沿用** R1 声明）。

采集面：`02_source/**` + `spikes/s12-session/**` + `spikes/s13-render/**`
        + 根级 `03_artisan_self_test.log` / `06_v0_m3_self_test.md`
        （**`V0_M3.sha256` 自身不入清单** —— 不可自哈希；`V0_M3.sha256.retake.json` 亦不在面内）
排除项：`__pycache__` / `*.pyc` / `.pytest_cache` / `.DS_Store` / `node_modules` / `.venv` / `dist` / `.build`
        / `attic-*` / `spikes/*/runtime*/**`（运行期副本，生成物）

R5-FIX（**声明修正轮**，非新一轮）：本文件的「声明 ↔ 实现」一致性逐条对齐（Raven `M4` 的 (a)(b)(c)(d)）——
  采集面/排除项的**范围未变**（未放宽、未收紧任何**排除规则**，只让实现与头部声明**逐字一致**）。

用法：python3 -B spikes/s12-session/scripts/retake-v0-m3.py <ws> [--dry-run]
"""

from __future__ import annotations

import hashlib
import fnmatch
import sys
from pathlib import Path

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".DS_Store", "node_modules", ".venv", "dist", ".build"}
# R3 / G3：**作废证据集**不入清单（`superseded/**`）—— 交付面不并存两套互斥结论，
# 且该目录的存在性由 `06` 的 M3 段就地作废标注 + 该目录的 README.md 说明。
#
# R5 / PM 裁决 `R4-M4`（**冻结面口径修正**）：**可重生成的运行产物**同样不入清单（与 `runtime*/**`、
# `superseded/**` 同类）。理由：f4 真浏览器每复跑一次都会重写它们（PNG / browser-accept-*.json /
# console-*.jsonl / negctl-*.log / *-summary.json / emitted-messages.jsonl）⇒ 清单若把它们钉进哈希面，
# 出口前**任何一次**复跑都会让 `shasum -c` 变红，被误读成「交付面被改」。其**判据结论**由门禁退出码
# 与 `06` 的登记承担（见本文件 HEADER 的显式声明）。
# 匹配口径：整条相对路径的 glob（`*` 可跨 `/`），但每个模式都以 `spikes/*/logs/` 前缀约束 ⇒
# 排除范围不会溢出这两个 logs 子树。
EXCLUDE_SUBPATHS = (
    "spikes/s12-session/logs/superseded/**",
    "spikes/s12-session/logs/*.png",
    "spikes/s12-session/logs/browser-accept-*.json",
    "spikes/s12-session/logs/console-*.jsonl",
    "spikes/s12-session/logs/negctl-*.log",
    "spikes/s12-session/logs/*-summary.json",
    # R5-FIX（F7(b)）：头部把 `serve-summary-*.json` 声明为**两个** logs 子树都排除，而 R5 实现只有 s13 侧
    # ⇒ 按「与声明逐字一致」补齐 s12 侧同模式（两目录**对称**，与 §1.3 的口径一致）。
    # 当前 s12 侧无此文件名 ⇒ `--dry-run` 的 `removed` 不变、`added=[]`（读数见 06 的 R5-FIX 段）。
    "spikes/s12-session/logs/serve-summary-*.json",
    "spikes/s12-session/logs/emitted-messages.jsonl",
    "spikes/s13-render/logs/*.png",
    "spikes/s13-render/logs/browser-accept-*.json",
    "spikes/s13-render/logs/console-*.jsonl",
    "spikes/s13-render/logs/negctl-*.log",
    "spikes/s13-render/logs/*-summary.json",
    # R5-POST（post-hoc，如实登记）：约束 §1.3 的字面模式 `*-summary.json` **不覆盖** f4 每个 case 的
    # `serve-summary-<tag>.json`（其结尾是 `-summary-<tag>.json`），但该文件是 f4 每复跑一次都会重写的
    # 运行产物（实测：R4 清单在一次 f4 复跑后 29 条 FAILED 里有 4 条就是它）。故按 §1.3 的**意图**
    # （可重生成的 f4 运行产物移出哈希面）补这一条**定向**模式；冲突/缺口已写进 06 R5 段与最终汇总。
    "spikes/s13-render/logs/serve-summary-*.json",
    "spikes/s13-render/logs/emitted-messages.jsonl",
)
ROOT_FILES = ("03_artisan_self_test.log", "06_v0_m3_self_test.md")
HEADER = """# V0_M3.sha256 — M3 冻结面自校验（采集面与排除项**显式声明**）
#
# 采集面：02_source/**（除生成残渣与运行期副本）+ spikes/s12-session/** + spikes/s13-render/**
#         + 根级 03_artisan_self_test.log / 06_v0_m3_self_test.md
#         （**V0_M3.sha256 自身不入清单** —— 不可自哈希；V0_M3.sha256.retake.json 亦不在面内。R5-FIX/F7(c)）
# 排除项：__pycache__ / *.pyc / .pytest_cache / .DS_Store / node_modules / .venv / dist / .build / attic-*
#         + spikes/*/runtime*/**（运行期副本：桥把 02_source 整树复制到运行目录，生成物；R1 已排除
#           spikes/s12-session/runtime/**，R2 按同一规则覆盖 spikes/s13-render/runtime*）
#         + spikes/s12-session/logs/superseded/**（R3 / G3：R1 崩溃型假红的**作废证据集**，不得作为判据）
#         + **运行产物（R5 / PM 裁决 `R4-M4`）**：`spikes/s12-session/logs/**` 与 `spikes/s13-render/logs/**`
#           下的 `*.png` / `browser-accept-*.json` / `console-*.jsonl` / `negctl-*.log` / `*-summary.json` /
#           `serve-summary-*.json`（f4 每个 case 的 serve 摘要；**字面模式 `*-summary.json` 不覆盖它**，
#           R5-POST 按同一口径定向补齐）/ `emitted-messages.jsonl`
# 语义：本清单是 M3 **时点快照**（与 V0_M2.sha256 同口径）；M4 增删文件后 `shasum -c` 按设计会红，
#       届时按「重取登记」规则（理由 + 变更清单 + 前后哈希）重取，**不得**静默改写。
# 运行产物口径（R5 显式声明）：**运行产物 = 可重生成，不入哈希面**；其**判据结论**由门禁退出码
#       与 `06` 的登记承担（f4 真浏览器每复跑一次都会重写它们 ⇒ 若钉进哈希面，出口前任何一次复跑
#       都会让 `shasum -c` 变红，被误读成「交付面被改」）。
# 验收口径（R5-FIX / F7(d)①）：**验收口径 = f4 真浏览器复跑**（`spikes/s13-render/negctl/f4_browser_negctl.py`）。
#       **非 f4 驱动**（f5 / f6 / f1 …）复跑会重写它们**自己的**产物，其中部分**仍在**哈希面内
#       （如 `spikes/s13-render/logs/f5-r4-negctl-summary-red.json`、`r4-*-widening.log`）⇒ 复跑这些驱动后
#       若 `shasum -c` 变红，须按本清单的「重取登记」规则处理（理由 + 变更清单 + 前后哈希），**不得**静默改写。
#       ⇒ **登记 M4**（是否把这些非 f4 驱动产物一并纳入排除项，属 M4 决策；R5-FIX 未扩张排除范围）。
# 排除语义边界（R5-FIX / F7(d)②，Raven `M3`）：排除**仅按名字模式**（`fnmatch`，`*` 可跨 `/`）⇒
#       **被排除路径不得承载判据性结论**；判据结论必须落在**门禁退出码**与 `06` / `03` 的登记上。
#       （已知残余：AC-M3-8③⑤ 的**原始**双读运行读数已随运行产物外置，只能靠复跑 f4 复现 ⇒ 登记 M4。）
# 重取（R2 / 修复轮）：理由与前后哈希见 `06_v0_m3_self_test.md` 的 R2 段「重取登记」。
# 重取（R3 / 最后一次修复迭代 3/3）：理由、变更清单与排除项变更见 `06` 的 R3-E 段。
# 重取（R4 / **有界补丁轮** · 关闭 `R3-C1`）：理由、变更清单与条目数见 `06` 的 R4-E 段。
# 重取（R5 / **终局有界轮** · 关闭 `R4-C1`/`R4-C2`/`R4-M1` 的**判据层** + `R4-M4` 冻结面口径）：
#       理由、变更清单与排除项变更见 `06` 的 R5-E 段。
# 重取（R5-FIX / **声明修正轮** · 两名门禁指出的**声明层**缺口）：理由与逐条改动面见 `06` 的
#       `R5-FIX` 段（采集面与排除**范围未变**；仅「声明 ↔ 实现」一致性对齐）。
# 条目数：{count}
"""


def collect(ws: Path) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    for base in ("02_source", "spikes/s12-session", "spikes/s13-render"):
        root = ws / base
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ws).as_posix()
            if any(part in EXCLUDE_DIRS or part.startswith("attic-") for part in path.parts):
                continue
            if path.suffix == ".pyc":
                continue
            if rel.startswith("spikes/s12-session/runtime/"):
                continue
            if any(fnmatch.fnmatch(rel, pattern) for pattern in EXCLUDE_SUBPATHS):
                continue
            # 运行期副本（桥把 02_source 整树复制到运行目录）一律排除：生成物，任何一次真跑都会重写。
            # R3 修正：判据与**头部声明**（`spikes/*/runtime*/**`）逐字对齐 —— 此前只匹配名为
            # `runtime` / `runtime-record` 的目录，R3 的负例驱动用 `runtime-<tag>`（避免互相覆盖）
            # 会漏进 854 条生成物。排除范围本身**未变**（声明早已是 `runtime*`），只是让实现与声明一致。
            # R5-FIX（F7(a)）：原实现是「**任意位置**的 `runtime*` 分量」，会静默排除 `02_source/**`
            # （实测可复现：`02_source/runtime-notes.md` / `02_source/v0_skeleton/web/runtime-snapshot.json`）
            # ⇒ **收紧到与声明逐字一致**：仅 `spikes/<dir>/runtime*/**`（即 `spikes/` 之下、深度 ≥2 的
            # `runtime*` 分量）。交付面当前无此类路径 ⇒ `--dry-run` 的 `added=[]`（读数见 06 的 R5-FIX 段）。
            parts = Path(rel).parts
            if len(parts) >= 3 and parts[0] == "spikes" and any(part.startswith("runtime") for part in parts[2:]):
                continue
            entries.append((rel, path))
    for name in ROOT_FILES:
        path = ws / name
        if path.is_file():
            entries.append((name, path))
    return sorted(entries)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: retake-v0-m3.py <ws> [--dry-run]", file=sys.stderr)
        return 2
    ws = Path(argv[1]).resolve()
    dry_run = "--dry-run" in argv
    entries = collect(ws)
    lines = [HEADER.format(count=len(entries))]
    for rel, path in entries:
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel}\n")
    rendered = "".join(lines)
    out = ws / "V0_M3.sha256"
    previous_paths = set()
    if out.is_file():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                previous_paths.add(line.split("  ", 1)[1].strip())
    current_paths = {rel for rel, _ in entries}
    print(f"entries={len(entries)} previous_entries={len(previous_paths)}")
    print(f"added={sorted(current_paths - previous_paths)}")
    print(f"removed={sorted(previous_paths - current_paths)}")
    if dry_run:
        print("dry-run: not written")
        return 0
    out.write_text(rendered, encoding="utf-8")
    print(f"written {out} sha256={hashlib.sha256(rendered.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
