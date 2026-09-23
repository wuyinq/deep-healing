#!/usr/bin/env python3
"""把 r2 的两段文本**追加**到交付面的 `03_artisan_self_test.log` / `06_v0_m52_self_test.md`。

为什么用脚本而不是手抄：追加内容含大量反引号/竖线/中文标点，脚本可保证**逐字节**落盘，
并在落盘后**回读一次**（打印新行数 + 追加段 sha256），满足「写『已落地』前必须回读盘上产物一次」。

用法：`python3 spikes/m52-live/tools/append_sections.py`
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
NOTES = WS / "spikes" / "m52-live" / "notes"

PLAN = (
    (WS / "03_artisan_self_test.log",
     [NOTES / "m52-r2-03-section.md", NOTES / "m52-r2-03-tail.md"]),
    (WS / "06_v0_m52_self_test.md",
     [NOTES / "m52-r2-06-section.md"]),
)


def main() -> int:
    for target, sources in PLAN:
        before = target.read_text(encoding="utf-8")
        payload = "".join(source.read_text(encoding="utf-8") for source in sources)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(payload)
        after = target.read_text(encoding="utf-8")
        appended = after[len(before):]
        print(f"{target.name}: lines {before.count(chr(10))} -> {after.count(chr(10))}; "
              f"appended_bytes={len(appended.encode('utf-8'))}; "
              f"sha256={hashlib.sha256(appended.encode('utf-8')).hexdigest()[:16]}; "
              f"byte_identical={appended == payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
