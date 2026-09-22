/**
 * 治愈系光照与材质约束（AC-11 的可执行部分）——V0 骨架。
 * 数值来自 assets/manifest.json 的 aesthetic_constraints，由 tools/aesthetic_check.py 校验。
 */

import * as THREE from 'three';

export const HEALING_LIGHTING = {
  ambientRatio: 0.42, // >= 0.35
  shadowSoftness: 0.62, // >= 0.5
  keyLightTempK: 4200,
  fillLightTempK: 5600,
  roughnessMin: 0.6,
} as const;

export function applyHealingLighting(scene: THREE.Scene): void {
  const ambient = new THREE.HemisphereLight(0xf6efe2, 0xcfc4b2, HEALING_LIGHTING.ambientRatio * 2);
  scene.add(ambient);

  const key = new THREE.DirectionalLight(0xfff1dc, 1.1);
  key.position.set(24, 30, 18);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.radius = HEALING_LIGHTING.shadowSoftness * 6;
  key.shadow.bias = -0.0006;
  scene.add(key);

  const fill = new THREE.DirectionalLight(0xe7f0ff, 0.25);
  fill.position.set(-18, 12, -14);
  scene.add(fill);
}

/** 材质工厂：默认粗糙度高、镜面弱（避免硬高对比）。 */
export function healingMaterial(color: string, roughness = 0.75): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color,
    roughness: Math.max(roughness, HEALING_LIGHTING.roughnessMin),
    metalness: 0.04,
  });
}
