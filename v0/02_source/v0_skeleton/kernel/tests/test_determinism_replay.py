"""RED 用例：同一事件日志重放两次 → 全部检查点 state_hash 一致（AC-M1-2）。

RED 先行：内核为接口桩时本文件必须真实失败（NotImplementedError）。
最小 GREEN 后必须全绿且 **非 skipped**（≥4 passed, 0 skipped）。

冻结运行形态：
    cd <workspace>/02_source/v0_skeleton/kernel && \
    PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_determinism_replay.py -q -p no:cacheprovider

覆盖设计 §6 的 R1~R4，含 3 类负例（wall-clock 泄漏 / 无序迭代 / 新增 stream 不扰动既有序列）
与 2 条反向对照（set[int] 恒序、共享计数器错误实现），保证负例不是「零命中绿」。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK_REL = "districts/xingfu-xiaoqu"
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SEED = 20260921

from deephealing_kernel import cli as cli_mod  # noqa: E402
from deephealing_kernel import events as events_mod  # noqa: E402
from deephealing_kernel import snapshot as snapshot_mod  # noqa: E402
from deephealing_kernel import tick as tick_mod  # noqa: E402
from deephealing_kernel.pack import load_pack  # noqa: E402


def _run_kernel(out_dir: Path, ticks: int = 60, snapshot_every: int = 20) -> Path:
    """在 out_dir 内跑一次 run（检查点落 out_dir/checkpoints），返回 out_dir。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    log = events_mod.EventLog(out_dir / "e.jsonl")
    kernel = tick_mod.WorldKernel(
        pack=load_pack(PACK_DIR),
        seed=SEED,
        log=log,
        snapshot_every=snapshot_every,
        checkpoint_dir=out_dir / "checkpoints",
        plan_ticks=ticks,
    )
    kernel.run(ticks)
    return out_dir


# --------------------------------------------------------------------------- R1
def test_replay_twice_yields_identical_checkpoints(tmp_path):
    """同一事件日志重放两次，逐检查点 state_hash / rng_state_digest / event_chain_hash 必须完全一致。"""
    left = _run_kernel(tmp_path / "run_a")
    right = _run_kernel(tmp_path / "run_b")
    assert snapshot_mod.compare_checkpoints(left / "checkpoints", right / "checkpoints") == []

    replay_dir = tmp_path / "replay"
    replay_dir.mkdir()
    rc = cli_mod.main(
        [
            "replay",
            "--events", str(left / "e.jsonl"),
            "--pack", str(PACK_DIR),
            "--checkpoint-every", "20",
            "--out", str(replay_dir),
        ]
    )
    assert rc == 0
    # x-ac2-criterion (5)：强制 run ↔ replay 三字段逐点比对
    # 修复轮 C9：replay 的检查点落 `<out>/checkpoints/`（与 run 同构）
    assert snapshot_mod.compare_checkpoints(left / "checkpoints", replay_dir / "checkpoints") == []


