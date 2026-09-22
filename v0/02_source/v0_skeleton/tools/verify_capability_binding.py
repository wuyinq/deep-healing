#!/usr/bin/env python3
"""能力契约校验器：provider 类别绑定（不可自声明的锚）+ 确定性闸门（**隔离子进程真执行体**）
+ 时间预算标定一致性 + provider 级 `determinism` 必填。

为什么需要它（预审 Q1 / Q2 的收口面 + round 3 审计 RR3-2 / RR3-3 + 修复迭代 2 的 N-1 / N-2）：
  * **RR3-3（类别绑定）**：判据必须是**不可自声明的锚** —— `slot ∈ imagine.*` 的能力，其**所有**
    provider 的 `class` 必须为 `remote_api`；`source_model` 用**前缀 / 正则（不区分大小写的子串）**
    匹配世界模型白名单；`imagine.*` 下 `source_model` **缺失即视为命中**（fail-closed）。
  * **RR3-2（确定性闸门）**：`determinism: "deterministic"` **只允许** `class == deterministic_rule`
    或 `class == cassette_replay`；这两类必须**在校验期真执行同一输入 ≥3 次并比对输出摘要**。
    `class ∈ {remote_api, local_model}` 声明 `deterministic` ⇒ **校验期拒收**（无法在校验期验证）。
  * **N-1（CRITICAL · 执行期逃逸，修复迭代 2 关闭）**：执行体**不得把 manifest 数据当代码执行**。
    四条缓解逐条落地（见下「执行体加固」），关闭判据是 stdlib / `__main__` / 任意 `sys.path`
    模块**全部转红**，且正例仍 exit 0。
  * **N-2（MEDIUM · `determinism` 缺失即放行，修复迭代 2 关闭）**：provider 级 `determinism`
    缺失/非法 ⇒ **直接拒收**（`B2_DETERMINISM_FIELD_MISSING`），并在下游一律归一化为
    `non_deterministic`（不得进规则层）—— 与 RR3-3 已确立的「缺失即视为命中」口径一致。
  * **D-0.9 标定**：断言 `timeout_ms ≥ p95`、`timeout_ms ≠ max`、`latency_ms_budget ≥ p90`，
    并检查 `calibration` 块齐备；`p95` 由 `calibrate.py check` 从**冻结的分布日志**独立重算。

执行体加固（N-1 缓解 ①~④，逐条可复核）：
  ① **impl 白名单 / 锚定**：`builtin:*` 只允许**登记名**（`BUILTIN_EXECUTORS` 的键）；
     `module:*` 必须前缀匹配 `deephealing_kernel.`，**且**解析出的模块文件位于 **kernel 根之内**
     （拒绝标准库 / `__main__` / 任意 `sys.path` 模块）。边界如实写明：`--impl-path` 是
     **运行门禁的人**给的参数，manifest **无法**自行扩大 import 根。
  ② **执行隔离**：provider 调用移入**子进程**（每个 provider 一个）+ **硬超时**（超时 `killpg`）
     + **资源上限**（CPU 秒 / 单文件大小 / 地址空间）；异常捕获为 `BaseException`，
     子进程的 stdout/stderr **只登记 sha256 与字节数**，绝不回显到门禁 stdout。
  ③ **digest 与输出校验**：`digest(output)` 在 `try` 内；返回值必须先过「JSON 可序列化」
     +「满足 `output_schema`」（`schema_validate`）才计入比对。
  ④ **收窄 `verified_impl` 语义**：`impl_exists` + `output_compliant` + `input_output_stable`
     **三者齐备**才算 `verified_impl`（逐项落进执行记录，reviewer 可逐条复核）。

H1（R3F2-1 / R3F2-8）派生计算加固（**上界数值见下，H3 声明同源**）：
  * **使用前先健全性检查**：`check_embedded_schema` = `schema_bounds`（迭代遍历，不递归，
    防「检查器自己先 RecursionError」）+ `schema_validate.check_schema`（引擎自带合法性）。
  * **上界**：嵌套深度 ≤ 32、schema 节点数 ≤ 512、单处 `minItems` ≤ 256、
    派生实例节点预算 ≤ 512（乘性展开也挡得住）、`enum` 必须是非空数组。超界 / 非法 ⇒ 显式拒收
    （`B5_SCHEMA_UNHEALTHY` / `B5_SCHEMA_DERIVATION_REFUSED`），**不展开、不 traceback、不静默 exit 0**。
  * fixture 回退路径的 `output_compliant=True` **真被引擎验证过**（不再是断言）：
    派生实例仍要过一遍 `output_schema`，不合规 ⇒ `B5_OUTPUT_SCHEMA_INVALID` 拒收。
  * **逐能力兜底**：单个能力抛出任何未预期异常 ⇒ 记 `B5_CHECK_CRASH_GUARDED` 拒收并继续，
    整轮门禁不会因为一个数据文件而丢掉全部判据记录；清单本身不可解析 ⇒ `B0_UNREADABLE_MANIFEST`。

H2（R3F2-2）确定性判据的**确切语义**：
  * `runs` 次调用发生在**同一个子进程内**（一次 spawn），因此 `verified_impl` 证明的是
    「**同进程内**同输入同输出 + 输出过 `output_schema` + impl 可解析」——
    进程内可变状态（模块级计数器 / 缓存 / 单例 / 第 2 次调用才抛错）在此**可见**。
  * 它**不**证明：跨进程 / 跨重启幂等，以及「随环境变量 / PID / 文件系统 / 导入期时钟变化」的行为。
    带进程内状态或依赖上述外部量的 provider **必须声明 `non_deterministic`**，不得进规则层。
    完整边界见 `02_source/capability.time-budget.spec.md` §H3。

执行体的三种结果（逐条落盘，可复核）：
  * `verified_impl`    —— impl 存在 + 输出合规 + **同一子进程内** ≥3 次输出摘要一致（三者齐备）；
  * `verified_fixture` —— impl 可解析但**首次调用**即抛 `NotImplementedError`（`08_v0_plan.md` 的
    `provider-rule` 步未做）⇒ 退回执行**固定 canonical fixture** ≥3 次，并落显式 **GAP** 记录
    （不隐藏、不冒充「已执行该 provider」）；
  * `reject`           —— 其余一切失败（impl 形状/白名单不通过 / 不可解析 / 抛其他异常 /
    超时 / 无响应 / 输出不可序列化 / 输出不满足 output_schema / 摘要不一致 / 声明带采样 /
    内嵌 schema 非法或超界 / 子进程回传协议不符）。

**本轮（修复迭代 3）仍存在的未加固面（显式声明，不隐藏）**：
  1. 父进程**没有** rlimit：`_apply_limits` 只作用于子进程；macOS 上 `RLIMIT_AS` 也不可设。
     父进程侧的防护是**上界 + 节点预算**（拒绝展开病态 schema），不是资源隔离。
  2. 内嵌 schema 的上界是**固定常量**（见上），不是按能力协商的配额；超界的**合法** schema
     同样会被拒收（fail-closed，宁可拒收不展开）。
  3. 单个 manifest 文件可声明任意多个 provider ⇒ 子进程 spawn 数随 provider 数**线性放大**
     （每个 provider 1 次 spawn；每次都有硬超时）⇒ 有界的放大面，本轮未设 provider 数上界。
  4. `IMPL_SHAPE_RE` 用 `$` 收尾，允许尾随换行（登记表查找是精确匹配 ⇒ 仍被拒收）；
     `module:` 路径里的空组件点串在**路径层**会被折叠、在 **import 层**报 `ModuleNotFoundError`
     ⇒ 两层都 fail-closed，本轮**未改**（只记录，改判据会动到已有 reason code）。
  5. 子进程**继承运行者全部环境变量**；`RLIMIT_FSIZE` 只限单文件大小、不限路径与文件个数
     ⇒ 挡住「任意路径写入」的是 **impl 白名单**，不是 rlimit。

用法：
  python3 verify_capability_binding.py --cap-dir <capabilities 目录> [--schema <capability.schema.json>]
                                       [--impl-path <kernel 根，可重复>] [--probe-timeout <秒>] [--json]
退出码：0 = 全部通过（可能带 GAP 记录）；1 = 有拒收项（逐条打印 reason code）；2 = 用法 / 环境错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

try:  # 同目录模块（以非常规方式加载时兜底）
    import schema_validate
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import schema_validate

DEFAULT_WHITELIST = ("NVIDIA Cosmos", "Cosmos", "HunyuanWorld-1.0", "Tencent HunyuanWorld-1.0",
                     "Genie 3", "Genie", "Decart Oasis", "Oasis", "Mirage", "Odyssey-1", "Odyssey-2",
                     "Marble", "Atlas", "dreamerv3", "gsplat", "gaussian-splatting")
REQUIRED_CALIBRATION = ("sample_count", "p50_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms",
                        "derivation_rule", "derivation_rule_sha256", "candidate_strict_ms",
                        "candidate_loose_ms", "accepted_degradation_range", "command", "workdir",
                        "exit", "log_path")
RULE_LAYER_CLASSES = {"remote_api", "local_model", "deterministic_rule", "cassette_replay"}
# 确定性声明**允许**的类别（在校验期可验证）；其余类别声明 deterministic 一律拒收（fail-closed）。
DETERMINISTIC_ALLOWED_CLASSES = ("deterministic_rule", "cassette_replay")
UNVERIFIABLE_CLASSES = ("remote_api", "local_model")
# 采样旋钮：带这些字段的 provider **不能**声明 deterministic（随机性来源与纯函数互斥）。
SAMPLING_RANDOMNESS_KEYS = ("temperature", "top_p", "top_k", "min_p", "presence_penalty",
                            "frequency_penalty", "repetition_penalty")
CONSISTENCY_RUNS = 3

# --------------------------------------------------------------------------- 执行体加固（N-1）
# ① impl 白名单：`module:` 只允许 kernel 包内的模块（与 capability.schema.json 的 impl 形状**分离**：
#    形状是「数据合法性」，白名单是「执行合法性」）。
MODULE_IMPL_PREFIX = "deephealing_kernel."
IMPL_SHAPE_RE = re.compile(r"^(builtin:[a-z0-9_]+|module:[A-Za-z0-9_.]+:[A-Za-z0-9_]+)$")
WORKER_NAME = "determinism_probe_worker.py"
# ② 执行隔离：每个 run 一个子进程 + 硬超时 + 资源上限。
DEFAULT_PROBE_TIMEOUT_S = 10.0
PROBE_CPU_SECONDS = 5
PROBE_FSIZE_BYTES = 1 << 20          # 单文件写入上限 1 MiB（`venv`/`compileall` 类写入会失败）
PROBE_AS_BYTES = 1 << 31             # 地址空间上限 2 GiB（best-effort，平台不支持则记 None）

# 子进程错误类型 ⇒ 门禁 reason code（逐条列明，禁止兜底吞掉）。
EXEC_ERROR_REASONS = {
    "ProbeTimeout": "B5_DETERMINISM_EXEC_TIMEOUT",
    "ProbeNoResponse": "B5_DETERMINISM_EXEC_NO_RESPONSE",
    "WorkerSpawnFailed": "B5_DETERMINISM_EXEC_UNRESOLVED",
    "ImplShapeInvalid": "B5_IMPL_SHAPE_INVALID",
    "ImplNotAllowed": "B5_IMPL_MODULE_NOT_ALLOWED",
    "ModuleFileNotInKernelRoot": "B5_DETERMINISM_EXEC_UNRESOLVED",
    "BuiltinNotRegistered": "B5_IMPL_BUILTIN_NOT_REGISTERED",
    "BuiltinRegistryUnavailable": "B5_IMPL_BUILTIN_NOT_REGISTERED",
    "ImplNotCallable": "B5_DETERMINISM_EXEC_UNRESOLVED",
    "ModuleNotFoundError": "B5_DETERMINISM_EXEC_UNRESOLVED",
    "ImportError": "B5_DETERMINISM_EXEC_UNRESOLVED",
    "AttributeError": "B5_DETERMINISM_EXEC_UNRESOLVED",
    "OutputNotSerializable": "B5_OUTPUT_NOT_SERIALIZABLE",
}
DEFAULT_EXEC_REASON = "B5_DETERMINISM_EXEC_FAILED"


def canonical_json(value) -> str:
    """与 `02_source` 的 canonical JSON 口径同族：排序键 + 紧凑分隔符 + 浮点归一到 6 位。"""
    def norm(v):
        if isinstance(v, float):
            return round(v, 6)
        if isinstance(v, dict):
            return {k: norm(x) for k, x in v.items()}
        if isinstance(v, list):
            return [norm(x) for x in v]
        return v

    return json.dumps(norm(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _one_line(value) -> str:
    """人类可读 stdout 用：把控制字符（含换行/回车）转义。

    为什么（`05 §10.5 R3F2-4`）：`id` / `impl` 等字段来自 manifest，直接插进人类可读 stdout
    时，一个含 `\\n` 的 `id` 能伪造出形如 `REJECT …` 的**假行**，污染审计阅读。
    `--json` 输出不受影响（JSON 会转义换行）；本函数只收紧人类可读那一面。
    """
    text = str(value)
    out: list[str] = []
    for char in text:
        if char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\x{ord(char):02x}")
        else:
            out.append(char)
    return "".join(out)


# --------------------------------------------------------------------------- 世界模型锚（F5）
def load_whitelist(schema_path: Path | None) -> tuple[str, ...]:
    if schema_path and schema_path.is_file():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        binding = schema.get("x-provider-class-binding") or {}
        whitelist = binding.get("world_model_whitelist")
        if whitelist:
            return tuple(whitelist)
    return DEFAULT_WHITELIST


def matches_world_model(source_model: str, whitelist: tuple[str, ...]) -> str | None:
    """**前缀 / 正则**匹配：白名单条目按「不区分大小写的子串」解释（子串包含前缀匹配）。

    这样 `nvidia/Cosmos-1.0-Diffusion-7B` 会命中 `Cosmos` —— 换名不再能绕过。
    """
    for entry in whitelist:
        pattern = re.compile(re.escape(entry.strip()), re.IGNORECASE)
        if pattern.search(source_model):
            return entry
    return None


def world_model_anchors(doc: dict, provider: dict, whitelist: tuple[str, ...]) -> list[str]:
    """返回「该 provider 以世界模型为后端」的锚（**不可自声明**的锚优先）。"""
    anchors: list[str] = []
    slot = doc.get("slot") or ""
    is_imagine = slot.startswith("imagine.")
    if is_imagine:
        anchors.append(f"slot={slot}（imagine.* ⇒ 该能力的**所有** provider 必须是 remote_api）")
    if provider.get("world_model_backend") is True:
        anchors.append("world_model_backend=true")
    source_model = provider.get("source_model")
    if isinstance(source_model, str) and source_model.strip():
        hit = matches_world_model(source_model, whitelist)
        if hit:
            anchors.append(f"source_model≈{source_model!r} 命中白名单条目 {hit!r}（前缀/正则匹配）")
    elif is_imagine:
        anchors.append("source_model 缺失/为空（imagine.* fail-closed：**缺失即视为命中**，不放行）")
    return anchors


# --------------------------------------------------------------------------- 确定性闸门（F2 / N-2）
def provider_determinism(provider: dict) -> str:
    """provider 级确定性的**归一化**值（N-2）：缺失 / 非法 ⇒ `non_deterministic`（fail-closed）。"""
    value = provider.get("determinism")
    return value if value in ("deterministic", "non_deterministic") else "non_deterministic"


def sampling_knobs(provider: dict) -> list[str]:
    """返回 provider 声明的**随机性旋钮**（`sampling.*` 或顶层同名键）。"""
    found: list[str] = []
    sampling = provider.get("sampling")
    if isinstance(sampling, dict):
        for key in SAMPLING_RANDOMNESS_KEYS:
            value = sampling.get(key)
            if value is None:
                continue
            if not _is_neutral(key, value):
                found.append(f"sampling.{key}={value!r}")
    for key in SAMPLING_RANDOMNESS_KEYS:
        value = provider.get(key)
        if value is not None and not _is_neutral(key, value):
            found.append(f"{key}={value!r}")
    return found


def _is_neutral(key: str, value) -> bool:
    """中性取值（不引入随机性）：temperature/top_k=0 或 1、top_p=1.0、penalty=0。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if key in ("temperature", "presence_penalty", "frequency_penalty", "repetition_penalty"):
        return number == 0.0
    if key == "top_p":
        return number >= 1.0
    if key in ("top_k", "min_p"):
        return number == 0.0
    return False


