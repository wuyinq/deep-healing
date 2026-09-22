#!/usr/bin/env python3
"""生成 district pack 的 pack.sig（内容包完整性清单）。

用法：
    python3 tools/pack_sign.py <pack_dir>

行为：
  - 遍历 pack 目录内所有普通文件（排除 pack.sig 自身），按 POSIX 相对路径字典序排列；
  - 逐文件算 sha256 与字节数，写入 <pack_dir>/pack.sig；
  - 拒绝包含可执行代码后缀的文件（内容层只有数据）。

对应设计：district.pack.spec.md §2 第 5 步；`kernel pack sign <dir>` 的最小可用实现。

**加固（M2 / P-5；只加强，不改语义）**：
  1. 可执行判据由「只按后缀名」升级为「**后缀名 + 内容魔数**」双判据（与 `tools/verify_pack.py`
     同一算法，由 `tests/test_pack_validate.py::test_pack_sign_and_verify_use_same_executable_criteria`
     逐条断言防漂移）。改名 `.txt` 的 shebang / ELF 内容不再能绕过写侧。
  2. **符号链接守卫**（写侧）：
     - pack 内任一文件解析后越出 pack 根 ⇒ 拒收（原先 `rglob` + `is_file()` 会跟随链接，
       把**包外**文件内容当成包内内容签名 —— 那会让 `pack.sig` 成为「包外内容哈希」的载体）；
     - `pack.sig` 自身是**符号链接** ⇒ 拒收（否则 `write_text` 会跟随链接**改写 pack 外文件**）。
  CLI 形态、退出码约定（0 成功 / 1 拒收 / 2 用法错误）与 `pack.sig` 格式**逐字不变**。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FORBIDDEN_SUFFIXES = {".py", ".js", ".ts", ".sh", ".rb", ".pl", ".exe", ".so", ".dylib"}
# 内容魔数（逐条列明；不按后缀名，改后缀名同样被拦）。与 tools/verify_pack.py 同一算法。
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
    """按**内容魔数**判断可执行容器；命中返回其名字，否则 None（与 tools/verify_pack.py 一致）。"""
    try:
        with path.open("rb") as handle:
            head = handle.read(8)
    except OSError:
        return None
    for magic, name in EXECUTABLE_MAGICS:
        if head.startswith(magic):
            return name
    return None


def _assert_within_root(path: Path, root: Path) -> None:
    """**符号链接守卫**：解析真实路径后必须仍位于 pack 根之内。

    与 `deephealing_kernel/pack.py::_assert_within_root` 同一口径：包**内**目标的符号链接合法，
    越出 pack 根的链接一律 `E_PACK_INVALID`。
    """
    resolved = path.resolve()
    root_resolved = root.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise SystemExit(
            f"E_PACK_INVALID: symlink escape: {path} resolves to {resolved} "
            f"which is outside pack root {root_resolved}"
        )


def sha256_of(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def build_signature(pack_dir: Path) -> dict:
    pack_dir = Path(pack_dir).resolve()
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.is_file():
        raise SystemExit(f"E_PACK_INVALID: missing pack.json in {pack_dir}")
    _assert_within_root(manifest_path, pack_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    entries = []
    for path in sorted(pack_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "pack.sig":
            continue
        # 符号链接守卫（写侧）：`rglob`/`is_file` 跟随链接 ⇒ 必须先解析真实路径再判越界
        _assert_within_root(path, pack_dir)
        suffix_hit = path.suffix in FORBIDDEN_SUFFIXES
        magic_hit = executable_kind(path)
        if suffix_hit or magic_hit:
            criteria = " + ".join(filter(None, ["后缀名" if suffix_hit else "",
                                                f"内容魔数={magic_hit}" if magic_hit else ""]))
            raise SystemExit(f"E_PACK_INVALID: executable file in content pack: {path}（判据：{criteria}）")
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


def write_signature(pack_dir: Path, signature: dict) -> Path:
    """写 `pack.sig`（**唯一写入点**，供 CLI 与本脚本共用）。

    **写侧符号链接守卫**：`pack.sig` 若是指向 pack 外文件的符号链接，`write_text` 会跟随链接
    **改写 pack 外文件** ⇒ 必须先拒收。目标文件因此**逐字节不变**（U11 B 证第 ② 条）。
    """
    pack_dir = Path(pack_dir).resolve()
    out = pack_dir / "pack.sig"
    if out.is_symlink():
        raise SystemExit(
            f"E_PACK_INVALID: refusing to write pack.sig through a symlink: {out} -> {out.resolve()}"
        )
    _assert_within_root(out, pack_dir)
    out.write_text(json.dumps(signature, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: pack_sign.py <pack_dir>", file=sys.stderr)
        return 2
    pack_dir = Path(argv[1]).resolve()
    signature = build_signature(pack_dir)
    out = write_signature(pack_dir, signature)
    print(f"wrote {out} entries={len(signature['entries'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
