#!/usr/bin/env python3
"""治愈系美学的可执行数值校验（assets/manifest.json）。

用法：
    python3 tools/aesthetic_check.py <assets_manifest.json>

判据（来自 district.pack.spec.md §5 / 01 设计 §10，全部为数值，不做主观评价）：
  - palette.saturation_pct <= 45
  - palette.hue_deg 落在 [20,60] 或 [180,210]
  - roughness_range[0] >= 0.6
  - audio_bed ∈ {ambient_lowfreq, none}
  - 夜间高饱和点缀色数量 <= 2
  - license ∈ 运行时白名单（GPL 系一律拒绝进运行时）

退出码：0 = 全部通过；1 = 有超界项；2 = 用法错误。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RUNTIME_ALLOWED_LICENSES = {
    "proprietary-self-authored",
    "CC0-1.0",
    "CC-BY-4.0",
    "MIT",
    "Apache-2.0",
}


def check(manifest: dict) -> list[str]:
    constraints = manifest["aesthetic_constraints"]
    palette_limits = constraints["palette"]
    problems: list[str] = []
    night_accents = 0

    for asset in manifest["assets"]:
        aid = asset["id"]
        palette = asset["palette"]
        if palette["saturation_pct"] > palette_limits["saturation_max_pct"]:
            problems.append(f"{aid}: saturation {palette['saturation_pct']} > {palette_limits['saturation_max_pct']}")
        hue = palette["hue_deg"]
        warm = palette_limits["warm_hue_range_deg"]
        cool = palette_limits["cool_complement_hue_range_deg"]
        in_warm = warm[0] <= hue <= warm[1]
        in_cool = cool[0] <= hue <= cool[1]
        if not (in_warm or in_cool):
            problems.append(f"{aid}: hue {hue} outside warm{warm} / cool{cool}")
        if palette["saturation_pct"] > palette_limits["saturation_max_pct"]:
            pass
        if asset["kind"] in {"texture", "material"} and palette["saturation_pct"] >= 40 and palette["lightness_pct"] >= 65:
            night_accents += 1
        rough_min = asset["roughness_range"][0]
        if rough_min < constraints["material"]["roughness_min"]:
            problems.append(f"{aid}: roughness_min {rough_min} < {constraints['material']['roughness_min']}")
        if asset["audio_bed"] not in constraints["audio"]["allowed_beds"]:
            problems.append(f"{aid}: audio_bed {asset['audio_bed']} not in {constraints['audio']['allowed_beds']}")
        if asset["license"] not in RUNTIME_ALLOWED_LICENSES:
            problems.append(f"{aid}: license {asset['license']} not allowed at runtime")

    if night_accents > palette_limits["night_high_saturation_accents_max"]:
        problems.append(
            f"night accents {night_accents} > {palette_limits['night_high_saturation_accents_max']}"
        )
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: aesthetic_check.py <assets_manifest.json>", file=sys.stderr)
        return 2
    manifest = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    problems = check(manifest)
    if problems:
        for problem in problems:
            print(f"E_AESTHETIC_OUT_OF_RANGE: {problem}", file=sys.stderr)
        return 1
    print(f"aesthetic_check: OK ({len(manifest['assets'])} assets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
