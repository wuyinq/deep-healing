#!/usr/bin/env python3
"""F-8 取证（N2-r2 / spike 专用，**非交付面**）：AC-10 资产管线阻塞的**先后顺序**。

r1 的 `03` / `06` 记的两条阻塞（循环 `pack.sig` 依赖 / 许可 default-deny）**只能**出自
**自建 probe manifest**。本脚本复现「更靠前」的那条阻塞，并把 probe manifest 一并留档：

  ① 交付 manifest（`districts/xingfu-xiaoqu-xuqin/assets/manifest.json`，条目用 `id`）
     ⇒ `verify_asset_pack.py:110` 抛 `KeyError: 'asset_id'`（**最早**的阻塞）；
  ② 把 `id` 改名为 `asset_id` 后（= probe manifest）⇒ 才轮到 r1 记录的那两条。

用法：
    python3 spikes/n2-appearance/n2-ac10-probe.py --out spikes/n2-appearance
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
SOURCE = WS / '02_source'
PACK_REL = Path('v0_skeleton/districts/xingfu-xiaoqu-xuqin')
LICENSE_REL = Path('asset.license.table.data.json')


def run_verifier(manifest: Path) -> tuple[int, str]:
    command = [sys.executable, 'tools/verify_asset_pack.py',
               '--pack', str(PACK_REL), '--manifest', str(manifest),
               '--license-table', f'../{LICENSE_REL}']
    completed = subprocess.run(command, cwd=str(SOURCE / 'v0_skeleton'),
                               capture_output=True, text=True, timeout=300)
    return completed.returncode, (completed.stdout or '') + (completed.stderr or '')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='spikes/n2-appearance')
    args = parser.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = WS / out
    (out / 'readback').mkdir(parents=True, exist_ok=True)

    delivery_manifest = SOURCE / PACK_REL / 'assets' / 'manifest.json'
    code_a, text_a = run_verifier(delivery_manifest)
    line_a = [line for line in text_a.splitlines() if 'Error' in line or 'error' in line][-1:]

    # ② probe manifest：只把 `assets[].id` 改名为 `assets[].asset_id`（其余逐字不变）
    document = json.loads(delivery_manifest.read_text(encoding='utf-8'))
    renamed = 0
    for asset in document.get('assets', []):
        if 'id' in asset and 'asset_id' not in asset:
            asset['asset_id'] = asset.pop('id')
            renamed += 1
    probe_path = out / 'readback' / 'n2-ac10-probe-manifest.json'
    probe_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    code_b, text_b = run_verifier(probe_path)
    line_b = [line for line in text_b.splitlines() if 'REJECT' in line or 'Error' in line or 'error' in line][-3:]

    report = {
        'delivery_manifest': str(delivery_manifest.relative_to(WS)),
        'probe_manifest': str(probe_path.relative_to(WS)),
        'probe_manifest_change': f'assets[].id -> assets[].asset_id（{renamed} 条；其余逐字不变）',
        'reading_delivery_manifest': {'exit': code_a, 'last_error_line': line_a},
        'reading_probe_manifest': {'exit': code_b, 'last_error_lines': line_b},
    }
    (out / 'readback' / 'n2-ac10-probe.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
