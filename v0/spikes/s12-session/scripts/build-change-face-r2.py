#!/usr/bin/env python3
"""R2 / F8：重建「交付面变更声明」（`m3-change-face.txt` 的 R2 修订段 + 机器可读声明 JSON）。

为什么要机器可读 + 时间锚（R2 / M3-15 的一半）：
  R1 的声明是**手写清单**，与 `shasum -c` 的实际差集靠人眼比对 ⇒ 口径漂移无法自动发现。
  本脚本从盘上**复算**三件事并落盘：
    ① `modified`  = `shasum -a 256 -c V0_M2.sha256` 的非 OK 集合（在采集面内的改动）；
    ② `added`     = `02_source/**` 里**不在** `V0_M2.sha256` 的新增文件；
    ③ `outside_face` = 采集面之外的声明改动（`spikes/s5-latency-calibration/**` 等）；
  并写入**时间锚**（`declared_at_epoch` + 当时的 `shasum -c` 原始输出）与**重取理由**。

用法：python3 -B spikes/s12-session/scripts/build-change-face-r2.py <ws>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

OUTSIDE_FACE = [
    ("spikes/s5-latency-calibration/calibration.registry.json",
     "P-9 / 3A-C3：绝对路径 → 相对路径迁移（本文件不在 V0_M2.sha256 采集面内）"),
    ("spikes/s5-latency-calibration/negctl/**",
     "R2 新增：registry 路径格式判据的负例载体（采集面外）"),
    ("spikes/s12-session/**",
     "R2 新增/改写：负例套件、判据驱动、变更声明（M3 采集面 = V0_M3.sha256，非 V0_M2）"),
    ("spikes/s13-render/**",
     "R2 新增：真浏览器验收驱动 + 截图 + 日志（M3 采集面 = V0_M3.sha256，非 V0_M2）"),
]


def shasum_check(ws: Path) -> tuple[list[str], str]:
    proc = subprocess.run(["shasum", "-a", "256", "-c", "V0_M2.sha256"], cwd=str(ws),
                          capture_output=True, text=True)
    lines = proc.stdout.splitlines()
    non_ok = [line for line in lines if not line.endswith(": OK")]
    return non_ok, proc.stdout


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: build-change-face-r2.py <workspace>", file=sys.stderr)
        return 2
    ws = Path(argv[1]).resolve()
    manifest = ws / "V0_M2.sha256"
    listed = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        listed.add(line.split("  ", 1)[1].strip())
    non_ok, raw = shasum_check(ws)
    modified = sorted(line.split(":")[0].strip() for line in non_ok)
    added = []
    for path in sorted((ws / "02_source").rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ws).as_posix()
        if any(part in ("__pycache__", ".pytest_cache", "node_modules", "dist", ".build") for part in path.parts):
            continue
        if rel not in listed:
            added.append(rel)

    declaration = {
        "schema_version": 1,
        "plan_id": "REQ-20260921-005-deephealing-v0-m3",
        "round": "R2",
        "basis": "V0_M2.sha256 采集面 + 02_source 全树（复算，不是手写）",
        "declared_at_epoch": int(time.time()),
        "declared_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "v0_m2_lines": len(listed),
        "modified": modified,
        "modified_count": len(modified),
        "added": added,
        "added_count": len(added),
        "outside_face": [{"path": path, "reason": reason} for path, reason in OUTSIDE_FACE],
        "inherited_m2_deviations": [{
            "path": "02_source/v0_skeleton/kernel/tools/calibrate_latency.py",
            "v0_m2_recorded_sha256": "e30be65b…（R1 登记，R1 已独立复现）",
            "m2_disk_sha256": "23fed40d…（R1 登记：M2 提交态与 V0_M2 记录不一致）",
            "reason": "M2 继承缺陷：V0_M2.sha256 的该条记录**在 M2 收尾时**就与盘上/M2 提交态不一致（M3 R1 未动过该文件）。"
                      "R2 本轮因 P-9（F5）**另有**修改 ⇒ 现在它同时是「本轮声明改动」。",
        }],
        "shasum_check_raw": raw,
        "note": "非 OK 集合必须 == modified（SECTION A）∪ inherited_m2_deviations 的解释面；双向判据见 ac-m3-1b-check.py。",
    }
    out = ws / "spikes" / "s12-session" / "m3-change-face.json"
    out.write_text(json.dumps(declaration, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    face = ws / "spikes" / "s12-session" / "m3-change-face.txt"
    text = face.read_text(encoding="utf-8")
    marker = "SECTION A-R2 — R2 AMENDMENT"
    block = [
        "",
        "--------------------------------------------------------------------------------",
        marker,
        "--------------------------------------------------------------------------------",
        f"Written at epoch {declaration['declared_at_epoch']} ({declaration['declared_at_local']}).",
        "复算口径：`shasum -a 256 -c V0_M2.sha256` 的非 OK 集合 + `02_source` 全树 vs 采集面差集。",
        f"machine-readable: spikes/s12-session/m3-change-face.json（含时间锚与 shasum 原始输出）",
        "",
        f"MODIFIED (in V0_M2 face; expected FAILED) count = {declaration['modified_count']}",
    ]
    block += modified
    block += [
        "",
        f"ADDED (not in V0_M2 face) count = {declaration['added_count']}",
    ]
    block += added
    block += [
        "",
        "OUTSIDE THE V0_M2 COLLECTION FACE (declared explicitly)",
    ]
    block += [f"{path}   ({reason})" for path, reason in OUTSIDE_FACE]
    block += [
        "",
        "INHERITED M2 DEVIATION (registered separately, per F8)",
        "02_source/v0_skeleton/kernel/tools/calibrate_latency.py"
        "   V0_M2 记 e30be65b… / M2 提交态 23fed40d…（M2 继承缺陷；R1 已独立复现，R2 因 P-9 另有本轮修改）",
        "",
    ]
    if marker in text:
        text = text[:text.index("SECTION A-R2 — R2 AMENDMENT")].rstrip() + "\n" + "\n".join(block)
    else:
        text = text.rstrip() + "\n" + "\n".join(block)
    face.write_text(text, encoding="utf-8")

    print(json.dumps({"declaration": str(out), "change_face": str(face),
                      "modified_count": declaration["modified_count"],
                      "added_count": declaration["added_count"],
                      "declared_at_epoch": declaration["declared_at_epoch"]},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
