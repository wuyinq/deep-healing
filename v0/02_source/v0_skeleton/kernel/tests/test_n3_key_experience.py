"""N3（关键经历自然产生）· W1/W2/W3 的判据（新增用例；既有用例与期望值一字未动）。

依据：`01_architecture_design.md` §4-W1/W2/W3、§6（AC-1..AC-5 / C1~C4 / C6）、§8（R-14/R-15/R-16）。

判据（逐条）：
  ① 新评价规则是**纯函数**（同输入同输出）、输出严格过 `emotion.appraise` 的 `output_schema`；
  ② 规则**只由经历要素决定**：同摘要不同 `tick` ⇒ 同输出（不读 tick）；摘要里没有经历 token ⇒ 基线档；
  ③ 闸门逐字未改（`deficit < emotion_pressure_threshold` + 默认 `URGENCY_THRESHOLD = 0.6`），
     且压力到位时 `emotion.appraise` 调用数 > 0、`fallback_reason is None`、降级总数 == 0；
  ④ 无 registry ⇒ **0 调用、零副作用**（`emotion_results == {}`、`emotion_fallbacks_log == []`）；
  ⑤ **声明默认关**：包未声明 `pressure_window` ⇒ 新代码路径完全惰性（事件流与「机制强制关闭」逐字节一致）；
  ⑥ **声明是唯一变量（R-14 非零命中证据）**：带声明 / 不带声明的两个包副本同 seed ⇒ 窗口起点之前逐字节一致、
     首次分叉**恰好**在窗口起点；
  ⑦ **负例（稀释）**：把 `MEMORY_SIGNAL_MIN_IMPORTANCE` 降到 0 ⇒ 分布分离判据必须判红；
  ⑧ **负例（归因）**：评价规则退回「不识别经历」的档（旧 `emotion_appraise_rule`）⇒ 越线条数回到 0；
  ⑨ **fail-closed**：声明非法（need 越域 / floor 越界 / 窗口倒挂 / 未知键 / 缺键 / 非对象 / 缺事件 id）⇒ 抛 ValueError。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import jsonschema
import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = KERNEL_ROOT.parents[1]
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu-xuqin"
CAPS_DIR = KERNEL_ROOT.parent / "capabilities"
TOOLS_DIR = KERNEL_ROOT.parent / "tools"
SEED = 20260921
WINDOW = (895, 905)
sys.path.insert(0, str(KERNEL_ROOT))
sys.path.insert(0, str(TOOLS_DIR))

from deephealing_kernel.events import EventLog                              # noqa: E402
from deephealing_kernel.memory.store import MemoryStore                     # noqa: E402
from deephealing_kernel.pack import load_pack                               # noqa: E402
from deephealing_kernel.providers import deterministic_rule as rule_mod     # noqa: E402
from deephealing_kernel.registry import CapabilityRegistry                  # noqa: E402
from deephealing_kernel.rules import decision as decision_mod               # noqa: E402
from deephealing_kernel.tick import WorldKernel                             # noqa: E402
from deephealing_kernel.tick import collect_experience_pressures            # noqa: E402
from deephealing_kernel.tick import EXPERIENCE_PRESSURE_KEY                 # noqa: E402

import pack_sign                                                            # noqa: E402


# ---------------------------------------------------------------------- 夹具
def _copy_pack(tmp_path: Path, *, declare: bool) -> Path:
    """把 xuqin 包复制到临时目录；`declare=False` 时**摘掉** `pressure_window` 并重签 pack.sig。"""
    target = tmp_path / ("declared" if declare else "undeclared") / PACK_DIR.name
    shutil.copytree(PACK_DIR, target)
    if not declare:
        path = target / "npcs" / "npc-006.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in document["key_events"]:
            entry.pop(EXPERIENCE_PRESSURE_KEY, None)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pack_sign.write_signature(target, pack_sign.build_signature(target))
    return target


def _registry(cassette_root: Path, *, replay_mode: bool = False) -> CapabilityRegistry:
    from deephealing_kernel.providers.cassette import CassetteReplayProvider, CassetteStore
    from deephealing_kernel.providers.local_model import LocalModelProvider
    from deephealing_kernel.providers.remote_api import RemoteApiProvider

    store = CassetteStore(cassette_root)
    registry = CapabilityRegistry(CAPS_DIR, CAPS_DIR / "pins.json", cassette_store=store,
                                  replay_mode=replay_mode)
    registry.register_adapter("remote_api", RemoteApiProvider())
    registry.register_adapter("local_model", LocalModelProvider())
    registry.register_adapter("deterministic_rule", rule_mod.DeterministicRuleProvider())
    registry.register_adapter("cassette_replay", CassetteReplayProvider(store))
    registry.discover()
    return registry


def _run(pack_dir: Path, out_dir: Path, ticks: int, *, declared_kernel: bool = True,
         on_kernel=None):
    """跑一段自然运行（可选接线），返回 `(kernel, events_path)`。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    pack = load_pack(pack_dir)
    events_path = out_dir / "events.jsonl"
    extra: dict = {}
    registry = None
    if declared_kernel:
        from deephealing_kernel.budget import BudgetLedger
        registry = _registry(out_dir / "cassettes")
        store = MemoryStore(out_dir / "kernel_memory.sqlite", write_enabled=True)
        store.init_schema()
        extra["capability_registry"] = registry
        extra["budget_ledger"] = BudgetLedger(day_ticks=1440, per_tick_calls=7,
                                              per_npc_daily_tokens=20000)
        extra["memory_store"] = store
    kernel = WorldKernel(pack=pack, seed=SEED, log=EventLog(events_path), snapshot_every=0, **extra)
    if on_kernel is not None:
        on_kernel(kernel)
    kernel.run(ticks)
    return kernel, events_path, registry


