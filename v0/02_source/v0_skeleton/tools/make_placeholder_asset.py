#!/usr/bin/env python3
"""V0 程序化占位资产生成器（**离线**，确定性，纯 stdlib，不依赖任何生成式模型）。

定位：AC-15 / D-0.8 的 V0 边界只要求「1 张程序化占位资产 + 1 份 manifest 示例」。
本脚本是那张资产的**生成命令**（`content-pipeline.spec.md` 第 1 步），也是「运行时零生成」
的对照物：它属于**离线内容管线**，不在任何运行时调用路径上。

产物：64×64 的 8-bit RGB PNG，低饱和米色渐变 + 一个柔和圆形，无任何 `tEXt`/`iTXt` 元数据。

用法：
  python3 make_placeholder_asset.py <out.png>
退出码：0 = 已生成；2 = 用法错误。
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

WIDTH = HEIGHT = 64


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def render_pixels() -> bytes:
    rows = bytearray()
    for y in range(HEIGHT):
        rows.append(0)  # filter type 0
        for x in range(WIDTH):
            # 低饱和暖灰渐变（治愈系基调：饱和度低、无强对比）
            base = 214 - int(18 * y / HEIGHT)
            r = max(0, min(255, base))
            g = max(0, min(255, base - 6))
            b = max(0, min(255, base - 14))
            dx, dy = x - WIDTH // 2, y - HEIGHT // 2
            if dx * dx + dy * dy < 220:  # 柔和圆形（程序化，非生成式）
                r, g, b = min(255, r + 6), min(255, g + 4), min(255, b + 2)
            rows += bytes((r, g, b))
    return bytes(rows)


def write_png(path: Path) -> None:
    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    payload = (b"\x89PNG\r\n\x1a\n"
               + _chunk(b"IHDR", header)
               + _chunk(b"IDAT", zlib.compress(render_pixels(), 9))
               + _chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    write_png(Path(argv[0]))
    print(f"placeholder asset written: {argv[0]} ({WIDTH}x{HEIGHT}, no tEXt/iTXt)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