# --------------------------------------------------------------------------- R2
def test_replay_detects_wall_clock_leak(tmp_path):
    """负例（对抗用例）：tick 内引入 wall-clock 后必须出现分歧；去掉泄漏后一致。双向断言。"""
    # ① 反向对照：无泄漏 ⇒ 两次产物一致
    clean_a = _run_kernel(tmp_path / "clean_a")
    clean_b = _run_kernel(tmp_path / "clean_b")
    assert snapshot_mod.compare_checkpoints(clean_a / "checkpoints", clean_b / "checkpoints") == []

    # ② 注入 wall-clock 泄漏：decide 阶段的 need 漂移改用 time.time_ns()
    original = tick_mod.stub_decide

    def leaky(world, rng, tick, ctx):
        intents = original(world, rng, tick, ctx)
        # 注意：`time.time_ns() % 1000` 在本机**恒为 0**（时钟微秒粒度）⇒ 注入会退化成常量，
        # 负例就变成零命中绿。故取**微秒**分量（实测逐次不同）。
        leaked = int(time.time_ns() // 1000) % 1000 - 500
        for intent in intents:
            intent["jitter_mm"] = leaked
        return intents

    tick_mod.stub_decide = leaky
    try:
        leaky_a = _run_kernel(tmp_path / "leaky_a")
        leaky_b = _run_kernel(tmp_path / "leaky_b")
    finally:
        tick_mod.stub_decide = original

    diffs = snapshot_mod.compare_checkpoints(leaky_a / "checkpoints", leaky_b / "checkpoints")
    assert diffs, "tick 内引入 wall-clock 后两次产物必须分歧（检测有效性证明）"
    assert any(d.startswith("field_diff:") and "field=state_hash" in d for d in diffs), diffs

    # ③ 干净 verify 子进程（无泄漏补丁）必须把泄漏日志判红，并打印首个分歧 tick
    proc = subprocess.run(
        [sys.executable, "-m", "deephealing_kernel", "verify",
         "--events", str(leaky_a / "e.jsonl"), "--pack", str(PACK_DIR)],
        capture_output=True, text=True, cwd=str(KERNEL_ROOT),
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    assert proc.returncode != 0, "泄漏日志必须被 verify 判红"
    assert re.search(r"divergence", proc.stdout + proc.stderr, re.I), proc.stdout + proc.stderr


# --------------------------------------------------------------------------- R3
_DRIVER = textwrap.dedent(
    '''
    """R3 子进程驱动器：注入「set 迭代顺序驱动决策」缺陷并把该顺序写进 state。

    用法：driver.py <kernel_root> <out_dir> <mode>
      mode = sorted | strset | intset
    """
    import sys
    from pathlib import Path

    kernel_root = Path(sys.argv[1]).resolve()
    out_dir = Path(sys.argv[2]).resolve()
    mode = sys.argv[3]
    sys.path.insert(0, str(kernel_root))

    from deephealing_kernel import events as events_mod
    from deephealing_kernel import tick as tick_mod
    from deephealing_kernel.pack import load_pack

    original = tick_mod.stub_decide

    def unordered(world, rng, tick, ctx):
        intents = original(world, rng, tick, ctx)
        if mode == "strset":
            order = list({"npc-001", "npc-002", "npc-003", "npc-004", "npc-005"})
        elif mode == "intset":
            order = ["npc-%03d" % n for n in {1, 2, 3, 4, 5}]
        else:
            order = sorted({"npc-001", "npc-002", "npc-003", "npc-004", "npc-005"})
        # 前提 (b)：迭代顺序必须真的进入 state_hash（编码成 needs.esteem 增量，逐 tick 累积）
        rank = order.index("npc-002")
        for intent in intents:
            intent["needs_delta"] = {"esteem": (rank + 1) / 1000.0}
        return intents

    tick_mod.stub_decide = unordered

    out_dir.mkdir(parents=True, exist_ok=True)
    log = events_mod.EventLog(out_dir / "e.jsonl")
    kernel = tick_mod.WorldKernel(
        pack=load_pack(kernel_root.parent / "districts" / "xingfu-xiaoqu"),
        seed=20260921, log=log, snapshot_every=20, checkpoint_dir=out_dir / "checkpoints",
    )
    kernel.run(60)
    '''
)


def test_replay_detects_unordered_iteration(tmp_path):
    """负例：用 set 迭代顺序驱动决策 → 跨进程哈希分歧必须被检出。

    前提（预审 M5 三条，缺一即零命中绿）：
      (a) 注入容器是 **set[str]**（set[int] 恒为 1..5、dict 恒为插入序 ⇒ 永远红不了）；
      (b) 迭代顺序真的进入 state_hash；
      (c) 两个产物在**不同子进程**产生（PYTHONHASHSEED=1 vs =2），测试进程**不作**比较方。
    """
    driver = tmp_path / "unordered_driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    kernel_root = str(KERNEL_ROOT)

    def produce(mode: str, hashseed: str, name: str) -> Path:
        out = tmp_path / name
        env = dict(os.environ, PYTHONHASHSEED=hashseed, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run(
            [sys.executable, str(driver), kernel_root, str(out), mode],
            capture_output=True, text=True, env=env, cwd=kernel_root,
        )
        assert proc.returncode == 0, proc.stderr
        return out / "checkpoints"

    # ① set[str] 跨进程 ⇒ 必须分歧，且分歧落在 state_hash 上
    diffs = snapshot_mod.compare_checkpoints(
        produce("strset", "1", "str_1"), produce("strset", "2", "str_2")
    )
    assert diffs, "跨进程 set[str] 迭代顺序分歧必须被检出"
    assert any(d.startswith("field_diff:") and "field=state_hash" in d for d in diffs), diffs

    # ② 反向对照：容器换成 set[int]（恒为 1..5）⇒ 必须**不**分歧，证明 ① 不是零命中绿
    assert snapshot_mod.compare_checkpoints(
        produce("intset", "1", "int_1"), produce("intset", "2", "int_2")
    ) == []

    # ③ 把注入改回 sorted() ⇒ 一致
    assert snapshot_mod.compare_checkpoints(
        produce("sorted", "1", "sorted_1"), produce("sorted", "2", "sorted_2")
    ) == []


# --------------------------------------------------------------------------- R4
def test_new_subsystem_does_not_perturb_existing_streams(tmp_path):
    """新增子系统 stream 不得改变既有 stream 序列（RNG 分流契约）。含「共享计数器」错误实现对照。"""
    from deephealing_kernel.rng import WorldRng

    first_rng = WorldRng(SEED)
    first = [first_rng.stream("npc.move").next_u64() for _ in range(8)]

    second_rng = WorldRng(SEED)
    second_rng.stream("new.subsystem")  # 先创建另一个流
    second = [second_rng.stream("npc.move").next_u64() for _ in range(8)]
    assert first == second, "新增 stream 不得扰动既有 stream 序列"

    # B5（修复轮）：如实断言两条不同的命题，不得写反
    #   ① 既有 stream 的 digest **逐位不变**（成立）
    #   ② 世界级 `rng_state_digest` 覆盖**全部已创建 stream** ⇒ 新增子系统**会**改变它
    plain = WorldRng(SEED)
    plain.stream("npc.move").next_u64()
    with_extra = WorldRng(SEED)
    with_extra.stream("npc.move").next_u64()
    with_extra.stream("new.subsystem").next_u64()
    assert plain.stream("npc.move").digest() == with_extra.stream("npc.move").digest(), \
        "① 既有 stream 的 digest 必须逐位不变"
    assert plain.digests() != with_extra.digests(), "② 世界级 digests 表必须因新增 stream 而变化"
    assert plain.state_digest() != with_extra.state_digest(), \
        "② 新增 stream 必须改变世界级 rng_state_digest（如实断言；它覆盖全部已创建 stream）"

    # 反向对照：错误实现（所有 stream 共享一个计数器）必须被同一条判据判红
    class _SharedCounterRng:
        """错误实现：无分流，所有 stream 共享一个计数器。"""

        def __init__(self, seed: int) -> None:
            self._counter = 0

        def stream(self, name: str):
            return self

        def next_u64(self) -> int:
            self._counter += 1
            return self._counter

    wrong_a = _SharedCounterRng(SEED)
    wrong_first = [wrong_a.stream("npc.move").next_u64() for _ in range(8)]
    wrong_b = _SharedCounterRng(SEED)
    wrong_b.stream("new.subsystem").next_u64()
    wrong_second = [wrong_b.stream("npc.move").next_u64() for _ in range(8)]
    assert wrong_first != wrong_second, "错误实现（共享计数器）必须被本判据判红"


# --------------------------------------------------------------------------- 边界
@pytest.mark.parametrize("ticks,snapshot_every", [(1, 1), (7, 3)])
def test_single_and_nondivisible_snapshot_every(tmp_path, ticks, snapshot_every):
    """边界：单 tick / snapshot_every 不整除 ticks 时仍必须确定性一致。"""
    left = _run_kernel(tmp_path / f"a_{ticks}_{snapshot_every}", ticks=ticks, snapshot_every=snapshot_every)
    right = _run_kernel(tmp_path / f"b_{ticks}_{snapshot_every}", ticks=ticks, snapshot_every=snapshot_every)
    assert snapshot_mod.compare_checkpoints(left / "checkpoints", right / "checkpoints") == []
