/**
 * L1 渲染层入口——V0 骨架。
 *
 * 职责：消费 snapshot/delta/event，渲染 3D 场景与双模式 UI。
 * 边界（硬）：零业务规则、零模型调用、零世界状态写；不得直读内容包与事件日志文件。
 */

import { createScene } from './scene/world.js';
import { RenderClient } from './net/client.js';
import { ObservePanel } from './ui/observe/panel.js';
import { InterventionPanel } from './ui/participate/intervention.js';

export async function bootstrap(): Promise<void> {
  const canvas = document.getElementById('scene') as HTMLCanvasElement | null;
  if (!canvas) throw new Error('missing #scene canvas');

  const scene = createScene(canvas);
  const client = new RenderClient();
  const observe = new ObservePanel(document.getElementById('hud') as HTMLElement);
  const intervene = new InterventionPanel(observe.root, client);

  client.onMessage((message) => {
    scene.apply(message);
    observe.apply(message);
  });

  await client.connect({ url: '/ws', sessionId: 'pending', mode: 'observe' });
  scene.startRenderLoop();
  intervene.mount();
}

void bootstrap();
