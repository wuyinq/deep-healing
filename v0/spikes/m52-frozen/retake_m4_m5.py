#!/usr/bin/env python3
"""重取 `V0_M4.sha256` / `V0_M5.sha256`（M5.2 r1 · 任务书 W9 / REQ §5 / Raven M-12）。

**为什么必须重取**：本轮三处内核改动（C1/C2/C3）+ 记忆链 + 关系演进 + 新 pack 全部落在
`02_source/**` 内，而 `02_source/**` 同时是 M4 与 M5 冻结面的采集根 ⇒ 两份旧清单必然失效。

口径**各自沿用原版**（不得混口径）：
  - **M4 口径**：`02_source/**` + `spikes/s14-observability/**` + `spikes/s15-autonomy/**`
    + `spikes/s16-liveworld/**` + 根级 `03_artisan_self_test.log` / `06_v0_m4_self_test.md` / `V0_SELF_TEST.md`；
  - **M5 口径**：`02_source/**` + `docs/**` + `fidelity/POINTER.md` + 根级 `03_artisan_self_test.log`。

两份清单**自身不入清单**；排除项与声明沿用各自原版（见生成后的文件头）。

用法：`python3 <ws>/spikes/m52-frozen/retake_m4_m5.py`  ⇒  各 `shasum -a 256 -c` 期望 0 非 OK。
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]      # <ws>

SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache", "node_modules", ".venv", "dist", ".build", ".git"}
SKIP_DIR_PATTERNS = (re.compile(r"^attic-"), re.compile(r"^runtime"))
SKIP_FILE_PATTERNS = (re.compile(r"\.pyc$"), re.compile(r"^\.DS_Store$"))
SPIKE_ARTIFACT_PATTERNS = (
    re.compile(r"\.png$"), re.compile(r"^console-.*\.jsonl$"), re.compile(r"^browser-live-.*\.json$"),
    re.compile(r"^emitted-messages-.*\.jsonl$"), re.compile(r".*-summary\.json$"),
    re.compile(r"^kernel-live\.out$"), re.compile(r"^serve-live\.out$"),
)

M4_ROOTS = ["02_source", "spikes/s14-observability", "spikes/s15-autonomy", "spikes/s16-liveworld"]
M4_ROOT_FILES = ["03_artisan_self_test.log", "06_v0_m4_self_test.md", "V0_SELF_TEST.md"]
M5_ROOTS = ["02_source", "docs"]
M5_ROOT_FILES = ["03_artisan_self_test.log", "fidelity/POINTER.md"]

M4_HEADER = """\
# V0_M4.sha256 — M4 冻结面自校验（采集面与排除项**显式声明**）
#
# **M5.2 r1 重取**：本轮三处内核改动 + 记忆链 + 关系演进 + 新 pack 全部落在 02_source/** 内，
#   而 02_source/** 是本面采集根 ⇒ 旧清单失效，按 **M4 原口径**重取并登记。
# 采集面：02_source/**  +  spikes/s14-observability/**  +  spikes/s15-autonomy/**
#         + spikes/s16-liveworld/**  +  根级 03_artisan_self_test.log / 06_v0_m4_self_test.md / V0_SELF_TEST.md
#         （**V0_M4.sha256 自身不入清单** —— 不可自哈希）
# 排除项：__pycache__ / *.pyc / .pytest_cache / .DS_Store / node_modules / .venv / dist / .build / attic-*
#         + spikes/*/runtime*/**  +  **浏览器运行产物（仅限 spikes/**）**：*.png / console-*.jsonl /
#         browser-live-*.json / emitted-messages-*.jsonl / *-summary.json / kernel-live.out / serve-live.out
#         **注意**：运行产物模式**只在 spikes/** 下生效**；02_source/** 一律不按名字排除。
# 声明（沿用 R5-RAV-M3）：**被排除路径不得承载判据性结论**。
# 生成方式：python3 <ws>/spikes/m52-frozen/retake_m4_m5.py（脚本不在采集面内）
# 自校验：cd <ws> && shasum -a 256 -c V0_M4.sha256   ⇒ 期望 0 非 OK 行
"""

M5_HEADER = """\
# V0_M5.sha256 — M5 冻结面自校验（采集面与排除项**显式声明**）
#
# **M5.2 r1 重取**：本轮改动落在 02_source/**（本面采集根）内 ⇒ 旧清单失效，按 **M5 原口径**重取并登记。
# 采集面：02_source/**  +  docs/**  +  fidelity/POINTER.md  +  根级 03_artisan_self_test.log
#         （**V0_M5.sha256 自身不入清单** —— 不可自哈希）
# 排除项：__pycache__ / *.pyc / .pytest_cache / .DS_Store / node_modules / .venv / dist / .build
#         / attic-* / runtime*
# 声明（沿用 R5-RAV-M3）：**被排除路径不得承载判据性结论**。
# 生成方式：python3 <ws>/spikes/m52-frozen/retake_m4_m5.py（脚本不在采集面内）
# 自校验：cd <ws> && shasum -a 256 -c V0_M5.sha256   ⇒ 期望 0 非 OK 行
"""


def keep_dir(name: str) -> bool:
    if name in SKIP_DIR_NAMES:
        return False
    return not any(pattern.match(name) for pattern in SKIP_DIR_PATTERNS)


def keep_file(name: str, *, spikes: bool) -> bool:
    if any(pattern.search(name) for pattern in SKIP_FILE_PATTERNS):
        return False
    if spikes and any(pattern.search(name) for pattern in SPIKE_ARTIFACT_PATTERNS):
        return False
    return True


def collect(roots: list[str], root_files: list[str]) -> list[str]:
    found: list[str] = []
    for root in roots:
        base = WS / root
        if not base.is_dir():
            continue
        is_spikes = root.startswith("spikes")
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(name for name in dirnames if keep_dir(name))
            for filename in sorted(filenames):
                if not keep_file(filename, spikes=is_spikes):
                    continue
                found.append(str((Path(dirpath) / filename).relative_to(WS)))
    for name in root_files:
        if (WS / name).is_file():
            found.append(name)
    return sorted(set(found))


def write(out_name: str, header: str, files: list[str]) -> None:
    lines = [header.rstrip("\n")]
    for relative in files:
        digest = hashlib.sha256((WS / relative).read_bytes()).hexdigest()
        lines.append(f"{digest}  {relative}")
    (WS / out_name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {WS / out_name} entries={len(files)}")


def main() -> int:
    m4 = collect(M4_ROOTS, M4_ROOT_FILES)
    m5 = collect(M5_ROOTS, M5_ROOT_FILES)
    if not m4 or not m5:
        print("E_EMPTY_MANIFEST", file=sys.stderr)
        return 2
    write("V0_M4.sha256", M4_HEADER, m4)
    write("V0_M5.sha256", M5_HEADER, m5)
    print("  V0_M4 采集面条目:", len(m4), "| V0_M5 采集面条目:", len(m5))
    for name in M4_ROOT_FILES:
        print(f"  M4 {name}: {'in' if name in m4 else 'MISSING'}")
    for name in M5_ROOT_FILES:
        print(f"  M5 {name}: {'in' if name in m5 else 'MISSING'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
