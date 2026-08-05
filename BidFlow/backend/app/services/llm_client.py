"""DashScope OpenAI 兼容接口客户端；仅在实际调用时导入 openai。"""

import json
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

    def _ensure_client(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise LlmServiceError("LLM_API_KEY 未配置。")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LlmServiceError("缺少 openai 依赖，请由组长在 requirements 中添加。") from exc
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url, timeout=self._timeout)
        return self._client

    def chat(self, messages: list[dict[str, str]]) -> str:
        """普通对话，返回纯文本"""
        client = self._ensure_client()
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = client.chat.completions.create(model=self._model, messages=messages)
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

    def chat_vision(self, images_base64: list[str], prompt: str) -> str:
        """视觉模型识别图片（OCR）。images_base64 为不含 data: 前缀的 base64 字符串。"""
        client = self._ensure_client()
        content_parts: list[dict] = [{"type": "text", "text": prompt}]
        for b64 in images_base64:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        messages = [{"role": "user", "content": content_parts}]
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = client.chat.completions.create(model=self._model, messages=messages)
                content = response.choices[0].message.content
                if not content:
                    raise LlmServiceError("视觉模型未返回文本内容。")
                return content
            except LlmServiceError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt == self._max_retries:
                    break
        raise LlmServiceError("视觉模型调用失败，请检查网络、模型配置或 API Key。") from last_error

    def chat_json(self, messages: list[dict[str, str]]) -> dict:
        """要求 LLM 以 JSON 对象返回结果，失败时抛出 LlmServiceError"""
        client = self._ensure_client()
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                content = response.choices[0].message.content
                if not content:
                    raise LlmServiceError("模型未返回文本内容。")
                return json.loads(content)
            except LlmServiceError:
                raise
            except json.JSONDecodeError as exc:
                raise LlmServiceError(f"LLM 返回非 JSON 内容: {exc}") from exc
            except Exception as exc:
                last_error = exc
                if attempt == self._max_retries:
                    break
        raise LlmServiceError("大模型服务调用失败，请检查网络、模型配置或 API Key。") from last_error

    def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict],
    ) -> tuple[str | None, list[dict]]:
        """Function calling 对话：返回 (content, tool_calls)。

        - content: 模型文本回复（无工具调用时非空；有工具调用时可能为 None）
        - tool_calls: 模型请求执行的工具调用列表
          [{id, function: {name, arguments(JSON 字符串)}}]
        模型/端点不支持 tools 时抛出 LlmServiceError，由调用方降级为纯文本。
        """
        client = self._ensure_client()
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
                msg = response.choices[0].message
                tool_calls = []
                for tc in (msg.tool_calls or []):
                    tool_calls.append({
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    })
                return msg.content, tool_calls
            except Exception as exc:
                last_error = exc
                if attempt == self._max_retries:
                    break
        raise LlmServiceError("大模型工具调用失败，请检查网络、模型配置或 API Key。") from last_error


class EmbeddingClient:
    """调用 DashScope / 兼容端点生成文本向量 Embedding"""

    def __init__(self, api_key: str, model: str = "text-embedding-v3", base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1", timeout: float = 30.0, max_retries: int = 2) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise LlmServiceError("LLM_API_KEY 未配置，无法生成 Embedding。")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LlmServiceError("缺少 openai 依赖，请由组长在 requirements 中添加。") from exc
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url, timeout=self._timeout)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本向量；单文本可传 [text]"""
        client = self._ensure_client()
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = client.embeddings.create(model=self._model, input=texts)
                return [d.embedding for d in response.data]
            except Exception as exc:
                last_error = exc
                if attempt == self._max_retries:
                    break
        raise LlmServiceError(f"Embedding 服务调用失败: {last_error}") from last_error
