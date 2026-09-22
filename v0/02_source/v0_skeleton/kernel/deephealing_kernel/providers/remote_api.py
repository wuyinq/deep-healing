"""remote_api provider：OpenAI 兼容远端模型调用（V0 骨架）。

安全硬约束：
  - 凭据**只**从环境变量读取（capability.providers[].requires_secrets 里声明的变量名）；
  - 凭据与 Authorization 头**不得**进入日志、事件、cassette、异常信息（一律 ***REDACTED***）；
  - secrets_in_context 必须为 false：能力上下文里不得出现任何凭据。
"""

from __future__ import annotations

import os

DEFAULT_BASE_URL = "https://api.tokenfab.cn/v1"
REDACTED = "***REDACTED***"


class RemoteApiProvider:
    """OpenAI 兼容 chat/embeddings 适配器。"""

    provider_class = "remote_api"

    def __init__(self, base_url: str = DEFAULT_BASE_URL, key_env: str = "") -> None:
        self._base_url = base_url
        self._key_env = key_env

    def _api_key(self) -> str:
        """从环境变量取凭据；缺失即抛错（**不打印任何凭据内容**）。"""
        value = os.environ.get(self._key_env, "")
        if not value:
            raise RuntimeError(f"missing credential in env var {self._key_env}")
        return value

    def invoke(self, capability: dict, payload: dict, *, timeout_ms: int) -> dict:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'provider-remote'")

    def redact_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """返回脱敏后的头（Authorization / api-key 一律替换为 ***REDACTED***）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'provider-remote'")
