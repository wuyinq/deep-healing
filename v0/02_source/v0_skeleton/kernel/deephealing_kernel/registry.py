"""原子能力注册表（D-0.6 / AC-13，V0-M2 实现，契约冻结）。

**本模块是「新增能力不改内核代码」的关键**：它只按数据 glob 扫描
`capabilities/**/*.capability.json`，不维护任何 import 列表 / if 分支 / 硬编码能力名。
新增能力 = 新增一个数据文件（+ 可选一个 provider adapter 文件）。

运行时环节（01 设计 §7.5）：
  发现（data glob）→ 契约校验（schema + 版本唯一 + provider 可解析）→ 惰性加载
  → 灰度（priority + weight 路由）→ 回滚（pins.json 钉版本 + provider 顺序回退）

**拒绝码（逐类给 reason code，AC-M2-2 负例）**：
  `E_CAP_SCHEMA` / `E_CAP_UNREGISTERED` / `E_CAP_VERSION_CONFLICT` /
  `E_CAP_DUPLICATE_ID` / `E_CAP_PROVIDER_UNRESOLVED` / `E_CAP_SLOT_CONFLICT` /
  `E_CAP_DIGEST_MISMATCH`（pin 与内容摘要不一致 / 未声明摘要）。

**确定性边界（设计 §3.4b）**：本模块**不写世界状态**、不碰 tick 阶段、不用 wall-clock
参与任何决策；路由与降级链全部是**显式排序 + 数据驱动**的（`sorted()` / `priority` 升序 /
字典序 tie-break），因此同输入同 seed ⇒ 同路由、同降级路径。
"""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import jsonschema

PROVIDER_CLASSES = ("remote_api", "local_model", "deterministic_rule", "cassette_replay")
MODULE_PREFIX = "deephealing_kernel."
# `builtin:<name>` 白名单（数据引用的**显式登记**面；未登记即 `E_CAP_UNREGISTERED`）
BUILTIN_IMPLS = (
    "openai_compatible_chat",
    "openai_compatible_embeddings",
    "cassette_replay",
    "ollama_chat",
    "transformers_local",
    "determinism_gate_reference",
)
REASON_SCHEMA = "E_CAP_SCHEMA"
REASON_UNREGISTERED = "E_CAP_UNREGISTERED"
REASON_VERSION_CONFLICT = "E_CAP_VERSION_CONFLICT"
REASON_DUPLICATE_ID = "E_CAP_DUPLICATE_ID"
REASON_PROVIDER_UNRESOLVED = "E_CAP_PROVIDER_UNRESOLVED"
# **修-5（R2-M1，收口轮）**：同一 slot 被多个不同 id 声明 ⇒ fail-closed（防 pins 语义被第三维度旁路）。
REASON_SLOT_CONFLICT = "E_CAP_SLOT_CONFLICT"
# **R2 / R-M2-1 收口**：pin 必须绑定**内容摘要**（pins.json 的 `digests`）——
# 「回滚到这一份产物」的语义只有在「钉住的版本的文件字节没被改」时才成立。
REASON_DIGEST_MISMATCH = "E_CAP_DIGEST_MISMATCH"

SOURCE_ROOT = Path(__file__).resolve().parents[3]          # <02_source>
CAPABILITY_SCHEMA = SOURCE_ROOT / "capability.schema.json"


def file_digest(path: Path) -> str:
    """能力产物的**内容摘要** = 文件字节的 sha256。

    为什么是字节级而不是「解析后的 canonical JSON」（R-M2-1 收口口径）：
      - pin 的语义是「回滚到**这一份**产物」，判据必须能被独立复跑的人用
        `shasum -a 256 <file>` 逐字复核；
      - canonical JSON 对格式/空白不敏感 ⇒ 「钉住版本的文件字节被改」这类篡改会被放过
        （正是任务书 F6 的负例形态：「钉住某版本后改其文件字节 ⇒ 解析必须拒」）。
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CapabilityError(Exception):
    """注册表结构化错误（带 `code`，供上层 fail-closed 判定）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class ProviderAdapter(Protocol):
    """provider 适配器契约：只做「输入 → 结构化输出」，不得持世界状态。"""

    provider_class: str

    def invoke(self, capability: dict, payload: dict, *, timeout_ms: int) -> dict: ...


