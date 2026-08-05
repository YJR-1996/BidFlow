from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from app.core.config import settings


@dataclass
class WorkflowContext:
    """编排工作流上下文，包含各阶段共享状态。"""
    project_id: int
    owner_id: str
    stages_done: List[str] = field(default_factory=list)
    requirements: List[Dict] = field(default_factory=list)
    retrieval_task_id: Optional[str] = None
    compliance_issues: List[Dict] = field(default_factory=list)
    human_review_required: bool = False
    review_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """工具注册表——为所有 Agent 提供统一的 LLM、检索等能力入口。"""

    def __init__(self):
        from app.core.config import settings as _settings
        from app.services.retrieval_service import retrieval_service as _retrieval_service
        self.settings = _settings
        self.retrieval_service = _retrieval_service

    def llm(self):
        """返回 LLM 客户端（在 need 时 lazy 实例化）。"""
        from app.services.llm_client import OpenAIChatClient
        return OpenAIChatClient(
            api_key=self.settings.DASHSCOPE_API_KEY,
            model=self.settings.LLM_MODEL_NAME,
        )


class BaseAgent:
    """所有 Agent 的基类。"""
    name = "base"

    def __init__(self, tools: ToolRegistry):
        self.tools = tools

    def run(self, ctx: WorkflowContext, db):
        raise NotImplementedError
