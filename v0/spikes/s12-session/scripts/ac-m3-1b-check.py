#!/usr/bin/env python3
"""R2 / F8：AC-M3-1b 的**双向**判据（修正口径）。

修正后的口径（R1 的 `06` 用的是「差集 == 声明清单」，而 `V0_M2.sha256` 自身含 **1 条 M2 继承偏差**）：
    非 OK 集合 == 声明清单（SECTION A / `modified`）  ∪  已登记的 M2 继承偏差
且**双向**成立：
  - `declared - nonOK` 必须为空（**虚报**：声明了却没变 ⇒ 声明失真）；
  - `nonOK - declared` 必须 ⊆ 已登记的继承偏差（**漏报**：变了却没声明 ⇒ 门禁失守）。

用法（workdir = <ws>）：
    python3 -B spikes/s12-session/scripts/ac-m3-1b-check.py --ws .
    python3 -B spikes/s12-session/scripts/ac-m3-1b-check.py --ws /tmp/copy --v0m2 <V0_M2.sha256> --declaration <json>

退出码：0 = 双向成立；1 = 有虚报/漏报；2 = 用法错误。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ac-m3-1b-check.py")
    parser.add_argument("--ws", default=".")
    parser.add_argument("--v0m2", default=None)
    parser.add_argument("--declaration", default=None)
    args = parser.parse_args(argv)
    ws = Path(args.ws).resolve()
    v0m2 = Path(args.v0m2).resolve() if args.v0m2 else ws / "V0_M2.sha256"
    declaration_path = (Path(args.declaration).resolve() if args.declaration
                        else ws / "spikes" / "s12-session" / "m3-change-face.json")
    if not v0m2.is_file() or not declaration_path.is_file():
        print(f"E_AC_M3_1B_USAGE: missing {v0m2} or {declaration_path}", file=sys.stderr)
        return 2

    proc = subprocess.run(["shasum", "-a", "256", "-c", str(v0m2)], cwd=str(ws),
                          capture_output=True, text=True)
    non_ok = sorted(line.split(":")[0].strip() for line in proc.stdout.splitlines()
                    if line.strip() and not line.endswith(": OK"))
    declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
    declared = sorted(declaration["modified"])
    inherited = sorted({item["path"] for item in declaration.get("inherited_m2_deviations", [])})

    declared_only = sorted(set(declared) - set(non_ok))
    non_ok_only = sorted(set(non_ok) - set(declared))
    unexplained = sorted(path for path in non_ok_only if path not in inherited)
    explained_by_inheritance = sorted(path for path in non_ok_only if path in inherited)

    report = {
        "workspace": str(ws),
        "v0_m2": str(v0m2),
        "declaration": str(declaration_path),
        "declared_at_epoch": declaration.get("declared_at_epoch"),
        "checked_at_epoch": __import__("time").time_ns() // 1_000_000_000,
        "non_ok_count": len(non_ok),
        "declared_count": len(declared),
        "declared_but_unchanged": declared_only,
        "changed_but_undeclared": unexplained,
        "changed_explained_by_inherited_deviation": explained_by_inheritance,
        "inherited_deviations": inherited,
        "bidirectional_ok": not declared_only and not unexplained,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if declared_only:
        print(f"E_AC_M3_1B: 声明了却没变（虚报）：{declared_only}", file=sys.stderr)
    if unexplained:
        print(f"E_AC_M3_1B: 变了却没声明（漏报）：{unexplained}", file=sys.stderr)
    return 0 if report["bidirectional_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
