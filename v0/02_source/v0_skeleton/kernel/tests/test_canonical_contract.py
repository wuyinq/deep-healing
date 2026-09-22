"""canonical JSON 契约的**独立序列化**对照（修复轮 C10 / 预审 M1、M3）。

问题（Raven 的质疑）：原先「跨语言逐位一致」这条判据是**拿内核自己的实现跟自己比**
（`snapshot.canonical_json` vs `tools/canonical_json.py`，同一份代码）⇒ 同源、零信息量。
契约一旦整体漂移（比如分隔符带空格），两边一起漂，判据照样绿。

本文件的做法：
  ① 在**测试里独立实现**一份「按冻结契约手写」的最小序列化器 `contract_canonical_json`
     （不 import 内核的 `canonical_json`，不 import `tools/canonical_json.py`）；
  ② 用固定样本逐条比对内核输出与独立输出 —— 这才是**跨实现**比对；
  ③ **反向对照**：把内核的 canonical 实现换成「分隔符带空格」的变体（保持 `sort_keys=True`，
     即只违反分隔符规则），在**子进程**里跑同一条判据 ⇒ 必须非 0（证明 ② 不是恒绿）。

冻结运行形态：cd <ws>/02_source/v0_skeleton/kernel && \
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_canonical_contract.py -q -p no:cacheprovider
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

KERNEL_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SRC = KERNEL_ROOT.parent / "tools" / "canonical_json.py"
ENV_NAME = "DEEPHEALING_CANONICAL_JSON"

from deephealing_kernel import snapshot as snapshot_mod  # noqa: E402

FLOAT_DIGITS = 6

SAMPLES = [
    {},
    {"b": 1, "a": 2},
    {"nested": {"z": [1, 2, 3], "a": {"deep": None}}},
    {"unicode": "幸福小区 / npc-001 \u00e9\u00fc\u4e2d\u6587"},
    {"floats": [1.0, 0.1 + 0.2, 1 / 3, -0.0, 2.5e-7]},
    {"mixed": [True, False, None, 0, -1, "s", [], {}]},
    {"trauma_flags": {"npc-001": [{"id": "t-1", "severity": 2, "since_tick": 10, "healed_tick": None}]}},
    {"big": 2**53 - 1, "neg": -(2**31)},
    # ---- F7（修复轮 2 / Raven R21）：**键序敏感**样本。原 8 个样本的键**全为小写** ⇒
    # 「键序按 `key.lower()`」这类契约漂移**检不出**（假绿）。以下样本让该子类可被检出。
    # 大写 / 混合大小写（ASCII 码点序与 lower 序不同：`"B"`=0x42 < `"a"`=0x61，但 `"b"` > `"a"`）
    {"B": 1, "a": 2},
    {"Z": {"B": 1, "a": 2}, "a": {"y": 1, "X": 2}},
    # 下划线（`"_"`=0x5F，介于大写与小写之间 ⇒ 与 lower 序分歧）
    {"_id": 1, "A": 2, "a": 3, "Zz": 4, "z": 5},
    {"env": {"FOO_API_KEY": "x", "foo": "y", "_private": 3, "Public": 4}},
    # Unicode 键（码点序与 lower 序在非 ASCII 上同样分歧）
    {"Ä": 1, "a": 2, "Ω": 3, "ω": 4, "中文": 5, "Z": 6},
    # ≥2 层嵌套 + 每层键序敏感（任一层的键序漂移都会被检出）
    {"outer": {"Inner": {"Deep": {"z": 1, "A": 2}}, "inner": {"deep": {"Z": 3, "a": 4}}}},
    {"events": [{"Type": "npc.action", "actor": "npc-001", "Payload": {"B": 1, "a": 2}}]},
    {"snapshot": {"State_Hash": "abc", "state_hash": "def", "_reserved": None}},
]


def _lower_sorted_for_probe(item):
    """探针用：按 `key.lower()` 递归排序（与被测实现无关，仅用于证明样本有判别力）。"""
    if isinstance(item, dict):
        return {k: _lower_sorted_for_probe(v) for k, v in sorted(item.items(), key=lambda p: p[0].lower())}
    if isinstance(item, list):
        return [_lower_sorted_for_probe(v) for v in item]
    return item


def contract_canonical_json(value):
    """**独立**按冻结契约实现的规范化序列化（手写，不依赖被测实现）。

    契约（snapshot.schema.json normalization / canonical_json.py 头部）：
      - 键按 Unicode 码点字典序排序
      - 分隔符 `,` 与 `:`，**无空格**
      - UTF-8，`ensure_ascii=False`
      - 整数不带小数点；浮点四舍五入到 6 位小数
    """
    def normalize(item):
        if isinstance(item, bool) or item is None:
            return item
        if isinstance(item, float):
            return round(item, FLOAT_DIGITS)
        if isinstance(item, dict):
            return {key: normalize(val) for key, val in item.items()}
        if isinstance(item, list):
            return [normalize(val) for val in item]
        return item

    def emit(item):
        # 手写编码器：不经过 json.dumps 的分隔符参数，避免与被测实现共享同一处配置
        if item is None:
            return "null"
        if item is True:
            return "true"
        if item is False:
            return "false"
        if isinstance(item, int):
            return str(item)
        if isinstance(item, float):
            text = repr(item)
            if "e" in text or "E" in text:          # 极小/极大浮点：json 用 e 记法，这里对齐 json 输出
                return json.dumps(item)
            return text
        if isinstance(item, str):
            return json.dumps(item, ensure_ascii=False)
        if isinstance(item, list):
            return "[" + ",".join(emit(val) for val in item) + "]"
        if isinstance(item, dict):
            pairs = sorted(item.items(), key=lambda pair: pair[0])
            return "{" + ",".join(
                json.dumps(key, ensure_ascii=False) + ":" + emit(val) for key, val in pairs
            ) + "}"
        raise AssertionError(f"unsupported type: {type(item)!r}")

    return emit(normalize(value))


def contract_sha256(value) -> str:
    return hashlib.sha256(contract_canonical_json(value).encode("utf-8")).hexdigest()


def test_kernel_canonical_matches_independent_contract_serialization():
    """① 内核输出必须与**独立实现**逐位一致（跨实现比对，不是自己跟自己比）。"""
    for sample in SAMPLES:
        expected = contract_canonical_json(sample)
        assert snapshot_mod.canonical_json(sample) == expected, sample
        assert snapshot_mod.hash_object(sample) == contract_sha256(sample), sample

    # 契约的**判别力**自证：独立实现自己也要对「带空格」变体说不
    spaced = json.dumps({}, separators=(", ", ": "))
    assert spaced == "{}"                                   # 空对象无分隔符 ⇒ 用它做对照是零命中
    assert json.dumps({"a": 1, "b": [1, 2]}, sort_keys=True, separators=(",", ":")) != json.dumps(
        {"a": 1, "b": [1, 2]}, sort_keys=True, separators=(", ", ": ")
    )


def _write_mutant(destination: Path) -> Path:
    """把真实实现复制一份，**只**改分隔符（保持 sort_keys=True）——即「契约整体漂移」的最小形态。"""
    source = CANONICAL_SRC.read_text(encoding="utf-8")
    assert 'separators=(",", ":")' in source, "夹具锚点失效：真实实现的分隔符写法变了"
    destination.write_text(source.replace('separators=(",", ":")', 'separators=(", ", ": ")'),
                            encoding="utf-8")
    return destination


def _write_lowercase_key_mutant(destination: Path) -> Path:
    """把真实实现复制一份，**只**改键序规则（`sort_keys=True` → 按 `key.lower()` 排序）。

    F7（修复轮 2 / Raven R21）：这是「契约整体漂移」中**键序子类**的最小形态，
    原先因为样本键全小写而**检不出**。本变体保持其它一切不变（分隔符 / ensure_ascii / float 位数）。
    """
    source = CANONICAL_SRC.read_text(encoding="utf-8")
    anchor = "def canonical_json(value: Any) -> str:"
    assert anchor in source, "夹具锚点失效：canonical_json 定义变了"
    helper = (
        "def _lower_sorted(item: Any) -> Any:\n"
        "    if isinstance(item, dict):\n"
        "        return {k: _lower_sorted(v) for k, v in sorted(item.items(), key=lambda p: p[0].lower())}\n"
        "    if isinstance(item, list):\n"
        "        return [_lower_sorted(v) for v in item]\n"
        "    return item\n\n\n"
    )
    source = source.replace(anchor, helper + anchor)
    old = "        _normalize(value),\n        sort_keys=True,"
    assert old in source, "夹具锚点失效：canonical_json 的 dumps 调用形态变了"
    source = source.replace(old, "        _lower_sorted(_normalize(value)),\n        sort_keys=False,")
    destination.write_text(source, encoding="utf-8")
    return destination


def test_contract_assertion_goes_red_under_mutated_canonical(tmp_path):
    """③ 反向对照：内核 canonical 实现漂移（分隔符带空格）⇒ 判据**必须**非 0。

    只跑本文件里的比对用例；子进程通过 `DEEPHEALING_CANONICAL_JSON` 注入变体实现。
    """
    mutant = _write_mutant(tmp_path / "canonical_json.mutant.py")

    baseline = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_canonical_contract.py::"
         "test_kernel_canonical_matches_independent_contract_serialization",
         "-q", "-p", "no:cacheprovider"],
        cwd=KERNEL_ROOT, capture_output=True, text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr   # 未注入时必须绿

    mutated = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_canonical_contract.py::"
         "test_kernel_canonical_matches_independent_contract_serialization",
         "-q", "-p", "no:cacheprovider"],
        cwd=KERNEL_ROOT, capture_output=True, text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **{ENV_NAME: str(mutant)}),
    )
    assert mutated.returncode != 0, (
        "canonical 实现漂移后判据仍为绿 ⇒ 该判据是零命中绿\n" + mutated.stdout + mutated.stderr
    )
    assert "test_kernel_canonical_matches_independent_contract_serialization" in (
        mutated.stdout + mutated.stderr
    )


def test_contract_assertion_goes_red_under_lowercase_key_order(tmp_path):
    """F7 反向对照（Raven R21）：键序改成 `key.lower()` ⇒ 判据**必须**非 0。

    原 8 个样本的键**全为小写** ⇒ 这一子类检不出（假绿）。样本扩充后必须可达。
    """
    mutant = _write_lowercase_key_mutant(tmp_path / "canonical_json.lowerkeys.py")

    baseline = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_canonical_contract.py::"
         "test_kernel_canonical_matches_independent_contract_serialization",
         "-q", "-p", "no:cacheprovider"],
        cwd=KERNEL_ROOT, capture_output=True, text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr

    mutated = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_canonical_contract.py::"
         "test_kernel_canonical_matches_independent_contract_serialization",
         "-q", "-p", "no:cacheprovider"],
        cwd=KERNEL_ROOT, capture_output=True, text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **{ENV_NAME: str(mutant)}),
    )
    assert mutated.returncode != 0, (
        "键序漂移（key.lower()）后判据仍为绿 ⇒ 该子类未被样本覆盖\n" + mutated.stdout + mutated.stderr
    )
    assert "test_kernel_canonical_matches_independent_contract_serialization" in (
        mutated.stdout + mutated.stderr
    )


def test_samples_actually_exercise_case_and_depth():
    """F7 自证：样本集必须**真的**含键序敏感形态（否则上一条反向对照会退化成零命中绿）。"""
    keys: set[str] = set()

    def collect(item):
        if isinstance(item, dict):
            keys.update(item)
            for value in item.values():
                collect(value)
        elif isinstance(item, list):
            for value in item:
                collect(value)

    for sample in SAMPLES:
        collect(sample)

    assert any(key != key.lower() for key in keys), "样本里必须有非全小写键"
    assert any(not key.isascii() for key in keys), "样本里必须有非 ASCII 键"
    assert any("_" in key for key in keys), "样本里必须含下划线键"
    # 「任一层的键序漂移可被检出」：至少有一个样本在 lower 序与码点序下**序列化结果不同**
    order_sensitive = 0
    for sample in SAMPLES:
        codepoint = contract_canonical_json(sample)
        lowered = json.dumps(
            _lower_sorted_for_probe(sample), sort_keys=False, separators=(",", ":"), ensure_ascii=False
        )
        if codepoint != lowered:
            order_sensitive += 1
    assert order_sensitive >= 6, order_sensitive
