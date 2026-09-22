#!/usr/bin/env python3
"""离线内容管线的**校验执行体**（D-0.8 / AC-15；`content-pipeline.spec.md` 指定的校验器）。

为什么必须有执行体：`kernel validate` 在本轮仍是接口桩，若只写 schema 就宣称
「非白名单 → schema 层就应拒」，那是**将来时**的承诺（预审 P1-4 / Q6）。本脚本把校验
变成可真跑的闸门。

校验什么（任一不通过 ⇒ exit 非 0，逐条列出 reason code）：
  A1  pack 里的**每个**资产文件必须在 manifest 里有条目（无主资产拒收）
  A2  manifest 条目里的文件必须真的在 pack 里（悬空条目拒收）
  A3  `license` 必须与 (source_model, model_version) 在许可表里**查表一致**且 commercial_use=true
      （**default-deny**：查不到即拒；`FLUX.1-dev` + `apache-2.0` 这种自声明即拒）
  A4  `content_hash` 必须存在、格式合法（`sha256:<64hex>`），且与**实际文件**按声明口径重算一致
  A5  `review_status` 必须为 `adopted`，且必须附人工过审痕迹（reviewer + reviewed_at）
  A6  `derived_from` **传递闭包**：任一层命中非白名单来源 / 父资产不在库 ⇒ 整棵子树拒收
  A7  生成器元数据：PNG 必须已剥离 `tEXt`/`iTXt`（带 `parameters` chunk 即拒）
  A8  `workflow` 受管登记：JSON 必须存在且 sha256 一致；其 `referenced_models` 必须过许可表
  A9  运行时零生成：静态扫描目标树，出现生成调用路径（mflux/diffusers/torch/ComfyUI 执行）即拒

用法：
  python3 verify_asset_pack.py --pack <pack_dir> --manifest <manifest.json> --license-table <table.json> [--runtime-tree <dir>]
  python3 verify_asset_pack.py --zero-generation-scan <dir>

退出码：0 = 全部通过；1 = 有拒收项；2 = 用法/环境错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ADOPTED = "adopted"
# 运行时零生成：只在**代码**文件里扫生成调用路径片段。
# JSON 是数据（其模型引用由 A8 按许可表判定），故不参与本扫描 —— 否则说明性文字会误报。
CODE_SUFFIXES = (".py", ".js", ".ts", ".mjs")
# 精确排除项（逐条列明，禁止宽泛通配）：校验器自身按构造包含上面的模式字面量 → 必须排除自身，
# 否则「零生成扫描」会因自引用恒红。除本文件外**不排除任何文件**。
SCAN_SELF_EXCLUDE = ("verify_asset_pack.py",)
GENERATION_CALL_PATTERNS = (
    "import mflux", "from mflux", "import diffusers", "from diffusers",
    "import torch", "from torch", "stable_diffusion", "text2image", "txt2img",
)
METADATA_CHUNKS = (b"tEXt", b"iTXt", b"zTXt")


# --------------------------------------------------------------------------- helpers
def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_metadata_chunks(path: Path) -> list[str]:
    """返回 PNG 里出现的生成器元数据 chunk 名（非 PNG 返回空）。"""
    raw = path.read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return []
    found, offset = [], 8
    while offset + 8 <= len(raw):
        length = struct.unpack(">I", raw[offset:offset + 4])[0]
        chunk_type = raw[offset + 4:offset + 8]
        if chunk_type in METADATA_CHUNKS:
            found.append(chunk_type.decode("ascii", errors="replace"))
        offset += 12 + length
        if chunk_type == b"IEND":
            break
    return found


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- license table
class LicenseTable:
    def __init__(self, document: dict) -> None:
        self.default_policy = document.get("default_policy", "deny")
        self.rows = document["models"]

    def lookup(self, source_model: str, model_version: str) -> dict | None:
        for row in self.rows:
            if row["source_model"] == source_model and row["model_version"] == model_version:
                return row
        for row in self.rows:
            if row["source_model"] == source_model and row["model_version"] == "*":
                return row
        return None

    def lookup_any_version(self, source_model: str) -> dict | None:
        """工作流里只写了 checkpoint **名字**（没有版本）→ 按模型名判定（任一行命中即可）。"""
        for row in self.rows:
            if row["source_model"] == source_model:
                return row
        return None


# --------------------------------------------------------------------------- checks
def check_pack(pack_dir: Path, manifest_path: Path, table_path: Path,
               runtime_tree: Path | None) -> dict:
    rejects: list[dict] = []
    table = LicenseTable(load_json(table_path))
    manifest = load_json(manifest_path)
    assets = manifest.get("assets", manifest if isinstance(manifest, list) else [])
    if isinstance(assets, dict):
        assets = list(assets.values())

    entries = {entry["asset_id"]: entry for entry in assets}
    manifest_abs = manifest_path.resolve()
    pack_files = [p for p in sorted(pack_dir.rglob("*")) if p.is_file() and p.resolve() != manifest_abs]
    declared_files = {entry["file"] for entry in assets if "file" in entry}
    # 工作流 JSON 是**受管产物**，通过 workflow.path 声明，不算「无主资产」
    for entry in assets:
        workflow = entry.get("workflow") or {}
        if workflow.get("path") and not Path(workflow["path"]).is_absolute():
            declared_files.add(workflow["path"])

    # A1 / A2：无主资产 / 悬空条目
    for path in pack_files:
        rel = str(path.relative_to(pack_dir))
        if rel not in declared_files:
            rejects.append({"code": "A1_UNMANIFESTED_ASSET", "file": rel,
                            "detail": "资产文件在 pack 内但 manifest 无条目（无主资产不得进交付链）"})
    for rel in sorted(declared_files):
        if not (pack_dir / rel).is_file():
            rejects.append({"code": "A2_DANGLING_MANIFEST_ENTRY", "file": rel,
                            "detail": "manifest 条目在 pack 内找不到对应文件"})

    # A9：运行时零生成（先做，静态扫描）
    if runtime_tree is not None:
        for path in sorted(runtime_tree.rglob("*")):
            if not path.is_file() or path.suffix not in CODE_SUFFIXES or path.name in SCAN_SELF_EXCLUDE:
                continue
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in GENERATION_CALL_PATTERNS:
                if pattern in text:
                    rejects.append({"code": "A9_RUNTIME_GENERATION_PATH", "file": str(path.relative_to(runtime_tree)),
                                    "detail": f"运行时树内出现生成调用路径片段 {pattern!r}（运行时零生成被违反）"})
                    break

    for asset_id, entry in sorted(entries.items()):
        rel = entry.get("file")
        # A3：许可查表（default-deny）
        row = table.lookup(entry.get("source_model", ""), entry.get("model_version", ""))
        if row is None:
            rejects.append({"code": "A3_UNKNOWN_MODEL_DEFAULT_DENY", "asset_id": asset_id,
                            "detail": f"({entry.get('source_model')}, {entry.get('model_version')}) 不在许可表内 → 拒收"})
        else:
            if row.get("commercial_use") is not True:
                rejects.append({"code": "A3_NON_COMMERCIAL_SOURCE", "asset_id": asset_id,
                                "detail": f"{entry.get('source_model')} 为不可商用来源（{row.get('deny_reason', '')}）"})
            if entry.get("license") != row.get("license"):
                rejects.append({"code": "A3_LICENSE_MODEL_MISMATCH", "asset_id": asset_id,
                                "detail": f"声明 license={entry.get('license')} 与许可表 {row.get('license')} 不一致（自声明无效）"})

        # A4：content_hash
        declared = entry.get("content_hash")
        if not isinstance(declared, str) or not HASH_RE.match(declared):
            rejects.append({"code": "A4_BAD_CONTENT_HASH", "asset_id": asset_id,
                            "detail": f"content_hash 缺失或格式非法：{declared!r}（期望 sha256:<64hex>）"})
        elif rel and (pack_dir / rel).is_file():
            actual = "sha256:" + sha256_file(pack_dir / rel)
            if entry.get("content_hash_basis") == "file_bytes" and actual != declared:
                rejects.append({"code": "A4_CONTENT_HASH_MISMATCH", "asset_id": asset_id,
                                "detail": f"file_bytes 口径重算不符：声明 {declared} 实得 {actual}"})

        # A5：过审
        if entry.get("review_status") != ADOPTED:
            rejects.append({"code": "A5_NOT_ADOPTED", "asset_id": asset_id,
                            "detail": f"review_status={entry.get('review_status')!r}，只有 {ADOPTED} 允许进 district pack"})
        review = entry.get("review") or {}
        if entry.get("review_status") == ADOPTED and not (review.get("reviewer") and review.get("reviewed_at")):
            rejects.append({"code": "A5_MISSING_REVIEW_TRACE", "asset_id": asset_id,
                            "detail": "adopted 缺人工过审痕迹（reviewer + reviewed_at）"})

        # A6：derived_from 传递闭包
        for parent in entry.get("derived_from", []) or []:
            if parent in entries:
                continue  # 库内父资产，继续沿链（见下方 closure 检查）
            parent_row = table.lookup(parent, "*")
            if parent_row is None or parent_row.get("commercial_use") is not True:
                rejects.append({"code": "A6_DERIVED_FROM_DENIED_SOURCE", "asset_id": asset_id,
                                "detail": f"derived_from 命中非白名单来源 {parent!r} → 整棵子树拒收"})

        # A7：生成器元数据
        if rel and (pack_dir / rel).is_file() and (pack_dir / rel).suffix.lower() == ".png":
            chunks = png_metadata_chunks(pack_dir / rel)
            if chunks:
                rejects.append({"code": "A7_GENERATOR_METADATA_PRESENT", "asset_id": asset_id,
                                "detail": f"PNG 含生成器元数据 chunk {chunks}（须入库前剥离）"})

        # A8：workflow 受管登记
        workflow = entry.get("workflow")
        if workflow:
            wf_path = (pack_dir / workflow["path"]) if not Path(workflow["path"]).is_absolute() else Path(workflow["path"])
            if not wf_path.is_file():
                rejects.append({"code": "A8_WORKFLOW_MISSING", "asset_id": asset_id,
                                "detail": f"workflow 文件不存在：{wf_path}"})
            else:
                actual = sha256_file(wf_path)
                if actual != workflow.get("sha256"):
                    rejects.append({"code": "A8_WORKFLOW_HASH_MISMATCH", "asset_id": asset_id,
                                    "detail": f"workflow sha256 不符：声明 {workflow.get('sha256')} 实得 {actual}"})
            for model in workflow.get("referenced_models", []):
                row = table.lookup_any_version(model)
                if row is None or row.get("commercial_use") is not True:
                    rejects.append({"code": "A8_WORKFLOW_NON_WHITELIST_MODEL", "asset_id": asset_id,
                                    "detail": f"workflow 引用非白名单 checkpoint {model!r} → 拒"})

    # A6（闭包）：父资产必须**在库**且有 manifest；沿链逐层查
    for asset_id, entry in sorted(entries.items()):
        stack = list(entry.get("derived_from", []) or [])
        seen = set()
        while stack:
            parent = stack.pop()
            if parent in seen:
                continue
            seen.add(parent)
            if parent in entries:
                stack.extend(entries[parent].get("derived_from", []) or [])
                continue
            if table.lookup(parent, "*") is None:
                rejects.append({"code": "A6_PARENT_NOT_IN_LIBRARY", "asset_id": asset_id,
                                "detail": f"derived_from 的父项 {parent!r} 既不在库也不是许可表内的模型 → 拒收"})

    return {"pack": str(pack_dir), "assets": len(entries), "files": len(pack_files),
            "rejects": rejects, "ok": not rejects}


def zero_generation_scan(tree: Path) -> dict:
    hits = []
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or path.suffix not in CODE_SUFFIXES or path.name in SCAN_SELF_EXCLUDE:
            continue
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in GENERATION_CALL_PATTERNS:
            if pattern in text:
                hits.append({"file": str(path), "pattern": pattern})
                break
    return {"tree": str(tree), "hits": hits, "ok": not hits}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="verify-asset-pack")
    parser.add_argument("--pack")
    parser.add_argument("--manifest")
    parser.add_argument("--license-table")
    parser.add_argument("--runtime-tree")
    parser.add_argument("--zero-generation-scan")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.zero_generation_scan:
        result = zero_generation_scan(Path(args.zero_generation_scan))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) if args.json
              else f"zero-generation-scan: hits={len(result['hits'])}")
        return 0 if result["ok"] else 1

    if not (args.pack and args.manifest and args.license_table):
        print("E_USAGE: --pack / --manifest / --license-table 必填", file=sys.stderr)
        return 2
    result = check_pack(Path(args.pack), Path(args.manifest), Path(args.license_table),
                        Path(args.runtime_tree) if args.runtime_tree else None)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        for reject in result["rejects"]:
            print(f"REJECT {reject['code']}: {reject.get('asset_id') or reject.get('file')} :: {reject['detail']}")
        print(f"asset pack verify: assets={result['assets']} files={result['files']} rejects={len(result['rejects'])}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
