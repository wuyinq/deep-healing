/**
 * 治愈系光照与材质（AC-M3-4 / AC-M3-8③）——M3 真实现 + **N4 写实光照（W1 / D-1）**。
 *
 * 两态差异**只**在本模块 + 材质亮度系数：
 *   - 表层 = `worldview.tone.surface`（晨光；具体色温/环境比**只在 pack 的 worldview.json 里定义**）
 *   - 深层 = `worldview.tone.underneath`（**同一色板降明度**：色温降、环境比降、饱和**不升**）
 * **禁止**换坐标 / 换几何 / 换相机 / 换地图。
 *
 * 数值**不硬编码**：全部来自 pack 的 `worldview.json`（由 `main.ts` 读入后传入）。
 * art-bible 约束仍成立：饱和 ≤45、粗糙度 ≥0.6、无镜面。
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * **N4（W1）：真实 HDRI 主导照明 + 人工灯降为辅助量级**
 *
 * 结构（D-1，与 `01_architecture_design.md` §10 的预审吸收一致）：
 *   1. **同步**挂程序化天空兜底（等距柱状 `DataTexture` 渐变 + `EquirectangularReflectionMapping`）
 *      ⇒ 首帧不黑、`scene.background` 恒为**纹理**（非纯色路径）；
 *   2. **异步** `HDRLoader` 加载 `web/assets/hdri/kloofendal_overcast_puresky_2k.hdr`，成功后
 *      `hdr.mapping = EquirectangularReflectionMapping`、`scene.background = hdr`、
 *      `backgroundBlurriness = 0.015`、`scene.environment = pmrem.fromEquirectangular(hdr).texture`、
 *      置 `window.__hdriReady = true`；
 *   3. 人工灯**降到辅助量级**：`HemisphereLight 0.16` + `DirectionalLight(sun) 0.55`（参考实现口径），
 *      阴影保留（`PCFSoftShadowMap` 由渲染器侧配置）。
 *
 * **两读法单调性（既有判据不可破）**：`scene.environmentIntensity`、`scene.backgroundIntensity`
 * 与人工灯强度**统一乘** `deriveLighting(tone).luminanceScale` ⇒ `underneath` 仍**更暗**
 * （`underneath_lowers_luminance` / `_lowers_ambient` / `_lowers_light_k` 保持绿），且**几何零改动**。
 *
 * **Node / 无 WebGL**：不触发任何网络请求（`options.webgl === false` ⇒ 只做同步兜底）。
 * 既有导出签名（`kelvinToRgb` / `deriveLighting` / `applyHealingLighting` / `healingMaterial` /
 * `ROUGHNESS_MIN`）**语义一字未改**。
 */

import * as THREE from 'three';
import { HDRLoader } from 'three/examples/jsm/loaders/HDRLoader.js';

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

// ================================================================== N4 / W1：真实光照主导
/** HDRI 资源（静态字符串字面量 ⇒ Vite 静态解析并 emit；Node 下退化为 `file://` 字符串、不发请求）。 */
export const HDRI_URL: string = new URL('../../assets/hdri/kloofendal_overcast_puresky_2k.hdr', import.meta.url).href;

/** 人工灯**辅助量级**（参考实现口径；AC-1 的「降到辅助量级」）。 */
export const ARTIFICIAL_LIGHT_INTENSITY = { hemisphere: 0.16, sun: 0.55 } as const;
/** `scene.environmentIntensity` 基准（乘 `luminanceScale` 后仍 ≥1.15）。 */
export const ENVIRONMENT_INTENSITY = 1.2;
/** AC-1：`backgroundBlurriness ≥ 0.01`。 */
export const BACKGROUND_BLURRINESS = 0.015;

export interface EnvironmentLightingOptions {
  /** 是否具备真 WebGL（`false` ⇒ 不构造加载器、不发请求、不碰 `window`）。 */
  webgl: boolean;
  /** 真 `THREE.WebGLRenderer`（有它才做 `PMREMGenerator` 预过滤；缺省则直接挂等距柱状纹理）。 */
  renderer?: unknown;
  /** 主材质 `envMapIntensity` 的最小值（由 `world.ts` 从材质注册表读出后传入；缺省为 `null`）。 */
  envMapIntensityMin?: number;
}