def probe_input(cap: dict) -> dict:
    """从能力的 `input_schema` 派生一个**固定**探针输入（同能力恒等，可复算）。

    口径沿用修复前（类型默认值），**不改输入面**；输出侧的「最小合法实例」见 `minimal_instance`。

    H1 / R3F2-8 加固：本函数读的也是 manifest 数据，修复前在**任何 `try` 之外** ——
    `input_schema.properties` 不是对象时直接 `AttributeError` 逃出门禁。
    现在畸形形状一律抛 `SchemaDerivationRefused`（调用方转显式拒收）。
    """
    schema = cap.get("input_schema") or {}
    if not isinstance(schema, dict):
        raise SchemaDerivationRefused(f"`input_schema` 不是对象（type={type(schema).__name__}）")
    raw_props = schema.get("properties")
    if raw_props is not None and not isinstance(raw_props, dict):
        raise SchemaDerivationRefused(f"`input_schema.properties` 不是对象"
                                     f"（type={type(raw_props).__name__}）")
    props = raw_props or {}
    raw_required = schema.get("required")
    if raw_required is not None and not isinstance(raw_required, list):
        raise SchemaDerivationRefused(f"`input_schema.required` 不是数组"
                                     f"（type={type(raw_required).__name__}）")
    required = raw_required or sorted(props)
    budget = {"remaining": MAX_DERIVED_NODES}

    def _one(key):
        spec = props.get(key)
        if spec is not None and not isinstance(spec, dict):
            raise SchemaDerivationRefused(f"`input_schema.properties.{key}` 不是对象"
                                          f"（type={type(spec).__name__}）")
        return _default_for(spec or {}, budget)

    return {key: _one(key) for key in required}


