#!/usr/bin/env python3
"""AC-5 交付物**可复算读数**（spikes/** 脚手架，**非交付面**）：不靠肉眼、不靠文件存在性。

判据（逐条对应任务书 §3 W10 / Raven M-16）：
  ① `shots/desktop-1440x900.png` 的 **PNG 头**尺寸 == 1440×900；
  ② `shots/narrow-390x844.png` 的 PNG 头尺寸 == 390×844；
  ③ `rec/*.webm` **时长 ≥ 15s** 且 **帧数 ≥ 100**（用 Playwright 自带 ffmpeg 探针）；
  ④ 录屏**真的录到了画面**：抽两帧（第 5 帧 / 第 200 帧）逐字节比较 ⇒ **不同**才算有画面变化；
  ⑤ 两张截图的字节数 > 0（存在性只是下限，上面才是判据）。

用法（workdir `<ws>`）：
    python3 spikes/m52-live/tools/check_artifacts.py --tag with \
        --ffmpeg ~/Library/Caches/ms-playwright/ffmpeg-1011/ffmpeg-mac
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
LIVE = WS / "spikes" / "m52-live"


def png_size(path: Path) -> tuple[int, int] | None:
    """读 PNG 头（IHDR）取宽高 —— 不依赖任何图像库。"""
    with path.open("rb") as handle:
        head = handle.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", head[16:24])
    return int(width), int(height)


def ffmpeg_probe(ffmpeg: Path, video: Path) -> dict:
    """用 ffmpeg 探针取时长（`-i` 的容器元数据；本构建**没有** `null` muxer ⇒ 不靠 `-f null`）。"""
    proc = subprocess.run([str(ffmpeg), "-i", str(video)], capture_output=True, text=True)
    text = proc.stderr
    duration = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", text)
    fps = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
    seconds = None
    if duration:
        seconds = int(duration.group(1)) * 3600 + int(duration.group(2)) * 60 + float(duration.group(3))
    return {"exit": proc.returncode, "duration_seconds": seconds,
            "fps_metadata": float(fps.group(1)) if fps else None,
            "duration_raw": duration.group(0) if duration else None}


def count_frames(ffmpeg: Path, video: Path, scratch: Path) -> dict:
    """**真解码计数**：把全部帧解成小图，数落盘文件数（Playwright 的 ffmpeg 构建无 `null`/`select`）。"""
    target = scratch / f"frames-{hashlib.sha256(str(video).encode()).hexdigest()[:8]}"
    target.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([str(ffmpeg), "-y", "-i", str(video), "-s", "160x100", str(target / "f%05d.png")],
                          capture_output=True, text=True)
    frames = sorted(target.glob("f*.png"))
    return {"exit": proc.returncode, "frames": len(frames), "dir": str(target),
            "last_stats_line": (proc.stderr.strip().splitlines() or [""])[-1][:160]}


def extract_frame(ffmpeg: Path, video: Path, at_seconds: float, target: Path) -> dict:
    """抽一帧（用 `-ss` 定位，**不用滤镜**：该构建的滤镜集不全）。"""
    proc = subprocess.run([str(ffmpeg), "-y", "-ss", str(at_seconds), "-i", str(video),
                           "-frames:v", "1", str(target)], capture_output=True, text=True)
    if not target.exists():
        return {"at_seconds": at_seconds, "exit": proc.returncode, "bytes": 0, "sha256": None}
    data = target.read_bytes()
    return {"at_seconds": at_seconds, "exit": proc.returncode, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AC-5 artifacts check (PNG size / webm duration+frames)")
    parser.add_argument("--tag", default="with")
    parser.add_argument("--ffmpeg", default=str(Path.home() / "Library/Caches/ms-playwright/ffmpeg-1011/ffmpeg-mac"))
    parser.add_argument("--scratch", default="/tmp/m52-live-frames")
    parser.add_argument("--json", dest="json_path", default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    ffmpeg = Path(args.ffmpeg).expanduser()
    scratch = Path(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)

    desktop = LIVE / "shots" / "desktop-1440x900.png"
    narrow = LIVE / "shots" / "narrow-390x844.png"
    # 录屏路径**按 tag 从回读文件取**（每个 tag 有自己的 .webm；`rec/` 下可能有多个）
    chain_file = LIVE / "readback" / f"chain-{args.tag}.json"
    video = None
    if chain_file.exists():
        recorded = json.loads(chain_file.read_text(encoding="utf-8")).get("video_path")
        if recorded:
            video = Path(recorded)
    if video is None or not video.exists():
        videos = sorted((LIVE / "rec").glob("*.webm"), key=lambda path: path.stat().st_mtime)
        video = videos[-1] if videos else None

    desktop_size = png_size(desktop) if desktop.exists() else None
    narrow_size = png_size(narrow) if narrow.exists() else None
    probe = ffmpeg_probe(ffmpeg, video) if (video and ffmpeg.exists()) else {"exit": None, "duration_seconds": None}
    counted = count_frames(ffmpeg, video, scratch) if (video and ffmpeg.exists()) else {"frames": None}
    frame_a = extract_frame(ffmpeg, video, 0.5, scratch / f"{args.tag}-t0.5.png") if video else None
    frame_b = extract_frame(ffmpeg, video, 10.0, scratch / f"{args.tag}-t10.png") if video else None

    criteria = {
        "desktop_is_1440x900": {"pass": desktop_size == (1440, 900), "reading": desktop_size},
        "narrow_is_390x844": {"pass": narrow_size == (390, 844), "reading": narrow_size},
        "video_duration_ge_15s": {"pass": bool(probe.get("duration_seconds") is not None
                                               and probe["duration_seconds"] >= 15.0),
                                  "reading": probe.get("duration_seconds")},
        "video_frames_ge_100": {"pass": bool(counted.get("frames") is not None and counted["frames"] >= 100),
                                "reading": counted.get("frames")},
        "video_has_motion": {"pass": bool(frame_a and frame_b and frame_a.get("sha256") and frame_b.get("sha256")
                                          and frame_a["sha256"] != frame_b["sha256"]),
                             "reading": {"t0.5": (frame_a or {}).get("sha256"),
                                         "t10": (frame_b or {}).get("sha256")}},
    }
    document = {
        "status": "measured", "tag": args.tag,
        "shots": {"desktop": str(desktop.relative_to(WS)), "narrow": str(narrow.relative_to(WS)),
                  "desktop_bytes": desktop.stat().st_size if desktop.exists() else None,
                  "narrow_bytes": narrow.stat().st_size if narrow.exists() else None},
        "video": {"path": str(video.relative_to(WS)) if video else None,
                  "bytes": video.stat().st_size if video else None, "probe": probe, "frame_count": counted},
        "frames": {"t0.5": frame_a, "t10": frame_b},
        "ffmpeg": str(ffmpeg), "ffmpeg_exists": ffmpeg.exists(),
        "criteria": criteria,
        "all_pass": all(item["pass"] for item in criteria.values()),
    }
    text = json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True)
    sys.stdout.write(text + "\n")
    target = Path(args.json_path) if args.json_path else LIVE / "readback" / f"artifact-check-{args.tag}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text + "\n", encoding="utf-8")
    return 0 if document["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
