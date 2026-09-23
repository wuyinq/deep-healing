/**
 * 极简 PNG 解码 + 像素统计（spike 工具；AC-M4-11④ 的取数面）。
 *
 * 为什么不用 `gl.readPixels`：headless Chromium 的 WebGL 绘制缓冲在 present 之后**不再保证可读**
 * （无 `preserveDrawingBuffer` 时实测读到全 0）⇒ 那不是「画面上有什么」的真读数。
 * 截图（`page.screenshot()`）才是**真的呈现结果**，所以这里解码 PNG 后统计。
 *
 * 支持：8 位深、非隔行、color type 2（RGB）/ 6（RGBA）。这是 Chromium 截图的实际形态。
 */

import { inflateSync } from 'node:zlib';
import { readFileSync } from 'node:fs';

const SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

/** 解码 PNG ⇒ { width, height, channels, data(RGBA) }。 */
export function decodePng(path) {
  const buffer = readFileSync(path);
  if (!buffer.subarray(0, 8).equals(SIGNATURE)) throw new Error(`not a PNG: ${path}`);
  let offset = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  let interlace = 0;
  const idat = [];
  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.subarray(offset + 4, offset + 8).toString('ascii');
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    if (type === 'IHDR') {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
      interlace = data[12];
    } else if (type === 'IDAT') {
      idat.push(data);
    } else if (type === 'IEND') {
      break;
    }
    offset += 12 + length;
  }
  if (bitDepth !== 8) throw new Error(`unsupported bit depth ${bitDepth}`);
  if (interlace !== 0) throw new Error('interlaced PNG is not supported');
  const channels = colorType === 6 ? 4 : colorType === 2 ? 3 : 0;
  if (channels === 0) throw new Error(`unsupported color type ${colorType}`);

  const raw = inflateSync(Buffer.concat(idat));
  const stride = width * channels;
  const out = Buffer.alloc(width * height * 4);
  let previous = Buffer.alloc(stride);
  for (let y = 0; y < height; y += 1) {
    const filter = raw[y * (stride + 1)];
    const line = Buffer.from(raw.subarray(y * (stride + 1) + 1, y * (stride + 1) + 1 + stride));
    for (let x = 0; x < stride; x += 1) {
      const left = x >= channels ? line[x - channels] : 0;
      const up = previous[x];
      const upLeft = x >= channels ? previous[x - channels] : 0;
      if (filter === 1) line[x] = (line[x] + left) & 0xff;
      else if (filter === 2) line[x] = (line[x] + up) & 0xff;
      else if (filter === 3) line[x] = (line[x] + ((left + up) >> 1)) & 0xff;
      else if (filter === 4) {
        const p = left + up - upLeft;
        const pa = Math.abs(p - left);
        const pb = Math.abs(p - up);
        const pc = Math.abs(p - upLeft);
        const predictor = pa <= pb && pa <= pc ? left : (pb <= pc ? up : upLeft);
        line[x] = (line[x] + predictor) & 0xff;
      }
    }
    for (let x = 0; x < width; x += 1) {
      const source = x * channels;
      const target = (y * width + x) * 4;
      out[target] = line[source];
      out[target + 1] = line[source + 1];
      out[target + 2] = line[source + 2];
      out[target + 3] = channels === 4 ? line[source + 3] : 255;
    }
    previous = line;
  }
  return { width, height, channels, data: out };
}

function saturationPct(r, g, b) {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  return max === 0 ? 0 : ((max - min) / max) * 100;
}

function hueDeg(r, g, b) {
  const rr = r / 255; const gg = g / 255; const bb = b / 255;
  const max = Math.max(rr, gg, bb);
  const min = Math.min(rr, gg, bb);
  const delta = max - min;
  if (delta === 0) return -1;
  let hue;
  if (max === rr) hue = 60 * (((gg - bb) / delta) % 6);
  else if (max === gg) hue = 60 * (((bb - rr) / delta) + 2);
  else hue = 60 * (((rr - gg) / delta) + 4);
  return (hue + 360) % 360;
}

/**
 * 像素统计。`exclude` = 需要剔除的矩形（HUD），坐标用**原始像素**。
 * 返回非背景占比、非背景像素的饱和分布、暖色相占比。
 */
export function pixelStats(path, { exclude = null } = {}) {
  const image = decodePng(path);
  const counts = new Map();
  const sampled = [];
  for (let y = 0; y < image.height; y += 1) {
    for (let x = 0; x < image.width; x += 1) {
      if (exclude && x >= exclude.x && x < exclude.x + exclude.width
          && y >= exclude.y && y < exclude.y + exclude.height) continue;
      const index = (y * image.width + x) * 4;
      const r = image.data[index];
      const g = image.data[index + 1];
      const b = image.data[index + 2];
      const key = `${r},${g},${b}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
      sampled.push([r, g, b]);
    }
  }
  let backgroundKey = '0,0,0';
  let backgroundCount = -1;
  for (const [key, count] of counts.entries()) {
    if (count > backgroundCount) { backgroundCount = count; backgroundKey = key; }
  }
  const nonBackground = sampled.filter(([r, g, b]) => `${r},${g},${b}` !== backgroundKey);
  const saturations = nonBackground.map(([r, g, b]) => saturationPct(r, g, b)).sort((a, b) => a - b);
  const hues = nonBackground.map(([r, g, b]) => hueDeg(r, g, b)).filter((hue) => hue >= 0);
  const percentile = (p) => (saturations.length
    ? saturations[Math.min(saturations.length - 1, Math.floor(saturations.length * p))] : 0);
  return {
    file: path,
    size: { width: image.width, height: image.height },
    excluded_rect: exclude,
    background_rgb: backgroundKey,
    background_ratio: Number((backgroundCount / sampled.length).toFixed(6)),
    non_background_ratio: Number((nonBackground.length / sampled.length).toFixed(6)),
    non_background_pixels: nonBackground.length,
    sampled_pixels: sampled.length,
    saturation_pct: {
      max: Number((saturations[saturations.length - 1] ?? 0).toFixed(3)),
      p95: Number(percentile(0.95).toFixed(3)),
      p50: Number(percentile(0.5).toFixed(3)),
    },
    warm_hue_share: Number((hues.length
      ? hues.filter((hue) => hue >= 20 && hue <= 60).length / hues.length : 0).toFixed(6)),
  };
}

/** 反例对照：合成一块**全饱和红**图 ⇒ 同一统计口径必须报超限。 */
export function syntheticSaturatedStats() {
  const pixels = Array.from({ length: 10000 }, () => [255, 0, 0]);
  const saturations = pixels.map(([r, g, b]) => saturationPct(r, g, b));
  return { saturation_max: Math.max(...saturations), non_background_ratio: 1 };
}
