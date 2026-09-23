#!/usr/bin/env python3
"""R2 / F7：P-8 证据**重采** —— 在全部写入完成、冻结面定格**之后**取 before/after。

R1 的问题：P-8 的 before/after 快照在 23:40 取，之后**又有 3 个文件被改** ⇒ 证据早于交付面。
本脚本：① 复算 before 清单（逐文件 sha256）→ ② 真跑一次桥（把 `02_source` 整树复制到运行目录）
→ ③ 复算 after 清单 ⇒ 两者必须**逐字节相同**（`02_source/**` 零改动、零残渣）。

用法：python3 -B spikes/s12-session/scripts/p8-freeze-recheck.py <ws>
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

GENERATED = ("__pycache__", ".pytest_cache", ".DS_Store", "node_modules", ".venv", "dist", ".build")


def manifest(root: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in GENERATED for part in path.parts) or path.suffix == ".pyc":
            continue
        entries[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return entries


def write_manifest(path: Path, entries: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{digest}  {rel}\n" for rel, digest in sorted(entries.items())), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: p8-freeze-recheck.py <workspace>", file=sys.stderr)
        return 2
    ws = Path(argv[1]).resolve()
    source = ws / "02_source"
    logs = ws / "spikes" / "s12-session" / "logs"
    runtime = Path("/tmp/r2-artisan/p8-runtime")
    if runtime.exists():
        shutil.rmtree(runtime)

    started = int(time.time())
    before = manifest(source)
    write_manifest(logs / "p8-before-r2.txt", before)

    bridge = source / "v0_skeleton" / "session" / "bridge" / "kernel_bridge.py"
    proc = subprocess.run(
        [sys.executable, "-B", str(bridge),
         "--kernel-src", str(source / "v0_skeleton" / "kernel"),
         "--pack-src", str(source / "v0_skeleton" / "districts" / "xingfu-xiaoqu"),
         "--runtime-dir", str(runtime), "--seed", "20260921", "--snapshot-every", "50", "--ticks", "300"],
        input=json.dumps({"cmd": "step", "n": 1}) + "\n" + json.dumps({"cmd": "stop"}) + "\n",
        capture_output=True, text=True, timeout=900)

    after = manifest(source)
    write_manifest(logs / "p8-after-r2.txt", after)

    identical = before == after
    report = {
        "workspace": str(ws),
        "reason_for_retake": "R1 的 P-8 快照（23:40）早于交付面最后写入（3 个文件被改）⇒ 全部写入完成、"
                             "冻结面定格后重采 before/after（F7 关闭判据）",
        "taken_at_epoch": started,
        "taken_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
        "bridge_exit": proc.returncode,
        "runtime_dir": str(runtime),
        "file_count_before": len(before),
        "file_count_after": len(after),
        "before_manifest": str(logs / "p8-before-r2.txt"),
        "after_manifest": str(logs / "p8-after-r2.txt"),
        "manifest_sha256_before": hashlib.sha256((logs / "p8-before-r2.txt").read_bytes()).hexdigest(),
        "manifest_sha256_after": hashlib.sha256((logs / "p8-after-r2.txt").read_bytes()).hexdigest(),
        "delivery_face_byte_identical": identical,
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(rel for rel in set(before) & set(after) if before[rel] != after[rel]),
    }
    out = logs / "p8-freeze-recheck.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("bridge_exit", "file_count_before", "file_count_after",
                       "delivery_face_byte_identical", "added", "removed", "changed",
                       "manifest_sha256_before", "manifest_sha256_after")},
                     ensure_ascii=False, sort_keys=True))
    return 0 if identical and proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
