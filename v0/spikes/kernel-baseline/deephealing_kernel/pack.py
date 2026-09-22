"""内容包（district pack）加载与校验（V0 骨架，契约冻结）。

校验顺序（district.pack.spec.md §2）：pack.json → engine_range → entrypoints glob 命中
→ 各数据文件 schema → pack.sig 逐文件 sha256。任一失败 → E_PACK_INVALID，内核不启动。

禁止：pack 目录内出现可执行代码；路径含 `..` 或绝对路径（防越界读取）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class PackInvalid(Exception):
    """E_PACK_INVALID：内容包校验失败（携带首个失败原因）。"""

    code = "E_PACK_INVALID"


@dataclass(slots=True)
class DistrictPack:
    root: Path
    manifest: dict
    world_seed: dict
    buildings: list[dict] = field(default_factory=list)
    npcs: list[dict] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)
    schedules: list[dict] = field(default_factory=list)
    assets: dict = field(default_factory=dict)
    portals: list[dict] = field(default_factory=list)


def load_pack(root: Path) -> DistrictPack:
    """加载并校验内容包（含 pack.sig 逐文件比对）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'pack-loader'")


def verify_signature(root: Path) -> list[str]:
    """返回不一致清单（空 = 通过）；与 tools/verify_pack.py 共用同一算法。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'pack-loader'")


def check_engine_range(manifest: dict, kernel_version: str) -> bool:
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'pack-loader'")


def build_portal_edges(packs: dict[str, DistrictPack]) -> list[dict]:
    """按 portals 数据建跨区边；目标 pack 未加载时边标 inactive（不报错、不崩）。"""
    raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'pack-loader'")
