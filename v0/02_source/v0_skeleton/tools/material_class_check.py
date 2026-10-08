#!/usr/bin/env python3
"""N5 / S-3 的判定工具：`AC-I-3a/b/c/d/e/f/g/h/i` + 定向数值（`AC-A-3③` 的类别锚）。

运行（workdir = 仓库根；**只读**交付源码，产物写独立输出目录）：
    python3 v0/02_source/v0_skeleton/tools/material_class_check.py \
        --inputs v0/02_source/v0_skeleton/web/scripts/assert_inputs.json \
        --report v0/spikes/n5-asset/readback/material_report.json \
        --json-out v0/spikes/n5-asset/readback/material_class_check.json

退出码：0 全通过；1 有失败；2 环境错误。

判据：
  I-3a  `SURFACE_IDS` 名集 == 冻结清单（12 条、消失 0）**且** `INPUTS` 块常量集合哈希 == 冻结值
  I-3b  每类别区间 ⊆ 旧口径 `roughness∈[0.6,0.95]` / `metalness∈[0,0.15]`，或属 skin/glass/metal 并给冻结理由
  I-3c  任一类别区间不得同时等于两个全局全域；成员数 ≥2；禁 singleton
  I-3d  每成员实测值落在其类别声明区间内
  I-3e  内容包 `assets/manifest.json` 的 `roughness_range[0]` 不得 < 0.6；皮肤/玻璃类只进 SURFACES_EXT
  I-3f  `SURFACES ∩ SURFACES_EXT == ∅`
  I-3g  场景使用面 ⊆ 并集 且 每面恰好归一个表
  I-3h  `material_classes.ts` 类别表块 sha256 == 冻结值
  I-3i  三条定向数值（skin ⇒ roughness<0.6；glass ⇒ 有 transmission/ior ∧ roughness≤0.15；metal ⇒ metalness≥0.6）

负对照（`--selftest`，在 `/tmp` 副本上做，**不碰交付树**）：
  ① 删一条 `SURFACES` 表面 ⇒ I-3a 必红
  ② `ground_wet.envMapIntensity` 1.3 → 2.0 ⇒ I-3a 必红（旧锚在此改动下保持全绿 ⇒ 证明新锚有牙）
  ③ 改一个类别区间 ⇒ I-3h 必红
  ④ 往 `SURFACES_EXT` 塞一个已在 `SURFACES` 里的 id ⇒ I-3f 必红
  ⑤ 把 metal 成员 metalness 置 0.04 ⇒ I-3i 必红
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

WS = Path(__file__).resolve().parents[4]
WEB = WS / "v0/02_source/v0_skeleton/web"
MATERIALS = WEB / "src/scene/materials.ts"
CLASSES = WEB / "src/scene/material_classes.ts"
PACK_MANIFEST = WS / "v0/02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin/assets/manifest.json"

LEGACY_ROUGHNESS = (0.6, 0.95)
LEGACY_METALNESS = (0.0, 0.15)
NUMBER_RE = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)(?![\w.])")
STRING_RE = re.compile(r"'([^'\\\n]*)'")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def block(text: str, start_prefix: str, end_line: str = "};") -> str:
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith(start_prefix))
    end = next(i for i in range(start, len(lines)) if lines[i] == end_line)
    return "\n".join(lines[start:end + 1])


def normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")


def constants_of(text: str) -> list[str]:
    """块内常量**多重集**（数字 toFixed(6) + 字符串字面量，排序**保重复**）。

    加严理由（自证反例）：去重集合对「1.3 → 2.0」不敏感（2.0 已在块内别处出现 ⇒ 集合不变 ⇒ 假绿）。
    """
    out: list[str] = []
    for m in NUMBER_RE.finditer(text):
        out.append(f"{float(m.group(1)):.6f}")
    for m in STRING_RE.finditer(text):
        out.append(m.group(1))
    return sorted(out)


def current_hashes(web: Path = WEB) -> dict:
    mtext = (web / "src/scene/materials.ts").read_text(encoding="utf-8")
    ctext = (web / "src/scene/material_classes.ts").read_text(encoding="utf-8")
    inputs_block = block(mtext, "const INPUTS: Record<SurfaceId, SurfaceInput> = {")
    class_block = block(ctext, "export const MATERIAL_CLASSES: Readonly<Record<MaterialClassId, MaterialClassDecl>> = {")
    surface_ids = sorted(set(re.findall(r"'([a-z_]+)'", re.findall(r"export type SurfaceId =([^;]+);", mtext)[0])))
    return {
        "materials_inputs_block_sha256": sha256_text(normalize(inputs_block)),
        "materials_inputs_constants_sha256": sha256_text("\n".join(constants_of(inputs_block))),
        "material_class_block_sha256": sha256_text(normalize(class_block)),
        "surface_ids": surface_ids,
    }


def check(inputs: dict, report: dict, hashes: dict, pack_manifest: Path):
    failures = []
    warnings = []
    frozen = inputs.get("hashes", {})

    # --- I-3a ---
    frozen_ids = sorted(inputs["checks"]["surface_ids_frozen"])
    if hashes["surface_ids"] != frozen_ids:
        missing = [i for i in frozen_ids if i not in hashes["surface_ids"]]
        extra = [i for i in hashes["surface_ids"] if i not in frozen_ids]
        failures.append(f"I-3a: SURFACE_IDS 名集 != 冻结清单（消失 {missing}，新增 {extra}）")
    if hashes["materials_inputs_constants_sha256"] != frozen["materials_inputs_constants_sha256"]:
        failures.append("I-3a: INPUTS 常量集合哈希 != 冻结值（既有表面常量被改）")

    # --- I-3h ---
    if hashes["material_class_block_sha256"] != frozen["material_class_block_sha256"]:
        failures.append("I-3h: 类别表块 sha256 != 冻结值")

    classes = {c["id"]: c for c in report.get("classes", [])}
    ext = {e["id"]: e for e in report.get("surfaces_ext", [])}

    # --- I-3b / I-3c ---
    for cid, c in classes.items():
        r_lo, r_hi = c["roughness"]
        m_lo, m_hi = c["metalness"]
        within = (r_lo >= LEGACY_ROUGHNESS[0] and r_hi <= LEGACY_ROUGHNESS[1]
                  and m_lo >= LEGACY_METALNESS[0] and m_hi <= LEGACY_METALNESS[1])
        if not within:
            if cid in ("skin", "glass", "metal") and c.get("frozen_reason"):
                pass  # 合法豁免（有冻结理由）
            else:
                failures.append(f"I-3b: 类别 {cid} 区间 ∉ 旧口径且无冻结理由")
        if r_lo == 0 and r_hi == 1 and m_lo == 0 and m_hi == 1:
            failures.append(f"I-3c: 类别 {cid} 是 catch-all（区间 == 两个全局全域）")
        if len(c.get("members", [])) < 2:
            failures.append(f"I-3c: 类别 {cid} 成员数 {len(c.get('members', []))} < 2")

    # --- I-3d ---
    for sid, e in ext.items():
        c = classes.get(e["class"])
        if not c:
            failures.append(f"I-3d: 表面 {sid} 的类别 {e.get('class')!r} 不在类别表内")
            continue
        if not (c["roughness"][0] <= e["roughness"] <= c["roughness"][1]):
            failures.append(f"I-3d: {sid} roughness {e['roughness']} ∉ {c['roughness']}")
        if not (c["metalness"][0] <= e["metalness"] <= c["metalness"][1]):
            failures.append(f"I-3d: {sid} metalness {e['metalness']} ∉ {c['metalness']}")

    # --- I-3i 定向数值 ---
    for sid, e in ext.items():
        if e["class"] == "skin" and not (e["roughness"] < 0.6):
            failures.append(f"I-3i①: skin 成员 {sid} roughness {e['roughness']} >= 0.6")
        if e["class"] == "glass":
            if e.get("transmission") is None or e.get("ior") is None:
                failures.append(f"I-3i②: glass 成员 {sid} 缺 transmission/ior")
            if not (e["roughness"] <= 0.15):
                failures.append(f"I-3i②: glass 成员 {sid} roughness {e['roughness']} > 0.15")
        if e["class"] == "metal" and not (e["metalness"] >= 0.6):
            failures.append(f"I-3i③: metal 成员 {sid} metalness {e['metalness']} < 0.6")

    # --- I-3f ---
    if report.get("intersection"):
        failures.append(f"I-3f: SURFACES ∩ SURFACES_EXT != ∅：{report['intersection']}")

    # --- I-3g ---
    legacy_ids = {s["surface"] for s in report.get("surfaces_legacy", [])}
    ext_ids = set(ext)
    used = set(report.get("scene_used_surfaces", []))
    unregistered = sorted(used - (legacy_ids | ext_ids))
    if unregistered:
        failures.append(f"I-3g: 场景使用面未登记：{unregistered}")
    both = sorted(legacy_ids & ext_ids)
    if both:
        failures.append(f"I-3g: 同一表面归属两个表：{both}")

    # --- I-3g+（N5-r2 / A3 加严；**新增**子句，上面既有的 I-3g 判据体一字未动） ---
    # 场景**实际**实例化的 ext 表面必须覆盖注册表全量：r1 的 `scene_used_surfaces` 取注册表并集
    # （自比对 ⇒ 恒真）⇒「注册表有、场景里没有」永远发现不了。本子句是「从场景里摘掉一件
    # ext 表面 ⇒ 必红」的机读形态（负对照见 `v0/spikes/n5-asset/r2_negative_controls.mjs` ③）。
    scene_ext = set(report.get("scene_used_ext", []))
    ext_expected_scene = set(report.get("ext_expected_in_scene", [])) or ext_ids
    if scene_ext != ext_expected_scene:
        failures.append(f"I-3g+: 场景未实例化的 ext 表面：{sorted(ext_expected_scene - scene_ext)}")
    if report.get("scene_unregistered"):
        failures.append(f"I-3g+: 场景使用了未登记表面：{report['scene_unregistered']}")

    # --- I-3g++（N5-r3 / A6；**新增**子句，上面既有的 I-3g / I-3g+ 判据体一字未动） ---
    # ① **渲染面**：`scene_visible_ext` 只统计「真的会被画」的 ext 表面 ⇒ 整棵子树被藏时必红
    #    （r2 的盲区：`scene_used_ext` 不看 `visible`）。② legacy 侧**下界**：探针世界是合成 snapshot
    #    （1 npc、无 zone/prop）⇒ 地面族 4 条必须都在（r2 的 legacy 侧是单向 ⊆，4/12 也全绿）。
    if "scene_visible_ext" not in report:
        failures.append("I-3g: 报告缺 `scene_visible_ext`（旧版探针产物 ⇒ 渲染面判据无牙）")
    else:
        scene_visible_ext = set(report.get("scene_visible_ext", []))
        if scene_visible_ext != ext_expected_scene:
            failures.append(f"I-3g: 未**可见**实例化的 ext 表面：{sorted(ext_expected_scene - scene_visible_ext)}")
    if report.get("scene_hidden_surfaces"):
        failures.append(f"I-3g: 场景里有表面被藏（不可见）：{report['scene_hidden_surfaces']}")
    floor = report.get("legacy_floor")
    if not isinstance(floor, list) or not floor:
        failures.append("I-3g: legacy 侧下界未声明（无下界 ⇒ 判据无牙）")
    else:
        missing_floor = sorted(set(floor) - set(report.get("scene_visible_legacy", [])))
        if missing_floor:
            failures.append(f"I-3g: legacy 侧下界未满足（探针世界地面族缺失）：{missing_floor}")

    # --- I-3e pack 侧硬约束 ---
    if pack_manifest.is_file():
        doc = json.loads(pack_manifest.read_text(encoding="utf-8"))
        for a in doc.get("assets", []):
            rr = a.get("roughness_range")
            if isinstance(rr, list) and rr and rr[0] < 0.6:
                failures.append(f"I-3e: pack asset {a.get('id')} roughness_range[0]={rr[0]} < 0.6")
    else:
        warnings.append("I-3e: pack assets/manifest.json 不存在（GAP）")

    # --- 非零命中前置（AC-A-3③ 注） ---
    if not report.get("surfaces_legacy") and not report.get("surfaces_ext"):
        failures.append("AC-A-3③: 机读锚集合为空 ⇒ GAP（不得 PASS）")

    return failures, warnings


def selftest(inputs: dict, report: dict, hashes: dict, pack_manifest: Path) -> int:
    cases = []
    # N5-r3 / A6：**基线补全**「渲染面」字段（旧版 report 缺 `scene_visible_*` / `legacy_floor` 时，
    # 用注册表全量与探针世界地面族合成）。否则基线自带 I-3g 失败 ⇒ 负对照会「假装翻红」（无信息量）。
    report = copy.deepcopy(report)
    ext_all = sorted(str(e.get("id")) for e in report.get("surfaces_ext", []))
    report.setdefault("scene_visible_ext", list(report.get("scene_used_ext", ext_all)))
    report.setdefault("scene_visible_legacy", list(report.get("scene_used_legacy", [])))
    report.setdefault("scene_hidden_surfaces", [])
    report.setdefault("legacy_floor", ["ground_grass", "ground_wet", "pavement_brick", "road_asphalt"])

    def run(label, mutate_report=None, mutate_hash=None, mutate_inputs=None):
        r = copy.deepcopy(report)
        h = copy.deepcopy(hashes)
        i = copy.deepcopy(inputs)
        if mutate_report:
            mutate_report(r)
        if mutate_hash:
            mutate_hash(h)
        if mutate_inputs:
            mutate_inputs(i)
        f, _ = check(i, r, h, pack_manifest)
        cases.append((label, bool(f)))

    # ① 删一条 SURFACES 表面（改 I-3a 真正读的那个输入：`surface_ids` 名集）
    #    注（N5-r2 / A3）：旧实现改的是 `report["surfaces_legacy"]`，靠「场景使用面 == 注册表全量」
    #    侧漏判红 —— A3 把场景使用面改成**真实遍历**后该形态不再必然红 ⇒ 改为直接改 I-3a 的输入
    #    （同一判据、同一取数面，不是放宽）。
    run("① 删一条 SURFACES 表面名 ⇒ I-3a 必红",
        mutate_hash=lambda h: h.__setitem__("surface_ids", h["surface_ids"][:-1]))
    # ② 改一条 INPUTS 常量：用 /tmp 副本重算哈希证明锚有牙
    with tempfile.TemporaryDirectory() as tmp:
        tmp_web = Path(tmp) / "web"
        for sub in ("src/scene", "scripts"):
            (tmp_web / sub).mkdir(parents=True, exist_ok=True)
        shutil.copy(MATERIALS, tmp_web / "src/scene/materials.ts")
        shutil.copy(CLASSES, tmp_web / "src/scene/material_classes.ts")
        mutated = (tmp_web / "src/scene/materials.ts").read_text(encoding="utf-8")
        mutated = mutated.replace("metalness: 0.0, roughness: 0.62, envMapIntensity: 1.3", 
                                  "metalness: 0.0, roughness: 0.62, envMapIntensity: 2.0")
        (tmp_web / "src/scene/materials.ts").write_text(mutated, encoding="utf-8")
        h2 = current_hashes(tmp_web)
        cases.append(("② ground_wet.envMapIntensity 1.3→2.0 ⇒ 常量哈希必变（红）",
                      h2["materials_inputs_constants_sha256"] != hashes["materials_inputs_constants_sha256"]
                      and h2["materials_inputs_block_sha256"] != hashes["materials_inputs_block_sha256"]))
    # ③ 改一个类别区间
    run("③ 改类别区间 ⇒ I-3h 必红", mutate_hash=lambda h: h.__setitem__("material_class_block_sha256", "0" * 64))
    # ④ 往 SURFACES_EXT 塞一个已在 SURFACES 里的 id
    run("④ 交集非空 ⇒ I-3f 必红", mutate_report=lambda r: r.__setitem__("intersection", ["glass"]))
    # ⑤ metal 成员 metalness 置 0.04
    def lower_metal(r):
        for e in r["surfaces_ext"]:
            if e["class"] == "metal":
                e["metalness"] = 0.04
                break
    run("⑤ metal 成员 metalness 置 0.04 ⇒ I-3i 必红", mutate_report=lower_metal)

    # ⑥ 从**场景实际实例化面**里摘掉一条 ext 表面 ⇒ I-3g+ 必红（A3 的负对照，机读形态）
    run("⑥ 场景摘掉一条 ext 表面 ⇒ I-3g+ 必红",
        mutate_report=lambda r: r.__setitem__("scene_used_ext", r["scene_used_ext"][:-1]))
    # ⑦ **渲染面**摘掉一条 ext 表面 ⇒ I-3g（visible）必红（N5-r3 / A6 的负对照，机读形态）
    run("⑦ 渲染面摘掉一条 ext 表面 ⇒ I-3g(visible) 必红",
        mutate_report=lambda r: r.__setitem__("scene_visible_ext", list(r["scene_visible_ext"])[:-1]))
    # ⑧ legacy 侧下界缺失（摘掉一条地面族）⇒ I-3g（legacy floor）必红
    run("⑧ 渲染面摘掉一条地面族 ⇒ I-3g(legacy floor) 必红",
        mutate_report=lambda r: r.__setitem__("scene_visible_legacy",
                                              [x for x in r["scene_visible_legacy"] if x != "ground_grass"]))

    ok = True
    for label, red in cases:
        if not red:
            ok = False
        print(f"  selftest {label}: {'RED(期望)' if red else 'GREEN(异常！)'}")
    print(f"selftest: {'OK（%d 条负对照全部判红）' % len(cases) if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", default=str(WEB / "scripts/assert_inputs.json"))
    ap.add_argument("--report", default=str(WS / "v0/spikes/n5-asset/readback/material_report.json"))
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    inputs_path = Path(args.inputs)
    report_path = Path(args.report)
    if not inputs_path.is_file() or not report_path.is_file():
        print(f"E_ENV: missing inputs({inputs_path}) or report({report_path})", file=sys.stderr)
        return 2
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    hashes = current_hashes()

    if args.selftest:
        return selftest(inputs, report, hashes, PACK_MANIFEST)

    failures, warnings = check(inputs, report, hashes, PACK_MANIFEST)
    out = {
        "schema_version": "n5-material-class-check/1",
        "inputs": str(inputs_path),
        "report": str(report_path),
        "current_hashes": hashes,
        "failures": failures,
        "warnings": warnings,
    }
    if args.json_out:
        p = Path(args.json_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"material_class_check: wrote {p}")
    print(f"material_class_check: failures={len(failures)} warnings={len(warnings)}")
    for f in failures:
        print(f"  FAIL  {f}")
    for w in warnings:
        print(f"  WARN  {w}")
    if failures:
        print("material_class_check: FAILED")
        return 1
    print("material_class_check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
