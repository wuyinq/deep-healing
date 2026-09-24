#!/usr/bin/env python3
"""N2-r2 负例组（**全部在 /tmp 整树副本上做；交付树零改动**）。

覆盖：r1 的 8 条（不得回归）+ 本轮新增 N-2b / N-3b / N-4b / N-9 / N-10。

用法：python3 /tmp/n2_negatives_r2.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

WS = Path('/Users/wooyinq/.hermes/profiles/lanova/dev_team_workspace/'
          'REQ-20260924-002-deephealing-xuqin-appearance')
SRC = WS / '02_source'
NEG = Path(f'/tmp/n2-r2-neg-{int(time.time())}')
NPC_REL = Path('v0_skeleton/districts/xingfu-xiaoqu-xuqin/npcs/npc-006.json')
MANIFEST_REL = Path('v0_skeleton/districts/xingfu-xiaoqu-xuqin/assets/manifest.json')
XUQIN_DIR = Path('v0_skeleton/districts/xingfu-xiaoqu-xuqin')
IGNORE = shutil.ignore_patterns('node_modules', '__pycache__', '.pytest_cache', 'dist')

RESULTS: list[dict] = []


def clone(name: str) -> Path:
    """整树副本（`02_source` 一份）+ `node_modules` 软链（`scene_assert` 需要）。"""
    root = NEG / name
    target = root / '02_source'
    shutil.copytree(SRC, target, symlinks=True, ignore=IGNORE)
    os.symlink(WS / 'node_modules', root / 'node_modules')
    return target


def mutate_json(path: Path, mutate) -> None:
    document = json.loads(path.read_text(encoding='utf-8'))
    mutate(document)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def checks_of(payload: dict | None) -> dict:
    return (payload or {}).get('checks') or {}


def summary_of(out: str) -> str:
    lines = [line for line in out.strip().splitlines() if line.startswith('scene_assert:')]
    return ' | '.join(lines) if lines else out.strip().splitlines()[-1:][0] if out.strip() else ''


def run(command: list[str], cwd: Path, timeout: int = 300) -> tuple[int, str]:
    completed = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return completed.returncode, (completed.stdout or '') + (completed.stderr or '')


def record(case: str, expected: str, exit_code: int, ok: bool, reading: str) -> None:
    RESULTS.append({'case': case, 'expected': expected, 'exit': exit_code,
                    'fired': bool(ok), 'reading': reading[:400]})
    print(f'  {"OK " if ok else "!! "} {case}: exit={exit_code} fired={ok} :: {reading[:150]}')


def verifier(tree: Path) -> tuple[int, dict | None, str]:
    code, out = run(['python3', 'v0_skeleton/tools/verify_npc_appearance.py', '--root', '.'], tree)
    payload = None
    for line in reversed(out.splitlines()):
        if line.startswith('{'):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = None
            break
    return code, payload, out


def scene_assert(tree: Path) -> tuple[int, str]:
    return run(['node', 'scripts/scene_assert.mjs'], tree / 'v0_skeleton' / 'web')


print(f'workdir = {NEG}')
NEG.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────── 基线（交付树）
code, payload, _ = verifier(SRC)
record('baseline_delivery_tree_verifier', 'exit 0 / appearance_ok+probe_ok', code,
       code == 0 and payload is not None and payload.get('appearance_ok') and payload.get('probe_ok'),
       f"appearance_ok={payload.get('appearance_ok')} probe_ok={payload.get('probe_ok')} "
       f"probes={len(payload.get('probe') or [])}")
code, out = scene_assert(SRC)
record('baseline_delivery_tree_scene_assert', 'exit 0', code, code == 0,
       out.strip().splitlines()[-1] if out.strip() else '')

# ─────────────────────────────────────────────── N-2b：build="quadruped"（F-2）
tree = clone('N-2b_build_quadruped')
mutate_json(tree / NPC_REL, lambda d: d['appearance']['build'].update({'value': 'quadruped'}))
code, payload, out = verifier(tree)
reading = json.dumps(checks_of(payload).get('schema_valid', {}).get('failures', [])[:1], ensure_ascii=False) if payload else out[:200]
record('N-2b_build_quadruped', 'verifier exit != 0 且结构化 JSON 报 build 非法', code,
       code != 0 and payload is not None and bool(checks_of(payload).get('schema_valid', {}).get('failures')), reading)

# ─────────────────────────────────────────────── N-3b：删 mask（states 仍声明 masked）（F-3）
tree = clone('N-3b_mask_missing')
mutate_json(tree / NPC_REL, lambda d: d['appearance'].pop('mask'))
code, payload, out = verifier(tree)
reading = json.dumps(checks_of(payload).get('schema_valid', {}).get('failures', [])[:1], ensure_ascii=False) if payload else out[:200]
record('N-3b_mask_missing_verifier', 'verifier exit != 0 且结构化 JSON 报 mask 必填', code,
       code != 0 and payload is not None and bool(checks_of(payload).get('schema_valid', {}).get('failures')), reading)
code, out = scene_assert(tree)
crash = 'TypeError' in out or 'ReferenceError' in out
degrade_line = [line for line in out.splitlines() if 'degrades_explicitly' in line]
record('N-3b_mask_missing_scene_assert', '不崩（无 traceback）且显式降级断言在场', code,
       (not crash) and bool(summary_of(out)) and bool(degrade_line),
       f"crash={crash} | {summary_of(out)} | {(degrade_line[0] if degrade_line else 'NO DEGRADE LINE')[:170]}")

# ─────────────────────────────────────────────── N-4b：mask.number = "9"（字符串）（F-4）
tree = clone('N-4b_mask_number_string')
mutate_json(tree / NPC_REL, lambda d: d['appearance']['mask'].__setitem__('number', '9'))
code, payload, out = verifier(tree)
reading = json.dumps((payload or {}).get('checks', {}).get('xuqin_required_fields', {}).get('missing', [])[:1],
                     ensure_ascii=False) if payload else out[:200]
record('N-4b_mask_number_string', '结构化拒收（非 0 + JSON，无 traceback）', code,
       code != 0 and payload is not None and 'Traceback' not in out, reading)

# ─────────────────────────────────────────────── N-9：三处锚点缺失（F-4）
tree = clone('N-9_anchors_missing')
def drop_anchors(document: dict) -> None:
    document['appearance']['eyes'].pop('color')
    document['appearance']['hair']['color'].pop('design_fill')
    document['appearance'].pop('mask')
mutate_json(tree / NPC_REL, drop_anchors)
code, payload, out = verifier(tree)
record('N-9_three_anchors_missing', 'EXIT_BAD_INJECTION(3) + 结构化 JSON（无 traceback）', code,
       code == 3 and payload is not None and 'Traceback' not in out,
       json.dumps(payload, ensure_ascii=False)[:220] if payload else out[:200])

# ─────────────────────────────────────────────── N-10：非 eyes 部件材质色偏差（两读法一致）（F-5）
tree = clone('N-10_arm_l_material_tamper')
world = tree / 'v0_skeleton/web/src/scene/world.ts'
text = world.read_text(encoding='utf-8')
needle = '          healingMaterial(part.source_hex, options.worldview[currentReading]),'
assert needle in text, 'N-10 注入锚点缺失（world.ts 部件材质构造点）'
text = text.replace(needle,
                    '          healingMaterial(part.part === \'arm_l\' ? \'#000000\' : part.source_hex,'
                    ' options.worldview[currentReading]),', 1)
world.write_text(text, encoding='utf-8')
code, out = scene_assert(tree)
fails = [line for line in out.splitlines() if line.startswith('FAIL')]
record('N-10_arm_l_material_tamper', 'character_material_hex_recomputable 必红', code,
       any('character_material_hex_recomputable' in line for line in fails),
       ' | '.join(fails[:2]) if fails else out.strip().splitlines()[-1])

# ─────────────────────────────────────────────── r1 的 8 条（不得回归）
# 1) 删 eyes.color ⇒ schema_valid 必红
tree = clone('R1-1_remove_eyes_color')
mutate_json(tree / NPC_REL, lambda d: d['appearance']['eyes'].pop('color'))
code, payload, out = verifier(tree)
record('R1-1_remove_eyes_color', 'schema_valid 必红', code,
       code != 0 and payload is not None and not checks_of(payload)['schema_valid']['pass'],
       json.dumps(checks_of(payload)['schema_valid']['failures'][:1], ensure_ascii=False) if payload else '')

# 2) 去掉 hair.color 的 design_fill ⇒ schema_valid 必红
tree = clone('R1-2_drop_hair_design_fill')
mutate_json(tree / NPC_REL, lambda d: d['appearance']['hair']['color'].pop('design_fill'))
code, payload, out = verifier(tree)
record('R1-2_drop_hair_design_fill', 'schema_valid 必红', code,
       code != 0 and payload is not None and not checks_of(payload)['schema_valid']['pass'],
       json.dumps(checks_of(payload)['schema_valid']['failures'][:1], ensure_ascii=False) if payload else '')

# 3) 伪造 CHR-99 ⇒ source_facts_resolve 必红
tree = clone('R1-3_forged_chr_99')
mutate_json(tree / NPC_REL, lambda d: d['appearance']['eyes']['color'].update({'source_facts': ['CHR-99']}))
code, payload, out = verifier(tree)
record('R1-3_forged_chr_99', 'source_facts_resolve 必红', code,
       code != 0 and payload is not None and not checks_of(payload)['source_facts_resolve']['pass'],
       str(checks_of(payload).get('source_facts_resolve', {}).get('unresolved', [])[:1]))

# 4) mask.number 改 9 ⇒ xuqin_required_fields 必红（校验器）
tree = clone('R1-4_mask_number_9')
mutate_json(tree / NPC_REL, lambda d: d['appearance']['mask']['number'].update({'value': '9'}))
code, payload, out = verifier(tree)
record('R1-4_mask_number_9', 'xuqin_required_fields 必红', code,
       code != 0 and payload is not None and not checks_of(payload)['xuqin_required_fields']['pass'],
       str(checks_of(payload).get('xuqin_required_fields', {}).get('missing', [])[:1]))

# 5) 顶层 source_fact_map 塞 appearance.* 新键 ⇒ 假绿陷阱必红
tree = clone('R1-5_top_level_appearance_key')
mutate_json(tree / NPC_REL, lambda d: d['source_fact_map'].update({'appearance.hair': ['CHR-22']}))
code, payload, out = verifier(tree)
record('R1-5_top_level_appearance_key', 'appearance_provenance_is_nested 必红', code,
       code != 0 and payload is not None and not checks_of(payload)['appearance_provenance_is_nested']['pass'],
       str(checks_of(payload).get('appearance_provenance_is_nested', {}).get('problems', [])[:1]))

# 6) 环境色板 S=60 ⇒ aesthetic_check 必红
tree = clone('R1-6_env_palette_saturation')
def bump_saturation(document: dict) -> None:
    for asset in document['assets']:
        if 'palette' in asset:
            asset['palette']['saturation_pct'] = 60
            break
mutate_json(tree / MANIFEST_REL, bump_saturation)
code, out = run(['python3', 'v0_skeleton/tools/aesthetic_check.py',
                 str(XUQIN_DIR / 'assets/manifest.json')], tree)
record('R1-6_env_palette_saturation', 'aesthetic_check 必红', code, code != 0,
       ' '.join(line for line in out.splitlines() if 'E_AESTHETIC' in line)[:200])

# 7) character.ts 内出现角色锚点 hex ⇒ scene_assert 静态判据必红
tree = clone('R1-7_ts_anchor_hex')
character = tree / 'v0_skeleton/web/src/scene/character.ts'
character.write_text(character.read_text(encoding='utf-8')
                     .replace("const NEUTRAL_EYES = '#4b4239';",
                              "const NEUTRAL_EYES = '#4b4239'; // inject #8b1919", 1), encoding='utf-8')
code, out = scene_assert(tree)
fails = [line for line in out.splitlines() if line.startswith('FAIL')]
record('R1-7_ts_anchor_hex', 'character_ts_has_no_anchor_hex_literal 必红', code,
       any('character_ts_has_no_anchor_hex_literal' in line for line in fails),
       ' | '.join(fails[:2]) if fails else out.strip().splitlines()[-1])

# 8) appearance 内出现引号包起来的正文长段 ⇒ scan_ip_boundary 必命中
tree = clone('R1-8_verbatim_paragraph')
LONG = '\u201c' + '\u7532' * 61 + '\u201d'
mutate_json(tree / NPC_REL,
            lambda d: d['appearance']['hair']['color'].update({'design_note': LONG}))
code, out = run(['python3', 'v0_skeleton/tools/scan_ip_boundary.py', '--root', '.'], tree)
record('R1-8_verbatim_paragraph', 'scan_ip_boundary 必命中', code, code != 0,
       ' '.join(line for line in out.splitlines() if 'verbatim_body_paragraph' in line)[:200])

# ─────────────────────────────────────────────── 汇总
summary = {'workdir': str(NEG), 'total': len(RESULTS),
           'fired': sum(1 for item in RESULTS if item['fired']),
           'not_fired': [item['case'] for item in RESULTS if not item['fired']],
           'cases': RESULTS}
(NEG / 'n2-r2-negatives.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
                                          encoding='utf-8')
print(f"\nall_fired={summary['fired']}/{summary['total']}  not_fired={summary['not_fired']}")
sys.exit(0 if not summary['not_fired'] else 1)
