#!/usr/bin/env node
/**
 * `AC-E-2a` / `AC-E-2d` 的机读锚 + **手算样例复算**（`01a §0.6`）。
 *
 * 运行：`cd <web> && node <ws>/v0/spikes/n5-asset/binding_probe.mjs [--out <dir>]`
 *
 * 口径（`01a §0.6` 写死，**不得**改排序键 / 分隔符 / 尾换行）：
 *   asset_bundle_sha256 = sha256( "\n".join(sorted(`${asset_id}:${converted_sha256}`)) )   UTF-8，**无尾换行**
 *   binding_set_sha256  = sha256( "\n".join(sorted(`${binding_id}:${glb_url}:${asset_version}`)) ) UTF-8，**无尾换行**
 *
 * 本探针**同时**复算 §0.6 的两条假数据样例：与冻结期望值前 16 位逐位一致 ⇒ 口径实现正确；
 * 不一致 ⇒ **实现口径不一致**（排序键 / 分隔符 / 尾换行 / 大小写），据此归因。
 */

import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { BINDINGS, bindingSetLines } from '../../02_source/v0_skeleton/web/src/scene/asset_binding.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const outIdx = argv.indexOf('--out');
const OUT = resolve(outIdx >= 0 ? argv[outIdx + 1] : `${HERE}/readback`);
const WEB = resolve(HERE, '../../02_source/v0_skeleton/web');

const sha256 = (text) => createHash('sha256').update(Buffer.from(text, 'utf8')).digest('hex');

// ---- 冻结期望（`01a §0.6`，已由 PM 亲跑复核） ----
const FROZEN_SAMPLES = [
  {
    label: 'asset_bundle_sha256',
    lines: [
      'demo_asset_a:1111111111111111111111111111111111111111111111111111111111111111',
      'demo_asset_b:2222222222222222222222222222222222222222222222222222222222222222',
    ],
    expected_prefix16: '158539f9eb553c7b',
  },
  {
    label: 'binding_set_sha256',
    lines: [
      'npc_generic:assets/character/generic.glb:0.1.0',
      'xuqin_default:assets/character/xuqin.glb:1.0.0',
    ],
    expected_prefix16: '6a1e9adc9d8ec9c7',
  },
];

const sampleResults = FROZEN_SAMPLES.map((s) => {
  const digest = sha256([...s.lines].sort().join('\n'));
  return {
    label: s.label,
    input_lines_sorted: [...s.lines].sort(),
    digest,
    prefix16: digest.slice(0, 16),
    expected_prefix16: s.expected_prefix16,
    matches: digest.slice(0, 16) === s.expected_prefix16,
  };
});

// ---- 真实读数 ----
const provenance = JSON.parse(readFileSync(`${WEB}/assets/provenance.json`, 'utf8'));
const assetLines = provenance.assets
  .map((a) => `${a.asset_id}:${a.converted_sha256}`)
  .sort();
const bindingLines = bindingSetLines();

const assetDigest = sha256(assetLines.join('\n'));
const bindingDigest = sha256(bindingLines.join('\n'));

const payload = {
  schema_version: 'n5-binding-probe/1',
  generated_by: 'artisan',
  generated_at_epoch: Math.floor(Date.now() / 1000),
  web_dir: WEB,
  /** §0.6 手算样例复算（口径自证） */
  frozen_sample_recompute: sampleResults,
  frozen_samples_all_match: sampleResults.every((r) => r.matches),
  /** 真实读数 */
  asset_bundle: {
    line_count: assetLines.length,
    lines: assetLines,
    sha256: assetDigest,
    prefix12: assetDigest.slice(0, 12),
  },
  binding_set: {
    line_count: bindingLines.length,
    lines: bindingLines,
    sha256: bindingDigest,
    prefix8: bindingDigest.slice(0, 8),
  },
  bindings: BINDINGS.map((b) => ({
    binding_id: b.binding_id,
    glb_url: b.glb_url,
    asset_version: b.asset_version,
    glb_on_disk: (() => {
      try {
        readFileSync(`${WEB}/${b.glb_url}`);
        return true;
      } catch {
        return false;
      }
    })(),
  })),
  /** `AC-A-2b` 四段式 tag 的取值面 */
  tag_parts: {
    commit_short7: readCommit(),
    asset_bundle_prefix12: assetDigest.slice(0, 12),
    binding_set_prefix8: bindingDigest.slice(0, 8),
    config_hash_prefix8: null,
  },
};

function readCommit() {
  try {
    return readFileSync(resolve(HERE, '../../../..', '.git/HEAD'), 'utf8').trim().slice(0, 7);
  } catch {
    return null;
  }
}

mkdirSync(OUT, { recursive: true });
writeFileSync(`${OUT}/binding_report.json`, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
process.stdout.write(`binding_probe: wrote ${OUT}/binding_report.json\n`);
for (const r of sampleResults) {
  process.stdout.write(`binding_probe: frozen sample ${r.label} ${r.matches ? 'MATCH' : 'MISMATCH'} `
    + `expect=${r.expected_prefix16} actual=${r.prefix16}\n`);
}
process.stdout.write(`binding_probe: asset_bundle_sha256=${assetDigest.slice(0, 16)} (${assetLines.length} lines)\n`);
process.stdout.write(`binding_probe: binding_set_sha256=${bindingDigest.slice(0, 16)} (${bindingLines.length} lines)\n`);
process.exit(payload.frozen_samples_all_match ? 0 : 1);
