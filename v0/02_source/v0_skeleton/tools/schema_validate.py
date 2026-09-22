#!/usr/bin/env python3
"""JSON-Schema（draft 2020-12）校验薄封装：门禁链与能力校验器**共用同一实现**。

用途（round 3 · 修复迭代 2）：
  * **G3**（Raven N-3）：`verify_specs.sh` 必须**真跑一次** JSON-Schema 校验。此前 schema 只被当作
    「白名单来源」传给校验器，`additionalProperties:false` / `required` / `enum` / `pattern`
    **从未被真正执行** —— 于是「带采样却声明 deterministic」的负例要么只能写成 schema 非法
    （谁都没发现），要么根本写不进去（判据不可达）。
  * **G1**（Raven N-1 缓解 ③/④）：确定性执行体的返回值必须先过 `output_schema`
    才计入比对；「实现存在 + 输出合规 + 同输入同输出」三者齐备才算 `verified_impl`。

引擎 = `jsonschema` 库（本机 4.26.0）。**不可用即环境错误（调用方 fail-closed，exit 2）** ——
不做「降级为自研弱校验」的兜底，否则等于把判据悄悄放宽（`04 §11.9 LOW-6` 的教训：
判据口径不得在写入之后漂移）。
"""
from __future__ import annotations

import json
from pathlib import Path

try:  # pragma: no cover - 环境探测
    import jsonschema
    from jsonschema.validators import validator_for

    try:
        from importlib.metadata import version as _pkg_version

        _VERSION = _pkg_version("jsonschema")
    except Exception:  # noqa: BLE001
        _VERSION = "unknown"
    ENGINE = f"jsonschema {_VERSION}"
    _IMPORT_ERROR = ""
except Exception as _exc:  # noqa: BLE001
    jsonschema = None
    validator_for = None
    ENGINE = ""
    _IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"


class SchemaEngineUnavailable(RuntimeError):
    """jsonschema 不可用：属环境错误，调用方必须 fail-closed，不得降级成弱校验。"""


def engine_name() -> str:
    if not ENGINE:
        raise SchemaEngineUnavailable(f"jsonschema 不可用（{_IMPORT_ERROR}）")
    return ENGINE


def load(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(instance, schema: dict) -> list[str]:
    """返回**全部**校验错误（人类可读、按路径排序）；无错误 ⇒ 空列表。"""
    if not ENGINE:
        raise SchemaEngineUnavailable(f"jsonschema 不可用（{_IMPORT_ERROR}）")
    cls = validator_for(schema)
    cls.check_schema(schema)
    errors: list[str] = []
    for error in cls(schema).iter_errors(instance):
        path = "/".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{path}: {error.message}")
    return sorted(errors)


def check_schema(schema) -> list[str]:
    """校验 **schema 自身**是否合法（不校验实例）；返回错误列表（空 = 合法）。

    为什么需要它（`05 §10.5 R3F2-1`）：`capability.schema.json` 对 `output_schema` 只约束到
    「是一个对象」，**内嵌** schema 自身仍可以非法（例如 `enum` 不是数组）—— 于是派生计算
    （`minimal_instance`）会以 traceback 收场。门禁必须在**使用前**能判定
    「这个内嵌 schema 能不能用」，判据就在这里。

    调用方纪律：本函数**只回答合法性**，不做资源上界（上界是调用方的责任）；
    异常一律转成错误列表，不向外抛（`SchemaEngineUnavailable` 除外 —— 那是环境错误）。
    """
    if not ENGINE:
        raise SchemaEngineUnavailable(f"jsonschema 不可用（{_IMPORT_ERROR}）")
    try:
        cls = validator_for(schema)
        cls.check_schema(schema)
    except Exception as error:  # noqa: BLE001 —— 合法性问题一律变成返回值，不抛给调用方
        return [f"{type(error).__name__}: {str(error)[:200]}"]
    return []


def validate_file(instance_path, schema_path) -> list[str]:
    return validate(load(instance_path), load(schema_path))


def main(argv: list[str]) -> int:
    """极简 CLI（便于 reviewer 手工复跑）：<schema> <instance> [...]。"""
    import sys

    if len(argv) < 2:
        print("usage: schema_validate.py <schema.json> <instance.json> [...]", file=sys.stderr)
        return 2
    schema_path, instances = argv[0], argv[1:]
    try:
        schema = load(schema_path)
        print(f"engine = {engine_name()}")
    except SchemaEngineUnavailable as error:
        print(f"E_ENGINE: {error}", file=sys.stderr)
        return 2
    rc = 0
    for instance_path in instances:
        errors = validate(load(instance_path), schema)
        if errors:
            rc = 1
            print(f"FAIL  {instance_path}")
            for message in errors:
                print(f"      - {message}")
        else:
            print(f"PASS  {instance_path}")
    return rc


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
