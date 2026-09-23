#!/usr/bin/env python3
"""把**未被任何回读文件引用**的录屏移出交付面（spikes/** 脚手架，**非交付面**）。

理由：`spikes/m52-*/**` 会进 `V0_M52.sha256` 的采集面，而 `*.webm` **不在**生成器的按名排除表里
⇒ 多轮试跑留下的陈旧录屏会白白进冻结清单。这里只保留 `readback/chain-<tag>.json` 里
`video_path` 指向的两份（with / without），其余**移入** `spikes/m52-live/runtime/rec-attic/`
（`runtime*` 目录被生成器按名排除；文件不删，可回溯）。

用法：`python3 spikes/m52-live/tools/prune_stale_recordings.py`
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
LIVE = WS / "spikes" / "m52-live"


def main() -> int:
    readback = LIVE / "readback"
    keep: set[str] = set()
    for tag in ("with", "without"):
        path = readback / f"chain-{tag}.json"
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        recorded = document.get("video_path")
        if recorded:
            keep.add(Path(recorded).name)
    attic = LIVE / "runtime" / "rec-attic"
    attic.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for path in sorted((LIVE / "rec").glob("*.webm")):
        if path.name in keep:
            continue
        shutil.move(str(path), str(attic / path.name))
        moved.append(path.name)
    print(json.dumps({"keep": sorted(keep), "moved": len(moved), "attic": str(attic)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
