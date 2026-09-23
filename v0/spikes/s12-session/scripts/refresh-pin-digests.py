#!/usr/bin/env python3
"""R2 / R-M2-1 收口：把 `pins.json` 的 `digests` 与盘上被钉住的能力产物**逐字节绑定**。

用法：python3 -B spikes/s12-session/scripts/refresh-pin-digests.py <02_source>
幂等：内容不变则不写盘（打印 `unchanged: true`）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: refresh-pin-digests.py <02_source_dir>", file=sys.stderr)
        return 2
    caps = Path(argv[1]).resolve() / "v0_skeleton" / "capabilities"
    pins_path = caps / "pins.json"
    document = json.loads(pins_path.read_text(encoding="utf-8"))
    pins = document.get("pins") or {}
    digests: dict[str, str] = {}
    for capability_id, version in sorted(pins.items()):
        target = caps / f"{capability_id}@{version}.capability.json"
        if not target.is_file():
            print(f"E_CAP_DIGEST_MISMATCH: pinned artifact missing: {target}", file=sys.stderr)
            return 1
        digests[f"{capability_id}@{version}"] = hashlib.sha256(target.read_bytes()).hexdigest()
    # 保持既有键顺序（schema_version / note / pins / digests / provider_overrides）
    ordered: dict = {}
    for key, value in document.items():
        ordered[key] = value
        if key == "pins":
            ordered["digests"] = digests
    if "digests" not in ordered:
        ordered["digests"] = digests
    rendered = json.dumps(ordered, ensure_ascii=False, indent=2) + "\n"
    before = pins_path.read_text(encoding="utf-8")
    if before == rendered:
        print(json.dumps({"pins": str(pins_path), "unchanged": True, "digests": digests},
                         ensure_ascii=False, sort_keys=True))
        return 0
    pins_path.write_text(rendered, encoding="utf-8")
    print(json.dumps({"pins": str(pins_path), "unchanged": False, "digests": digests},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
