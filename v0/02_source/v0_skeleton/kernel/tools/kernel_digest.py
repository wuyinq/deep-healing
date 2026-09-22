#!/usr/bin/env python3
"""W0b · 内核源码指纹（V0-M1 新增，AC-M1-5）。

**口径**（= `08` §2 W0b 的排除表；措辞更正见预审 L5）：
    遍历根 = `<root>/deephealing_kernel/**/*.py`
    排除   = `.venv` / `__pycache__` / `tests`
    `kernel_digest(root) -> {"files": {relpath: sha256}, "digest": sha256(canonical_json(files))}`

与 `spikes/s2-capability-cassette/engine.py:kernel_digest()` 先例的**差异**（不得笼统称「同口径」）：
先例仅排 `.venv`，且遍历根是 spike 根而非 `deephealing_kernel/`。
契约函数形状（`{"files","digest"}` + `hash_object(files)`）与先例一致。

**判据（新增能力零内核改动）**：before/after 差集必须满足
    `changed == []` 且 `added ⊆ {deephealing_kernel/adapters/**, deephealing_kernel/providers/adapters/**}`
adapter 目录口径取**并集**（设计 §4.8 裁决）：`refs/08` 与 REQ 都写 `providers/adapters/`，
但冻结骨架里**没有该目录**（只有 `deephealing_kernel/adapters/`）；并**不新增**它（属 W3 面）。

**import 约束（architect 探针实测）**：以脚本形式运行时 `sys.path[0]` = `kernel/tools/`
（**不是** cwd）⇒ 本脚本**不得** `import deephealing_kernel`；它只按文件路径加载
`<v0_skeleton>/tools/canonical_json.py`，并把 `deephealing_kernel/**/*.py` 当**数据**遍历。

用法：
    cd <workspace>/02_source/v0_skeleton/kernel
    python3 tools/kernel_digest.py --root .                       # 人读输出
    python3 tools/kernel_digest.py --root . --json                # 机器可读
    python3 tools/kernel_digest.py --root . --diff-before A --diff-after B
    python3 tools/kernel_digest.py --selftest                     # 判据自证（两条负例 + 一条正例）

退出码：0 = 成立；1 = 判据不成立（差集越界 / changed 非空）；2 = 用法错误。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent            # <v0_skeleton>/kernel/tools
KERNEL_ROOT = HERE.parent                          # <v0_skeleton>/kernel
V0_SKELETON = KERNEL_ROOT.parent                   # <v0_skeleton>
CANONICAL_JSON_PATH = V0_SKELETON / "tools" / "canonical_json.py"

EXCLUDED_DIRS = {".venv", "__pycache__", "tests"}
ADAPTER_DIRS = ("adapters/", "providers/adapters/")


def _load_hash_object():
    spec = importlib.util.spec_from_file_location("deephealing_canonical_json_digest", CANONICAL_JSON_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load canonical JSON module from {CANONICAL_JSON_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.hash_object


hash_object = _load_hash_object()


def kernel_digest(root: Path) -> dict:
    """内核源码指纹：`{"files": {relpath: sha256}, "digest": hash_object(files)}`。"""
    root = Path(root)
    package_root = root / "deephealing_kernel"
    if not package_root.is_dir():
        raise FileNotFoundError(f"no deephealing_kernel package under {root}")
    files: dict[str, str] = {}
    for path in sorted(package_root.rglob("*.py")):
        rel_parts = path.relative_to(package_root).parts
        if any(part in EXCLUDED_DIRS for part in rel_parts):
            continue
        files["/".join(rel_parts)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"files": files, "digest": hash_object(files)}


def diff_snapshots(before: dict, after: dict) -> dict:
    """before/after 差集（relpath 相对 `deephealing_kernel/`）。"""
    before_files, after_files = before["files"], after["files"]
    return {
        "changed": sorted(
            rel for rel in set(before_files) & set(after_files) if before_files[rel] != after_files[rel]
        ),
        "added": sorted(set(after_files) - set(before_files)),
        "removed": sorted(set(before_files) - set(after_files)),
        "digest_before": before["digest"],
        "digest_after": after["digest"],
    }


def criterion_ok(diff: dict) -> tuple[bool, list[str]]:
    """新增能力零内核改动判据：`changed == []` 且 `added` 全部落在 adapter 目录并集内。"""
    reasons: list[str] = []
    if diff["changed"]:
        reasons.append(f"changed is not empty: {diff['changed']}")
    if diff["removed"]:
        reasons.append(f"removed is not empty: {diff['removed']}")
    out_of_bounds = [
        rel for rel in diff["added"] if not any(rel.startswith(prefix) for prefix in ADAPTER_DIRS)
    ]
    if out_of_bounds:
        reasons.append(f"added outside adapter dirs {ADAPTER_DIRS}: {out_of_bounds}")
    return (not reasons), reasons


def _copy_tree(src: Path, dst: Path) -> Path:
    import shutil

    package = dst / "deephealing_kernel"
    if package.exists():
        shutil.rmtree(package)
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src / "deephealing_kernel", package,
                    ignore=shutil.ignore_patterns(*EXCLUDED_DIRS, "*.pyc"))
    return dst


def _flip_byte(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[0] ^= 0x01
    path.write_bytes(bytes(data))


def cmd_selftest(_args) -> int:
    """判据自证：① 正例（adapter 目录新增）成立；② 改 tick.py 一字节必红；③ 包根新增 .py 必红。"""
    before = kernel_digest(KERNEL_ROOT)
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="kd_selftest_") as tmp:
        tmp_root = Path(tmp)

        ok_root = _copy_tree(KERNEL_ROOT, tmp_root / "ok")
        (ok_root / "deephealing_kernel" / "adapters" / "relation_infer.py").write_text(
            "# 新能力的 provider 适配器（隔离副本夹具）\n", encoding="utf-8"
        )
        ok_ok, ok_reasons = criterion_ok(diff_snapshots(before, kernel_digest(ok_root)))
        print(f"[① 正例 adapter 新增] ok={ok_ok} reasons={ok_reasons}")
        if not ok_ok:
            failures.append("positive case (adapter added) must satisfy the criterion")

        bad1_root = _copy_tree(KERNEL_ROOT, tmp_root / "bad1")
        _flip_byte(bad1_root / "deephealing_kernel" / "tick.py")
        diff1 = diff_snapshots(before, kernel_digest(bad1_root))
        ok1, reasons1 = criterion_ok(diff1)
        print(f"[② 负例 改 tick.py 一字节] changed={diff1['changed']} ok={ok1} reasons={reasons1}")
        if ok1 or diff1["changed"] != ["tick.py"]:
            failures.append("negative case (tick.py byte flip) must fail the criterion with changed=['tick.py']")

        bad2_root = _copy_tree(KERNEL_ROOT, tmp_root / "bad2")
        (bad2_root / "deephealing_kernel" / "extra_module.py").write_text("# 包根新增\n", encoding="utf-8")
        diff2 = diff_snapshots(before, kernel_digest(bad2_root))
        ok2, reasons2 = criterion_ok(diff2)
        print(f"[③ 负例 包根新增 .py] added={diff2['added']} ok={ok2} reasons={reasons2}")
        if ok2 or diff2["added"] != ["extra_module.py"]:
            failures.append("negative case (root-level .py) must fail the criterion with added=['extra_module.py']")

        pv_root = _copy_tree(KERNEL_ROOT, tmp_root / "providers_adapters")
        (pv_root / "deephealing_kernel" / "providers" / "adapters").mkdir(parents=True, exist_ok=True)
        (pv_root / "deephealing_kernel" / "providers" / "adapters" / "x.py").write_text("# 夹具\n", encoding="utf-8")
        diff3 = diff_snapshots(before, kernel_digest(pv_root))
        ok3, reasons3 = criterion_ok(diff3)
        print(f"[④ 正例 providers/adapters/ 并集] added={diff3['added']} ok={ok3} reasons={reasons3}")
        if not ok3:
            failures.append("REQ-literal path providers/adapters/ must be accepted (union criterion)")

    if failures:
        for failure in failures:
            print(f"E_SELFTEST: {failure}", file=sys.stderr)
        return 1
    print("selftest: OK (1 positive + 2 mandatory negatives + 1 union positive)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kernel_digest.py")
    parser.add_argument("--root", default=str(KERNEL_ROOT), help="内核根目录（含 deephealing_kernel/）")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    parser.add_argument("--diff-before", default=None, help="before 快照根目录")
    parser.add_argument("--diff-after", default=None, help="after 快照根目录")
    parser.add_argument("--selftest", action="store_true", help="跑判据自证（正例 + 两条强制负例）")
    args = parser.parse_args(argv)

    if args.selftest:
        return cmd_selftest(args)

    root = Path(args.root).resolve()
    before = kernel_digest(root)
    if args.json:
        print(json.dumps({"root": str(root), "files": len(before["files"]), "digest": before["digest"]},
                         ensure_ascii=False, sort_keys=True))
    else:
        print(f"kernel_digest root={root} files={len(before['files'])} digest={before['digest']}")
        for rel in sorted(before["files"]):
            print(f"  {rel} {before['files'][rel]}")

    if args.diff_before and args.diff_after:
        diff = diff_snapshots(kernel_digest(Path(args.diff_before)), kernel_digest(Path(args.diff_after)))
        ok, reasons = criterion_ok(diff)
        print(json.dumps({"diff": diff, "criterion_ok": ok, "reasons": reasons}, ensure_ascii=False, sort_keys=True))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
