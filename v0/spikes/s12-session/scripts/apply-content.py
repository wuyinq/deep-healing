#!/usr/bin/env python3
"""M3 内容层落地脚本（artisan 一次性工具，**不属交付面**）。

做三件事（幂等；全部数据驱动，无 per-pack 代码分支）：
  1. 给两个 pack 的每个 NPC 加 `healing_face` / `hidden_face`（D-6：**加字段不删字段**，
     既有 `narrative_hooks` 原样保留）。
  2. 给两个 pack 的 `pack.json` 的 `entrypoints` 加 `worldview = "worldview.json"`（D-5）。
  3. 打印每个文件的 sha256，便于前后比对。

用法：python3 spikes/s12-session/scripts/apply-content.py <ws>/02_source
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PACKS = ("xingfu-xiaoqu", "xingfu-xiaoqu-north")

# 两面的文案：数据（内容作者写死在这里，不构成代码分支；两个 pack 的 NPC 内容相同）
FACES = {
    "npc-001": {
        "healing_face": ["清晨会替整层楼把走廊的灯关掉"],
        "hidden_face": ["一夜没关灯：这层楼整晚只有这一扇窗是醒着的"],
    },
    "npc-002": {
        "healing_face": ["出门前会回头看一眼走廊，像在确认什么都在"],
        "hidden_face": ["加班成了理所当然，直到有人替他记了一次晚饭"],
    },
    "npc-003": {
        "healing_face": ["每天同一时间坐在同一张长椅上，谁经过都点头"],
        "hidden_face": ["他记得所有住户的口味，却没人记得他吃什么"],
    },
    "npc-004": {
        "healing_face": ["把所有人的事都排在自己前面"],
        "hidden_face": ["洗衣服的时候会站着发一会儿呆：洗衣机今天转到同一格第三次"],
    },
    "npc-005": {
        "healing_face": ["把窗户开一条缝，让楼下的说话声飘上来"],
        "hidden_face": ["台灯亮到很晚，桌上那本书很久没翻页"],
    },
}


def dump(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def add_faces(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    document = json.loads(original)
    npc_id = str(document.get("id"))
    faces = FACES.get(npc_id)
    if faces is None:
        print(f"SKIP  {path}: no face data for {npc_id}")
        return False
    changed = False
    rebuilt: dict = {}
    for key, value in document.items():
        rebuilt[key] = value
        if key == "narrative_hooks":
            for face_key, face_value in faces.items():
                if rebuilt.get(face_key) != face_value:
                    changed = True
                rebuilt[face_key] = face_value
    for face_key, face_value in faces.items():  # narrative_hooks 缺失时的兜底（本 pack 不会走到）
        if face_key not in rebuilt:
            rebuilt[face_key] = face_value
            changed = True
    if not changed:
        print(f"SAME  {path}")
        return False
    text = dump(rebuilt)
    path.write_text(text, encoding="utf-8")
    print(f"WRITE {path} sha256={sha256_text(text)}")
    return True


def add_entrypoint(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    document = json.loads(original)
    entrypoints = document.get("entrypoints") or {}
    if entrypoints.get("worldview") == "worldview.json":
        print(f"SAME  {path}")
        return False
    rebuilt: dict = {}
    for key, value in document.items():
        if key == "entrypoints":
            new_entrypoints: dict = {}
            for entry_key, entry_value in value.items():
                new_entrypoints[entry_key] = entry_value
                if entry_key == "assets_manifest":
                    new_entrypoints["worldview"] = "worldview.json"
            if "worldview" not in new_entrypoints:
                new_entrypoints["worldview"] = "worldview.json"
            rebuilt[key] = new_entrypoints
        else:
            rebuilt[key] = value
    text = dump(rebuilt)
    path.write_text(text, encoding="utf-8")
    print(f"WRITE {path} sha256={sha256_text(text)}")
    return True


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: apply-content.py <02_source_dir>", file=sys.stderr)
        return 2
    source = Path(argv[1]).resolve()
    districts = source / "v0_skeleton" / "districts"
    touched = 0
    for pack in PACKS:
        pack_dir = districts / pack
        for npc_path in sorted((pack_dir / "npcs").glob("*.json")):
            touched += 1 if add_faces(npc_path) else 0
        touched += 1 if add_entrypoint(pack_dir / "pack.json") else 0
    print(f"changed files: {touched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