interface EnvironmentState {
  background_path: 'procedural_sky' | 'hdri' | 'color' | 'texture' | 'none';
  background_is_texture: boolean;
  background_blurriness: number;
  background_intensity: number;
  environment_is_texture: boolean;
  environment_intensity: number;
  artificial_lights: Array<{ name: string; type: string; intensity: number }>;
  artificial_light_intensity_sum: number;
  /**
   * N5-C r2 / FIX-1⑤：**主光源的阴影参数读数**（`AC-A-3⑥` 点名要求 `mapSize` / `radius`）。
   * 从**真 `THREE.DirectionalLight` 实例**读回（非字面量）；`null` = 该路径未挂主光。
   */
  sun_shadow: {
    cast_shadow: boolean;
    map_size: [number, number];
    radius: number;
    bias: number;
    camera: { left: number; right: number; top: number; bottom: number; near: number; far: number };
  } | null;
  luminance_scale: number;
  env_map_intensity_min: number | null;
  hdri_ready: boolean;
  hdri_pending: boolean;
  hdri_error: string | null;
  degradations: string[];
}

const environmentState: EnvironmentState = {
  background_path: 'color',
  background_is_texture: false,
  background_blurriness: 0,
  background_intensity: 1,
  environment_is_texture: false,
  environment_intensity: 0,
  artificial_lights: [],
  artificial_light_intensity_sum: 0,
  sun_shadow: null,
  luminance_scale: 1,
  env_map_intensity_min: null,
  hdri_ready: false,
  hdri_pending: false,
  hdri_error: null,
  degradations: [],
};

let proceduralSky: THREE.DataTexture | null = null;
let hdriTexture: THREE.Texture | null = null;
let pmremEnvironment: THREE.Texture | null = null;
let hdriLoadStarted = false;
const pendingScenes = new Map<THREE.Scene, number>();

/**
 * 程序化天空兜底：等距柱状（equirectangular）**确定性**渐变纹理。
 * 为什么不是纯色：AC-1 要求 `scene.background` **非纯色路径**，且首帧不能黑；
 * 用 `DataTexture` ⇒ Node 下也能构造（零 WebGL / 零网络 / 零 DOM），读数在两环境同源。
 */
function proceduralSkyTexture(): THREE.DataTexture {
  const width = 32;
  const height = 16;
  const data = new Uint8Array(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    const t = y / (height - 1); // 0 = 天顶，1 = 天底
    const value = t <= 0.5
      ? 176 + (236 - 176) * (t / 0.5)      // 天顶 → 地平线：越靠地平线越亮（阴天口径）
      : 236 - (236 - 120) * ((t - 0.5) / 0.5); // 地平线 → 天底：地面反射衰减
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      data[index] = Math.round(value);
      data[index + 1] = Math.round(value * 0.995);
      data[index + 2] = Math.round(value * 0.975);
      data[index + 3] = 255;
    }
  }
  const texture = new THREE.DataTexture(data, width, height, THREE.RGBAFormat);
  texture.mapping = THREE.EquirectangularReflectionMapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

/** 把（已加载的）HDRI 挂到某个场景 —— 两读法共用同一条路径，`luminanceScale` 由调用方给。 */
function applyHdri(scene: THREE.Scene, luminanceScale: number): void {
  if (!hdriTexture) return;
  scene.background = hdriTexture;
  scene.backgroundBlurriness = BACKGROUND_BLURRINESS;
  scene.backgroundIntensity = luminanceScale;
  scene.environment = pmremEnvironment ?? hdriTexture;
  scene.environmentIntensity = ENVIRONMENT_INTENSITY * luminanceScale;
  environmentState.background_path = 'hdri';
  environmentState.background_is_texture = true;
  environmentState.background_blurriness = BACKGROUND_BLURRINESS;
  environmentState.background_intensity = luminanceScale;
  environmentState.environment_is_texture = true;
  environmentState.environment_intensity = ENVIRONMENT_INTENSITY * luminanceScale;
  environmentState.hdri_ready = true;
  environmentState.hdri_pending = false;
}

function startHdriLoad(scene: THREE.Scene, luminanceScale: number, options: EnvironmentLightingOptions): void {
  if (pmremEnvironment || hdriTexture) {
    applyHdri(scene, luminanceScale);
    return;
  }
  pendingScenes.set(scene, luminanceScale);
  environmentState.hdri_pending = true;
  if (hdriLoadStarted) return;
  hdriLoadStarted = true;
  const loader = new HDRLoader();
  loader.load(HDRI_URL, (hdr) => {
    hdr.mapping = THREE.EquirectangularReflectionMapping;
    const renderer = options.renderer as THREE.WebGLRenderer | undefined;
    try {
      if (renderer && typeof renderer.getRenderTarget === 'function') {
        const pmrem = new THREE.PMREMGenerator(renderer);
        pmremEnvironment = pmrem.fromEquirectangular(hdr).texture;
        pmrem.dispose();
      } else {
        pmremEnvironment = null;
        environmentState.degradations.push('E_PMREM_UNAVAILABLE: renderer 缺席 ⇒ 直接挂等距柱状纹理');
      }
    } catch (error) {
      pmremEnvironment = null;
      environmentState.degradations.push(`E_PMREM_FAILED: ${String(error)}`);
    }
    hdriTexture = hdr;
    for (const [target, scale] of pendingScenes) applyHdri(target, scale);
    pendingScenes.clear();
    if (typeof window !== 'undefined') {
      (window as unknown as { __hdriReady?: boolean }).__hdriReady = true;
    }
  }, undefined, (error: unknown) => {
    environmentState.hdri_error = String(error);
    environmentState.hdri_pending = false;
    environmentState.degradations.push(`E_HDRI_LOAD_FAILED: ${String(error)}`);
  });
}

