"""辅助需求生成服务

基于已抽取的招标需求项，调用 LLM 派生/补全可编辑的辅助需求项：
- 隐性合规点、常见投标易漏项、资格衍生要求等
- 新增项标记 source='ai_aux'，不覆盖 parse_tender_document 已产出的解析项
- LLM 失败时降级返回空列表 + 日志告警
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.requirement import Requirement
from app.services.llm_client import OpenAIChatClient, LlmServiceError
from app.services.prompt_templates import build_aux_requirement_messages

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"资格", "商务", "技术", "评分", "其他"}
VALID_PRIORITIES = {"P0", "P1", "P2"}


class AuxiliaryRequirementService:
    """辅助需求生成服务（LLM 派生）"""

    def __init__(self):
        self._chat_client: Optional[OpenAIChatClient] = None

    def _get_chat_client(self) -> Optional[OpenAIChatClient]:
        if self._chat_client is None:
            api_key = settings.DASHSCOPE_API_KEY
            if not api_key:
                logger.warning("[aux_req] DASHSCOPE_API_KEY not configured, LLM unavailable")
                return None
            self._chat_client = OpenAIChatClient(
                api_key=api_key,
                model=settings.LLM_MODEL_NAME,
            )
        return self._chat_client

    def generate(
        self,
        db: Session,
        project_id: int,
        tender_document_id: Optional[int] = None,
        max_items: int = 10,
    ) -> list[Requirement]:
        """基于已解析的需求项，生成辅助需求

        Args:
            db: 数据库会话
            project_id: 项目 ID
            tender_document_id: 招标文件 ID（可选）
            max_items: 最多生成条数

        Returns:
            本次生成的辅助需求列表
        """
        # 1. 防重复：查询是否已有 ai_aux 项
        existing = self._check_existing_ai_aux(db, project_id, tender_document_id)
        if existing:
            return existing

        # 2. 查询已解析的需求项作为 LLM 输入
        parsed_reqs = self._fetch_parsed_reqs(db, project_id, tender_document_id)
        if not parsed_reqs:
            logger.warning("[aux_req] no parsed requirements found for project=%d", project_id)
            return []

        # 3. 构造 LLM 输入
        input_reqs = [
            {"content": r.content, "category": r.category, "priority": r.priority}
            for r in parsed_reqs
        ]

        # 4. 调用 LLM
        chat_client = self._get_chat_client()
        if chat_client is None:
            logger.warning("[aux_req] LLM client unavailable, returning empty list for project=%d", project_id)
            return []

        try:
            raw_result = self._call_llm(chat_client, input_reqs, max_items)
            aux_items = self._parse_llm_result(raw_result, max_items)
        except LlmServiceError as e:
            logger.warning("[aux_req] LLM call failed: %s, returning empty list", e)
            return []
        except Exception as e:
            logger.warning("[aux_req] unexpected error during generation: %s, returning empty list", e)
            return []

        if not aux_items:
            logger.info("[aux_req] LLM returned no auxiliary items for project=%d", project_id)
            return []

        # 5. 写入数据库
        created = self._write_aux_requirements(db, project_id, tender_document_id, aux_items)
        logger.info("[aux_req] generated %d auxiliary requirements for project=%d", len(created), project_id)
        return created

    def _check_existing_ai_aux(
        self,
        db: Session,
        project_id: int,
        tender_document_id: Optional[int],
    ) -> Optional[list[Requirement]]:
        """查询是否已存在 ai_aux 项，存在则直接返回"""
        query = db.query(Requirement).filter(
            Requirement.project_id == project_id,
            Requirement.source == "ai_aux",
        )
        if tender_document_id:
            query = query.filter(Requirement.tender_document_id == tender_document_id)
        existing = query.all()
        if existing:
            logger.info(
                "[aux_req] existing ai_aux items found: project=%d, count=%d, skipping LLM",
                project_id, len(existing)
            )
            return existing
        return None

    def _fetch_parsed_reqs(
        self,
        db: Session,
        project_id: int,
        tender_document_id: Optional[int],
    ) -> list[Requirement]:
        """查询已解析的需求项"""
        query = db.query(Requirement).filter(
            Requirement.project_id == project_id,
            Requirement.source == "parsed",
        )
        if tender_document_id:
            query = query.filter(Requirement.tender_document_id == tender_document_id)
        return query.order_by(Requirement.priority).all()

    def _call_llm(
        self,
        chat_client: OpenAIChatClient,
        input_reqs: list[dict],
        max_items: int,
    ) -> dict:
        """调用 LLM 生成辅助需求"""
        messages = build_aux_requirement_messages(input_reqs, max_items=max_items)
        return chat_client.chat_json(messages)

    def _write_aux_requirements(
        self,
        db: Session,
        project_id: int,
        tender_document_id: Optional[int],
        items: list[dict],
    ) -> list[Requirement]:
        """将生成的辅助需求写入数据库"""
        created = []
        for item in items:
            req = Requirement(
                project_id=project_id,
                tender_document_id=tender_document_id,
                category=item.get("category", "其他"),
                content=item.get("content", ""),
                source_text="",
                source_ref="ai_aux",
                source="ai_aux",
                priority=item.get("priority", "P2"),
                status="未处理",
                risk_level=item.get("risk_level", "低"),
            )
            db.add(req)
            created.append(req)

        db.commit()
        for r in created:
            db.refresh(r)
        return created

    @staticmethod
    def _parse_llm_result(raw: dict, max_items: int) -> list[dict]:
        """解析 LLM 返回的 JSON，提取辅助需求项"""
        items = raw.get("requirements", [])
        if not isinstance(items, list):
            return []

        result = []
        for item in items[:max_items]:
            if not isinstance(item, dict):
                continue
            content = item.get("content", "").strip()
            if not content:
                continue
            category = item.get("category", "其他")
            if category not in VALID_CATEGORIES:
                category = "其他"
            priority = item.get("priority", "P2")
            if priority not in VALID_PRIORITIES:
                priority = "P2"
            result.append({
                "content": content,
                "category": category,
                "priority": priority,
                "risk_level": item.get("risk_level", "低"),
                "source": "ai_aux",
            })
        return result


# 全局单例
auxiliary_requirement_service = AuxiliaryRequirementService()