"""remote_api provider：OpenAI 兼容远端模型调用（V0-M2 实现）。

安全硬约束：
  - 凭据**只**从环境变量读取（capability.providers[].requires_secrets 里声明的变量名）；
  - 凭据与 Authorization 头**不得**进入日志、事件、cassette、异常信息（一律 ***REDACTED***）；
  - secrets_in_context 必须为 false：能力上下文里不得出现任何凭据。

**变量名单一来源（M2 明确口径）**：变量名**只**从能力契约的 `requires_secrets[].env` 读，
代码里**不硬编码**任何变量名，也**不加** `TOOLFAB` 别名回退（会把一个环境里不存在的名字固化进实现）。
构造参数 `key_env` 只作**显式覆盖**（测试注入用）；契约声明优先。

**依赖纪律**：只用标准库 `urllib.request`（环境无新依赖预算）。

**脱敏面（M2 / M-8）**：`redact_headers()` 既替换凭据类头，也**剥离时间/追踪类头**
（`Date` / `x-request-id` / `cf-ray` / `server-timing` …）—— 它们会让「逐字节可复现」的
cassette 主张失效。请求体只记 canonical 化摘要（由 `cassette.py` 负责），**不记原始请求体**。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.tokenfab.cn/v1"
REDACTED = "***REDACTED***"

# 凭据类头（键名一律归一化小写后比较）
CREDENTIAL_HEADERS = frozenset({
    "authorization", "api-key", "apikey", "x-api-key", "x-auth-token", "proxy-authorization", "cookie",
})
# 时间/追踪类头：**必须剥离**（否则 cassette 无法逐字节复现）
VOLATILE_HEADERS = frozenset({
    "date", "age", "etag", "last-modified", "expires",
    "x-request-id", "request-id", "x-trace-id", "traceparent", "tracestate",
    "x-amzn-trace-id", "x-cloud-trace-context", "x-envoy-upstream-service-time",
    "cf-ray", "cf-cache-status", "server-timing", "report-to", "nel", "via", "x-served-by",
    "x-cache", "set-cookie",
})


class RemoteApiError(RuntimeError):
    """远端调用失败（结构化，可被 fallback 链捕获）。"""

    code = "E_REMOTE_API"


def redact_headers(headers: dict) -> dict:
    """返回脱敏后的头：凭据类 → `***REDACTED***`；时间/追踪类 → **整条剥离**。"""
    redacted: dict[str, str] = {}
    for key, value in (headers or {}).items():
        name = str(key).lower()
        if name in VOLATILE_HEADERS:
            continue
        redacted[key] = REDACTED if name in CREDENTIAL_HEADERS else value
    return redacted


def _declared_key_env(capability: dict) -> str:
    """从能力契约取凭据变量名（**单一来源**；不硬编码、不加别名回退）。"""
    for provider in capability.get("providers", []) if isinstance(capability, dict) else []:
        if not isinstance(provider, dict) or provider.get("class") != "remote_api":
            continue
        for entry in provider.get("requires_secrets", []) or []:
            name = entry.get("env") if isinstance(entry, dict) else entry
            if isinstance(name, str) and name:
                return name
    return ""


def _remote_provider_entry(capability: dict) -> dict:
    for provider in capability.get("providers", []) if isinstance(capability, dict) else []:
        if isinstance(provider, dict) and provider.get("class") == "remote_api":
            return provider
    return {}


def _output_contract(capability: dict) -> str:
    """把 output_schema 摘要成给模型的 JSON 契约（只含属性名与类型，不含任何凭据）。"""
    schema = capability.get("output_schema") if isinstance(capability, dict) else None
    schema = schema if isinstance(schema, dict) else {}
    properties = schema.get("properties") or {}
    fields = {}
    for name in sorted(properties):
        spec = properties[name] if isinstance(properties[name], dict) else {}
        kind = spec.get("type")
        if isinstance(kind, list):
            kind = "|".join(str(item) for item in kind)
        entry: dict = {"type": kind or "any"}
        if "enum" in spec:
            entry["enum"] = spec["enum"]
        if "minimum" in spec:
            entry["minimum"] = spec["minimum"]
        if "maximum" in spec:
            entry["maximum"] = spec["maximum"]
        fields[name] = entry
    return json.dumps({"required": schema.get("required", []), "properties": fields},
                      ensure_ascii=False, sort_keys=True)


class RemoteApiProvider:
    """OpenAI 兼容 chat/embeddings 适配器。"""

    provider_class = "remote_api"

    def __init__(self, base_url: str = DEFAULT_BASE_URL, key_env: str = "") -> None:
        self._base_url = base_url
        self._key_env = key_env

    # ------------------------------------------------------------------ 凭据
    def key_env(self, capability: dict) -> str:
        """生效的凭据变量名：**契约声明优先**，构造参数只作显式覆盖。"""
        return _declared_key_env(capability) or self._key_env

    def _api_key(self, capability: dict) -> str:
        """从环境变量取凭据；缺失即抛错（**不打印任何凭据内容**）。"""
        name = self.key_env(capability)
        if not name:
            raise RemoteApiError("capability declares no remote_api requires_secrets env var")
        value = os.environ.get(name, "")
        if not value:
            raise RemoteApiError(f"missing credential in env var {name}")
        return value

    # ------------------------------------------------------------------ 调用
    def invoke(self, capability: dict, payload: dict, *, timeout_ms: int) -> dict:
        """发起一次真实远端调用并返回**已解析的输出对象**（凭据不落盘、不进异常文本）。

        `timeout_ms` **只**来自能力契约的声明值（本文件不定义任何毫秒常量）。
        """
        entry = _remote_provider_entry(capability)
        model = entry.get("model") or ""
        base_url = entry.get("base_url") or self._base_url
        impl = str(entry.get("impl") or "")
        if not model:
            raise RemoteApiError("remote_api provider declares no model id")
        if impl.endswith("embeddings"):
            body = {"model": model, "input": [str(item) for item in (payload.get("texts") or [])]}
            endpoint = "/embeddings"
        else:
            body = {
                "model": model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": (
                        "你是结构化抽取器。只输出一个 JSON 对象，不要 markdown 代码块、不要解释。"
                        f"必须满足此契约：{_output_contract(capability)}"
                    )},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
                ],
                "response_format": {"type": "json_object"},
            }
            endpoint = "/chat/completions"

        request = urllib.request.Request(
            url=f"{base_url.rstrip('/')}{endpoint}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key(capability)}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(0.001, int(timeout_ms) / 1000.0)) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:  # 状态码可见，响应体不落盘（可能含追踪信息）
            raise RemoteApiError(f"remote_api HTTP {error.code} on {endpoint}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RemoteApiError(f"remote_api transport error on {endpoint}: {type(error).__name__}") from None

        document = json.loads(raw)
        usage = document.get("usage") if isinstance(document, dict) else None
        if isinstance(usage, dict):
            # 只取**计数**（整数），不落盘任何请求/响应原文
            self.last_usage = {
                "in": int(usage.get("prompt_tokens", 0) or 0),
                "out": int(usage.get("completion_tokens", 0) or 0),
            }
        if endpoint == "/embeddings":
            vectors = [item.get("embedding", []) for item in document.get("data", [])]
            dim = len(vectors[0]) if vectors else 0
            return {"dim": dim, "vectors": vectors, "provider_note": f"remote_api:{model}"}
        content = ((document.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        parsed = _parse_json_object(content)
        if parsed is None:
            raise RemoteApiError("remote_api returned non-JSON content (fallback required)")
        return parsed


def _parse_json_object(content: str) -> dict | None:
    """从模型文本里取出第一个 JSON 对象（容忍 ```json 围栏与前后解释文字）。"""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if len(text.split("```")) > 1 else text
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
