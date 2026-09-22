#!/usr/bin/env python3
"""AC-M1-5 基线锚点捕获（W0b，实现前快照）。

口径（= 08 §2 W0b 排除表，预审 L5 措辞更正）：
  遍历根 = <root>/deephealing_kernel/**/*.py
  排除   = .venv / __pycache__ / tests
  digest = sha256(canonical_json(files))，files = {relpath: sha256}
  与 spike 先例（spikes/s2-capability-cassette/engine.py:kernel_digest()）的差异：
  先例仅排 .venv，且遍历根是 spike 根而非 deephealing_kernel/。

用途：把「实现前」的内核源码树复制到 spikes/kernel-baseline/deephealing_kernel/
并打印 files 数 + digest，作为 AC-M1-5 的 before 独立锚点
（预审 M4 给出 files=24 / digest=058e9a548be3c2186fc501441c556a27096c9eebfcca78cf4043b9e496697837）。

用法：
    python3 spikes/kernel-baseline/capture_baseline.py <kernel_root> <dest_root>
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

EXCLUDED_DIRS = {".venv", "__pycache__", "tests"}


def _load_canonical_json(kernel_root: Path):
    path = kernel_root.parent / "tools" / "canonical_json.py"
    spec = importlib.util.spec_from_file_location("deephealing_canonical_json_baseline", path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kernel_digest(kernel_root: Path, hash_object) -> dict:
    pkg_root = kernel_root / "deephealing_kernel"
    files: dict[str, str] = {}
    for path in sorted(pkg_root.rglob("*.py")):
        rel_parts = path.relative_to(pkg_root).parts
        if any(part in EXCLUDED_DIRS for part in rel_parts):
            continue
        files["/".join(rel_parts)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"files": files, "digest": hash_object(files)}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: capture_baseline.py <kernel_root> <dest_root>", file=sys.stderr)
        return 2
    kernel_root = Path(argv[1]).resolve()
    dest_root = Path(argv[2]).resolve()
    canonical = _load_canonical_json(kernel_root)

    src_pkg = kernel_root / "deephealing_kernel"
    dest_pkg = dest_root / "deephealing_kernel"
    if dest_pkg.exists():
        shutil.rmtree(dest_pkg)
    dest_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_pkg, dest_pkg, ignore=shutil.ignore_patterns(*EXCLUDED_DIRS, "*.pyc"))

    result = kernel_digest(dest_root, canonical.hash_object)
    print(json.dumps({"files": len(result["files"]), "digest": result["digest"]}, ensure_ascii=False))
    for rel in sorted(result["files"]):
        print(f"  {rel} {result['files'][rel]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
