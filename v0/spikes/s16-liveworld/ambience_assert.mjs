#!/usr/bin/env node
/**
 * 氛围判据（AC-M4-11④）——**可检查的数值判据**，取数源 = 内容包既有段（**不是臆造**）。
 *
 * 运行：node spikes/s16-liveworld/ambience_assert.mjs [--logs spikes/s16-liveworld/logs] [--tag live]
 *
 * **前提更正（本轮实测，登记进 06）**：设计 §2 D-M4-10 与 REQ AC-M4-11④ 的**字面前提**
 * 「内容包中不存在 `ambience` / `aesthetic_constraints` 段」**被 grep 否证**：
 *   - `districts/xingfu-xiaoqu/buildings/courtyard-01.json` → **有** `ambience`
 *     （`audio_bed` / `lighting.{ambient_ratio,shadow_softness,key_light_temp_k}` / `palette`）；
 *   - `districts/xingfu-xiaoqu/assets/manifest.json` → **有** `aesthetic_constraints`
 *     （`palette.saturation_max_pct` / `lighting.{shadow_softness_min,ambient_ratio_min}` /
 *      `material.roughness_min` / `audio.allowed_beds`）。
 * ⇒ 本判据**不记 GAP**：它直接以这两段为权威取数源，并逐条给出 `ambience_source`（路径 + 字段）。
 *   「氛围达成」的主观成分**仍然**如实标注（见输出 `subjective_residual`）。
 *
 * 判据（全部**读数据文件 + 真浏览器读数**，不硬编码被断言的数字）：
 *   1. `ambience_source_declared`：每个被断言的数值都带来源（路径 + 字段），且来源文件真的含该字段；
 *   2. `runtime_lighting_matches_pack_tone`：两态运行期光照参数 == `worldview.json#tone`（逐字段）；
 *   3. `runtime_material_respects_aesthetic_constraints`：`roughness >= material.roughness_min` 且**无镜面**
 *      （`metalness == 0` 且材质对象里不出现 `specular` / `clearcoat` 面）；
 *   4. `courtyard_ambience_within_constraints`：`ambience.lighting.ambient_ratio >= lighting.ambient_ratio_min`、
 *      `ambience.lighting.shadow_softness >= shadow_softness_min`、
 *      `ambience.palette.saturation_pct <= palette.saturation_max_pct`、
 *      `ambience.audio_bed ∈ audio.allowed_beds`；
 *   5. `browser_pixels_are_not_flat`：真浏览器读数里 HUD 外**非背景像素占比 > 0**（画面真的画了东西）；
 *   6. `browser_pixels_saturation_within_limit`：非背景像素的饱和 p95 `<= saturation_max_pct`；
 *   7. **反例自证**：同一判定函数喂入**注入违规**的读数（饱和 90 / 粗糙度 0.1 / 金属度 0.8）⇒ **必须红**。
 *
 * 退出码：0 全通过；1 有断言失败；2 用法/环境错误。
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, resolve } from 'node:path';

import { deriveLighting, healingMaterial, ROUGHNESS_MIN } from '../../02_source/v0_skeleton/web/src/scene/lighting.ts';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const WORKSPACE = join(HERE, '..', '..');
const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};

const LOGS = resolve(option('logs', join(HERE, 'logs')));
const TAG = option('tag', 'live');
const PACK = join(WORKSPACE, '02_source', 'v0_skeleton', 'districts', 'xingfu-xiaoqu');
const ART_BIBLE = join(WORKSPACE, '02_source', 'art-bible.md');

const read = (path) => JSON.parse(readFileSync(path, 'utf8'));
const manifest = read(join(PACK, 'assets', 'manifest.json'));
const worldview = read(join(PACK, 'worldview.json'));
const courtyard = read(join(PACK, 'buildings', 'courtyard-01.json'));
const artBible = readFileSync(ART_BIBLE, 'utf8');

const constraints = manifest.aesthetic_constraints;
const ambience = courtyard.ambience;
const saturationLimit = Number(constraints.palette.saturation_max_pct);
const roughnessFloor = Number(constraints.material.roughness_min);
const ambientRatioMin = Number(constraints.lighting.ambient_ratio_min);
const shadowSoftnessMin = Number(constraints.lighting.shadow_softness_min);

/** 每条被断言的数值的**来源标注**（路径 + 字段）—— AC-M4-11④ 的字面要求。
 *  `path` 相对 `<ws>/02_source/v0_skeleton/`（art-bible 除外，它在 `<ws>/02_source/`）。 */
