#!/usr/bin/env python3
"""确定性探针的**隔离子进程执行体**（Raven N-1 缓解 ②：执行隔离；H2/R3F2-2：进程内 N 次调用）。

为什么必须是独立进程（`05_raven_risk_report.md §9.5 N-1`）：
  * 目标代码由 manifest 指名的 `impl` 决定。它可能 `sys.exit()`、死循环、吃满内存、
    往**任意绝对路径**写文件 —— 这些**不得**影响门禁自身的退出码、stdout 与证据可复核性。
  * 因此：父侧**每个 provider 一个子进程** + **硬超时**（`subprocess` timeout，超时 `killpg`）；
    本文件自己设**资源上限**（CPU 秒 / 单文件大小 / 地址空间）；
    结果只经 `response_path` **文件通道**回传，**不混进 stdout**（stdout 由父侧单独捕获，
    只登记 sha256 与字节数，绝不回显到门禁 stdout）。

为什么 `runs` 次调用必须在本**同一个**进程内（H2 / `05 §10.5 R3F2-2`）：
  * 规则层是**长驻进程**，它需要的性质是「**同进程内**同输入同输出」。
    若每次 run 起一个新进程，模块级计数器 / 缓存 / 单例 /「第二次调用才抛错」的实现
    每次都从零开始 ⇒ 三次输出相同 ⇒ 假绿 `verified_impl`。
  * 所以：一次 spawn、进程内调用 `runs` 次、逐次回传输出；隔离目标（崩溃/挂起/写盘不外溢）
    不变 —— 仍是一个独立进程 + 硬超时 + rlimit，只是这个进程里多跑了几次。

本文件**不面向人工调用**，由 `verify_capability_binding.py` 以
`python3 determinism_probe_worker.py <request.json> <response.json>` 拉起。

请求（JSON）：
  {"impl": "builtin:<name>" | "module:<python.module>:<attr>",
   "probe": {...},                      # 由能力 input_schema 派生的固定探针输入
   "context": {"capability_id", "capability_version", "output_schema"},
   "runs": 3,                           # **同一进程内**的调用次数（默认 3）
   "kernel_root": "<import 根绝对路径>",
   "module_prefix": "deephealing_kernel.",
   "registry_path": "<verify_capability_binding.py 绝对路径，用于取 builtin 登记表>",
   "cpu_seconds": 5, "fsize_bytes": 1048576, "as_bytes": 2147483648}

响应（JSON）：
  {"status": "ok",    "output": <第 1 次输出>, "outputs": [<第 1..runs 次输出>], "runs": 3,
   "impl_kind": "builtin"|"module", "module_file": ..., "limits": {...}}
  {"status": "error", "error_type": "<类名或 reason>", "error": "<摘要>",
   "run_index": <第几次调用失败，0 基>, "runs": 3, ...}

退出码：0 = 已写出 response（结果在文件里）；其它 = 子进程自身异常（父侧按「无响应」fail-closed）。
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import resource
import sys
from pathlib import Path

DEFAULT_MODULE_PREFIX = "deephealing_kernel."
RESPONSE_LIMIT = 200
DEFAULT_RUNS = 3
MAX_RUNS = 32          # 调用次数上界：`runs` 来自父侧，仍设硬上界（防协议侧被放大）


def _apply_limits(request: dict) -> dict:
    """设资源上限（best-effort：平台不支持则记 `None`，硬超时由父侧兜底）。"""
    applied: dict[str, int | None] = {}
    wanted = (
        ("RLIMIT_CPU", int(request.get("cpu_seconds") or 0)),
        ("RLIMIT_FSIZE", int(request.get("fsize_bytes") or 0)),
        ("RLIMIT_AS", int(request.get("as_bytes") or 0)),
    )
    for name, value in wanted:
        if value <= 0 or not hasattr(resource, name):
            continue
        try:
            _soft, hard = resource.getrlimit(getattr(resource, name))
            new = value if hard == resource.RLIM_INFINITY else min(value, hard)
            resource.setrlimit(getattr(resource, name), (new, new))
            applied[name] = new
        except (ValueError, OSError):
            applied[name] = None
    return applied


def _resolve_module_file(module_path: str, kernel_root: str) -> Path | None:
    """**路径层**校验：`<kernel_root>/<module_path 转路径>.py`（或包的 `__init__.py`）必须存在，
    且 resolve 后仍位于 kernel 根之内（拒绝符号链接逃出）。"""
    root = Path(kernel_root).resolve()
    rel = Path(*module_path.split("."))
    for candidate in ((root / rel).with_suffix(".py"), root / rel / "__init__.py"):
        if candidate.is_file():
            resolved = candidate.resolve()
            if resolved == root or root in resolved.parents:
                return resolved
    return None


def _load_builtin_registry(registry_path: str):
    """从校验器源码取 `BUILTIN_EXECUTORS`（**登记名**白名单的唯一来源）。"""
    spec = importlib.util.spec_from_file_location("_dh_verify_capability_binding", registry_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "BUILTIN_EXECUTORS", None)


def _error(error_type: str, message: str, **extra) -> dict:
    payload = {"status": "error", "error_type": error_type, "error": str(message)[:RESPONSE_LIMIT]}
    payload.update(extra)
    return payload


def _resolve_target(request: dict):
    """解析 impl → (可调用对象, impl_kind, module_file, limits)；失败返回 error dict。"""
    impl = request.get("impl")
    limits = _apply_limits(request)
    if not isinstance(impl, str):
        return _error("ImplShapeInvalid", f"impl 不是字符串：{impl!r}", limits=limits)

    if impl.startswith("builtin:"):
        name = impl.split(":", 1)[1]
        registry = _load_builtin_registry(request.get("registry_path") or "")
        if not registry:
            return _error("BuiltinRegistryUnavailable", "无法载入 builtin 登记表", limits=limits)
        target = registry.get(name)
        if target is None:
            return _error("BuiltinNotRegistered",
                          f"builtin:{name} 不在登记表内（只允许登记名 {sorted(registry)}）",
                          limits=limits)
        return (lambda probe: target(probe, request.get("context") or {})), "builtin", None, limits

    if impl.startswith("module:"):
        body = impl.split(":", 1)[1]
        module_path, _, fn_name = body.rpartition(":")
        prefix = request.get("module_prefix") or DEFAULT_MODULE_PREFIX
        if (not module_path or not fn_name or not module_path.startswith(prefix)
                or "__main__" in module_path):
            return _error("ImplNotAllowed",
                          f"module 路径 {module_path!r} 不满足白名单（必须前缀 {prefix}，"
                          f"且不得含 __main__）", limits=limits)
        module_file = _resolve_module_file(module_path, request.get("kernel_root") or "")
        if module_file is None:
            return _error("ModuleFileNotInKernelRoot",
                          f"{module_path!r} 未解析到 kernel 根之内的模块文件", limits=limits)
        root = str(Path(request["kernel_root"]).resolve())
        if root not in sys.path:
            sys.path.insert(0, root)
        module = importlib.import_module(module_path)
        target = getattr(module, fn_name, None)
        if not callable(target):
            return _error("ImplNotCallable", f"{module_path}:{fn_name} 不是可调用对象", limits=limits)
        return (lambda probe: target(probe)), "module", str(module_file), limits

    return _error("ImplShapeInvalid", f"impl={impl!r} 既不是 builtin: 也不是 module:",
                  limits=limits)


def _execute(request: dict) -> dict:
    """解析一次 → **同一进程内**调用 `runs` 次 → 逐次回传输出。"""
    raw_runs = request.get("runs", DEFAULT_RUNS)
    try:
        runs = int(raw_runs)
    except (TypeError, ValueError):
        return _error("RunsInvalid", f"runs 不是整数：{raw_runs!r}")
    if runs < 1 or runs > MAX_RUNS:
        return _error("RunsInvalid", f"runs={runs} 超出 [1, {MAX_RUNS}]")

    resolved = _resolve_target(request)
    if isinstance(resolved, dict):
        resolved.setdefault("runs", runs)
        return resolved
    call, impl_kind, module_file, limits = resolved

    outputs: list = []
    for index in range(runs):
        try:
            output = call(request.get("probe"))
        except BaseException as error:  # noqa: BLE001 —— 含 SystemExit / KeyboardInterrupt
            return _error(type(error).__name__, f"{type(error).__name__}: {error}",
                          run_index=index, runs=runs, impl_kind=impl_kind,
                          module_file=module_file, limits=limits)
        try:
            json.dumps(output, ensure_ascii=False)
        except (TypeError, ValueError) as error:
            return _error("OutputNotSerializable", f"{type(error).__name__}: {error}",
                          run_index=index, runs=runs, impl_kind=impl_kind,
                          module_file=module_file, limits=limits)
        outputs.append(output)
    return {"status": "ok", "output": outputs[0], "outputs": outputs, "runs": runs,
            "impl_kind": impl_kind, "module_file": module_file, "limits": limits}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: determinism_probe_worker.py <request.json> <response.json>", file=sys.stderr)
        return 2
    request_path, response_path = Path(argv[0]), Path(argv[1])
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        response = _execute(request)
    except BaseException as error:  # noqa: BLE001 —— 连 SystemExit/KeyboardInterrupt 也要变成可判定结果
        response = _error(type(error).__name__, f"{type(error).__name__}: {error}")
    response_path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