def _episodic_importances(events_path: Path, npc: str = "npc-006") -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    with events_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            payload = event.get("payload") or {}
            if (event.get("type") == "memory.written" and event.get("actor") == npc
                    and payload.get("layer") == "episodic"
                    and isinstance(payload.get("importance"), (int, float))):
                out.append((int(event["tick"]), float(payload["importance"])))
    return out


def _separation_holds(values: list[float], threshold: float) -> bool:
    """C1：`max(未越线) < threshold <= min(越线)`；**无未越线样本 ⇒ 判红**（稀释检测的牙）。"""
    crossing = [value for value in values if value >= threshold]
    below = [value for value in values if value < threshold]
    if not below or not crossing:
        return False
    return max(below) < threshold <= min(crossing)


# ---------------------------------------------------------------------- ① / ② 规则本身
def test_experience_rule_is_pure_and_passes_output_schema():
    payload = {
        "npc_id": "npc-006", "tick": 900,
        "event_summary": ("tick=900 action=flee need=safety branch=flee "
                          "experience=xuqin-pushes-hanfei-away target_home=1 trauma=4 "
                          "relation=- observable=先推开对端并让其下楼，随后改口一起走"),
        "current_emotion": {"valence": -0.1, "arousal": 0.5},
    }
    first = rule_mod.experience_appraise_rule(payload)
    second = rule_mod.experience_appraise_rule(copy_of(payload))
    assert first == second, "纯函数：同输入必须逐位同输出"
    assert first["importance"] == pytest.approx(0.80, abs=1e-9)

    capability = json.loads((CAPS_DIR / "emotion.appraise@1.0.0.capability.json").read_text("utf-8"))
    jsonschema.validate(first, capability["output_schema"])
    assert first["mood_label"] in capability["output_schema"]["properties"]["mood_label"]["enum"]


def copy_of(value: dict) -> dict:
    return json.loads(json.dumps(value))


def test_experience_rule_ignores_tick_and_deficit():
    """**不读 tick、不读缺口**：同摘要换 `tick` ⇒ 输出逐位相同；摘要无经历 token ⇒ 基线档 0.20。"""
    base = {"npc_id": "npc-006", "event_summary": "tick=900 action=flee need=safety branch=flee",
            "current_emotion": {"valence": 0.0, "arousal": 0.0}}
    at_900 = rule_mod.experience_appraise_rule({**base, "tick": 900})
    at_99999 = rule_mod.experience_appraise_rule({**base, "tick": 99999})
    assert at_900 == at_99999
    assert at_900["importance"] == pytest.approx(0.20, abs=1e-9), "无经历要素 ⇒ 基线档，不稀释"

    # 逐项权重可复算（事件显著性 / 目标相关性 / 创伤相关性 / 关系代价）
    def importance(summary: str) -> float:
        return rule_mod.experience_appraise_rule(
            {"npc_id": "npc-006", "tick": 1, "event_summary": summary,
             "current_emotion": {"valence": 0.0, "arousal": 0.0}})["importance"]

    assert importance("t x experience=e1 target_home=0 trauma=0 relation=-") == pytest.approx(0.50, abs=1e-9)
    assert importance("t x experience=e1 target_home=1 trauma=4 relation=-") == pytest.approx(0.80, abs=1e-9)
    assert importance("t x experience=e1 target_home=1 trauma=4 relation=npc-007:0.05") == pytest.approx(0.90, abs=1e-9)
    assert importance("t x experience=e1 target_home=0 trauma=2 relation=-") == pytest.approx(0.50, abs=1e-9)


