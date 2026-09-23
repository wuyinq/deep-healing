"""世界钟（V0-M4 新增，设计 §2 D-M4-3 / §4.2）。

**相位从内容包派生，不发明新相位、不硬编码**：
  源 = `districts/<pack>/schedules/weekday.json#time_scale_note`
  （原文形如「1 tick = 1 世界分钟（600:1 压缩）；tick 0 = 07:00 起床点。」）

派生规则（可核验）：
  - 正则取 `tick 0 = HH:MM` ⇒ `tick0_minutes = HH*60+MM`（**由内容包算出，不写死常量**）；
  - 正则取 `1 tick = <n> 世界分钟` ⇒ `minutes_per_tick`；
  - 一致性断言：`day_ticks`（取自内容包 schedule 文档）必须 == `world.seed.json` 的
    `constants.day_ticks`，且 `day_ticks * minutes_per_tick == 24*60`；
  - 任一处解析/断言失败 ⇒ 抛 `E_CLOCK_SEMANTICS_UNKNOWN`（**fail-closed，不静默兜底**）。

两个速率必须分开命名（设计 §2 D-M4-3 的显式要求）：
  - `tick_semantics`：内容包声明的 tick 语义（1 tick = 1 世界分钟 = 600:1 压缩）；
  - `pace_s_per_tick`：`live` 的**节流档**（1× 档 = 1 真实秒 = 1 世界分钟）。
  两者不是同一件事，`/live/meta` 分别给出。

时钟是**派生只读视图**：`clock = (tick0 + tick * minutes_per_tick) % day_ticks`。
它**不写世界状态**，`state_hash` 不受时钟影响。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

#: 世界钟使用的时区（用户指令：UTC+8）
TZ_UTC8 = timezone(timedelta(hours=8))
TZ_NAME = "UTC+8"

ERROR_CODE = "E_CLOCK_SEMANTICS_UNKNOWN"

_TICK0_PATTERN = re.compile(r"tick\s*0\s*=\s*(\d{1,2}):(\d{2})")
_MINUTES_PER_TICK_PATTERN = re.compile(r"1\s*tick\s*=\s*(\d+)\s*世界分钟")
_SCALE_PATTERN = re.compile(r"(\d+)\s*:\s*1")


class ClockSemanticsError(Exception):
    """世界钟语义无法从内容包派生（fail-closed；调用方转结构化 `E_CLOCK_SEMANTICS_UNKNOWN`）。"""

    code = ERROR_CODE

    def __init__(self, detail: str) -> None:
        super().__init__(f"{ERROR_CODE}: {detail}")
        self.detail = detail


def _find_note_document(pack) -> tuple[dict, str]:
    """在内容包 schedules 文档里找带 `time_scale_note` 的那一份（按 id 升序，确定）。"""
    for document in sorted(pack.schedules, key=lambda item: str(item.get("id", ""))):
        note = document.get("time_scale_note")
        if isinstance(note, str) and note.strip():
            return document, note
    raise ClockSemanticsError(
        "no schedule document declares `time_scale_note`; the world clock phase cannot be derived "
        "from the content pack (refusing to fall back to a hard-coded phase)"
    )


def derive_clock_semantics(pack) -> dict:
    """从内容包派生世界钟语义（fail-closed）。

    返回 `{tick0_minutes, minutes_per_tick, day_ticks, source, raw, tick_semantics}`。
    """
    if pack is None:
        raise ClockSemanticsError("no content pack loaded")
    document, raw = _find_note_document(pack)
    match = _TICK0_PATTERN.search(raw)
    if match is None:
        raise ClockSemanticsError(f"cannot parse `tick 0 = HH:MM` from time_scale_note: {raw!r}")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ClockSemanticsError(f"parsed clock phase {hour:02d}:{minute:02d} is out of range")
    tick0_minutes = hour * 60 + minute

    rate = _MINUTES_PER_TICK_PATTERN.search(raw)
    if rate is None:
        raise ClockSemanticsError(f"cannot parse `1 tick = <n> 世界分钟` from time_scale_note: {raw!r}")
    minutes_per_tick = int(rate.group(1))
    if minutes_per_tick <= 0:
        raise ClockSemanticsError(f"minutes_per_tick must be positive, got {minutes_per_tick}")

    day_ticks = document.get("day_ticks")
    if not isinstance(day_ticks, int) or isinstance(day_ticks, bool) or day_ticks <= 0:
        raise ClockSemanticsError(
            f"schedule document {document.get('id')!r} must declare a positive integer `day_ticks`"
        )
    seed_constants = (pack.world_seed or {}).get("constants") or {}
    seed_day_ticks = seed_constants.get("day_ticks")
    if seed_day_ticks != day_ticks:
        raise ClockSemanticsError(
            f"day_ticks mismatch: schedules/{document.get('id')} declares {day_ticks} but "
            f"world.seed.json constants.day_ticks is {seed_day_ticks!r}"
        )
    if day_ticks * minutes_per_tick != 24 * 60:
        raise ClockSemanticsError(
            f"day_ticks * minutes_per_tick must equal one world day, got "
            f"{day_ticks} * {minutes_per_tick} = {day_ticks * minutes_per_tick}"
        )

    scale = _SCALE_PATTERN.search(raw)
    return {
        "tick0_minutes": tick0_minutes,
        "minutes_per_tick": minutes_per_tick,
        "day_ticks": day_ticks,
        "source": f"districts/{pack.manifest['id']}/schedules/{document.get('id')}.json#time_scale_note",
        "raw": raw,
        "tick_semantics": f"1 tick = {minutes_per_tick} world-minute"
                          f" ({scale.group(1) + ':1' if scale else 'n/a'} compression declared by "
                          f"the content pack)",
    }


def clock_minutes(tick: int, sem: dict) -> int:
    """tick ⇒ 世界日内的分钟数（派生只读视图；不写世界状态）。"""
    day_ticks = int(sem["day_ticks"])
    minutes_per_tick = int(sem["minutes_per_tick"])
    return (int(sem["tick0_minutes"]) + int(tick) * minutes_per_tick) % day_ticks


def clock_of(tick: int, sem: dict) -> str:
    """tick ⇒ `"HH:MM"`（UTC+8 世界钟读数）。"""
    minutes = clock_minutes(tick, sem)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def world_day_of(tick: int, sem: dict) -> int:
    """tick ⇒ 世界日序号（第几天，从 0 起）。"""
    day_ticks = int(sem["day_ticks"])
    minutes_per_tick = int(sem["minutes_per_tick"])
    return (int(sem["tick0_minutes"]) + int(tick) * minutes_per_tick) // day_ticks


def warmup_ticks(now_utc8: datetime, sem: dict) -> int:
    """启动快进 tick 数 = `((hh*60+mm) - tick0) mod day_ticks`（算式与实数都要打印）。"""
    if now_utc8.tzinfo is None:
        now_utc8 = now_utc8.replace(tzinfo=TZ_UTC8)
    else:
        now_utc8 = now_utc8.astimezone(TZ_UTC8)
    wall_minutes = now_utc8.hour * 60 + now_utc8.minute
    day_ticks = int(sem["day_ticks"])
    return (wall_minutes - int(sem["tick0_minutes"])) % day_ticks


def wall_minutes_elapsed(started_at: float, now: float, pace_s_per_tick: float) -> float:
    """真实秒数 ⇒ 世界分钟数（按节流档折算；`pace_s_per_tick` = 每个世界 tick 的真实秒数）。"""
    if pace_s_per_tick <= 0:
        raise ValueError("pace_s_per_tick must be positive")
    return (float(now) - float(started_at)) / float(pace_s_per_tick)


def now_utc8() -> datetime:
    """当前 UTC+8 墙上钟（**唯一**允许读时钟的位置；仅用于启动锚定，不进 tick 内）。"""
    return datetime.now(TZ_UTC8)
