"""cassette_replay provider：录制/回放（V0 骨架，契约见 cassette.format.md）。

key = sha256(canonical_json({capability_id, capability_version, canonical_input_hash, provider}))
miss 策略默认 fail_closed（抛 E_CASSETTE_MISS），回放跑绝不静默切远端。
命中后仍必须过 output_schema（防手工篡改）。
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_MISS_POLICY = "fail_closed"


class CassetteMiss(Exception):
    code = "E_CASSETTE_MISS"


class CassetteStore:
    """append-only 的 cassette 存储（每能力×provider 一个 JSONL 文件）。"""

    def __init__(self, root: Path, miss_policy: str = DEFAULT_MISS_POLICY) -> None:
        self._root = root
        self._miss_policy = miss_policy

    def cassette_key(self, capability_id: str, capability_version: str, canonical_input_hash: str, provider: str) -> str:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'cassette'")

    def record(self, capability: dict, provider: str, payload: dict, output: dict, meta: dict) -> str:
        """录制一条记录（meta.redacted_fields 必须自证脱敏）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'cassette'")

    def lookup(self, capability: dict, provider: str, payload: dict) -> dict:
        """按 key 查找；miss 时按 miss_policy 处理（fail_closed → 抛 CassetteMiss）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'cassette'")

    def verify_chain(self) -> list[str]:
        """校验文件内 prev_hash 链；返回断链位置（空 = 完好）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'cassette'")


class CassetteReplayProvider:
    """provider 适配器：只从 cassette 读，绝不发起网络请求。"""

    provider_class = "cassette_replay"

    def __init__(self, store: CassetteStore) -> None:
        self._store = store

    def invoke(self, capability: dict, payload: dict, *, timeout_ms: int) -> dict:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'cassette'")
