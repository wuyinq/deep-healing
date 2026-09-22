/**
 * 会话层 RED 用例（AC-4）——V0 骨架。
 * 运行：cd 02_source/v0_skeleton/session && node --test test/
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { checkUpstream, canSubscribe } from '../src/mode.js';

test('observe 会话上行 intent 被拒（E_MODE_READONLY）', () => {
  assert.equal(checkUpstream('observe'), 'E_MODE_READONLY');
});

test('participate 会话允许上行 intent', () => {
  assert.equal(checkUpstream('participate'), null);
});

test('两种模式都允许只读订阅', () => {
  assert.equal(canSubscribe('observe'), true);
  assert.equal(canSubscribe('participate'), true);
});

test('未知模式必须被拒（E_SCHEMA_INVALID）', () => {
  assert.throws(() => canSubscribe('spectator'), /E_SCHEMA_INVALID/);
});

test('rate_limit / cooldown / impact_budget 待实现（RED）', { skip: 'pending InterventionPolicy implementation' }, () => {
  assert.ok(false);
});
