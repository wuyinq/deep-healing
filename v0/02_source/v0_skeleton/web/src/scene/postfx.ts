/**
 * 后处理链（N4 / W2 / D-2 + Raven 预审 P-C）—— **环境光遮蔽（GTAO）**。
 *
 * 链：`RenderPass → GTAOPass → OutputPass`。
 *   - `gtao.output = GTAOPass.OUTPUT.Default`（在**原画面**上混合 AO，不是只输出 AO）；
 *   - `gtao.blendIntensity = 1.0`（AC-2 要求 ≥ 0.8）；
 *   - `updateGtaoMaterial(...)` 见 `GTAO_MATERIAL_PARAMETERS`；`updatePdMaterial(...)` 见 `GTAO_DENOISE_PARAMETERS`。
 *
 * **N4-r2 / M-1（关闭 AC-2 的「画面级可见」）**：r1 的参数（radius 0.55 / scale 1.0 / samples 16 /
 * blend 0.92）在**冻结口径 win=96** 下只有 **6.29**（阈值 8）⇒ 判 FAIL。逐轮实测（脚本
 * `v0/spikes/n4-art/ao-sweep.mjs`，读数 `readback/ao-sweep/*-diff.json`）：
 *   | 参数组 | win96 | 视觉核验（`readback/ao-config-compare.png` 并排裁切） |
 *   |---|---|---|
 *   | r1 基线 r0.55/s1.0/b0.92 | 6.29 | 判「看不到 AO」 |
 *   | r2.0/s1.0/b1.0 | 18.27 | 判「dirty black patches（太宽）」 |
 *   | r1.0/s2.2/b1.0 | 23.59 | 判「broad soft gradient，不够贴」 |
 *   | r1.0/s3.0/b1.0 | 30.00 | 判「implausible smear（最差）」 |
 *   | **r0.7/s3.0/b1.0 + 去噪 rings4** | **22.80** | **判「clear but localized darker band at the wall base … plausible contact shadow」（最优）** |
 * 关键机制：`GTAOShader` 里 `ao = pow(ao, scale)` ⇒ **`scale > 1` 是「更暗」、`radius` 是「更宽」**。
 * ⇒ 采纳**窄半径（0.7 m，街面接触尺度）+ 强 AO（scale 3.0）+ 满混合（1.0）+ 泊松去噪（rings 4）**：
 * 暗带**紧贴墙脚**（不向墙面/地面漫开成脏灰），同时 96 px 窗口仍有 2.85× 余量。
 * **诚实边界**：全画面正常视距下，接触暗部**仍属局部细节**（不是强对比的大黑带）——
 * 逐组并排裁切证据在 `readback/ao-config-compare.png`，Sentinel 可独立复核。
 *
 * **不接 bloom / cinematic 色调 pass**（取舍理由写进 `03`）：`art-bible` §1 要求低饱和、
 * `assets/manifest.json` 的 `aesthetic_constraints.palette.saturation_max_pct = 45`；
 * bloom 会推高亮部并引入镜面感，与「治愈系低对比」冲突。
 *
 * **Node / 无 WebGL ⇒ `createPostFX()` 返回 `null`**，`world.ts` 的 `renderFrame()` 走原直渲路径
 * （`scene_assert` 的相机判据语义零变化）。
 *
 * **P-C 修正（预审结论，必须做）**：本模块的 pass 会调用 `renderer.render(...)`
 * （`RenderPass`/`GTAOPass` 用**场景相机**，`OutputPass` 的 `FullScreenQuad` 用**内置正交相机**）
 * ⇒ `world.ts` 的渲染记录点**只认「目标是场景」的那次调用**，并把非场景调用按 pass 分开记，
 * 见 `RenderCameraReport.scene_camera` / `pass_cameras`。
 */

import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/examples/jsm/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';

/**
 * AC-2 的 AO 混合强度（配置面；画面面由 A/B 像素对照承担）。
 *
 * **N4-r3 / R3-4（修复 architect 打回）**：r2 把它取到上限 1.0、并把 `scale` 取到 3.0，是为了把
 * `win96` 推过阈值 8。但 `scale` 是 **AO 的 gamma（`ao = pow(ao, scale)`）**——`scale = 3.0` 意味着
 * 把 AO 项**三次方**，即把「物理量」当「美术可调旋钮」用来刷指标。architect 已打回该做法。
 *
 * r3 退回**物理上站得住**的配置：`blendIntensity = 0.92`（不顶格）、`scale = 1.0`（不加幂曲线）。
 * `radius = 0.7 m` 保留（世界尺度的 AO 采样半径，房间尺度下站得住）；`samples = 32` 保留
 * （提高采样数是**减少估计方差**，不是放大信号）。
 *
 * 代价：`win96` 会退回阈值以下 ⇒ **AC-2 如实记 FAIL**（见 `03_artisan_self_test.log` 的 r3 节）。
 * 宁可不达标，也不把 gamma 当调参旋钮。
 */