def _default_for(spec: dict, budget: dict | None = None):
    if budget is None:
        budget = {"remaining": MAX_DERIVED_NODES}
    _budget_node(budget, 0)
    if not isinstance(spec, dict):
        raise SchemaDerivationRefused(f"`properties` 的取值不是对象（type={type(spec).__name__}）")
    kind = spec.get("type")
    if kind == "integer":
        return 0
    if kind == "number":
        return 0.0
    if kind == "boolean":
        return False
    if kind == "array":
        return []
    if kind == "object":
        return {}
    return "probe"


# --------------------------------------------------------------------------- H1（R3F2-1）派生计算加固
# 校验期对**内嵌 schema**（`output_schema` / `input_schema`）的派生计算必须**有界**：
# 修复迭代 2 的 G1③/④ 新增了 `minimal_instance(output_schema)`（fixture 回退路径），
# 它读 manifest 数据、在**父进程**、不在 `try` 内、不受 `RLIMIT_*` 约束 ⇒ 一个纯数据
# manifest（内嵌 schema 非法或病态）就能让门禁 traceback / 内存放大（`05 §10.5 R3F2-1`）。
#
# 三层收口（逐条可复核）：
#   ① 使用前先做**健全性检查**：`schema_bounds`（迭代遍历、不递归）+ `check_schema`（引擎自带）；
#   ② **上界**（下列常量；取自交付清单实测最坏值的宽裕倍数 —— 实测 depth=6 / nodes=16 / minItems=1）；
#   ③ 派生计算入 `try` + **节点预算**（乘性展开也挡得住），越界 ⇒ 显式拒收，不 traceback、不静默 exit 0。
#
# 上界数值（H3 声明同源）：
#   * 嵌套深度  ≤ 32   （交付实测最坏 6）
#   * schema 节点数 ≤ 512（交付实测最坏 16）
#   * 单处 minItems ≤ 256（交付实测最坏 1）
#   * 派生实例节点预算 ≤ 512（乘性展开的上界：200×200=4e4 即越界）
MAX_SCHEMA_DEPTH = 32
MAX_SCHEMA_NODES = 512
MAX_SCHEMA_MIN_ITEMS = 256
MAX_DERIVED_NODES = 512
SCHEMA_UNHEALTHY_REASON = "B5_SCHEMA_UNHEALTHY"
DERIVATION_REFUSED_REASON = "B5_SCHEMA_DERIVATION_REFUSED"
PROTOCOL_MISMATCH_REASON = "B5_DETERMINISM_PROTOCOL_MISMATCH"
CHECK_GUARD_REASON = "B5_CHECK_CRASH_GUARDED"
BAD_MANIFEST_REASON = "B0_UNREADABLE_MANIFEST"


class SchemaDerivationRefused(RuntimeError):
    """派生计算越界（深度 / minItems / 节点预算）⇒ **拒收**，不展开、不静默截断。"""


