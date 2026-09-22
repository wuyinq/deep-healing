"""cassette_replay provider：录制/回放（V0-M2 实现，契约见 cassette.format.md）。

key = sha256(canonical_json({capability_id, capability_version, canonical_input_hash, provider}))
miss 策略默认 fail_closed（抛 E_CASSETTE_MISS），回放跑绝不静默切远端。
命中后仍必须过 output_schema（防手工篡改）。

**四键口径（M2 / M-6 / F-13）**：`provider` **必须在键里**，否则同一输入会在
`deterministic_rule` 与 `remote_api` 下命中同一条 cassette。本模块提供两种调用形态：
  - `cassette_key(capability, payload, provider)` —— 设计 §3.1 冻结接口（从能力文档 + 输入算键）；
  - `cassette_key_from_parts(capability_id, capability_version, canonical_input_hash, provider)`
    —— 骨架桩声明的四元形态（四个键值显式传入），两者必须给出**同一个键**（有测试断言）。

**内容纪律（M2 / M-8）**：
  - 请求体**只记 canonical 化摘要**（`canonical_input_hash`），不记原始请求体；
  - 响应体不得含凭据（凭据从不进入 output：`remote_api` 只把解析后的输出对象交回来）；
  - 时间/追踪类响应头由 `remote_api.redact_headers()` 剥离，**不写进 cassette**；
  - `meta` 逐字遵守 `cassette.schema.json` 的 `$defs/meta`（`additionalProperties:false`），
    因此骨架 docstring 里的 `meta.redacted_fields` **不能**落进记录（与冻结 schema 冲突，
    已在 `06` 登记）；脱敏自证改由 `redaction_report()` 在**记录之外**给出。

**强度边界（FROZEN-CASSETTE-INTEGRITY-1）**：`hash`/`prev_hash` 链**无密钥**，
只检损坏 / 篡改，**不是真实性保证**。
"""

from __future__ import annotations

import json
from pathlib import Path

from ..snapshot import GENESIS_HASH, canonical_json, chained_hash, hash_object

DEFAULT_MISS_POLICY = "fail_closed"
SCHEMA_VERSION = "1.0.0"
RECORD_FIELDS = (
    "key", "capability_id", "capability_version", "provider",
    "canonical_input_hash", "output", "meta", "prev_hash", "hash",
)
# 回放时的**录制源**查找顺序（显式、确定性；回放 provider 自身不参与 key）
REPLAY_SOURCES = ("remote_api", "local_model", "deterministic_rule")


class CassetteMiss(Exception):
    code = "E_CASSETTE_MISS"


class CassetteTampered(Exception):
    code = "E_CASSETTE_TAMPERED"


