#!/usr/bin/env node
/** B-2b 定位：打印最大 |Δyaw_displayed| 的前若干对及其权威上下文（一次性诊断）。 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const WORKSPACE = resolve(HERE, '..', '..');
const SOURCE = join(WORKSPACE, '02_source');
const OUT = join(HERE, 'runtime', 'a-evidence', 'out');
const NPC = 'npc-006';

const records = readFileSync(join(OUT, 'bridge-records-a-evidence.jsonl'), 'utf8')
  .split('\n').filter(Boolean).map((line) => JSON.parse(line));
const byTick = new Map();
for (const snapshot of records.filter((r) => r.kind === 'snapshot')) {
  const entity = (snapshot.state?.entities ?? []).find((item) => item.id === NPC);
  if (!entity) continue;
  byTick.set(Number(snapshot.tick), { tick: Number(snapshot.tick), pos_mm: entity.transform?.pos_mm,
                                      nav_node_id: entity.transform?.nav_node_id });
}
const authority = [...byTick.values()].sort((a, b) => a.tick - b.tick);

const presentation = await import(join(SOURCE, 'v0_skeleton', 'web', 'src', 'scene', 'presentation.ts'));
const { wrapToPi } = presentation;
presentation.resetPresentation();
const engine = presentation.createPresentation({ smoothingMs: 100, epsAuthorityMaxStepM: 0.92736 });
const displayed = [];
for (const row of authority) {
  const pos = row.pos_mm ?? { x: 0, y: 0, z: 0 };
  presentation.apply([{ entityId: NPC, pos_m: [pos.x / 1000, pos.y / 1000, pos.z / 1000],
                        stateId: 'daily', tick: row.tick }], row.tick);
  engine.step(100);
  const line = engine.displayed().find((item) => item.entityId === NPC);
  displayed.push({ tick: row.tick, pos: line?.displayed_position_m, yaw: line?.facing_yaw_rad,
                   auth_nav: row.nav_node_id, auth_pos: [pos.x / 1000, pos.y / 1000, pos.z / 1000] });
}
const pairs = displayed.slice(1).map((row, index) => {
  const prev = displayed[index];
  const dAuth = Math.hypot(row.auth_pos[0] - prev.auth_pos[0], row.auth_pos[1] - prev.auth_pos[1],
                           row.auth_pos[2] - prev.auth_pos[2]);
  const authDir = dAuth > 1e-6 ? Math.atan2(row.auth_pos[0] - prev.auth_pos[0],
                                            row.auth_pos[2] - prev.auth_pos[2]) : null;
  const prevAuthDir = index > 0 ? (() => {
    const p2 = displayed[index - 1];
    const d = Math.hypot(prev.auth_pos[0] - p2.auth_pos[0], prev.auth_pos[1] - p2.auth_pos[1],
                         prev.auth_pos[2] - p2.auth_pos[2]);
    return d > 1e-6 ? Math.atan2(prev.auth_pos[0] - p2.auth_pos[0], prev.auth_pos[2] - p2.auth_pos[2]) : null;
  })() : null;
  return { i: index, tick: row.tick, dAuth: Number(dAuth.toFixed(4)),
           dYawDeg: Number((Math.abs(wrapToPi(row.yaw - prev.yaw)) * 180 / Math.PI).toFixed(2)),
           authDirDeg: authDir === null ? null : Number((authDir * 180 / Math.PI).toFixed(1)),
           prevAuthDirDeg: prevAuthDir === null ? null : Number((prevAuthDir * 180 / Math.PI).toFixed(1)),
           nav_from: prev.auth_nav, nav_to: row.auth_nav };
}).sort((a, b) => b.dYawDeg - a.dYawDeg);
writeFileSync(join(HERE, 'readback', 'b2b-top-pairs.json'), `${JSON.stringify(pairs.slice(0, 12), null, 2)}\n`);
process.stdout.write(`TOP ${JSON.stringify(pairs.slice(0, 6))}\n`);
process.stdout.write(`moving_pairs_over_90deg ${JSON.stringify(pairs.filter((p) => p.dYawDeg > 90 && p.dAuth > 0.001).length)}\n`);