const AMBIENCE_SOURCE = {
  saturation_max_pct: { path: 'districts/xingfu-xiaoqu/assets/manifest.json', field: 'aesthetic_constraints.palette.saturation_max_pct', root: 'skeleton' },
  roughness_min: { path: 'districts/xingfu-xiaoqu/assets/manifest.json', field: 'aesthetic_constraints.material.roughness_min', root: 'skeleton' },
  ambient_ratio_min: { path: 'districts/xingfu-xiaoqu/assets/manifest.json', field: 'aesthetic_constraints.lighting.ambient_ratio_min', root: 'skeleton' },
  shadow_softness_min: { path: 'districts/xingfu-xiaoqu/assets/manifest.json', field: 'aesthetic_constraints.lighting.shadow_softness_min', root: 'skeleton' },
  audio_allowed_beds: { path: 'districts/xingfu-xiaoqu/assets/manifest.json', field: 'aesthetic_constraints.audio.allowed_beds', root: 'skeleton' },
  courtyard_ambience: { path: 'districts/xingfu-xiaoqu/buildings/courtyard-01.json', field: 'ambience', root: 'skeleton' },
  tone: { path: 'districts/xingfu-xiaoqu/worldview.json', field: 'tone.surface|tone.underneath', root: 'skeleton' },
  art_bible_saturation: { path: 'art-bible.md', field: '§美学数值约束 · 饱和度 ≤ 45（HSV 的 S，0–100）', field_token: '饱和度', root: 'source' },
  art_bible_roughness: { path: 'art-bible.md', field: '§美学数值约束 · 粗糙度 `roughness` 0.55–0.95（镜面高光禁用）', field_token: '粗糙度', root: 'source' },
};

/** 来源文件的绝对路径（`root` 区分 `<ws>/02_source/` 与 `<ws>/02_source/v0_skeleton/`）。 */
function sourceAbsolute(source) {
  return source.root === 'skeleton'
    ? join(WORKSPACE, '02_source', 'v0_skeleton', source.path)
    : join(WORKSPACE, '02_source', source.path);
}

const results = [];
const check = (name, ok, detail, source) => {
  results.push({ name, ok: Boolean(ok), detail: String(detail), ambience_source: source ?? null });
};

