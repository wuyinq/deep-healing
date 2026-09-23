/**
 * 会话协议运行时（`session.protocol.schema.json` 的**逐字段**对应物）——M3 新增。
 *
 * 为什么要有它：契约里的 `additionalProperties:false` / `required` / 枚举 / `const` 只有在
 * **运行时真的被求值**时才算判据；否则「逐字段一致」只是一句声称（Raven N-3 的教训）。
 * 本模块是 L2 唯一的出入消息构造与校验点：
 *   - `validateClientMessage` 拒收多余字段 / 缺失字段 / 非法 kind / 非法 client_tick；
 *   - `validateServerMessage` 自检下行消息（含 `t` 的 allOf 条件必填）；
 *   - `validateCreateSessionRequest` 校验建会话请求体（`additionalProperties:false`）。
 *
 * 边界（硬）：本模块**不做**权限判定（`mode.js`）、**不做**限流（`policy.js`）、
 * **不碰**世界状态（内核是唯一权威写入点）。
 */

export const MESSAGE_TYPES = ['snapshot', 'delta', 'event', 'tick_meta', 'intent_ack', 'error'];

export const ERROR_CODES = [
  'E_MODE_READONLY',
  'E_FORBIDDEN_ACTION',
  'E_RATE_LIMITED',
  'E_COOLDOWN',
  'E_BUDGET_EXHAUSTED',
  'E_TARGET_UNKNOWN',
  'E_SCHEMA_INVALID',
  'E_SESSION_UNKNOWN',
  'E_SESSION_EXPIRED',
  'E_KERNEL_UNAVAILABLE',
  'E_PACK_INVALID',
  'E_CASSETTE_MISS',
];

/** V0 只实现 `delegate_instruction`；其余通道**即使 schema 枚举里有**也必须 `E_SCHEMA_INVALID`。 */
export const IMPLEMENTED_KINDS = ['delegate_instruction'];
export const DECLARED_KINDS = ['delegate_instruction', 'ghost_hand', 'avatar'];

export const SCHEMA_VERSION = '1.0.0';
export const TICK_RATE = 10;

const SESSION_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const HEX64_RE = /^[0-9a-f]{64}$/;

function isPlainObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function fail(reason, detail) {
  return { ok: false, reason, detail };
}

function ok(value) {
  return { ok: true, value };
}

/** 未知字段检查（对应 schema 的 `additionalProperties:false`）。 */
function extraKeys(object, allowed) {
  return Object.keys(object).filter((key) => !allowed.includes(key));
}

export function validateCreateSessionRequest(body) {
  if (!isPlainObject(body)) return fail('E_SCHEMA_INVALID', 'request body must be an object');
  const extra = extraKeys(body, ['mode', 'district_pack_id', 'client_version', 'record']);
  if (extra.length) return fail('E_SCHEMA_INVALID', `unexpected field(s): ${extra.join(',')}`);
  if (!['observe', 'participate'].includes(body.mode)) {
    return fail('E_SCHEMA_INVALID', `mode must be observe|participate, got ${JSON.stringify(body.mode)}`);
  }
  if (typeof body.district_pack_id !== 'string' || body.district_pack_id.length === 0) {
    return fail('E_SCHEMA_INVALID', 'district_pack_id must be a non-empty string');
  }
  if (typeof body.client_version !== 'string' || body.client_version.length === 0) {
    return fail('E_SCHEMA_INVALID', 'client_version must be a non-empty string');
  }
  if (body.record !== undefined && typeof body.record !== 'boolean') {
    return fail('E_SCHEMA_INVALID', 'record must be a boolean');
  }
  return ok({
    mode: body.mode,
    district_pack_id: body.district_pack_id,
    client_version: body.client_version,
    record: body.record === true,
  });
}

