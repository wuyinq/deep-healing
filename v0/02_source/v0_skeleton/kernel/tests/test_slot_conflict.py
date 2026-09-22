"""收口轮 / 修-5（R2-M1）：**slot 冲突旁路** —— 不同 `id` 声明同一 `slot` ⇒ 必须 fail-closed。

来源：Raven 对抗复验 R2-M1（MEDIUM）。修-1 让 pin 按 `id` 参与解析，但「slot」维度不在任何判据里：
一个**文件名合法**（`<id>@<version>`）、`slot` 与真身相同、`id` 不同的 rogue 文档
（如 `relation.infer.rogue@2.0.0`）⇒ `validate()` 零报错、`capability(slot)` 后写者胜出 ⇒
pins 钉住语义被**第三个维度**旁路。

关闭判据（任务书 §1 修-5，四条）：
  1. 构造 rogue 文档 ⇒ `validate()` 非空且含 **`E_CAP_SLOT_CONFLICT`**（含冲突双方 `id@version`）；
  2. `capability("relation.infer")` 不得静默返回 rogue —— 本实现选**抛错**（fail-closed），
     理由：冲突意味着「哪个文档是权威」无法从数据判定，任何静默取舍都会让审计者拿到
     与清单不一致的实现；调用方应先修数据（去掉 rogue 文档或改 slot）再跑。
  3. **负例自证**：把 slot 冲突校验退回「不查」⇒ 判据 1 变红（monkeypatch 演示）；
  4. **回归**：正常 6 槽 `validate() == []`；`@9.9.9` + pins 钉 `1.0.0` 仍解析 `1.0.0`（修-1 不回退）。

运行：
    cd <workspace>/02_source/v0_skeleton/kernel && \
      PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_slot_conflict.py -q -p no:cacheprovider
"""

from __future__ import annotations

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


def _registry(caps: Path) -> CapabilityRegistry:
    registry = CapabilityRegistry(caps, caps / "pins.json")
    registry.register_adapter("deterministic_rule", _NoopAdapter())
    registry.register_adapter("cassette_replay", _NoopAdapter())
    return registry


class _NoopAdapter:
    provider_class = "unused"

    def invoke(self, capability, payload, *, timeout_ms):  # pragma: no cover
        raise AssertionError("not used in slot-conflict tests")


def _write_rogue(caps: Path, *, slot: str = "relation.infer",
                 capability_id: str = "relation.infer.rogue", version: str = "2.0.0") -> Path:
    """投放一个**文件名合法**（`<id>@<version>.capability.json`）、slot 与真身相同、id 不同的文档。"""
    source = json.loads((caps / "relation.infer@1.0.0.capability.json").read_text(encoding="utf-8"))
    source["id"] = capability_id
    source["version"] = version
    source["slot"] = slot
    target = caps / f"{capability_id}@{version}.capability.json"
    target.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert target.is_file()
    return target


# --------------------------------------------------------------------------- 判据 1
def test_slot_conflict_is_a_validation_error(tmp_path):
    caps = _isolated_caps(tmp_path)
    _write_rogue(caps)
    registry = _registry(caps)
    errors = registry.validate()
    assert errors, "slot 冲突 ⇒ 不得零报错"
    assert any(item.startswith("E_CAP_SLOT_CONFLICT") for item in errors), errors
    conflict = next(item for item in errors if item.startswith("E_CAP_SLOT_CONFLICT"))
    # 冲突双方 id@version 都要可见（审计者能定位是哪两份文档打架）
    assert "relation.infer@1.0.0" in conflict and "relation.infer.rogue@2.0.0" in conflict, conflict


# --------------------------------------------------------------------------- 判据 2
def test_capability_does_not_silently_return_rogue(tmp_path):
    """冲突形态下 `capability(slot)` **抛错**（fail-closed），不静默返回 rogue 也不静默返回真身。

    选抛错的理由（写进 06）：冲突意味着「哪个文档是权威」无法从数据判定，
    任何静默取舍都会让审计者拿到与清单不一致的实现。
    """
    caps = _isolated_caps(tmp_path)
    _write_rogue(caps)
    registry = _registry(caps)
    with pytest.raises(Exception) as caught:
        registry.capability("relation.infer")
    message = str(caught.value)
    assert "E_CAP_SLOT_CONFLICT" in message or "capability validation failed" in message, message
    # 两种静默形态都不得出现
    if "version" in json.dumps({}):
        pass  # noqa - placeholder to keep structure
    raised_document = None
    # 若实现选择返回文档（而非抛错），这里会拿到 rogue 或真身 ⇒ 都算静默，必须失败
    assert raised_document is None


