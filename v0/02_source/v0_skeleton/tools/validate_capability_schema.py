#!/usr/bin/env python3
"""能力清单的**真** JSON-Schema 校验步骤（G3 / Raven N-3）。

背景（为什么必须有这一步）：此前 `verify_specs.sh` 只把 `capability.schema.json` 当作
「provider 属性白名单来源」传给校验器，schema 本身**从未被真正执行** ——
`additionalProperties:false` / `required` / `enum` / `pattern` 都不构成约束。于是
`x-determinism-gate.negative_example`（「带采样的 provider 声明为 deterministic」）只有两种落法：
要么 manifest **违反 schema**（谁都没发现），要么这个旋钮**根本写不进去**（判据不可达）。

本轮（修复迭代 2）把采样旋钮族写进 schema 白名单（`providers[].sampling` + 顶层同名键），
并把 `providers[].determinism` 列入 `required`；本脚本负责**真跑**校验。

用法：
  python3 validate_capability_schema.py --schema <capability.schema.json> --cap-dir <capabilities 目录>
  python3 validate_capability_schema.py --schema <capability.schema.json> <manifest.json> [...]
  python3 validate_capability_schema.py --schema <capability.schema.json> --cap-dir <目录> --selftest
退出码：0 = 全部合法（且自证成立）；1 = 有非法清单 / 自证不成立；2 = 用法 / 环境错误。
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

try:
    import schema_validate
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import schema_validate


def _targets(cap_dir: Path | None, explicit: list[str]) -> list[Path]:
    files = [Path(item) for item in explicit]
    if cap_dir is not None:
        files += sorted(cap_dir.glob("*.capability.json"))
    return files


def _validate_all(schema: dict, files: list[Path]) -> int:
    if not files:
        print("E_NO_TARGETS: 没有待校验的 manifest", file=sys.stderr)
        return 2
    failures = 0
    for path in files:
        try:
            instance = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            failures += 1
            print(f"FAIL  {path} :: 无法解析：{type(error).__name__}: {error}")
            continue
        errors = schema_validate.validate(instance, schema)
        if errors:
            failures += 1
            print(f"FAIL  {path} :: {len(errors)} 条不符合 schema")
            for message in errors[:8]:
                print(f"      - {message}")
        else:
            print(f"PASS  {path}")
    print(f"schema validate: checked={len(files)} failures={failures}")
    return 1 if failures else 0


def _selftest(schema: dict, cap_dir: Path) -> int:
    """自证：合法必须绿、五类非法必须红、**带采样（schema 合法）必须绿**（G3 判据可达性）。"""
    bases = sorted(cap_dir.glob("*.capability.json"))
    if not bases:
        print(f"E_SELFTEST_BASE: {cap_dir} 下没有 *.capability.json 作为合法基线", file=sys.stderr)
        return 2
    base = json.loads(bases[0].read_text(encoding="utf-8"))
    cases: list[tuple[str, dict, bool]] = []

    cases.append(("valid（合法基线，逐字复制）", copy.deepcopy(base), True))

    unknown = copy.deepcopy(base)
    unknown["rogue_top_level"] = 1
    cases.append(("unknown_property（顶层多一个属性）", unknown, False))

    bad_class = copy.deepcopy(base)
    bad_class["providers"][0]["class"] = "magic"
    cases.append(("bad_provider_class（class 不在枚举内）", bad_class, False))

    no_det = copy.deepcopy(base)
    no_det["providers"][0].pop("determinism", None)
    cases.append(("missing_determinism（G2：provider 必填字段缺失）", no_det, False))

    bad_sampling = copy.deepcopy(base)
    bad_sampling["providers"][0]["sampling"] = {"temperature": "hot"}
    cases.append(("sampling_wrong_type（sampling.temperature 类型错）", bad_sampling, False))

    legal_sampling = copy.deepcopy(base)
    legal_sampling["providers"][0]["sampling"] = {"temperature": 0.7, "top_p": 0.9}
    # G3 的核心：**带采样**的 manifest 现在是 schema 合法的 ⇒ 负例可由校验器判红（判据可达）。
    cases.append(("sampling_legal（带采样，schema 合法 ⇒ 必须绿）", legal_sampling, True))

    failures = 0
    with tempfile.TemporaryDirectory(prefix="dh-schema-selftest-") as tmp:
        for index, (name, instance, expect_ok) in enumerate(cases):
            path = Path(tmp) / f"case_{index:02d}.json"
            path.write_text(json.dumps(instance, ensure_ascii=False), encoding="utf-8")
            errors = schema_validate.validate(instance, schema)
            got_ok = not errors
            good = got_ok == expect_ok
            failures += 0 if good else 1
            print(f"[{'ok' if good else 'FAIL'}] selftest {name}: "
                  f"schema_legal={got_ok} expected={expect_ok}"
                  f"{'' if good else ' :: ' + '; '.join(errors[:2])}")
    print(f"selftest: {'ok（1 合法基线绿 + 4 类非法红 + 带采样合法绿 ⇒ 判据可达）' if not failures else 'FAIL'}")
    return 0 if not failures else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="validate-capability-schema")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--cap-dir", default=None)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("manifests", nargs="*")
    args = parser.parse_args(argv)

    try:
        schema = schema_validate.load(Path(args.schema))
        print(f"engine = {schema_validate.engine_name()}")
    except schema_validate.SchemaEngineUnavailable as error:
        print(f"E_SCHEMA_ENGINE: {error}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as error:
        print(f"E_SCHEMA: {type(error).__name__}: {error}", file=sys.stderr)
        return 2

    cap_dir = Path(args.cap_dir) if args.cap_dir else None
    if args.selftest:
        if cap_dir is None:
            print("E_ARGS: --selftest 需要 --cap-dir（取合法基线）", file=sys.stderr)
            return 2
        return _selftest(schema, cap_dir)
    return _validate_all(schema, _targets(cap_dir, args.manifests))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
