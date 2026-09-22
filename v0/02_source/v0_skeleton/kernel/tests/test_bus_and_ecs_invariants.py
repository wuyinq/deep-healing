"""内核正确性支撑用例（设计 §6 R13~R16）：state 过 schema / canonical 单一来源 / bus 异常隔离 / ECS 排序。

每条判据都带**反向对照**（把被测行为退回错误形态 ⇒ 断言必须变红），确保不是零命中绿。

冻结运行形态：cd <ws>/02_source/v0_skeleton/kernel && \
  PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_bus_and_ecs_invariants.py -q -p no:cacheprovider
"""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import jsonschema
import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
WS_ROOT = KERNEL_ROOT.parents[2]
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"

from deephealing_kernel import snapshot as snapshot_mod  # noqa: E402
from deephealing_kernel import tick as tick_mod  # noqa: E402
from deephealing_kernel.bus import KernelBus  # noqa: E402
from deephealing_kernel.ecs import Entity, World  # noqa: E402
from deephealing_kernel.pack import load_pack  # noqa: E402


def _world_schema() -> dict:
    return json.loads((WS_ROOT / "02_source" / "world.schema.json").read_text(encoding="utf-8"))


def _kernel():
    return tick_mod.WorldKernel(pack=load_pack(PACK_DIR), seed=20260921, snapshot_every=20)


# --------------------------------------------------------------------------- R13
def test_state_passes_world_schema():
    """`snapshot.state` 必须过 `world.schema.json`，且**不含** `weather`（内容包元数据不进内核状态）。"""
    kernel = _kernel()
    kernel.run(5)
    state = kernel.world.to_state()

    assert set(state) == {"schema_version", "seed", "tick", "constants", "entities"}
    assert "weather" not in state
    jsonschema.validate(state, _world_schema())

    # entities 必须按 id 升序
    ids = [entity["id"] for entity in state["entities"]]
    assert ids == sorted(ids)
    assert len(ids) == 12

    # 内容包声明的 tags 必须**存活**到 state（不得被静默丢弃）
    by_id = {entity["id"]: entity for entity in state["entities"]}
    assert by_id["room-101"]["tags"] == ["floor-1", "residential"]  # 显式排序
    assert by_id["npc-001"]["tags"] == ["night-shift", "resident"]

    # 反向对照：把 weather 塞进 state ⇒ 校验必红（证明「不含 weather」这条断言有牙齿）
    tainted = dict(state)
    tainted["weather"] = {"condition": "clear", "temperature_c": 21.5, "time_of_day": "07:30"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(tainted, _world_schema())

    # 反向对照：entities 逆序 ⇒ 排序断言必红
    reversed_ids = [entity["id"] for entity in reversed(state["entities"])]
    assert reversed_ids != sorted(reversed_ids)


def test_weather_is_read_explicitly_and_dropped():
    """预审 U2：`weather` 必须被**显式读取**（pack 里断言存在）但**有意丢弃**（state 里没有）。"""
    pack = load_pack(PACK_DIR)
    assert "weather" in pack.world_seed
    kernel = tick_mod.WorldKernel(pack=pack, seed=20260921)
    state = kernel.world.to_state()
    assert "weather" not in state
    assert "weather" not in json.dumps(state, ensure_ascii=False)


# --------------------------------------------------------------------------- R14
def test_canonical_single_source(tmp_path):
    """内核用的 canonical 实现必须与 `tools/canonical_json.py` **同一文件**（禁止复制）。"""
    expected = (WS_ROOT / "02_source" / "v0_skeleton" / "tools" / "canonical_json.py").resolve()
    assert Path(inspect.getsourcefile(snapshot_mod.canonical_json)).resolve() == expected

    spec = importlib.util.spec_from_file_location("shared_canonical_reference", expected)
    assert spec is not None and spec.loader is not None
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)

    samples = [
        {"b": 1, "a": [3, 2, 1], "c": {"y": 1.23456789, "x": None}},
        {"unicode": "幸福小区", "n": 42},
        [{"z": 0.1, "a": 0.2}],
    ]
    for sample in samples:
        assert snapshot_mod.canonical_json(sample) == shared.canonical_json(sample)

    # 反向对照：复制一份并把 FLOAT_DIGITS 6 → 5 ⇒ 输出必须不同、来源路径必须不同
    forked_path = tmp_path / "canonical_json_fork.py"
    forked_path.write_text(
        expected.read_text(encoding="utf-8").replace("FLOAT_DIGITS = 6", "FLOAT_DIGITS = 5"),
        encoding="utf-8",
    )
    fork_spec = importlib.util.spec_from_file_location("forked_canonical", forked_path)
    assert fork_spec is not None and fork_spec.loader is not None
    forked = importlib.util.module_from_spec(fork_spec)
    fork_spec.loader.exec_module(forked)
    assert Path(inspect.getsourcefile(forked.canonical_json)).resolve() != expected
    assert forked.canonical_json({"a": 1.23456789}) != snapshot_mod.canonical_json({"a": 1.23456789})