export function validateClientMessage(message) {
  if (!isPlainObject(message)) return fail('E_SCHEMA_INVALID', 'message must be an object');
  const extra = extraKeys(message, ['t', 'id', 'kind', 'target', 'payload', 'client_tick']);
  if (extra.length) return fail('E_SCHEMA_INVALID', `unexpected field(s): ${extra.join(',')}`);
  if (message.t !== 'intent') return fail('E_SCHEMA_INVALID', `t must be "intent", got ${JSON.stringify(message.t)}`);
  if (typeof message.id !== 'string' || message.id.length === 0) {
    return fail('E_SCHEMA_INVALID', 'id must be a non-empty string');
  }
  if (message.kind !== undefined && !DECLARED_KINDS.includes(message.kind)) {
    return fail('E_SCHEMA_INVALID', `kind not in enum: ${JSON.stringify(message.kind)}`);
  }
  if (message.kind !== undefined && !IMPLEMENTED_KINDS.includes(message.kind)) {
    // schema 合法但 V0 未实现 ⇒ 契约 `$comment` 冻结：返回 E_SCHEMA_INVALID
    return fail('E_SCHEMA_INVALID', `channel ${message.kind} is not implemented in V0`);
  }
  if (message.target !== undefined && typeof message.target !== 'string') {
    return fail('E_SCHEMA_INVALID', 'target must be a string');
  }
  if (message.client_tick !== undefined) {
    if (!Number.isInteger(message.client_tick) || message.client_tick < 0) {
      return fail('E_SCHEMA_INVALID', 'client_tick must be an integer >= 0');
    }
  }
  if (message.payload !== undefined) {
    if (!isPlainObject(message.payload)) return fail('E_SCHEMA_INVALID', 'payload must be an object');
    const payloadExtra = extraKeys(message.payload, ['instruction_text', 'urgency']);
    if (payloadExtra.length) {
      return fail('E_SCHEMA_INVALID', `unexpected payload field(s): ${payloadExtra.join(',')}`);
    }
    if (message.payload.instruction_text !== undefined) {
      if (typeof message.payload.instruction_text !== 'string') {
        return fail('E_SCHEMA_INVALID', 'payload.instruction_text must be a string');
      }
      if (message.payload.instruction_text.length > 1000) {
        return fail('E_SCHEMA_INVALID', 'payload.instruction_text exceeds maxLength 1000');
      }
    }
    if (message.payload.urgency !== undefined) {
      const urgency = message.payload.urgency;
      if (typeof urgency !== 'number' || urgency < 0 || urgency > 1) {
        return fail('E_SCHEMA_INVALID', 'payload.urgency must be a number in [0,1]');
      }
    }
  }
  return ok(message);
}

/** 下行消息自检：与 schema 的 `allOf` 条件必填逐条对应。 */
export function validateServerMessage(message) {
  if (!isPlainObject(message)) return fail('E_SCHEMA_INVALID', 'message must be an object');
  if (!MESSAGE_TYPES.includes(message.t)) return fail('E_SCHEMA_INVALID', `unknown t: ${message.t}`);
  if (!Number.isInteger(message.tick) || message.tick < 0) return fail('E_SCHEMA_INVALID', 'tick must be integer >= 0');
  if (!Number.isInteger(message.seq) || message.seq < 0) return fail('E_SCHEMA_INVALID', 'seq must be integer >= 0');
  const extra = extraKeys(message, [
    't', 'tick', 'seq', 'state', 'state_hash', 'ops', 'event', 'ms',
    'id', 'status', 'reason', 'detail', 'impact_budget_remaining',
  ]);
  if (extra.length) return fail('E_SCHEMA_INVALID', `unexpected field(s): ${extra.join(',')}`);
  if (message.t === 'snapshot') {
    if (!isPlainObject(message.state)) return fail('E_SCHEMA_INVALID', 'snapshot requires state');
    if (typeof message.state_hash !== 'string' || !HEX64_RE.test(message.state_hash)) {
      return fail('E_SCHEMA_INVALID', 'snapshot requires state_hash (64 hex)');
    }
  }
  if (message.t === 'delta' && !Array.isArray(message.ops)) return fail('E_SCHEMA_INVALID', 'delta requires ops[]');
  if (message.t === 'event' && !isPlainObject(message.event)) return fail('E_SCHEMA_INVALID', 'event requires event');
  if (message.t === 'tick_meta' && typeof message.ms !== 'number') return fail('E_SCHEMA_INVALID', 'tick_meta requires ms');
  if (message.t === 'intent_ack') {
    if (typeof message.id !== 'string') return fail('E_SCHEMA_INVALID', 'intent_ack requires id');
    if (!['queued', 'rejected', 'applied'].includes(message.status)) {
      return fail('E_SCHEMA_INVALID', 'intent_ack requires status in queued|rejected|applied');
    }
    if (message.status === 'rejected' && !ERROR_CODES.includes(message.reason)) {
      return fail('E_SCHEMA_INVALID', 'rejected intent_ack requires a frozen error code');
    }
  }
  if (message.t === 'error' && !ERROR_CODES.includes(message.reason)) {
    return fail('E_SCHEMA_INVALID', 'error requires a frozen error code');
  }
  return ok(message);
}

// ------------------------------------------------------------------ 构造器（字段显式，不依赖 provider 默认值）
export function makeSnapshot({ tick, seq, state, stateHash }) {
  return { t: 'snapshot', tick, seq, state, state_hash: stateHash };
}

export function makeDelta({ tick, seq, ops }) {
  return { t: 'delta', tick, seq, ops };
}

export function makeEvent({ tick, seq, event }) {
  return { t: 'event', tick, seq, event };
}

export function makeTickMeta({ tick, seq, ms }) {
  return { t: 'tick_meta', tick, seq, ms };
}

export function makeIntentAck({ tick, seq, id, status, reason, detail, impactBudgetRemaining }) {
  const message = { t: 'intent_ack', tick, seq, id, status };
  if (reason !== undefined) message.reason = reason;
  if (detail !== undefined) message.detail = detail;
  if (impactBudgetRemaining !== undefined) message.impact_budget_remaining = impactBudgetRemaining;
  return message;
}

export function makeError({ tick, seq, reason, detail }) {
  return { t: 'error', tick, seq, reason, detail };
}

export function isSessionId(value) {
  return typeof value === 'string' && SESSION_ID_RE.test(value);
}
