"""M5.2 r1 · AC-3 事件→记忆→决策链 + W4 关系（友善度）运行时演进的判据。

依据：`01_architecture_design.md` §5.2 / §5.3 / §5.4 + **§11.1 C-1 / C-2**（Raven 预审处置，
硬性，覆盖 §5.2/§5.4 的字面 payload 与值形状）+ §11.2 M-2 / M-13 / M-15。

判据（逐条）：
  ① 真实事件流出现 `memory.written`，**每条**都过 `events.schema.json` 的 `then` 子句（C-2）；
  ② `layer` 走 **store 词表 → 事件词表**映射（`working|episodes|facts` → `working|episodic|semantic`），
     **禁止**把 store 词表直接写进事件；
  ③ `ref` **恒为 string**；`write_enabled=False` ⇒ 不写库但仍 emit，`ref == "none"`；
  ④ **`memory_store=None` ⇒ 与「记忆链未接线」的对照臂逐字节一致**（单变量对拍，见下）；
  ⑤ `memory_view` **只读**：`decide` 前后规范化哈希不变；改它不影响 store 读回值；
     `memory_view.relations` 形状 = `{npc_id: float}`（C-1 / M-13③）；
  ⑥ **关系演进**：`relation.changed` 事件带 6 个冻结字段、过 schema、同 seed 逐位一致（W4）；
  ⑦ **AC-3.4**：`utility_ranking` 可由 `memory_influence.by_action` **独立复算**（M-15：主判据落在
     `npc.action` / `target_entity` 序列的差异上，`memory_influence` 只作辅助字段）。

**单变量对拍（④）的做法**：把交付树复制到临时目录，只在副本里做**两处注入**把「记忆链接线」
退回未接线形态（`memory_view=None` + 跳过写入），再与交付树跑同 seed 同 tick 数，
**事件行逐字节 diff 必须为 0**。这样「记忆链」是唯一被改变的变量（C1/C2/C3 与关系演进两臂都有）。
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = KERNEL_ROOT.parents[1]                     # 02_source/
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SCHEMA_PATH = SOURCE_ROOT / "events.schema.json"
SEED = 20260921
sys.path.insert(0, str(KERNEL_ROOT))

from deephealing_kernel import snapshot as snapshot_mod  # noqa: E402
from deephealing_kernel.events import EventLog  # noqa: E402
from deephealing_kernel.memory.store import EVENT_LAYER_NAMES, MemoryStore  # noqa: E402
from deephealing_kernel.pack import load_pack  # noqa: E402
from deephealing_kernel.rules import decision as decision_mod  # noqa: E402
from deephealing_kernel.rules import utility as utility_mod  # noqa: E402
from deephealing_kernel.tick import WorldKernel  # noqa: E402

MEMORY_REQUIRED = ("npc_id", "layer", "ref")
RELATION_REQUIRED = ("npc_id", "peer_npc_id", "from", "to", "tick", "source_event")
LAYER_ENUM = ("working", "episodic", "semantic")

RUNNER = textwrap.dedent(
    '''
    import json, sys
    from pathlib import Path
    kernel_root, pack_dir, out_path, ticks = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    sys.path.insert(0, kernel_root)
    from deephealing_kernel.events import EventLog
    from deephealing_kernel.pack import load_pack
    from deephealing_kernel.tick import WorldKernel
    kernel = WorldKernel(pack=load_pack(Path(pack_dir)), seed=20260921,
                         log=EventLog(Path(out_path)), snapshot_every=0, checkpoint_dir=None)
    kernel.run(ticks)
    print(json.dumps({"state_hash": kernel.state_hash()}))
    '''
)


def _run(tmp_path: Path, *, ticks: int = 30, name: str = "a", store=None):
    pack = load_pack(PACK_DIR)
    log = EventLog(tmp_path / name / "events.jsonl")
    extra = {"memory_store": store} if store is not None else {}
    kernel = WorldKernel(pack=pack, seed=SEED, log=log, snapshot_every=0, checkpoint_dir=None, **extra)
    kernel.run(ticks)
    return kernel, log


def _store(tmp_path: Path, name: str = "m.sqlite", *, enabled: bool = True) -> MemoryStore:
    store = MemoryStore(tmp_path / name, write_enabled=enabled)
    store.init_schema()
    return store


# ------------------------------------------------------------------ ① ② ③ 记忆写入与 payload
def test_memory_written_events_carry_frozen_payload(tmp_path):
    """① `memory.written` 真的出现在事件流里，且带 3 个必核字段 + 可选 `kind`。"""
    store = _store(tmp_path)
    kernel, log = _run(tmp_path, ticks=12, name="mw", store=store)
    events = [event for event in log.read_all() if event.type == "memory.written"]
    npc_count = len(load_pack(PACK_DIR).npcs)
    assert len(events) == 12 * npc_count * 2, (
        f"期望 12 tick x {npc_count} NPC x 2 层 = {12 * npc_count * 2} 条，实测 {len(events)}"
    )
    for event in events:
        for field in MEMORY_REQUIRED:
            assert field in event.payload, f"memory.written 缺必核字段 {field}"
        assert isinstance(event.payload["ref"], str), "C-2：ref 恒为 string"
        assert event.payload["layer"] in LAYER_ENUM, (
            f"C-2：layer={event.payload['layer']!r} 不在事件词表 {LAYER_ENUM}（store 词表禁止入事件）"
        )
    # 写入真的落库（不是只 emit）
    assert store.layer_counts("npc-001")["episodes"]["total"] == 12
    assert store.write_count > 0
    assert kernel.ticks_done == 12


def test_layer_vocabulary_mapping_is_pinned():
    """② store 词表 → 事件词表的映射**钉死**（防「直接写 store 词表」回归）。"""
    assert EVENT_LAYER_NAMES == {"working": "working", "episodes": "episodic", "facts": "semantic"}
    assert set(EVENT_LAYER_NAMES.values()) == set(LAYER_ENUM)
    assert "episodes" not in EVENT_LAYER_NAMES.values()
    assert "facts" not in EVENT_LAYER_NAMES.values()


def test_write_disabled_emits_but_writes_nothing(tmp_path):
    """③ `write_enabled=False` ⇒ 不写库但**仍 emit**，且 `ref == "none"`（不得用 null）。"""
    store = _store(tmp_path, "off.sqlite", enabled=False)
    _, log = _run(tmp_path, ticks=8, name="off", store=store)
    events = [event for event in log.read_all() if event.type == "memory.written"]
    assert events, "write_enabled=False 仍必须 emit（观测要能分辨「想写」与「写了」）"
    assert {event.payload["ref"] for event in events} == {"none"}
    assert store.write_count == 0
    assert store.layer_counts("npc-001")["episodes"]["total"] == 0


def test_every_memory_written_payload_passes_frozen_schema(tmp_path):
    """① 每一条 `memory.written` 必须过 `events.schema.json` 的 `then` 子句（形态照抄
    `test_autonomous_decision.py::test_decision_event_payload_satisfies_frozen_schema`）。"""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    store = _store(tmp_path)
    _, log = _run(tmp_path, ticks=6, name="schema", store=store)
    events = [event for event in log.read_all()
              if event.type in ("memory.written", "relation.changed", "npc.decision")]
    assert [event for event in events if event.type == "memory.written"]
    for event in events:
        jsonschema.validate(event.to_dict(), schema)


def test_schema_criterion_goes_red_when_ref_is_dropped(tmp_path):
    """① 的**负对照**：把 `ref` 从 episodic payload 里去掉 ⇒ 上面那条判据**必须变红**。

    注入在**隔离副本**上做（交付树零改动），且注入后**回读复核**锚点真的落地。
    """
    copy_root = tmp_path / "copy" / "02_source"
    shutil.copytree(SOURCE_ROOT, copy_root)
    target = copy_root / "v0_skeleton/kernel/deephealing_kernel/tick.py"
    source = target.read_text(encoding="utf-8")
    anchor = '                "ref": str(episode_ref) if written else "none",'
    assert source.count(anchor) == 1, "注入锚点失效：episodic payload 的 ref 行形态变了"
    target.write_text(source.replace(anchor, '                "ref_probe_removed": "x",', 1),
                      encoding="utf-8")
    assert 'ref_probe_removed' in target.read_text(encoding="utf-8"), "注入未落地"

    (copy_root / "runner_probe.py").write_text(RUNNER, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest",
         "v0_skeleton/kernel/tests/test_m52_memory_chain.py::"
         "test_every_memory_written_payload_passes_frozen_schema",
         "-q", "-p", "no:cacheprovider"],
        cwd=copy_root, capture_output=True, text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    assert completed.returncode != 0, (
        "去掉 ref 后 schema 判据仍为绿 ⇒ 该判据是零命中绿\n" + completed.stdout[-2000:]
    )
    assert "test_every_memory_written_payload_passes_frozen_schema" in (
        completed.stdout + completed.stderr
    )


# ------------------------------------------------------------------ ④ 单变量对拍
def _write_runner(path: Path) -> None:
    path.write_text(RUNNER, encoding="utf-8")


def test_memory_store_none_is_bit_identical_to_unwired_arm(tmp_path):
    """④ `memory_store=None` ⇒ 事件流与「记忆链未接线」对照臂**逐字节一致**。

    对照臂 = 交付树的副本 + **两处注入**（`memory_view=None`、跳过写入）⇒ 唯一变量 = 记忆链接线。
    """
    wired = tmp_path / "wired.jsonl"
    _write_runner(tmp_path / "runner.py")
    first = subprocess.run(
        [sys.executable, str(tmp_path / "runner.py"), str(KERNEL_ROOT), str(PACK_DIR), str(wired), "40"],
        capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    assert first.returncode == 0, first.stdout + first.stderr

    copy_root = tmp_path / "copy" / "02_source"
    shutil.copytree(SOURCE_ROOT, copy_root)
    target = copy_root / "v0_skeleton/kernel/deephealing_kernel/tick.py"
    source = target.read_text(encoding="utf-8")
    edits = [
        ("memory_view=self._build_memory_view())", "memory_view=None)"),
        ("            if self.memory_store is not None:", "            if False:  # probe: memory wiring removed"),
    ]
    for anchor, replacement in edits:
        assert source.count(anchor) == 1, f"注入锚点失效：{anchor!r}"
        source = source.replace(anchor, replacement, 1)
    target.write_text(source, encoding="utf-8")
    reread = target.read_text(encoding="utf-8")
    assert "memory_view=self._build_memory_view()" not in reread and "if False:  # probe" in reread, \
        "注入未落地"

    unwired = tmp_path / "unwired.jsonl"
    second = subprocess.run(
        [sys.executable, str(tmp_path / "runner.py"),
         str(copy_root / "v0_skeleton/kernel"), str(copy_root / "v0_skeleton/districts/xingfu-xiaoqu"),
         str(unwired), "40"],
        capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    assert second.returncode == 0, second.stdout + second.stderr

    left = wired.read_text(encoding="utf-8").splitlines()
    right = unwired.read_text(encoding="utf-8").splitlines()
    assert len(left) == len(right), f"事件条数不同：{len(left)} vs {len(right)}"
    for index, (a, b) in enumerate(zip(left, right)):
        assert a == b, f"第 {index} 行事件逐字节不同（memory_store=None 应零副作用）:\n{a}\n{b}"
    assert "memory.written" not in wired.read_text(encoding="utf-8")


# ------------------------------------------------------------------ ⑤ memory_view 只读性
def test_memory_view_is_read_only_and_decoupled_from_store(tmp_path):
    """⑤ `memory_view` 只读：`decide` 前后规范化哈希相同；改它不影响 store 读回值；
    `relations` 形状 = `{npc_id: float}`（C-1 / M-13）。"""
    store = _store(tmp_path, "view.sqlite")
    kernel, _ = _run(tmp_path, ticks=10, name="view", store=store)
    view = kernel._build_memory_view()
    assert view is not None
    for npc_id, entry in view.items():
        assert set(entry) == {"episodes", "facts", "relations"}
        for peer, value in entry["relations"].items():
            assert isinstance(peer, str) and isinstance(value, float) and not isinstance(value, bool), (
                f"C-1：memory_view.relations 形状必须是 {{npc_id: float}}，实测 {peer!r}: {value!r}"
            )

    before_hash = snapshot_mod.hash_object(view)
    before_episodes = store.fetch_episodes("npc-001")
    intents = decision_mod.decide(kernel.world, kernel.rng, 11, None,
                                  pack_profiles=kernel.pack_profiles, memory_view=view)
    assert intents
    assert snapshot_mod.hash_object(view) == before_hash, "decide 改写了只读 memory_view"
    assert store.fetch_episodes("npc-001") == before_episodes, "memory_view 与 store 未解耦"

    # 反向对照：改副本**不影响** store 读回值（解耦），但会被哈希检出（证明哈希判据有判别力）
    mutated = copy.deepcopy(view)
    mutated["npc-001"]["episodes"].append({"ref": 999, "tick": 999, "kind": "flee", "importance": 1.0})
    assert snapshot_mod.hash_object(mutated) != before_hash
    assert store.fetch_episodes("npc-001") == before_episodes


# ------------------------------------------------------------------ ⑥ 关系演进
def test_relation_changes_are_emitted_with_frozen_payload(tmp_path):
    """⑥ 关系变更 emit `relation.changed`（6 个冻结字段）+ 值形状仍是数值标量（C-1）。"""
    kernel, log = _run(tmp_path, ticks=30, name="rel")
    events = [event for event in log.read_all() if event.type == "relation.changed"]
    assert events, "30 tick 内必须出现关系变更（`talk` 会推动友善度）"
    for event in events:
        for field in RELATION_REQUIRED:
            assert field in event.payload, f"relation.changed 缺冻结字段 {field}"
        assert event.payload["from"] != event.payload["to"]
    state = kernel.world.to_state()
    for entity in state["entities"]:
        relations = entity.get("relations")
        if relations is None:
            continue
        assert isinstance(relations, dict)
        for peer, value in relations.items():
            assert isinstance(value, (int, float)) and not isinstance(value, bool), (
                f"C-1：relations 值必须是数值标量（world.schema.json 冻结），实测 {peer}: {value!r}"
            )


def test_relation_trajectory_is_deterministic(tmp_path):
    """⑥ 同 seed 两次运行 relations 轨迹**逐位一致**（确定性）。"""
    first, _ = _run(tmp_path, ticks=25, name="det-a")
    second, _ = _run(tmp_path, ticks=25, name="det-b")
    assert first.state_hash() == second.state_hash()
    left = [(entity.id, entity.components.get("relations")) for entity in first.world.query(kind="npc")]
    right = [(entity.id, entity.components.get("relations")) for entity in second.world.query(kind="npc")]
    assert left == right
    # 反向对照：轨迹真的动过（否则「逐位一致」是恒真式）
    initial = sorted((doc["id"], doc.get("relations"))
                     for doc in load_pack(PACK_DIR).world_seed["entities"]
                     if doc.get("kind") == "npc")
    assert left != initial


# ------------------------------------------------------------------ ⑦ AC-3.4 复算
def test_utility_ranking_is_independently_recomputable_from_memory_influence(tmp_path):
    """⑦ 决策 payload 的 `utility_ranking` 可由 `memory_influence.by_action` **独立复算**。

    复算口径：`utility.score_actions` 的原始分数 + `by_action[action]`，再按同一 tie-break 排序。
    这是 M-15 要求的「不得自报」：判据用**另一条独立路径**重算，而不是读被测对象给的排序。
    """
    store = _store(tmp_path, "recompute.sqlite")
    pack = load_pack(PACK_DIR)
    log = EventLog(tmp_path / "recompute" / "events.jsonl")
    kernel = WorldKernel(pack=pack, seed=SEED, log=log, snapshot_every=0, checkpoint_dir=None,
                         memory_store=store)
    # 逐 tick 记录**决策当时看到的需求状态**（decide 读的是上一步执行阶段写下的 needs）
    needs_by_tick: dict[int, dict] = {}
    for tick in range(1, 7):
        needs_by_tick[tick] = {entity.id: copy.deepcopy(entity.components.get("needs") or {})
                               for entity in kernel.world.query(kind="npc")}
        kernel.step()

    decisions = [event for event in log.read_all() if event.type == "npc.decision"]
    assert decisions
    checked = 0
    for event in decisions:
        payload = event.payload
        influence = payload.get("memory_influence")
        assert influence is not None and influence["read"] is True, "记忆链已接线 ⇒ read 必须为 True"
        needs = needs_by_tick[int(event.tick)][payload["npc_id"]]
        weights = (kernel.pack_profiles.get(payload["npc_id"]) or {}).get("need_weights") or {}
        candidates = (decision_mod.candidate_actions(payload["schedule_state"])
                      + decision_mod.branch_candidates(payload["bt_branch"], payload["schedule_state"]))
        base = utility_mod.score_actions(needs, weights, {"schedule_state": payload["schedule_state"]},
                                         candidates)
        adjusted = [
            {**item, "score": round(item["score"] + influence["by_action"].get(item["action"], 0.0), 6)}
            for item in base
        ]
        adjusted.sort(key=lambda item: (-item["score"], item["need"], item["target_entity"] or ""))
        recomputed = [{"action": item["action"], "need": item["need"], "score": item["score"]}
                      for item in adjusted[:3]]
        assert recomputed == payload["utility_ranking"], (
            f"utility_ranking 无法独立复算：{payload['npc_id']} tick={event.tick}\n"
            f"实测 {payload['utility_ranking']}\n复算 {recomputed}"
        )
        assert payload["chosen_action"] == adjusted[0]["action"]
        checked += 1
    assert checked >= 5


def test_memory_view_none_leaves_decision_payload_unchanged(tmp_path):
    """⑦ 的**不变式**：`memory_view=None` ⇒ `npc.decision` payload 里**没有** `memory_influence` 键
    （保证未接线路径与改前逐字节一致）。"""
    _, log = _run(tmp_path, ticks=4, name="noview")
    decisions = [event.payload for event in log.read_all() if event.type == "npc.decision"]
    assert decisions
    for payload in decisions:
        assert "memory_influence" not in payload
