/**
 * 渲染客户端判据（AC-M3-3）——**真跑，非 skip**。
 *
 * 运行：cd 02_source/v0_skeleton/web && node --test test/render-client.test.ts
 *
 * 三组各自一条用例：
 *   - 乱序 delta **被丢弃**
 *   - observe 会话调 `submitIntent` **本地即拒**
 *   - 同一消息 `apply` 两次**幂等**
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { RenderClient } from '../src/net/client.ts';

function delta(tick: number, seq: number) {
  return { t: 'delta' as const, tick, seq, ops: [{ op: 'set', entity: 'npc-001', component: 'transform', value: {} }] };
}

test('test_out_of_order_delta_is_dropped', () => {
  const client = new RenderClient();
  assert.equal(client.apply(delta(10, 5)), true);
  // 过期 tick：丢弃
  assert.equal(client.apply(delta(9, 99)), false);
  // 同 tick 但 seq 回退：乱序，丢弃
  assert.equal(client.apply(delta(10, 4)), false);
  // 同 tick 更大 seq：接受
  assert.equal(client.apply(delta(10, 6)), true);
  // 更大 tick：接受
  assert.equal(client.apply(delta(11, 1)), true);
});

test('test_observe_session_submit_intent_rejected_locally', async () => {
  const client = new RenderClient();
  client.mode = 'observe';
  const result = await client.submitIntent({ id: 'ui-1', kind: 'delegate_instruction', target: 'npc-001' });
  assert.equal(result.status, 'rejected');
  assert.equal(result.reason, 'E_MODE_READONLY');
  // 未连接时 participate 也不得伪造成功
  client.mode = 'participate';
  const offline = await client.submitIntent({ id: 'ui-2', kind: 'delegate_instruction', target: 'npc-001' });
  assert.equal(offline.reason, 'E_KERNEL_UNAVAILABLE');
});

test('test_apply_is_idempotent_for_the_same_message', () => {
  const client = new RenderClient();
  const message = delta(42, 7);
  assert.equal(client.apply(message), true);
  assert.equal(client.apply(message), false, '同一消息 apply 两次必须幂等（第二次不得再变更状态）');
  assert.equal(client.apply({ ...message }), false, '同一 (tick,seq,t) 的等价消息同样幂等');
  assert.equal(client.appliedKeys.length, 1);
});

test('test_snapshot_then_delta_ordering_is_preserved', () => {
  const client = new RenderClient();
  assert.equal(client.apply({ t: 'snapshot', tick: 50, seq: 1, state: {}, state_hash: 'a'.repeat(64) }), true);
  assert.equal(client.apply(delta(50, 2)), true);
  assert.equal(client.apply(delta(50, 1)), false);
  assert.equal(client.apply(delta(51, 1)), true);
  // 非法消息（缺 tick/seq）不得进入状态机
  assert.equal(client.apply({ t: 'delta', tick: 51, seq: 2, ops: [] } as never), true);
  assert.equal(client.apply({ t: 'delta' } as never), false);
});
