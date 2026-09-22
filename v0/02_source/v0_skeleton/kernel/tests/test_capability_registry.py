"""RED 用例：能力注册表数据驱动发现 / provider 切换 / 新增能力不改内核代码（AC-13）。

运行（实现完成后）：
    cd <workspace>/02_source/v0_skeleton/kernel && python3 -m pytest tests/test_capability_registry.py -q

**M2 状态**：本文件 6 条用例在 M1 是 `skip`（骨架未实现），M2 **全部转为真跑**（AC-M2-2 判据）。
每条都带**自证反例**（把被测行为退回错误形态 ⇒ 断言必须变红）。
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
WS_ROOT = KERNEL_ROOT.parents[2]
SKELETON = KERNEL_ROOT.parent
CAPS_DIR = SKELETON / "capabilities"
PINS = CAPS_DIR / "pins.json"

from deephealing_kernel.providers.cassette import CassetteMiss, CassetteReplayProvider, CassetteStore  # noqa: E402
from deephealing_kernel.providers.deterministic_rule import DeterministicRuleProvider  # noqa: E402
from deephealing_kernel.registry import CapabilityRegistry, InvocationResult  # noqa: E402


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _registry(tmp_path: Path | None = None, *, caps_dir: Path | None = None,
              cassette: CassetteStore | None = None, replay_mode: bool = False) -> CapabilityRegistry:
    store = cassette if cassette is not None else CassetteStore(tmp_path / "cassettes" if tmp_path else Path("/tmp/dh-unused"))
    registry = CapabilityRegistry(caps_dir or CAPS_DIR, (caps_dir / "pins.json") if caps_dir else PINS,
                                  cassette_store=store, replay_mode=replay_mode)
    registry.register_adapter("remote_api", _UnusedAdapter())
    registry.register_adapter("local_model", _UnusedAdapter())
    registry.register_adapter("deterministic_rule", DeterministicRuleProvider())
    registry.register_adapter("cassette_replay", CassetteReplayProvider(store))
    return registry


class _UnusedAdapter:
    """占位适配器：注册面齐备，但**从不**被本文件的用例选中（避免真实网络调用）。"""

    provider_class = "unused"

    def invoke(self, capability, payload, *, timeout_ms):  # pragma: no cover - 不会被调用
        raise AssertionError("this adapter must never be invoked in unit tests")


def _capability_document(capability_id: str = "probe.only", version: str = "1.0.0") -> dict:
    """合成能力文档。

    ⚠ `slot` 必须是 `capability.schema.json` **枚举内的真实槽位**（`embed.text`）——
    合成 `slot` 会被 schema 拒收（这本身就是 E_CAP_SCHEMA 判据的一部分）。
    """
    return {
        "id": capability_id, "version": version, "slot": "embed.text",
        "input_schema": {"type": "object", "additionalProperties": False, "required": ["text"],
                         "properties": {"text": {"type": "string"}}},
        "output_schema": {"type": "object", "additionalProperties": False, "required": ["ok"],
                          "properties": {"ok": {"type": "boolean"}}},
        "providers": [
            {"class": "remote_api", "impl": "builtin:openai_compatible_chat", "priority": 10,
             "determinism": "non_deterministic", "determinism_note": "best_effort"},
            {"class": "cassette_replay", "impl": "builtin:cassette_replay", "priority": 20,
             "determinism": "deterministic", "determinism_note": "replayable"},
            {"class": "local_model", "impl": "builtin:ollama_chat", "priority": 30,
             "determinism": "non_deterministic", "determinism_note": "best_effort"},
            {"class": "deterministic_rule", "impl": "module:deephealing_kernel.providers.deterministic_rule:embed_text_rule",
             "priority": 40, "determinism": "deterministic", "determinism_note": "pure"},
        ],
        "cost": {"usd_per_1k_in": 0.0001, "usd_per_1k_out": 0.0002, "est_tokens_in": 10,
                 "est_tokens_out": 5, "currency": "USD"},
        "latency_ms_budget": 1000, "timeout_ms": 2000,
        "fallback": {
            "on_timeout": {"provider": "deterministic_rule",
                           "impl": "module:deephealing_kernel.providers.deterministic_rule:embed_text_rule"},
            "on_error": {"provider": "deterministic_rule",
                         "impl": "module:deephealing_kernel.providers.deterministic_rule:embed_text_rule"},
            "on_invalid_schema": {"provider": "deterministic_rule",
                                  "impl": "module:deephealing_kernel.providers.deterministic_rule:embed_text_rule"},
            "on_budget_exhausted": {"provider": "deterministic_rule",
                                    "impl": "module:deephealing_kernel.providers.deterministic_rule:embed_text_rule"},
            "on_cassette_miss": "deterministic_stub",
        },
        "determinism": {"mode": "pure",
                        "cassette_key_fields": ["capability_id", "capability_version",
                                                "canonical_input_hash", "provider"],
                        "seed_policy": "no_randomness"},
        "safety": {"secrets_in_context": False, "redact_fields": ["headers.Authorization"],
                   "max_output_bytes": 1024, "schema_strict": True},
        "calibration": {"sample_count": 24, "p50_ms": 10.0, "p90_ms": 20.0, "p95_ms": 30.0, "p99_ms": 40.0,
                        "max_ms": 50.0, "derivation_rule": "test", "derivation_rule_sha256": "0" * 64,
                        "candidate_strict_ms": 100, "candidate_loose_ms": 200,
                        "accepted_degradation_range": "0.00-0.30", "command": "test", "workdir": "/tmp",
                        "exit": 0, "log_path": "/tmp/x.json"},
        "rule_layer_adoption": {"allowed": True, "provider_classes_allowed": ["deterministic_rule"],
                                "consistency_check": {"required": True, "runs": 3}},
    }


def _write_capability(directory: Path, document: dict, *, filename: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    name = filename or f"{document.get('id')}@{document.get('version')}.capability.json"
    path = directory / name
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- 发现
def test_registry_discovers_capability_files(tmp_path):
    """丢入一个 *.capability.json 即被发现（无需改任何源码）。"""
    caps = tmp_path / "capabilities"
    _write_capability(caps, _capability_document("probe.only"))
    registry = _registry(tmp_path, caps_dir=caps)
    assert registry.discover() == ["probe.only@1.0.0"]
    assert registry.validate() == []
    assert registry.slots() == ["embed.text"]

    # 再加一个：**不改任何源码**，只加数据文件
    _write_capability(caps, _capability_document("probe.only.second"))
    assert registry.discover() == ["probe.only.second@1.0.0", "probe.only@1.0.0"]

    # 自证反例：把文件后缀改掉 ⇒ 发现面为空（证明发现真的是按数据 glob，不是硬编码列表）
    (caps / "probe.only@1.0.0.capability.json").rename(caps / "probe.only@1.0.0.json")
    (caps / "probe.only.second@1.0.0.capability.json").rename(caps / "probe.only.second@1.0.0.json")
    assert registry.discover() == []


def test_new_capability_requires_no_kernel_source_change(tmp_path):
    """新增 relation.infer@1.0.0 后，kernel/ 源码哈希必须不变（AC-13 判据）。

    实验在**隔离副本**内做（真实时序对）：`before` = 副本去掉 `providers/adapters/relation_infer.py`，
    `after` = 副本补回该文件。真实内核根不在本用例的写入面内。
    """
    tool = _load_module("kernel_digest_for_registry_test", KERNEL_ROOT / "tools" / "kernel_digest.py")

    copy = tmp_path / "kernel-copy"
    shutil.copytree(KERNEL_ROOT / "deephealing_kernel", copy / "deephealing_kernel",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    adapter_dir = copy / "deephealing_kernel" / "providers" / "adapters"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    adapter_source = (KERNEL_ROOT / "deephealing_kernel" / "providers" / "adapters" / "relation_infer.py")
    adapter_text = adapter_source.read_text(encoding="utf-8")
    (adapter_dir / "relation_infer.py").unlink(missing_ok=True)   # before = 未加入 adapter 的形态

    # before = 未加入 adapter 的形态
    before = tool.kernel_digest(copy)
    (adapter_dir / "relation_infer.py").write_text(adapter_text, encoding="utf-8")
    after = tool.kernel_digest(copy)

    diff = tool.diff_snapshots(before, after)
    assert diff["changed"] == [], diff["changed"]
    assert diff["removed"] == []
    assert diff["added"] == ["providers/adapters/relation_infer.py"], diff["added"]
    ok, reasons = tool.criterion_ok(diff)
    assert ok, reasons

    # 自证反例：改 tick.py 一字节 ⇒ changed 非空（判据不是恒绿）
    tick_path = copy / "deephealing_kernel" / "tick.py"
    tick_path.write_bytes(b"\x00" + tick_path.read_bytes()[1:])
    flipped = tool.diff_snapshots(before, tool.kernel_digest(copy))
    assert flipped["changed"] == ["tick.py"], flipped["changed"]
    assert tool.criterion_ok(flipped)[0] is False

    # 自证反例 2：把 adapter 放到**非豁免目录** ⇒ added 越界 ⇒ 判据必须红
    stray = copy / "deephealing_kernel" / "stray_rule.py"
    stray.write_text("# 非 adapter 目录\n", encoding="utf-8")
    out_of_bounds = tool.diff_snapshots(before, tool.kernel_digest(copy))
    assert tool.criterion_ok(out_of_bounds)[0] is False


# --------------------------------------------------------------------------- provider 切换
def test_provider_switch_remote_to_cassette_to_rule(tmp_path):
    """remote_api → cassette_replay → deterministic_rule 三类均产出通过 output_schema 的结果。

    本用例**不发起真实网络调用**：`remote_api` 的位置用「录制源 = deterministic_rule」的等价路径
    代替（设计 §6：`deterministic_rule ↔ cassette_replay` 的 cassette 由 rule 录制）；
    `remote_api` 的**真实调用**证据在 `spikes/s8-registry/**` 的真跑日志里。
    """
    store = CassetteStore(tmp_path / "cassettes")
    registry = _registry(tmp_path, cassette=store)
    assert registry.validate() == []
    payload = {"texts": ["幸福小区"]}

    rule_result = registry.invoke("embed.text", payload, force_provider="deterministic_rule")
    assert isinstance(rule_result, InvocationResult) and rule_result.ok
    assert rule_result.provider_class == "deterministic_rule"

    replay_result = registry.invoke("embed.text", payload, force_provider="cassette_replay")
    assert replay_result.provider_class == "cassette_replay"
    assert replay_result.output == rule_result.output, "rule 录制的 cassette 回放必须逐字节等价"

    # 改 provider ⇒ cassette 键必须变化（四键口径，M-6）
    key_rule = store.cassette_key(registry.capability("embed.text"), payload, "deterministic_rule")
    key_remote = store.cassette_key(registry.capability("embed.text"), payload, "remote_api")
    assert key_rule != key_remote
    # 两种键形态（设计 §3.1 与骨架四元形态）必须同值
    from deephealing_kernel.snapshot import hash_object

    assert key_rule == store.cassette_key_from_parts(
        "embed.text", "1.0.0", hash_object(payload), "deterministic_rule")

    # 自证反例：把 payload 改一个字符 ⇒ 键必须变（否则「同输入」判据零命中）
    assert store.cassette_key(registry.capability("embed.text"), {"texts": ["幸福小区!"]},
                              "deterministic_rule") != key_rule


def test_invalid_capability_file_is_rejected(tmp_path):
    """非法能力文件（缺 safety / secrets_in_context=true）必须被拒绝加载且不静默。"""
    caps = tmp_path / "capabilities"

    # ① 缺 safety ⇒ E_CAP_SCHEMA
    broken = _capability_document("probe.broken")
    del broken["safety"]
    _write_capability(caps, broken, filename="probe.broken@1.0.0.capability.json")
    errors = _registry(tmp_path, caps_dir=caps).validate()
    assert any(item.startswith("E_CAP_SCHEMA") for item in errors), errors

    # ② secrets_in_context=true ⇒ E_CAP_SCHEMA
    caps2 = tmp_path / "caps2"
    leaky = _capability_document("probe.leaky")
    leaky["safety"]["secrets_in_context"] = True
    _write_capability(caps2, leaky, filename="probe.leaky@1.0.0.capability.json")
    assert any(item.startswith("E_CAP_SCHEMA") for item in _registry(tmp_path, caps_dir=caps2).validate())

    # ③ 未登记 impl ⇒ E_CAP_UNREGISTERED
    caps3 = tmp_path / "caps3"
    unregistered = _capability_document("probe.unregistered")
    unregistered["providers"][3]["impl"] = "module:somewhere_else.module:fn"
    _write_capability(caps3, unregistered, filename="probe.unregistered@1.0.0.capability.json")
    assert any(item.startswith("E_CAP_UNREGISTERED") for item in _registry(tmp_path, caps_dir=caps3).validate())

    # ④ 无适配器 / 未注册 provider ⇒ E_CAP_PROVIDER_UNRESOLVED
    #    归因声明：`providers[].class` 的**枚举面**由 `capability.schema.json` 先关掉
    #    （写 `magic_model` ⇒ E_CAP_SCHEMA）；因此本用例走**可达路径**：schema 合法但
    #    该 provider class **没有注册适配器**。
    caps4 = tmp_path / "caps4"
    _write_capability(caps4, _capability_document("probe.noadapter"),
                      filename="probe.noadapter@1.0.0.capability.json")
    bare = CapabilityRegistry(caps4, caps4 / "pins.json")
    assert bare.validate() == [], "schema 合法（四类 class 均在枚举内）"
    with pytest.raises(Exception) as caught:
        bare.invoke("embed.text", {"text": "x"})
    assert "E_CAP_PROVIDER_UNRESOLVED" in str(caught.value), str(caught.value)
    # 另一条可达路径：强制一个**未注册适配器**的 provider class
    partial = _registry(tmp_path, caps_dir=caps4)
    partial._adapters.pop("local_model", None)  # noqa: SLF001 (判据注入)
    with pytest.raises(Exception) as caught2:
        partial.invoke("embed.text", {"text": "x"}, force_provider="local_model")
    assert "E_CAP_PROVIDER_UNRESOLVED" in str(caught2.value), str(caught2.value)
    # 枚举外的 class ⇒ 由 schema 关掉（E_CAP_SCHEMA），不是零命中
    caps4b = tmp_path / "caps4b"
    bad_class = _capability_document("probe.badclass")
    bad_class["providers"][0]["class"] = "magic_model"
    _write_capability(caps4b, bad_class, filename="probe.badclass@1.0.0.capability.json")
    assert any(item.startswith("E_CAP_SCHEMA") for item in _registry(tmp_path, caps_dir=caps4b).validate())

    # ⑤ 重复 id@version ⇒ E_CAP_DUPLICATE_ID（同 key 的两份文件出现在不同子目录：rglob 会都扫到）
    caps5 = tmp_path / "caps5"
    _write_capability(caps5, _capability_document("probe.dup"))
    _write_capability(caps5 / "nested", _capability_document("probe.dup"))
    errors5 = _registry(tmp_path, caps_dir=caps5).validate()
    assert any(item.startswith("E_CAP_DUPLICATE_ID") for item in errors5), errors5

    # ⑥ 同 id 多版本且 pins.json 未钉 ⇒ E_CAP_VERSION_CONFLICT
    caps6 = tmp_path / "caps6"
    _write_capability(caps6, _capability_document("probe.multi", "1.0.0"))
    _write_capability(caps6, _capability_document("probe.multi", "2.0.0"))
    _write_capability(caps6, {"schema_version": "1.0.0", "pins": {}, "provider_overrides": {}},
                      filename="pins.json")
    assert any(item.startswith("E_CAP_VERSION_CONFLICT")
               for item in _registry(tmp_path, caps_dir=caps6).validate())

    # 自证反例：合法清单必须**零**错误（证明上面不是「恒红」）
    assert _registry(tmp_path).validate() == []


def test_cassette_miss_is_fail_closed(tmp_path):
    """回放模式下 cassette miss 必须抛 E_CASSETTE_MISS，不得静默切远端。"""
    store = CassetteStore(tmp_path / "cassettes")
    registry = _registry(tmp_path, cassette=store, replay_mode=True)
    with pytest.raises(CassetteMiss) as caught:
        registry.invoke("embed.text", {"texts": ["never recorded"]})
    assert caught.value.code == "E_CASSETTE_MISS"
    assert any(entry.get("event") == "cassette.miss" for entry in registry.journal), registry.journal

    # 自证反例：同输入**先录制**后回放 ⇒ 必须命中（证明上面不是「恒抛」）
    recording = _registry(tmp_path, cassette=store)
    recording.invoke("embed.text", {"texts": ["never recorded"]}, force_provider="deterministic_rule")
    replayed = registry.invoke("embed.text", {"texts": ["never recorded"]})
    assert replayed.provider_class == "cassette_replay"


def test_invalid_model_output_falls_back(tmp_path):
    """模型输出不合 schema → fallback 链降级且落 capability.fallback 事件。"""
    store = CassetteStore(tmp_path / "cassettes")
    registry = _registry(tmp_path, cassette=store)

    class _BadOutput:
        provider_class = "remote_api"

        def invoke(self, capability, payload, *, timeout_ms):
            return {"not_in_schema": True}

    registry.register_adapter("remote_api", _BadOutput())
    result = registry.invoke("emotion.appraise", {"npc_id": "npc-001", "tick": 1,
                                                 "event_summary": "还好", "current_emotion": {}},
                             force_provider="remote_api")
    assert result.ok and result.fallback_reason == "on_invalid_schema"
    assert result.provider_class == "deterministic_rule"
    fallbacks = [entry for entry in registry.journal if entry.get("event") == "capability.fallback"]
    assert fallbacks and fallbacks[-1]["reason"] == "on_invalid_schema"

    # 自证反例：合 schema 的输出 ⇒ **不得**产生 fallback（证明降级不是恒触发）
    registry.journal.clear()
    good = registry.invoke("emotion.appraise", {"npc_id": "npc-001", "tick": 1,
                                               "event_summary": "还好", "current_emotion": {}},
                           force_provider="deterministic_rule")
    assert good.fallback_reason is None
    assert not [entry for entry in registry.journal if entry.get("event") == "capability.fallback"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
