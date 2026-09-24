#!/usr/bin/env python3
"""F-1 可见性读数（N2-r2 / spike 专用，**非交付面**）。

对某张截图，在**3D 视口区**（= 画布减去 HUD 面板）内统计「期望材质色」的像素数与 bbox ——
期望色来自**内容包的包内 hex × 读法亮度系数**（与 `scene_assert.mjs` 的
`character_material_hex_recomputable` 同一复算口径），逐部件给出，并给出「角色区域」的总 bbox。

用法：
    python3 spikes/n2-appearance/n2-visibility-readout.py --out spikes/n2-appearance \
        --shot n2-obs-indoor-daily --parts '{"head":"#bdb2aa","hair":"#161413",...}'
    # 不给 --parts 时，从 readback/n2-obs-shots.json 里读实机读回的 material_hex
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def bbox_of(mask: np.ndarray) -> list[int] | None:
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if rows.size == 0 or cols.size == 0:
        return None
    return [int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])]


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="spikes/n2-appearance")
    parser.add_argument("--shot", required=True)
    parser.add_argument("--state", default="daily", help="readback 里要读的读数键（daily/masked）")
    parser.add_argument("--tolerance", type=int, default=12, help="逐通道容差（光照/抗锯齿）")
    parser.add_argument("--dominant", type=int, default=12, help="主导色条数")
    args = parser.parse_args()

    root = Path(args.out)
    rects = json.loads((root / "readback" / "n2-ui-rects.json").read_text(encoding="utf-8"))
    shots = json.loads((root / "readback" / "n2-obs-shots.json").read_text(encoding="utf-8"))
    key = {"daily": "indoor_daily", "masked": "indoor_masked"}[args.state]
    reading = shots["readings"][key]
    expected = {part["part"]: part["material_hex"]
                for part in reading["character"] if part["entity_id"] == shots["npc"]}

    image = np.asarray(Image.open(root / "shots" / f"{args.shot}.png").convert("RGB")).astype(np.int16)
    height, width = image.shape[0], image.shape[1]
    hud = rects["hud"]
    viewport = np.ones((height, width), dtype=bool)
    viewport[max(0, hud["y"] - 2):min(height, hud["y"] + hud["height"] + 2),
             max(0, hud["x"] - 2):min(width, hud["x"] + hud["width"] + 2)] = False

    per_part = {}
    union = np.zeros((height, width), dtype=bool)
    for part, hex_value in sorted(expected.items()):
        rgb = np.array(hex_to_rgb(hex_value), dtype=np.int16)
        distance = np.abs(image - rgb).max(axis=2)
        close = (distance <= args.tolerance) & viewport
        per_part[part] = {
            "material_hex": hex_value,
            "pixels_within_tolerance": int(close.sum()),
            "bbox_within_tolerance": bbox_of(close),
            "min_channel_distance_in_viewport": int(distance[viewport].min()),
        }
        union |= close

    # 主导色（渲染是**平面着色**：每个面一个常量色 ⇒ 主导色即「画面上真正看到的东西」）
    region = image[viewport]
    flat = region.reshape(-1, 3)
    packed = (flat[:, 0].astype(np.int32) << 16) | (flat[:, 1].astype(np.int32) << 8) | flat[:, 2].astype(np.int32)
    values, counts = np.unique(packed, return_counts=True)
    order = np.argsort(-counts)[: args.dominant]
    dominant = []
    for index in order:
        code = int(values[index])
        rgb = ((code >> 16) & 0xFF, (code >> 8) & 0xFF, code & 0xFF)
        match = (packed == code)
        mask = np.zeros((height, width), dtype=bool)
        mask[viewport] = match
        dominant.append({"hex": "#{:02x}{:02x}{:02x}".format(*rgb), "pixels": int(counts[index]),
                         "bbox": bbox_of(mask),
                         "share_of_viewport": round(float(counts[index]) / float(viewport.sum()), 6)})

    document = {
        "shot": f"{args.shot}.png",
        "state": args.state,
        "tolerance": args.tolerance,
        "viewport_region": {"x0": 0, "y0": 0, "x1": width, "y1": height,
                            "excluded_hud": [hud["x"], hud["y"], hud["x"] + hud["width"], hud["y"] + hud["height"]]},
        "expected_material_hex_from_live_readback": expected,
        "per_part": per_part,
        "dominant_colors_in_viewport": dominant,
        "character_region_pixels": int(union.sum()),
        "character_region_bbox": bbox_of(union),
        "character_region_share_of_viewport": round(
            float(union.sum()) / float(viewport.sum()), 6),
    }
    (root / "readback" / f"n2-visibility-{args.shot}.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