def test_rule_registration_and_capability_wiring():
    assert "experience_appraise_rule" in rule_mod.RULE_IMPLS
    assert rule_mod.RULE_IMPLS["emotion_appraise_rule"] is rule_mod.emotion_appraise_rule, "既有规则不动"
    raw = (CAPS_DIR / "emotion.appraise@1.0.0.capability.json").read_text("utf-8")
    assert raw.count("providers.deterministic_rule:experience_appraise_rule") == 5, "主 impl + 4 条 fallback 同步"
    assert '"priority": 5' in raw, "检测到 priority 路由（40 → 5）"
    capability = json.loads(raw)
    classes = sorted(provider["class"] for provider in capability["providers"])
    assert classes == ["cassette_replay", "deterministic_rule", "local_model", "remote_api"]


# ---------------------------------------------------------------------- ③ 闸门未改 + 调用数 > 0
def test_gate_is_verbatim_and_calls_happen_when_pressure_is_declared(tmp_path):
    source = (KERNEL_ROOT / "deephealing_kernel" / "tick.py").read_text("utf-8")
    assert "if deficit < self.emotion_pressure_threshold:" in source
    assert "emotion_pressure_threshold: float = URGENCY_THRESHOLD" in source
    assert decision_mod.URGENCY_THRESHOLD == 0.6
    assert decision_mod.MEMORY_SIGNAL_MIN_IMPORTANCE == 0.5
    assert "if importance < MEMORY_SIGNAL_MIN_IMPORTANCE:" in (
        KERNEL_ROOT / "deephealing_kernel" / "rules" / "decision.py").read_text("utf-8")

    kernel, events_path, registry = _run(_copy_pack(tmp_path, declare=True), tmp_path / "out", 1200)
    calls = [call for call in registry.calls if call.get("slot") == "emotion.appraise"]
    assert len(calls) == WINDOW[1] - WINDOW[0] + 1, "闸门只在窗口内自然打开"
    assert all(call.get("fallback_reason") is None for call in calls), "达标运行不得走降级"
    assert all(call.get("provider") == "deterministic_rule" for call in calls)
    assert kernel.emotion_fallbacks_log == [], "降级读数必须为空"
    crossers = [tick for tick, value in _episodic_importances(events_path) if value >= 0.5]
    assert crossers == list(range(WINDOW[0], WINDOW[1] + 1)), "越线必须逐字落在窗口内"
    assert kernel.experience_pressures and kernel.experience_pressures[0]["npc_id"] == "npc-006"


# ---------------------------------------------------------------------- ④ 无 registry ⇒ 零副作用
def test_without_registry_no_calls_and_no_side_effects(tmp_path):
    kernel, events_path, _ = _run(_copy_pack(tmp_path, declare=True), tmp_path / "out", 1200,
                                  declared_kernel=False)
    assert kernel.emotion_results == {}
    assert kernel.emotion_fallbacks == [] and kernel.emotion_fallbacks_log == []
    types = set()
    with events_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                types.add(json.loads(line)["type"])
    assert "memory.written" not in types and "npc.action" in types