# --------------------------------------------------------------------------- R15
def test_bus_subscriber_exception_isolated():
    """订阅者抛异常不得中断投递；必须记 metric；其余订阅者仍收到消息。"""
    bus = KernelBus()
    seen: list[int] = []

    def bad(_message):
        raise RuntimeError("subscriber exploded")

    def good(message):
        seen.append(message["n"])

    bus.subscribe("events", bad)
    bus.subscribe("events", good)
    bus.publish("events", {"n": 1})  # 必须不抛
    assert seen == [1]
    assert bus.metrics["subscriber_errors"] == 1
    assert bus.metrics["delivered"] == 1

    # 未知 topic 必须 fail-closed（不静默吞掉拼写错误）
    with pytest.raises(ValueError):
        bus.publish("topic-typo", {"n": 2})

    # 反向对照：未隔离的实现必须把异常抛出去（证明本判据有牙齿）
    class _NaiveBus:
        def __init__(self) -> None:
            self._subs: list = []

        def subscribe(self, fn) -> None:
            self._subs.append(fn)

        def publish(self, message) -> None:
            for fn in self._subs:
                fn(message)

    naive = _NaiveBus()
    naive.subscribe(bad)
    naive.subscribe(good)
    with pytest.raises(RuntimeError):
        naive.publish({"n": 3})


# --------------------------------------------------------------------------- R16
def test_ecs_query_sorted_by_id():
    """`query()` 必须按 entity id 升序返回（与插入顺序无关）。"""
    insertion_order = ["npc-005", "npc-003", "npc-001", "npc-004", "npc-002"]
    world = World()
    for entity_id in insertion_order:
        world.spawn(Entity(id=entity_id, kind="npc",
                           components={"transform": {"pos_mm": {"x": 0, "y": 0, "z": 0}}}))
    ids = [entity.id for entity in world.query(kind="npc")]
    assert ids == sorted(insertion_order)
    assert ids == ["npc-001", "npc-002", "npc-003", "npc-004", "npc-005"]

    # 反向对照：插入顺序与升序不同 ⇒ 若实现直接返回 dict 迭代顺序，本断言必红
    assert insertion_order != sorted(insertion_order)

    # 组件存在性过滤 + 未知组件必须被拒（新增组件需 ADR）
    assert [entity.id for entity in world.query(has=["transform"])] == ids
    with pytest.raises(ValueError):
        world.set_component("npc-001", "not_a_component", 1)
    with pytest.raises(KeyError):
        world.set_component("npc-999", "needs", {})
    with pytest.raises(ValueError):
        world.spawn(Entity(id="npc-001", kind="npc"))


def test_apply_delta_round_trip():
    """delta 应用必须落到 state（权威侧唯一写点）。"""
    world = World()
    world.spawn(Entity(id="prop-01", kind="prop", components={"transform": {"pos_mm": {"x": 1, "y": 2, "z": 3}}}))
    world.apply_delta([{"op": "set_component", "entity": "prop-01", "name": "tags", "value": ["b", "a"]}])
    state = world.to_state()
    entity = state["entities"][0]
    assert entity["tags"] == ["a", "b"]  # tags 显式排序
    with pytest.raises(ValueError):
        world.apply_delta([{"op": "not-a-delta-op"}])
