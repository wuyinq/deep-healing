/**
 * L1 渲染层入口——M3 真实现。
 *
 * 职责：消费 snapshot/delta/event，渲染 3D 场景与双模式 UI；把 pack 的 `worldview` 交给场景
 * （**两态读法**：表层 / 深层 = 同一几何，只换光照与材质亮度）。
 * 边界（硬）：零业务规则、零模型调用、零世界状态写；不直读事件日志文件。
 *
 * 世界观来源（R2 / F13 修正）：**不再静态 import pack#1 的 worldview.json**，也不再有第二份
 * 数值副本（`FALLBACK_WORLDVIEW` 已删除）。URL 由**会话的 `district_pack_id`** 决定：
 * `/packs/<district_pack_id>/worldview.json`（由宿主静态服务从 `districts/<pack>/worldview.json` 提供）
 * ⇒ 同一组 tone 数值在全树**只有一处定义点**（pack 数据文件）。
 */

import { createScene, type SceneHandle } from './scene/world.js';
import { RenderClient, type ServerMessage } from './net/client.js';
import { ObservePanel } from './ui/observe/panel.js';
import { InterventionPanel } from './ui/participate/intervention.js';
import type { Reading, Tone } from './scene/lighting.js';

export interface WorldviewDocument {
  schema_version: string;
  pack_id: string;
  tone: Tone;
  anomalies: Array<{ id: string; at_entity: string; kind: string; surface_read: string; underneath_read: string; reveal_at_tick: number }>;
  fault_lines: Array<{ id: string; about: string; kind: string; repair_via: string; repaired_state: string }>;
}

/** 世界观 URL：由会话 `district_pack_id` 决定（**唯一**取值路径）。 */
export function worldviewUrlFor(districtPackId: string): string {
  return `/packs/${districtPackId}/worldview.json`;
}

export async function loadWorldview(url: string): Promise<WorldviewDocument> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`E_PACK_INVALID: cannot load worldview (${response.status}) ${url}`);
  const document = (await response.json()) as WorldviewDocument;
  if (!document.tone?.surface || !document.tone?.underneath) {
    throw new Error('E_PACK_INVALID: worldview.tone.surface/underneath are required');
  }
  return document;
}

export interface AppHandle {
  scene: SceneHandle;
  client: RenderClient;
  observe: ObservePanel;
  intervene: InterventionPanel;
  worldview: WorldviewDocument;
  setReading(reading: Reading): void;
  setMode(mode: 'observe' | 'participate'): void;
}

export async function bootstrap(options: { worldviewUrl?: string; autoConnect?: boolean; districtPackId?: string } = {}): Promise<AppHandle> {
  const canvas = document.getElementById('scene') as HTMLCanvasElement | null;
  if (!canvas) throw new Error('missing #scene canvas');
  const hud = document.getElementById('hud') as HTMLElement;

  const client = new RenderClient();
  // **先建会话**（会话层是 `district_pack_id` 的权威）⇒ 世界观 URL 由它决定，渲染层不写死 pack。
  if (options.autoConnect !== false) {
    try {
      await client.connect({ url: '/ws', mode: 'observe', districtPackId: options.districtPackId });
    } catch {
      // 无会话层时仍尝试用显式传入的 pack id（离线开发）；**不**伪造任何世界状态或基调数值
    }
  }
  const packId = options.districtPackId ?? client.districtPackId;
  const worldview = await loadWorldview(options.worldviewUrl ?? worldviewUrlFor(packId));
  const tone: Tone = worldview.tone;

  const scene = createScene(canvas, { worldview: tone });
  const observe = new ObservePanel(hud);
  const intervene = new InterventionPanel(document.getElementById('intervention-host') ?? hud, client);

  client.onMessage((message: ServerMessage) => {
    scene.apply(message as { t: string; tick: number; state?: never; ops?: never });
    observe.apply(message);
    if (message.t === 'event') {
      const event = message.event as Record<string, unknown>;
      if (event?.type === 'task.state_changed') intervene.renderTaskEvolution([event.payload as Record<string, unknown>]);
    }
  });

  const modeBadge = document.getElementById('mode-badge');
  const readingBadge = document.getElementById('reading-badge');
  const setReading = (reading: Reading) => {
    scene.setReading(reading);
    observe.renderAnomalyReads(worldview, observeTick(observe), reading);
    if (readingBadge) readingBadge.textContent = reading;
  };
  const setMode = (mode: 'observe' | 'participate') => {
    client.mode = mode;
    if (modeBadge) modeBadge.textContent = mode;
    if (mode === 'participate') intervene.mount();
  };

  document.getElementById('toggle-reading')?.addEventListener('click', () => {
    setReading(scene.reading() === 'surface' ? 'underneath' : 'surface');
  });
  document.getElementById('toggle-mode')?.addEventListener('click', () => {
    setMode(client.mode === 'observe' ? 'participate' : 'observe');
  });

  // 暴露给真浏览器验收脚本（Playwright）读取，不构成写路径
  (globalThis as unknown as { __deephealing?: unknown }).__deephealing = {
    scene, client, observe, intervene, worldview, setReading, setMode,
    geometry: () => scene.geometry(),
    entityIds: () => scene.entityIds(),
    writeControls: () => observe.listWriteControls(),
    reading: () => scene.reading(),
    mode: () => client.mode,
    // R3 / G2：判据必须能经**应用装配路径**取数（含 mesh 层读回）
    geometryFor: (reading: Reading) => scene.geometryFor(reading),
    assemblyReport: () => scene.assemblyReport(),
    // R3 / G1：画布尺寸 / 绘制缓冲读数
    viewport: () => scene.viewport(),
  };

  setMode('observe');
  setReading('surface');
  scene.startRenderLoop();

  if (options.autoConnect !== false) {
    try {
      await client.connect({ url: '/ws', mode: 'observe' });
    } catch {
      // 无会话层时仍渲染本地场景（离线可看），但**不**伪造世界状态
    }
  }
  return { scene, client, observe, intervene, worldview, setReading, setMode };
}

function observeTick(panel: ObservePanel): number {
  const el = document.getElementById('tick');
  const match = el?.textContent?.match(/tick\s+(\d+)/);
  return match ? Number(match[1]) : 0;
}

void bootstrap();