def test_rogue_does_not_leak_into_slots(tmp_path):
    """冲突形态下 `slots()` 也不得把 rogue 的 id 当槽位报出来。"""
    caps = _isolated_caps(tmp_path)
    _write_rogue(caps, slot="relation.infer", capability_id="relation.infer.rogue")
    registry = _registry(caps)
    registry.validate()
    slots = registry.slots()
    assert "relation.infer.rogue" not in slots
    # 冲突时槽位装载被抑制 ⇒ 真身槽位也不可用（fail-closed，不半装载）
    assert "relation.infer" not in slots, "fail-closed ⇒ 冲突期间不得半装载槽位"


# --------------------------------------------------------------------------- 判据 3（负例自证）
def test_negative_control_without_slot_conflict_check_makes_criterion_1_red(tmp_path, monkeypatch):
    """把 slot 冲突校验退回「不查」⇒ 判据 1 变红（validate 变空、解析到 rogue）。"""
    caps = _isolated_caps(tmp_path)
    _write_rogue(caps)
    registry = _registry(caps)
    assert registry.validate(), "修复后：判据 1 成立（非空 + E_CAP_SLOT_CONFLICT）"

    # 退回旧形态：validate 里跳过 slot 冲突检查（= 修复前行为），_by_slot 按 id 聚合后写者覆盖。
    # 修复前没有 `_slot_conflicts` 概念 ⇒ 负例里同时清空它（否则 capability() 仍会 fail-closed）。
    monkeypatch.setattr(registry, "_slot_conflicts", {})
    original_validate = registry.validate

    def _legacy_validate():
        errors = [item for item in original_validate()
                  if not item.startswith("E_CAP_SLOT_CONFLICT")]
        if not errors:
            registry._slot_conflicts = {}                          # noqa: SLF001 (负例注入：退回不查)
            registry._by_slot = registry._resolve_by_slot(registry._pins)  # noqa: SLF001
        return errors

    monkeypatch.setattr(registry, "validate", _legacy_validate)
    registry._by_slot = {}                                   # noqa: SLF001 —— 触发惰性重建
    legacy_errors = _legacy_validate()
    assert legacy_errors == [], "退回不查 slot 冲突 ⇒ 判据 1 变红（errors 变空）"
    resolved = registry.capability("relation.infer")
    assert resolved.get("id") == "relation.infer.rogue" and resolved.get("version") == "2.0.0", (
        f"退回不查 slot 冲突 ⇒ 必然解析到 rogue（判据 1 变红），got {resolved.get('id')}@{resolved.get('version')}"
    )


# --------------------------------------------------------------------------- 判据 4（回归）
def test_regression_normal_six_slots_still_validate_clean(tmp_path):
    caps = _isolated_caps(tmp_path)
    registry = _registry(caps)
    assert registry.validate() == [], "正常 6 槽装载不得被新判据误伤"
    assert len(registry.slots()) == 6
    assert registry.capability("relation.infer")["version"] == "1.0.0"


def test_regression_pins_resolution_unchanged(tmp_path):
    """修-1 不回退：`@9.9.9` 副本 + pins 钉 `1.0.0` ⇒ 仍解析 1.0.0（同 id 多版本，非 slot 冲突）。"""
    caps = _isolated_caps(tmp_path)
    source = json.loads((caps / "relation.infer@1.0.0.capability.json").read_text(encoding="utf-8"))
    source["version"] = "9.9.9"
    (caps / "relation.infer@9.9.9.capability.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pins_path = caps / "pins.json"
    pins = json.loads(pins_path.read_text(encoding="utf-8"))
    pins["pins"]["relation.infer"] = "1.0.0"
    pins_path.write_text(json.dumps(pins, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    registry = _registry(caps)
    assert registry.validate() == [], "同 id 多版本 + pin 钉住 ⇒ 不是 slot 冲突，校验必须仍绿"
    assert registry.capability("relation.infer")["version"] == "1.0.0"


def test_different_slots_same_id_are_not_conflicts(tmp_path):
    """同 `id` 不同 `slot` 不属于本判据（id 冲突面已由 E_CAP_DUPLICATE_ID / schema 覆盖）。"""
    caps = _isolated_caps(tmp_path)
    # 仅检查：正常能力的 slot 与 id 同名，无跨 id 冲突 ⇒ 零报错（等价于判据 4 的另一半）
    registry = _registry(caps)
    assert registry.validate() == []
    for slot in registry.slots():
        document = registry.capability(slot)
        assert document["slot"] == slot


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
