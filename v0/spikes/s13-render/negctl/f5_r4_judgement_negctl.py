#!/usr/bin/env python3
"""F5 / R4 负例：关闭 `R3-C1`（判据层）—— 加宽后的判据必须**真的**有牙。

背景（PM 独立复现，见 `.task-artisan-r4.md` §1）：AC-M3-8③ 的机器判据
`two_reads_share_rendered_geometry` 名不副实 —— 只覆盖 `geometry.parameters` + `position`
attribute + 装配后 `mesh.position`，于是「只作用于 `underneath` 读法」的
`mesh.scale` / `mesh.rotation` 注入**逃逸**，而 D-7 明文禁止的「换相机」此前**零判据**。

四个 case（R4-C）：
  - `r4_neg_mesh_scale`     装配后 `mesh.scale.set(3,3,3)`（underneath）⇒ `two_reads_share_rendered_geometry` 必红
  - `r4_neg_mesh_rotation`  装配后 `mesh.rotation.y = Math.PI/2`（underneath）⇒ 同上
  - `r4_neg_camera_switch`  underneath 分支 `camera.position.set(40,40,40)` ⇒ `two_reads_share_camera` 必红
  - `r4_ctl_position_shift` 对照（`mesh.position.x += 5` 形态）⇒ 仍红（不得因加宽而失效）

纪律（照旧，硬）：
  - 负例**一律**在整树副本上注入（`NEGCTL_ROOT=/tmp/r4-artisan`），交付面一个字节都不动；
  - `turned_red` **只给** `judged_red`；`crash` 单列；每条给 `delivery_face_unchanged`；
  - 每个 case 单独取交付面 sha256（跑前/跑后）⇒ `delivery_face_unchanged` 是**逐 case 实测**，不是全局自述。

用法：
  python3 -B spikes/s13-render/negctl/f5_r4_judgement_negctl.py            # GREEN 相位（加宽后）
  python3 -B spikes/s13-render/negctl/f5_r4_judgement_negctl.py red        # RED 相位（加宽**前**，复现逃逸）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["NEGCTL_ROOT"] = "/tmp/r4-artisan"  # R4-C：本轮负例根（必须在 import 之前设）

sys.path.insert(0, str(Path(__file__).resolve().parent))
import negctl_lib as lib  # noqa: E402

WORLD_REL = "v0_skeleton/web/src/scene/world.ts"
ASSERT_REL = "v0_skeleton/web/scripts/scene_assert.mjs"

# 注入锚点：`rebuild()` 的 forEach 尾部（`f1g` 用的同一锚点 ⇒ 已证明唯一命中）
REBUILD_TAIL = "      meshes.set(box.id, mesh);\n    });\n  }"
REBUILD_HEAD = "    const boxes = buildEntityBoxes(state, currentReading);"
CAMERA_JUDGEMENT = "two_reads_share_camera"

CASES = [
    {
        "case": "r4_pristine",
        "why": "阳性对照：无注入 ⇒ 必须绿（证明副本 + 依赖软链可用，不是环境假红）",
        "expect": "judged_green",
        "inject": [],
    },
    {
        "case": "r4_neg_mesh_scale",
        "why": ("R4-C / PM 读数 B：装配后把 underneath 的 mesh 放大 3 倍 —— 旧判据（只比 "
                "parameters/position attribute/mesh.position）看不见 ⇒ 加宽后 `mesh_scales` 必须抓到"),
        "expect": "judged_red",
        "expect_fail": "two_reads_share_rendered_geometry",
        "inject": [(WORLD_REL, REBUILD_TAIL,
                    "      meshes.set(box.id, mesh);\n"
                    "      if (currentReading === 'underneath') { mesh.scale.set(3, 3, 3); }\n"
                    "    });\n  }")],
    },
    {
        "case": "r4_neg_mesh_rotation",
        "why": ("R4-C / PM 读数 C：装配后把 underneath 的 mesh 转 90°（改 `rotation` ⇒ 同步改 "
                "`quaternion`）—— 旧判据看不见 ⇒ 加宽后 `mesh_rotations` 必须抓到"),
        "expect": "judged_red",
        "expect_fail": "two_reads_share_rendered_geometry",
        "inject": [(WORLD_REL, REBUILD_TAIL,
                    "      meshes.set(box.id, mesh);\n"
                    "      if (currentReading === 'underneath') { mesh.rotation.y = Math.PI / 2; }\n"
                    "    });\n  }")],
    },
    {
        "case": "r4_neg_camera_switch",
        "why": ("R4-C / PM 读数 D：D-7 明文禁止「换相机」，此前**零判据** ⇒ 新增的 "
                "`two_reads_share_camera` 必须红（且这是本 case 的**唯一**期望失败点）"),
        "expect": "judged_red",
        "expect_fail": CAMERA_JUDGEMENT,
        "inject": [(WORLD_REL, REBUILD_HEAD,
                    REBUILD_HEAD + "\n    if (currentReading === 'underneath')"
                    " { camera.position.set(40, 40, 40); }")],
    },
    {
        "case": "r4_ctl_position_shift",
        "why": ("R4-C 对照 / PM 读数 E：`mesh.position.x += 5` 形态 —— 加宽**不得**让它失效，"
                "必须仍由 `two_reads_share_rendered_geometry` 判红"),
        "expect": "judged_red",
        "expect_fail": "two_reads_share_rendered_geometry",
        "inject": [(WORLD_REL, REBUILD_TAIL,
                    "      meshes.set(box.id, mesh);\n"
                    "      if (currentReading === 'underneath') { mesh.position.x += 5; }\n"
                    "    });\n  }")],
    },
]


def main() -> int:
    label = (sys.argv[1] if len(sys.argv) > 1 else "green").lower()
    results = []
    lines = []
    for spec in CASES:
        before = lib.sha_tree(lib.SRC)                      # 逐 case：交付面跑前指纹
        root = lib.fresh_copy(spec["case"])
        injections = []
        for rel, old, new in spec["inject"]:
            injections.append(lib.inject(root / "02_source" / rel, old, new))
        # 相位证据：加宽前副本里**没有**相机判据（RED 相位必须 False）
        assert_text = (root / "02_source" / ASSERT_REL).read_text(encoding="utf-8")
        camera_judgement_present = CAMERA_JUDGEMENT in assert_text
        cwd = root / "02_source" / "v0_skeleton" / "web"
        exit_code, stdout, stderr, secs = lib.run(["node", "scripts/scene_assert.mjs"], cwd)
        verdict = lib.classify_scene_assert(exit_code, stdout, stderr)
        after = lib.sha_tree(lib.SRC)                       # 逐 case：交付面跑后指纹
        delivery_face_unchanged = before == after
        log = lib.write_log(f"negctl-{spec['case']}.log",
                            f"# case {spec['case']}  (label={label})\n# copy {root}\n"
                            f"# injections: {injections}\n"
                            f"# camera_judgement_present_in_copy={camera_judgement_present}\n"
                            f"# cmd: node scripts/scene_assert.mjs   (cwd {cwd})\n"
                            f"# exit={exit_code} seconds={secs}\n"
                            f"# delivery_face_sha_tree before={before} after={after}\n"
                            f"# delivery_face_unchanged={delivery_face_unchanged}\n"
                            f"# stderr:\n{stderr}\n# stdout:\n{stdout}\n")
        ok = verdict["verdict"] == spec["expect"] and delivery_face_unchanged
        if spec.get("expect_fail"):
            ok = ok and spec["expect_fail"] in verdict["fail_names"]
        results.append({
            "case": spec["case"], "why": spec["why"], "copy": str(root),
            "injections": injections, "cmd": "node scripts/scene_assert.mjs", "cwd": str(cwd),
            "log": str(log), "seconds": secs, "expect": spec["expect"],
            "expect_fail": spec.get("expect_fail"), "ok": ok,
            "camera_judgement_present_in_copy": camera_judgement_present,
            "delivery_face_sha_tree_before": before, "delivery_face_sha_tree_after": after,
            "delivery_face_unchanged": delivery_face_unchanged,
            **verdict,
        })
        line = (f"[{spec['case']}] verdict={verdict['verdict']} exit={exit_code} "
                f"PASS={verdict['pass']} FAIL={verdict['fail']} fail_names={verdict['fail_names']} "
                f"camera_judgement={camera_judgement_present} "
                f"delivery_face_unchanged={delivery_face_unchanged} ok={ok}")
        lines.append(line)
        print(line)

    escaped = sorted(r["case"] for r in results
                     if r["expect"] == "judged_red" and r["verdict"] == "judged_green")
    summary = {
        "round": "R4", "label": label,
        "item": "F5 R4 judgement widening (mesh scale/quaternion + camera consistency)",
        "neg_root": str(lib.NEG_ROOT),
        "cases": results,
        "turned_red": sorted(r["case"] for r in results if r["turned_red"]),
        "crashes": sorted(r["case"] for r in results if r["verdict"] == "crash"),
        "escapes": escaped,
        "all_delivery_face_unchanged": all(r["delivery_face_unchanged"] for r in results),
        "all_ok": all(r["ok"] for r in results),
    }
    name = ("f5-r4-negctl-summary.json" if label == "green"
            else f"f5-r4-negctl-summary-{label}.json")
    path = lib.write_summary(name, summary)
    text_name = ("r4-green-after-widening.log" if label == "green" else "r4-red-before-widening.log")
    text = (f"# R4 / F5 negative controls — label={label}\n"
            f"# neg_root={lib.NEG_ROOT}\n"
            f"# summary={path}\n" + "\n".join(lines) + "\n"
            f"# turned_red={summary['turned_red']}\n"
            f"# crashes={summary['crashes']}\n"
            f"# escapes(expect red but judged green)={escaped}\n"
            f"# all_delivery_face_unchanged={summary['all_delivery_face_unchanged']}\n"
            f"# all_ok={summary['all_ok']}\n")
    lib.write_log(text_name, text)
    print(f"summary={path} turned_red={summary['turned_red']} crashes={summary['crashes']} "
          f"escapes={escaped} all_delivery_face_unchanged={summary['all_delivery_face_unchanged']} "
          f"all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
