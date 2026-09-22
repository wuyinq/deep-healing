"""原子能力注册表（D-0.6 / AC-13，V0 骨架，契约冻结）。

**本模块是「新增能力不改内核代码」的关键**：它只按数据 glob 扫描
`capabilities/**/*.capability.json`，不维护任何 import 列表 / if 分支 / 硬编码能力名。
新增能力 = 新增一个数据文件（+ 可选一个 provider adapter 文件）。

运行时环节（01 设计 §7.5）：
  发现（data glob）→ 契约校验（schema + 版本唯一 + provider 可解析）→ 惰性加载
  → 灰度（priority + weight 路由）→ 回滚（pins.json 钉版本 + provider 顺序回退）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

PROVIDER_CLASSES = ("remote_api", "local_model", "deterministic_rule", "cassette_replay")


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


class CapabilityRegistry:
    """能力注册表（数据驱动发现，无代码硬编码）。"""

    def __init__(self, capabilities_dir: Path, pins_path: Path | None = None) -> None:
        self._dir = capabilities_dir
        self._pins_path = pins_path
        self._by_slot: dict[str, dict[str, dict]] = {}
        self._adapters: dict[str, ProviderAdapter] = {}

    def discover(self) -> list[str]:
        """扫描 `**/*.capability.json` 并返回 `id@version` 列表（按 id 排序）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'registry'")

    def validate(self) -> list[str]:
        """契约校验（schema / 版本唯一 / provider 可解析）；返回错误列表（空 = 通过）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'registry'")

    def register_adapter(self, provider_class: str, adapter: ProviderAdapter) -> None:
        """注册 provider 适配器（按 class 注册，与能力数据解耦）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'registry'")

    def invoke(
        self,
        slot: str,
        payload: dict,
        *,
        force_provider: str | None = None,
        replay_mode: bool = False,
        npc_id: str | None = None,
        budget: "BudgetLedger | None" = None,
    ) -> InvocationResult:
        """按 slot 调用能力。

        路由规则：force_provider > replay_mode（强制 cassette_replay + fail-closed）
        > providers[].priority 升序；每步出口都过 output_schema，失败按 fallback 链降级。
        """
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'registry'")

    def resolve_impl(self, impl: str) -> Callable[..., Any]:
        """解析 `builtin:<name>` 或 `module:<mod>:<attr>`（数据引用，非硬编码）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'registry'")

    def slots(self) -> list[str]:
        """当前已注册的槽位（按名排序）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'registry'")
