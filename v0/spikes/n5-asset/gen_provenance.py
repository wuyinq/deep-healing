#!/usr/bin/env python3
"""生成 `web/assets/provenance.json`（N5 / B-1；`AC-G-*`、`AC-E-2b` 的登记面）。

可复跑：`python3 v0/spikes/n5-asset/gen_provenance.py --write`
幂等：除 `registered_at` 外全部字段由盘上读数派生（哈希、字节数）；重复跑输出逐字节一致。

许可证据快照（外部锚）：`v0/spikes/n5-asset/frozen/license_evidence/` 下的**真实抓取件**，
其 sha256 由本脚本重算写入 `license_evidence.snapshot_sha256`（G-3b 的外部锚）。
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
WEB_ASSETS = WS / "v0/02_source/v0_skeleton/web/assets"
PACK = WS / "v0/02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin"
EVID = WS / "v0/spikes/n5-asset/frozen/license_evidence"

N5_REGISTERED_AT = "2026-10-08T03:28:02Z"
N4_FIRST_REGISTERED_AT = "2026-09-24T13:37:28+08:00"

PH_URL = "https://polyhaven.com/license"
PH_SNAPSHOT = "v0/spikes/n5-asset/frozen/license_evidence/polyhaven-license.html"
CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
CC0_SNAPSHOT = "v0/spikes/n5-asset/frozen/license_evidence/cc0-1.0-legalcode.txt"
CCBY_URL = "https://creativecommons.org/licenses/by/4.0/"
CCBY_SNAPSHOT = "v0/spikes/n5-asset/frozen/license_evidence/cc-by-4.0-legalcode.txt"
CESIUM_README_URL = ("https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/"
                     "main/Models/CesiumMan/README.md")
CESIUM_SNAPSHOT = "v0/spikes/n5-asset/frozen/license_evidence/cesiumman-README.md"

# ---- Poly Haven 表面族（作者 / 上游 asset id / 上游目录取自 `web/assets/manifest.txt` 的逐行登记） ----
PH_FAMILIES = {
    "grey_plaster": dict(asset_id="grey_plaster", author="Rob Tuytel", upstream="tex",
                         surface="wall_plaster", files={"Diffuse.jpg": "色图", "nor_gl.jpg": "法线（OpenGL 朝向）",
                                                        "arm.jpg": "AO(R)/粗糙(G)/金属(B) 打包图"}),
    "brick_wall_04": dict(asset_id="brick_wall_04", author="Dimitrios Savva", upstream="tex2",
                          surface="wall_brick", files={"Diffuse.jpg": "色图", "nor_gl.jpg": "法线（OpenGL 朝向）",
                                                       "arm.jpg": "AO/粗糙/金属 打包图"}),
    "clay_roof_tiles_02": dict(asset_id="clay_roof_tiles_02", author="Amal Kumar", upstream="tex2",
                               surface="roof_tile", files={"Diffuse.jpg": "色图", "nor_gl.jpg": "法线（OpenGL 朝向）",
                                                           "arm.jpg": "AO/粗糙/金属 打包图"}),
    "brick_pavement": dict(asset_id="brick_pavement", author="Charlotte Baglioni", upstream="tex",
                           surface="pavement_brick", files={"Diffuse.jpg": "色图", "nor_gl.jpg": "法线（OpenGL 朝向）",
                                                            "arm.jpg": "AO/粗糙/金属 打包图"}),
    "asphalt_02": dict(asset_id="asphalt_02", author="Rob Tuytel", upstream="tex",
                       surface="road_asphalt", files={"Diffuse.jpg": "色图", "nor_gl.jpg": "法线（OpenGL 朝向）",
                                                      "arm.jpg": "AO/粗糙/金属 打包图"}),
    "grass_ground": dict(asset_id="grass_ground", author="Charlotte Baglioni", upstream="tex",
                         surface="ground_grass", files={"Diffuse.jpg": "色图", "nor_gl.jpg": "法线（OpenGL 朝向）",
                                                        "arm.jpg": "AO/粗糙/金属 打包图"}),
    "brushed_concrete": dict(asset_id="brushed_concrete", author="Dimitrios Savva", upstream="tex",
                             surface="ground_wet+glass", files={"Diffuse.jpg": "色图", "nor_gl.jpg": "法线（OpenGL 朝向）",
                                                                "arm.jpg": "AO/粗糙/金属 打包图"}),
    "black_painted_planks": dict(asset_id="black_painted_planks", author="Dimitrios Savva", upstream="tex2",
                                 surface="wood_plank", files={"Diffuse.jpg": "色图", "nor_gl.jpg": "法线（OpenGL 朝向）",
                                                              "arm.jpg": "AO/粗糙/金属 打包图"}),
    "corrugated_iron_02": dict(asset_id="corrugated_iron_02", author="Sergej Majboroda", upstream="tex2",
                               surface="metal_corrugated", files={"Diffuse.jpg": "色图", "nor_gl.jpg": "法线（OpenGL 朝向）",
                                                                  "arm.jpg": "AO/粗糙/金属 打包图"}),
    "cotton_jersey": dict(asset_id="cotton_jersey", author="colormass", upstream="tex2",
                          surface="fabric_cotton", files={"Diffuse.jpg": "色图", "nor_gl.jpg": "法线（OpenGL 朝向）",
                                                          "arm.jpg": "AO/粗糙/金属 打包图"}),
    "leather_red_02": dict(asset_id="leather_red_02", author="Rob Tuytel", upstream="tex2",
                           surface="leather_red", files={"coll2.jpg": "色图（上游色图名为 coll2，不是 Diffuse）",
                                                         "nor_gl.jpg": "法线（OpenGL 朝向）",
                                                         "arm.jpg": "AO/粗糙/金属 打包图"}),
}

CONVERSION_PH = {
    "tool": "sips (macOS)",
    "version": "N4-r3 登记口径",
    "params": "源 2048² 由 refs/asset-pack/<upstream>/<asset>/ 取用，经 sips 缩放至 1024² + JPEG q85（逐字见 "
              "v0/02_source/v0_skeleton/web/assets/manifest.txt 的「生成方式」列）",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def evidence(url, snapshot_rel, fetched_at):
    snap = WS / snapshot_rel
    return {
        "url": url,
        "fetched": snap.is_file(),
        "fetched_at": fetched_at,
        "snapshot_path": snapshot_rel,
        "snapshot_sha256": sha256_file(snap) if snap.is_file() else None,
    }


def entry_for(path: Path, rel: str, **kw) -> dict:
    base = {
        "path": rel,
        "asset_id": None,
        "role": "surface",
        "source_type": "cc0_library",
        "license": "cc0-1.0",
        "license_evidence": evidence(PH_URL, PH_SNAPSHOT, "2026-10-08T03:27:00Z"),
        "author": None,
        "attribution": None,
        "license_url": CC0_URL,
        "ai_generated": False,
        "generator": None,
        "generator_version": None,
        "prompt_digest": None,
        "original": {"path_or_url": None, "sha256": None},
        "conversion": CONVERSION_PH,
        "converted_sha256": sha256_file(path),
        "converted_pixel_hash": None,
        "editable_source": "none（CC0 扫描件，上游不提供工程源）；导出流程 = sips 缩放 + JPEG q85（见 conversion.params）",
        "binding_ref": None,
        "byte_size": path.stat().st_size,
        "registered_at": N5_REGISTERED_AT,
        "first_registered_at": N4_FIRST_REGISTERED_AT,
        "note": "哈希口径 = 字节哈希（file_bytes），`shasum -a 256` 可复算（01 §7.2 v3 统一口径）"
                "；`registered_at` = **N5 本轮重新登记时刻**（A-1c 的口径），`first_registered_at` = "
                "N4 首次登记时刻（追溯用，不改写历史）。",
    }
    base.update(kw)
    return base


def build() -> dict:
    assets = []

    # ---- 1) Poly Haven 表面族（33 件） ----
    for fam, meta in PH_FAMILIES.items():
        for fname, purpose in meta["files"].items():
            path = WEB_ASSETS / fam / fname
            assert path.is_file(), f"missing {path}"
            rel = f"{fam}/{fname}"
            assets.append(entry_for(
                path, rel,
                asset_id=f"{meta['asset_id']}_{fname.split('.')[0].lower()}",
                role="surface",
                source_type="cc0_library",
                license="cc0-1.0",
                author=meta["author"],
                attribution=f"Poly Haven — {meta['asset_id']}（{meta['author']}），CC0 1.0",
                original={
                    "path_or_url": f"refs/asset-pack/{meta['upstream']}/{meta['asset_id']}/{fname}（工作区只读资产包）",
                    "sha256": None,
                    "sha256_unavailable_reason": "上游原始件不在交付树内（工作区只读包不进 git）；"
                                                 "可核锚 = converted_sha256（字节哈希）",
                },
                binding_ref=f"surface:{meta['surface']}",
                note=f"用途：{meta['surface']} 的 {purpose}；" + base_note(),
            ))

    # ---- 2) HDRI（1 件） ----
    hdri = WEB_ASSETS / "hdri/kloofendal_overcast_puresky_2k.hdr"
    assets.append(entry_for(
        hdri, "hdri/kloofendal_overcast_puresky_2k.hdr",
        asset_id="kloofendal_overcast_puresky_2k",
        role="hdri",
        author="Greg Zaal",
        attribution="Poly Haven — kloofendal_overcast_puresky（Greg Zaal），CC0 1.0",
        original={
            "path_or_url": "refs/asset-pack/hdri/kloofendal_overcast_puresky_2k.hdr（工作区只读资产包）",
            "sha256": None,
            "sha256_unavailable_reason": "同表面族：上游原始件不在交付树内",
        },
        conversion={
            "tool": "byte-exact copy",
            "version": "N4-r3 登记口径",
            "params": "字节逐字复制（4 335 717 B，未重编码）—— 见 web/assets/manifest.txt",
        },
        binding_ref="environment:scene",
        note="用途：scene.background + scene.environment（HDRI 主导照明）；" + base_note(),
    ))

    # ---- 3) 角色 GLB（N5 新增，1 件） ----
    glb = WEB_ASSETS / "character/xuqin-body.glb"
    assets.append(entry_for(
        glb, "character/xuqin-body.glb",
        asset_id="xuqin_body_cesiumman",
        role="character",
        source_type="cc_by_library",
        license="cc-by-4.0",
        license_evidence=evidence(CESIUM_README_URL, CESIUM_SNAPSHOT, "2026-10-08T03:23:00Z"),
        license_url=CCBY_URL,
        author="Cesium",
        attribution="© 2017 Cesium — CC BY 4.0 International（经 Khronos glTF-Sample-Assets 分发："
                    "Models/CesiumMan/glTF-Binary/CesiumMan.glb）",
        original={
            "path_or_url": ("https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/"
                            "main/Models/CesiumMan/glTF-Binary/CesiumMan.glb"),
            "sha256": None,
            "sha256_unavailable_reason": "下载件即交付件，字节与上游一致（curl 未重编码）；"
                                         "可核锚 = converted_sha256",
        },
        conversion={
            "tool": "curl -L（byte-exact download，无重编码、无格式转换）",
            "version": "curl (macOS 内置)",
            "params": "直接落盘为 web/assets/character/xuqin-body.glb；容器 glTF binary v2，"
                      "22 nodes / 1 mesh / 1 skin(19 joints) / 1 image / 1 animation(57 channels)，自包含无外部 uri",
        },
        editable_source="none（上游 GLB 为分发件，无 .blend 工程源）；导出流程 = 直接使用上游 GLB，"
                        "本仓库不做二次导出",
        binding_ref="binding:xuqin_default",
        registered_at=N5_REGISTERED_AT,
        note="N5 / B-1 真实 rigged 人物资产（含骨骼 19 joints 与动画）。许可页 fetched=true，"
             "快照 sha256 为盘上真实抓取件；" + base_note(),
    ))

    # ---- 4) 角色皮肤贴图（U-4：许可未证实 ⇒ 从运行时剔除） ----
    skin = WEB_ASSETS / "character/skin-pale-01.jpg"
    assets.append(entry_for(
        skin, "character/skin-pale-01.jpg",
        asset_id="skin-pale-01",
        role="surface",
        source_type="ai_generated",
        license="unknown",
        license_evidence={
            "url": "none",
            "fetched": False,
            "fetched_at": None,
            "snapshot_path": None,
            "snapshot_sha256": None,
        },
        license_url=None,
        author=None,
        attribution=None,
        ai_generated=True,
        generator="Seedream",
        generator_version="doubao-seedream-5-0",
        prompt_digest=None,
        generator_evidence={
            "source": "文件内嵌 C2PA 清单（JUMBF/CBOR）",
            "assertion": "c2pa.actions.v2 → action=c2pa.created, softwareAgent.name=Volcengine_Ark_CN, "
                         "softwareAgent.version=1.0.0, parameters.model_name=doubao-seedream-5-0, "
                         "when=2026-09-24T01:38:21Z",
            "digital_source_type": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
            "claim_generator": "c2pa-rs 0.78.4",
            "extraction_command": "python3 v0/spikes/n5-asset/c2pa_scan.py --path "
                                  "v0/02_source/v0_skeleton/web/assets/character/skin-pale-01.jpg",
            "cross_check": "与 web/assets/manifest.txt:67 的生成记录（generator=Seedream / "
                           "model id doubao-seedream-5-0-260128）**不矛盾**（G-4c 的 EXIF/XMP 一致性）",
        },
        original={"path_or_url": "refs/asset-pack/character/skin-pale-01.png（PM 提供）",
                  "sha256": None,
                  "sha256_unavailable_reason": "该只读包内 tex-manifest.json / tex2-manifest.json 均无此条目"},
        conversion={"tool": "byte-exact copy", "version": "N4-r3 登记口径",
                    "params": "字节逐字复制（504 506 B，md5 ca2406484d0bad2d6d474912e10d5ff8，未重编码）"},
        editable_source="none（生成式图像无工程源）",
        binding_ref=None,
        runtime_excluded=True,
        license_disposition="runtime_excluded",
        runtime_excluded_reason=(
            "U-4 二选一执行 ⇒ **取 ②「从运行时剔除」**。理由：① 需要 prompt_digest，而 C2PA 清单与 "
            "web/assets/manifest.txt **都没有原始提示词** ⇒ prompt_digest **无法在不伪造的前提下填写**；"
            "且 (generator=doubao-seedream-5-0) 在 `asset.license.table.data.json` 中**查不到** ⇒ "
            "G-5 的 default-deny 判定为**拒收**。⇒ 该件不得进入运行时渲染路径（`world.ts` 不再调用 "
            "`loadSkinDetailMaterial`）。文件保留在树内**仅作历史登记**（E-2b 覆盖 + N4 判据 "
            "`skin_asset_is_ai_generated` 依赖 manifest 行），不参与 N5 运行时。"),
        note="许可未证实（源包无条目、无许可页）+ 生成器不在许可表白名单 ⇒ 运行时剔除。"
             "**绝不**标 CC0（用户 §六 + C-4）。",
    ))

    # ---- 5) 内容包角色参考图（5 件，ai_generated：C2PA 证书） ----
    refs = PACK / "assets/character-refs"
    ref_files = sorted(p.name for p in refs.glob("*.jpg"))
    for name in ref_files:
        path = refs / name
        assets.append(entry_for(
            path, f"assets/character-refs/{name}",
            asset_id=f"xuqin-ref-{name.replace('.jpg', '')}",
            role="reference",
            source_type="ai_generated",
            license="unknown",
            license_evidence={"url": "none", "fetched": False, "fetched_at": None,
                              "snapshot_path": None, "snapshot_sha256": None},
            license_url=None, author=None, attribution=None,
            ai_generated=True,
            generator="Seedream",
            generator_version="doubao-seedream-5-0",
            prompt_digest=None,
            generator_evidence={
                "source": "文件内嵌 C2PA 清单（JUMBF/CBOR）",
                "assertion": "c2pa.actions.v2 → c2pa.created, softwareAgent.name=Volcengine_Ark_CN, "
                             "parameters.model_name=doubao-seedream-5-0",
                "digital_source_type": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
                "extraction_command": "python3 v0/spikes/n5-asset/c2pa_scan.py --path " f"{rel_ws(path)}",
                "prompt_digest_unavailable_reason": "C2PA 清单不含原始提示词 ⇒ 记 GAP，不伪造 digest",
            },
            original={"path_or_url": f"refs/asset-pack/character-refs/{name}",
                      "sha256": None, "sha256_unavailable_reason": "只读包不进交付树"},
            conversion={"tool": "byte-exact copy / 内容包登记", "version": "N4 登记口径",
                        "params": "见内容包 assets/manifest.json 与 v0/02_source/manifest.txt 的登记行"},
            editable_source="none（生成式图像无工程源）",
            binding_ref="reference:A-1a",
            license_disposition="reference_only_escalated",
            note="A-1a 的风格/构图参考件（role=reference）；生成器由文件内嵌 C2PA 核出；"
                 "prompt_digest 不可得 ⇒ 记 GAP（不伪造）；"
                 "**G-5 default-deny**：`doubao-seedream-5-0` 不在 `asset.license.table.data.json` 的白名单内 ⇒ "
                 "按口径应**拒收**；本件是 N4 已验收的历史参考件（C-3：不改写 N4 结论），"
                 "**不进运行时渲染路径**（`role=reference`，只作取证参考）⇒ 记为**上抛项**而非静默放行；"
                 "许可证据 `fetched=false` ⇒ A-1a 的 `license_evidence.fetched == true` 记 GAP。" ,
        ))

    return {
        "schema_version": "n5-provenance/1",
        "pack_id": "xingfu-xiaoqu-xuqin",
        "coverage": {
            "asset_roots": ["v0/02_source/v0_skeleton/web/assets", 
                            "v0/02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin/assets"],
            "excluded_patterns": ["*/__pycache__/*", "*.pyc", "*/.pytest_cache/*", "*/.DS_Store",
                                  "*/node_modules/*", "*/.venv/*", "*/dist/*", "attic-*/*"],
            "non_asset_files": [
                {"path": "v0/02_source/v0_skeleton/web/assets/manifest.txt",
                 "why": "N4 资产**登记表**（人类可读 registry），不是被引用的素材；按 AC-E-2b 的"
                        "「非资产文件 ⇒ 哈希清单口径」记入 assert_inputs.json"},
                {"path": "v0/02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin/assets/manifest.json",
                 "why": "内容包**清单**（pack 元数据），同上按哈希清单口径覆盖"},
                {"path": "v0/02_source/v0_skeleton/districts/xingfu-xiaoqu-xuqin/npcs/npc-006.json",
                 "why": "AC-E-2b 明文归入「非资产文件」（改按哈希清单口径）"},
                {"path": "v0/02_source/v0_skeleton/web/src/scene/asset_binding.ts",
                 "why": "AC-E-2b 明文归入「非资产文件」（改按哈希清单口径）"},
            ],
        },
        "license_snapshots": {
            "polyhaven_license": {"path": PH_SNAPSHOT, "sha256": sha256_file(WS / PH_SNAPSHOT),
                                  "url": PH_URL, "fetched_at": "2026-10-08T03:27:00Z"},
            "cc0_legalcode": {"path": CC0_SNAPSHOT, "sha256": sha256_file(WS / CC0_SNAPSHOT),
                              "url": CC0_URL, "fetched_at": "2026-10-08T03:27:00Z"},
            "cc_by_4_0_legalcode": {"path": CCBY_SNAPSHOT, "sha256": sha256_file(WS / CCBY_SNAPSHOT),
                                    "url": CCBY_URL, "fetched_at": "2026-10-08T03:23:00Z"},
            "cesiumman_readme": {"path": CESIUM_SNAPSHOT, "sha256": sha256_file(WS / CESIUM_SNAPSHOT),
                                 "url": CESIUM_README_URL, "fetched_at": "2026-10-08T03:23:00Z"},
        },
        "assets": assets,
    }


def base_note() -> str:
    return "哈希口径 = 字节哈希（file_bytes），`shasum -a 256` 可复算（01 §7.2 v3 统一口径）"


def rel_ws(p: Path) -> str:
    return str(p.relative_to(WS))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default=str(WEB_ASSETS / "provenance.json"))
    args = ap.parse_args()
    doc = build()
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"gen_provenance: wrote {args.out} ({len(doc['assets'])} entries)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