def schema_bounds(schema, label: str = "schema") -> list[str]:
    """**迭代**遍历内嵌 schema，返回越界原因（空 = 在上界之内）。

    为什么迭代不递归：待检查的正是「深嵌套」这一类病态输入 —— 递归检查器自己会先
    `RecursionError`，那就把「检查」变成了新的崩溃面。
    """
    reasons: list[str] = []
    if not isinstance(schema, dict):
        return [f"{label} 不是 JSON 对象（type={type(schema).__name__}）"]
    stack: list[tuple[object, int, str]] = [(schema, 0, "$")]
    nodes = 0
    while stack:
        node, level, path = stack.pop()
        nodes += 1
        if nodes > MAX_SCHEMA_NODES:
            reasons.append(f"{label} 节点数超过上界 {MAX_SCHEMA_NODES}（已遍历 > {MAX_SCHEMA_NODES}，路径 {path}）")
            break
        if level > MAX_SCHEMA_DEPTH:
            reasons.append(f"{label} 嵌套深度超过上界 {MAX_SCHEMA_DEPTH}（路径 {path}）")
            break
        if isinstance(node, dict):
            min_items = node.get("minItems")
            if isinstance(min_items, int) and not isinstance(min_items, bool) \
                    and min_items > MAX_SCHEMA_MIN_ITEMS:
                reasons.append(f"{label} 的 minItems={min_items} 超过上界 {MAX_SCHEMA_MIN_ITEMS}"
                               f"（路径 {path}/minItems）")
            enum = node.get("enum")
            if enum is not None and (not isinstance(enum, list) or not enum):
                # 空 `enum` = 「没有任何合法实例」；`minimal_instance` 会静默退化成 type 分支，
                # 派生出的实例其实**不满足**该 schema ⇒ 必须在用前拒收（R3F2-1 同族）。
                length = len(enum) if isinstance(enum, list) else "n/a"
                reasons.append(f"{label} 的 enum 不是非空数组"
                               f"（type={type(enum).__name__}, len={length}，路径 {path}/enum）")
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    stack.append((value, level + 1, f"{path}/{key}"))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                if isinstance(value, (dict, list)):
                    stack.append((value, level + 1, f"{path}[{index}]"))
    return reasons


def check_embedded_schema(schema, label: str) -> str | None:
    """**使用前**的健全性检查：返回拒收原因（`None` = 健康）。

    顺序是刻意的：先 `schema_bounds`（廉价、迭代、有界），**再** `check_schema`（引擎自带，
    对深嵌套/巨 schema 自身可能递归）—— 反过来就等于让检查器去吃病态输入。
    任何异常（含 `RecursionError` / `MemoryError`）都转成原因字符串，绝不外抛。
    """
    try:
        bounds = schema_bounds(schema, label)
        if bounds:
            return "；".join(bounds[:3])
        try:
            errors = schema_validate.check_schema(schema)
        except schema_validate.SchemaEngineUnavailable as error:
            return f"schema 引擎不可用（{error}）⇒ fail-closed"
        if errors:
            return f"{label} 自身不是合法 JSON Schema：{errors[:3]}"
    except BaseException as error:  # noqa: BLE001 —— 检查器自身也不得让 traceback 逃出
        return f"{label} 健全性检查异常：{type(error).__name__}: {str(error)[:160]}"
    return None


def _budget_node(budget: dict, depth: int) -> None:
    budget["remaining"] -= 1
    if budget["remaining"] < 0:
        raise SchemaDerivationRefused(f"派生实例节点数超过预算 {MAX_DERIVED_NODES}")
    if depth > MAX_SCHEMA_DEPTH:
        raise SchemaDerivationRefused(f"派生实例嵌套深度超过上界 {MAX_SCHEMA_DEPTH}")


def minimal_instance(schema, budget: dict | None = None, depth: int = 0):
    """从 JSON Schema 派生一个**确定性的最小合法实例**（输出侧专用）。

    为什么需要它（N-1 缓解 ③/④）：返回值必须先过 `output_schema` 才计入比对，所以
    canonical fixture 与 pinned cassette 的 output 段不能再是「任意形状的字典」，
    必须**由冻结 schema 派生**，从而天然合规、可复算。

    H1（R3F2-1）加固：带**节点预算**与深度上界，越界抛 `SchemaDerivationRefused`
    （调用方转显式拒收）；`enum` 非数组等畸形形状同样抛，不再静默取值。
    调用方**必须先** `check_embedded_schema` —— 本函数是第二道防线，不是第一道。
    """
    if budget is None:
        budget = {"remaining": MAX_DERIVED_NODES}
    _budget_node(budget, depth)
    if not isinstance(schema, dict):
        return None
    enum = schema.get("enum")
    if enum is not None:
        if not isinstance(enum, list) or not enum:
            raise SchemaDerivationRefused(
                f"`enum` 不是非空数组（type={type(enum).__name__}, "
                f"len={len(enum) if isinstance(enum, list) else 'n/a'}）")
        return enum[0]
    if "const" in schema:
        return schema["const"]
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((item for item in kind if item != "null"), kind[0] if kind else None)
    if kind == "object" or "properties" in schema:
        raw_props = schema.get("properties")
        if raw_props is not None and not isinstance(raw_props, dict):
            raise SchemaDerivationRefused(f"`properties` 不是对象（type={type(raw_props).__name__}）")
        props = raw_props or {}
        raw_required = schema.get("required")
        if raw_required is not None and not isinstance(raw_required, list):
            raise SchemaDerivationRefused(f"`required` 不是数组（type={type(raw_required).__name__}）")
        required = raw_required or sorted(props)
        return {key: minimal_instance(props.get(key) or {}, budget, depth + 1) for key in required}
    if kind == "array":
        raw = schema.get("minItems")
        try:
            count = int(raw or 0)
        except (TypeError, ValueError):
            raise SchemaDerivationRefused(f"`minItems` 不是整数（{raw!r}）") from None
        if count > MAX_SCHEMA_MIN_ITEMS:
            raise SchemaDerivationRefused(f"`minItems`={count} 超过上界 {MAX_SCHEMA_MIN_ITEMS}")
        if count < 0:
            raise SchemaDerivationRefused(f"`minItems`={count} 为负数")
        items = schema.get("items") or {}
        return [minimal_instance(items, budget, depth + 1) for _ in range(count)]
    if kind == "integer":
        try:
            return int(schema.get("minimum") or 0)
        except (TypeError, ValueError):
            raise SchemaDerivationRefused(f"`minimum` 不是整数（{schema.get('minimum')!r}）") from None
    if kind == "number":
        try:
            return float(schema.get("minimum") or 0)
        except (TypeError, ValueError):
            raise SchemaDerivationRefused(f"`minimum` 不是数（{schema.get('minimum')!r}）") from None
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return "probe"


# --------------------------------------------------------------------------- builtin 执行体（登记名白名单）
def pinned_cassette_bytes(cap: dict) -> bytes:
    """`cassette_replay` 的**固定 cassette**：逐字节确定（其 sha256 落进执行记录，供第三方复算）。

    output 段由能力的 `output_schema` 派生 ⇒ 回放结果天然满足输出合规判据。
    """
    record = {
        "key": "probe",
        "capability_id": cap.get("id"),
        "capability_version": cap.get("version"),
        "canonical_input_hash": "probe",
        "provider": "cassette_replay",
        "output": minimal_instance(cap.get("output_schema") or {}),
        "prev_hash": "0" * 64,
    }
    return (canonical_json(record) + "\n").encode("utf-8")


def builtin_cassette_replay(payload: dict, context: dict) -> dict:
    """`builtin:cassette_replay` 的执行体：对**固定 cassette** 做一次真回放（解析 → 取 output）。

    契约：builtin 执行体签名 = `(payload, context)`；`module:` 目标的签名 = `(payload)`
    （既有内核实现不得改动，故两侧签名如实不同）。
    """
    raw = pinned_cassette_bytes(context.get("capability") or {})
    records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    return records[0]["output"]


def builtin_reference_rule(payload: dict, context: dict) -> dict:
    """V0 骨架下的 canonical fixture（纯函数：同输入同输出）。仅用于 `verified_fixture`。"""
    return minimal_instance(context.get("output_schema") or {})


BUILTIN_EXECUTORS = {
    "cassette_replay": builtin_cassette_replay,
    "determinism_gate_reference": builtin_reference_rule,
}


