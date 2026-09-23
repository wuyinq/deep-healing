#!/usr/bin/env python3
"""F1 负例：`scene_assert` 两态判据必须**真的有命中能力**（R2 / CRITICAL-1 / M3-01 / M3-14）。

每个 case 在**整树副本**（`/tmp/r3-artisan/<case>/02_source`，旁挂 `node_modules` 软链）里注入，
跑 `node 02_source/v0_skeleton/web/scripts/scene_assert.mjs`，按
`crash` / `judged_red` / `judged_green` 分类（只有 `judged_red` 记 `turned_red`）。

R3 / G2 新增三条负例（对应 §3B-1 G2③）：
  (a) `f1e_reading_dependent_size`  —— 读法相关**尺寸**（顶点数恒 24 ⇒ 旧判据看不见）
  (b) `f1f_violation_in_rebuild`    —— 违规写在 `rebuild()` 装配路径里
  (c) `f1g_mesh_layer_after_assembly` —— 装配**之后**（网格层）再分叉

用法：python3 -B spikes/s13-render/negctl/f1_scene_assert_negctl.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import negctl_lib as lib  # noqa: E402

WORLD_REL = "v0_skeleton/web/src/scene/world.ts"
ASSERT_REL = "v0_skeleton/web/scripts/scene_assert.mjs"

CASES = [
    {
        "case": "f1_pristine",
        "why": "阳性对照：无注入 ⇒ 必须绿（PASS>=15 / exit 0）",
        "expect": "judged_green",
        "inject": [],
    },
    {
        "case": "f1a_reading_dependent_offset",
        "why": "D-7 明令禁止：深层态换一套坐标（读法相关装配偏移）",
        "expect": "judged_red",
        "expect_fail": "two_reads_share_geometry",
        "inject": [(WORLD_REL, "underneath: { y_offset_mm: 0, drop_kind: null }",
                    "underneath: { y_offset_mm: 12345, drop_kind: null }")],
    },
    {
        "case": "f1b_reading_dependent_drop_entity",
        "why": "D-7 明令禁止：深层态少一个实体（读法相关丢 kind）",
        "expect": "judged_red",
        "expect_fail": "two_reads_share_geometry",
        "inject": [(WORLD_REL, "underneath: { y_offset_mm: 0, drop_kind: null }",
                    "underneath: { y_offset_mm: 0, drop_kind: 'npc' }")],
    },
    {
        "case": "f1c_global_position_shift",
        "why": "M3-14 替换：R1 的 N-10 形态（两读法共用同一路径 +12345）现在必须被坐标判据捕获",
        "expect": "judged_red",
        "expect_fail": "geometry_positions_match_seeded_state",
        "inject": [(WORLD_REL, "position: [pos.x / MM, (pos.y + profile.y_offset_mm) / MM, pos.z / MM]",
                    "position: [(pos.x + 12345) / MM, (pos.y + profile.y_offset_mm) / MM, pos.z / MM]")],
    },
    {
        "case": "f1d_report_ignores_reading",
        "why": "读法必须真被接收并传进装配：让 geometryReport 丢弃入参 ⇒ 独立装配判据必须红",
        "expect": "judged_red",
        "expect_fail": "two_reads_are_independent_assemblies",
        "inject": [(WORLD_REL, "  const boxes = buildEntityBoxes(state, reading);",
                    "  const boxes = buildEntityBoxes(state);"),
                   (WORLD_REL, "  return {\n    reading,\n    entity_count: boxes.length,",
                    "  return {\n    reading: 'surface',\n    entity_count: boxes.length,")],
    },
    {
        "case": "f1e_reading_dependent_size",
        "why": ("R3 / G2③a：读法相关**尺寸**。`BoxGeometry` 的位置顶点数与尺寸**无关**（恒 24）"
                "⇒ 只比顶点数的旧判据看不见这种 D-7 违规；形状指纹必须红。"),
        "expect": "judged_red",
        "expect_fail": "two_reads_share_geometry",
        "inject": [(WORLD_REL, "    const size = sizeFor(entity.kind);",
                    "    const baseSize = sizeFor(entity.kind);\n"
                    "    const size = (reading === 'underneath' ? baseSize.map((value) => value * 0.35) : baseSize)"
                    " as [number, number, number];")],
    },
    {
        "case": "f1f_violation_in_rebuild",
        "why": ("R3 / G2③b：违规写在 `rebuild()` **装配路径**里（装配函数的产物本身仍等价）"
                "⇒ 只有从场景图 mesh 层读回的判据能看见。"),
        "expect": "judged_red",
        "expect_fail": "two_reads_share_rendered_geometry",
        "inject": [(WORLD_REL, "    const boxes = buildEntityBoxes(state, currentReading);",
                    "    const boxes = buildEntityBoxes(state, currentReading);\n"
                    "    if (currentReading === 'underneath') { boxes.forEach((box) => { box.position[1] += 2; }); }")],
    },
    {
        "case": "f1g_mesh_layer_after_assembly",
        "why": ("R3 / G2③c（= Raven r2 的 a5 形态）：装配**之后**在网格层再分叉"
                "（直接改 mesh 的 geometry 属性）⇒ 场景图读回判据必须红。"),
        "expect": "judged_red",
        "expect_fail": "two_reads_share_rendered_geometry",
        "inject": [(WORLD_REL, "      meshes.set(box.id, mesh);\n    });\n  }",
                    "      meshes.set(box.id, mesh);\n    });\n"
                    "    if (currentReading === 'underneath') { for (const mesh of meshes.values())"
                    " { (mesh.geometry as THREE.BoxGeometry).scale(3, 3, 3); } }\n  }")],
    },
]


def main() -> int:
    before = lib.sha_tree(lib.SRC)
    results = []
    for spec in CASES:
        root = lib.fresh_copy(spec["case"])
        injections = []
        for rel, old, new in spec["inject"]:
            injections.append(lib.inject(root / "02_source" / rel, old, new))
        cwd = root / "02_source" / "v0_skeleton" / "web"
        exit_code, stdout, stderr, secs = lib.run(["node", "scripts/scene_assert.mjs"], cwd)
        verdict = lib.classify_scene_assert(exit_code, stdout, stderr)
        log = lib.write_log(f"negctl-{spec['case']}.log",
                            f"# case {spec['case']}\n# copy {root}\n# injections: {injections}\n"
                            f"# cmd: node scripts/scene_assert.mjs   (cwd {cwd})\n"
                            f"# exit={exit_code} seconds={secs}\n# stderr:\n{stderr}\n# stdout:\n{stdout}\n")
        ok = verdict["verdict"] == spec["expect"]
        if spec.get("expect_fail"):
            ok = ok and spec["expect_fail"] in verdict["fail_names"]
        results.append({
            "case": spec["case"], "why": spec["why"], "copy": str(root),
            "injections": injections, "cmd": "node scripts/scene_assert.mjs", "cwd": str(cwd),
            "log": str(log), "seconds": secs, "expect": spec["expect"],
            "expect_fail": spec.get("expect_fail"), "ok": ok, **verdict,
        })
        print(f"[{spec['case']}] verdict={verdict['verdict']} exit={exit_code} "
              f"PASS={verdict['pass']} FAIL={verdict['fail']} fail_names={verdict['fail_names']} ok={ok}")
    after = lib.sha_tree(lib.SRC)
    summary = {
        "round": "R3", "item": "F1 scene_assert teeth (G2 shape fingerprint + assembly path)",
        "neg_root": str(lib.NEG_ROOT), "delivery_face_unchanged": before == after,
        "delivery_face_sha_tree": before, "cases": results,
        "turned_red": sorted(r["case"] for r in results if r["turned_red"]),
        "crashes": sorted(r["case"] for r in results if r["verdict"] == "crash"),
        "all_ok": all(r["ok"] for r in results) and before == after,
    }
    path = lib.write_summary("f1-negctl-summary.json", summary)
    print(f"summary={path} delivery_face_unchanged={before == after} all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
