#!/usr/bin/env python3
"""GLB 结构读数（N5 / `AC-E-2e` / `AC-H-5` / `AC-I-3` 的资产面证据）。

运行：`python3 v0/spikes/n5-asset/glb_probe.py --path <glb> [--json-out <path>]`

**只读**：解析 glTF binary 容器（magic/version/JSON chunk/BIN chunk），输出：
  - `asset.generator` / `version`
  - `nodes` / `meshes` / `skins`（含 `joints` 数）/ `materials` / `images`
  - `animations[]`（名称 + channel 数）
  - **外部 uri 清单**（`AC-E-2e`：自包含 ⇒ 必须为空）
  - `extensionsUsed` / `extensionsRequired`
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

MAGIC = b"glTF"
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def parse(path: Path) -> dict:
    data = path.read_bytes()
    magic, version, length = struct.unpack("<4sII", data[:12])
    if magic != MAGIC:
        raise ValueError(f"not a GLB (magic={magic!r})")
    off = 12
    gltf = None
    bin_len = 0
    while off < length:
        clen, ctype = struct.unpack("<II", data[off:off + 8])
        chunk = data[off + 8:off + 8 + clen]
        if ctype == JSON_CHUNK:
            gltf = json.loads(chunk.decode("utf-8"))
        elif ctype == BIN_CHUNK:
            bin_len = len(chunk)
        off += 8 + clen
    if gltf is None:
        raise ValueError("no JSON chunk")
    external = []
    for key in ("images", "buffers"):
        for e in gltf.get(key, []):
            if "uri" in e:
                external.append({"kind": key, "uri": e["uri"][:120]})
    return {
        "path": str(path),
        "file_bytes": len(data),
        "container": {"magic": magic.decode(), "version": version, "declared_length": length},
        "asset": gltf.get("asset"),
        "nodes": len(gltf.get("nodes", [])),
        "meshes": len(gltf.get("meshes", [])),
        "skins": [{"name": s.get("name"), "joints": len(s.get("joints", []))} for s in gltf.get("skins", [])],
        "skin_joint_count": sum(len(s.get("joints", [])) for s in gltf.get("skins", [])),
        "materials": len(gltf.get("materials", [])),
        "materials_detail": [{"name": m.get("name"),
                              "pbr": list((m.get("pbrMetallicRoughness") or {}).keys())}
                             for m in gltf.get("materials", [])],
        "images": len(gltf.get("images", [])),
        "animations": [{"name": a.get("name"), "channels": len(a.get("channels", []))}
                       for a in gltf.get("animations", [])],
        "animation_count": len(gltf.get("animations", [])),
        "bin_chunk_bytes": bin_len,
        "external_uris": external,
        "self_contained": len(external) == 0,
        "extensionsUsed": gltf.get("extensionsUsed"),
        "extensionsRequired": gltf.get("extensionsRequired"),
        "node_names": [n.get("name") for n in gltf.get("nodes", [])][:30],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    p = Path(args.path)
    if not p.is_file():
        print(f"E_ENV: not a file: {p}", file=sys.stderr)
        return 2
    doc = parse(p)
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"glb_probe: wrote {out}")
    else:
        print(text)
    print(f"glb_probe: nodes={doc['nodes']} meshes={doc['meshes']} skin_joints={doc['skin_joint_count']} "
          f"animations={doc['animation_count']} self_contained={doc['self_contained']}")
    return 0 if doc["self_contained"] else 1


if __name__ == "__main__":
    sys.exit(main())
