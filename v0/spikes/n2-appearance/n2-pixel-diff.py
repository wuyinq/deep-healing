#!/usr/bin/env python3
"""F-1 像素可区分性读数（N2-r2 / spike 专用，**非交付面**）。

对 `shots/*.png` 做逐像素 diff，给出：差异像素数、差异 bbox、以及**排除 HUD 面板后**
（= 3D 视口区）的差异像素数与 bbox —— 「bbox 落在角色区域而非只在 HUD 面板内」由此可判。

用法：
    python3 spikes/n2-appearance/n2-pixel-diff.py --out spikes/n2-appearance
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

PAIRS = [
    ("n2-obs-indoor-daily", "n2-obs-indoor-masked",
     "室内取证机位：日常态 vs 面具态（**达标判据**：diff > 0 且差异落在角色区域）"),
    ("n2-obs-indoor-closeup-daily", "n2-obs-indoor-closeup-masked",
     "室内近景：日常态 vs 面具态（瞳/唇/面具可判读）"),
    ("n2-obs-indoor-side-daily", "n2-obs-indoor-side-masked",
     "室内 3/4 侧向：日常态 vs 面具态（**达标判据**：diff > 0 且差异落在角色区域）"),
    ("n2-obs-indoor-side-daily", "n2-obs-indoor-side-daily-2",
     "确定性自证：3/4 侧向机位 / 同一状态**重拍**（预期 diff == 0）"),
    ("n2-default-wide-daily", "n2-default-wide-masked",
     "**默认交付取景**：日常态 vs 面具态（预期差异**只**落在 HUD 面板 ⇒ 玩家看不到人）"),
    ("n2-obs-indoor-daily", "n2-obs-indoor-daily-2",
     "确定性自证：同一机位 / 同一状态**重拍**（预期 diff == 0）"),
    ("n2-obs-indoor-daily", "n2-obs-indoor-control-generic",
     "对照臂：徐琴（pack）vs `setAppearance(null)` 通用人形（同一室内机位）"),
    ("n2-default-wide-daily", "n2-obs-indoor-daily",
     "默认取景 vs 室内机位（同一状态）—— 证明取景真的不同"),
]


def bbox_of(mask: np.ndarray) -> list[int] | None:
    """`[x0, y0, x1, y1]`（含端点）；全 False ⇒ None。"""
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if rows.size == 0 or cols.size == 0:
        return None
    return [int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="spikes/n2-appearance")
    parser.add_argument("--threshold", type=int, default=0, help="逐通道差值阈值（0 = 严格逐字节）")
    args = parser.parse_args()

    root = Path(args.out)
    shots = root / "shots"
    rects_path = root / "readback" / "n2-ui-rects.json"
    rects = json.loads(rects_path.read_text(encoding="utf-8"))
    hud = rects["hud"]
    # HUD 面板区域（含 2px 余量）；此区域外的差异 = 3D 视口区的差异
    y0, y1 = max(0, hud["y"] - 2), min(rects["viewport"]["height"], hud["y"] + hud["height"] + 2)
    x0, x1 = max(0, hud["x"] - 2), min(rects["viewport"]["width"], hud["x"] + hud["width"] + 2)

    results = []
    for left_name, right_name, note in PAIRS:
        left = np.asarray(Image.open(shots / f"{left_name}.png").convert("RGB")).astype(np.int16)
        right = np.asarray(Image.open(shots / f"{right_name}.png").convert("RGB")).astype(np.int16)
        if left.shape != right.shape:
            raise SystemExit(f"size mismatch: {left_name} {left.shape} vs {right_name} {right.shape}")
        delta = np.abs(left - right).max(axis=2)
        differing = delta > args.threshold
        viewport_only = differing.copy()
        viewport_only[y0:y1, x0:x1] = False
        results.append({
            "left": f"{left_name}.png",
            "right": f"{right_name}.png",
            "note": note,
            "size": [int(left.shape[1]), int(left.shape[0])],
            "diff_pixels": int(differing.sum()),
            "diff_bbox": bbox_of(differing),
            "diff_pixels_outside_hud": int(viewport_only.sum()),
            "diff_bbox_outside_hud": bbox_of(viewport_only),
            "hud_rect": [hud["x"], hud["y"], hud["x"] + hud["width"], hud["y"] + hud["height"]],
        })

    document = {"threshold": args.threshold, "ui_rects": rects, "pairs": results}
    (root / "readback" / "n2-pixel-diff.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in results:
        print(f"{item['left']} vs {item['right']}")
        print(f"    diff={item['diff_pixels']} bbox={item['diff_bbox']}"
              f" | 视口区(排除HUD) diff={item['diff_pixels_outside_hud']} bbox={item['diff_bbox_outside_hud']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
