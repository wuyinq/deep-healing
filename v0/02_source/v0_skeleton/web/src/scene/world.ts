/**
 * 场景装配（L1）——V0 骨架。
 * 只消费 snapshot/delta；实体与组件来自下发状态，不得直读内容包文件。
 */

import * as THREE from 'three';
import { applyHealingLighting } from './lighting.js';

export interface SceneHandle {
  apply(message: { t: string; tick: number; state?: unknown; ops?: unknown[] }): void;
  startRenderLoop(): void;
  dispose(): void;
}

export function createScene(canvas: HTMLCanvasElement): SceneHandle {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio ?? 1, 2));

  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#f3efe8');
  scene.fog = new THREE.Fog('#e9e2d6', 40, 120);

  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 500);
  camera.position.set(18, 14, 24);
  camera.lookAt(9, 0, 6);

  applyHealingLighting(scene);

  const root = new THREE.Group();
  root.name = 'world-root';
  scene.add(root);

  return {
    apply(message) {
      // V0 骨架：把 state/delta 映射为场景对象（实体 id → mesh），实现见 08_v0_plan.md。
      if (message.t !== 'snapshot' && message.t !== 'delta') return;
      throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-scene")');
    },
    startRenderLoop() {
      throw new Error('E_NOT_IMPLEMENTED: V0 skeleton (see 08_v0_plan.md step "web-scene")');
    },
    dispose() {
      renderer.dispose();
    },
  };
}
