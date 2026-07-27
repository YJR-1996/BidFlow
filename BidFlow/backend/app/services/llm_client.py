"""DashScope OpenAI 兼容接口客户端；仅在实际调用时导入 openai。"""

import time
from typing import Any


class LlmServiceError(RuntimeError):
    pass


class OpenAIChatClient:
    def __init__(self, api_key: str, model: str = "qwen-flash-2025-07-28", base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1", timeout: float = 30.0, max_retries: int = 2) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: Any | None = None

    def chat(self, messages: list[dict[str, str]]) -> str:
        if not self._api_key:
            raise LlmServiceError("LLM_API_KEY 未配置。")
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LlmServiceError("缺少 openai 依赖，请由组长在 requirements 中添加。") from exc
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url, timeout=self._timeout)
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                started = time.monotonic()
                response = self._client.chat.completions.create(model=self._model, messages=messages)
                _ = time.monotonic() - started
                content = response.choices[0].message.content
                if not content:
                    raise LlmServiceError("模型未返回文本内容。")
                return content
            except LlmServiceError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt == self._max_retries:
                    break
        raise LlmServiceError("大模型服务调用失败，请检查网络、模型配置或 API Key。") from last_error
