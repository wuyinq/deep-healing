#!/usr/bin/env python3
"""N2-r3 面部可见性**投影取样**探针（spike 专用，**非交付面**）。

为什么需要它：`n2-visibility-readout.py` 的「按 `material_hex` + 容差匹配」只在
**平面着色**下才等价于「画面上看到的东西」；本渲染层是 `MeshStandardMaterial` + 光照，
**背光面的实际像素色 ≠ 参考 `material_hex`** ⇒ 那个读数会把「真的可见」误报成 0 px。

本探针不猜：用**实测相机读数**（`cameraReport()` 的 position / quaternion /
projection_matrix / aspect / viewport）把每个部件的**正面（+z 面）**四角投影到屏幕坐标，
再直接**采样 PNG 的像素**，给出：

  ① 每个部件正面四边形内的**主导像素色**与占比（画面上真正看到的是什么色）；
  ② 该四边形的中心 / 四角采样色；
  ③ 全图**平坦色块**清单（含 bbox）—— 渲染是低模平面着色，色块 = 画面上真实存在的面。

用法（workdir `<ws>`）：
    python3 spikes/n2-appearance/n2-r3-face-probe.py --out spikes/n2-appearance \
        --shot n2-obs-indoor-closeup-daily --reading indoor_closeup_daily
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

#: 部件几何取自**实机读回**的 `characterReport()`（`readings.<key>.character`）。
#: 这里只声明「按什么顺序看哪几个部件的 +z 正面」，不重复任何尺寸常量。
PROBE_PARTS = ['head', 'eyes', 'lips', 'hair', 'torso', 'coat', 'arm_l', 'leg_l', 'mask']


def quaternion_to_matrix(q: list[float]) -> np.ndarray:
    """three.js 四元数 `[x, y, z, w]` ⇒ 3x3 旋转矩阵。"""
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def project(point: np.ndarray, camera: dict, width: int, height: int) -> tuple[float, float]:
    """世界点 ⇒ 屏幕像素坐标（three 透视相机；相机看向视图空间 −z）。"""
    rotation = quaternion_to_matrix(camera['quaternion'])
    view = rotation.T @ (point - np.array(camera['position'], dtype=np.float64))
    m = np.array(camera['projection_matrix'], dtype=np.float64).reshape(4, 4).T
    clip = m @ np.array([view[0], view[1], view[2], 1.0])
    ndc = clip[:3] / clip[3]
    return ((ndc[0] + 1) / 2 * width, (1 - ndc[1]) / 2 * height)


def quad_of(part: dict, placement: list[float], camera: dict, width: int, height: int) -> dict:
    """部件**正面（+z）**四角的屏幕坐标 + 中心。"""
    sx, sy, sz = part['size']
    ox, oy, oz = part['local_offset']
    front_z = oz + sz / 2
    corners = []
    for dx, dy in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)):
        world = np.array([placement[0] + ox + dx, placement[1] + oy + dy, placement[2] + front_z])
        corners.append(project(world, camera, width, height))
    center = project(np.array([placement[0] + ox, placement[1] + oy, placement[2] + front_z]),
                     camera, width, height)
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return {
        'part': part['part'], 'front_z_local': round(front_z, 6),
        'center_px': [round(center[0], 1), round(center[1], 1)],
        'rect_px': [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
        'corners_px': [[round(x, 1), round(y, 1)] for x, y in corners],
        'source_hex': part.get('source_hex'), 'reference_material_hex': part.get('material_hex'),
    }


def dominant_in_quad(image: np.ndarray, rect: list[float], top: int = 3) -> list[dict]:
    """四边形**内接区**（缩 15% 以避开边缘抗锯齿）的主导像素色。"""
    x0, y0, x1, y1 = rect
    inset_x = (x1 - x0) * 0.15
    inset_y = (y1 - y0) * 0.15
    xa, xb = int(max(0, x0 + inset_x)), int(min(image.shape[1], x1 - inset_x + 1))
    ya, yb = int(max(0, y0 + inset_y)), int(min(image.shape[0], y1 - inset_y + 1))
    if xb <= xa or yb <= ya:
        return []
    region = image[ya:yb, xa:xb].reshape(-1, 3)
    packed = (region[:, 0].astype(np.int32) << 16) | (region[:, 1].astype(np.int32) << 8) | region[:, 2]
    values, counts = np.unique(packed, return_counts=True)
    order = np.argsort(-counts)[:top]
    total = int(region.shape[0])
    out = []
    for index in order:
        code = int(values[index])
        out.append({'hex': '#{:02x}{:02x}{:02x}'.format((code >> 16) & 0xFF, (code >> 8) & 0xFF, code & 0xFF),
                    'pixels': int(counts[index]), 'share': round(float(counts[index]) / total, 4)})
    return out


def flat_blocks(image: np.ndarray, min_pixels: int) -> list[dict]:
    """全图平坦色块（低模平面着色 ⇒ 色块 = 画面上真实存在的面）。"""
    flat = image.reshape(-1, 3)
    packed = (flat[:, 0].astype(np.int32) << 16) | (flat[:, 1].astype(np.int32) << 8) | flat[:, 2]
    values, counts = np.unique(packed, return_counts=True)
    out = []
    for index in np.argsort(-counts):
        count = int(counts[index])
        if count < min_pixels:
            break
        code = int(values[index])
        mask = (packed == code).reshape(image.shape[0], image.shape[1])
        rows = np.flatnonzero(mask.any(axis=1))
        cols = np.flatnonzero(mask.any(axis=0))
        out.append({
            'hex': '#{:02x}{:02x}{:02x}'.format((code >> 16) & 0xFF, (code >> 8) & 0xFF, code & 0xFF),
            'pixels': count,
            'bbox': [int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])],
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='spikes/n2-appearance')
    parser.add_argument('--shot', required=True)
    parser.add_argument('--reading', required=True, help='readback 里的读数键（如 indoor_closeup_daily）')
    parser.add_argument('--min-pixels', type=int, default=800)
    args = parser.parse_args()

    root = Path(args.out)
    shots = json.loads((root / 'readback' / 'n2-obs-shots.json').read_text(encoding='utf-8'))
    reading = shots['readings'][args.reading]
    camera = reading['camera']
    image = np.asarray(Image.open(root / 'shots' / f'{args.shot}.png').convert('RGB'))
    height, width = image.shape[0], image.shape[1]
    if int(round(camera['aspect'] * height)) != width:
        raise SystemExit(f"camera aspect {camera['aspect']} vs image {width}x{height} 不一致")
    npc = shots['npc']
    pos_mm = reading['npc_position_mm']
    placement = [pos_mm['x'] / 1000, pos_mm['y'] / 1000, pos_mm['z'] / 1000]
    parts = {part['part']: part for part in reading['character'] if part['entity_id'] == npc}

    probe = []
    for name in PROBE_PARTS:
        part = parts.get(name)
        if not part:
            continue
        quad = quad_of(part, placement, camera, width, height)
        quad['dominant_inside_front_quad'] = dominant_in_quad(image, quad['rect_px'])
        cx, cy = quad['center_px']
        if 0 <= int(cy) < height and 0 <= int(cx) < width:
            quad['center_px_color'] = '#{:02x}{:02x}{:02x}'.format(*image[int(cy), int(cx)])
        probe.append(quad)

    document = {
        'shot': f'{args.shot}.png',
        'reading': args.reading,
        'npc': npc,
        'placement_m': placement,
        'camera': {key: camera[key] for key in ('position', 'quaternion', 'fov', 'near', 'far', 'aspect')},
        'image_size': [width, height],
        'note': '正面 = 部件局部 +z 面；屏幕坐标由实测 cameraReport() 投影得到，像素色为 PNG 真实值',
        'front_face_probe': probe,
        'flat_blocks': flat_blocks(image, args.min_pixels),
    }
    (root / 'readback' / f'n2-r3-face-probe-{args.shot}.json').write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(f"== {args.shot} (reading={args.reading}) placement={placement} ==")
    for item in probe:
        dom = ' '.join(f"{d['hex']}x{d['pixels']}({d['share']})" for d in item['dominant_inside_front_quad'])
        print(f"  {item['part']:<6} front_z={item['front_z_local']:<8} rect={item['rect_px']}"
              f" center={item['center_px']} center_color={item.get('center_px_color')}"
              f" ref={item['reference_material_hex']}")
        print(f"         正面四边形内主导色: {dom}")
    print('  --- 全图平坦色块（>=%d px）---' % args.min_pixels)
    for block in document['flat_blocks']:
        print(f"    {block['hex']} {block['pixels']:>7} px bbox={block['bbox']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
