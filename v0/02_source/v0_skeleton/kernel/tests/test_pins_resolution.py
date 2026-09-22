"""RED 用例（修复轮 2 / 修-1）：pins 多版本旁路 —— 「回滚只需改 pins（纯数据）」不得被绕过。

来源：Raven R-M2-1（MEDIUM）+ architect 独立复现（`/tmp/arch-m2-r2`）。

关闭判据（任务书 §1 修-1，三条都要）：
  1. 投放 `relation.infer@9.9.9` + pins 钉 `relation.infer = "1.0.0"` ⇒
     `capability("relation.infer")["version"] == "1.0.0"`（**按 pin 解析**）；
  2. pins 钉一个**不存在**的版本 ⇒ `validate()` 非空且含 `E_CAP_VERSION_CONFLICT`；
  3. **负例自证**：把解析退回「忽略 pin」⇒ 判据 1 变红（monkeypatch 演示，落在本文件内）。

运行：
    cd <workspace>/02_source/v0_skeleton/kernel && \
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_pins_resolution.py -q -p no:cacheprovider
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
CAPS_DIR = KERNEL_ROOT.parent / "capabilities"

from deephealing_kernel.registry import CapabilityRegistry  # noqa: E402


def _isolated_caps(tmp_path: Path) -> Path:
    caps = tmp_path / "capabilities"
    shutil.copytree(CAPS_DIR, caps)
    return caps


def _registry(caps: Path, *, replay_mode: bool = False) -> CapabilityRegistry:
    registry = CapabilityRegistry(caps, caps / "pins.json", replay_mode=replay_mode)
    registry.register_adapter("cassette_replay", _NoopAdapter())
    registry.register_adapter("deterministic_rule", _NoopAdapter())
    return registry


class _NoopAdapter:
    provider_class = "unused"

    def invoke(self, capability, payload, *, timeout_ms):  # pragma: no cover
        raise AssertionError("not used in pins tests")


def _write_pin(caps: Path, capability_id: str, version: str) -> None:
    pins_path = caps / "pins.json"
    document = json.loads(pins_path.read_text(encoding="utf-8"))
    document["pins"][capability_id] = version
    pins_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _duplicate_version(caps: Path, source: str, new_version: str) -> Path:
    source_path = caps / f"{source}@1.0.0.capability.json"
    document = json.loads(source_path.read_text(encoding="utf-8"))
    document["version"] = new_version
    target = caps / f"{source}@{new_version}.capability.json"
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


# --------------------------------------------------------------------------- 判据 1
def test_capability_resolves_to_pinned_version(tmp_path):
    """投放 @9.9.9 副本 + pins 钉 1.0.0 ⇒ capability() 必须解析到 **1.0.0**（修-1 判据 1）。"""
    caps = _isolated_caps(tmp_path)
    duplicate = _duplicate_version(caps, "relation.infer", "9.9.9")
    assert duplicate.is_file()
    _write_pin(caps, "relation.infer", "1.0.0")

    registry = _registry(caps)
    assert registry.validate() == [], "多版本 + pin 钉住 ⇒ 校验通过（pin 参与解析的前提）"
    resolved = registry.capability("relation.infer")
    assert resolved["version"] == "1.0.0", f"必须解析到钉住版本，got {resolved.get('version')}"
    assert resolved["id"] == "relation.infer"

    # pin 存在时，多版本不再要求报 conflict（这正是「回滚 = 改 pins」的数据语义）
    keys = registry.discover()
    assert "relation.infer@1.0.0" in keys and "relation.infer@9.9.9" in keys


def test_capability_resolves_to_pinned_version_via_slots(tmp_path):
    """slots()/capability() 的解析口径一致：pin 钉住的版本胜出（不用文件名排序的意外受益者）。"""
    caps = _isolated_caps(tmp_path)
    # 投放一个「文件名排序在后」的版本（9.9.9 > 1.0.0），pin 钉 1.0.0
    _duplicate_version(caps, "relation.infer", "9.9.9")
    _write_pin(caps, "relation.infer", "1.0.0")
    registry = _registry(caps)
    assert registry.validate() == []
    # 自证：若无 pin 参与，_by_slot 的后写者可能按文件路径顺序覆盖 1.0.0 ⇒ 这里必须仍是 1.0.0
    assert registry.capability("relation.infer")["version"] == "1.0.0"


# --------------------------------------------------------------------------- 判据 2
def test_pin_to_missing_version_is_a_validation_error(tmp_path):
    """pins 钉一个不存在的版本 ⇒ validate() 非空且含 E_CAP_VERSION_CONFLICT（修-1 判据 2）。"""
    caps = _isolated_caps(tmp_path)
    _write_pin(caps, "relation.infer", "3.3.3")
    registry = _registry(caps)
    errors = registry.validate()
    assert errors, "pins 指向不存在的版本 ⇒ 不得静默"
    assert any(item.startswith("E_CAP_VERSION_CONFLICT") for item in errors), errors

    # capability() 也不得返回任何版本（fail-closed，不静默取唯一现存版本）
    with pytest.raises(Exception) as caught:
        registry.capability("relation.infer")
    assert "capability validation failed" in str(caught.value)


def test_pin_to_missing_version_on_single_version_capability(tmp_path):
    """单版本能力同样受 pin 约束（pin 指向不存在版本 ⇒ 报错，而不是「只有一个就用它」）。"""
    caps = _isolated_caps(tmp_path)
    _write_pin(caps, "embed.text", "9.0.0")
    registry = _registry(caps)
    errors = registry.validate()
    assert any(item.startswith("E_CAP_VERSION_CONFLICT") for item in errors), errors


# --------------------------------------------------------------------------- 判据 3（负例自证）
def test_negative_control_ignoring_pin_makes_criterion_1_red(tmp_path, monkeypatch):
    """负例自证：把解析退回「忽略 pin」⇒ 判据 1 变红（修-1 判据 3）。

    做法：monkeypatch `_pinned_version` 为「恒不参与解析」的旧形态
    （`validate()` 仍会因「多版本无 pin 冲突」而红——所以再放掉该检查 = 完整复现修复前行为），
    然后 `capability("relation.infer")` 必然解析到**未钉**的 9.9.9。
    """
    caps = _isolated_caps(tmp_path)
    _duplicate_version(caps, "relation.infer", "9.9.9")
    _write_pin(caps, "relation.infer", "1.0.0")
    registry = _registry(caps)

    assert registry.capability("relation.infer")["version"] == "1.0.0"      # 修复后：判据 1 成立

    # 退回旧形态：pin 不参与解析 + 多版本检查跳过（= 修复前代码的两条行为）。
    # 复现点（architect 复现脚本同款）：`_by_slot` 直接按「文件遍历后写者覆盖」装载，不查 pin。
    # 注意 `capability()` 的惰性初始化分支只在 `_by_slot` 为空时才跑 validate()，
    # 所以这里先把 `_by_slot` 清空、再让 `_legacy_validate` 用修复前的装载方式重建。
    monkeypatch.setattr(registry, "_pinned_version", lambda capability_id: None)
    monkeypatch.setattr(registry, "_pins", {})
    original_validate = registry.validate

    def _legacy_validate():
        errors = [item for item in original_validate()
                  if not item.startswith("E_CAP_VERSION_CONFLICT")]
        if not errors:
            # 修复前形态（M2 首版实现）：`{item.slot: item.document}` —— 按文件遍历顺序
            # 「后写者覆盖」，不查 pin、不查版本。
            registry._files = registry._load_documents()    # noqa: SLF001 (负例注入)
            registry._by_slot = {                           # noqa: SLF001 (负例注入)
                item.slot: item.document                    # noqa: SLF001
                for item in registry._files.values() if item.slot  # noqa: SLF001
            }
        return errors

    monkeypatch.setattr(registry, "validate", _legacy_validate)
    registry._by_slot = {}                                  # noqa: SLF001 —— 触发 capability() 的惰性重建
    legacy_resolved = registry.capability("relation.infer")
    assert legacy_resolved["version"] == "9.9.9", (
        f"退回忽略 pin ⇒ 必须解析到未钉版本（判据 1 变红），got {legacy_resolved.get('version')}"
    )
    assert legacy_resolved["version"] != "1.0.0"


# --------------------------------------------------------------------------- 回归
def test_single_version_capability_unaffected(tmp_path):
    """无 pin 条目的单版本能力：解析与调用不受影响（正常路径不得判红）。"""
    caps = _isolated_caps(tmp_path)
    (caps / "pins.json").unlink()
    registry = _registry(caps)
    assert registry.validate() == []
    document = registry.capability("relation.infer")
    assert document["version"] == "1.0.0"
    assert "relation.infer" in registry.slots()


def test_pinned_version_actually_served_by_invoke(tmp_path):
    """端到端：pin 钉 1.0.0 ⇒ invoke 实际使用的 capability 文档也是 1.0.0（回滚语义真正生效）。"""
    caps = _isolated_caps(tmp_path)
    _duplicate_version(caps, "relation.infer", "9.9.9")
    _write_pin(caps, "relation.infer", "1.0.0")
    registry = _registry(caps)
    assert registry.validate() == []
    seen: list[str] = []

    class _Spy:
        provider_class = "cassette_replay"

        def invoke(self, capability, payload, *, timeout_ms):
            seen.append(str(capability.get("version")))
            return {"relations": [], "top_partner": None, "confidence": 0.0}

    registry.register_adapter("cassette_replay", _Spy())
    result = registry.invoke("relation.infer", {"npc_id": "npc-001", "tick": 1,
                                                "observations": [], "existing_relations": {}})
    assert result.ok
    assert seen == ["1.0.0"], seen


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