# ---------------------------------------------------------------------- ⑤ 声明默认关 ⇒ 惰性
def test_undeclared_pack_leaves_the_new_paths_inert(tmp_path, monkeypatch):
    pack_dir = _copy_pack(tmp_path, declare=False)
    _, plain_events, _ = _run(pack_dir, tmp_path / "plain", 300, declared_kernel=False)

    monkeypatch.setattr(WorldKernel, "_apply_experience_pressures", lambda self, tick: None, raising=True)
    monkeypatch.setattr(WorldKernel, "_experience_tokens",
                        lambda self, npc_id, tick, target_entity: "", raising=True)
    _, inert_events, _ = _run(pack_dir, tmp_path / "inert", 300, declared_kernel=False)

    assert plain_events.read_bytes() == inert_events.read_bytes(), "未声明 ⇒ 新代码路径不得改变任何字节"


# ---------------------------------------------------------------------- ⑥ 声明是唯一变量
def test_declaration_is_the_only_variable(tmp_path):
    declared = _copy_pack(tmp_path, declare=True)
    undeclared = _copy_pack(tmp_path, declare=False)
    _kernel_a, events_a, _ = _run(declared, tmp_path / "a", 1000, declared_kernel=False)
    _kernel_b, events_b, _ = _run(undeclared, tmp_path / "b", 1000, declared_kernel=False)

    def records(path: Path) -> list[dict]:
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    rows_a = [(r["tick"], r["type"], r["actor"], json.dumps(r["payload"], sort_keys=True))
              for r in records(events_a)]
    rows_b = [(r["tick"], r["type"], r["actor"], json.dumps(r["payload"], sort_keys=True))
              for r in records(events_b)]
    assert len(rows_a) == len(rows_b)
    first_diff = next(index for index, (x, y) in enumerate(zip(rows_a, rows_b)) if x != y)
    assert all(x == y for x, y in zip(rows_a[:first_diff], rows_b[:first_diff])), "窗口之前必须逐字节一致"
    # 首次分叉必须**恰好**落在窗口起点（tick 895 的 `npc.decision`）
    assert rows_a[first_diff][0] == WINDOW[0], f"首次分叉 tick={rows_a[first_diff][0]} != {WINDOW[0]}"
    assert rows_a[first_diff][1] == "npc.decision"


# ---------------------------------------------------------------------- ⑦ 负例：稀释
def test_dilution_negative_detects_threshold_removal(tmp_path):
    _kernel, events_path, _ = _run(_copy_pack(tmp_path, declare=True), tmp_path / "out", 1200)
    values = [value for _tick, value in _episodic_importances(events_path)]
    assert _separation_holds(values, decision_mod.MEMORY_SIGNAL_MIN_IMPORTANCE) is True
    # 把阈值降到 0（**只在进程内**改，不写盘）⇒ 分离判据必须判红（没有未越线样本 = 稀释）
    lowered = 0.0
    assert _separation_holds(values, lowered) is False, "阈值降到 0 必须判红"
    # 阈值是 0.5 这件事必须由源码逐字担保（不是靠内存里的值）
    assert "MEMORY_SIGNAL_MIN_IMPORTANCE = 0.5" in (
        KERNEL_ROOT / "deephealing_kernel" / "rules" / "decision.py").read_text("utf-8")


# ---------------------------------------------------------------------- ⑧ 负例：归因
def test_attribution_negative_constant_appraisal_loses_the_crossing(tmp_path, monkeypatch):
    """**C2b（设计原文口径）**：把 appraisal 输出**强制为常量**（不识别经历）⇒ 越线条数恰好 0。

    常量取新规则的**基线档 0.20**（=「没有任何经历要素被识别」）⇒ 混合项 = `0.5*0.6 + 0.5*0.20 = 0.40 < 0.5`
    ⇒ 越线消失。这直接证明：**越线依赖评价层真的识别出经历**，不是靠缺口自己越线。
    """
    def constant_appraisal(self, capability, payload, *, timeout_ms):
        return {"valence": -0.06, "arousal": 0.2, "mood_label": "numb", "importance": 0.20}

    monkeypatch.setattr(rule_mod.DeterministicRuleProvider, "invoke", constant_appraisal, raising=True)
    kernel, events_path, _ = _run(_copy_pack(tmp_path, declare=True), tmp_path / "out", 1200)
    crossers = [tick for tick, value in _episodic_importances(events_path) if value >= 0.5]
    assert crossers == [], f"归因负例必须让越线条数回到 0，实测 {crossers}"
    assert len(kernel.emotion_fallbacks_log) == 0


