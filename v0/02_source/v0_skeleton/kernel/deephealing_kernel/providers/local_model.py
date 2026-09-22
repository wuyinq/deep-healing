"""local_model provider：本地推理降级通道（V0-M2 实现：**槽位设计 + 诚实 GAP**）。

工具链事实（计入 ADR 成本）：本机**无 NVIDIA GPU**；vllm / SGLang 走 GPU 路线不现实；
ollama 与 transformers CPU 小模型是可行降级路径；浏览器内推理（web-llm / transformers.js）列 V1 备选。

**本轮口径（REQ §6 / 设计 §6，硬）**：
  - 只交**槽位设计** + **诚实 GAP**：本机**没有**本地模型服务 ⇒ `available()` **恒 False**；
  - `available()` 是**真跑**的探测（对 `DEFAULT_ENDPOINT` 发起一次极短的只读请求，
    连不上就返回 False）——返回值本身就是「本机无服务」的真跑证据；
  - `invoke()` 在不可用时**抛结构化错误**（交给注册表的 fallback 链做**确定性降级**），
    **绝不伪造输出**；本文件**不得**出现任何「假装跑过」的分支。

`LOCAL_PROBE_BUDGET_S` 是**探测预算（秒）**，不是能力契约里的 `timeout_ms`
（能力超时值一律来自 `capabilities/*.capability.json` 的声明值，代码里零毫秒常量）。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
LOCAL_PROBE_BUDGET_S = 0.5


class LocalModelUnavailable(RuntimeError):
    """本地运行时不可用（结构化，可被 fallback 链捕获；**不是**伪造输出的理由）。"""

    code = "E_LOCAL_MODEL_UNAVAILABLE"


class LocalModelProvider:
    """本地模型适配器（ollama / transformers 二选一实现）。"""

    provider_class = "local_model"

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, model: str = "") -> None:
        self._endpoint = endpoint
        self._model = model

    def available(self) -> bool:
        """本地运行时是否可用（不可用即直接走 fallback，不阻塞 tick）。

        **真跑**：向 `<endpoint>/api/tags` 发一次只读探测；任何连接/协议错误一律返回 False
        （不抛异常 —— tick 内不得因为「本机没装模型」而断线）。
        """
        request = urllib.request.Request(url=f"{self._endpoint.rstrip('/')}/api/tags", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=LOCAL_PROBE_BUDGET_S) as response:
                json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return False
        return True

    def invoke(self, capability: dict, payload: dict, *, timeout_ms: int) -> dict:
        """不可用时抛 `E_LOCAL_MODEL_UNAVAILABLE`（由注册表转确定性降级），**不伪造输出**。"""
        if not self.available():
            raise LocalModelUnavailable(
                f"no local model server at {self._endpoint} (slot design only; honest GAP)"
            )
        raise LocalModelUnavailable(
            "local model runtime detected but no model is loaded for this slot "
            "(V0 ships the slot design only; no fabricated output)"
        )
