"""provider 适配器包（四类 provider 的唯一实现位置）。

契约级禁令：模型/HTTP/SDK 调用**只允许**出现在本包内；业务模块（tick/ecs/rules/memory）
一律经 CapabilityRegistry.invoke。Sentinel 会按此扫描内核业务模块中的 HTTP/SDK 调用。
"""

from __future__ import annotations

__all__ = ["remote_api", "local_model", "deterministic_rule", "cassette"]
