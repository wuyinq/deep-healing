/**
 * 治愈系光照与材质（AC-M3-4 / AC-M3-8③）——M3 真实现。
 *
 * 两态差异**只**在本模块 + 材质亮度系数：
 *   - 表层 = `worldview.tone.surface`（晨光；具体色温/环境比**只在 pack 的 worldview.json 里定义**）
 *   - 深层 = `worldview.tone.underneath`（**同一色板降明度**：色温降、环境比降、饱和**不升**）
 * **禁止**换坐标 / 换几何 / 换相机 / 换地图。
 *
 * 数值**不硬编码**：全部来自 pack 的 `worldview.json`（由 `main.ts` 读入后传入）。
 * art-bible 约束仍成立：饱和 ≤45、粗糙度 ≥0.6、无镜面。
 */

import * as THREE from 'three';

export type Reading = 'surface' | 'underneath';

export interface ToneReading {
  light_k: number;
  ambient_ratio: number;
  saturation_pct: number;
}

export interface Tone {
  surface: ToneReading;
  underneath: ToneReading;
}

export const ROUGHNESS_MIN = 0.6; // art-bible：粗糙度 ≥0.55（本项目取 0.6）

/** 色温（开尔文）→ RGB（暖区）。纯函数，可离线断言。 */
export function kelvinToRgb(kelvin: number): [number, number, number] {
  const temperature = Math.max(1000, Math.min(40000, kelvin)) / 100;
  const red = temperature <= 66 ? 255 : Math.max(0, Math.min(255, 329.698727446 * ((temperature - 60) ** -0.1332047592)));
  const green = temperature <= 66
    ? Math.max(0, Math.min(255, 99.4708025861 * Math.log(temperature) - 161.1195681661))
    : Math.max(0, Math.min(255, 288.1221695283 * ((temperature - 60) ** -0.0755148492)));
  const blue = temperature >= 66
    ? 255
    : (temperature <= 19 ? 0 : Math.max(0, Math.min(255, 138.5177312231 * Math.log(temperature - 10) - 305.0447927307)));
  return [red / 255, green / 255, blue / 255];
}

/** 从基调派生渲染参数。**降明度**在这里体现：`luminanceScale` 随 `light_k` / `ambient_ratio` 单调下降。 */
export function deriveLighting(tone: ToneReading) {
  const [red, green, blue] = kelvinToRgb(tone.light_k);
  const luminanceScale = Math.min(1, (tone.light_k / 5200) * (0.5 + tone.ambient_ratio));
  return {
    keyColor: new THREE.Color(red, green, blue),
    keyIntensity: 1.1 * luminanceScale,
    ambientIntensity: tone.ambient_ratio * 2 * luminanceScale,
    fillIntensity: 0.25 * luminanceScale,
    luminanceScale,
    saturation: tone.saturation_pct / 100,
    roughnessMin: ROUGHNESS_MIN,
  };
}

export function applyHealingLighting(scene: THREE.Scene, tone: ToneReading): void {
  const derived = deriveLighting(tone);
  const existing = scene.getObjectByName('healing-lighting');
  if (existing) scene.remove(existing);
  const rig = new THREE.Group();
  rig.name = 'healing-lighting';

  const ambient = new THREE.HemisphereLight(0xf6efe2, 0xcfc4b2, derived.ambientIntensity);
  ambient.name = 'ambient';
  rig.add(ambient);

  const key = new THREE.DirectionalLight(derived.keyColor, derived.keyIntensity);
  key.name = 'key';
  key.position.set(24, 30, 18);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.radius = 0.62 * 6;
  key.shadow.bias = -0.0006;
  rig.add(key);

  const fill = new THREE.DirectionalLight(0xe7f0ff, derived.fillIntensity);
  fill.name = 'fill';
  fill.position.set(-18, 12, -14);
  rig.add(fill);

  scene.add(rig);
}

/** 材质工厂：粗糙度高、镜面弱（避免硬高对比）；`luminanceScale` 只**降**明度，不升饱和。 */
export function healingMaterial(color: string, tone: ToneReading, roughness = 0.75): THREE.MeshStandardMaterial {
  const derived = deriveLighting(tone);
  const base = new THREE.Color(color);
  const material = new THREE.MeshStandardMaterial({
    roughness: Math.max(roughness, ROUGHNESS_MIN),
    metalness: 0.04,
  });
  // 深层态 = 同一色板降明度：乘性变暗，**不**提高饱和度
  material.color = base.clone().multiplyScalar(derived.luminanceScale);
  return material;
}
