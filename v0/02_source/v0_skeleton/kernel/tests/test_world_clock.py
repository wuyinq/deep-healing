"""W12 世界钟判据（AC-M4-9②a/②b/②c/③；设计 §2 D-M4-3、§11 D-M4-13/D-M4-15④）。

判据（口径按 §11 D-M4-13 的裁决，**② 拆三条**）：
  ① **派生**：`derive_clock_semantics` 的相位**来自内容包**（`schedules/weekday.json#time_scale_note`），
     不是硬编码；改包反例（隔离副本 + 重签）⇒ 相位随之平移；
  ②a **锚定精度**：启动快进后世界钟读数与当前 UTC+8 墙上钟差 **≤ 1 分钟**；
  ②b **节流精度（无漂移）**：跨 **≥300 真实秒**，`|tick 增量 − 真实秒数| ≤ 1`，并给 `max_drift_ms`；
  ②c **如实披露**：打印「世界钟读数 − 墙上钟读数」原始量（1× 档下按构造每 300 秒约 +295 分钟，属预期）；
  ③ 1× 档 **1 真实秒 = 1 世界分钟**：`N ≥ 60` 真实秒 ⇒ tick 增量 `N`（容差 ≤1）；
  负例：去掉节流（无 sleep 快进）⇒ ③ **必须变红**。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

KERNEL_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = KERNEL_ROOT.parent / "districts" / "xingfu-xiaoqu"
SEED = 20260921
sys.path.insert(0, str(KERNEL_ROOT))

from deephealing_kernel import world_clock  # noqa: E402
from deephealing_kernel.events import EventLog  # noqa: E402
from deephealing_kernel.live import LiveWorld  # noqa: E402
from deephealing_kernel.pack import load_pack  # noqa: E402
from deephealing_kernel.tick import WorldKernel  # noqa: E402

REQUIRED_SEMANTIC_KEYS = ("tick0_minutes", "minutes_per_tick", "day_ticks", "source", "raw")


def _kernel(tmp_path: Path, name: str = "k") -> WorldKernel:
    out = tmp_path / name
    out.mkdir(parents=True, exist_ok=True)
    return WorldKernel(pack=load_pack(PACK_DIR), seed=SEED, log=EventLog(out / "events.jsonl"),
                       snapshot_every=0, checkpoint_dir=None)


# ---------------------------------------------------------------------------- ① 派生
def test_clock_semantics_are_derived_from_the_content_pack():
    sem = world_clock.derive_clock_semantics(load_pack(PACK_DIR))
    for key in REQUIRED_SEMANTIC_KEYS:
        assert key in sem, f"派生结果缺少 {key}"
    assert sem["tick0_minutes"] == 7 * 60, f"tick 0 应为 07:00，实测 {sem['tick0_minutes']}"
    assert sem["minutes_per_tick"] == 1
    assert sem["day_ticks"] == 24 * 60
    assert sem["day_ticks"] * sem["minutes_per_tick"] == 24 * 60
    assert "weekday.json#time_scale_note" in sem["source"]
    assert "tick 0 = 07:00" in sem["raw"]
    assert world_clock.clock_of(0, sem) == "07:00"
    assert world_clock.clock_of(600, sem) == "17:00"
    assert world_clock.clock_of(24 * 60, sem) == "07:00"      # 跨日回绕


def test_modified_pack_shifts_the_phase_counter_example(tmp_path):
    """反例（D-M4-15④）：在**隔离副本**上把 `tick 0 = 07:00` 改成 `08:30`（并重签）⇒ 相位必须平移。

    硬编码实现会留在 07:00（`tick0_minutes == 420`）⇒ 本判据变红。
    """
    copy = tmp_path / "xingfu-xiaoqu"      # 目录名必须等于 pack.json.id（district.pack.spec.md §1）
    shutil.copytree(PACK_DIR, copy)
    schedule_path = copy / "schedules" / "weekday.json"
    document = json.loads(schedule_path.read_text(encoding="utf-8"))
    document["time_scale_note"] = "1 tick = 1 世界分钟（600:1 压缩）；tick 0 = 08:30 起床点。"
    schedule_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")

    # 内容包有逐文件签名 ⇒ 改包后必须重签（否则 `load_pack` 会拒）
    proc = subprocess.run([sys.executable, "-m", "deephealing_kernel", "pack", "sign", str(copy)],
                          capture_output=True, text=True, cwd=str(KERNEL_ROOT))
    assert proc.returncode == 0, proc.stdout + proc.stderr

    sem = world_clock.derive_clock_semantics(load_pack(copy))
    assert sem["tick0_minutes"] == 8 * 60 + 30, (
        f"改包后相位必须平移（期望 510），实测 {sem['tick0_minutes']} ⇒ 相位是硬编码的")
    assert world_clock.clock_of(0, sem) == "08:30"
    # 快进算式随之平移 90 tick
    probe = datetime(2026, 9, 23, 7, 0, tzinfo=world_clock.TZ_UTC8)
    assert world_clock.warmup_ticks(probe, sem) == (7 * 60 - 510) % (24 * 60)


def test_clock_phase_is_not_a_hardcoded_literal():
    """静态：`world_clock.py` / `live.py` 里**不得**出现硬编码相位字面量（`420`）。"""
    needle = "420"
    for name in ("world_clock.py", "live.py"):
        path = KERNEL_ROOT / "deephealing_kernel" / name
        proc = subprocess.run(["grep", "-n", needle, str(path)], capture_output=True, text=True)
        assert proc.returncode == 1, f"{name} 出现硬编码相位字面量：{proc.stdout}"
    # 可达性对照（零命中不算证据）：同一个 grep 打到含该字面量的文件上 ⇒ 必须命中
    control = KERNEL_ROOT / "tools" / "duckdb_queries.sql"   # 交付树内、与该判据无关的文件
    proc = subprocess.run(["grep", "-c", needle, str(control)], capture_output=True, text=True)
    assert int(proc.stdout.strip() or 0) == 0, "对照文件不应含该字面量"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
        handle.write("TICK0 = 420\n")
        probe_path = Path(handle.name)
    try:
        proc = subprocess.run(["grep", "-n", needle, str(probe_path)],
                              capture_output=True, text=True)
        assert proc.returncode == 0 and "420" in proc.stdout, (
            "注入字面量后 grep 必须命中 ⇒ 证明上面的零命中不是「检查空转」")
    finally:
        probe_path.unlink()


def test_clock_semantics_fail_closed_when_the_note_is_missing():
    """内容包派生失败 ⇒ `E_CLOCK_SEMANTICS_UNKNOWN`（**不静默兜底**）。"""
    class _Stub:
        manifest = {"id": "stub-pack"}
        world_seed = {"constants": {"day_ticks": 24 * 60}}
        schedules = [{"id": "weekday", "day_ticks": 24 * 60}]   # 没有 time_scale_note

    with pytest.raises(world_clock.ClockSemanticsError) as excinfo:
        world_clock.derive_clock_semantics(_Stub())
    assert excinfo.value.code == "E_CLOCK_SEMANTICS_UNKNOWN"
    assert world_clock.ERROR_CODE in str(excinfo.value)

    # 对照：有 note 但 day_ticks 与 world.seed.json 不一致 ⇒ 同样 fail-closed
    class _Inconsistent(_Stub):
        schedules = [{"id": "weekday", "day_ticks": 1440,
                      "time_scale_note": "1 tick = 1 世界分钟；tick 0 = 07:00"}]
        world_seed = {"constants": {"day_ticks": 720}}

    with pytest.raises(world_clock.ClockSemanticsError):
        world_clock.derive_clock_semantics(_Inconsistent())


def test_clock_is_a_derived_read_only_view():
    """时钟**不写世界状态**：`state_hash` 不受时钟读数影响。"""
    sem = world_clock.derive_clock_semantics(load_pack(PACK_DIR))
    first = world_clock.clock_of(123, sem)
    second = world_clock.clock_of(123, sem)
    assert first == second
    assert world_clock.clock_minutes(123, sem) == (7 * 60 + 123) % (24 * 60)


# ---------------------------------------------------------------------------- ②a 锚定
def test_startup_anchor_matches_the_utc8_wall_clock(tmp_path):
    """②a 锚定精度：快进后世界钟读数与当前 UTC+8 墙上钟差 ≤ 1 分钟（给算式与实数）。"""
    sem = world_clock.derive_clock_semantics(load_pack(PACK_DIR))
    wall = world_clock.now_utc8()
    warmup = world_clock.warmup_ticks(wall, sem)
    kernel = _kernel(tmp_path)
    kernel.run(warmup)
    reading = world_clock.clock_of(kernel.world.tick, sem)
    wall_minutes = wall.hour * 60 + wall.minute
    reading_minutes = world_clock.clock_minutes(kernel.world.tick, sem)
    delta = abs(reading_minutes - wall_minutes)
    print(f"②a 锚定: 墙上钟 {wall.strftime('%H:%M')} | warmup = "
          f"(({wall_minutes}) - {sem['tick0_minutes']}) mod {sem['day_ticks']} = {warmup} ticks | "
          f"世界钟读数 {reading} | 差 {delta} 分钟")
    assert delta <= 1, f"锚定偏差 {delta} 分钟 > 1（warmup 算式错）"
    # 反例（自证）：若相位被硬编码成另一份内容包的值（tick 0 = 08:30），同一算式给出的读数
    # 会差 90 分钟 ⇒ 判据必然变红（证明「≤1 分钟」不是恒真）
    shifted = dict(sem, tick0_minutes=8 * 60 + 30)
    shifted_reading = world_clock.clock_minutes(kernel.world.tick, shifted)
    assert abs(shifted_reading - wall_minutes) > 1, "相位平移后仍 ≤1 分钟 ⇒ ②a 是恒真判据"


# ---------------------------------------------------------------------------- ③ 节流 1×
def _measure_pace(seconds: int, *, pace: float = 1.0, warmup: bool = True) -> dict:
    """真实推进 `seconds` 秒并给出读数（不依赖 pytest 的 tmp 目录）。

    `warmup=True` 时先做启动锚定（快进到当前 UTC+8 时刻）——这是 `live` 的**真实**启动形态，
    ②c 的「两钟原始偏差」只有在这个形态下才有设计所述的量级。
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        kernel = WorldKernel(pack=load_pack(PACK_DIR), seed=SEED,
                             log=EventLog(out / "events.jsonl"), snapshot_every=0,
                             checkpoint_dir=None)
        sem = world_clock.derive_clock_semantics(load_pack(PACK_DIR))
        wall = world_clock.now_utc8()
        warmup_ticks = world_clock.warmup_ticks(wall, sem) if warmup else 0
        if warmup_ticks:
            kernel.run(warmup_ticks)
        world = LiveWorld(kernel, sem=sem, pace_s_per_tick=pace, warmup=warmup_ticks)
        started = time.monotonic()
        before = world.tick
        loop = world.advance_loop(max_ticks=seconds)
        elapsed = time.monotonic() - started
        return {"ticks": world.tick - before, "elapsed_s": elapsed,
                "max_drift_ms": loop["max_drift_ms"], "loop_ticks": loop["ticks"],
                "tick_before": before, "tick_after": world.tick,
                "warmup_ticks": warmup_ticks, "wall_at_start": wall,
                "clock_before": world_clock.clock_of(before, sem),
                "clock_after": world_clock.clock_of(world.tick, sem)}


