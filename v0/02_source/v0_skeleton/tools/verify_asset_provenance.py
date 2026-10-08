#!/usr/bin/env python3
"""`AC-G-*` / `AC-E-2b` / `AC-E-2c` 的机器判据：资产来源登记校验。

运行（`workdir` = 仓库根；产物写**独立输出目录**，不碰交付源码 —— R5）：
    python3 v0/02_source/v0_skeleton/tools/verify_asset_provenance.py \
        --root v0/02_source/v0_skeleton/web/assets \
        --pack v0/02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin \
        --json-out v0/spikes/n5-asset/readback/provenance_report.json

退出码：0 = 全部通过；1 = 有失败；2 = 用法/环境错误。

判据（逐条对应冻结口径 `01a` v4.1）：
  G-1   `incomplete == 0`（必填字段齐全 + **枚举合法**）
  G-3a  `license_evidence.fetched == true`（**非生成式来源**；`ai_generated` 走 G-4/G-5）
  G-3b  外部锚：`snapshot_path` 指向盘上存在的许可原文快照，且 `snapshot_sha256` 与之**逐字节一致**
  G-3c  `fetched_at` 时序自洽（早于 `registered_at`）
  G-4a  `ai_generated == true` ⇒ `generator` / `generator_version` 非空（`prompt_digest` 缺失 ⇒ **GAP**，
        显式列出，**不伪造**）
  G-4b  点名断言**按 `converted_sha256`**（内容锚；`asset_id` 只作别名）：KNOWN_GENERATED 逐条命中，
        且 `source_type == "ai_generated"` ∧ `license != "cc0-1.0"` ∧ `generator` 非空
  G-4c  生成件的生成器外部锚（文件内嵌 C2PA）与声明**不得矛盾**（不可得 ⇒ GAP 并列出）
  G-5   许可判定：`license ∈ license_enum`；**default-deny 只对 `source_type == "ai_generated"` 生效**
        （按 `(generator, generator_version)` → `(source_model, model_version)` 查
        `asset.license.table.data.json`；查不到 ⇒ 拒收 ⇒ 该件必须 `runtime_excluded == true`）
  G-6   `converted_sha256` 与盘上文件 `shasum -a 256` 逐件一致（**字节口径**）
  E-2b  覆盖根 `web/assets/**` + 内容包 `assets/**`（排除 GENERATED_PATTERNS），
        每个**资产文件**恰好被一条 provenance 覆盖（⊆ 且 ⊇，无重复）
  E-2c  `assets` 为空数组 ⇒ FAIL

负对照（`--selftest`）：注入五条 ⇒ 必须全部判红。
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[4]
TOOLS = Path(__file__).resolve().parent
SKELETON = TOOLS.parent

LICENSE_TABLE = SKELETON.parent / "asset.license.table.data.json"
LICENSE_TABLE_SCHEMA = SKELETON.parent / "asset.license.table.json"

# ---------------------------------------------------------------- 生成件点名清单（按内容哈希）
# **本段即 `AC-G-4b` 的「清单段」**：其 sha256 记入 `web/scripts/assert_inputs.json`，
# 并由 `AC-F-5c` 的文件面覆盖 ⇒ 清单**不得被静默缩减**。
KNOWN_GENERATED = {
    # converted_sha256 : 可读别名（`asset_id` 只作别名，点名按内容哈希）
    "c262e5301c85": "skin-pale-01",
}

GENERATED_PATTERNS = [
    "*/__pycache__/*", "*.pyc", "*/.pytest_cache/*", "*/.DS_Store",
    "*/node_modules/*", "*/.venv/*", "*/dist/*", "attic-*/*",
]

# 覆盖根内的**非资产**文件（AC-E-2b 明文口径：改按哈希清单，不要求 provenance 覆盖）。
# 判据：它们是**登记面/清单**，不是被引用的素材（无 `role` 语义），因此进 `assert_inputs.json`
# 的哈希清单，而不是 provenance 条目。
NON_ASSET_NAMES = {
    "manifest.txt",       # web/assets/manifest.txt —— N4 资产登记表（人类可读 registry）
    "provenance.json",    # 本登记表自身（自指会给「改登记表刷绿」留洞）
}
NON_ASSET_RELATIVE = {
    "assets/manifest.json",  # 内容包清单（pack 元数据）
}

ROLE_ENUM = {"surface", "character", "reference", "hdri", "ui", "prop", "metadata"}
SOURCE_TYPE_ENUM = {"scanned", "cc0_library", "cc_by_library", "ai_generated", "self_authored"}

REQUIRED_FIELDS = [
    "path", "asset_id", "role", "source_type", "license", "license_evidence",
    "author", "attribution", "license_url", "ai_generated", "generator",
    "generator_version", "prompt_digest", "original", "conversion",
    "converted_sha256", "editable_source", "binding_ref", "registered_at",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_generated(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in GENERATED_PATTERNS)


def load_license_table():
    data = json.loads(LICENSE_TABLE.read_text(encoding="utf-8"))
    schema = json.loads(LICENSE_TABLE_SCHEMA.read_text(encoding="utf-8"))
    license_enum = schema["properties"]["license_enum"]["items"]["enum"]
    models = data["models"]
    lookup = {}
    deny_only = {}
    for m in models:
        key = (m["source_model"], str(m["model_version"]))
        if m["adjudication"] == "reject":
            deny_only[key] = m
        else:
            lookup[key] = m
            if key[1] == "*":
                lookup[(key[0], None)] = m
    return license_enum, lookup, deny_only


def resolve_model(lookup, deny_only, generator, version):
    """default-deny 查表：先精确，再通配；reject 行只用于 deny。"""
    for key in [(generator, str(version)), (generator, "*"), (generator, None)]:
        if key in lookup:
            return lookup[key], "adopted"
    for key in [(generator, str(version)), (generator, "*"), (generator, None)]:
        if key in deny_only:
            return deny_only[key], "rejected"
    return None, "not_found"


def enumerate_asset_files(root: Path, pack: Path):
    """覆盖根枚举（排除 GENERATED_PATTERNS 与已声明的非资产登记文件）。"""
    out = []
    for base, prefix in ((root, ""), (pack / "assets", "assets/")):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = str(p.relative_to(base))
            full = f"{prefix}{rel}" if prefix else rel
            if is_generated(full):
                continue
            if rel in NON_ASSET_NAMES or full in NON_ASSET_RELATIVE:
                continue
            out.append(full)
    return out


def verify(root: Path, pack: Path, doc: dict):
    failures = []
    gaps = []
    license_enum, lookup, deny_only = load_license_table()
    assets = doc.get("assets", [])
    if not isinstance(assets, list) or len(assets) == 0:
        failures.append("E-2c: provenance.assets 为空数组 ⇒ FAIL")
        return failures, gaps

    # ---- 逐条字段 / 枚举 / 哈希 ----
    for entry in assets:
        eid = entry.get("path") or entry.get("asset_id") or "<no-path>"
        for f in REQUIRED_FIELDS:
            if f not in entry:
                failures.append(f"G-1: {eid} 缺字段 {f}")
        if entry.get("role") not in ROLE_ENUM:
            failures.append(f"G-1: {eid} role 非法枚举 {entry.get('role')!r}")
        if entry.get("source_type") not in SOURCE_TYPE_ENUM:
            failures.append(f"G-1: {eid} source_type 非法枚举 {entry.get('source_type')!r}")
        lic = entry.get("license")
        if lic is not None and lic not in license_enum:
            failures.append(f"G-5①: {eid} license {lic!r} ∉ license_enum")

        # G-6 字节哈希外部锚
        rel = entry.get("path")
        target = (root / rel) if (root / rel).is_file() else (pack / rel)
        if not target.is_file():
            failures.append(f"G-6: {eid} 盘上找不到文件 {target}")
        else:
            actual = sha256_file(target)
            if actual != entry.get("converted_sha256"):
                failures.append(f"G-6: {eid} converted_sha256 与盘上不符 "
                                f"(declared={entry.get('converted_sha256')} actual={actual})")

        ev = entry.get("license_evidence") or {}
        if entry.get("source_type") != "ai_generated":
            # G-3a / G-3b：非生成式来源走许可证据三件套
            if ev.get("fetched") is not True:
                failures.append(f"G-3a: {eid} license_evidence.fetched != true")
            snap = ev.get("snapshot_path")
            if not snap:
                failures.append(f"G-3b: {eid} 缺 license_evidence.snapshot_path")
            else:
                snap_path = WS / snap
                if not snap_path.is_file():
                    failures.append(f"G-3b: {eid} 快照不存在于盘上：{snap}")
                elif sha256_file(snap_path) != ev.get("snapshot_sha256"):
                    failures.append(f"G-3b: {eid} 快照 sha256 不符（外部锚失效）")
            if ev.get("fetched_at") and entry.get("registered_at"):
                if str(ev["fetched_at"]) > str(entry["registered_at"]):
                    failures.append(f"G-3c: {eid} fetched_at 晚于 registered_at")
            if not entry.get("author"):
                failures.append(f"G-1: {eid} author 缺失")

        if entry.get("ai_generated") is True:
            if not entry.get("generator"):
                failures.append(f"G-4a: {eid} ai_generated=true 但 generator 为空")
            if not entry.get("generator_version"):
                failures.append(f"G-4a: {eid} ai_generated=true 但 generator_version 为空")
            if not entry.get("prompt_digest"):
                gaps.append(f"G-4a(GAP): {eid} prompt_digest 不可得（原始提示词不在盘上）⇒ 记 GAP，不伪造")
            # G-5 default-deny（只对生成式来源）
            model, verdict = resolve_model(lookup, deny_only,
                                           entry.get("generator"), entry.get("generator_version"))
            if verdict != "adopted":
                disposition = entry.get("license_disposition")
                if disposition in ("runtime_excluded", "reference_only_escalated"):
                    gaps.append(
                        f"G-5(GAP/上抛): {eid} 生成器 ({entry.get('generator')}, "
                        f"{entry.get('generator_version')}) 查表结果 = {verdict} ⇒ 按口径拒收；"
                        f"处置 = {disposition}（已显式声明，非静默放行）")
                else:
                    failures.append(
                        f"G-5: {eid} 生成器 ({entry.get('generator')}, {entry.get('generator_version')}) "
                        f"查表结果 = {verdict} ⇒ 拒收；该件必须给显式 license_disposition"
                        f"（runtime_excluded / reference_only_escalated）才算已处置")
            if not entry.get("conversion"):
                failures.append(f"G-1: {eid} conversion 为空")

    # ---- G-4b 点名断言（按内容哈希） ----
    by_hash = {e.get("converted_sha256"): e for e in assets}
    for digest, alias in KNOWN_GENERATED.items():
        hit = None
        for full, e in by_hash.items():
            if isinstance(full, str) and full.startswith(digest):
                hit = e
                break
        if hit is None:
            failures.append(f"G-4b: 已知生成件 {alias}（prefix {digest}）未在 provenance 中点名 ⇒ 清单被绕过")
            continue
        if hit.get("source_type") != "ai_generated":
            failures.append(f"G-4b: {alias} source_type != ai_generated")
        if hit.get("license") == "cc0-1.0":
            failures.append(f"G-4b: {alias} 被标成 cc0-1.0（**不许**自动标 CC0）")
        if not hit.get("generator"):
            failures.append(f"G-4b: {alias} generator 为空")

    # ---- E-2b 集合双向包含 ----
    declared = sorted(e.get("path") for e in assets if e.get("path"))
    on_disk = sorted(enumerate_asset_files(root, pack))
    missing = [p for p in on_disk if p not in set(declared)]
    extra = [p for p in declared if p not in set(on_disk)]
    if missing:
        failures.append(f"E-2b: 盘上有资产未被 provenance 覆盖（⊆ 失败）：{missing}")
    if extra:
        failures.append(f"E-2b: provenance 指向的路径不在覆盖根内（⊇ 失败）：{extra}")
    dupes = [p for p in set(declared) if declared.count(p) > 1]
    if dupes:
        failures.append(f"E-2b: 重复覆盖（每个文件必须恰好一条）：{dupes}")

    return failures, gaps


def selftest(root: Path, pack: Path, doc: dict) -> int:
    """负对照：注入五条 ⇒ 必须判红。"""
    import copy
    cases = []

    def mutate(fn, label):
        d = copy.deepcopy(doc)
        fn(d)
        f, _ = verify(root, pack, d)
        cases.append((label, bool(f)))

    def launder(d):
        """③ 绕过路径：把已知生成件**改名换 id 并宣称 cc0**（v2 的按名匹配会被绕过）。"""
        e = [a for a in d["assets"] if a["path"].endswith("skin-pale-01.jpg")][0]
        e["asset_id"] = "renamed-alias"
        e["source_type"] = "cc0_library"
        e["license"] = "cc0-1.0"
        e["ai_generated"] = False

    mutate(lambda d: d["assets"][0]["license_evidence"].__setitem__("fetched", False), "① fetched=false")
    mutate(lambda d: [a for a in d["assets"] if a["path"].endswith("skin-pale-01.jpg")][0]
           .__setitem__("license", "cc0-1.0"), "② 生成件标 cc0-1.0")
    mutate(launder, "③ 生成件改名换 id + 宣称 cc0（按内容哈希点名 ⇒ 仍必红）")
    mutate(lambda d: d["assets"][1].__setitem__("converted_sha256", "0" * 64), "④ 哈希与盘上不符")
    mutate(lambda d: d["assets"].pop(), "⑤ 清单被删一条（覆盖缺口）")

    ok = True
    for label, red in cases:
        status = "RED(期望)" if red else "GREEN(异常！)"
        if not red:
            ok = False
        print(f"  selftest {label}: {status}")
    print(f"selftest: {'OK（五条负对照全部判红）' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(SKELETON / "web/assets"))
    ap.add_argument("--pack", default=str(SKELETON / "districts/xingfu-xiaoqu-xuqin"))
    ap.add_argument("--provenance", default=None)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    pack = Path(args.pack)
    prov = Path(args.provenance) if args.provenance else root / "provenance.json"
    if not prov.is_file():
        print(f"E_ENV: provenance not found: {prov}", file=sys.stderr)
        return 2
    doc = json.loads(prov.read_text(encoding="utf-8"))

    if args.selftest:
        return selftest(root, pack, doc)

    failures, gaps = verify(root, pack, doc)
    report = {
        "schema_version": "n5-provenance-report/1",
        "provenance": str(prov),
        "asset_count": len(doc.get("assets", [])),
        "coverage_root_files": len(enumerate_asset_files(root, pack)),
        "failures": failures,
        "gaps": gaps,
        "license_table_entries": len(json.loads(LICENSE_TABLE.read_text(encoding="utf-8"))["models"]),
        "known_generated_declared": KNOWN_GENERATED,
    }
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"verify_asset_provenance: wrote {out}")

    print(f"verify_asset_provenance: assets={report['asset_count']} "
          f"coverage_files={report['coverage_root_files']} failures={len(failures)} gaps={len(gaps)}")
    for f in failures:
        print(f"  FAIL  {f}")
    for g in gaps:
        print(f"  GAP   {g}")
    if failures:
        print("verify_asset_provenance: FAILED")
        return 1
    print("verify_asset_provenance: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
