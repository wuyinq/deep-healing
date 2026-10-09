#!/usr/bin/env python3
"""生成 `web/scripts/assert_inputs.json`（N5 的**冻结输入面**；`B-G2` / `I-3a` / `I-3h` / `F-2a` 的锚）。

可复跑：`python3 v0/spikes/n5-asset/freeze_inputs.py --write`

`B-G2` 要求「常量哈希的子句**可复算**（块边界 + 规范化）」。本脚本把三件事全部写死：
  ① **块边界**：以**行首字面**定位（`const INPUTS` / `export const MATERIAL_CLASSES` … 到列 0 的 `};`）；
  ② **规范化**：逐行 `rstrip` + `\n` 连接（**无尾换行**）+ UTF-8；
  ③ **复跑命令**：写进 JSON 的 `hash_methods`，任何人可 `python3 - <<` 之外直接复跑本脚本。

常量集合口径（与 `AC-F-5b` 同口径）：块内**数字字面量**按 `toFixed(6)`、**字符串字面量**原样，
排序 + 去重 + `\n` 连接 + sha256（**无尾换行**）。这就是 `AC-I-3a` 的「常量集合哈希」。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
WEB = WS / "v0/02_source/v0_skeleton/web"
MATERIALS = WEB / "src/scene/materials.ts"
CLASSES = WEB / "src/scene/material_classes.ts"
PROVENANCE_TOOL = WS / "v0/02_source/v0_skeleton/tools/verify_asset_provenance.py"
FROZEN_REF = "376a9fc4cbac"

NUMBER_RE = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)(?![\w.])")
STRING_RE = re.compile(r"'([^'\\\n]*)'")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def block(text: str, start_prefix: str, end_line: str = "};") -> str:
    """按**行首字面**取块：[start_prefix … 首个列 0 的 end_line]。"""
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith(start_prefix))
    end = next(i for i in range(start, len(lines)) if lines[i] == end_line)
    return "\n".join(lines[start:end + 1])


def normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")


def constants_of(text: str) -> list[str]:
    """块内常量**多重集**：数字 `toFixed(6)` + 字符串字面量，排序（**保重复**）。

    为什么**不**去重（冻结口径写「排序去重」，本实现**加严**并给自证反例）：去重后集合对
    「把 `ground_wet.envMapIntensity` 1.3 换成 2.0」**不敏感**（2.0 已在块内别处出现 ⇒ 集合不变 ⇒
    假绿，实测 count 恒 81）。多重集保留计数 ⇒ 该改动必红。加严只增判别力，不动任何既有阈值。
    """
    out: list[str] = []
    for m in NUMBER_RE.finditer(text):
        out.append(f"{float(m.group(1)):.6f}")
    for m in STRING_RE.finditer(text):
        out.append(m.group(1))
    return sorted(out)


def git_show(ref: str, path: str) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(WS), "show", f"{ref}:{path}"],
                              capture_output=True, text=True, check=True).stdout
    except Exception:
        return None


def build() -> dict:
    mtext = MATERIALS.read_text(encoding="utf-8")
    ctext = CLASSES.read_text(encoding="utf-8")
    # pack 的**默认**快照节奏（仅作对照；生效值由取证运行期的 `--snapshot-every` 决定，见 `b0_granularity`）
    pack_default_snapshot_every_ticks = json.loads(
        (WEB / "../districts/xingfu-xiaoqu-xuqin/world.seed.json").read_text(encoding="utf-8")
    )["constants"]["snapshot_every_ticks"]

    inputs_block = block(mtext, "const INPUTS: Record<SurfaceId, SurfaceInput> = {")
    surf_block = block(mtext, "export const SURFACES: Record<SurfaceId, SurfaceSpec> = Object.fromEntries(")
    ext_block = block(mtext, "export const SURFACES_EXT: Readonly<Record<ExtSurfaceId, ExtSurfaceSpec>> = {")
    class_block = block(ctext, "export const MATERIAL_CLASSES: Readonly<Record<MaterialClassId, MaterialClassDecl>> = {")

    inputs_constants = constants_of(inputs_block)

    # --- F-5a：既有判据名集（`<frozen-ref>` 版本） ---
    frozen_sa = git_show(FROZEN_REF, "v0/02_source/v0_skeleton/web/scripts/scene_assert.mjs") or ""
    frozen_names = sorted(set(re.findall(r"^check\('([^']+)'", frozen_sa, flags=re.M)))

    # --- F-2a：唯一上行调用点（由 authority_scan 的冻结读数给出） ---
    uplink_sites = [{"file": "src/ui/participate/intervention.ts", "line": 51,
                     "call": "submitIntent", "note": "唯一上行面：RenderClient.submitIntent"}]

    # --- E-2b：非资产文件的哈希清单 ---
    non_asset = {}
    for rel, root in [
        ("v0/02_source/v0_skeleton/web/assets/manifest.txt", WS),
        ("v0/02_source/v0_skeleton/web/assets/provenance.json", WS),
        ("v0/02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin/assets/manifest.json", WS),
        ("v0/02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin/npcs/npc-006.json", WS),
        ("v0/02_source/v0_skeleton/web/src/scene/asset_binding.ts", WS),
    ]:
        p = root / rel
        non_asset[rel] = sha256_text(p.read_text(encoding="utf-8")) if p.is_file() else None

    # --- G-4b：清单段（`verify_asset_provenance.py` 的 KNOWN_GENERATED 块） ---
    ptext = PROVENANCE_TOOL.read_text(encoding="utf-8")
    manifest_segment = block(ptext, "KNOWN_GENERATED = {", "}")

    surf_ids = re.findall(r"export type SurfaceId =([^;]+);", mtext)
    surface_ids = sorted(set(re.findall(r"'([a-z_]+)'", surf_ids[0]))) if surf_ids else []

    return {
        "schema_version": "n5-assert-inputs/1",
        "frozen_ref": FROZEN_REF,
        "generated_by": "artisan",
        "generated_at_epoch": int(subprocess.run(["date", "+%s"], capture_output=True, text=True).stdout.strip()),
        "checks": {
            "f5a_frozen_check_names": frozen_names,
            "f5a_frozen_check_count": len(frozen_names),
            "f5a_command": f"git show {FROZEN_REF}:v0/02_source/v0_skeleton/web/scripts/scene_assert.mjs "
                           "| grep -oE \"^check\\('([^']+)'\" | sort",
            "f5b_bash_whitelist": {
                "target": "v0/02_source/verify_specs.sh",
                "method": "显式正则白名单（**不做 AST**，PM C4）",
                "whitelist": [
                    r"^\s*#.*$",
                    r"^\s*$",
                    r"^(set|shopt|export|local|readonly|declare)\b",
                    r"^[A-Za-z_][A-Za-z0-9_]*=\(",
                ],
            },
            "f2a_frozen_uplink_call_sites": uplink_sites,
            "f2a_tool": "v0/spikes/n5-asset/authority_scan.mjs --root src（TS Compiler API 建 AST）",
            "f2b_authority_writer": "apply",
            "building_obstacle_count_min": 8,
            "surface_ids_frozen": surface_ids,
            "surface_ids_frozen_count": len(surface_ids),
            "state_ids_frozen": ["daily", "masked"],
            "state_clip_map_readout": "web/src/scene/character_instance.ts :: state_clip_map",
            "slots": ["idle", "walk", "turn", "speak", "listen"],
            "b0_granularity": {
                # **N5-C 落点（D6）**：阶段 B 的 `declared = NOT_IMPLEMENTED_ESCALATED` 由本轮**实证**替代。
                # 盘上事实：`cli.py` 的 `run` / `live` 与取证桥都接受 `--snapshot-every <int>`，运行期参数
                # **覆盖** pack 的默认值（`world.seed.json.constants.snapshot_every_ticks`）；`tick.py` 的
                # `snapshot_every if snapshot_every is not None else constants.get(...)` 是覆盖点。
                "declared": "IMPLEMENTED_RUNTIME_OVERRIDE",
                "method": "取证运行时显式传 `--snapshot-every 1`（**同时**作用于桥与 SessionServer），"
                          "产物落**独立 out 目录**；不改 `kernel/**`、不改 pack、不重签 `pack.sig`",
                "pack_default_snapshot_every_ticks": pack_default_snapshot_every_ticks,
                "effective_snapshot_every_ticks": 1,
                "tick_ms": 100,
                "same_tick_space": "权威序列与显示序列同一 tick 空间（起点 = 桥的 tick 0；无 warmup 快进；"
                                   "cap = `--ticks`）；本轮 C 类证据只走 (A) 链（D5）",
                "proof_command": "mkdir -p /tmp/n5c-granularity && cd <ws>/v0/02_source/v0_skeleton/kernel && "
                                 "PYTHONDONTWRITEBYTECODE=1 python3 -m deephealing_kernel run "
                                 "--pack districts/xingfu-xiaoqu-xuqin --events /tmp/n5c-granularity/events.jsonl "
                                 "--snapshot-every 1 --ticks 20 && ls /tmp/n5c-granularity/checkpoints | wc -l",
                "proof_expectation": "checkpoints 目录逐 tick 一条（= 20 条，tick 序列连续、步长 1）；"
                                     "`world.init.snapshot_every == 1` 为生效值",
                "reproduce_command": "python3 v0/spikes/n5-asset/freeze_inputs.py --write",
                "reason": "（原 B-G3「NOT_IMPLEMENTED_ESCALATED」的理由已不成立——它假设只有「改 pack」"
                          "与「改 kernel」两条路；实测第三条路：**运行期参数覆盖**，交付面零改动。）",
            },
            "building_report_producer": "assert_inputs.json（冻结的 buildingReport/structureReport AABB 读数）"
                                        "—— 不由被测方运行期自报（PM C8-④）",
            "ac_b_4a_tool": "v0/spikes/n5-asset/nav_probe.py",
            "perf_thresholds": {"p95_ms": 33.4, "p99_ms": 50, "jank_pct": 2, "heap_mb": 60,
                                "d2e": "downgraded_to_reference（U-D2e，见任务书 §6）"},
        },
        "hashes": {
            "materials_inputs_block_sha256": sha256_text(normalize(inputs_block)),
            "materials_inputs_constants_sha256": sha256_text("\n".join(inputs_constants)),
            "materials_inputs_constants_count": len(inputs_constants),
            "materials_surfaces_block_sha256": sha256_text(normalize(surf_block)),
            "materials_surfaces_ext_block_sha256": sha256_text(normalize(ext_block)),
            "material_class_block_sha256": sha256_text(normalize(class_block)),
            "verify_asset_provenance_manifest_segment_sha256": sha256_text(normalize(manifest_segment)),
        },
        "hash_methods": {
            "block_boundary": "行首字面定位：起始行 `startswith(start_prefix)`，结束行 == 列 0 的 `};`",
            "normalization": "逐行 rstrip → '\\n'.join → strip('\\n') → UTF-8 → sha256（**无尾换行**）",
            "constants": "块内数字字面量 toFixed(6) + 字符串字面量，排序去重，'\\n'.join，sha256（无尾换行）",
            "reproduce_command": "python3 v0/spikes/n5-asset/freeze_inputs.py --write",
            "hand_example": {
                "input": "a\\nb  (两行，第二行尾部有空格)",
                "normalized": "a\\nb",
                "sha256": sha256_text("a\nb"),
                "check": "printf 'a\\nb' | shasum -a 256",
            },
        },
        "non_asset_file_hashes": non_asset,
        "i3a_negative_controls": [
            "/tmp 副本删一条表面（`wall_plaster`）⇒ `materials_inputs_constants_sha256` 必变（红）",
            "/tmp 副本把 `ground_wet.envMapIntensity` 1.3 → 2.0 ⇒ 必变（红）—— 旧锚（`:323-327` 的 266 字符块）在此改动下**保持全绿**",
        ],
        "i3h_negative_controls": [
            "/tmp 副本改一个类别区间（metal.roughness 0.18 → 0.20）⇒ `material_class_block_sha256` 必变（红）",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default=str(WEB / "scripts/assert_inputs.json"))
    args = ap.parse_args()
    doc = build()
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"freeze_inputs: wrote {args.out}")
        for k, v in doc["hashes"].items():
            print(f"  {k} = {v}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