/**
 * **背景 / 环境贴图的真实读回**（N4-r2 / M-6 关闭 Raven N-1）。
 *
 * 为什么需要它：旧实现把 `background_is_texture` / `environment_is_texture` 写成**常量 `true`**，
 * 于是 AC-1 的主判据里存在**恒真子句** —— 把 `scene.background` 换成 `new THREE.Color(...)`
 * 之后判据照样全绿（Raven 的注入实测 `PASS=83 FAIL=0`），机器判据**发现不了背景退化**。
 * 现在改为从**真实场景对象**读：判据的负例可以拿一个真的「纯色背景」场景喂进同一个读取函数，
 * 于是「背景静默退化为纯色」必然判红。
 *
 * 口径：`procedural_sky` 也是**纹理**路径（程序化天空是 `THREE.Texture`），
 * 只有 `scene.background` 是 `Color`（或空）时才算 `color` 路径。
 */
export function backgroundStateOf(scene: THREE.Scene): {
  background_path: 'texture' | 'color' | 'none';
  background_is_texture: boolean;
  background_blurriness: number;
  environment_is_texture: boolean;
} {
  const background = scene.background as { isTexture?: boolean; isColor?: boolean } | null | undefined;
  const environment = scene.environment as { isTexture?: boolean } | null | undefined;
  const backgroundIsTexture = background?.isTexture === true;
  const backgroundIsColor = background?.isColor === true;
  return {
    background_path: backgroundIsTexture ? 'texture' : (backgroundIsColor ? 'color' : 'none'),
    background_is_texture: backgroundIsTexture,
    background_blurriness: Number(scene.backgroundBlurriness ?? 0),
    environment_is_texture: environment?.isTexture === true,
  };
}

/**
 * **N4 的照明入口**：程序化天空兜底（同步）+ HDRI 主导（异步）+ 人工灯降为辅助。
 * `options.webgl === false`（Node / 无 WebGL）⇒ 只做同步兜底，**不发请求**。
 */
