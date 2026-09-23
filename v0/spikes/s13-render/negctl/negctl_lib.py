#!/usr/bin/env python3
"""R2 负例公共库（隔离执行：整树副本 + node_modules 软链）。

纪律（任务书 §4.1 / §4.3）：
  - 负例**只**在 `<NEG_ROOT>/<case>/` 的整树副本上跑，交付面 `02_source/**` 一个字节都不动；
  - 每个副本旁挂 `node_modules` 软链 ⇒ 依赖可达，禁止出现 `ERR_MODULE_NOT_FOUND` 假红；
  - `turned_red` **只**允许给 `judged_red`（断言真判红）；`crash` 必须单独分类。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

WS = Path("/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/REQ-20260921-005-deephealing-v0-m3")
SRC = WS / "02_source"
LOG_DIR = WS / "spikes" / "s13-render" / "logs"
NEG_ROOT = Path(os.environ.get("NEGCTL_ROOT", "/tmp/r3-artisan"))

GENERATED = ("node_modules", "__pycache__", "dist", ".build", ".pytest_cache", ".DS_Store", ".venv")


def fresh_copy(case: str, source: Path | None = None) -> Path:
    """整树副本 `<NEG_ROOT>/<case>/02_source` + `<case>/node_modules` 软链。"""
    root = NEG_ROOT / case
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    shutil.copytree(source or SRC, root / "02_source", ignore=shutil.ignore_patterns(*GENERATED))
    (root / "node_modules").symlink_to(WS / "node_modules")
    return root


def inject(path: Path, old: str, new: str, expect: int = 1) -> str:
    """定点注入：锚点必须**恰好**命中 `expect` 次，否则直接报错（不猜）。"""
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != expect:
        raise SystemExit(f"INJECT-ANCHOR-MISS {path}: found={found} expect={expect} anchor={old!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")
    return f"{old!r} -> {new!r} (x{found})"


def run(cmd: list[str], cwd: Path, timeout: int = 900, extra_env: dict | None = None):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra_env:
        env.update(extra_env)
    started = time.time()
    proc = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True,
                          text=True, env=env, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr, round(time.time() - started, 2)


CRASH_MARKERS = ("ERR_MODULE_NOT_FOUND", "Cannot find package", "Cannot find module",
                 "ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING", "SyntaxError")


def classify_scene_assert(exit_code: int, stdout: str, stderr: str) -> dict:
    """区分 `crash`（模块/环境错误）/ `judged_red`（断言真判红）/ `judged_green`。"""
    pass_lines = [line for line in stdout.splitlines() if line.startswith("PASS")]
    fail_lines = [line for line in stdout.splitlines() if line.startswith("FAIL")]
    fail_names = [line.split()[1] for line in fail_lines if len(line.split()) > 1]
    markers = sorted({m for m in CRASH_MARKERS if m in stderr or m in stdout})
    verdict = "inconsistent"
    if markers or (not pass_lines and not fail_lines):
        verdict = "crash"
    elif exit_code != 0 and fail_lines:
        verdict = "judged_red"
    elif exit_code == 0 and not fail_lines:
        verdict = "judged_green"
    return {"verdict": verdict, "exit": exit_code, "pass": len(pass_lines), "fail": len(fail_lines),
            "fail_names": fail_names, "crash_markers": markers,
            "turned_red": verdict == "judged_red"}


def sha_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in GENERATED for part in path.parts) or path.suffix == ".pyc":
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("utf-8"))
    return digest.hexdigest()


def write_log(name: str, text: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / name
    path.write_text(text, encoding="utf-8")
    return path


def write_summary(name: str, payload: dict) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- R3 / G1：像素级读数
def _decode_png_pure(data: bytes):
    """**无依赖** PNG 解码（8-bit、非隔行、color type 2/6）⇒ (width, height, channels, bytes)。

    为什么自带解码器：像素判据不能依赖某个可选库（PIL）在场 —— 否则「跑不出读数」会被误读成「判据通过」。
    自带实现让判据在任何装了 python3 的机器上都能复跑。
    """
    import zlib

    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos = 8
    idat = bytearray()
    width = height = bit_depth = color_type = interlace = None
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width = int.from_bytes(chunk[0:4], "big")
            height = int.from_bytes(chunk[4:8], "big")
            bit_depth = chunk[8]
            color_type = chunk[9]
            interlace = chunk[12]
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
    if bit_depth != 8 or interlace != 0 or color_type not in (2, 6):
        raise ValueError(f"unsupported png: depth={bit_depth} color={color_type} interlace={interlace}")
    channels = 3 if color_type == 2 else 4
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    out = bytearray(height * stride)
    previous = bytearray(stride)
    offset = 0
    for row in range(height):
        filter_type = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset + stride])
        offset += stride
        if filter_type == 1:
            for index in range(channels, stride):
                line[index] = (line[index] + line[index - channels]) & 0xFF
        elif filter_type == 2:
            for index in range(stride):
                line[index] = (line[index] + previous[index]) & 0xFF
        elif filter_type == 3:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                line[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
        elif filter_type == 4:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                up = previous[index]
                up_left = previous[index - channels] if index >= channels else 0
                estimate = left + up - up_left
                dist_left, dist_up, dist_up_left = abs(estimate - left), abs(estimate - up), abs(estimate - up_left)
                if dist_left <= dist_up and dist_left <= dist_up_left:
                    predictor = left
                elif dist_up <= dist_up_left:
                    predictor = up
                else:
                    predictor = up_left
                line[index] = (line[index] + predictor) & 0xFF
        out[row * stride:(row + 1) * stride] = line
        previous = line
    return width, height, channels, bytes(out)


def decode_png(path: Path):
    """返回 `(width, height, channels, bytes, decoder)`；优先 PIL，缺库时用自带解码器。"""
    data = path.read_bytes()
    try:
        from PIL import Image  # noqa: PLC0415
        with Image.open(path) as image:
            converted = image.convert("RGB")
            width, height = converted.size
            return width, height, 3, converted.tobytes(), "PIL"
    except Exception:  # noqa: BLE001 —— 缺 PIL / 打开失败 ⇒ 退回自带解码器
        width, height, channels, raw = _decode_png_pure(data)
        return width, height, channels, raw, "pure-python"


def pixel_stats(path: Path, hud_rect: dict | None = None) -> dict:
    """像素统计：背景占比 / 非背景像素包围盒 / **HUD 区域之外**的非背景占比。

    口径（与 architect 的只读探针一致，便于交叉复核）：
      - 背景 = 出现次数最多的 RGB 三元组；
      - 非背景 = 与背景任一通道差 > 8 的像素；
      - `outside_hud_nonbg_ratio` = HUD 矩形**之外**的非背景像素数 / HUD 矩形之外的像素总数。
    """
    width, height, channels, raw, decoder = decode_png(path)
    counts: dict[tuple[int, int, int], int] = {}
    for index in range(0, len(raw), channels):
        key = (raw[index], raw[index + 1], raw[index + 2])
        counts[key] = counts.get(key, 0) + 1
    background, background_count = max(counts.items(), key=lambda item: item[1])

    hud = hud_rect or {}
    hx0 = int(hud.get("x", 0))
    hy0 = int(hud.get("y", 0))
    hx1 = hx0 + int(hud.get("width", 0))
    hy1 = hy0 + int(hud.get("height", 0))

    nonbg = 0
    outside_nonbg = 0
    outside_total = 0
    min_x = min_y = None
    max_x = max_y = None
    for y in range(height):
        row = y * width * channels
        inside_row = hy0 <= y < hy1
        for x in range(width):
            index = row + x * channels
            red, green, blue = raw[index], raw[index + 1], raw[index + 2]
            is_nonbg = (abs(red - background[0]) > 8 or abs(green - background[1]) > 8
                        or abs(blue - background[2]) > 8)
            in_hud = inside_row and hx0 <= x < hx1
            if not in_hud:
                outside_total += 1
            if is_nonbg:
                nonbg += 1
                if not in_hud:
                    outside_nonbg += 1
                min_x = x if min_x is None else min(min_x, x)
                min_y = y if min_y is None else min(min_y, y)
                max_x = x if max_x is None else max(max_x, x)
                max_y = y if max_y is None else max(max_y, y)
    total = width * height
    return {
        "file": path.name,
        "width": width, "height": height, "decoder": decoder,
        "background": list(background),
        "background_ratio": round(background_count / total, 6),
        "nonbg_pixels": nonbg,
        "nonbg_ratio": round(nonbg / total, 6),
        "nonbg_bbox": [min_x, min_y, max_x, max_y] if nonbg else None,
        "hud_rect": {"x": hx0, "y": hy0, "width": hx1 - hx0, "height": hy1 - hy0},
        "outside_hud_pixels": outside_total,
        "outside_hud_nonbg_pixels": outside_nonbg,
        "outside_hud_nonbg_ratio": round(outside_nonbg / outside_total, 6) if outside_total else 0.0,
    }
