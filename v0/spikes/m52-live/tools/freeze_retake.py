#!/usr/bin/env python3
"""终版冻结面重取（W12 · r2 = 最后写入者）。**两遍执行**，顺序在脚本里钉死。

- `--pass 1`：① 跑两个生成器 → ② `shasum -a 256 -c` 三份 → ③ 把读数 + **mtime 对照表**写进
  `spikes/m52-live/evidence/frozen-verify.txt`（该文件本身此时**还不在**清单里）。
- `--pass 2`（**最终**）：① 再跑两个生成器（此时清单**包含** `frozen-verify.txt` 与全部终版文本）
  → ② `shasum -a 256 -c` 三份 → ③ 读数写 `spikes/m52-live/runtime/frozen-final-shasum.txt`
  （`runtime*` 目录被生成器**按名排除** ⇒ **不在**清单内、**不改动**任何被哈希的文件）。

用法：`python3 spikes/m52-live/tools/freeze_retake.py --pass 1` 然后 `--pass 2`
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
LIVE = WS / "spikes" / "m52-live"
MANIFESTS = ("V0_M52.sha256", "V0_M4.sha256", "V0_M5.sha256")
GENERATORS = (("python3", "V0_M52.gen.py"), ("python3", "spikes/m52-frozen/retake_m4_m5.py"))


def run(command: list[str]) -> dict:
    proc = subprocess.run(command, cwd=str(WS), capture_output=True, text=True)
    return {"cmd": " ".join(command), "exit": proc.returncode,
            "stdout_tail": proc.stdout.strip().splitlines()[-4:],
            "stderr_tail": proc.stderr.strip().splitlines()[-3:]}


def mtime_table() -> dict:
    surface = [path for path in (WS / "spikes" / "m52-live").rglob("*") if path.is_file()]
    surface += [WS / "03_artisan_self_test.log", WS / "06_v0_m52_self_test.md"]
    surface = [path for path in surface if path.is_file()]
    newest = max(surface, key=lambda path: path.stat().st_mtime)
    table = {}
    for name in MANIFESTS:
        path = WS / name
        table[name] = {"mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime)),
                       "mtime_epoch": path.stat().st_mtime,
                       "entries": len(path.read_text(encoding="utf-8").splitlines())}
    return {"manifests": table,
            "newest_surface_file": {"path": str(newest.relative_to(WS)),
                                    "mtime": time.strftime("%Y-%m-%d %H:%M:%S",
                                                           time.localtime(newest.stat().st_mtime)),
                                    "mtime_epoch": newest.stat().st_mtime},
            "manifests_newer_than_surface": all(table[name]["mtime_epoch"] > newest.stat().st_mtime
                                                for name in MANIFESTS),
            "manifest_covers_frozen_verify": "spikes/m52-live/evidence/frozen-verify.txt"
                                             in (WS / "V0_M52.sha256").read_text(encoding="utf-8")}


def main() -> int:
    parser = argparse.ArgumentParser(description="M5.2 r2 freeze re-take (two passes)")
    parser.add_argument("--pass", dest="phase", type=int, choices=(1, 2), required=True)
    args = parser.parse_args()

    steps = [run(list(command)) for command in GENERATORS]
    verify = subprocess.run(["shasum", "-a", "256", "-c", *MANIFESTS], cwd=str(WS),
                            capture_output=True, text=True)
    lines = verify.stdout.splitlines()
    not_ok = [line for line in lines if not line.endswith(": OK")]
    document = {
        "pass": args.phase,
        "generators": steps,
        "shasum": {"exit": verify.returncode, "lines": len(lines), "not_ok": not_ok,
                   "not_ok_count": len(not_ok)},
        "mtime_table": mtime_table(),
    }
    text = json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True)
    if args.phase == 1:
        target = LIVE / "evidence" / "frozen-verify.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("cmd（workdir <ws>）：python3 V0_M52.gen.py; python3 spikes/m52-frozen/retake_m4_m5.py; "
                          "shasum -a 256 -c V0_M52.sha256 V0_M4.sha256 V0_M5.sha256\n"
                          f"pass 1 读数：not_ok_count={len(not_ok)}（期望 0）；entries="
                          f"{document['mtime_table']['manifests']}\n\n"
                          + "\n".join(lines) + "\n\n" + text + "\n", encoding="utf-8")
    else:
        target = LIVE / "runtime" / "frozen-final-shasum.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")
    return 0 if not not_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
