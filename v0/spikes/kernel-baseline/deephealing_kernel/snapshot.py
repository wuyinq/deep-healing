"""快照与状态哈希（V0 骨架，契约冻结）。

    state_hash        = sha256(canonical_json(state))
    event_chain_hash  = 截至该 tick 的事件日志末条 hash
    rng_state_digest  = sha256(canonical_json(rng_state))，rng_state 按 stream 名排序

规范化规则见 snapshot.schema.json 的 normalization 字段；实现必须与
tools/canonical_json.py 共用同一套序列化，禁止各写一份。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Snapshot:
    tick: int
    state: dict
    state_hash: str
    event_chain_hash: str
    rng_state_digest: str


def canonical_json(value: object) -> str:
    """规范化 JSON（键排序、分隔符 ,:、UTF-8、浮点 6 位、整数不带小数点）。"""
    raise NotImplementedError("V0 skeleton: reuse tools/canonical_json.py implementation")


def state_hash(state: dict) -> str:
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'snapshot'")


def take_snapshot(world: dict, tick: int, event_chain_hash: str, rng_state_digest: str) -> Snapshot:
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'snapshot'")


def write_checkpoint(snapshot: Snapshot, out_dir: Path) -> Path:
    """写 checkpoints/<tick>.json（回放时间轴与 verify 的数据源）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'snapshot'")


def compare_checkpoints(left_dir: Path, right_dir: Path) -> list[str]:
    """逐检查点比对 state_hash；返回分歧 tick 列表（空 = 一致，AC-2 判据）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'replay'")


def dump_divergence(left_dir: Path, right_dir: Path, tick: int) -> dict:
    """--dump-divergence：输出分歧 tick 的组件级 diff（根因定位辅助）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'replay'")
