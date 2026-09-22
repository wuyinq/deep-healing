#!/usr/bin/env python3
"""W0e · D-0.9 时间预算标定工具链（V0-M1）：`dist → derive → degrade → check`。

口径与 `spikes/s5-latency-calibration/`（round 3 / 002 工作区）一致：
  - 最近秩分位（nearest-rank：k = ceil(q*N)，取排序后第 k 个样本）；
  - `ceil_to(m, x) = m * ceil(x / m)`；
  - `strict = ceil_to(50, p95) + offset`、`adopted = ceil_to(100, p95) + offset`、
    `loose = ceil_to(500, p99 + 1000) + offset`、`budget = ceil_to(50, p90) + offset`；
  - 逐能力 `offset_ms` 见 `DERIVATION-RULE.frozen.md` 的表（本文件镜像为 `CAP_OFFSET_MS`，
    并由 `tests/test_calibrate_latency.py` 断言「镜像 == 冻结文件里的表」以防漂移）。

本轮硬约束（设计 §4.9）：
  - 两份冻结物（`DERIVATION-RULE.frozen.md` / `ACCEPTED-DEGRADATION-RANGE.frozen.md`）必须是
    002 工作区同名文件的**逐字节副本**，sha256 由 `registry` 登记；
  - **禁止**修改 `02_source/**` 的任何 `timeout_ms` / `calibration` 声明值（数值重标 = Q1，归 PM）；
    因此本工具的 `degrade` **不写能力清单**，只测量「在声明值下会有多少调用被推入降级」；
  - 远端降级 / 样本被污染 ⇒ `derive` fail-closed 拒绝产出声明值，如实记 GAP，绝不编数。

凭据：只从环境变量 `HERMES_CUSTOM_TOKENFAB_API_KEY` 读取；**值绝不落盘**。
本工具**不写任何 HTTP transcript**（只记 latency_ms / http_status / tokens），
从根上排除「transcript 未脱敏」这类风险（预审 G3）。

用法（workdir = `02_source/v0_skeleton/kernel`）：
    python3 tools/calibrate_latency.py registry
    python3 tools/calibrate_latency.py dist --samples 24 --timeout-ms 60000 \
        --out ../../../../spikes/s5-latency-calibration/logs/latency.distribution.json
    python3 tools/calibrate_latency.py derive --dist <dist.json> --out <calibration.json>
    python3 tools/calibrate_latency.py degrade --formula adopted --runs 10 --out <degrade.json>
    python3 tools/calibrate_latency.py check --calibration <calibration.json> --dist <dist.json>

自证（合成样本，明确标注 synthetic；不消耗凭据、不联网）：
    python3 tools/calibrate_latency.py dist --synthetic clean   --out <clean.json>
    python3 tools/calibrate_latency.py dist --synthetic polluted --out <polluted.json>

退出码：0 = 该子命令成立；1 = 不成立（样本不足 / 环境降级 / 区间外 / 声明值不一致）；2 = 用法错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent          # <ws>/02_source/v0_skeleton/kernel/tools
KERNEL_ROOT = HERE.parent                        # <ws>/02_source/v0_skeleton/kernel
V0_SKELETON = KERNEL_ROOT.parent                 # <ws>/02_source/v0_skeleton
SOURCE_ROOT = V0_SKELETON.parent                 # <ws>/02_source
WS_ROOT = SOURCE_ROOT.parent                     # <ws>

SPIKE_DIR = WS_ROOT / "spikes" / "s5-latency-calibration"
LOGS_DIR = SPIKE_DIR / "logs"
RULE_FILE = SPIKE_DIR / "DERIVATION-RULE.frozen.md"
RANGE_FILE = SPIKE_DIR / "ACCEPTED-DEGRADATION-RANGE.frozen.md"
ENVCLASS_FILE = SPIKE_DIR / "ENVIRONMENT-CLASS.frozen.md"
REGISTRY = SPIKE_DIR / "calibration.registry.json"

BASE_URL = os.environ.get("DEEPHEALING_BASE_URL", "https://api.tokenfab.cn/v1")
DEFAULT_MODEL = "deepseek-v4.1-flash"
CREDENTIAL_ENV = "HERMES_CUSTOM_TOKENFAB_API_KEY"

# 冻结物 sha256（预审 C3 关闭判据；`registry` 会断言盘上文件与这两个值一致）
FROZEN_RULE_SHA256 = "7590eab4b765671860eaa50b68de807606581bfdd439cb3aa6fe2d953edb0feb"
FROZEN_RANGE_SHA256 = "713dba90df07f63e685fc98dcf276769ba37f2617f9c8a4b38319d8c174bddb4"

# DERIVATION-RULE.frozen.md 的 offset_ms 表（镜像；由测试断言防漂移）
CAP_OFFSET_MS = {
    "emotion.appraise": 0,
    "intent.plan": 500,
    "memory.reflect": 1000,
    "relation.infer": 0,
    "embed.text": 250,
    "imagine.predict": 500,
    "imagine.rollout": 750,
}

# ACCEPTED-DEGRADATION-RANGE.frozen.md 的三行区间（镜像）
ACCEPTED_RANGE = {"strict": (0.00, 0.40), "adopted": (0.00, 0.30), "loose": (0.00, 0.10)}

# ENVIRONMENT-CLASS.frozen.md 的判定阈值（镜像）
MIN_SAMPLES = 20
MAX_P90_MS = 20000.0
MAX_P90_P50_RATIO = 3.0

SYNTHETIC_CLEAN = [820.0, 940.0, 1010.0, 1180.0, 1240.0, 1310.0, 1450.0, 1520.0,
                   1580.0, 1610.0, 1720.0, 1840.0, 1900.0, 2050.0, 2180.0, 2260.0,
                   2410.0, 2580.0, 2760.0, 2980.0, 3120.0, 3340.0, 3610.0, 3980.0]
SYNTHETIC_POLLUTED = [3120.0, 3486.0, 4102.0, 4330.0, 5120.0, 5560.0, 6010.0, 6420.0,
                      6880.0, 7120.0, 7443.0, 8010.0, 9020.0, 10440.0, 12380.0, 14820.0,
                      18630.0, 22710.0, 28460.0, 33280.0, 38110.0, 42110.0, 48630.0, 54031.0]


# --------------------------------------------------------------------------- helpers
def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nearest_rank(values: list[float], q: float) -> float:
    ordered = sorted(values)
    k = max(1, math.ceil(q * len(ordered)))
    return ordered[k - 1]


def ceil_to(step: int, value: float) -> int:
    return int(step * math.ceil(value / step))


def mtime_iso(path: Path) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(path.stat().st_mtime))


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def classify(p50: float | None, p90: float | None, ok_count: int, failed_count: int) -> tuple[str, list[str]]:
    """环境可用性判定（阈值与理由见 ENVIRONMENT-CLASS.frozen.md，测量前声明）。"""
    reasons: list[str] = []
    if ok_count < MIN_SAMPLES:
        reasons.append(f"sample_count_ok={ok_count} < {MIN_SAMPLES}")
    if failed_count != 0:
        reasons.append(f"sample_count_failed={failed_count} != 0")
    if p90 is None:
        reasons.append("p90 unavailable")
    else:
        if p90 > MAX_P90_MS:
            reasons.append(f"p90_ms={p90} > {MAX_P90_MS}")
        if p50:
            ratio = p90 / p50
            if ratio > MAX_P90_P50_RATIO:
                reasons.append(f"p90/p50={round(ratio, 3)} > {MAX_P90_P50_RATIO}")
    return ("degraded" if reasons else "usable"), reasons


def _http_chat(prompt: str, timeout_ms: int, model: str) -> dict:
    """一次真实 OpenAI 兼容 chat 调用。凭据只从环境变量读，**不回显、不落盘**。"""
    credential = os.environ.get(CREDENTIAL_ENV)
    if not credential:
        raise RuntimeError(f"{CREDENTIAL_ENV} not set in environment")
    body = json.dumps(
        {"model": model, "messages": [{"role": "user", "content": prompt}],
         "temperature": 0, "max_tokens": 32},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json",
                 # 日志/产物里只允许出现脱敏形态
                 "Authorization": f"Bearer {credential}"},
    )
    started = time.time()
    with urllib.request.urlopen(request, timeout=timeout_ms / 1000.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
        status = response.status
    latency_ms = round((time.time() - started) * 1000, 3)
    usage = payload.get("usage") or {}
    return {
        "latency_ms": latency_ms,
        "http_status": status,
        "tokens": {"in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")},
    }


# --------------------------------------------------------------------------- registry
def cmd_registry(_args) -> int:
    """登记三份冻结物的 sha256/mtime（**幂等**）。

    **幂等性（修复轮 2 / F1 / Sentinel Bug#9）**：修复前每次都写入
    `registry_written_at: time.strftime(...)` ⇒ 每跑一次就改写
    `spikes/s5-latency-calibration/calibration.registry.json`，使 `V0_M1.sha256` 的自校验
    由「642 OK / 0 非 OK」变成「641 OK / 1 FAILED」（**任何**独立复跑 AC-M1-6 工具链首步的人都会看到）。

    现在的口径：`registry_written_at` 是**首次写入时刻**，不再是「本次执行时刻」——
      - 若盘上既有文件的**全部内容字段**（除 `registry_written_at`）与新算值一致 ⇒ **沿用原时刻**，
        且**内容逐字节相同则不写盘**（`unchanged`）；
      - 否则（首次 / 冻结物真的变了）⇒ 写入当前时刻。
    ⇒ 连跑两次 `registry` 后文件 sha256 **不变**（关闭判据）。
    """
    for path, expected in ((RULE_FILE, FROZEN_RULE_SHA256), (RANGE_FILE, FROZEN_RANGE_SHA256)):
        actual = sha256_file(path)
        if actual != expected:
            print(f"E_FROZEN_MISMATCH: {path} sha256={actual} expected={expected}", file=sys.stderr)
            return 1
    document = {
        "frozen_rule": {"path": str(RULE_FILE), "sha256": sha256_file(RULE_FILE), "mtime": mtime_iso(RULE_FILE)},
        "accepted_degradation_range": {"path": str(RANGE_FILE), "sha256": sha256_file(RANGE_FILE),
                                       "mtime": mtime_iso(RANGE_FILE)},
        "environment_class_rule": {"path": str(ENVCLASS_FILE), "sha256": sha256_file(ENVCLASS_FILE),
                                   "mtime": mtime_iso(ENVCLASS_FILE)},
        "note": "规则 / 区间 / 环境判定三份冻结物必须先于测量落盘；本文件即「时间戳顺序」的登记处（防自证第 1/3/4 条）。",
    }

    written_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if REGISTRY.is_file():
        try:
            existing = json.loads(REGISTRY.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        if {k: v for k, v in existing.items() if k != "registry_written_at"} == document:
            written_at = existing["registry_written_at"]        # 沿用首次写入时刻 ⇒ 内容稳定
    document["registry_written_at"] = written_at

    rendered = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    unchanged = REGISTRY.is_file() and REGISTRY.read_text(encoding="utf-8") == rendered
    if not unchanged:
        _write_json(REGISTRY, document)
    print(json.dumps({"registry": str(REGISTRY), "unchanged": unchanged,
                      "registry_written_at": written_at, "sha256": sha256_file(REGISTRY)},
                     ensure_ascii=False, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- dist
def cmd_dist(args) -> int:
    synthetic = args.synthetic
    samples: list[dict] = []
    errors: list[dict] = []

    if synthetic:
        values = SYNTHETIC_CLEAN if synthetic == "clean" else SYNTHETIC_POLLUTED
        for index, value in enumerate(values):
            samples.append({"i": index, "latency_ms": value, "http_status": None, "tokens": None, "ok": True})
            print(f"sample {index + 1}/{len(values)}: latency_ms={value} (synthetic)")
    else:
        prompt = "Reply with the single word: ok"
        for index in range(args.samples):
            try:
                meta = _http_chat(prompt, args.timeout_ms, args.model)
                samples.append({"i": index, **meta, "ok": True})
            except Exception as exc:  # noqa: BLE001 —— 失败样本必须如实记，不得静默丢弃
                errors.append({"i": index, "error": type(exc).__name__, "detail": str(exc)[:200]})
                samples.append({"i": index, "latency_ms": None, "ok": False})
            print(f"sample {index + 1}/{args.samples}: latency_ms={samples[-1]['latency_ms']}")

    latencies = [s["latency_ms"] for s in samples if s["latency_ms"] is not None]
    p50 = nearest_rank(latencies, 0.50) if latencies else None
    p90 = nearest_rank(latencies, 0.90) if latencies else None
    p95 = nearest_rank(latencies, 0.95) if latencies else None
    p99 = nearest_rank(latencies, 0.99) if latencies else None
    environment_class, reasons = classify(p50, p90, len(latencies), len(errors))

    document = {
        "kind": "latency.distribution",
        "synthetic": synthetic or None,
        "api_base": None if synthetic else BASE_URL,
        "model": None if synthetic else args.model,
        "request_timeout_ms": args.timeout_ms,
        "sample_count_requested": args.samples if not synthetic else len(samples),
        "sample_count_ok": len(latencies),
        "sample_count_failed": len(errors),
        "samples": samples,
        "errors": errors,
        "p50_ms": p50, "p90_ms": p90, "p95_ms": p95, "p99_ms": p99,
        "min_ms": min(latencies) if latencies else None,
        "max_ms": max(latencies) if latencies else None,
        "environment_class": environment_class,
        "environment_class_reasons": reasons,
        "credential_source": CREDENTIAL_ENV if not synthetic else None,
        "credential_redaction": "Authorization: Bearer ***REDACTED***" if not synthetic else None,
        "transcript_written": False,
        "prompt_scope": (
            "minimal single-turn chat completion (max_tokens=32) —— 代表**远端通道**的延迟，"
            "不代表某个 capability 专属 prompt 形状（那属 W3 providers，本轮不在范围）"
        ) if not synthetic else "synthetic fixture (no network, no credential)",
        "command": f"python3 tools/calibrate_latency.py dist --samples {args.samples} --timeout-ms {args.timeout_ms}"
                   + (f" --synthetic {synthetic}" if synthetic else ""),
        "workdir": str(KERNEL_ROOT),
        "log_path": str(LOGS_DIR / "calibrate_latency.console.log"),
        "note": "逐次真实远端调用；失败样本单独列在 errors，不静默丢弃。本工具不写 HTTP transcript。",
    }
    _write_json(Path(args.out), document)
    print(json.dumps({k: document[k] for k in ("sample_count_ok", "sample_count_failed", "p50_ms", "p90_ms",
                                               "p95_ms", "p99_ms", "max_ms", "environment_class")},
                     ensure_ascii=False, sort_keys=True))
    if environment_class != "usable":
        print(f"GAP: 环境判为 degraded（{'; '.join(reasons)}）⇒ derive 将 fail-closed 拒绝产出声明值", file=sys.stderr)
        return 1
    return 0


# --------------------------------------------------------------------------- derive
def cmd_derive(args) -> int:
    dist = json.loads(Path(args.dist).read_text(encoding="utf-8"))
    p50, p90, p95, p99, mx = (dist["p50_ms"], dist["p90_ms"], dist["p95_ms"], dist["p99_ms"], dist["max_ms"])
    if p95 is None:
        print("GAP: 分布为空，无法推导", file=sys.stderr)
        return 1

    environment_class, reasons = classify(p50, p90, dist["sample_count_ok"], dist["sample_count_failed"])
    per_cap = {
        cap: {
            "offset_ms": offset,
            "strict_candidate_ms": ceil_to(50, p95) + offset,
            "adopted_ms": ceil_to(100, p95) + offset,
            "loose_candidate_ms": ceil_to(500, p99 + 1000) + offset,
            "latency_ms_budget_ms": ceil_to(50, p90) + offset,
        }
        for cap, offset in sorted(CAP_OFFSET_MS.items())
    }
    document = {
        "kind": "latency.calibration",
        "distribution_log": str(Path(args.dist)),
        "sample_count": dist["sample_count_ok"],
        "environment_class": environment_class,
        "environment_class_reasons": reasons,
        "refuses_to_declare": environment_class != "usable",
        "four_value_table": {"p50_ms": p50, "p90_ms": p90, "p95_ms": p95, "p99_ms": p99, "max_ms": mx,
                             "strict_candidate_ms": ceil_to(50, p95), "adopted_ms": ceil_to(100, p95),
                             "loose_candidate_ms": ceil_to(500, p99 + 1000)},
        "derivation_rule_sha256": sha256_file(RULE_FILE),
        "derivation_rule_mtime": mtime_iso(RULE_FILE),
        "distribution_log_mtime": mtime_iso(Path(args.dist)),
        "rule_frozen_before_measurement": RULE_FILE.stat().st_mtime < Path(args.dist).stat().st_mtime,
        "adopted_differs_from_max": ceil_to(100, p95) != mx,
        "timeout_ge_p95": all(v["adopted_ms"] >= p95 for v in per_cap.values()),
        "accepted_degradation_range": {k: f"{v[0]:.2f}-{v[1]:.2f}" for k, v in sorted(ACCEPTED_RANGE.items())},
        "per_capability": per_cap if environment_class == "usable" else {},
        "command": f"python3 tools/calibrate_latency.py derive --dist {args.dist}",
        "workdir": str(KERNEL_ROOT),
        "log_path": str(LOGS_DIR / "calibrate_latency.console.log"),
    }
    _write_json(Path(args.out), document)
    print(json.dumps({"environment_class": environment_class, "refuses_to_declare": document["refuses_to_declare"],
                      "four_value_table": document["four_value_table"],
                      "rule_frozen_before_measurement": document["rule_frozen_before_measurement"],
                      "adopted_differs_from_max": document["adopted_differs_from_max"]},
                     ensure_ascii=False, sort_keys=True))

    if environment_class != "usable":
        print(f"GAP: 环境 degraded（{'; '.join(reasons)}）⇒ fail-closed，不产出任何声明值", file=sys.stderr)
        return 1
    if not document["rule_frozen_before_measurement"]:
        print("E_RULE_NOT_FROZEN_FIRST: 规则文件 mtime 不早于分布日志", file=sys.stderr)
        return 1
    if not document["adopted_differs_from_max"]:
        print("E_ADOPTED_EQUALS_MAX: 采用值等于当次实测最大值（规则被禁用分支）", file=sys.stderr)
        return 1
    return 0


# --------------------------------------------------------------------------- degrade
def _formula_key(formula: str) -> str:
    return {"strict": "strict_candidate_ms", "adopted": "adopted_ms", "loose": "loose_candidate_ms"}[formula]


def cmd_degrade(args) -> int:
    calibration = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
    if calibration.get("refuses_to_declare"):
        print("GAP: 标定未产出声明值（environment degraded）⇒ 降级率无从测量，fail-closed", file=sys.stderr)
        return 1
    key = _formula_key(args.formula)
    declared = {cap: values[key] for cap, values in sorted(calibration["per_capability"].items())}

    # 本工具**不写能力清单**（写集禁止改 02_source 的 timeout_ms）；只测「在声明值下有多少调用会降级」。
    runs: list[dict] = []
    if args.synthetic:
        base = SYNTHETIC_CLEAN if args.synthetic == "clean" else SYNTHETIC_POLLUTED
        timeout_ms = declared["emotion.appraise"]
        for index in range(args.runs):
            latency = base[index % len(base)]
            runs.append({"i": index, "latency_ms": latency, "timeout_ms": timeout_ms,
                         "degraded": latency > timeout_ms, "synthetic": True})
    else:
        timeout_ms = declared["emotion.appraise"]
        for index in range(args.runs):
            try:
                meta = _http_chat("Reply with the single word: ok", timeout_ms, args.model)
                runs.append({"i": index, "latency_ms": meta["latency_ms"], "timeout_ms": timeout_ms,
                             "degraded": meta["latency_ms"] > timeout_ms})
            except Exception as exc:  # noqa: BLE001
                runs.append({"i": index, "latency_ms": None, "timeout_ms": timeout_ms, "degraded": True,
                             "error": type(exc).__name__})
            print(f"degrade run {index + 1}/{args.runs}: {runs[-1]}")

    degraded = sum(1 for run in runs if run["degraded"])
    rate = round(degraded / len(runs), 6) if runs else None
    low, high = ACCEPTED_RANGE[args.formula]
    document = {
        "kind": "degradation.rate",
        "formula": args.formula,
        "declared_value_key": key,
        "declared_timeout_ms": declared["emotion.appraise"],
        "declared_values": declared,
        "runs": runs,
        "runs_count": len(runs),
        "degraded_count": degraded,
        "degradation_rate": rate,
        "accepted_range": [low, high],
        "within_accepted_range": (rate is not None and low <= rate <= high),
        "synthetic": args.synthetic or None,
        "credential_source": CREDENTIAL_ENV if not args.synthetic else None,
        "transcript_written": False,
        "command": f"python3 tools/calibrate_latency.py degrade --formula {args.formula} --runs {args.runs}",
        "workdir": str(KERNEL_ROOT),
        "log_path": str(LOGS_DIR / "calibrate_latency.console.log"),
    }
    _write_json(Path(args.out), document)
    print(json.dumps({k: document[k] for k in ("formula", "declared_timeout_ms", "runs_count",
                                               "degraded_count", "degradation_rate", "accepted_range",
                                               "within_accepted_range")}, ensure_ascii=False, sort_keys=True))
    return 0 if document["within_accepted_range"] else 1


# --------------------------------------------------------------------------- check
def cmd_check(args) -> int:
    problems: list[str] = []
    calibration = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
    dist_path = Path(args.dist or calibration["distribution_log"])
    dist = json.loads(dist_path.read_text(encoding="utf-8"))

    # ① 规则文件 mtime 早于分布日志 + 冻结物 sha256 与 round-3 逐字节一致
    if not RULE_FILE.stat().st_mtime < dist_path.stat().st_mtime:
        problems.append("rule file mtime is not earlier than the distribution log")
    if sha256_file(RULE_FILE) != FROZEN_RULE_SHA256:
        problems.append(f"DERIVATION-RULE.frozen.md sha256 != {FROZEN_RULE_SHA256}")
    if sha256_file(RANGE_FILE) != FROZEN_RANGE_SHA256:
        problems.append(f"ACCEPTED-DEGRADATION-RANGE.frozen.md sha256 != {FROZEN_RANGE_SHA256}")

    # ② 独立重算（不信任 calibration.json 的自报值）—— 修复轮 C5：p50/p90/p95/p99/max **五个量全部**重算
    latencies = [s["latency_ms"] for s in dist["samples"] if s.get("latency_ms") is not None]
    recomputed: dict[str, float | None] = {}
    if latencies:
        recomputed = {
            "p50_ms": nearest_rank(latencies, 0.50),
            "p90_ms": nearest_rank(latencies, 0.90),
            "p95_ms": nearest_rank(latencies, 0.95),
            "p99_ms": nearest_rank(latencies, 0.99),
            "max_ms": max(latencies),
        }
        for name in ("p50_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms"):
            recorded = calibration["four_value_table"].get(name)
            if recorded != recomputed[name]:
                problems.append(
                    f"calibration {name} != independently recomputed {name} "
                    f"(recorded={recorded} recomputed={recomputed[name]})"
                )

    if calibration.get("refuses_to_declare"):
        print(json.dumps({"environment_class": calibration["environment_class"],
                          "refuses_to_declare": True,
                          "four_value_table": calibration["four_value_table"],
                          "frozen_sha256_ok": sha256_file(RULE_FILE) == FROZEN_RULE_SHA256
                          and sha256_file(RANGE_FILE) == FROZEN_RANGE_SHA256,
                          "problems": problems}, ensure_ascii=False, sort_keys=True))
        print("GAP: 标定 fail-closed（环境 degraded）⇒ 判据 ②③④ 无从成立；判据 ① 已由本命令断言", file=sys.stderr)
        return 1

    # ③ timeout_ms >= p95 且 != max（逐能力）；判据 ② 的重算值在此复用
    p90 = recomputed.get("p90_ms")
    p95 = recomputed.get("p95_ms")
    mx = recomputed.get("max_ms")
    if p95 is None or p90 is None or mx is None:
        problems.append("distribution has no usable samples ⇒ criteria (2)/(3) cannot be evaluated")

    # ③b **结构性塌缩**（修复轮 C4 / 预审 R5、Sentinel Bug#5）：`strict` 与 `adopted` 必须是**两个不同**
    #     的声明值 —— 冻结区间文件对 adopted 行的理由是「采用值比严值**松一档**，降级率必须明显低于严值」。
    #     当 `ceil_to(50,p95) == ceil_to(100,p95)`（p95 落在同一取整窗口）时两者塌缩成同一数值，
    #     判据③ 的「三行对照」实际只剩**两条独立探针** ⇒ 该前提**不成立**。
    #     它与普通区间越界**分开报告**（成因不同：一个是测量越界，一个是判据口径退化）。
    collapsed = sorted(
        cap for cap, values in calibration["per_capability"].items()
        if values["adopted_ms"] == values["strict_candidate_ms"]
    )

    for cap, values in sorted(calibration["per_capability"].items()):
        if p95 is not None and values["adopted_ms"] < p95:
            problems.append(f"{cap}: adopted_ms={values['adopted_ms']} < p95={p95}")
        if mx is not None and values["adopted_ms"] == mx:
            problems.append(f"{cap}: adopted_ms == max_ms")
        if p90 is not None and values["latency_ms_budget_ms"] < p90:
            problems.append(f"{cap}: latency_ms_budget_ms < p90")

    # ④ 02_source 现有声明值必须与本轮推导值**一致或明确标注未重标**（Q1 归 PM，本轮禁止改）
    if args.cap_dir:
        for cap_path in sorted(Path(args.cap_dir).glob("*.capability.json")):
            doc = json.loads(cap_path.read_text(encoding="utf-8"))
            if doc["id"] not in calibration["per_capability"]:
                continue
            expected = calibration["per_capability"][doc["id"]]["adopted_ms"]
            if doc["timeout_ms"] != expected:
                print(f"INFO {doc['id']}: 盘上 timeout_ms={doc['timeout_ms']} != 本轮推导 {expected}"
                      f"（Q1 未重标，归 PM；本轮**不得**修改 02_source 声明值）")

    # ⑤ 严/采用/松三行对照必须都落在事先声明的区间内
    for formula, path in sorted((args.degrade or {}).items() if isinstance(args.degrade, dict) else []):
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        low, high = ACCEPTED_RANGE[formula]
        if not (low <= report["degradation_rate"] <= high):
            problems.append(f"{formula}: degradation_rate={report['degradation_rate']} outside [{low}, {high}]")

    print(json.dumps({"environment_class": calibration["environment_class"],
                      "frozen_sha256_ok": True,
                      "structural_collapse": {"adopted_equals_strict": bool(collapsed), "capabilities": collapsed},
                      "problems": problems}, ensure_ascii=False, sort_keys=True))
    if collapsed:
        print(f"E_CALIBRATION_STRUCTURAL: adopted == strict for {collapsed} "
              f"⇒ 判据③的「松一档」前提不成立（冻结推导规则在 p95 落在同一 ceil_to 窗口时塌缩；"
              f"与普通区间越界分开报告）", file=sys.stderr)
    if problems:
        for problem in problems:
            print(f"E_CALIBRATION: {problem}", file=sys.stderr)
        return 1
    if collapsed:
        return 1
    return 0


# --------------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="calibrate_latency.py")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("registry", help="登记三份冻结物的 sha256/mtime（必须先于测量）")

    dist = sub.add_parser("dist", help="采样延迟分布")
    dist.add_argument("--samples", type=int, default=24)
    dist.add_argument("--timeout-ms", type=int, default=60000)
    dist.add_argument("--model", default=DEFAULT_MODEL)
    dist.add_argument("--out", required=True)
    dist.add_argument("--synthetic", choices=["clean", "polluted"], default=None,
                      help="合成样本（自证用，明确标注 synthetic；不联网、不消耗凭据）")

    derive = sub.add_parser("derive", help="按冻结规则推导候选值/采用值")
    derive.add_argument("--dist", required=True)
    derive.add_argument("--out", required=True)

    degrade = sub.add_parser("degrade", help="在声明值下测量降级率")
    degrade.add_argument("--formula", choices=["strict", "adopted", "loose"], required=True)
    degrade.add_argument("--runs", type=int, default=10)
    degrade.add_argument("--model", default=DEFAULT_MODEL)
    degrade.add_argument("--calibration", required=True)
    degrade.add_argument("--out", required=True)
    degrade.add_argument("--synthetic", choices=["clean", "polluted"], default=None)

    check = sub.add_parser("check", help="断言标定链成立")
    check.add_argument("--calibration", required=True)
    check.add_argument("--dist", default=None)
    check.add_argument("--cap-dir", default=None)
    check.add_argument("--degrade", action="append", default=None, metavar="FORMULA=PATH")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "check" and args.degrade:
        parsed: dict[str, str] = {}
        for item in args.degrade:
            formula, _, path = item.partition("=")
            parsed[formula] = path
        args.degrade = parsed
    return {
        "registry": cmd_registry,
        "dist": cmd_dist,
        "derive": cmd_derive,
        "degrade": cmd_degrade,
        "check": cmd_check,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