class CassetteStore:
    """append-only 的 cassette 存储（每能力×provider 一个 JSONL 文件）。"""

    def __init__(self, root: Path, miss_policy: str = DEFAULT_MISS_POLICY) -> None:
        self._root = Path(root)
        self._miss_policy = miss_policy

    # ------------------------------------------------------------------ key
    def cassette_key(self, capability: dict, payload: dict, provider: str) -> str:
        """设计 §3.1 冻结接口：从能力文档 + 输入 + provider 算键（**四键**）。"""
        return self.cassette_key_from_parts(
            str(capability.get("id", "")),
            str(capability.get("version", "")),
            hash_object(payload if isinstance(payload, dict) else {}),
            str(provider),
        )

    def cassette_key_from_parts(
        self, capability_id: str, capability_version: str, canonical_input_hash: str, provider: str
    ) -> str:
        """四键口径的显式形态（与 `cassette_key` 同值）。"""
        return hash_object({
            "capability_id": capability_id,
            "capability_version": capability_version,
            "canonical_input_hash": canonical_input_hash,
            "provider": provider,
        })

    # ------------------------------------------------------------------ 文件
    def _path(self, capability_id: str, provider: str) -> Path:
        safe = capability_id.replace("/", "_")
        return self._root / f"{safe}__{provider}.jsonl"

    def _read(self, path: Path) -> list[dict]:
        if not path.is_file():
            return []
        records: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records

    # ------------------------------------------------------------------ 写
    def record(self, capability: dict, provider: str, payload: dict, output: dict, meta: dict) -> str:
        """录制一条记录（`meta` 必须逐字满足 `cassette.schema.json` 的 `$defs/meta`）。"""
        key = self.cassette_key(capability, payload, provider)
        path = self._path(str(capability.get("id", "")), provider)
        previous = self._read(path)
        prev_hash = previous[-1]["key"] if previous else GENESIS_HASH
        body = {
            "key": key,
            "capability_id": str(capability.get("id", "")),
            "capability_version": str(capability.get("version", "")),
            "provider": str(provider),
            "canonical_input_hash": hash_object(payload if isinstance(payload, dict) else {}),
            "output": output,
            "meta": meta,
            "prev_hash": prev_hash,
        }
        record = dict(body)
        record["hash"] = chained_hash(prev_hash, body)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(record) + "\n")
        return key

    # ------------------------------------------------------------------ 读
    def lookup(self, capability: dict, provider: str, payload: dict) -> dict:
        """按 key 查找；miss 时按 miss_policy 处理（fail_closed → 抛 CassetteMiss）。"""
        key = self.cassette_key(capability, payload, provider)
        path = self._path(str(capability.get("id", "")), provider)
        for record in self._read(path):
            if record.get("key") != key:
                continue
            _assert_record_hash(record)
            output = record.get("output")
            if not isinstance(output, dict):
                raise CassetteTampered(f"{key}: recorded output is not an object")
            return output
        if self._miss_policy == "fail_closed":
            raise CassetteMiss(f"{key}: no cassette for {capability.get('id')} provider={provider}")
        raise CassetteMiss(f"{key}: miss with unsupported policy {self._miss_policy!r}")

    def lookup_any(self, capability: dict, payload: dict, sources: tuple[str, ...] = REPLAY_SOURCES) -> tuple[dict, str]:
        """按**显式顺序**在录制源里查（回放用）；全部 miss ⇒ `CassetteMiss`（fail-closed）。"""
        for provider in sources:
            try:
                return self.lookup(capability, provider, payload), provider
            except CassetteMiss:
                continue
        raise CassetteMiss(
            f"{capability.get('id')}: no cassette in sources {sources} for canonical_input_hash="
            f"{hash_object(payload if isinstance(payload, dict) else {})}"
        )

    def verify_chain(self) -> list[str]:
        """校验文件内 prev_hash 链 + **同一 key 重复出现**；返回问题位置（空 = 完好）。

        **F-3（修复轮 5 / R4-C1）**：冻结条文 `cassette.format.md` §4.1.2 / §6 / §5.1 点名
        「同一文件内同一 key 出现多次 = 文件损坏 ⇒ `E_CASSETTE_TAMPERED`」，而此前只比
        `prev_hash` 链 ⇒ **回填产生的重复 key 零告警**（回填记录自洽，链上完全合法）。
        这里补上该判据：同一 key 第二次出现即记一条 problem（不取首个、不静默）。

        **F-3b（同轮）**：`prev_hash`-only 形态（改 `prev_hash` 不重签 / 改后自洽重签）实测
        已被本函数的「prev_hash 链 + 记录自校验 hash」两条判据覆盖（见 03 自测日志读数）；
        本函数不做结构性改动，仅由测试钉住该形态。
        """
        problems: list[str] = []
        if not self._root.is_dir():
            return problems
        for path in sorted(self._root.glob("*.jsonl")):
            previous_key = GENESIS_HASH
            seen_keys: set[str] = set()
            for index, record in enumerate(self._read(path)):
                key = record.get("key")
                if isinstance(key, str):
                    if key in seen_keys:
                        problems.append(f"{path.name}:{index} duplicate key {key} "
                                        f"(same key appears more than once in file)")
                    seen_keys.add(key)
                if record.get("prev_hash") != previous_key:
                    problems.append(f"{path.name}:{index} prev_hash mismatch "
                                    f"(expected {previous_key}, got {record.get('prev_hash')})")
                body = {name: record.get(name) for name in RECORD_FIELDS if name != "hash"}
                expected = chained_hash(record.get("prev_hash", GENESIS_HASH), body)
                if record.get("hash") != expected:
                    problems.append(f"{path.name}:{index} hash mismatch (expected {expected})")
                previous_key = record.get("key", "")
        return problems


def _assert_record_hash(record: dict) -> None:
    body = {name: record.get(name) for name in RECORD_FIELDS if name != "hash"}
    expected = chained_hash(record.get("prev_hash", GENESIS_HASH), body)
    if record.get("hash") != expected:
        raise CassetteTampered(f"{record.get('key')}: record hash mismatch (expected {expected})")


def redaction_report(capability: dict, payload: dict, headers: dict, redacted: dict) -> dict:
    """**记录之外**的脱敏自证（不落进 cassette 记录，见模块 docstring）。

    返回：凭据类头是否已替换、时间/追踪类头是否已剥离、请求体是否只以 canonical 摘要出现。
    """
    credential_leaks = sorted(
        key for key in (headers or {}) if str(key).lower() in {"authorization", "api-key", "x-api-key"}
        and redacted.get(key) != "***REDACTED***"
    )
    volatile_kept = sorted(key for key in (redacted or {}) if str(key).lower() in {
        "date", "x-request-id", "cf-ray", "server-timing",
    })
    return {
        "capability_id": str(capability.get("id", "")),
        "credential_headers_redacted": not credential_leaks,
        "credential_headers_leaked": credential_leaks,
        "volatile_headers_stripped": not volatile_kept,
        "volatile_headers_kept": volatile_kept,
        # `record()` 只把请求体写进 `canonical_input_hash`（摘要），不写原始请求体 ⇒ 逐字可核验
        "raw_request_body_stored": False,
        "canonical_input_hash": hash_object(payload if isinstance(payload, dict) else {}),
    }


class CassetteReplayProvider:
    """provider 适配器：只从 cassette 读，绝不发起网络请求。"""

    provider_class = "cassette_replay"

    def __init__(self, store: CassetteStore) -> None:
        self._store = store

    def invoke(self, capability: dict, payload: dict, *, timeout_ms: int) -> dict:
        """命中即返回录制输出（命中时**先校验记录 hash**）；miss ⇒ `E_CASSETTE_MISS`（fail-closed）。"""
        output, _source = self._store.lookup_any(capability, payload)
        return output