export function applyEnvironmentLighting(
  scene: THREE.Scene,
  tone: ToneReading,
  options: EnvironmentLightingOptions,
): void {
  const derived = deriveLighting(tone);
  const scale = derived.luminanceScale;

  const existing = scene.getObjectByName('healing-lighting');
  if (existing) scene.remove(existing);
  const rig = new THREE.Group();
  rig.name = 'healing-lighting';

  // 人工灯**只做辅助**：阴天 HDRI 主导 ⇒ 半球光补天光、单向光补方向与阴影。
  const ambient = new THREE.HemisphereLight(0xdfe6ef, 0xb9b3a6,
    ARTIFICIAL_LIGHT_INTENSITY.hemisphere * scale);
  ambient.name = 'ambient';
  rig.add(ambient);

  const sun = new THREE.DirectionalLight(derived.keyColor, ARTIFICIAL_LIGHT_INTENSITY.sun * scale);
  sun.name = 'key';
  sun.position.set(24, 30, 18);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.radius = 0.62 * 6;
  sun.shadow.bias = -0.0006;
  // 阴影相机必须覆盖**整个街区**（three 的默认正交阴影相机只有 ±5 m ⇒ 只有原点附近有影子）；
  // 注视点设到街区中心（主包 rooms 在 x∈[3.5,14.5] / z∈[0.5,8.5]）⇒ 接触暗部覆盖交付面。
  sun.shadow.camera.left = -45;
  sun.shadow.camera.right = 45;
  sun.shadow.camera.top = 45;
  sun.shadow.camera.bottom = -45;
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 220;
  sun.shadow.camera.updateProjectionMatrix();
  sun.target.position.set(9, 0, 9);
  rig.add(sun.target);
  rig.add(sun);

  scene.add(rig);

  // 同步兜底：首帧不黑，且 `background` 恒为**纹理**（非纯色路径）。
  if (!proceduralSky) proceduralSky = proceduralSkyTexture();
  scene.background = proceduralSky;
  scene.backgroundBlurriness = BACKGROUND_BLURRINESS;
  scene.backgroundIntensity = scale;
  scene.environment = proceduralSky;
  scene.environmentIntensity = ENVIRONMENT_INTENSITY * scale;

  // N4-r2 / M-6（Raven N-1）：**不再无条件硬赋值** —— 从**真实场景对象**读回，
  // 这样「背景静默退化为纯色 / 环境贴图丢失」这类回归能被机器判据拦住。
  // 旧写法（`background_is_texture = true` 常量）是恒真子句：把 `scene.background` 换成
  // `new THREE.Color(...)` 后判据照样全绿（Raven 的注入 P-4 实测 PASS=83 FAIL=0）。
  const backgroundState = backgroundStateOf(scene);
  environmentState.background_path = hdriTexture
    ? 'hdri'
    : (backgroundState.background_is_texture ? 'procedural_sky' : backgroundState.background_path);
  environmentState.background_is_texture = backgroundState.background_is_texture;
  environmentState.background_blurriness = Number(scene.backgroundBlurriness ?? 0);
  environmentState.background_intensity = Number(scene.backgroundIntensity ?? 0);
  environmentState.environment_is_texture = backgroundState.environment_is_texture;
  environmentState.environment_intensity = ENVIRONMENT_INTENSITY * scale;
  environmentState.luminance_scale = scale;
  environmentState.artificial_lights = [
    { name: 'ambient', type: 'HemisphereLight', intensity: ambient.intensity },
    { name: 'key', type: 'DirectionalLight', intensity: sun.intensity },
  ];
  environmentState.artificial_light_intensity_sum = ambient.intensity + sun.intensity;
  // N5-C r2 / FIX-1⑤：`AC-A-3⑥` 点名的阴影参数 —— 从**实例**读回（含阴影相机视锥）。
  environmentState.sun_shadow = {
    cast_shadow: sun.castShadow === true,
    map_size: [Number(sun.shadow.mapSize.x), Number(sun.shadow.mapSize.y)],
    radius: Number(sun.shadow.radius),
    bias: Number(sun.shadow.bias),
    camera: {
      left: Number(sun.shadow.camera.left), right: Number(sun.shadow.camera.right),
      top: Number(sun.shadow.camera.top), bottom: Number(sun.shadow.camera.bottom),
      near: Number(sun.shadow.camera.near), far: Number(sun.shadow.camera.far),
    },
  };
  if (typeof options.envMapIntensityMin === 'number') {
    environmentState.env_map_intensity_min = options.envMapIntensityMin;
  }

  if (options.webgl) startHdriLoad(scene, scale, options);
}

/** 人工灯强度总和（AC-1 的机器读数；surface 读法下必须 ≤ 1.0）。 */
export function artificialLightIntensitySum(): number {
  return environmentState.artificial_light_intensity_sum;
}

/**
 * 环境照明读数（AC-1 / D-7）。
 * **口径声明**：本读数是**配置面读数**，不构成画面证据 ——
 * 画面面由 `v0/spikes/n4-art/` 的实机截图（含 `window.__hdriReady === true` 的等待与网络失败检查）承担。
 */
export function environmentReport(): Record<string, unknown> {
  return {
    background_path: environmentState.background_path,
    background_is_texture: environmentState.background_is_texture,
    background_is_color_path: environmentState.background_path === 'color',
    background_blurriness: environmentState.background_blurriness,
    background_intensity: environmentState.background_intensity,
    environment_is_texture: environmentState.environment_is_texture,
    environment_intensity: environmentState.environment_intensity,
    luminance_scale: environmentState.luminance_scale,
    artificial_lights: environmentState.artificial_lights.map((light) => ({ ...light })),
    artificial_light_intensity_sum: artificialLightIntensitySum(),
    sun_shadow: environmentState.sun_shadow === null
      ? null
      : { ...environmentState.sun_shadow,
          map_size: [...environmentState.sun_shadow.map_size] as [number, number],
          camera: { ...environmentState.sun_shadow.camera } },
    env_map_intensity_min: environmentState.env_map_intensity_min,
    hdri_url: HDRI_URL,
    hdri_ready: environmentState.hdri_ready,
    hdri_pending: environmentState.hdri_pending,
    hdri_error: environmentState.hdri_error,
    degradations: [...environmentState.degradations],
    evidence_class: 'config_plane (not pixel evidence)',
  };
}