@dataclass(frozen=True, slots=True)
class InvocationResult:
    output: dict
    provider_class: str
    ms: float
    ok: bool
    cassette_key: str | None = None
    fallback_reason: str | None = None


@dataclass(slots=True)
class _Capability:
    path: Path
    document: dict
    slot: str
    key: str


class CapabilityRegistry:
    """能力注册表（数据驱动发现，无代码硬编码）。"""

    def __init__(self, capabilities_dir: Path, pins_path: Path | None = None,
                 cassette_store: Any = None, clock: Callable[[], float] | None = None,
                 replay_mode: bool = False) -> None:
        self._dir = Path(capabilities_dir)
        self._pins_path = Path(pins_path) if pins_path is not None else None
        self._cassette = cassette_store
        self._clock = clock
        # 会话级回放开关（`kernel run --replay`）：所有 invoke 默认走 `cassette_replay` + fail-closed
        self.default_replay_mode = bool(replay_mode)
        self._by_slot: dict[str, dict[str, dict]] = {}
        self._adapters: dict[str, ProviderAdapter] = {}
        self._files: dict[str, _Capability] = {}
        # pins.json 解析缓存（validate() 时刷新；修-1：pin 参与 capability 解析）
        self._pins: dict[str, str] = self._load_pins()
        # pin 的**内容摘要**绑定（R2 / R-M2-1 收口）：`{"<id>@<version>": sha256(file bytes)}`
        self._pin_digests: dict[str, str] = self._load_pin_digests()
        # 摘要绑定失败的 pin（非空 ⇒ `capability()` 对该 slot fail-closed）
        self._digest_rejections: dict[str, dict] = {}
        # slot 冲突登记（validate() 时刷新；修-5：非空 ⇒ capability()/slots() fail-closed）
        self._slot_conflicts: dict[str, dict[str, str]] = {}
        # 只追加的审计流水（fallback / 降级 / 拒绝），顺序确定 ⇒ 可回放
        self.journal: list[dict] = []
        # 每一次 invoke 的出口记录（成功与失败都记；顺序确定）⇒ 可核验「哪一类 provider 真跑过」
        self.calls: list[dict] = []

    # ------------------------------------------------------------------ 发现
    def _load_documents(self) -> dict[str, _Capability]:
        loaded: dict[str, _Capability] = {}
        if not self._dir.is_dir():
            return loaded
        for path in sorted(self._dir.rglob("*.capability.json")):
            key = path.name[: -len(".capability.json")]
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                document = None
            loaded[path.as_posix()] = _Capability(
                path=path,
                document=document if isinstance(document, dict) else {},
                slot=str((document or {}).get("slot", "")),
                key=key,
            )
        return loaded

    def discover(self) -> list[str]:
        """扫描 `**/*.capability.json` 并返回 `id@version` 列表（按 id 排序）。"""
        self._files = self._load_documents()
        keys = sorted(item.key for item in self._files.values())
        return keys

    # ------------------------------------------------------------------ 校验
    def validate(self) -> list[str]:
        """契约校验（schema / 版本唯一 / provider 可解析）；返回错误列表（空 = 通过）。"""
        if not self._files:
            self._files = self._load_documents()
        errors: list[str] = []
        schema = _load_schema()
        seen: dict[str, str] = {}
        by_id: dict[str, set[str]] = {}
        for path in sorted(self._files):
            item = self._files[path]
            document = item.document
            if not document:
                errors.append(f"{REASON_SCHEMA}: unparsable or empty capability document: {item.path}")
                continue
            try:
                jsonschema.validate(document, schema)
            except jsonschema.ValidationError as exc:
                location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
                errors.append(f"{REASON_SCHEMA}: {item.path.name} at {location}: {exc.message}")
                continue
            if item.key != f"{document.get('id')}@{document.get('version')}":
                errors.append(
                    f"{REASON_SCHEMA}: filename {item.path.name!r} != id@version "
                    f"{document.get('id')}@{document.get('version')}"
                )
                continue
            if document.get("safety", {}).get("secrets_in_context") is not False:
                errors.append(f"{REASON_SCHEMA}: safety.secrets_in_context must be false: {item.path.name}")
                continue
            identity = item.key
            if identity in seen:
                errors.append(f"{REASON_DUPLICATE_ID}: {identity} declared twice ({seen[identity]}, {item.path})")
                continue
            seen[identity] = str(item.path)
            by_id.setdefault(str(document.get("id")), set()).add(str(document.get("version")))
            for provider in document.get("providers", []):
                provider_class = provider.get("class")
                if provider_class not in PROVIDER_CLASSES:
                    errors.append(
                        f"{REASON_PROVIDER_UNRESOLVED}: {identity} declares unknown provider class "
                        f"{provider_class!r} (known: {', '.join(PROVIDER_CLASSES)})"
                    )
                    continue
                impl = str(provider.get("impl", ""))
                if impl.startswith("builtin:"):
                    name = impl.split(":", 1)[1]
                    if name not in BUILTIN_IMPLS:
                        errors.append(f"{REASON_UNREGISTERED}: {identity} builtin impl not registered: {impl}")
                elif impl.startswith("module:"):
                    module_path = impl.split(":", 2)[1]
                    if not module_path.startswith(MODULE_PREFIX):
                        errors.append(f"{REASON_UNREGISTERED}: {identity} module impl outside kernel: {impl}")
                else:
                    errors.append(f"{REASON_UNREGISTERED}: {identity} impl shape not allowed: {impl!r}")

        pins = self._load_pins()
        self._pin_digests = self._load_pin_digests()
        digest_rejections: dict[str, dict] = {}
        for capability_id in sorted(by_id):
            versions = sorted(by_id[capability_id])
            pinned = pins.get(capability_id)
            if pinned is not None and pinned not in versions:
                errors.append(
                    f"{REASON_VERSION_CONFLICT}: pins.json pins {capability_id}@{pinned} "
                    f"but only {versions} are present"
                )
            elif pinned is None and len(versions) > 1:
                errors.append(
                    f"{REASON_VERSION_CONFLICT}: {capability_id} has multiple versions {versions} "
                    "and no pins.json entry"
                )
            elif pinned is not None:
                # **R2 / R-M2-1 收口**：pin 必须绑定**内容摘要** —— 「未声明摘要」与
                # 「摘要不一致」都 fail-closed（钉住后改文件字节必须被拒）。
                problem = self._digest_problem(capability_id, pinned)
                if problem is not None:
                    errors.append(problem)
                    digest_rejections[capability_id] = {"version": pinned, "problem": problem}
        self._digest_rejections = digest_rejections

        # **修-5（R2-M1，收口轮）**：同一 `slot` 被多个**不同** `id` 声明 ⇒ fail-closed。
        # 机制（Raven 实证）：`_resolve_by_slot` 按 `id` 聚合版本、pin 按 `id` 查找，
        # 「slot」维度不在任何判据里 ⇒ 一个文件名合法、slot 与真身相同、id 不同的 rogue 文档
        # 会**后写者覆盖**已钉能力 —— pins 钉住语义被第三个维度旁路。
        # 口径：报 `E_CAP_SLOT_CONFLICT`（含冲突双方 `id@version`）；冲突期间 `_by_slot` 不装载
        # （`capability()` / `slots()` fail-closed，不半装载、不静默取舍）。
        by_slot_owners: dict[str, dict[str, str]] = {}
        for item in self._files.values():
            if item.slot and item.document:
                capability_id = str(item.document.get("id"))
                by_slot_owners.setdefault(item.slot, {}).setdefault(capability_id, str(item.path))
        slot_conflicts: dict[str, dict[str, str]] = {}
        for slot in sorted(by_slot_owners):
            owners = by_slot_owners[slot]
            if len(owners) > 1:
                # **同一 slot 被多个不同 id 声明**（同 id 多版本由 pin / E_CAP_VERSION_CONFLICT 管辖）。
                detail = "; ".join(
                    f"{capability_id} (versions: {sorted(str(item.document.get('version')) for item in self._files.values() if item.document and str(item.document.get('id')) == capability_id and item.slot == slot)}, file: {path})"
                    for capability_id, path in sorted(owners.items())
                )
                errors.append(
                    f"{REASON_SLOT_CONFLICT}: slot {slot!r} declared by multiple capability ids: {detail}"
                )
                slot_conflicts[slot] = dict(sorted(owners.items()))
        self._slot_conflicts = slot_conflicts

        if not errors:
            self._pins = pins
            self._by_slot = self._resolve_by_slot(pins)
        return errors

    def _pinned_version(self, capability_id: str) -> str | None:
        """返回该能力在 `pins.json` 里钉住的版本（无条目 ⇒ None）。

        **修-1（Raven R-M2-1）**：pin 必须**参与解析**——「回滚只需改 pins（纯数据）」的语义
        依赖这一点；pin 只做存在性校验而不参与解析 ⇒ 回滚语义失效（architect 已独立复现：
        投放 `@9.9.9` 副本 + pin 钉 `1.0.0` ⇒ `capability()` 解析到未钉的 9.9.9）。
        """
        return self._pins.get(str(capability_id))

    def _resolve_by_slot(self, pins: dict[str, str]) -> dict[str, dict]:
        """按 slot 装载能力文档：**pin 钉住的版本胜出**；无 pin 时才按 `id@version` 唯一性取用。"""
        by_id: dict[str, dict[str, dict]] = {}
        for item in self._files.values():
            if not item.slot or not item.document:
                continue
            by_id.setdefault(str(item.document.get("id")), {})[str(item.document.get("version"))] = item.document
        resolved: dict[str, dict] = {}
        for capability_id in sorted(by_id):
            versions = by_id[capability_id]
            pinned = str(pins.get(capability_id)) if capability_id in pins else None
            if pinned is not None and pinned in versions:
                # **R2 / R-M2-1 收口**：摘要绑定不成立 ⇒ 该能力**不装载**（fail-closed，
                # 绝不静默返回一份未通过内容校验的产物）。
                problem = self._digest_problem(capability_id, pinned)
                if problem is not None:
                    self._digest_rejections.setdefault(capability_id,
                                                        {"version": pinned, "problem": problem})
                    continue
                document = versions[pinned]
            elif len(versions) == 1:
                document = next(iter(versions.values()))
            else:
                # 多版本且无 pin：validate() 已报 E_CAP_VERSION_CONFLICT ⇒ 这里取确定性最大版本，
                # 仅在「未先 validate() 就直接 capability()」的异常路径兜底（上层会 fail-closed）。
                document = versions[sorted(versions)[-1]]
            if document.get("slot"):
                resolved[str(document["slot"])] = document
        return resolved

    def _load_pins(self) -> dict[str, str]:
        if self._pins_path is None or not self._pins_path.is_file():
            return {}
        try:
            document = json.loads(self._pins_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        pins = document.get("pins")
        return {str(key): str(value) for key, value in pins.items()} if isinstance(pins, dict) else {}

    def _load_pin_digests(self) -> dict[str, str]:
        """读 `pins.json` 的 `digests`（`{"<id>@<version>": "<sha256 of file bytes>"}`）。

        R2 / R-M2-1 收口：pin 只做「存在性校验」不够 —— 必须把「钉住的那一份产物」的
        内容摘要一并声明并在解析时校验，否则「钉住后改文件字节」不会被发现。
        """
        if self._pins_path is None or not self._pins_path.is_file():
            return {}
        try:
            document = json.loads(self._pins_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        digests = document.get("digests")
        return {str(key): str(value) for key, value in digests.items()} if isinstance(digests, dict) else {}

    def _file_for(self, capability_id: str, version: str) -> _Capability | None:
        key = f"{capability_id}@{version}"
        for item in self._files.values():
            if item.key == key:
                return item
        return None

    def _digest_problem(self, capability_id: str, version: str) -> str | None:
        """返回该 pin 的摘要问题描述（None = 绑定成立）。

        两类问题都算 fail-closed：
          ① pins.json **未声明**该 pin 的内容摘要（无从校验 ⇒ 不得当成通过）；
          ② 声明的摘要与盘上文件字节的 sha256 不一致（钉住的产物被改）。
        """
        item = self._file_for(capability_id, version)
        if item is None:
            return None
        declared = self._pin_digests.get(f"{capability_id}@{version}")
        actual = file_digest(item.path)
        if declared is None:
            return (f"{REASON_DIGEST_MISMATCH}: pins.json pins {capability_id}@{version} but declares no "
                    f"content digest for it (digests[{capability_id}@{version}] is mandatory; actual={actual})")
        if declared != actual:
            return (f"{REASON_DIGEST_MISMATCH}: {capability_id}@{version} content digest declared={declared} "
                    f"actual={actual} (file: {item.path})")
        return None

    # ------------------------------------------------------------------ 适配器
    def register_adapter(self, provider_class: str, adapter: ProviderAdapter) -> None:
        """注册 provider 适配器（按 class 注册，与能力数据解耦）。"""
        if provider_class not in PROVIDER_CLASSES:
            raise CapabilityError(REASON_PROVIDER_UNRESOLVED, f"unknown provider class {provider_class!r}")
        self._adapters[provider_class] = adapter

    def resolve_impl(self, impl: str) -> Callable[..., Any]:
        """解析 `builtin:<name>` 或 `module:<mod>:<attr>`（数据引用，非硬编码）。"""
        if impl.startswith("builtin:"):
            name = impl.split(":", 1)[1]
            if name not in BUILTIN_IMPLS:
                raise CapabilityError(REASON_UNREGISTERED, f"builtin impl not registered: {impl}")
            adapter = self._adapters.get(_builtin_provider_class(name))
            if adapter is None:
                raise CapabilityError(REASON_PROVIDER_UNRESOLVED, f"no adapter registered for {impl}")
            if name == "determinism_gate_reference":
                return _determinism_gate_reference
            return adapter.invoke
        if impl.startswith("module:"):
            _, module_path, attribute = impl.split(":", 2)
            if not module_path.startswith(MODULE_PREFIX):
                raise CapabilityError(REASON_UNREGISTERED, f"module impl outside kernel: {impl}")
            try:
                module = importlib.import_module(module_path)
                return getattr(module, attribute)
            except (ImportError, AttributeError) as exc:
                raise CapabilityError(REASON_UNREGISTERED, f"cannot resolve {impl}: {type(exc).__name__}") from None
        raise CapabilityError(REASON_UNREGISTERED, f"impl shape not allowed: {impl!r}")

    def slots(self) -> list[str]:
        """当前已注册的槽位（按名排序）。"""
        if self._slot_conflicts:
            # **修-5（R2-M1）**：slot 冲突 ⇒ 不半装载（fail-closed），不报任何槽位。
            return []
        if not self._by_slot:
            if not self._files:
                self.discover()
            self.validate()
        return sorted(self._by_slot)

    def capability(self, slot: str) -> dict:
        if not self._by_slot:
            # 惰性初始化：未显式 discover()/validate() 时先按数据 glob 装载并校验一次
            if not self._files:
                self.discover()
            if self.validate():
                if self._digest_rejections:
                    detail = "; ".join(f"{cid}@{info['version']}" for cid, info in
                                       sorted(self._digest_rejections.items()))
                    raise CapabilityError(
                        REASON_DIGEST_MISMATCH,
                        f"capability resolution blocked by pin content-digest mismatch: {detail}")
                # 校验失败即 fail-closed（不静默返回半装载的注册表）
                raise CapabilityError(REASON_SCHEMA, f"capability validation failed for slot {slot!r}")
        if self._slot_conflicts:
            # **修-5（R2-M1）**：slot 冲突 ⇒ fail-closed，**不静默返回** rogue 或真身中的任何一个。
            # 理由（写进 06）：冲突意味着「哪个文档是权威」无法从数据判定，任何静默取舍
            # 都会让审计者拿到与清单不一致的实现；调用方应先修数据再跑。
            detail = "; ".join(
                f"slot {slot!r}: {' vs '.join(sorted(owners))}"
                for slot, owners in sorted(self._slot_conflicts.items())
            )
            raise CapabilityError(REASON_SLOT_CONFLICT,
                                  f"capability resolution blocked by slot conflict: {detail}")
        document = self._by_slot.get(slot)
        if document is None:
            raise CapabilityError(REASON_PROVIDER_UNRESOLVED, f"unknown capability slot {slot!r}")
        # **R2 / R-M2-1 收口**：解析出口**再校验一次** pin 的内容摘要 —— 覆盖
        # 「validate() 之后、使用之前被改字节」的窗口（「钉住后改文件字节 ⇒ 解析必须拒」）。
        capability_id = str(document.get("id"))
        pinned = self._pins.get(capability_id)
        if pinned is not None:
            problem = self._digest_problem(capability_id, pinned)
            if problem is not None:
                self._digest_rejections.setdefault(capability_id, {"version": pinned, "problem": problem})
                raise CapabilityError(REASON_DIGEST_MISMATCH, problem)
        return document

    # ------------------------------------------------------------------ 调用
    def _route(self, capability: dict, *, force_provider: str | None, replay_mode: bool) -> str:
        """路由：`force_provider` > `replay_mode`（强制 cassette_replay）> `priority` 升序。"""
        declared = [
            provider for provider in capability.get("providers", [])
            if provider.get("class") in self._adapters
        ]
        if force_provider is not None:
            if force_provider not in PROVIDER_CLASSES:
                raise CapabilityError(REASON_PROVIDER_UNRESOLVED, f"unknown provider class {force_provider!r}")
            if not any(provider.get("class") == force_provider for provider in capability.get("providers", [])):
                raise CapabilityError(
                    REASON_PROVIDER_UNRESOLVED,
                    f"{capability.get('id')} does not declare provider {force_provider!r}",
                )
            if force_provider not in self._adapters:
                raise CapabilityError(
                    REASON_PROVIDER_UNRESOLVED, f"no adapter registered for forced provider {force_provider!r}"
                )
            return force_provider
        if replay_mode:
            if "cassette_replay" not in self._adapters:
                raise CapabilityError(REASON_PROVIDER_UNRESOLVED, "cassette_replay adapter is not registered")
            return "cassette_replay"
        if not declared:
            raise CapabilityError(
                REASON_PROVIDER_UNRESOLVED, f"{capability.get('id')} has no resolvable provider adapter"
            )
        ordered = sorted(declared, key=lambda provider: (int(provider.get("priority", 0)), str(provider.get("class"))))
        return str(ordered[0]["class"])

    def invoke(
        self,
        slot: str,
        payload: dict,
        *,
        force_provider: str | None = None,
        replay_mode: bool = False,
        npc_id: str | None = None,
        budget: "Any | None" = None,
    ) -> InvocationResult:
        """按 slot 调用能力。

        路由规则：force_provider > replay_mode（强制 cassette_replay + fail-closed）
        > providers[].priority 升序；每步出口都过 output_schema，失败按 fallback 链降级。
        """
        capability = self.capability(slot)
        replay_mode = bool(replay_mode or self.default_replay_mode)
        tick = int(payload.get("tick", 0)) if isinstance(payload, dict) and isinstance(payload.get("tick"), int) else 0
        if npc_id is None and isinstance(payload, dict) and isinstance(payload.get("npc_id"), str):
            npc_id = payload["npc_id"]

        if budget is not None:
            allowed, reason = budget.allow_call(tick, npc_id)
            if not allowed:
                return self._fallback(capability, payload, "on_budget_exhausted", f"budget:{reason}",
                                      slot=slot, npc_id=npc_id, replay_mode=replay_mode)

        provider_class = self._route(capability, force_provider=force_provider, replay_mode=replay_mode)
        adapter = self._adapters[provider_class]
        started = self._clock() if self._clock is not None else None
        try:
            output = adapter.invoke(capability, payload, timeout_ms=int(capability["timeout_ms"]))
        except Exception as error:  # noqa: BLE001 —— 任何 provider 失败都必须转确定性降级，不得裸奔
            # **回放模式的 fail-closed（设计 §2 / §6）**：`--replay` 下 cassette miss 必须**抛出**
            # `E_CASSETTE_MISS`，不得降级、更不得静默切远端（`on_cassette_miss` 的确定性兜底
            # 只适用于**非回放**路径）。
            if replay_mode and provider_class == "cassette_replay":
                from .providers.cassette import CassetteMiss

                if isinstance(error, CassetteMiss):
                    self.journal.append({
                        "event": "cassette.miss", "slot": slot, "provider": provider_class,
                        "npc_id": npc_id, "fail_closed": True,
                    })
                    raise
            reason = _fallback_key(error)
            self.journal.append({
                "event": "provider.error", "slot": slot, "provider": provider_class,
                "error": type(error).__name__, "reason": reason, "npc_id": npc_id,
            })
            # **修-6 / R2-M2（收口轮）**：cassette 篡改是**独立的 fail-closed 信号**（不是普通
            # provider 错误）—— 显式记 `cassette.tampered` 事件，`cmd_run` 据此转命令层 exit 1。
            if type(error).__name__ == "CassetteTampered":
                self.journal.append({
                    "event": "cassette.tampered", "slot": slot, "provider": provider_class,
                    "npc_id": npc_id, "fail_closed": True, "detail": str(error)[:200],
                })
            return self._fallback(capability, payload, reason, f"{type(error).__name__}",
                                  slot=slot, npc_id=npc_id, replay_mode=replay_mode)
        elapsed = 0.0 if started is None else (self._clock() - started) * 1000.0

        problems = _schema_problems(capability.get("output_schema"), output)
        if problems:
            self.journal.append({
                "event": "provider.invalid_output", "slot": slot, "provider": provider_class,
                "reason": "on_invalid_schema", "problems": problems[:3], "npc_id": npc_id,
            })
            return self._fallback(capability, payload, "on_invalid_schema", problems[0], slot=slot,
                                  npc_id=npc_id, replay_mode=replay_mode)

        cassette_key = None
        # 录制面（设计 §3.4b(4) / §6）：`remote_api` 的**真跑结果必须录制**；
        # `deterministic_rule` 也录制 —— 它是 `cassette_replay` 的**录制源**，
        # 「rule ↔ replay 逐字节等价」这条判据的 cassette 就是由 rule 录的。
        # **R4-C1（修复轮 5）/ F-2**：与 `_fallback()` 同源路径 —— 生效回放模式下**不得录制**
        # （`--replay` 下正常不可达，但 `force_provider` 可触达 ⇒ 同类缺陷，一并堵）。
        if provider_class in ("remote_api", "deterministic_rule") and self._cassette is not None \
                and not replay_mode:
            cassette_key = self._cassette.record(
                capability, provider_class, payload, output,
                _cassette_meta(capability, provider_class, adapter, elapsed),
            )
        elif provider_class in ("remote_api", "deterministic_rule") and self._cassette is not None:
            self.journal.append({
                "event": "cassette.record_suppressed", "slot": slot, "provider": provider_class,
                "reason": "replay_mode", "replay_mode": True, "npc_id": npc_id,
            })
        if budget is not None:
            cost = capability.get("cost") or {}
            tokens_in = int(cost.get("est_tokens_in", 0))
            tokens_out = int(cost.get("est_tokens_out", 0))
            usd = (tokens_in / 1000.0) * float(cost.get("usd_per_1k_in", 0.0)) \
                + (tokens_out / 1000.0) * float(cost.get("usd_per_1k_out", 0.0))
            budget.record(tick, npc_id, tokens_in, tokens_out, usd)
        self.calls.append({
            "slot": slot, "provider": provider_class, "ok": True, "fallback_reason": None,
            "ms": round(elapsed, 3), "cassette_key": cassette_key, "npc_id": npc_id,
            "output_digest": _digest(output),
        })
        return InvocationResult(output=output, provider_class=provider_class, ms=elapsed, ok=True,
                                cassette_key=cassette_key)

    def _fallback(self, capability: dict, payload: dict, key: str, detail: str,
                  *, slot: str, npc_id: str | None, replay_mode: bool = False) -> InvocationResult:
        """按契约的 `fallback.<key>` 目标做**确定性降级**（禁止静默回填）。

        **R4-C1（修复轮 5）**：`replay_mode` 是 `invoke()` 里解析出的**生效**值
        （`invoke(replay_mode=True) or self.default_replay_mode`，L391），必须显式传入 ——
        只读 `self.default_replay_mode` 会在「调用参数与构造参数不一致」时漏判。
        生效回放模式下**一律不得** `record()`：`--cassette-dir` 指向的是 replay 源，
        回放是审计路径，禁止改写它正在验证的产物（冻结条文 `cassette.format.md` §5）。
        """
        target = (capability.get("fallback") or {}).get(key)
        self.journal.append({
            "event": "capability.fallback", "slot": slot, "reason": key, "detail": detail,
            "target": target if isinstance(target, str) else (target or {}).get("provider"),
            "npc_id": npc_id,
        })
        if not isinstance(target, dict):
            raise CapabilityError("E_CAP_FALLBACK_UNRESOLVED",
                                  f"{capability.get('id')} has no structured fallback for {key}")
        provider_class = str(target.get("provider", ""))
        impl = str(target.get("impl", ""))
        if provider_class not in PROVIDER_CLASSES or provider_class not in self._adapters:
            raise CapabilityError("E_CAP_FALLBACK_UNRESOLVED",
                                  f"{capability.get('id')} fallback {key} -> {provider_class!r} has no adapter")
        callable_impl = self.resolve_impl(impl)
        output = callable_impl(payload) if provider_class == "deterministic_rule" else \
            self._adapters[provider_class].invoke(capability, payload, timeout_ms=int(capability["timeout_ms"]))
        problems = _schema_problems(capability.get("output_schema"), output)
        if problems:
            raise CapabilityError("E_CAP_FALLBACK_INVALID",
                                  f"{capability.get('id')} fallback {key} output invalid: {problems[0]}")
        # 确定性降级的输出**也要录制**（它是 `cassette_replay` 的录制源；回放才有东西可命中）
        # **R4-C1（修复轮 5）**：但**生效回放模式下一律不录** —— 否则降级输出会被写回
        # `--cassette-dir` 指向的 replay 源（5→6→7 条、链分叉、零告警）。
        if provider_class == "deterministic_rule" and self._cassette is not None and not replay_mode:
            self._cassette.record(capability, provider_class, payload, output,
                                  _cassette_meta(capability, provider_class, self._adapters[provider_class], 0.0))
        elif provider_class == "deterministic_rule" and self._cassette is not None and replay_mode:
            # 可观测：回放模式下「本来要回填」这件事必须留痕（零回填 ≠ 零痕迹）
            self.journal.append({
                "event": "cassette.record_suppressed", "slot": slot, "provider": provider_class,
                "reason": key, "replay_mode": True, "npc_id": npc_id,
            })
        self.calls.append({
            "slot": slot, "provider": provider_class, "ok": True, "fallback_reason": key,
            "ms": 0.0, "cassette_key": None, "npc_id": npc_id, "output_digest": _digest(output),
        })
        return InvocationResult(output=output, provider_class=provider_class, ms=0.0, ok=True,
                                fallback_reason=key)


# ---------------------------------------------------------------------- 模块级小工具
def _builtin_provider_class(name: str) -> str:
    if name in ("openai_compatible_chat", "openai_compatible_embeddings"):
        return "remote_api"
    if name in ("ollama_chat", "transformers_local"):
        return "local_model"
    if name == "cassette_replay":
        return "cassette_replay"
    return "deterministic_rule"


def _determinism_gate_reference(payload: dict) -> dict:
    """`builtin:determinism_gate_reference` 的执行体（纯函数，仅供确定性闸门参照）。"""
    return {"reference": True, "keys": sorted(payload) if isinstance(payload, dict) else []}


def _fallback_key(error: Exception) -> str:
    name = type(error).__name__
    if name == "CassetteMiss":
        return "on_cassette_miss"
    if name in ("TimeoutError", "RemoteApiError") and "timeout" in str(error).lower():
        return "on_timeout"
    return "on_error"


def _load_schema() -> dict:
    return json.loads(CAPABILITY_SCHEMA.read_text(encoding="utf-8"))


def _digest(value: Any) -> str:
    """输出对象的 canonical 摘要（审计流水用；不含凭据）。"""
    import hashlib

    from .snapshot import canonical_json

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _schema_problems(schema: Any, output: Any) -> list[str]:
    if not isinstance(schema, dict):
        return []
    try:
        jsonschema.validate(output, schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        return [f"{location}: {exc.message}"]
    return []


def _cassette_meta(capability: dict, provider_class: str, adapter: Any, elapsed_ms: float) -> dict:
    """`cassette.schema.json` 的 `$defs/meta`（`additionalProperties:false`，逐字对齐）。"""
    import datetime

    model = None
    for provider in capability.get("providers", []):
        if provider.get("class") == provider_class:
            model = provider.get("model")
            break
    usage = getattr(adapter, "last_usage", None) or {}
    tokens = {
        "in": int(usage.get("in", 0)) if isinstance(usage, dict) else 0,
        "out": int(usage.get("out", 0)) if isinstance(usage, dict) else 0,
    }
    return {
        "model": model if isinstance(model, str) else None,
        "tokens": tokens,
        "latency_ms": round(float(elapsed_ms), 3),
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "schema_version": "1.0.0",
    }
