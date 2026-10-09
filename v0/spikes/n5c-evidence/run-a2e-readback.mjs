#!/usr/bin/env node
/** `AC-A-2e` · **运行期读回**绑定表 ⇒ 复算 `binding_set_sha256` 前 8，断言与 A-2b tag 第三段一致。 */
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const READBACK = join(HERE, 'readback');
const a = JSON.parse(readFileSync(join(READBACK, 'a-evidence-reading.json'), 'utf8'));
const ie = JSON.parse(readFileSync(join(READBACK, 'i-evidence-reading.json'), 'utf8'));

const tag = a.tag;
const tagSegment3 = tag.split('-')[2];
const linesFromPage = ie.normal_world.binding.binding_set_lines;
const recomputed = createHash('sha256').update(linesFromPage.slice().sort().join('\n'), 'utf8').digest('hex');

const reading = {
  task: 'a2e-runtime-binding-readback',
  page_url: 'http://127.0.0.1:8850/?pack=xingfu-xiaoqu-xuqin（真浏览器 1440×900）',
  source: 'i-evidence-reading.json :: normal_world.binding.binding_set_lines（**从运行页面读回**，非构建期常量）',
  binding_set_lines: linesFromPage,
  recomputed_sha256: recomputed,
  recomputed_prefix8: recomputed.slice(0, 8),
  tag,
  tag_segment3: tagSegment3,
  match: recomputed.slice(0, 8) === tagSegment3,
  note: '页面的 bindingReport() 不自行算哈希（其 binding_set_sha256 字段为 null）⇒ 哈希由取证侧按写死定义复算',
};
writeFileSync(join(READBACK, 'a2e-runtime-binding-readback.json'), `${JSON.stringify(reading, null, 2)}\n`);
process.stdout.write(`A2E ${JSON.stringify({ tag, tag_segment3: tagSegment3, recomputed_prefix8: reading.recomputed_prefix8,
  match: reading.match })}\n`);
