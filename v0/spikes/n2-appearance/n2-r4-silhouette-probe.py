#!/usr/bin/env python3
"""N2-r4 轮廓读数探针（spike 专用，**非交付面**）。

为什么需要它：r4 的修复项是**性别可读的轮廓**（长发过肩 / 收腰 / 露腿）。判据
（`scene_assert.mjs` 的 6c 组）读的是**部件盒几何**；本探针补一条**独立的画面侧**读数：

  ① 用**实测相机读数**（`cameraReport()`：position / quaternion / projection_matrix / aspect）
     把每个部件盒的 **8 个角**投影到屏幕，给出该部件在**画面上**的 bbox（低模 ⇒ 盒即轮廓）；
  ② 直接**采样 PNG 像素**：在「头/发/躯干/外衣/腿」的投影区内取主导色，报告画面上真实的色块；
  ③ 给出**屏幕纵向次序**读数：发下缘 y 与肩线（躯干上缘）y、外衣下摆 y、腿底 y 的**像素关系**
     —— 「长发垂到肩下多少像素」「下摆以下露出多少像素的腿」由此可核。

口径：只声明「按什么顺序看哪几个部件」，**不重复任何尺寸常量**（几何一律取实机读回的
`readings.<key>.character`）。8 角投影同时覆盖 +x 侧与 +z 正面 ⇒ 正面 / 3/4 侧向机位都适用。

用法（workdir `<ws>`）：
    python3 spikes/n2-appearance/n2-r4-silhouette-probe.py --out spikes/n2-appearance \
        --shot n2-obs-indoor-side-daily --reading indoor_side_daily
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

#: 轮廓关心的部件（按画面从上到下的顺序排列）。
PROBE_PARTS = ['head', 'hair', 'torso', 'arm_l', 'arm_r', 'coat', 'leg_l', 'leg_r']


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


def box_screen(part: dict, placement: list[float], camera: dict, width: int, height: int) -> dict:
    """部件盒 **8 个角**的屏幕投影 ⇒ 画面 bbox + 各面中心。"""
    sx, sy, sz = part['size']
    ox, oy, oz = part['local_offset']
    xs = [ox - sx / 2, ox + sx / 2]
    ys = [oy - sy / 2, oy + sy / 2]
    zs = [oz - sz / 2, oz + sz / 2]
    corners = []
    for x in xs:
        for y in ys:
            for z in zs:
                corners.append(project(np.array([placement[0] + x, placement[1] + y, placement[2] + z]),
                                       camera, width, height))
    px = [c[0] for c in corners]
    py = [c[1] for c in corners]
    faces = {}
    for name, (x, z) in {'front_+z': (ox, zs[1]), 'side_+x': (xs[1], oz), 'side_-x': (xs[0], oz)}.items():
        center = project(np.array([placement[0] + x, placement[1] + oy, placement[2] + z]),
                         camera, width, height)
        faces[name] = [round(center[0], 1), round(center[1], 1)]
    # 底部 / 顶部中点（纵向次序读数用）
    bottom = project(np.array([placement[0] + ox, placement[1] + ys[0], placement[2] + oz]),
                     camera, width, height)
    top = project(np.array([placement[0] + ox, placement[1] + ys[1], placement[2] + oz]),
                  camera, width, height)
    return {
        'part': part['part'],
        'size': part['size'], 'local_offset': part['local_offset'],
        'screen_bbox': [round(min(px), 1), round(min(py), 1), round(max(px), 1), round(max(py), 1)],
        'screen_height_px': round(max(py) - min(py), 1),
        'screen_width_px': round(max(px) - min(px), 1),
        'bottom_px': [round(bottom[0], 1), round(bottom[1], 1)],
        'top_px': [round(top[0], 1), round(top[1], 1)],
        'face_centers_px': faces,
        'source_hex': part.get('source_hex'),
    }


def dominant_at(image: np.ndarray, x: float, y: float, radius: int = 3) -> dict | None:
    """在某屏幕点周围取 (2r+1)² 邻域的主导像素色。"""
    height, width = image.shape[0], image.shape[1]
    xa, xb = max(0, int(x) - radius), min(width, int(x) + radius + 1)
    ya, yb = max(0, int(y) - radius), min(height, int(y) + radius + 1)
    if xb <= xa or yb <= ya:
        return None
    region = image[ya:yb, xa:xb].reshape(-1, 3)
    packed = (region[:, 0].astype(np.int32) << 16) | (region[:, 1].astype(np.int32) << 8) | region[:, 2]
    values, counts = np.unique(packed, return_counts=True)
    code = int(values[int(np.argmax(counts))])
    return {'hex': '#{:02x}{:02x}{:02x}'.format((code >> 16) & 0xFF, (code >> 8) & 0xFF, code & 0xFF),
            'pixels': int(counts.max()), 'of': int(region.shape[0])}


def column_profile(image: np.ndarray, bbox: list[float], x_px: int) -> dict:
    """在部件 bbox 的纵向范围内，统计某一列上出现的主导色（自证「这一列上看到的是什么」）。"""
    x0, y0, x1, y1 = (int(v) for v in bbox)
    x_px = max(0, min(image.shape[1] - 1, x_px))
    ya, yb = max(0, y0), min(image.shape[0], y1 + 1)
    if yb <= ya:
        return {}
    column = image[ya:yb, x_px]
    packed = (column[:, 0].astype(np.int32) << 16) | (column[:, 1].astype(np.int32) << 8) | column[:, 2]
    values, counts = np.unique(packed, return_counts=True)
    out = {}
    for index in np.argsort(-counts)[:4]:
        code = int(values[index])
        out['#{:02x}{:02x}{:02x}'.format((code >> 16) & 0xFF, (code >> 8) & 0xFF, code & 0xFF)] = int(counts[index])
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='spikes/n2-appearance')
    parser.add_argument('--shot', required=True)
    parser.add_argument('--reading', required=True, help='readback 里的读数键（如 indoor_side_daily）')
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
        entry = box_screen(part, placement, camera, width, height)
        # 画面上的**实测色**：取盒 bbox 内几个采样点（面中心 + bbox 中心 + 纵向中轴列）
        samples = {}
        for face, (cx, cy) in entry['face_centers_px'].items():
            samples[face] = dominant_at(image, cx, cy)
        x0, y0, x1, y1 = entry['screen_bbox']
        samples['bbox_center'] = dominant_at(image, (x0 + x1) / 2, (y0 + y1) / 2)
        entry['screen_color_samples'] = samples
        entry['column_profile_at_center_x'] = column_profile(image, entry['screen_bbox'], int((x0 + x1) / 2))
        probe.append(entry)

    by_part = {entry['part']: entry for entry in probe}
    ordering = {}
    if 'hair' in by_part and 'torso' in by_part and 'coat' in by_part and 'leg_l' in by_part:
        ordering = {
            'note': '屏幕纵向次序（y 越大越靠下；低模盒即轮廓）',
            'hair_bottom_y_px': by_part['hair']['bottom_px'][1],
            'torso_top_y_px': by_part['torso']['top_px'][1],
            'hair_below_shoulder_px': round(by_part['hair']['bottom_px'][1] - by_part['torso']['top_px'][1], 1),
            'hair_height_px': by_part['hair']['screen_height_px'],
            'coat_bottom_y_px': by_part['coat']['bottom_px'][1],
            'leg_bottom_y_px': by_part['leg_l']['bottom_px'][1],
            'leg_visible_below_hem_px': round(by_part['leg_l']['bottom_px'][1] - by_part['coat']['bottom_px'][1], 1),
            'hair_wide_vs_torso_px': round(by_part['hair']['screen_width_px'] - by_part['torso']['screen_width_px'], 1),
            'hair_wide_vs_coat_px': round(by_part['hair']['screen_width_px'] - by_part['coat']['screen_width_px'], 1),
        }

    document = {
        'shot': f'{args.shot}.png',
        'reading': args.reading,
        'npc': npc,
        'placement_m': placement,
        'camera': {key: camera[key] for key in ('position', 'quaternion', 'fov', 'near', 'far', 'aspect')},
        'image_size': [width, height],
        'note': '部件盒 8 角由实测 cameraReport() 投影；像素色为 PNG 真实值（低模盒即轮廓）',
        'silhouette_probe': probe,
        'screen_ordering': ordering,
    }
    (root / 'readback' / f'n2-r4-silhouette-probe-{args.shot}.json').write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(f"== {args.shot} (reading={args.reading}) camera={[round(v, 2) for v in camera['position']]} ==")
    for entry in probe:
        print(f"  {entry['part']:<6} size={entry['size']} offset={entry['local_offset']}"
              f" bbox={entry['screen_bbox']} h={entry['screen_height_px']}px w={entry['screen_width_px']}px")
        print(f"         面上实测色: " + ' '.join(
            f"{face}={sample['hex']}" for face, sample in entry['screen_color_samples'].items() if sample))
    if ordering:
        print('  --- 屏幕纵向次序 ---')
        for key, value in ordering.items():
            print(f"    {key} = {value}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
