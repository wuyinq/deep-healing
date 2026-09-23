#!/usr/bin/env python3
"""F4 判据与负例（R2 / CRITICAL-4 · AC-M3-3 + AC-M3-4 双判据 + AC-M3-8③）：
**真 Chromium** 跑两档视口 × 两态读法，判定在原始读数上做。

判据（全部来自 `spikes/s13-render/browser-accept.mjs` 的真读数）：
  ① 两档视口 × 两态读法 ≥4 张截图；
  ② console 零 error / 零 pageerror / 零 4xx-5xx；
  ③ 观察模式 UI 树无写控件（真浏览器枚举 + 文档级控件表 allow-list）；
  ④ 写接口被拒：客户端本地拒 + 服务端 WS 上行拒（都必须是 E_MODE_READONLY）；
  ⑤ 两态几何逐项相同（真浏览器读数）+ 12 实体；读法切换真生效；
  ⑥ reload 后回读：tick 前进、模式复位 observe、连接恢复；
  ⑦ 首帧补齐：连上后很快看得见世界（≤3s，且 12 实体）；
  ⑧ 下行 tick 流：`spikes/s12-session/logs/emitted-messages.jsonl` 含 snapshot + delta + tick_meta，
     且每个 delta 覆盖 5 个 NPC、tick 连续覆盖 ≥40 个 tick（真·持续 tick）。
  ⑨ **负例**：给观察面板加一个写控件（重建注入版 bundle）⇒ ③ 必须红。

**R3 / G1 新增（Sentinel r2 CRITICAL：3D 世界不可见）**：
  ⑩ canvas 的 `getBoundingClientRect()` **随视口变化**（= 视口尺寸，两档各一读数）；
  ⑪ **绘制缓冲跟随画布**（`gl.drawingBufferWidth/Height` ≈ canvas 盒 × DPR）；
  ⑫ **像素级判据**：**HUD 区域之外**的非背景像素占比 ≥ `OUTSIDE_HUD_MIN_RATIO`（阈值 + 实测值见 06）；
  ⑬ 负例：把 `setSize` 退回固定 300×150 ⇒ ⑪ 必须红；连同 `#scene` 的显式尺寸一起退回 R3 之前形态
     （只退 `setSize` 时 CSS 会把 300×150 拉伸铺满 ⇒ 单退一处不足以复现旧缺陷）⇒ ⑩⑫ 必须红。

**R3 / G2 新增**：真浏览器里的 `assemblyReport()`（场景图 mesh 层）两态逐项相同
（`entity_ids` / `shape_digests` / `geometry_digest`；跨 tick 的世界坐标合法变化故不参与比较）。

用法：python3 -B spikes/s13-render/negctl/f4_browser_negctl.py
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

WS = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3")
sys.path.insert(0, str(WS / "spikes" / "s13-render" / "negctl"))
import negctl_lib as lib  # noqa: E402

PANEL_REL = "v0_skeleton/web/src/ui/observe/panel.ts"
WORLD_REL = "v0_skeleton/web/src/scene/world.ts"
HTML_REL = "v0_skeleton/web/index.html"
NPC_IDS = ["npc-001", "npc-002", "npc-003", "npc-004", "npc-005"]
WRITE_CAPABLE_TAGS = {"input", "textarea", "select", "form"}
VIEW_ONLY_ALLOWED = {"toggle-reading", "toggle-mode"}
EMITTED = WS / "spikes" / "s12-session" / "logs" / "emitted-messages.jsonl"
LOG_DIR = WS / "spikes" / "s13-render" / "logs"

# ---- R3 / G1：像素判据阈值（**自定 + 实测值写进 06**；见 06 的 R3 段）
OUTSIDE_HUD_MIN_RATIO = 0.05

# 只退 setSize（CSS 仍是 R3 后的显式尺寸）⇒ 绘制缓冲判据必须红
PIN_BUFFER_OLD = ("    renderer.setPixelRatio(pixelRatio);\n"
                  "    // 第三个参数 = false：**不**让 three 去改内联样式（尺寸由 CSS 决定，绘制缓冲跟着 CSS 走）\n"
                  "    renderer.setSize(width, height, false);")
PIN_BUFFER_NEW = ("    renderer.setPixelRatio(pixelRatio);\n"
                  "    renderer.setSize(300, 150, false);")
# 连同 `#scene` 的显式尺寸一起退回 R3 之前形态（复现旧缺陷的完整条件）
CSS_OLD = "#scene { position: absolute; inset: 0; width: 100%; height: 100%; display: block; z-index: 0; }"
CSS_NEW = "#scene { position: absolute; inset: 0; }"


def judge_browser(data: dict, shots_stats: dict) -> dict:
    checks = {
        "shots_at_least_4": len([p for p in data["shots"] if "after-reload" not in p]) >= 4,
        "console_zero_errors": data["console"]["errors"] == 0,
        "zero_page_errors": len(data["page_errors"]) == 0,
        "zero_bad_responses": len(data.get("bad_responses", [])) == 0,
    }
    rects = {}
    for entry in data["viewports"]:
        tag = entry["viewport"]
        rects[tag] = entry["canvas_rect"]
        controls = entry["controls_observe_mode"]
        write_capable = [c for c in controls if c["tag"] in WRITE_CAPABLE_TAGS
                         or (c["tag"] == "button" and c.get("type") == "submit")]
        unknown_buttons = [c["id"] for c in controls if c["tag"] == "button" and c["id"] not in VIEW_ONLY_ALLOWED]
        checks[f"{tag}_observe_no_write_controls"] = entry["observe_panel_write_controls"] == []
        checks[f"{tag}_observe_ui_tree_no_write_controls"] = len(write_capable) == 0 and len(unknown_buttons) == 0
        checks[f"{tag}_no_duplicate_dom_ids"] = entry["duplicate_id_count"] == 0
        checks[f"{tag}_client_local_rejection"] = entry["client_local_rejection"]["reason"] == "E_MODE_READONLY"
        checks[f"{tag}_server_ws_rejection"] = (entry["server_ws_rejection"]["ack"]["status"] == "rejected"
                                               and entry["server_ws_rejection"]["ack"]["reason"] == "E_MODE_READONLY")
        surface, underneath = entry["geometry_surface"], entry["geometry_underneath"]
        checks[f"{tag}_two_reads_same_geometry"] = (
            surface["entity_ids"] == underneath["entity_ids"]
            and surface["vertex_counts"] == underneath["vertex_counts"]
            and surface["shape_digests"] == underneath["shape_digests"]
            and surface["geometry_digest"] == underneath["geometry_digest"]
            and surface["reading"] == "surface" and underneath["reading"] == "underneath")
        checks[f"{tag}_geometry_covers_12_entities"] = len(entry["entity_ids"]) == 12
        checks[f"{tag}_reading_switch_effective"] = (entry["reading_after_click"] == "underneath"
                                                     and entry["reading_badge_after_click"] == "underneath")
        checks[f"{tag}_first_frame_fast"] = (entry["first_frame_ms"] is not None
                                             and entry["first_frame_ms"] <= 3000
                                             and entry["first_frame_entities"] == 12)
        checks[f"{tag}_reload_tick_advances"] = (
            int("".join(ch for ch in str(entry["reload"]["tick_after"]) if ch.isdigit()) or 0)
            > int("".join(ch for ch in str(entry["reload"]["tick_before"]) if ch.isdigit()) or 0))
        checks[f"{tag}_reload_resets_to_observe"] = entry["reload"]["mode_after"] == "observe"
        checks[f"{tag}_reload_reconnected"] = entry["reload"]["applied_messages_after"] > 0
        checks[f"{tag}_participate_mounts_write_controls"] = len(entry["write_controls_participate"]) > 0
        checks[f"{tag}_real_intervention_queued"] = entry["intent_status_text"] == "queued"
        checks[f"{tag}_deep_reading_revealed"] = (entry["underneath_tick_at_shot"] >= entry["reveal_at_tick"]
                                                  and "underneath" in (entry["anomaly_read_underneath"] or ""))

        # ---- R3 / G1⑩⑪：canvas 盒 + 绘制缓冲
        rect = entry["canvas_rect"]
        dpr = min(float(entry["window_metrics"].get("devicePixelRatio") or 1), 2)
        checks[f"{tag}_canvas_rect_fills_viewport"] = (abs(rect["width"] - entry["width"]) <= 1
                                                       and abs(rect["height"] - entry["height"]) <= 1)
        checks[f"{tag}_canvas_rect_at_viewport_origin"] = abs(rect["x"]) <= 1 and abs(rect["y"]) <= 1
        buffer = entry.get("gl_drawing_buffer") or entry.get("canvas_attributes") or {"width": 0, "height": 0}
        checks[f"{tag}_drawing_buffer_follows_canvas"] = (
            buffer["width"] >= rect["width"] - 1 and buffer["height"] >= rect["height"] - 1
            and buffer["width"] <= round(entry["width"] * dpr) + 1
            and buffer["height"] <= round(entry["height"] * dpr) + 1)

        # ---- R3 / G2：场景图 mesh 层两态一致（跨 tick 的世界坐标不参与比较）
        asm_surface, asm_underneath = entry["assembly_surface"], entry["assembly_underneath"]
        checks[f"{tag}_assembly_two_reads_same_geometry"] = (
            asm_surface["entity_ids"] == asm_underneath["entity_ids"]
            and asm_surface["shape_digests"] == asm_underneath["shape_digests"]
            and asm_surface["geometry_digest"] == asm_underneath["geometry_digest"]
            and asm_surface["reading"] == "surface" and asm_underneath["reading"] == "underneath")
        checks[f"{tag}_assembly_shape_fingerprint_present"] = (
            len(asm_surface["shape_digests"]) == 12
            and all(len(value) >= 60 for value in asm_surface["shape_digests"].values()))

        # ---- R3 / G1⑫：像素级判据（HUD 之外必须真的看得见世界）
        hud = entry["hud_rect"]
        for shot in entry["shots"]:
            name = Path(shot).name
            stats = shots_stats.get(name)
            checks[f"{tag}_{name[:-4]}_world_visible_outside_hud"] = bool(
                stats is not None
                and stats["outside_hud_nonbg_ratio"] >= OUTSIDE_HUD_MIN_RATIO
                and stats["outside_hud_nonbg_pixels"] > 0)
        checks[f"{tag}_hud_does_not_cover_viewport"] = (hud["width"] * hud["height"]) < 0.5 * (entry["width"] * entry["height"])

    checks["canvas_rect_differs_across_viewports"] = (
        len(rects) >= 2
        and len({(round(r["width"]), round(r["height"])) for r in rects.values()}) == len(rects))
    return checks


def judge_stream(path: Path) -> dict:
    if not path.exists():
        return {"stream_exists": False}
    messages = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    kinds = {}
    for message in messages:
        kinds[message["t"]] = kinds.get(message["t"], 0) + 1
    deltas = [message for message in messages if message["t"] == "delta"]
    delta_entities = sorted({op["entity"] for message in deltas for op in message.get("ops", [])})
    ticks = sorted({message["tick"] for message in messages})
    contiguous = bool(ticks) and ticks == list(range(ticks[0], ticks[-1] + 1))
    return {
        "stream_exists": True, "stream_total": len(messages), "stream_kinds": kinds,
        "stream_tick_span": [ticks[0], ticks[-1]] if ticks else None,
        "stream_tick_contiguous": contiguous,
        "stream_delta_entities": delta_entities,
        "snapshot_present": kinds.get("snapshot", 0) >= 1,
        "tick_meta_present": kinds.get("tick_meta", 0) >= 1,
        "delta_present": kinds.get("delta", 0) >= 1,
        "deltas_cover_5_npcs": delta_entities == NPC_IDS,
        "tick_span_at_least_40": (len(ticks) >= 40) if ticks else False,
    }


def stream_checks(stream: dict) -> dict:
    return {
        "stream_has_snapshot_delta_tickmeta": bool(stream.get("snapshot_present")
                                                  and stream.get("delta_present")
                                                  and stream.get("tick_meta_present")),
        "stream_deltas_cover_5_npcs": bool(stream.get("deltas_cover_5_npcs")),
        "stream_ticks_contiguous_over_40": bool(stream.get("stream_tick_contiguous")
                                                and stream.get("tick_span_at_least_40")),
    }


def start_serve(web: Path, port: int, tag: str, run_seconds: int):
    log_path = lib.NEG_ROOT / f"f4-serve-{tag}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w")
    process = subprocess.Popen(
        ["node", str(WS / "spikes" / "s13-render" / "serve.mjs"),
         "--web", str(web), "--port", str(port), "--run-seconds", str(run_seconds),
         "--emit", str(EMITTED),
         "--runtime", str(WS / "spikes" / "s13-render" / f"runtime-{tag}"),
         "--summary", str(LOG_DIR / f"serve-summary-{tag}.json")],
        cwd=str(WS), stdout=handle, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    deadline = time.time() + 90
    while time.time() < deadline:
        if "SERVE_READY" in log_path.read_text(encoding="utf-8", errors="ignore"):
            return process, handle, log_path
        if process.poll() is not None:
            raise SystemExit(f"serve exited early ({process.returncode}); see {log_path}")
        time.sleep(0.5)
    raise SystemExit(f"serve never became ready; see {log_path}")


CASES = [
    {"case": "f4_pristine", "tag": "pristine", "port": 8891, "expect_all": True, "build": None},
    {"case": "f4_neg_observe_write_control", "tag": "neg-write-control", "port": 8892, "expect_all": False,
     "expect_failed_patterns": ["observe_no_write_controls"],
     "build": [(PANEL_REL,
                "    // 只读控件：面板本体不产生任何输入控件\n",
                "    // 负例注入（F4）：给**观察面板**加一个写控件\n"
                "    const injected = document.createElement('input');\n"
                "    injected.id = 'injected-write-control';\n"
                "    injected.placeholder = 'negative control';\n"
                "    this.root.append(injected);\n")]},
    # R3 / G1⑬-A：只把 `setSize` 退回固定 300×150（CSS 仍显式）⇒ 绘制缓冲判据必须红
    {"case": "f4_neg_pinned_buffer_only", "tag": "neg-pinned-buffer", "port": 8893, "expect_all": False,
     "expect_failed_patterns": ["drawing_buffer_follows_canvas"],
     "build": [(WORLD_REL, PIN_BUFFER_OLD, PIN_BUFFER_NEW)]},
    # R3 / G1⑬-B：连同 `#scene` 的显式尺寸一起退回 R3 之前形态 ⇒ canvas 盒 + 像素判据必须红
    {"case": "f4_neg_fixed_canvas", "tag": "neg-fixed-canvas", "port": 8894, "expect_all": False,
     "expect_failed_patterns": ["canvas_rect_fills_viewport", "world_visible_outside_hud"],
     "build": [(WORLD_REL, PIN_BUFFER_OLD, PIN_BUFFER_NEW), (HTML_REL, CSS_OLD, CSS_NEW)]},
]


def main() -> int:
    before = lib.sha_tree(lib.SRC)
    results = []
    for spec in CASES:
        web = WS / ".build" / "web"
        injections = []
        if spec["build"]:
            root = lib.fresh_copy(spec["case"])
            for rel, old, new in spec["build"]:
                injections.append(lib.inject(root / "02_source" / rel, old, new))
            build_exit, build_out, build_err, build_secs = lib.run(
                ["node", str(root / "node_modules" / "vite" / "bin" / "vite.js"), "build"],
                root / "02_source" / "v0_skeleton" / "web", timeout=600)
            web = root / ".build" / "web"
            if build_exit != 0 or not (web / "index.html").exists():
                raise SystemExit(f"injected build failed exit={build_exit}\n{build_out}\n{build_err}")
        else:
            build_exit, build_secs = 0, 0.0

        process, handle, log_path = start_serve(web, spec["port"], spec["tag"], 60)
        try:
            driver_exit, stdout, stderr, secs = lib.run(
                ["node", str(WS / "spikes" / "s13-render" / "browser-accept.mjs"),
                 "--url", f"http://127.0.0.1:{spec['port']}",
                 "--out", str(LOG_DIR), "--tag", spec["tag"]],
                WS, timeout=900)
            try:
                process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.kill()
            handle.close()

        data = None
        try:
            data = json.loads((LOG_DIR / f"browser-accept-{spec['tag']}.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass

        # ---- R3 / G1⑫：对本次采集的**每一张**截图做像素统计（HUD 之外必须真的看得见世界）
        shots_stats = {}
        if data:
            for entry in data["viewports"]:
                for shot in entry["shots"]:
                    path = Path(shot)
                    if path.exists():
                        shots_stats[path.name] = lib.pixel_stats(path, entry.get("hud_rect"))

        judged = judge_browser(data, shots_stats) if data else {}
        stream = judge_stream(EMITTED)
        judged.update(stream_checks(stream))
        all_ok = bool(judged) and all(judged.values())
        failed = sorted(key for key, value in judged.items() if not value)
        patterns = spec.get("expect_failed_patterns", [])
        patterns_matched = {pattern: any(pattern in name for name in failed) for pattern in patterns}
        ok = (all_ok == spec["expect_all"]) and all(patterns_matched.values())
        serve_summary = json.loads((LOG_DIR / f"serve-summary-{spec['tag']}.json").read_text(encoding="utf-8"))
        log = lib.write_log(f"negctl-{spec['case']}.log",
                            f"# case {spec['case']}\n# web {web}\n# injections {injections}\n"
                            f"# injected build exit={build_exit} seconds={build_secs}\n"
                            f"# serve log {log_path}\n# driver exit={driver_exit} seconds={secs}\n"
                            f"# driver stderr:\n{stderr}\n"
                            f"# expect_all_checks={spec['expect_all']} expect_failed_patterns={patterns}\n"
                            f"# patterns_matched={patterns_matched}\n"
                            f"# pixel threshold OUTSIDE_HUD_MIN_RATIO={OUTSIDE_HUD_MIN_RATIO}\n"
                            f"# pixel stats:\n{json.dumps(shots_stats, ensure_ascii=False, indent=2)}\n"
                            f"# checks:\n{json.dumps(judged, ensure_ascii=False, indent=2)}\n"
                            f"# serve summary:\n{json.dumps(serve_summary, ensure_ascii=False, indent=2)}\n"
                            f"# stream:\n{json.dumps(stream, ensure_ascii=False, indent=2)}\n")
        results.append({"case": spec["case"], "tag": spec["tag"], "web": str(web),
                        "injections": injections, "build_exit": build_exit, "log": str(log),
                        "driver_exit": driver_exit, "expect_all_checks": spec["expect_all"],
                        "expect_failed_patterns": patterns, "patterns_matched": patterns_matched,
                        "all_checks_pass": all_ok, "ok": ok,
                        "verdict": "judged_green" if all_ok else "judged_red",
                        "failed_checks": failed,
                        "pixel_stats": shots_stats, "checks": judged, "stream": stream,
                        "canvas_readings": [
                            {"viewport": entry["viewport"], "canvas_rect": entry["canvas_rect"],
                             "canvas_attributes": entry["canvas_attributes"],
                             "gl_drawing_buffer": entry["gl_drawing_buffer"],
                             "hud_rect": entry["hud_rect"],
                             "window": entry["window_metrics"]}
                            for entry in (data or {}).get("viewports", [])],
                        "serve_summary": {k: serve_summary.get(k) for k in
                                          ("emitted_total", "emitted_kinds", "delta_entities",
                                           "max_tick_in_stream", "ticks_reached", "sessions")}})
        print(f"[{spec['case']}] all_checks_pass={all_ok} driver_exit={driver_exit} "
              f"failed={failed[:6]} patterns={patterns_matched} ok={ok}")
    after = lib.sha_tree(lib.SRC)
    summary = {"round": "R3", "item": "F4 real browser acceptance (G1 visibility + G2 assembly path)",
               "neg_root": str(lib.NEG_ROOT), "outside_hud_min_ratio": OUTSIDE_HUD_MIN_RATIO,
               "cases": results, "delivery_face_unchanged": before == after,
               "delivery_face_sha_tree": before,
               "all_ok": all(r["ok"] for r in results) and before == after}
    path = lib.write_summary("f4-browser-summary.json", summary)
    print(f"summary={path} delivery_face_unchanged={before == after} all_ok={summary['all_ok']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