# --------------------------------------------------------------------------- 子进程执行（N-1 缓解 ①②）
def locate_module_file(module_path: str, impl_paths: tuple[Path, ...]) -> tuple[Path | None, Path | None]:
    """**路径层**定位（不 import）：返回 (module_file, kernel_root)；越界 / 不存在 ⇒ (None, None)。

    拒绝符号链接逃出：候选文件 `resolve()` 之后必须仍在 kernel 根之内。
    """
    rel = Path(*module_path.split("."))
    for root in impl_paths:
        root_resolved = root.resolve()
        for candidate in ((root_resolved / rel).with_suffix(".py"), root_resolved / rel / "__init__.py"):
            if candidate.is_file():
                resolved = candidate.resolve()
                if resolved == root_resolved or root_resolved in resolved.parents:
                    return resolved, root_resolved
    return None, None


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.communicate(timeout=5)
    except Exception:  # noqa: BLE001 —— 清理路径，不再抛出
        pass


def run_probe_child(impl: str, kernel_root: Path | None, probe: dict, context: dict,
                    timeout_s: float, runs: int = CONSISTENCY_RUNS) -> dict:
    """在**子进程**里执行 `runs` 次探针调用：硬超时 + 资源上限 + 文件通道回传结果。

    H2（R3F2-2）语义：`runs` 次调用发生在**同一个子进程内**（一次 spawn），
    因此「同进程内同输入同输出」这一性质被真正观测到 —— 修复前每次 run 一个新进程，
    模块级计数器 / 缓存 / 单例 / 「第二次调用才抛错」的实现会假绿。
    隔离目标（崩溃/挂起/写盘不外溢）不变：仍是一个独立进程 + 硬超时 + rlimit。
    """
    worker = Path(__file__).resolve().parent / WORKER_NAME
    if not worker.is_file():
        return {"status": "error", "error_type": "WorkerSpawnFailed",
                "error": f"执行体不存在：{worker}"}
    request = {
        "impl": impl,
        "probe": probe,
        "context": context,
        "runs": runs,
        "kernel_root": str(kernel_root) if kernel_root else "",
        "module_prefix": MODULE_IMPL_PREFIX,
        "registry_path": str(Path(__file__).resolve()),
        "cpu_seconds": PROBE_CPU_SECONDS,
        "fsize_bytes": PROBE_FSIZE_BYTES,
        "as_bytes": PROBE_AS_BYTES,
    }
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"      # 不在交付树里留 __pycache__
    env.pop("PYTHONSTARTUP", None)
    with tempfile.TemporaryDirectory(prefix="dh-probe-") as tmp:
        request_path = Path(tmp) / "request.json"
        response_path = Path(tmp) / "response.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        try:
            proc = subprocess.Popen(
                [sys.executable, str(worker), str(request_path), str(response_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                cwd=tmp, env=env, start_new_session=True)
        except OSError as error:
            return {"status": "error", "error_type": "WorkerSpawnFailed",
                    "error": f"{type(error).__name__}: {error}"}
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            return {"status": "error", "error_type": "ProbeTimeout",
                    "error": f"超过硬超时 {timeout_s}s（子进程已被 killpg）"}
        if not response_path.is_file():
            # 子进程自己 `sys.exit()` / `os._exit()` / 被杀 ⇒ 无响应（不掩盖，直接 fail-closed）。
            return {"status": "error", "error_type": "ProbeNoResponse",
                    "error": f"子进程未回传结果（exit={proc.returncode}）",
                    "child_returncode": proc.returncode,
                    "child_stdout_bytes": len(stdout), "child_stdout_sha256": sha256_bytes(stdout)}
        try:
            response = json.loads(response_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return {"status": "error", "error_type": "ProbeNoResponse",
                    "error": f"响应不可解析：{type(error).__name__}: {error}",
                    "child_returncode": proc.returncode}
        response["child_returncode"] = proc.returncode
        response["child_stdout_bytes"] = len(stdout)
        response["child_stdout_sha256"] = sha256_bytes(stdout)
        response["child_stderr_bytes"] = len(stderr)
        return response


def _reject(record: dict, reason_code: str, detail: str) -> dict:
    record.update({"result": "reject", "reason_code": reason_code, "detail": detail,
                   "impl_exists": False, "output_compliant": False, "input_output_stable": False})
    return record


def _reject_keep_impl(record: dict, reason_code: str, detail: str) -> dict:
    """拒收，但**不改写** `impl_exists` —— 用于「impl 已解析、失败发生在后续阶段」的记录。

    （`_reject` 把 `impl_exists` 置 False 是给「形状/白名单就没过」用的；在 fixture 派生
    计算被拒这种场景里，impl 确实存在过，把它改写成 False 反而与事实不符。）
    """
    record.update({"result": "reject", "reason_code": reason_code, "detail": detail,
                   "output_compliant": False, "input_output_stable": False})
    return record


def execute_determinism_probe(provider: dict, cap: dict, impl_paths: tuple[Path, ...],
                              runs: int = CONSISTENCY_RUNS,
                              timeout_s: float = DEFAULT_PROBE_TIMEOUT_S) -> dict:
    """**隔离执行体**：同一输入在**同一个子进程内**重复 `runs` 次 → 输出合规检查 → 比对摘要。

    返回执行记录（含 `impl_exists` / `output_compliant` / `input_output_stable` 三项，
    三者齐备才算 `verified_impl`）。

    H2（R3F2-2）：`verified_impl` 的语义 = **同一子进程内**同输入同输出（进程内可变状态可见）。
    它**不**证明：跨进程 / 跨重启的可复现性，以及「与环境/PID/文件系统/导入期时间相关的状态」。
    确切边界见 `02_source/capability.time-budget.spec.md` §H3。
    """
    impl = provider.get("impl")
    output_schema = cap.get("output_schema") or {}
    input_schema = cap.get("input_schema") or {}
    context = {"capability_id": cap.get("id"), "capability_version": cap.get("version"),
               "capability": cap, "output_schema": output_schema}
    record = {
        "capability": cap.get("id"), "class": provider.get("class"), "impl": impl, "runs": runs,
        "isolation": {"mode": "subprocess", "per_run": False, "calls_per_spawn": runs,
                      "spawns_per_provider": 1, "timeout_s": timeout_s,
                      "cpu_seconds": PROBE_CPU_SECONDS, "fsize_bytes": PROBE_FSIZE_BYTES,
                      "as_bytes": PROBE_AS_BYTES},
        "schema_bounds": {"max_depth": MAX_SCHEMA_DEPTH, "max_nodes": MAX_SCHEMA_NODES,
                          "max_min_items": MAX_SCHEMA_MIN_ITEMS,
                          "max_derived_nodes": MAX_DERIVED_NODES},
        "impl_exists": False, "output_compliant": False, "input_output_stable": False,
    }

    # ⓪ H1（R3F2-1 / R3F2-8）：**使用前**先做内嵌 schema 健全性检查 + 上界检查
    #    （非法 / 超界 ⇒ 显式拒收，绝不进入派生计算、绝不 traceback）
    for label, embedded in (("output_schema", output_schema), ("input_schema", input_schema)):
        unhealthy = check_embedded_schema(embedded, label)
        if unhealthy:
            return _reject(record, SCHEMA_UNHEALTHY_REASON,
                           f"内嵌 {label} 未通过健全性/上界检查（深度≤{MAX_SCHEMA_DEPTH}、"
                           f"节点≤{MAX_SCHEMA_NODES}、minItems≤{MAX_SCHEMA_MIN_ITEMS}）：{unhealthy}")

    # ⓪b 探针输入派生（H1/R3F2-8：修复前在任何 try 之外）
    try:
        probe = probe_input(cap)
        record["probe"] = probe
        record["probe_digest"] = digest(probe)
    except BaseException as error:  # noqa: BLE001
        return _reject(record, DERIVATION_REFUSED_REASON,
                       f"探针输入派生被拒绝（内嵌 input_schema）："
                       f"{type(error).__name__}: {str(error)[:160]}")

    # ① impl 形状 + 白名单 / 锚定（**不 import、不执行**）
    if not isinstance(impl, str) or not IMPL_SHAPE_RE.match(impl):
        return _reject(record, "B5_IMPL_SHAPE_INVALID",
                       f"impl={impl!r} 不满足冻结形状 ^(builtin:[a-z0-9_]+|"
                       f"module:[A-Za-z0-9_.]+:[A-Za-z0-9_]+)$")
    kernel_root: Path | None = None
    if impl.startswith("builtin:"):
        name = impl.split(":", 1)[1]
        if name not in BUILTIN_EXECUTORS:
            return _reject(record, "B5_IMPL_BUILTIN_NOT_REGISTERED",
                           f"builtin:{name} 不在登记表内（只允许登记名 "
                           f"{sorted(BUILTIN_EXECUTORS)}）")
        record["impl_kind"] = "builtin"
    else:
        body = impl.split(":", 1)[1]
        module_path, _, fn_name = body.rpartition(":")
        head = module_path.split(".")[0] if module_path else ""
        if (not module_path.startswith(MODULE_IMPL_PREFIX) or "__main__" in module_path
                or head in sys.stdlib_module_names):
            return _reject(record, "B5_IMPL_MODULE_NOT_ALLOWED",
                           f"module 路径 {module_path!r} 不满足白名单：必须前缀 "
                           f"{MODULE_IMPL_PREFIX} 且模块文件位于 kernel 根之内"
                           f"（拒绝标准库 / __main__ / 任意 sys.path 模块）")
        module_file, kernel_root = locate_module_file(module_path, impl_paths)
        if module_file is None:
            return _reject(record, "B5_DETERMINISM_EXEC_UNRESOLVED",
                           f"{module_path!r} 未解析到 kernel 根之内的模块文件"
                           f"（import 根={[str(p) for p in impl_paths]}）⇒ fail-closed")
        record.update({"impl_kind": "module", "module_file": str(module_file),
                       "kernel_root": str(kernel_root)})
    record["impl_exists"] = True

    # ② 一次 spawn 内真执行 `runs` 次（H2）+ ③ 输出合规 + digest 在 try 内
    digests: list[str] = []
    attempt = run_probe_child(impl, kernel_root, probe, context, timeout_s, runs=runs)
    record.setdefault("child_runs", []).append(
        {key: attempt.get(key) for key in
         ("status", "error_type", "run_index", "runs", "child_returncode", "child_stdout_bytes",
          "child_stdout_sha256", "child_stderr_bytes", "limits")})
    if attempt.get("status") != "ok":
        error_type = str(attempt.get("error_type") or "Unknown")
        failed_run = int(attempt.get("run_index") or 0)
        if error_type == "NotImplementedError" and failed_run == 0:
            # V0 骨架：impl 存在但**第一次**调用就未实现 ⇒ 退回固定 canonical fixture，
            # 落显式 GAP（不隐藏）。**后续调用**才抛错不算「未实现」⇒ 走拒收（见下）。
            record.update({
                "result": "verified_fixture",
                "reason_code": "B5_GAP_IMPL_NOT_IMPLEMENTED",
                "detail": (f"impl={impl!r} 可解析但在 V0 骨架下**首次调用**即抛 NotImplementedError"
                           f"（{str(attempt.get('error', ''))[:80]}）⇒ 退回执行固定 canonical "
                           f"fixture ≥{runs} 次（不冒充「已执行该 provider」）"),
                "fixture": "determinism_gate_reference",
                "fixture_sha256": hashlib.sha256(b"determinism_gate_reference").hexdigest(),
            })
            # H1（R3F2-1）：派生计算整段入 `try`，任何异常转**显式拒收**（不 traceback、不静默 exit 0）
            try:
                fixture_output = builtin_reference_rule(probe, context)
                digests = [digest(fixture_output) for _ in range(runs)]
                # `output_compliant=True` 必须**真被验证过**（不能只是断言）：
                # 派生实例是「由 schema 推出」的，仍要过一遍引擎，避免 schema 里有
                # `enum: []` 这类「没有合法实例」的形状时把不合规输出记成合规。
                fixture_errors = schema_validate.validate(fixture_output, output_schema)
            except schema_validate.SchemaEngineUnavailable as error:
                return _reject_keep_impl(record, "B5_OUTPUT_SCHEMA_ENGINE_UNAVAILABLE", str(error))
            except BaseException as error:  # noqa: BLE001
                return _reject_keep_impl(record, DERIVATION_REFUSED_REASON,
                                         f"fixture 回退的派生计算被拒绝（内嵌 output_schema）："
                                         f"{type(error).__name__}: {str(error)[:160]}")
            if fixture_errors:
                return _reject_keep_impl(record, "B5_OUTPUT_SCHEMA_INVALID",
                                         f"fixture 派生实例不满足 output_schema："
                                         f"{fixture_errors[:3]}（共 {len(fixture_errors)} 条）")
            record["output_compliant"] = True
        else:
            return _reject(record, EXEC_ERROR_REASONS.get(error_type, DEFAULT_EXEC_REASON),
                           f"第 {failed_run + 1}/{runs} 次执行失败（同一子进程内）：{error_type}: "
                           f"{str(attempt.get('error', ''))[:160]}")

    if not digests:
        outputs = attempt.get("outputs")
        if not isinstance(outputs, list) or len(outputs) != runs:
            # 协议不符（旧 worker / 回传缺项）⇒ **fail-closed**，不按 1 次结果冒充 runs 次
            return _reject(record, PROTOCOL_MISMATCH_REASON,
                           f"子进程回传的 outputs 不是长度 {runs} 的数组"
                           f"（type={type(outputs).__name__}, "
                           f"len={len(outputs) if isinstance(outputs, list) else 'n/a'}）"
                           f"⇒ 拒绝按「跨进程冷启动」口径放行")
        for index, output in enumerate(outputs):
            # ③a JSON 可序列化（子进程已预检，父侧再判一次：口径不依赖子进程）
            try:
                digest(output)
            except (TypeError, ValueError) as error:
                return _reject(record, "B5_OUTPUT_NOT_SERIALIZABLE",
                               f"第 {index + 1}/{runs} 次输出不可 JSON 序列化："
                               f"{type(error).__name__}: {str(error)[:120]}")
            # ③b 满足 output_schema（G1 缓解 ③）
            try:
                schema_errors = schema_validate.validate(output, output_schema)
            except schema_validate.SchemaEngineUnavailable as error:
                return _reject(record, "B5_OUTPUT_SCHEMA_ENGINE_UNAVAILABLE", str(error))
            if schema_errors:
                return _reject(record, "B5_OUTPUT_SCHEMA_INVALID",
                               f"第 {index + 1}/{runs} 次输出不满足 output_schema："
                               f"{schema_errors[:3]}（共 {len(schema_errors)} 条）")
            record["output_compliant"] = True
            digests.append(digest(output))

    record["output_digests"] = digests
    # H2（R3F2-2）：摘要比对的是**同一个子进程内** `runs` 次调用的输出 ——
    # 进程内可变状态（模块级计数器 / 缓存 / 单例 / 第二次调用才抛错）在此**可见**。
    record["input_output_stable"] = len(set(digests)) == 1 and len(digests) == runs
    if not record["input_output_stable"]:
        return _reject(record, "B5_DETERMINISM_INCONSISTENT",
                       f"同一输入在**同一子进程内** {runs} 次执行输出摘要不一致：{digests}")
    record.setdefault("result", "verified_impl")
    record["output_digest"] = digests[0]
    # ④ 收窄语义：三者齐备才算 verified_impl（fixture 路径已在上面落 result，不受此判据影响）。
    if record["result"] == "verified_impl" and not (record["impl_exists"]
                                                    and record["output_compliant"]
                                                    and record["input_output_stable"]):
        return _reject(record, "B5_VERIFIED_SEMANTICS_INCOMPLETE",
                       "verified_impl 需要「实现存在 + 输出合规 + 同输入同输出」三者齐备")
    return record


# --------------------------------------------------------------------------- 逐能力校验
def check_capability(doc: dict, whitelist: tuple[str, ...], impl_paths: tuple[Path, ...],
                     do_execute: bool = True,
                     timeout_s: float = DEFAULT_PROBE_TIMEOUT_S) -> tuple[list[dict], list[dict], list[dict]]:
    rejects: list[dict] = []
    gaps: list[dict] = []
    exec_records: list[dict] = []
    cap_id = doc.get("id", "<no-id>")
    slot = doc.get("slot") or ""

    for provider in doc.get("providers", []):
        # B1 · provider 类别绑定（不可自声明的锚 + default-deny）
        anchors = world_model_anchors(doc, provider, whitelist)
        if anchors and provider.get("class") != "remote_api":
            if slot.startswith("imagine."):
                rejects.append({"code": "B1_IMAGINE_SLOT_CLASS_NOT_REMOTE_API", "capability": cap_id,
                                "detail": f"slot={slot} 的 provider class={provider.get('class')!r}；"
                                          f"锚={anchors}；imagine.* 的**所有** provider 必须是 remote_api"})
            rejects.append({"code": "B1_WORLD_MODEL_CLASS_NOT_REMOTE_API", "capability": cap_id,
                            "detail": f"provider class={provider.get('class')!r}，锚={anchors}；"
                                      f"以世界模型为后端的能力必须声明为 remote_api（default-deny）"})

        # B2 · provider 级 determinism **必填**（N-2：缺失/非法 ⇒ 拒收 + 归一化为 non_deterministic）
        raw_determinism = provider.get("determinism")
        determinism = provider_determinism(provider)
        provider_class = provider.get("class")
        if raw_determinism not in ("deterministic", "non_deterministic"):
            rejects.append({"code": "B2_DETERMINISM_FIELD_MISSING", "capability": cap_id,
                            "detail": f"provider class={provider_class!r} 的 determinism="
                                      f"{raw_determinism!r} 缺失/非法；该字段必填，缺失即视为 "
                                      f"non_deterministic（fail-closed）且不得进规则层"})
        if determinism == "non_deterministic" and provider.get("allowed_in_rule_layer"):
            rejects.append({"code": "B2_NONDETERMINISTIC_IN_RULE_LAYER", "capability": cap_id,
                            "detail": f"provider class={provider_class!r} 声明 non_deterministic "
                                      f"却 allowed_in_rule_layer=true"})
        # B5 · 确定性闸门（**隔离执行体** + fail-closed）
        # `--no-execute` 只用于自证反例：退回**修复前**的旧行为（不读确定性声明、不执行），
        # 因此 F2①/F2② 两条负例在该模式下必须**不再**被检出（证明红来自执行体）。
        if do_execute and (determinism == "deterministic" or provider_class in DETERMINISTIC_ALLOWED_CLASSES):
            if determinism == "deterministic" and provider_class in UNVERIFIABLE_CLASSES:
                rejects.append({"code": "B5_DETERMINISM_CLASS_UNVERIFIABLE", "capability": cap_id,
                                "detail": f"class={provider_class!r} 声明 determinism=deterministic，"
                                          f"但该类无法在校验期验证（只允许 "
                                          f"{list(DETERMINISTIC_ALLOWED_CLASSES)}）⇒ fail-closed 拒收"})
            knobs = sampling_knobs(provider)
            if knobs and determinism == "deterministic":
                rejects.append({"code": "B5_DETERMINISM_WITH_SAMPLING", "capability": cap_id,
                                "detail": f"声明 determinism=deterministic 却带采样旋钮 {knobs}；"
                                          f"随机性来源与纯函数互斥 ⇒ 拒收"})
            if determinism == "deterministic" and provider_class in DETERMINISTIC_ALLOWED_CLASSES:
                record = execute_determinism_probe(provider, doc, impl_paths, timeout_s=timeout_s)
                exec_records.append(record)
                if record["result"] == "reject":
                    rejects.append({"code": record["reason_code"], "capability": cap_id,
                                    "detail": record.get("detail", "")})
                elif record["result"] == "verified_fixture":
                    gaps.append({"code": record["reason_code"], "capability": cap_id,
                                 "provider_class": provider_class,
                                 "detail": record.get("detail", "")})

    # B3 · 规则层采纳面 + 一致性检查（N-2：缺失 determinism 的 provider 类别同样**不得进规则层**）
    adoption = doc.get("rule_layer_adoption") or {}
    allowed_classes = set(adoption.get("provider_classes_allowed") or [])
    if not allowed_classes <= RULE_LAYER_CLASSES:
        rejects.append({"code": "B3_UNKNOWN_PROVIDER_CLASS", "capability": cap_id,
                        "detail": f"provider_classes_allowed 含未知类别：{sorted(allowed_classes - RULE_LAYER_CLASSES)}"})
    # 缺失/非法 determinism 的 provider 也归一化为 non_deterministic ⇒ 其**类别**同样不得进规则层（N-2）
    non_det_classes = {p.get("class") for p in doc.get("providers", [])
                       if provider_determinism(p) != "deterministic"}
    if allowed_classes & non_det_classes:
        rejects.append({"code": "B3_NONDETERMINISTIC_CLASS_ALLOWED", "capability": cap_id,
                        "detail": f"规则层采纳面含 non_deterministic（含 determinism 缺失）的类别："
                                  f"{sorted(allowed_classes & non_det_classes)}"})
    check = adoption.get("consistency_check") or {}
    if check.get("required") is not True or int(check.get("runs", 0)) < CONSISTENCY_RUNS:
        rejects.append({"code": "B3_CONSISTENCY_CHECK_TOO_WEAK", "capability": cap_id,
                        "detail": f"consistency_check={check!r}；校验期必跑且 runs ≥ {CONSISTENCY_RUNS}"
                                  f"（该字段是补充信息，唯一判据是执行体真跑结果）"})

    # B4 · 时间预算标定（防自证）
    calibration = doc.get("calibration") or {}
    missing = [field for field in REQUIRED_CALIBRATION if field not in calibration]
    if missing:
        rejects.append({"code": "B4_CALIBRATION_INCOMPLETE", "capability": cap_id,
                        "detail": f"calibration 缺字段：{missing}"})
        return rejects, gaps, exec_records
    timeout_ms = doc.get("timeout_ms")
    budget = doc.get("latency_ms_budget")
    p95, p90, max_ms = calibration["p95_ms"], calibration["p90_ms"], calibration["max_ms"]
    if timeout_ms is None or timeout_ms < p95:
        rejects.append({"code": "B4_TIMEOUT_BELOW_P95", "capability": cap_id,
                        "detail": f"timeout_ms={timeout_ms} < p95={p95}（声明值必须 ≥ p95）"})
    if timeout_ms == max_ms:
        rejects.append({"code": "B4_TIMEOUT_EQUALS_MAX", "capability": cap_id,
                        "detail": f"timeout_ms={timeout_ms} == max={max_ms}（不得取当次实测最大值）"})
    if budget is None or budget < p90:
        rejects.append({"code": "B4_BUDGET_BELOW_P90", "capability": cap_id,
                        "detail": f"latency_ms_budget={budget} < p90={p90}"})
    if calibration["candidate_strict_ms"] >= calibration["candidate_loose_ms"]:
        rejects.append({"code": "B4_CANDIDATES_NOT_ORDERED", "capability": cap_id,
                        "detail": "candidate_strict_ms 必须 < candidate_loose_ms"})
    if not calibration.get("derivation_rule_sha256"):
        rejects.append({"code": "B4_RULE_NOT_FROZEN", "capability": cap_id,
                        "detail": "缺 derivation_rule_sha256（推导规则必须先冻结）"})
    return rejects, gaps, exec_records


def default_impl_path(cap_dir: Path) -> Path | None:
    """默认 kernel 根：`<cap-dir>/../kernel`（V0 骨架的 `module:deephealing_kernel...` 落点）。"""
    candidate = (cap_dir / ".." / "kernel").resolve()
    return candidate if candidate.is_dir() else None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="verify-capability-binding")
    parser.add_argument("--cap-dir", required=True)
    parser.add_argument("--schema")
    parser.add_argument("--impl-path", action="append", default=None,
                        help="解析 module: impl 时的**附加** import 根（可重复；默认总是含 <cap-dir>/../kernel）。"
                             "注意：白名单要求 module 前缀 deephealing_kernel. 且文件在该根之内")
    parser.add_argument("--probe-timeout", type=float, default=DEFAULT_PROBE_TIMEOUT_S,
                        help=f"单次子进程探针的硬超时秒数（默认 {DEFAULT_PROBE_TIMEOUT_S}）")
    parser.add_argument("--no-execute", action="store_true",
                        help="**仅用于自证反例**：退回修复前的旧行为（只读声明字段、不做确定性声明检查）"
                             "，负例必须因此变红")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    cap_dir = Path(args.cap_dir)
    if not cap_dir.is_dir():
        print(f"E_CAP_DIR: {cap_dir} 不是目录", file=sys.stderr)
        return 2
    try:
        engine = schema_validate.engine_name()
    except schema_validate.SchemaEngineUnavailable as error:
        print(f"E_SCHEMA_ENGINE: {error}（输出合规判据无法执行 ⇒ fail-closed）", file=sys.stderr)
        return 2
    whitelist = load_whitelist(Path(args.schema) if args.schema else None)
    impl_paths: list[Path] = []
    default_path = default_impl_path(cap_dir)
    if default_path is not None:
        impl_paths.append(default_path)
    for extra in args.impl_path or []:
        resolved = Path(extra).resolve()
        if resolved not in impl_paths:
            impl_paths.append(resolved)
    impl_paths_tuple = tuple(impl_paths)
    files = sorted(cap_dir.glob("*.capability.json"))
    rejects: list[dict] = []
    gaps: list[dict] = []
    exec_records: list[dict] = []
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            rejects.append({"code": "B0_BAD_JSON", "capability": path.name, "detail": str(exc)[:160]})
            continue
        except BaseException as exc:  # noqa: BLE001 —— 深嵌套 / 病态文本也不得让 traceback 逃出
            rejects.append({"code": BAD_MANIFEST_REASON, "capability": path.name,
                            "detail": f"清单不可解析（{type(exc).__name__}: {str(exc)[:120]}）"
                                      f"⇒ fail-closed 拒收，不进入派生计算"})
            continue
        try:
            file_rejects, file_gaps, file_records = check_capability(
                doc, whitelist, impl_paths_tuple, do_execute=not args.no_execute,
                timeout_s=args.probe_timeout)
        except BaseException as exc:  # noqa: BLE001 —— 逐能力兜底：单个能力不得让整轮门禁 traceback
            rejects.append({"code": CHECK_GUARD_REASON, "capability": path.name,
                            "detail": f"校验该能力时抛出未预期异常（{type(exc).__name__}: "
                                      f"{str(exc)[:160]}）⇒ 记为拒收，不静默放行、不中断整轮"})
            continue
        rejects.extend(file_rejects)
        gaps.extend(file_gaps)
        exec_records.extend(file_records)

    result = {"cap_dir": str(cap_dir), "capabilities": len(files),
              "impl_paths": [str(p) for p in impl_paths_tuple],
              "executor_enabled": not args.no_execute, "schema_engine": engine,
              "executor_isolation": {"mode": "subprocess", "per_run": False,
                                     "calls_per_spawn": CONSISTENCY_RUNS,
                                     "spawns_per_provider": 1,
                                     "timeout_s": args.probe_timeout,
                                     "cpu_seconds": PROBE_CPU_SECONDS,
                                     "fsize_bytes": PROBE_FSIZE_BYTES, "as_bytes": PROBE_AS_BYTES},
              "schema_derivation_bounds": {"max_depth": MAX_SCHEMA_DEPTH,
                                           "max_nodes": MAX_SCHEMA_NODES,
                                           "max_min_items": MAX_SCHEMA_MIN_ITEMS,
                                           "max_derived_nodes": MAX_DERIVED_NODES},
              "module_impl_prefix": MODULE_IMPL_PREFIX,
              "registered_builtins": sorted(BUILTIN_EXECUTORS),
              "determinism_exec": exec_records,
              "gaps": gaps, "rejects": rejects, "ok": not rejects}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"ENGINE {engine} :: impl 白名单 module 前缀={MODULE_IMPL_PREFIX} "
              f":: builtin 登记名={sorted(BUILTIN_EXECUTORS)} "
              f":: 执行隔离=subprocess(calls_per_spawn={CONSISTENCY_RUNS}, "
              f"timeout={args.probe_timeout}s)")
        for record in exec_records:
            print(f"EXEC  {_one_line(record['capability'])} :: {_one_line(record['class'])} :: "
                  f"{record['result']} runs={record['runs']} "
                  f"digest={str(record.get('output_digest'))[:16]}… "
                  f"impl_exists={record['impl_exists']} output_compliant={record['output_compliant']} "
                  f"stable={record['input_output_stable']}")
        for gap in gaps:
            print(f"GAP   {gap['code']}: {_one_line(gap['capability'])} :: {_one_line(gap['detail'])}")
        for reject in rejects:
            print(f"REJECT {reject['code']}: {_one_line(reject['capability'])} :: "
                  f"{_one_line(reject['detail'])}")
        print(f"capability binding verify: capabilities={len(files)} exec={len(exec_records)} "
              f"gaps={len(gaps)} rejects={len(rejects)}")
    return 0 if not rejects else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