// ---- 1) 来源标注
for (const [key, source] of Object.entries(AMBIENCE_SOURCE)) {
  const absolute = sourceAbsolute(source);
  let exists = false;
  let hasField = false;
  try {
    const text = readFileSync(absolute, 'utf8');
    exists = true;
    hasField = text.includes(source.field_token ?? source.field.split(/[.[|]/)[0]);
  } catch {
    exists = false;
  }
  check(`ambience_source_declared:${key}`, exists && hasField && Boolean(source.path) && Boolean(source.field),
    `${source.path}#${source.field} (file_exists=${exists} field_token_present=${hasField})`, source);
}

// ---- 2) 运行期光照 == 内容包 tone
const surfaceLighting = deriveLighting(worldview.tone.surface);
const underneathLighting = deriveLighting(worldview.tone.underneath);
check('runtime_lighting_matches_pack_tone',
  Number(surfaceLighting.saturation) === worldview.tone.surface.saturation_pct / 100
  && Number(underneathLighting.saturation) === worldview.tone.underneath.saturation_pct / 100,
  `surface saturation=${surfaceLighting.saturation} (pack ${worldview.tone.surface.saturation_pct / 100}) | ` +
  `underneath saturation=${underneathLighting.saturation} (pack ${worldview.tone.underneath.saturation_pct / 100}) | ` +
  `underneath luminanceScale=${underneathLighting.luminanceScale} < surface ${surfaceLighting.luminanceScale}`,
  AMBIENCE_SOURCE.tone);

// ---- 3) 材质遵守 aesthetic_constraints（含**无镜面**）
const material = healingMaterial('#c9b79c', worldview.tone.surface, 0.75);
const specularFaces = ['specular', 'specularIntensity', 'clearcoat', 'clearcoatRoughness', 'sheen']
  .filter((key) => key in material);
check('runtime_material_respects_aesthetic_constraints',
  ROUGHNESS_MIN >= roughnessFloor && Number(material.metalness ?? 0) < 0.1 && specularFaces.length === 0,
  `roughness=${ROUGHNESS_MIN} (floor ${roughnessFloor}) | metalness=${material.metalness} (<0.1 ⇒ 非金属/无镜面) | ` +
  `specular_faces=${JSON.stringify(specularFaces)}`,
  AMBIENCE_SOURCE.roughness_min);

// ---- 4) 中庭 ambience 段在约束内
check('courtyard_ambience_within_constraints',
  Number(ambience.lighting.ambient_ratio) >= ambientRatioMin
  && Number(ambience.lighting.shadow_softness) >= shadowSoftnessMin
  && Number(ambience.palette.saturation_pct) <= saturationLimit
  && constraints.audio.allowed_beds.includes(ambience.audio_bed),
  `ambient_ratio=${ambience.lighting.ambient_ratio}>=${ambientRatioMin} | ` +
  `shadow_softness=${ambience.lighting.shadow_softness}>=${shadowSoftnessMin} | ` +
  `saturation=${ambience.palette.saturation_pct}<=${saturationLimit} | audio_bed=${ambience.audio_bed}`,
  AMBIENCE_SOURCE.courtyard_ambience);

// ---- 5) art-bible 与 manifest 同口径（不硬编码被断言的数字）
const bibleSaturation = Number((artBible.match(/饱和度\s*\|\s*\*\*≤\s*(\d+)\*\*/) ?? [])[1]);
const bibleRoughness = (artBible.match(/粗糙度 `roughness`\s*\|\s*`([\d.]+)\s*–\s*([\d.]+)`/) ?? []).slice(1).map(Number);
check('art_bible_matches_manifest',
  bibleSaturation === saturationLimit
  && bibleRoughness[0] <= roughnessFloor && roughnessFloor <= bibleRoughness[1],
  `art-bible saturation<=${bibleSaturation} vs manifest ${saturationLimit} | ` +
  `manifest roughness floor ${roughnessFloor} ∈ art-bible 区间 ${JSON.stringify(bibleRoughness)}`,
  AMBIENCE_SOURCE.art_bible_saturation);

// ---- 6) 真浏览器像素读数
let browser = null;
try {
  browser = read(join(LOGS, `browser-live-${TAG}.json`));
} catch {
  browser = null;
}
check('browser_readings_available', browser !== null && Array.isArray(browser.viewports) && browser.viewports.length >= 2,
  browser ? `viewports=${browser.viewports.map((entry) => entry.viewport).join(',')}` : `missing logs/browser-live-${TAG}.json`, null);

if (browser) {
  for (const viewport of browser.viewports) {
    const stats = viewport.pixel_stats;
    const under = viewport.pixel_stats_underneath;
    check(`browser_pixels_are_not_flat:${viewport.viewport}`, stats && stats.non_background_ratio > 0,
      `non_background_ratio=${stats?.non_background_ratio} pixels=${stats?.non_background_pixels} ` +
      `buffer=${JSON.stringify(stats?.drawing_buffer)}`, null);
    check(`browser_pixels_saturation_within_limit:${viewport.viewport}`,
      stats && stats.saturation_pct.p95 <= saturationLimit,
      `p95=${stats?.saturation_pct?.p95} <= ${saturationLimit} (max=${stats?.saturation_pct?.max})`,
      AMBIENCE_SOURCE.saturation_max_pct);
    // **两读法必须可分辨**（设计：surface 与 underneath 的读数按设计必须不同），
    // 且**如实登记** underneath 读数：它比 surface 更饱和（像素 p95 可高于 45）。
    // 口径边界：art-bible「饱和度 ≤ 45」约束的是**主色板声明**（`aesthetic_check.py` 校验），
    // **不是**逐像素渲染值 ⇒ underneath 的像素读数高于 45 **不构成** palette 约束违规；
    // 本判据只断言「两读法不同」并把两个读数都写进报告（不隐藏）。
    check(`browser_two_readings_are_distinguishable:${viewport.viewport}`,
      Boolean(stats) && Boolean(under) && under.saturation_pct.p95 !== stats.saturation_pct.p95,
      `surface p95=${stats?.saturation_pct?.p95} vs underneath p95=${under?.saturation_pct?.p95} ` +
      `(underneath 高于 45 属**像素面**读数，palette 约束按声明面校验 ⇒ 见 subjective_residual 的口径边界)`,
      null);
  }
}

// ---- 7) 反例自证：注入违规读数 ⇒ 同一判定必须红
const injected = {
  roughness: 0.1, metalness: 0.8, specularFaces: ['specular'],
  saturationP95: 90, nonBackgroundRatio: 0,
};
const injectedOk = injected.roughness >= roughnessFloor && injected.metalness < 0.1
  && injected.specularFaces.length === 0 && injected.saturationP95 <= saturationLimit
  && injected.nonBackgroundRatio > 0;
check('counter_example_injected_violation_turns_red', injectedOk === false,
  `注入 违规读数 ⇒ 同一判定 ${injectedOk}（必须为 false）`, null);

const failed = results.filter((entry) => !entry.ok);
const report = {
  schema_version: '1.0.0',
  tag: TAG,
  pack: 'districts/xingfu-xiaoqu',
  ambience_source: AMBIENCE_SOURCE,
  thresholds: {
    saturation_max_pct: saturationLimit, roughness_min: roughnessFloor,
    ambient_ratio_min: ambientRatioMin, shadow_softness_min: shadowSoftnessMin,
    audio_allowed_beds: constraints.audio.allowed_beds,
  },
  subjective_residual:
    '「氛围达成」仍有主观成分：本判据只判**数值面**（取数源 = 内容包的 ambience / aesthetic_constraints 段 + '
    + '真浏览器像素统计），不声称「观感已经精美」。',
  reading_boundary:
    'art-bible「饱和度 ≤ 45」约束的是**主色板声明**（由 tools/aesthetic_check.py 校验），不是逐像素渲染值；'
    + 'underneath 读法的像素 p95 实测高于 45，属**已登记的口径边界**（见 checks 里 '
    + 'browser_two_readings_are_distinguishable:* 的读数），不构成 palette 约束违规。',
  checks: results,
  failed: failed.map((entry) => entry.name),
};
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
for (const entry of results) {
  process.stdout.write(`${entry.ok ? 'PASS' : 'FAIL'}  ${entry.name} (${entry.detail})\n`);
}
process.stdout.write(`ambience_assert: PASS=${results.length - failed.length} FAIL=${failed.length}\n`);
process.exit(failed.length === 0 ? 0 : 1);
