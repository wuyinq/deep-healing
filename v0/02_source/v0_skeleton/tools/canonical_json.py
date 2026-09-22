"""canonical JSON 与哈希工具（内核与离线工具共用同一实现）。

冻结规则（见 snapshot.schema.json 的 normalization）：
  - 键按 Unicode 码点字典序排序
  - 分隔符 "," 与 ":"，无空格
  - UTF-8，ensure_ascii=False
  - 整数不带小数点；浮点四舍五入到 6 位小数
  - 数组按 schema 声明显式排序（本模块只做序列化，不猜业务顺序）
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

FLOAT_DIGITS = 6


def _normalize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, FLOAT_DIGITS)
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    """返回规范化 JSON 文本（跨语言必须逐位一致）。"""
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_object(value: Any) -> str:
    return sha256_hex(canonical_bytes(value))


def chained_hash(prev_hash: str, body: Any) -> str:
    """事件哈希链：sha256(prev_hash || canonical_json(body))。"""
    return sha256_hex(prev_hash.encode("ascii") + canonical_bytes(body))


GENESIS_HASH = "0" * 64
