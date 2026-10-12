"""AC-10 探针臂判据的对照用例（W3 · `xuqin-gate-harden-20261011` r1 · 设计 rev1 §6.2 / 预审 M-1）。

`importlib` 动态导入真实 `v0_skeleton/tools/ac10_probe.py`（只读），monkeypatch `_run_measure` 返回合成
`document`，再调**真实的 `_probe_case()`** ⇒ copytree / 注入 / `missing_keys` / `measured` / `fired` /
`status` 的记录构造全走**真实代码路径**，本文件**不复写任何判据映射**（平行实现 = 伪证）。**E6/E7 关 CR-2**：
真布尔但方向不符 ⇒ 必须 `fired=False`（退化成 `fired = bool(measured)` 必红，E1~E5 拦不住）；oracle 只证差异范围，一律 `PYTHONDONTWRITEBYTECODE=1`。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve()
PROBE_PATH = HERE.parents[2] / "tools" / "ac10_probe.py"
CRITERIA_KEYS = ("10a_pass", "10b_pass", "10c_pass", "10d1_pass", "10d2_pass")
C1_EDIT_LABEL = "c1:ACTION_EXTRA_NEEDS"


def _load_probe():
    """动态导入**真实的**被测模块（只读；不复制其任何实现）。"""
    spec = importlib.util.spec_from_file_location("ac10_probe_under_test", PROBE_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {PROBE_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROBE = _load_probe()


def _document(**overrides):
    """合成 `measure_behaviour_diversity.py` 的 `document`：5 键默认**真布尔** + `status="measured"`。"""
    doc = {"status": "measured", "10a_share": 0.1, "10b_share": 0.1,
           "10d1_outdoor_share": 0.5, "10d2_npcs_at_or_above_20pct": 3}
    doc.update(dict.fromkeys(CRITERIA_KEYS, True))
    doc.update(overrides)
    return doc


def _run_arm(monkeypatch, workdir, name, doc, expectations):
    """stub 外部测量工具 ⇒ 调**真实** `_probe_case()` ⇒ 真实构造出来的 arm 记录。"""
    monkeypatch.setattr(PROBE, "_run_measure", lambda copy_root, out_json: doc)
    record, meta = PROBE._probe_case(
        workdir, name, [(PROBE.C1_ANCHOR, PROBE.C1_INJECTED, C1_EDIT_LABEL)], expectations)
    assert meta[0]["line"] >= 1 and meta[0]["file"].endswith("rules/decision.py")
    return record


def _check(record, status, fired, missing):
    """断言真实记录三元组（期望值由调用方给，**不在此复写判据映射**）。"""
    assert record["status"] == status
    assert record["fired"] is fired
    assert record["missing_criteria_keys"] == missing


def test_e1_falsy_non_boolean_negative_expectation_is_degraded(monkeypatch, tmp_path):
    """E1：`10a_pass=0`（falsy 非布尔）⇒ degraded / 不打响 / 该键被列出。"""
    record = _run_arm(monkeypatch, tmp_path, "e1", _document(**{"10a_pass": 0}), [("10a_pass", False)])
    _check(record, "degraded", False, ["10a_pass"])


def test_e2_true_value_against_true_expectation_still_fires(monkeypatch, tmp_path):
    """E2：`10a_pass=True` + 期望 True ⇒ measured / 打响（防收窄误伤正期望臂）。"""
    record = _run_arm(monkeypatch, tmp_path, "e2", _document(**{"10a_pass": True}), [("10a_pass", True)])
    _check(record, "measured", True, [])


def test_e3_true_boolean_negative_expectation_still_fires(monkeypatch, tmp_path):
    """E3：真布尔 `False` + 期望 False ⇒ measured / 打响（真布尔负期望仍可命中）。"""
    record = _run_arm(monkeypatch, tmp_path, "e3", _document(**{"10a_pass": False}), [("10a_pass", False)])
    _check(record, "measured", True, [])


@pytest.mark.parametrize("value", ["", []])
def test_e4_other_falsy_non_booleans_are_degraded(monkeypatch, tmp_path, value):
    """E4：`""` / `[]` ⇒ 与 E1 同形。"""
    record = _run_arm(monkeypatch, tmp_path, "e4", _document(**{"10a_pass": value}), [("10a_pass", False)])
    _check(record, "degraded", False, ["10a_pass"])


def test_e5_unmeasured_document_is_degraded(monkeypatch, tmp_path):
    """E5：`status="skipped_missing_input"` ⇒ degraded / 不打响（回归）。"""
    record = _run_arm(monkeypatch, tmp_path, "e5", _document(status="skipped_missing_input"),
                      [("10a_pass", False)])
    _check(record, "degraded", False, [])


def test_e6_true_value_against_false_expectation_does_not_fire(monkeypatch, tmp_path):
    """E6：全真布尔 + `10a_pass=True` 但期望 False ⇒ 齐备（measured）**且** fired=False。"""
    record = _run_arm(monkeypatch, tmp_path, "e6", _document(**{"10a_pass": True}), [("10a_pass", False)])
    _check(record, "measured", False, [])


def test_e7_false_value_against_true_expectation_does_not_fire(monkeypatch, tmp_path):
    """E7：全真布尔 + `10a_pass=False` 但期望 True ⇒ 齐备（measured）**且** fired=False。"""
    record = _run_arm(monkeypatch, tmp_path, "e7", _document(**{"10a_pass": False}), [("10a_pass", True)])
    _check(record, "measured", False, [])


def test_e6_e7_are_load_bearing_against_toothless_fired(monkeypatch, tmp_path):
    """CR-2 元检验：失牙实现 `fired = bool(measured)` 在 E6/E7 上必红（status=measured ⇒ 恒 True）。"""
    record = _run_arm(monkeypatch, tmp_path, "e6-e7-projection",
                      _document(**{"10a_pass": True}), [("10a_pass", False)])
    assert record["status"] == "measured" and record["fired"] is False


ORACLE_VALUES = (0, "", [], 1, True, False, None)


def _pre_change_predicate(value):
    """**改前**谓词（`document.get(key) is None`；盘上已不存在，逐值复现用于差分）。"""
    return value is None


def _post_change_predicate(value):
    """**改后**谓词（与 `ac10_probe.py` 现盘同形：`not (v is True or v is False)`）。"""
    return not (value is True or value is False)


def test_oracle_predicate_difference_range(monkeypatch, tmp_path):
    """oracle：逐值差分 + 真实路径 status 对照（证差异范围，非正确性证明）。"""
    changed = [v for v in ORACLE_VALUES if _pre_change_predicate(v) != _post_change_predicate(v)]
    assert changed == [0, "", [], 1], changed        # 差异恰为 4 个「非布尔且非 None」值
    table = []
    for index, value in enumerate(ORACLE_VALUES):
        record = _run_arm(monkeypatch, tmp_path, "oracle-%d" % index,
                          _document(**{"10a_pass": value}), [("10a_pass", False)])
        table.append((repr(value), _post_change_predicate(value), record["status"], record["fired"]))
        if _post_change_predicate(value):
            _check(record, "degraded", False, ["10a_pass"])
        else:
            assert record["status"] == "measured" and record["missing_criteria_keys"] == [], value
    # 口径差：**改前** fired 由冻结旧表达式派生（非实测 —— 旧代码已不在盘上）
    print("oracle(value,new_missing,status,fired)=%r pre_change_fired=%r"
          % (table, [(repr(v), bool(v) is bool(False)) for v in changed]))
