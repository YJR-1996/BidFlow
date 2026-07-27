"""基于已检索资料生成响应草稿；不负责检索和数据库写入。"""

from dataclasses import dataclass
from typing import Any, Protocol

from app.services.prompt_templates import build_response_messages


class ChatClient(Protocol):
    def chat(self, messages: list[dict[str, str]]) -> str: ...


@dataclass(frozen=True)
class GenerationResult:
    content: str
    sources: list[dict[str, Any]]
    status: str
    message: str


class ResponseGenerationService:
    def __init__(self, llm_client: ChatClient) -> None:
        self._llm_client = llm_client

    def generate(self, requirement: dict[str, Any], sources: list[dict[str, Any]]) -> GenerationResult:
        if not sources:
            return GenerationResult("待人工补充：未检索到可引用的企业资料。", [], "needs_manual", "缺少可引用资料，未调用大模型。")
        messages = build_response_messages(requirement["content"], sources)
        content = self._llm_client.chat(messages).strip()
        if not content:
            return GenerationResult("待人工补充：模型未返回有效草稿。", sources, "needs_manual", "模型未返回有效内容。")
        return GenerationResult(content, sources, "pending_review", "草稿已生成，等待人工审核。")
