"""local_model provider：本地推理降级通道（V0 骨架）。

工具链事实（计入 ADR 成本）：本机**无 NVIDIA GPU**；vllm / SGLang 走 GPU 路线不现实；
ollama 与 transformers CPU 小模型是可行降级路径；浏览器内推理（web-llm / transformers.js）列 V1 备选。
"""

from __future__ import annotations

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"


class LocalModelProvider:
    """本地模型适配器（ollama / transformers 二选一实现）。"""

    provider_class = "local_model"

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, model: str = "") -> None:
        self._endpoint = endpoint
        self._model = model

    def available(self) -> bool:
        """本地运行时是否可用（不可用即直接走 fallback，不阻塞 tick）。"""
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'provider-local'")

    def invoke(self, capability: dict, payload: dict, *, timeout_ms: int) -> dict:
        raise NotImplementedError("V0 skeleton: implement per 08_v0_plan.md step 'provider-local'")
