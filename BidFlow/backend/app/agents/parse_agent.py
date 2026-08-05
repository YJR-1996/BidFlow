import logging
from typing import List, Dict

from app.agents.base import BaseAgent, WorkflowContext

logger = logging.getLogger(__name__)


class ParseAgent(BaseAgent):
    """招标文件解析 Agent：遍历项目未解析 TenderDocument，复用 document_parser + TenderRequirementExtractorService 写 requirements，填 ctx.requirements。"""

    name = "parse"

    def run(self, ctx: WorkflowContext, db) -> WorkflowContext:
        from sqlalchemy.orm import joinedload
        from app.models.bid_project import BidProject
        from app.models.tender_document import TenderDocument
        from app.models.requirement import Requirement
        from app.services.document_parser import DocumentParserService
        from app.services.tender_requirement_extractor import TenderRequirementExtractorService

        parser = DocumentParserService()
        extractor = TenderRequirementExtractorService()

        # 查询项目下未解析的招标文件
        docs = (
            db.query(TenderDocument)
            .filter(
                TenderDocument.project_id == ctx.project_id,
                TenderDocument.status != "parsed",
            )
            .all()
        )

        all_reqs: List[Requirement] = []
        for doc in docs:
            try:
                # 1. 解析文件
                paragraphs = parser.parse(doc.file_path, doc.file_type)
                # 2. 抽取需求并写库
                reqs = extractor.extract(
                    db=db,
                    project_id=ctx.project_id,
                    tender_document_id=doc.id,
                    parsed_paragraphs=paragraphs,
                )
                # 3. 更新文档状态
                doc.status = "parsed"
                db.add(doc)
                all_reqs.extend(reqs)
                logger.info(
                    "[ParseAgent] document_id=%s extracted %d requirements",
                    doc.id, len(reqs),
                )
            except Exception as exc:
                logger.exception("[ParseAgent] document_id=%s failed: %s", doc.id, exc)
                continue

        db.commit()

        ctx.requirements = [
            {
                "id": r.id,
                "content": r.content,
                "category": r.category,
                "priority": r.priority,
                "status": r.status,
                "source_ref": r.source_ref,
            }
            for r in all_reqs
        ]
        # 注意：stages_done 由 Orchestrator 统一追加，agent 内不再重复 append
        logger.info("[ParseAgent] done project=%d, requirements=%d", ctx.project_id, len(ctx.requirements))
        return ctx
