#!/usr/bin/env python3
"""生成 district pack 的 pack.sig（内容包完整性清单）。

用法：
    python3 tools/pack_sign.py <pack_dir>

行为：
  - 遍历 pack 目录内所有普通文件（排除 pack.sig 自身），按 POSIX 相对路径字典序排列；
  - 逐文件算 sha256 与字节数，写入 <pack_dir>/pack.sig；
  - 拒绝包含可执行代码后缀的文件（内容层只有数据）。

对应设计：district.pack.spec.md §2 第 5 步；`kernel pack sign <dir>` 的最小可用实现。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FORBIDDEN_SUFFIXES = {".py", ".js", ".ts", ".sh", ".rb", ".pl", ".exe", ".so", ".dylib"}


def sha256_of(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def build_signature(pack_dir: Path) -> dict:
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.is_file():
        raise SystemExit(f"E_PACK_INVALID: missing pack.json in {pack_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    entries = []
    for path in sorted(pack_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "pack.sig":
            continue
        if path.suffix in FORBIDDEN_SUFFIXES:
            raise SystemExit(f"E_PACK_INVALID: executable file in content pack: {path}")
        rel = path.relative_to(pack_dir).as_posix()
        digest, size = sha256_of(path)
        entries.append({"path": rel, "sha256": digest, "bytes": size})

    return {
        "algorithm": "sha256",
        "pack_id": manifest["id"],
        "pack_version": manifest["version"],
        "generated_by": "tools/pack_sign.py",
        "entries": entries,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: pack_sign.py <pack_dir>", file=sys.stderr)
        return 2
    pack_dir = Path(argv[1]).resolve()
    signature = build_signature(pack_dir)
    out = pack_dir / "pack.sig"
    out.write_text(json.dumps(signature, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} entries={len(signature['entries'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