def test_pace_1x_is_one_real_second_per_world_minute():
    """③ `N ≥ 60` 真实秒 ⇒ tick 增量 `N`（容差 ≤1），并给 `max_drift_ms`。"""
    reading = _measure_pace(60)
    delta = reading["ticks"]
    print(f"③ 节流 1×: 真实 {reading['elapsed_s']:.3f}s ⇒ tick 增量 {delta}"
          f"（{reading['clock_before']} → {reading['clock_after']}）"
          f" | max_drift_ms {reading['max_drift_ms']}")
    assert abs(delta - 60) <= 1, f"1× 档下 60 真实秒的 tick 增量应为 60±1，实测 {delta}"
    # `max_drift_ms` = **单 tick 的 sleep 过冲**（deadline 锚定 ⇒ 不累积）。
    # macOS 的 sleep 粒度可达数十毫秒，故这里钉「单 tick 过冲 < 250ms」+ 上一条「不累积」的判据。
    assert reading["max_drift_ms"] < 250.0, f"单 tick 节流过冲过大：{reading['max_drift_ms']} ms"


def test_removing_the_throttle_turns_the_pace_criterion_red():
    """负例（AC-M4-9⑤）：去掉节流（`pace=0` 等效的无 sleep 快进）⇒ ③ 的判据**必须**变红。

    做法：把 `LiveWorld.advance_loop` 的 sleep 面绕过（`pace_s_per_tick=0`），
    同一窗口内 tick 增量远超真实秒数 ⇒ `|增量 − 真实秒数| ≤ 1` **不成立**。
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        kernel = WorldKernel(pack=load_pack(PACK_DIR), seed=SEED,
                             log=EventLog(out / "events.jsonl"), snapshot_every=0,
                             checkpoint_dir=None)
        sem = world_clock.derive_clock_semantics(load_pack(PACK_DIR))
        world = LiveWorld(kernel, sem=sem, pace_s_per_tick=0.0, warmup=0)
        started = time.monotonic()
        before = world.tick
        world.advance_loop(max_ticks=60)
        elapsed = time.monotonic() - started
        delta = world.tick - before
    assert elapsed < 1.0, f"无节流时应远快于 60 秒，实测 {elapsed:.3f}s"
    assert abs(delta - elapsed) > 1, (
        f"去掉节流后 |tick 增量 {delta} − 真实秒数 {elapsed:.3f}| 必须 > 1（否则③是恒真判据）")


# ---------------------------------------------------------------------------- ②b/②c 长窗口
def test_pace_holds_over_a_five_minute_window_and_discloses_the_raw_offset():
    """②b 跨 **≥300 真实秒** `|tick 增量 − 真实秒数| ≤ 1`；②c 如实披露两钟原始偏差。"""
    window = 300
    reading = _measure_pace(window)
    delta = reading["ticks"]
    drift = abs(delta - reading["elapsed_s"])
    sem = world_clock.derive_clock_semantics(load_pack(PACK_DIR))
    wall = world_clock.now_utc8()
    world_minutes = world_clock.clock_minutes(reading["tick_after"], sem)
    wall_minutes = wall.hour * 60 + wall.minute
    offset = (world_minutes - wall_minutes) % (24 * 60)
    print(f"②b 节流精度: 启动锚定 warmup = {reading['warmup_ticks']} ticks | "
          f"跨 {reading['elapsed_s']:.1f} 真实秒 ⇒ tick 增量 {delta} | "
          f"|增量 − 真实秒| = {drift:.3f} | max_drift_ms {reading['max_drift_ms']}")
    print(f"②c 如实披露（**不是失败**）: 世界钟读数 {world_clock.clock_of(reading['tick_after'], sem)} "
          f"− 墙上钟 {wall.strftime('%H:%M')} = +{offset} 分钟原始量"
          f"（1× 档按构造每 300 秒约 +295 分钟：世界每真实秒走 1 世界分钟，墙上钟只走 1/60 分钟）")
    assert reading["elapsed_s"] >= window - 1, f"窗口不足 {window} 真实秒：{reading['elapsed_s']}"
    assert drift <= 1.0, f"跨 {window} 秒的节流漂移 {drift:.3f} > 1 ⇒ 节流在漂"
    assert 200 <= offset <= 300, (
        f"原始偏差 {offset} 分钟不在预期区间（1× 档 300 秒约 +295 分钟）⇒ "
        f"要么锚定没生效、要么两钟被误当成同步（②c 的披露面被掩盖）")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-s"]))
