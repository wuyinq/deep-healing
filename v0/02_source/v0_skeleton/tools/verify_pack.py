#!/usr/bin/env python3
"""逐文件比对 pack.sig（内容包完整性校验）。

**定位（F9 / RR3-13 收口，必读）**：本脚本是 `pack.sig` 的**完整性校验器**，
**不是**资产管线的权威校验器 —— 资产 / manifest / 许可 / `review_status` / 元数据剥离面的
**权威校验器**是 `tools/verify_asset_pack.py`（见 `content-pipeline.spec.md` §7）。
`verify_specs.sh` 仍调用本脚本，但只用于「pack.sig 与盘上文件逐条一致」这一件事。

用法：
    python3 tools/verify_pack.py <pack_dir>

退出码：0 = 全部一致；1 = 有不一致（缺文件/多文件/哈希不符/字节数不符/含可执行文件）；2 = 用法错误或 pack.sig 缺失。

**可执行文件判据（RM-13 收口：只按后缀名拦可被改名绕过）**：**后缀名** 与 **内容魔数** 双判据，
任一命中即拒收（ELF / PE / Mach-O / shebang 脚本 / Python 字节码）。

对应设计：district.pack.spec.md §2 第 5 步；`kernel validate --pack <dir>` 的签名校验部分。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FORBIDDEN_SUFFIXES = {".py", ".js", ".ts", ".sh", ".rb", ".pl", ".exe", ".so", ".dylib"}
# 内容魔数（逐条列明；不按后缀名，改后缀名同样被拦）。
EXECUTABLE_MAGICS = (
    (b"\x7fELF", "ELF"),
    (b"MZ", "PE"),
    (b"\xfe\xed\xfa\xce", "Mach-O 32 BE"),
    (b"\xfe\xed\xfa\xcf", "Mach-O 64 BE"),
    (b"\xce\xfa\xed\xfe", "Mach-O 32 LE"),
    (b"\xcf\xfa\xed\xfe", "Mach-O 64 LE"),
    (b"\xca\xfe\xba\xbe", "Mach-O universal"),
    (b"#!", "shebang 脚本"),
    (b"\x03\xf3\x0d\x0a", "Python 字节码"),
    (b"\x0d\x0d\x0a", "Python 字节码（PEP 552）"),
)


def executable_kind(path: Path) -> str | None:
    """按**内容魔数**判断可执行容器；命中返回其名字，否则 None。"""
    try:
        with path.open("rb") as handle:
            head = handle.read(8)
    except OSError:
        return None
    for magic, name in EXECUTABLE_MAGICS:
        if head.startswith(magic):
            return name
    return None


def sha256_of(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: verify_pack.py <pack_dir>", file=sys.stderr)
        return 2
    pack_dir = Path(argv[1]).resolve()
    sig_path = pack_dir / "pack.sig"
    if not sig_path.is_file():
        print(f"E_PACK_INVALID: missing pack.sig in {pack_dir}", file=sys.stderr)
        return 2

    signature = json.loads(sig_path.read_text(encoding="utf-8"))
    declared = {entry["path"]: entry for entry in signature["entries"]}

    actual: dict[str, dict] = {}
    for path in sorted(pack_dir.rglob("*")):
        if not path.is_file() or path.name == "pack.sig":
            continue
        suffix_hit = path.suffix in FORBIDDEN_SUFFIXES
        magic_hit = executable_kind(path)
        if suffix_hit or magic_hit:
            criteria = " + ".join(filter(None, ["后缀名" if suffix_hit else "",
                                                f"内容魔数={magic_hit}" if magic_hit else ""]))
            print(f"E_PACK_INVALID: executable file in content pack: {path}（判据：{criteria}）", file=sys.stderr)
            return 1
        rel = path.relative_to(pack_dir).as_posix()
        digest, size = sha256_of(path)
        actual[rel] = {"sha256": digest, "bytes": size}

    problems: list[str] = []
    for rel, entry in sorted(declared.items()):
        if rel not in actual:
            problems.append(f"missing_file: {rel}")
            continue
        if actual[rel]["sha256"] != entry["sha256"]:
            problems.append(f"hash_mismatch: {rel} expected={entry['sha256']} actual={actual[rel]['sha256']}")
        elif "bytes" in entry and actual[rel]["bytes"] != entry["bytes"]:
            problems.append(f"size_mismatch: {rel} expected={entry['bytes']} actual={actual[rel]['bytes']}")
    for rel in sorted(set(actual) - set(declared)):
        problems.append(f"undeclared_file: {rel}")

    if problems:
        for problem in problems:
            print(f"E_PACK_SIG_MISMATCH: {problem}", file=sys.stderr)
        print(f"verify_pack: FAIL ({len(problems)} problems, {len(declared)} declared, {len(actual)} present)")
        return 1

    print(f"verify_pack: OK ({len(declared)} files, pack_id={signature['pack_id']} version={signature['pack_version']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