export const GTAO_BLEND_INTENSITY = 0.92;

/**
 * GTAO 材质参数（N4-r3 / R3-4 退回物理可辩护配置）。
 * `radius` 单位米（世界尺度）；`scale` 是 AO 的 gamma（`ao = pow(ao, scale)`）——**r3 起固定 1.0**，
 * 不允许用 >1 的 gamma 放大 AO 以刷 `win96` 读数。
 */
export const GTAO_MATERIAL_PARAMETERS = {
  radius: 0.7,
  distanceExponent: 1.0,
  thickness: 1.0,
  scale: 1.0,
  samples: 32,
  distanceFallOff: 1.0,
  screenSpaceRadius: false,
} as const;

/**
 * 泊松去噪参数（N4-r2 / M-1）：加大 rings/samples 让接触暗带**平滑**（减少 r1 的噪点状「脏」感）。
 * 实测对 win96 影响可忽略（22.34 → 22.31），收益在画质。
 */
export const GTAO_DENOISE_PARAMETERS = {
  rings: 4,
  samples: 32,
  radius: 12,
} as const;

/** 链上的 pass（顺序即渲染顺序）。 */
export const POSTFX_CHAIN: readonly string[] = ['RenderPass', 'GTAOPass', 'OutputPass'] as const;

export interface PostFX {
  composer: unknown;
  gtao: unknown;
  render(): void;
  setSize(width: number, height: number): void;
  dispose(): void;
  report(): Record<string, unknown>;
}

/**
 * **链的声明配置**（无论是否构造成功都必须给出）——
 * 让 Node / 无 WebGL 环境下的判据仍能核「配置面」，而不是因为「没构造」就无内容可核。
 */
function declaredConfig(available: boolean, reason: string | null): Record<string, unknown> {
  return {
    available,
    reason,
    chain: [...POSTFX_CHAIN],
    gtao: {
      blend_intensity: GTAO_BLEND_INTENSITY,
      output: Number(GTAOPass.OUTPUT.Default),
      parameters: { ...GTAO_MATERIAL_PARAMETERS },
    },
    bloom_connected: false,
    cinematic_connected: false,
    bloom_omission_reason: 'art-bible §1 低饱和（saturation_max_pct=45）⇒ bloom 推高亮部并引入镜面感，与本项目口径冲突',
    evidence_class: 'config_plane (not pixel evidence)',
  };
}

let lastReport: Record<string, unknown> = declaredConfig(false, 'not_constructed');

/**
 * 构造后处理链。`options.webgl === false`（Node / 无 WebGL）⇒ **返回 `null`**。
 * 注意：`renderer` 必须是 `world.ts` 的**包装渲染器**（其 `render` 已被记录点替换）——
 * 这样 `RenderPass`/`GTAOPass`/`OutputPass` 内部的每一次 `renderer.render()` 都会被记录。
 */
export function createPostFX(
  renderer: unknown,
  scene: THREE.Scene,
  camera: THREE.Camera,
  size: { width: number; height: number },
  options: { webgl?: boolean } = {},
): PostFX | null {
  const webgl = options.webgl ?? renderer instanceof THREE.WebGLRenderer;
  if (!webgl) {
    lastReport = declaredConfig(false, 'no_webgl');
    return null;
  }

  const composer = new EffectComposer(renderer as THREE.WebGLRenderer);
  composer.setSize(Math.max(1, size.width), Math.max(1, size.height));

  const renderPass = new RenderPass(scene, camera);
  const gtao = new GTAOPass(scene, camera, Math.max(1, size.width), Math.max(1, size.height));
  gtao.output = GTAOPass.OUTPUT.Default;
  gtao.blendIntensity = GTAO_BLEND_INTENSITY;
  gtao.updateGtaoMaterial({ ...GTAO_MATERIAL_PARAMETERS });
  gtao.updatePdMaterial({ ...GTAO_DENOISE_PARAMETERS });
  const outputPass = new OutputPass();

  composer.addPass(renderPass);
  composer.addPass(gtao);
  composer.addPass(outputPass);

  const report = (): Record<string, unknown> => ({
    ...declaredConfig(true, null),
    pass_count: composer.passes.length,
    // **实测读数**（从真实 pass 实例读回；配置面）
    gtao: {
      blend_intensity: Number(gtao.blendIntensity),
      output: Number(gtao.output),
      parameters: { ...GTAO_MATERIAL_PARAMETERS },
      denoise: { ...GTAO_DENOISE_PARAMETERS },
    },
  });

  const postfx: PostFX = {
    composer,
    gtao,
    render() { composer.render(); },
    setSize(width, height) {
      composer.setSize(Math.max(1, width), Math.max(1, height));
    },
    dispose() {
      composer.dispose();
    },
    report,
  };
  lastReport = report();
  return postfx;
}

/** 最近一次构造的链读数（AC-2 / D-7）。未构造 ⇒ `available: false` 且给出原因。 */
export function postfxReport(): Record<string, unknown> {
  return { ...lastReport };
}
