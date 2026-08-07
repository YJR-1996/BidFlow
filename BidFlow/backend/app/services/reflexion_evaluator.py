"""Reflexion 质量评估服务：对生成的响应做 LLM 质量门。

设计要点：
- 只做"质量门"，不阻断主流程：任何失败（LLM 不可用 / JSON 解析失败 / 缺字段）
  一律视为"通过"（passed=True），避免评估器故障把本来可用的响应卡死。
- 评估标准刻意偏宽：只拦实质不达标（答非所问 / 关键条款整条遗漏 / 无支撑编造），
  避免过度重写导致成本膨胀。
- 与 batch_task_service 解耦：本服务只接收纯数据，不碰 DB，便于单测。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.config import settings
from app.services.llm_client import OpenAIChatClient
from app.services.prompt_templates import (
    build_reflexion_evaluate_messages,
    build_reflexion_refine_messages,
)

logger = logging.getLogger(__name__)


@dataclass
class ReflexionVerdict:
    """一次质量评估的结论。"""
    passed: bool
    feedback: str = ""
    missing_points: list[str] = field(default_factory=list)


class ReflexionEvaluator:
    """响应质量评估器：LLM 判断响应是否充分满足招标要求。"""

    def __init__(self, llm_client: Optional[OpenAIChatClient] = None):
        self._llm_client = llm_client

    def _client(self) -> Optional[OpenAIChatClient]:
        if self._llm_client is not None:
            return self._llm_client
        if not settings.DASHSCOPE_API_KEY:
            return None
        return OpenAIChatClient(
            api_key=settings.DASHSCOPE_API_KEY,
            model=settings.LLM_MODEL_NAME,
        )

    def evaluate(
        self,
        requirement_content: str,
        response_content: str,
        sources: list[dict[str, Any]],
    ) -> ReflexionVerdict:
        """评估响应是否达标。

        任何异常（无 Key / LLM 失败 / JSON 非法 / 字段缺失）都返回 passed=True，
        保证评估器永远不阻断生成链路。
        """
        if not response_content or not response_content.strip():
            return ReflexionVerdict(passed=False, feedback="响应内容为空", missing_points=["响应为空，无法通过质量门"])

        client = self._client()
        if client is None:
            return ReflexionVerdict(passed=True)  # 无 LLM 可用 → 放行

        try:
            messages = build_reflexion_evaluate_messages(requirement_content, response_content, sources)
            data = client.chat_json(messages)
            passed = bool(data.get("passed", True))
            feedback = str(data.get("feedback", "") or "")
            missing = data.get("missing_points") or []
            if not isinstance(missing, list):
                missing = []
            missing = [str(m) for m in missing][:5]
            return ReflexionVerdict(passed=passed, feedback=feedback, missing_points=missing)
        except Exception as e:
            logger.warning("[reflexion] evaluate failed, treat as passed: %s", e)
            return ReflexionVerdict(passed=True)

    def refine(
        self,
        requirement_content: str,
        draft_content: str,
        sources: list[dict[str, Any]],
        feedback: str,
        missing_points: list[str],
    ) -> Optional[str]:
        """基于评估反馈重写响应草稿。失败返回 None（保留原草稿）。"""
        client = self._client()
        if client is None:
            return None
        try:
            messages = build_reflexion_refine_messages(
                requirement_content, draft_content, sources, feedback, missing_points,
            )
            refined = client.chat(messages).strip()
            return refined or None
        except Exception as e:
            logger.warning("[reflexion] refine failed, keep original draft: %s", e)
            return None


reflexion_evaluator = ReflexionEvaluator()
