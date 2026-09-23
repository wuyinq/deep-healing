#!/usr/bin/env python3
"""F6 / R5 负例矩阵 —— 关闭 `R4-C1`（相机投影面）/ `R4-C2`（几何拓扑面）/ `R4-M1`（世界根与父级变换）
在**判据层**的逃逸；并给「不得假红 / 不得恒真 / 不得自命中」三组控制读数。

背景（PM 独立复现，见 `.round5-constraint.txt` §0）：R4 的 `two_reads_share_rendered_geometry` 是
**逐字段白名单** ⇒ `camera.zoom` / 手改 `projectionMatrix` / `setViewOffset` / `geometry.setIndex` /
`mesh.parent.position.x += 50` 全部**逃逸**（`PASS=29 FAIL=0`）。R5 把比较面改成**闭式结构摘要**
（`structureReport()`：几何 index/groups/attributes + 每对象 matrixWorld/visible/layers/renderOrder +
根子树身份与父子关系）+ 相机结构面 + **渲染相机入参**。

分组（任务书 §8）：
  A（R4 已抓 8 类，必须仍红）  B（R4 未抓 3 类，必须真红）  C（拓扑）  D（世界根/父级变换）
  E（对象面）  F（渲染相机身份）  G（泛化：不同数值变体）  H（**不得假红**）
  I（**不得恒真 / 不得自命中**：反向注入必须变绿 ⇒ 判据真在比较）

纪律（照旧，硬）：
  - 负例**一律**在整树副本上注入（`NEGCTL_ROOT=/tmp/r5-artisan`；RED 相位 `/tmp/r5-artisan-red`），
    交付面 `02_source` 一个字节都不动；
  - `turned_red` **只给** `judged_red`；`crash` 单列；**每条**给逐 case 实测的 `delivery_face_unchanged`
    （交付面目录级 sha256 跑前/跑后，自算，不接受自报计数）。

用法：
  python3 -B spikes/s13-render/negctl/f6_r5_structure_negctl.py          # GREEN 相位（R5 判据面）
  python3 -B spikes/s13-render/negctl/f6_r5_structure_negctl.py red      # RED 相位（加宽**前**的整树副本）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PHASE = (sys.argv[1] if len(sys.argv) > 1 else "green").lower()
if PHASE not in ("green", "red"):
    raise SystemExit("usage: f6_r5_structure_negctl.py [green|red]")

# RED 相位的**加宽前**整树副本（R5 编码开始前冻结，见 03 的 R5-1）
RED_SRC = Path(os.environ.get("R5_RED_SRC", "/tmp/r5-pristine/02_source"))
os.environ["NEGCTL_ROOT"] = "/tmp/r5-artisan-red" if PHASE == "red" else "/tmp/r5-artisan"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import negctl_lib as lib  # noqa: E402

WORLD_REL = "v0_skeleton/web/src/scene/world.ts"
ASSERT_REL = "v0_skeleton/web/scripts/scene_assert.mjs"

# ---- 注入锚点（每个锚点在本轮实现里**恰好命中 1 次**，由 `negctl_lib.inject` 强制）
REBUILD_HEAD = "    const boxes = buildEntityBoxes(state, currentReading);"
REBUILD_TAIL_BODY = "      meshes.set(box.id, mesh);\n"
REBUILD_TAIL = "      meshes.set(box.id, mesh);\n    });\n  }"
SET_READING_HEAD = ("    setReading(reading) {\n      currentReading = reading;\n"
                    "      applyHealingLighting(scene, options.worldview[reading]);")
RENDER_FRAME = "  function renderFrame(): void {\n    renderer.render(scene, camera);\n  }"
STRUCT_GEO_DIGEST = "      geometry_digest: geometryParts.join('|'),"
STRUCT_OBJ_DIGEST = "      objects_digest: JSON.stringify(objects),"
ASSERT_CAM_UNDERNEATH = "const camUnderneath = scene.cameraReport();"
ASSERT_SET_READING_UNDERNEATH = "scene.setReading('underneath');"
ASSERT_SNAPSHOT_SURFACE = "scene.apply({ t: 'snapshot', tick: 0, state });\nscene.setReading('surface');"

# ---- 判据名（命中能力与「相位证据」都按名字核验）
STRUCTURE_JUDGEMENT = "two_reads_share_scene_structure"
OLD_JUDGEMENT = "two_reads_share_rendered_geometry"
CAMERA_JUDGEMENT = "two_reads_share_camera"
RENDER_CAMERA_JUDGEMENT = "two_reads_use_same_render_camera"


def mesh_underneath(statement: str) -> tuple[str, str, str]:
    """`rebuild()` 的 forEach 尾部：**只在 underneath 读法**生效的注入。"""
    return (WORLD_REL, REBUILD_TAIL_BODY,
            REBUILD_TAIL_BODY + f"      if (currentReading === 'underneath') {{ {statement} }}\n")


def head_underneath(statement: str) -> tuple[str, str, str]:
    """`rebuild()` 头部（`boxes` 之前）：**只在 underneath 读法**生效的注入。"""
    return (WORLD_REL, REBUILD_HEAD,
            REBUILD_HEAD + f"\n    if (currentReading === 'underneath') {{ {statement} }}")


def reading_underneath(statement: str) -> tuple[str, str, str]:
    """`setReading()` 入口：**只在切到 underneath 读法**时生效的注入。"""
    return (WORLD_REL, SET_READING_HEAD,
            "    setReading(reading) {\n      currentReading = reading;\n"
            f"      if (reading === 'underneath') {{ {statement} }}\n"
            "      applyHealingLighting(scene, options.worldview[reading]);")


# `mesh.parent.position.x += 50` 的等价形态：在 mesh 与其父 Group 之间插入一层并偏移
PARENT_GROUP_NEW = ("      meshes.set(box.id, mesh);\n    });\n"
                    "    if (currentReading === 'underneath') {\n"
                    "      const wrapper = new THREE.Group();\n"
                    "      wrapper.name = 'injected-parent';\n"
                    "      wrapper.position.y += 3;\n"
                    "      for (const child of [...meshes.values()]) wrapper.add(child);\n"
                    "      root.add(wrapper);\n"
                    "    }\n  }")

# 「第二相机只用于 underneath 渲染」：渲染入参被换掉 ⇒ `two_reads_use_same_render_camera` 必红
SECOND_CAMERA_NEW = ("  const injectedCamera = new THREE.PerspectiveCamera(45, 1, 0.1, 500);\n"
                     "  function renderFrame(): void {\n"
                     "    if (currentReading === 'underneath') { renderer.render(scene, injectedCamera); return; }\n"
                     "    renderer.render(scene, camera);\n  }")

CASES = [
    # ---------------- A：R4 已抓 8 类（必须**仍红**；对照也必须仍红）
    {"case": "r5_pristine", "group": "0", "red_phase": True, "expect": "judged_green",
     "why": "阳性对照：无注入 ⇒ 必须绿（证明副本 + 依赖软链可用，不是环境假红）", "inject": []},
    {"case": "r5_a_mesh_scale", "group": "A", "red_phase": True, "expect": "judged_red",
     "expect_fail": STRUCTURE_JUDGEMENT, "red_expect_fail": OLD_JUDGEMENT,
     "why": "R4 已抓：装配后 underneath 的 mesh 放大 3 倍（`mesh.scale.set(3,3,3)`）",
     "inject": [mesh_underneath("mesh.scale.set(3, 3, 3);")]},
    {"case": "r5_a_mesh_rotation", "group": "A", "red_phase": True, "expect": "judged_red",
     "expect_fail": STRUCTURE_JUDGEMENT, "red_expect_fail": OLD_JUDGEMENT,
     "why": "R4 已抓：`mesh.rotation.y = Math.PI/2`",
     "inject": [mesh_underneath("mesh.rotation.y = Math.PI / 2;")]},
    {"case": "r5_a_camera_position", "group": "A", "red_phase": True, "expect": "judged_red",
     "expect_fail": CAMERA_JUDGEMENT,
     "why": "R4 已抓：D-7 禁止的换相机（`camera.position.set(40,40,40)`）",
     "inject": [head_underneath("camera.position.set(40, 40, 40);")]},
    {"case": "r5_a_ctl_position_shift", "group": "A", "red_phase": True, "expect": "judged_red",
     "expect_fail": STRUCTURE_JUDGEMENT, "red_expect_fail": OLD_JUDGEMENT,
     "why": "**对照负例**：`mesh.position.x += 5`（既有形态）—— 加宽不得让它失效",
     "inject": [mesh_underneath("mesh.position.x += 5;")]},
    {"case": "r5_a_mesh_scale_tiny", "group": "A", "red_phase": True, "expect": "judged_red",
     "expect_fail": STRUCTURE_JUDGEMENT, "red_expect_fail": OLD_JUDGEMENT,
     "why": "R4 已抓：亚微米级缩放 `mesh.scale.set(1.0001,1,1)`（量化口径必须仍看得见）",
     "inject": [mesh_underneath("mesh.scale.set(1.0001, 1, 1);")]},
    {"case": "r5_a_mesh_quaternion", "group": "A", "red_phase": True, "expect": "judged_red",
     "expect_fail": STRUCTURE_JUDGEMENT, "red_expect_fail": OLD_JUDGEMENT,
     "why": "R4 已抓：`mesh.quaternion` 转 0.01 rad",
     "inject": [mesh_underneath("mesh.quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), 0.01);")]},
    {"case": "r5_a_single_box", "group": "A", "red_phase": True, "expect": "judged_red",
     "expect_fail": STRUCTURE_JUDGEMENT, "red_expect_fail": OLD_JUDGEMENT,
     "why": "R4 已抓：**只改第一个** box（`meshes.size === 1` ⇒ 该 forEach 迭代恰好是首个）",
     "inject": [mesh_underneath("if (meshes.size === 1) { mesh.scale.set(2, 2, 2); }")]},
    {"case": "r5_a_mesh_scale_nonuniform", "group": "A", "red_phase": True, "expect": "judged_red",
     "expect_fail": STRUCTURE_JUDGEMENT, "red_expect_fail": OLD_JUDGEMENT,
     "why": "R4 已抓：非均匀缩放 `mesh.scale.set(1,2,3)`",
     "inject": [mesh_underneath("mesh.scale.set(1, 2, 3);")]},

    # ---------------- B：R4 **未抓** 3 类（必须**真红**；RED 相位期望**绿** = 逃逸证据）
    {"case": "r5_b_camera_zoom", "group": "B", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": CAMERA_JUDGEMENT,
     "why": "R4 逃逸（`R4-C1`）：`camera.zoom = 2` + `updateProjectionMatrix()`",
     "inject": [reading_underneath("const perspective = camera as THREE.PerspectiveCamera; "
                                  "perspective.zoom = 2; perspective.updateProjectionMatrix();")]},
    {"case": "r5_b_camera_zoom_bare", "group": "B", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": CAMERA_JUDGEMENT,
     "why": "R4 逃逸：只改 `camera.zoom = 2`（**不**调 `updateProjectionMatrix`）⇒ `zoom` 字段必须有牙",
     "inject": [reading_underneath("(camera as THREE.PerspectiveCamera).zoom = 2;")]},
    {"case": "r5_b_projection_matrix", "group": "B", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": CAMERA_JUDGEMENT,
     "why": "R4 逃逸：**手改** `camera.projectionMatrix.elements[0] *= 1.5`（不碰 position/quaternion/fov）",
     "inject": [reading_underneath("camera.projectionMatrix.elements[0] *= 1.5;")]},
    {"case": "r5_b_view_offset", "group": "B", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": CAMERA_JUDGEMENT,
     "why": "R4 逃逸：`setViewOffset(100,100,10,10,50,50)`（`view_offset` 含 `enabled` 必须有牙）",
     "inject": [reading_underneath("(camera as THREE.PerspectiveCamera).setViewOffset(100, 100, 10, 10, 50, 50);")]},

    # ---------------- C：几何拓扑面
    {"case": "r5_c_geometry_index", "group": "C", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": STRUCTURE_JUDGEMENT,
     "why": "R4 逃逸（`R4-C2`）：`geometry.setIndex([0,1,2])` ⇒ 几何 `index` 摘要必须有牙",
     "inject": [mesh_underneath("(mesh.geometry as THREE.BufferGeometry).setIndex([0, 1, 2]);")]},

    # ---------------- D：世界根 / 父级变换 / matrixAutoUpdate
    {"case": "r5_d_root_offset", "group": "D", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": STRUCTURE_JUDGEMENT,
     "why": "R4 逃逸（`R4-M1`）：`root.position.x += 50` ⇒ 根变换必须进结构面（matrixWorld）",
     "inject": [head_underneath("root.position.x += 50;")]},
    {"case": "r5_d_parent_group_offset", "group": "D", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": STRUCTURE_JUDGEMENT,
     "why": "R4 逃逸：`mesh.parent.position.x += 50` 的等价形态 —— 在 mesh 与根之间插入**父级 Group** 并偏移",
     "inject": [(WORLD_REL, REBUILD_TAIL, PARENT_GROUP_NEW)]},
    {"case": "r5_d_matrix_auto_update", "group": "D", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": STRUCTURE_JUDGEMENT,
     "why": "R4 逃逸：`matrixAutoUpdate=false` + 手改 `matrix` 与 `matrixWorld`（自动更新被关掉）",
     "inject": [mesh_underneath("mesh.matrixAutoUpdate = false; mesh.matrix.makeTranslation(9, 9, 9); "
                               "mesh.matrixWorld.makeTranslation(9, 9, 9);")]},

    # ---------------- E：对象面
    {"case": "r5_e_visible", "group": "E", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": STRUCTURE_JUDGEMENT, "why": "`mesh.visible = false`",
     "inject": [mesh_underneath("mesh.visible = false;")]},
    {"case": "r5_e_layers_mask", "group": "E", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": STRUCTURE_JUDGEMENT, "why": "`mesh.layers.mask` 改动（渲染可见性分组）",
     "inject": [mesh_underneath("(mesh.layers as THREE.Layers).mask = 2;")]},
    {"case": "r5_e_render_order", "group": "E", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": STRUCTURE_JUDGEMENT, "why": "`mesh.renderOrder` 改动（绘制顺序）",
     "inject": [mesh_underneath("mesh.renderOrder = 7;")]},

    # ---------------- F：实际渲染相机身份（D-7 的字面形态）
    {"case": "r5_f_second_render_camera", "group": "F", "red_phase": False, "expect": "judged_red",
     "expect_fail": RENDER_CAMERA_JUDGEMENT,
     "why": "D-7 字面形态：**第二相机**只用于 underneath 渲染 ⇒ `renderer.render()` 入参必须被记录",
     "inject": [(WORLD_REL, RENDER_FRAME, SECOND_CAMERA_NEW)]},

    # ---------------- G：泛化（不同数值变体 ⇒ 证明不是模式匹配）
    {"case": "r5_g_scale_other_values", "group": "G", "red_phase": True, "expect": "judged_red",
     "expect_fail": STRUCTURE_JUDGEMENT, "red_expect_fail": OLD_JUDGEMENT,
     "why": "A 组变体：`mesh.scale.set(7, 0.5, 2)`（与 A 组数值全不同）",
     "inject": [mesh_underneath("mesh.scale.set(7, 0.5, 2);")]},
    {"case": "r5_g_root_offset_other_value", "group": "G", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": STRUCTURE_JUDGEMENT,
     "why": "D 组变体：`root.position.y -= 12`（与 D 组轴向/数值都不同）",
     "inject": [head_underneath("root.position.y -= 12;")]},
    {"case": "r5_g_camera_zoom_other_value", "group": "G", "red_phase": True, "red_expect": "judged_green",
     "expect": "judged_red", "expect_fail": CAMERA_JUDGEMENT,
     "why": "B 组变体：`zoom = 3.5` + `updateProjectionMatrix()`（与 B 组数值不同）",
     "inject": [reading_underneath("const perspective = camera as THREE.PerspectiveCamera; "
                                  "perspective.zoom = 3.5; perspective.updateProjectionMatrix();")]},

    # ---------------- H：**不得假红**（合法操作必须仍绿）
    {"case": "r5_h_legal_resize_idempotent", "group": "H", "red_phase": False, "expect": "judged_green",
     "why": "合法 `scene.resize()`（画布盒不变 ⇒ 幂等）夹在两读之间 ⇒ 判据**不得假红**",
     "inject": [(ASSERT_REL, ASSERT_SET_READING_UNDERNEATH,
                 "scene.resize();\n" + ASSERT_SET_READING_UNDERNEATH)]},
    {"case": "r5_h_legal_resize_outside_window", "group": "H", "red_phase": False, "expect": "judged_green",
     "why": "合法改视口 + `resize()` 发生在**两读窗口之外** ⇒ 两读仍须绿（口径见 06 R5 段）",
     "inject": [(ASSERT_REL, ASSERT_SNAPSHOT_SURFACE,
                 "canvasStub.clientWidth = 1024;\ncanvasStub.clientHeight = 768;\nscene.resize();\n"
                 + ASSERT_SNAPSHOT_SURFACE)]},
    {"case": "r5_h_legal_delta", "group": "H", "red_phase": False, "expect": "judged_green",
     "why": "合法 delta（真走增量路径）+ 重新下发快照，均发生在两读窗口之外 ⇒ 不得假红",
     "inject": [(ASSERT_REL, ASSERT_SNAPSHOT_SURFACE,
                 "scene.apply({ t: 'delta', tick: 1, ops: [{ entity: 'npc-001', component: 'transform', "
                 "value: { pos_mm: { x: 1234, y: 0, z: 5678 } } }] });\n"
                 "scene.apply({ t: 'snapshot', tick: 1, state });\n" + ASSERT_SNAPSHOT_SURFACE)]},

    # ---------------- I：**不得恒真 / 不得自命中**（反向注入 ⇒ 对应负例必须**变绿**）
    {"case": "r5_i_pinned_geometry_digest", "group": "I", "red_phase": False, "expect": "judged_green",
     "why": "把**几何结构摘要读回值钉成常量** + C 组负例 ⇒ 负例**变绿** = 判据真在比较（非恒真）",
     "inject": [(WORLD_REL, STRUCT_GEO_DIGEST, "      geometry_digest: 'PINNED-CONST',"),
                mesh_underneath("(mesh.geometry as THREE.BufferGeometry).setIndex([0, 1, 2]);")]},
    {"case": "r5_i_pinned_objects_digest", "group": "I", "red_phase": False, "expect": "judged_green",
     "why": "把**对象结构摘要读回值钉成常量** + D 组负例 ⇒ 负例**变绿** = 判据真在比较",
     "inject": [(WORLD_REL, STRUCT_OBJ_DIGEST, "      objects_digest: 'PINNED-CONST',"),
                head_underneath("root.position.x += 50;")]},
    {"case": "r5_i_camera_same_read_twice", "group": "I", "red_phase": False, "expect": "judged_green",
     "why": "把**相机判据改成比较同一读数两次** + B 组负例 ⇒ 负例**变绿** = 相机判据真在比较两态",
     "inject": [(ASSERT_REL, ASSERT_CAM_UNDERNEATH, "const camUnderneath = camSurface;"),
                reading_underneath("const perspective = camera as THREE.PerspectiveCamera; "
                                  "perspective.zoom = 2; perspective.updateProjectionMatrix();")]},
]


def main() -> int:
    source = RED_SRC if PHASE == "red" else lib.SRC
    cases = [spec for spec in CASES if PHASE == "green" or spec.get("red_phase")]
    results = []
    lines = []
    for spec in cases:
        before = lib.sha_tree(lib.SRC)                      # 逐 case：交付面跑前指纹（**交付面**，不是副本）
        root = lib.fresh_copy(spec["case"], source)
        injections = []
        for rel, old, new in spec["inject"]:
            injections.append(lib.inject(root / "02_source" / rel, old, new))
        assert_text = (root / "02_source" / ASSERT_REL).read_text(encoding="utf-8")
        structure_present = STRUCTURE_JUDGEMENT in assert_text
        old_present = OLD_JUDGEMENT in assert_text
        render_camera_present = RENDER_CAMERA_JUDGEMENT in assert_text
        cwd = root / "02_source" / "v0_skeleton" / "web"
        exit_code, stdout, stderr, secs = lib.run(["node", "scripts/scene_assert.mjs"], cwd)
        verdict = lib.classify_scene_assert(exit_code, stdout, stderr)
        after = lib.sha_tree(lib.SRC)                       # 逐 case：交付面跑后指纹
        delivery_face_unchanged = before == after
        # 相位语义：RED 相位比较「加宽**前**」的应有读数（逃逸 ⇒ 期望**绿**），GREEN 相位比较本轮判据面。
        if PHASE == "red":
            expected = spec.get("red_expect", spec["expect"])
            expect_fail = (None if expected == "judged_green"
                           else spec.get("red_expect_fail", spec.get("expect_fail")))
        else:
            expected = spec["expect"]
            expect_fail = spec.get("expect_fail")
        log = lib.write_log(f"negctl-{spec['case']}.log",
                            f"# case {spec['case']} (group {spec['group']}, phase {PHASE})\n"
                            f"# why {spec['why']}\n# source {source}\n# copy {root}\n"
                            f"# injections: {injections}\n"
                            f"# judgement_present: structure={structure_present} "
                            f"old_rendered={old_present} render_camera={render_camera_present}\n"
                            f"# cmd: node scripts/scene_assert.mjs   (cwd {cwd})\n"
                            f"# exit={exit_code} seconds={secs}\n"
                            f"# delivery_face_sha_tree before={before} after={after}\n"
                            f"# delivery_face_unchanged={delivery_face_unchanged}\n"
                            f"# expected: verdict={expected} fail={expect_fail}\n"
                            f"# stderr:\n{stderr}\n# stdout:\n{stdout}\n")
        ok = verdict["verdict"] == expected and delivery_face_unchanged
        if expect_fail:
            ok = ok and expect_fail in verdict["fail_names"]
        results.append({
            "case": spec["case"], "group": spec["group"], "why": spec["why"], "copy": str(root),
            "injections": injections, "cmd": "node scripts/scene_assert.mjs", "cwd": str(cwd),
            "log": str(log), "seconds": secs, "expect": expected,
            "expect_fail": expect_fail, "ok": ok,
            "judgement_present_in_copy": {"structure": structure_present, "old_rendered": old_present,
                                          "render_camera": render_camera_present},
            "delivery_face_sha_tree_before": before, "delivery_face_sha_tree_after": after,
            "delivery_face_unchanged": delivery_face_unchanged,
            **verdict,
        })
        line = (f"[{spec['group']}/{spec['case']}] verdict={verdict['verdict']} exit={exit_code} "
                f"PASS={verdict['pass']} FAIL={verdict['fail']} fail_names={verdict['fail_names']} "
                f"expect={expected} expect_fail={expect_fail} "
                f"delivery_face_unchanged={delivery_face_unchanged} ok={ok}")
        lines.append(line)
        print(line)

    escaped = sorted(r["case"] for r in results
                     if r["expect"] == "judged_red" and r["verdict"] == "judged_green")
    red_group_missed = sorted(r["case"] for r in results if not r["ok"])
    # RED 相位的关键读数：**加宽前**真的逃逸的注入（期望绿且判绿）⇒ 「判据曾有洞」的负例侧证据
    pre_widening_escapes = sorted(r["case"] for r in results
                                  if r["expect"] == "judged_green" and r["verdict"] == "judged_green")
    summary = {
        "round": "R5", "phase": PHASE, "source": str(source), "neg_root": str(lib.NEG_ROOT),
        "item": "F6 R5 closed-form structural face (geometry/objects/camera/render-camera) negative matrix",
        "cases": results,
        "turned_red": sorted(r["case"] for r in results if r["turned_red"]),
        "crashes": sorted(r["case"] for r in results if r["verdict"] == "crash"),
        "escapes": escaped,
        "pre_widening_escapes": pre_widening_escapes if PHASE == "red" else [],
        "expected_red_not_ok": red_group_missed,
        "all_delivery_face_unchanged": all(r["delivery_face_unchanged"] for r in results),
        "all_ok": all(r["ok"] for r in results),
    }
    name = "f6-r5-negctl-summary.json" if PHASE == "green" else "f6-r5-negctl-red-summary.json"
    path = lib.write_summary(name, summary)
    # 文本日志名**故意**落在 `negctl-*.log` 模式内 ⇒ 属 R5 声明的「可重生成运行产物」，
    # 不入冻结面（复跑本驱动不得让 `shasum -c` 变红）；判据读数由 03/06 的 R5 段承担。
    text_name = "negctl-r5-green-closed-form.log" if PHASE == "green" else "negctl-r5-red-closed-form.log"
    text = (f"# R5 / F6 negative controls — phase={PHASE}\n# source={source}\n# neg_root={lib.NEG_ROOT}\n"
            f"# summary={path}\n" + "\n".join(lines) + "\n"
            f"# turned_red={summary['turned_red']}\n# crashes={summary['crashes']}\n"
            f"# escapes(expect red but judged green)={escaped}\n"
            f"# pre_widening_escapes={summary['pre_widening_escapes']}\n"
            f"# expected_red_not_ok={red_group_missed}\n"
            f"# all_delivery_face_unchanged={summary['all_delivery_face_unchanged']}\n"
            f"# all_ok={summary['all_ok']}\n")
    lib.write_log(text_name, text)
    print(f"summary={path} turned_red={summary['turned_red']} crashes={summary['crashes']} "
          f"escapes={escaped} pre_widening_escapes={summary['pre_widening_escapes']} "
          f"all_delivery_face_unchanged={summary['all_delivery_face_unchanged']} "
          f"all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