def test_emotion_results_emptied_arm_documents_the_structural_limit(tmp_path, monkeypatch):
    """**已登记的「诚实边界」**（不是判据通过项，是**事实读数**）：

    设计 §6-C2 的另一半写法是「**或 `emotion_results` 置空** ⇒ 越线条数 = 0」。这条在本机制下**结构上做不到**：
    闸门阈值（`tick.py` 默认 `URGENCY_THRESHOLD = 0.6`）**高于**记忆阈值（`MEMORY_SIGNAL_MIN_IMPORTANCE = 0.5`）
    ⇒ 任何能触发评价层的 tick 必有 `dominant_deficit >= 0.6`；而 `_write_memory` 在**无**情绪结果时
    `importance := clamp(deficit) = 0.6 >= 0.5` ⇒ **缺口单独就越线**。
    两个阈值都在冻结面（逐字未动）⇒ 本项只能如实记为**结构不可达**，不能靠改机制凑绿。
    """
    original = WorldKernel._appraise_emotions

    def emptied(self, intents, tick):
        original(self, intents, tick)      # 评价层**仍然被调用**（闸门照开）
        self.emotion_results = {}          # 但结果置空 ⇒ 混合项不发生

    monkeypatch.setattr(WorldKernel, "_appraise_emotions", emptied, raising=True)
    _kernel, events_path, _ = _run(_copy_pack(tmp_path, declare=True), tmp_path / "out", 1200)
    crossers = [tick for tick, value in _episodic_importances(events_path) if value >= 0.5]
    assert crossers == list(range(WINDOW[0], WINDOW[1] + 1)), "缺口单独即可越线（结构性事实）"


# ---------------------------------------------------------------------- ⑨ fail-closed
@pytest.mark.parametrize("mutate", [
    lambda entry: entry.update({EXPERIENCE_PRESSURE_KEY: {"need": "hunger", "start_tick": 1, "end_tick": 2, "floor": 0.9}}),
    lambda entry: entry.update({EXPERIENCE_PRESSURE_KEY: {"need": "safety", "start_tick": 1, "end_tick": 2, "floor": 1.5}}),
    lambda entry: entry.update({EXPERIENCE_PRESSURE_KEY: {"need": "safety", "start_tick": 9, "end_tick": 2, "floor": 0.9}}),
    lambda entry: entry.update({EXPERIENCE_PRESSURE_KEY: {"need": "safety", "start_tick": 1.5, "end_tick": 2, "floor": 0.9}}),
    lambda entry: entry.update({EXPERIENCE_PRESSURE_KEY: {"need": "safety", "start_tick": 1, "end_tick": 2, "floor": 0.9, "surprise": 1}}),
    lambda entry: entry.update({EXPERIENCE_PRESSURE_KEY: {"need": "safety", "floor": 0.9}}),
    lambda entry: entry.update({EXPERIENCE_PRESSURE_KEY: "safety"}),
    lambda entry: entry.update({EXPERIENCE_PRESSURE_KEY: {"need": "safety", "start_tick": -1, "end_tick": 2, "floor": 0.9}}),
])
def test_invalid_declaration_fails_closed(tmp_path, mutate):
    pack_dir = _copy_pack(tmp_path, declare=True)
    path = pack_dir / "npcs" / "npc-006.json"
    document = json.loads(path.read_text("utf-8"))
    mutate(document["key_events"][0])
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pack_sign.write_signature(pack_dir, pack_sign.build_signature(pack_dir))
    with pytest.raises(ValueError):
        collect_experience_pressures(load_pack(pack_dir))


def test_declaration_absent_is_no_op_and_carrier_is_loaded(tmp_path):
    """默认关：未声明的包 ⇒ 空声明；同时证明载体**真的被加载**（非零命中，R-14）。"""
    kernel_a, _e, _r = _run(_copy_pack(tmp_path, declare=True), tmp_path / "a", 5, declared_kernel=False)
    kernel_b, _e2, _r2 = _run(_copy_pack(tmp_path, declare=False), tmp_path / "b", 5, declared_kernel=False)
    assert kernel_a.experience_pressures, "声明必须被读到（载体已加载）"
    assert kernel_b.experience_pressures == [], "未声明 ⇒ 空（默认关）"
    assert kernel_b.pack is not None and kernel_b.pack.npcs, "载体文档本身仍在 pack 内被加载"
