#!/usr/bin/env python3
"""NPC 外形契约校验器（N2 / W1d · REQ-20260924-002 的 AC-1 / AC-2 / AC-4 / AC-10）。

用法：
    python3 v0_skeleton/tools/verify_npc_appearance.py --root .            # 交付树读数
    python3 v0_skeleton/tools/verify_npc_appearance.py --root . --probe-only   # 只跑自证（/tmp 隔离副本）
    python3 v0_skeleton/tools/verify_npc_appearance.py --root . --json out.json

判据（**每条都能红**；读数逐条打印，末行给机器可读 JSON）：

  1. `schema_valid`            —— 每个带 `appearance` 的 NPC 文档过 `npc.appearance.schema.json`
                                  （真跑 jsonschema，不是存在性检查）。
  2. `every_field_has_provenance` —— 每个外形字段**恰好**有 `source_facts` 或 `design_fill: true`
                                  （互斥且必居其一：不得把设计补全冒充原著，也不得给原著事实加 design_fill）。
  3. `source_facts_resolve`    —— 每个 `source_facts` 编号在 `fidelity/05-character-dossiers.md` 内
                                  **存在**且**不是** `UNVERIFIED`（与 `check_chr_provenance.py` 同一口径）。
  4. `xuqin_required_fields`   —— 徐琴（`xingfu-xiaoqu-xuqin/npcs/npc-006.json`）必填项齐全，
                                  且面具数据含编号 `8` 与 `八号`。
  5. `xuqin_states_declared`   —— 日常态 / 面具态两态在场；`masked` 的谓词只读**既有 state 字段**
                                  （`target_entity_in = ["kitchen-01"]`，实机自然可达）。
  6. `appearance_provenance_is_nested` —— ① 顶层 `source_facts` / `source_fact_map` 的规范化摘要
                                  == **起点冻结锚**（逐字节未改）；② 顶层 map 里 `appearance.` 前缀的键
                                  **只**允许既有的两个旧键（`appearance.red_coat` / `appearance.scarlet_eyes`）
                                  —— 新外形项**不得**挂在顶层（否则会假绿）；③ `appearance` 内不得出现
                                  顶层 `source_facts` / `source_fact_map`。
  7. `residents_have_appearance` —— 北区 5 个住户各带**基础** `appearance`，且**全部**标 `design_fill`
                                  （住户通用人形；**不得**编造原著事实）。
  8. `main_pack_exempt_declared` —— 主包 5 个 NPC **不**带 `appearance`，且该状态被**显式**豁免声明覆盖
                                  （主包逐字节零改动 / 冻结锚）。任何**新** NPC 文档既无 `appearance`
                                  又不在豁免表内 ⇒ 必红。
  9. `character_refs_registered`（AC-10）—— 提案包 `assets/manifest.json` 的 `character_refs` 里
                                  徐琴角色参考表 ≥3 张、`asset_id` 唯一、`file` 真实存在、
                                  **每个** `derived_from` 目标都能解析到同文件内的 `asset_id`。
 10. `appearance_has_no_verbatim_paragraph` —— `appearance` 内不得出现引号包起来的原著正文长串
                                  （D-4 规则：引号内 CJK ≥24 且 ≥2 个句末/分句标点，或 CJK ≥60）。

**隔离纪律**：全部注入型负例都在 `/tmp` 的**整树副本**上执行（交付树零改动）。

**N2-r2（F-2 / F-3 / F-4）**：
  - `build` 改为**枚举**（`$defs/buildField`：slim / average / stocky）⇒ `build="quadruped"` 必红；
  - `states` 声明 `mask: true` ⇒ `mask` **条件必填**（schema 顶层 `allOf` 的 `if/then`）；
  - 取值一律 `isinstance(x, dict)` 守卫（`appearance` / `mask` / `mask.number` / `mask.number_label`）；
  - 注入 lambda 的 `KeyError` / `AttributeError` / `TypeError` / `IndexError` 一律转成 `BadInjection`：
    该 case 记 `skipped_anchor_missing`（`fired=false`），**整次运行归 `EXIT_BAD_INJECTION`**；
    **但 `evaluate()` 照跑** ⇒ 结构化读数（哪条判据因何变红）不丢（此前是未捕获 traceback、
    既无结构化诊断也让评估整体丢失）。
  - 探针 case 数：**9**（原 6 + `build_quadruped` + `mask_missing_while_masked` + `mask_number_string`）。

退出码：0 全绿；1 有判据为假；2 前置输入缺失；3 注入锚点失效（与「判据无牙」分开）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover - 环境缺失必须显式（不得静默降级）
    print(f"E_ENV: jsonschema unavailable: {exc}", file=sys.stderr)
    raise SystemExit(2)

EXIT_OK, EXIT_RED, EXIT_SKIP, EXIT_BAD_INJECTION = 0, 1, 2, 3

SCHEMA_NAME = "npc.appearance.schema.json"
DOSSIERS_REL = "fidelity/05-character-dossiers.md"
XUQIN_NPC_REL = "v0_skeleton/districts/xingfu-xiaoqu-xuqin/npcs/npc-006.json"
XUQIN_PACK_REL = "v0_skeleton/districts/xingfu-xiaoqu-xuqin"
NORTH_PACK_REL = "v0_skeleton/districts/xingfu-xiaoqu-north"
MAIN_PACK_REL = "v0_skeleton/districts/xingfu-xiaoqu"

#: 顶层出处字段的**起点冻结锚**（2026-09-24 采集：`<repo>/v0/.../npc-006.json` @ 18f9fac，
#: 规范化 JSON（sort_keys + 无空白）的 sha256）。N2 **只**新增嵌套 `appearance`，
#: 顶层 `source_facts` / `source_fact_map` 必须逐字节不变。
TOP_LEVEL_PROVENANCE_SHA256 = "a0997e45736befc1ebbcf0fa79160b7361a8e8f36e48ade802cd98a8d914da31"

#: 顶层 map 里 `appearance.` 前缀的**既有**键（N2 之前就存在；新外形项**不得**再用这个前缀）。
LEGACY_TOP_LEVEL_APPEARANCE_KEYS = ("appearance.red_coat", "appearance.scarlet_eyes")

#: 主包豁免（逐条给理由）。**不在**本表内、又缺 `appearance` 的 NPC ⇒ 判红。
MAIN_PACK_EXEMPTION = (
    "主包 `districts/xingfu-xiaoqu/**` 逐字节零改动（冻结锚 844f7606… 钉死 pack.sig）"
    "⇒ 本轮**不写入** appearance；渲染由 character.ts 的确定性通用人形兜底（AC-3 仍成立）"
)

CHR_LINE_RE = re.compile(r"\[(CHR-\d+)\]")
HEX_RE = re.compile(r"^#[0-9a-f]{6}$")
SENT_PUNCT = "。！？；"
QUOTE_PAIRS = (("\u201c", "\u201d"), ("\u300c", "\u300d"))
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
D4_LONG_CJK = 60
D4_MIN_CJK = 24


class BadInjection(Exception):
    pass


# --------------------------------------------------------------------------- 小工具
def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dossier_sets(dossiers: Path) -> tuple[set[str], set[str]]:
    verified: set[str] = set()
    unverified: set[str] = set()
    for line in dossiers.read_text(encoding="utf-8").splitlines():
        for match in CHR_LINE_RE.finditer(line):
            identifier = match.group(1)
            (unverified if "UNVERIFIED" in line else verified).add(identifier)
    return verified, unverified


def iter_fields(node: object, path: str = "appearance"):
    """递归产出 `(路径, 字段对象)`；字段 = 含 `value` 键的对象。"""
    if isinstance(node, dict):
        if "value" in node:
            yield path, node
            return
        for key, value in node.items():
            yield from iter_fields(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_fields(value, f"{path}[{index}]")


def quoted_segments(line: str) -> list[str]:
    out: list[str] = []
    for opener, closer in QUOTE_PAIRS:
        start = 0
        while True:
            begin = line.find(opener, start)
            if begin < 0:
                break
            end = line.find(closer, begin + 1)
            if end < 0:
                break
            out.append(line[begin + 1:end])
            start = end + 1
    return out


def is_verbatim_paragraph(segment: str) -> bool:
    count = len(CJK_RE.findall(segment))
    if count >= D4_LONG_CJK:
        return True
    if count >= D4_MIN_CJK:
        return sum(segment.count(mark) for mark in SENT_PUNCT) >= 2
    return False


def npc_documents(root: Path) -> list[tuple[str, Path, dict]]:
    """全部 `districts/*/npcs/*.json` → `(pack_id, 路径, 文档)`。"""
    out: list[tuple[str, Path, dict]] = []
    districts = root / "v0_skeleton" / "districts"
    if not districts.is_dir():
        return out
    for path in sorted(districts.glob("*/npcs/*.json")):
        out.append((path.parent.parent.name, path, read_json(path)))
    return out


# --------------------------------------------------------------------------- 判据
def evaluate(root: Path) -> dict:
    schema_path = root / SCHEMA_NAME
    dossiers_path = root / DOSSIERS_REL
    missing = [str(path) for path in (schema_path, dossiers_path) if not path.is_file()]
    if missing:
        return {"status": "skipped_missing_input", "missing": missing}

    schema = read_json(schema_path)
    validator = jsonschema.Draft202012Validator(schema)
    verified, unverified = dossier_sets(dossiers_path)
    documents = npc_documents(root)
    if not documents:
        return {"status": "skipped_missing_input", "missing": ["districts/*/npcs/*.json"]}

    checks: dict[str, dict] = {}

    # 1) schema
    schema_failures: list[str] = []
    with_appearance: list[tuple[str, Path, dict]] = []
    without_appearance: list[tuple[str, Path, dict]] = []
    for pack_id, path, document in documents:
        appearance = document.get("appearance")
        if appearance is None:
            without_appearance.append((pack_id, path, document))
            continue
        with_appearance.append((pack_id, path, document))
        errors = sorted(validator.iter_errors(appearance), key=lambda error: list(error.path))
        for error in errors:
            location = "/".join(str(part) for part in error.path) or "<root>"
            schema_failures.append(f"{path.relative_to(root)}: {location}: {error.message}")
    checks["schema_valid"] = {
        "checked": len(with_appearance),
        "failures": schema_failures,
        "pass": bool(with_appearance) and not schema_failures,
    }

    # 2) 每个字段恰好一种出处
    provenance_failures: list[str] = []
    field_count = 0
    for _, path, document in with_appearance:
        for field_path, field in iter_fields(document.get("appearance")):
            field_count += 1
            has_facts = isinstance(field.get("source_facts"), list) and bool(
                [item for item in field["source_facts"] if str(item).strip()])
            has_fill = field.get("design_fill") is True
            if has_facts == has_fill:
                provenance_failures.append(
                    f"{path.relative_to(root)}:{field_path}: "
                    f"source_facts={field.get('source_facts')!r} design_fill={field.get('design_fill')!r}")
    checks["every_field_has_provenance"] = {
        "fields": field_count,
        "failures": provenance_failures,
        "pass": field_count > 0 and not provenance_failures,
    }

    # 3) source_facts 编号可解析且非 UNVERIFIED
    unresolved: list[str] = []
    unverified_hits: list[str] = []
    referenced: set[str] = set()
    for _, path, document in with_appearance:
        for field_path, field in iter_fields(document.get("appearance")):
            for identifier in field.get("source_facts") or []:
                identifier = str(identifier)
                referenced.add(identifier)
                if identifier in unverified:
                    unverified_hits.append(f"{path.relative_to(root)}:{field_path}:{identifier}")
                elif identifier not in verified:
                    unresolved.append(f"{path.relative_to(root)}:{field_path}:{identifier}")
    checks["source_facts_resolve"] = {
        "referenced": sorted(referenced),
        "unresolved": unresolved,
        "unverified_hits": unverified_hits,
        "verified_count_in_dossiers": len(verified),
        "pass": bool(referenced) and not unresolved and not unverified_hits,
    }

    # 4) 徐琴必填项 + 面具编号
    xuqin_path = root / XUQIN_NPC_REL
    xuqin = read_json(xuqin_path) if xuqin_path.is_file() else None
    xuqin_missing: list[str] = []
    mask_number = None
    mask_label = None
    if xuqin is None:
        xuqin_missing.append("npc-006.json missing")
    else:
        raw_appearance = xuqin.get("appearance")
        # N2-r2 / F-4：`appearance` 非 dict（字符串 / null / 数组）⇒ 显式记问题，**不**抛异常。
        if not isinstance(raw_appearance, dict):
            xuqin_missing.append(f"appearance is not an object ({type(raw_appearance).__name__})")
            raw_appearance = {}
        appearance = raw_appearance
        for key in ("eyes", "lips", "skin", "hair", "garment", "height_cm", "build", "age_look", "states"):
            if key not in appearance:
                xuqin_missing.append(f"appearance.{key}")
        for key in ("eyes", "lips", "skin", "hair", "garment"):
            holder = appearance.get(key)
            color = holder.get("color") if isinstance(holder, dict) else None
            value = color.get("value") if isinstance(color, dict) else None
            if not HEX_RE.match(str(value if value is not None else "")):
                xuqin_missing.append(f"appearance.{key}.color(hex)")
        # N2-r2 / F-4：`mask` / `mask.number` / `mask.number_label` 取值一律加 `isinstance(x, dict)`
        # 守卫（与 `eyes.color` 同一写法）—— 类型混淆 ⇒ **结构化拒收**，不 `AttributeError`。
        mask = appearance.get("mask")
        mask = mask if isinstance(mask, dict) else {}
        number_field = mask.get("number")
        number_field = number_field if isinstance(number_field, dict) else {}
        label_field = mask.get("number_label")
        label_field = label_field if isinstance(label_field, dict) else {}
        mask_number = number_field.get("value")
        mask_label = label_field.get("value")
        if mask_number != "8":
            xuqin_missing.append(f"appearance.mask.number(={mask_number!r}, expected '8')")
        if mask_label != "八号":
            xuqin_missing.append(f"appearance.mask.number_label(={mask_label!r}, expected '八号')")
    checks["xuqin_required_fields"] = {
        "missing": xuqin_missing,
        "mask_number": mask_number,
        "mask_number_label": mask_label,
        "pass": not xuqin_missing,
    }

    # 5) 两态声明 + 谓词只读既有 state 字段
    states = (xuqin or {}).get("appearance", {}).get("states") if xuqin else None
    states = states if isinstance(states, list) else []
    ids = [item.get("id") for item in states if isinstance(item, dict)]
    masked = next((item for item in states if isinstance(item, dict) and item.get("id") == "masked"), None)
    daily = next((item for item in states if isinstance(item, dict) and item.get("id") == "daily"), None)
    allowed_predicate_keys = {"target_entity_in", "schedule_state_in", "room_id_in", "tags_include"}
    predicate_keys = set((masked or {}).get("when", {}) or {}) if masked else set()
    states_problems: list[str] = []
    if "daily" not in ids:
        states_problems.append("missing state id 'daily'")
    if masked is None:
        states_problems.append("missing state id 'masked'")
    else:
        if masked.get("mask") is not True:
            states_problems.append("masked.mask is not true")
        if not predicate_keys:
            states_problems.append("masked.when is empty")
        if not predicate_keys <= allowed_predicate_keys:
            states_problems.append(f"masked.when uses non-state keys: {sorted(predicate_keys - allowed_predicate_keys)}")
        if "kitchen-01" not in ((masked.get("when") or {}).get("target_entity_in") or []):
            states_problems.append("masked.when.target_entity_in lacks 'kitchen-01'")
    if daily is not None and daily.get("when") is not None:
        states_problems.append("daily must not declare `when` (it is the default state)")
    checks["xuqin_states_declared"] = {
        "state_ids": ids,
        "masked_predicate_keys": sorted(predicate_keys),
        "problems": states_problems,
        "pass": not states_problems,
    }

    # 6) 出处只读**嵌套**字段（R-18 假绿陷阱）+ 顶层逐字节未改
    nested_problems: list[str] = []
    top_level_digest = None
    top_appearance_keys: list[str] = []
    if xuqin is None:
        nested_problems.append("npc-006.json missing")
    else:
        top_level_digest = canonical_sha256({
            "source_facts": xuqin.get("source_facts"),
            "source_fact_map": xuqin.get("source_fact_map"),
        })
        if top_level_digest != TOP_LEVEL_PROVENANCE_SHA256:
            nested_problems.append(
                f"top-level source_facts/source_fact_map changed: {top_level_digest} != {TOP_LEVEL_PROVENANCE_SHA256}")
        fact_map = xuqin.get("source_fact_map")
        fact_map = fact_map if isinstance(fact_map, dict) else {}
        top_appearance_keys = sorted(key for key in fact_map if str(key).startswith("appearance."))
        unexpected = [key for key in top_appearance_keys if key not in LEGACY_TOP_LEVEL_APPEARANCE_KEYS]
        if unexpected:
            nested_problems.append(
                f"new appearance.* keys at TOP level (false-green trap): {unexpected}")
        appearance = xuqin.get("appearance")
        if isinstance(appearance, dict):
            for forbidden in ("source_facts", "source_fact_map"):
                if forbidden in appearance:
                    nested_problems.append(f"appearance.{forbidden} must not exist (provenance is per-field)")
    checks["appearance_provenance_is_nested"] = {
        "top_level_provenance_sha256": top_level_digest,
        "expected_sha256": TOP_LEVEL_PROVENANCE_SHA256,
        "top_level_appearance_prefixed_keys": top_appearance_keys,
        "legacy_keys": list(LEGACY_TOP_LEVEL_APPEARANCE_KEYS),
        "problems": nested_problems,
        "pass": not nested_problems,
    }

    # 7) 北区住户基础外形（全 design_fill，不编造原著事实）
    north_dir = root / NORTH_PACK_REL / "npcs"
    north_files = sorted(north_dir.glob("*.json")) if north_dir.is_dir() else []
    residents_problems: list[str] = []
    if not north_files:
        residents_problems.append(f"no NPC files under {NORTH_PACK_REL}/npcs")
    for path in north_files:
        document = read_json(path)
        appearance = document.get("appearance")
        if not isinstance(appearance, dict):
            residents_problems.append(f"{path.name}: appearance missing")
            continue
        for field_path, field in iter_fields(appearance):
            if field.get("design_fill") is not True or field.get("source_facts"):
                residents_problems.append(f"{path.name}:{field_path}: must be design_fill-only")
    checks["residents_have_appearance"] = {
        "files": [path.name for path in north_files],
        "problems": residents_problems,
        "pass": bool(north_files) and not residents_problems,
    }

    # 8) 主包豁免**显式**声明（不在豁免表内又缺 appearance ⇒ 红）
    exempt_problems: list[str] = []
    main_pack_npcs = [item for item in without_appearance if item[0] == "xingfu-xiaoqu"]
    for pack_id, path, _ in without_appearance:
        if pack_id != "xingfu-xiaoqu":
            exempt_problems.append(f"{path.relative_to(root)}: appearance missing and pack is NOT exempt")
    checks["main_pack_exempt_declared"] = {
        "main_pack_npcs_without_appearance": [path.name for _, path, _ in main_pack_npcs],
        "exemption": MAIN_PACK_EXEMPTION,
        "problems": exempt_problems,
        "pass": not exempt_problems,
    }

    # 9) AC-10：角色参考表登记 + derived_from 可解析
    pack_manifest_path = root / XUQIN_PACK_REL / "assets" / "manifest.json"
    refs_problems: list[str] = []
    ref_ids: list[str] = []
    derived_targets: list[str] = []
    ref_count = 0
    if not pack_manifest_path.is_file():
        refs_problems.append("proposal pack assets/manifest.json missing")
    else:
        manifest = read_json(pack_manifest_path)
        block = manifest.get("character_refs")
        if not isinstance(block, dict):
            refs_problems.append("character_refs block missing")
        else:
            refs = block.get("refs")
            refs = refs if isinstance(refs, list) else []
            ref_count = len(refs)
            minimum = block.get("sheet_min_images")
            if not isinstance(minimum, int) or minimum < 3:
                refs_problems.append(f"sheet_min_images={minimum!r} (art-bible §7 requires >= 3)")
            for ref in refs:
                asset_id = ref.get("asset_id") if isinstance(ref, dict) else None
                if not isinstance(asset_id, str) or not asset_id:
                    refs_problems.append(f"ref without asset_id: {ref!r}")
                    continue
                ref_ids.append(asset_id)
                file_rel = ref.get("file")
                if not isinstance(file_rel, str) or not (root / XUQIN_PACK_REL / file_rel).is_file():
                    refs_problems.append(f"{asset_id}: file missing in pack: {file_rel!r}")
            if len(set(ref_ids)) != len(ref_ids):
                refs_problems.append("duplicate ref asset_id")
            if isinstance(minimum, int) and ref_count < minimum:
                refs_problems.append(f"refs {ref_count} < sheet_min_images {minimum}")
            consumers = block.get("consumers")
            consumers = consumers if isinstance(consumers, list) else []
            for consumer in consumers:
                for target in (consumer or {}).get("derived_from") or []:
                    derived_targets.append(str(target))
                    if str(target) not in ref_ids:
                        refs_problems.append(f"derived_from target not resolvable: {target!r}")
            if not consumers or not derived_targets:
                refs_problems.append("no consumer asset declares derived_from")
    checks["character_refs_registered"] = {
        "manifest": str(pack_manifest_path.relative_to(root)) if pack_manifest_path.is_file() else None,
        "ref_count": ref_count,
        "ref_asset_ids": ref_ids,
        "derived_from_targets": derived_targets,
        "problems": refs_problems,
        "pass": ref_count >= 3 and bool(derived_targets) and not refs_problems,
    }

    # 10) appearance 内不得有引号包起来的原著长串（D-4 规则）
    verbatim_hits: list[str] = []
    for _, path, document in with_appearance:
        appearance = document.get("appearance")
        for line_number, line in enumerate(json.dumps(appearance, ensure_ascii=False, indent=2).splitlines(), start=1):
            for segment in quoted_segments(line):
                if is_verbatim_paragraph(segment):
                    verbatim_hits.append(f"{path.relative_to(root)}:line{line_number}")
    checks["appearance_has_no_verbatim_paragraph"] = {
        "hits": verbatim_hits,
        "pass": not verbatim_hits,
    }

    return {
        "status": "measured",
        "root": str(root),
        "checks": checks,
        "appearance_ok": all(item["pass"] for item in checks.values()),
        "appearance_required_packs": ["xingfu-xiaoqu-xuqin", "xingfu-xiaoqu-north"],
    }


# --------------------------------------------------------------------------- 自证
def probe(root: Path, workdir: Path) -> list[dict]:
    """全部注入都在**副本**上做（交付树零改动）；每条断言「注入是否真的落地 + 判据是否真的变红」。"""
    cases: list[dict] = []

    def clone(name: str) -> Path:
        target = workdir / name
        shutil.copytree(root, target, symlinks=True,
                        ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache"))
        return target

    def inject_json(path: Path, mutate) -> None:
        document = read_json(path)
        # N2-r2 / F-4：注入 lambda 的「锚点已不存在」形态（`KeyError` / `AttributeError` /
        # `TypeError` / `IndexError`）**不得**变成未捕获 traceback —— 一律转成 `BadInjection`，
        # 由 `main()` 走它自己设计的结构化路径（`EXIT_BAD_INJECTION` + JSON `reason`）。
        try:
            mutate(document)
        except (KeyError, AttributeError, TypeError, IndexError) as exc:
            raise BadInjection(
                f"{path.name}: {type(exc).__name__}: {exc} "
                f"(injection anchor missing; see F-4 in 03_artisan_self_test.log)") from exc
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def record(case: str, red: bool, reading, skipped_anchor_missing: str | None = None) -> None:
        entry = {"case": case, "fired": bool(red), "reading": reading}
        if skipped_anchor_missing:
            entry["skipped_anchor_missing"] = skipped_anchor_missing
        cases.append(entry)

    npc_rel = Path(XUQIN_NPC_REL)
    skipped_cases: list[str] = []

    def set_mask_number_9(document: dict) -> None:
        """把徐琴的 `mask.number.value` 改成 `'9'`（注入意图固定）。

        F-4：① 锚点 `appearance.mask` 缺失 ⇒ `KeyError` ⇒ 该 case 标 `skipped_anchor_missing`；
        ② `mask.number` 是**字符串**（类型混淆）⇒ 用同义注入替换成对象（编号值仍 = 9），
        使判据侧的 `isinstance` 守卫的结构化拒收可被观测，而不是让整个探针中止。
        """
        appearance = document["appearance"]
        mask = appearance["mask"]
        number = mask.get("number")
        if isinstance(number, dict):
            number["value"] = "9"
        else:
            mask["number"] = {"value": "9", "source_facts": ["CHR-16", "CHR-17"]}

    def probe_case(name: str, target: Path, mutate, check_name: str, reading_key: str = "failures") -> None:
        """跑一个注入 case。

        F-4①：注入 lambda 的 `KeyError` / `AttributeError` / `TypeError` / `IndexError`
        （= 锚点已不存在）走 `BadInjection` ⇒ 该 case 记 `skipped_anchor_missing`
        （`fired=False`，且 `probe()` 把整次运行标成 `EXIT_BAD_INJECTION`）。
        **无论是否 skipped，`evaluate()` 都照跑** —— 结构化读数（哪条判据因何变红）不丢。
        """
        copy = clone(name)
        skip: str | None = None
        try:
            inject_json(copy / target, mutate)
        except BadInjection as exc:
            skip = str(exc)
            skipped_cases.append(name)
        result = evaluate(copy)
        reading = (result.get("checks") or {}).get(check_name) or {}
        values = reading.get(reading_key) or []
        record(name, skip is None and reading.get("pass") is False, values[:1], skipped_anchor_missing=skip)

    # 1) 删 eyes.color ⇒ schema_valid 必红
    probe_case("remove_eyes_color", npc_rel,
               lambda document: document["appearance"]["eyes"].pop("color"), "schema_valid")

    # 2) 去掉 hair.color 的 design_fill ⇒ 必红（不得把设计补全冒充原著）
    probe_case("drop_hair_design_fill", npc_rel,
               lambda document: document["appearance"]["hair"]["color"].pop("design_fill"), "schema_valid")

    # 3) 伪造 CHR-99 ⇒ source_facts_resolve 必红
    probe_case("forged_chr_99", npc_rel,
               lambda document: document["appearance"]["eyes"]["color"].update({"source_facts": ["CHR-99"]}),
               "source_facts_resolve", "unresolved")

    # 4) mask.number 改 9 ⇒ xuqin_required_fields 必红
    probe_case("mask_number_9", npc_rel, set_mask_number_9, "xuqin_required_fields", "missing")

    # 5) 往**顶层** source_fact_map 塞一个 appearance.* 新键 ⇒ 假绿陷阱必红
    def add_top_level(document: dict) -> None:
        document["source_fact_map"]["appearance.hair"] = ["CHR-22"]
    probe_case("top_level_appearance_key", npc_rel, add_top_level,
               "appearance_provenance_is_nested", "problems")

    # 6) 删一张**被 derived_from 引用**的参考图 ⇒ character_refs_registered 必红
    def drop_ref(document: dict) -> None:
        block = document["character_refs"]
        victim = block["consumers"][0]["derived_from"][0]
        block["refs"] = [ref for ref in block["refs"] if ref.get("asset_id") != victim]
    probe_case("drop_referenced_ref", Path(XUQIN_PACK_REL) / "assets" / "manifest.json", drop_ref,
               "character_refs_registered", "problems")

    # 7) F-2：`build` 改 `"quadruped"`（自由文本时代的静默放过）⇒ schema_valid 必红
    probe_case("build_quadruped", npc_rel,
               lambda document: document["appearance"]["build"].update({"value": "quadruped"}), "schema_valid")

    # 8) F-3①：删 `appearance.mask` 而 `states` 仍声明 `masked` ⇒ 条件必填 ⇒ schema_valid 必红
    probe_case("mask_missing_while_masked", npc_rel,
               lambda document: document["appearance"].pop("mask"), "schema_valid")

    # 9) F-4②：`mask.number` 传**字符串**（类型混淆）⇒ 结构化拒收，不 traceback
    probe_case("mask_number_string", npc_rel,
               lambda document: document["appearance"]["mask"].__setitem__("number", "9"),
               "xuqin_required_fields", "missing")

    return cases, skipped_cases


def emit(document: dict, json_path: str | None) -> None:
    text = json.dumps(document, ensure_ascii=False, sort_keys=True)
    sys.stdout.write(text + "\n")
    if json_path:
        target = Path(json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="NPC appearance contract verifier (N2)")
    parser.add_argument("--root", default=".")
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        emit({"status": "skipped_missing_input", "missing": [str(root)]}, args.json_path)
        return EXIT_SKIP

    try:
        probe_cases, skipped_cases = probe(root, Path(tempfile.mkdtemp(prefix="n2-appearance-probe-")))
    except BadInjection as exc:
        emit({"appearance_ok": None, "probe_ok": False, "reason": f"injection_anchor_missing: {exc}"},
             args.json_path)
        return EXIT_BAD_INJECTION

    document = evaluate(root)
    document["probe"] = probe_cases
    document["probe_ok"] = all(case["fired"] for case in probe_cases) and len(probe_cases) > 0
    # F-4①：有 case 因**锚点已不存在**而跳过 ⇒ 整次运行归 `EXIT_BAD_INJECTION`
    # （与「判据无牙」分开）；**结构化读数照给**（`checks` / `probe` 都在本 JSON 里）。
    document["probe_skipped_anchor_missing"] = skipped_cases
    emit(document, args.json_path)

    if document.get("status") == "skipped_missing_input":
        return EXIT_SKIP
    if args.probe_only:
        return EXIT_OK if document["probe_ok"] else EXIT_RED
    if skipped_cases:
        return EXIT_BAD_INJECTION
    return EXIT_OK if document["appearance_ok"] and document["probe_ok"] else EXIT_RED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
