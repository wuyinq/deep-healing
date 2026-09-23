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
  python3 validate_capability_schema.py --schema <capability.schema.json> --cap-dir <目录> --selftest [--json]
退出码：0 = 全部合法（且自证成立）；1 = 有非法清单 / 自证不成立；2 = 用法 / 环境错误。

`--json`（M5.1 r2.6 / PM m5-08 §7.1）：额外打一行机器可读判定字段
`{"self_proof_ok": <bool>, "cases": N, "fired": N, "back_to_baseline": null, "engine": "<name>"}`
—— 门禁**自证项**读它，**不读退出码**（退出码把「真实树读数」与「探针读数」合成了一个）。
自证的**基线来源与被测树解耦**（PM §8.2 处置二 · 实现 ③）：合法基线是模块**内嵌夹具**，
**不再**从 `--cap-dir` 取（旧写法取 `sorted(cap_dir.glob(...))[0]`，改坏它会把自证一起染红）。
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


# ----------------------------------------------------------------- 内嵌自证夹具
# PM m5-08 §8.2 处置二 · 选实现 ③：**工具内嵌**的最小合法 fixture。
# 它与被测树（`--cap-dir`）**零交集** —— 改坏 cap_dir 下**任何一个** manifest（含实测的
# `bases[0] = embed.text@1.0.0`）都不会影响本夹具 ⇒ 自证判定与被测树解耦
# （对应 PM §8.3 的「6 次逐个注入」判据：每次都必须「自证绿 + 树项红」）。
# 内容只承载「schema 合法」这一件事，**不承载任何交付读数**（不是任何能力的标定值）。
EMBEDDED_LEGAL_BASELINE: dict = {
    "id": "embed.text",
    "version": "1.0.0",
    "slot": "embed.text",
    "input_schema": {"type": "object", "properties": {"text": {"type": "string"}},
                     "required": ["text"], "additionalProperties": False},
    "output_schema": {"type": "object", "properties": {"vector": {"type": "array"}},
                      "required": ["vector"], "additionalProperties": False},
    "providers": [{
        "class": "deterministic_rule",
        "impl": "builtin:embed_text_rule",
        "priority": 10,
        "determinism": "deterministic",
        "determinism_note": "pure：自证夹具内嵌规则（不读被测树、不落盘、无网络）",
    }],
    "cost": {"usd_per_1k_in": 0.0, "usd_per_1k_out": 0.0,
             "est_tokens_in": 0, "est_tokens_out": 0, "currency": "USD"},
    "latency_ms_budget": 100,
    "timeout_ms": 200,
    "fallback": {"on_timeout": "deterministic_stub", "on_error": "deterministic_stub",
                 "on_invalid_schema": "deterministic_stub",
                 "on_budget_exhausted": "deterministic_stub"},
    "determinism": {"mode": "pure",
                    "cassette_key_fields": ["capability_id", "capability_version",
                                            "canonical_input_hash", "provider"],
                    "seed_policy": "no_randomness"},
    "safety": {"secrets_in_context": False, "redact_fields": [],
               "max_output_bytes": 65536, "schema_strict": True},
    "calibration": {"sample_count": 1, "p50_ms": 1.0, "p90_ms": 2.0, "p95_ms": 3.0,
                    "p99_ms": 4.0, "max_ms": 5.0,
                    "derivation_rule": "自证夹具：非实测标定（只证判据可达，不承载交付读数）",
                    "derivation_rule_sha256": "0" * 64,
                    "candidate_strict_ms": 100, "candidate_loose_ms": 200,
                    "accepted_degradation_range": "0.00-0.30",
                    "command": "n/a（内嵌夹具）", "workdir": "n/a（内嵌夹具）", "exit": 0,
                    "log_path": "n/a（内嵌夹具）"},
    "rule_layer_adoption": {"allowed": True, "provider_classes_allowed": ["deterministic_rule"],
                            "consistency_check": {"required": True, "runs": 3}},
}


def _selftest(schema: dict, cap_dir: Path | None = None) -> tuple[int, int, int]:
    """自证：合法必须绿、五类非法必须红、**带采样（schema 合法）必须绿**（G3 判据可达性）。

    **基线来源与被测树解耦（M5.1 r2.6 / PM m5-08 §8.2 处置二 · 选实现 ③）**：
    合法基线 = 本模块**内嵌**的最小合法夹具 `EMBEDDED_LEGAL_BASELINE`（运行时深拷贝）。
    旧写法 `sorted(cap_dir.glob("*.capability.json"))[0]` 把**被测树**当成自证基线 ——
    实测 `bases[0] = embed.text@1.0.0.capability.json` ⇒ 改坏它时 `--selftest` 也变红，
    与「树脏而自证仍绿」的负对照①期望**相反**（PM §8.1 地雷表）。
    选项 ②（把基线快照进临时目录）不满足同一要求（快照源仍是被测树）⇒ 不采用；
    选 ③ 的理由：夹具与 `cap_dir` **零交集**，且不新增交付文件、无路径依赖。
    `cap_dir` 形参保留**仅为向后兼容调用面**（CLI 仍要求传 `--cap-dir`），**本函数不再读它**。

    返回 (退出码, 用例数, 达标用例数)。
    """
    base = copy.deepcopy(EMBEDDED_LEGAL_BASELINE)
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
    return (0 if not failures else 1), len(cases), len(cases) - failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="validate-capability-schema")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--cap-dir", default=None)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--json", action="store_true",
                        help="打一行机器可读判定字段 {self_proof_ok,cases,fired,back_to_baseline,engine}；"
                             "门禁自证项读它，**不读退出码**（PM m5-08 §三.1）")
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
            print("E_ARGS: --selftest 需要 --cap-dir（调用面兼容；自证基线已内嵌，本函数不读该目录）",
                  file=sys.stderr)
            return 2
        rc, cases, fired = _selftest(schema, cap_dir)
        if args.json:
            print(json.dumps({"self_proof_ok": rc == 0, "cases": cases, "fired": fired,
                              "back_to_baseline": None, "engine": schema_validate.engine_name()},
                             ensure_ascii=False, sort_keys=True))
        return rc
    return _validate_all(schema, _targets(cap_dir, args.manifests))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
