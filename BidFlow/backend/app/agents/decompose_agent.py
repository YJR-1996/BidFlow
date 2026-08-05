import logging

from app.agents.base import BaseAgent, WorkflowContext

logger = logging.getLogger(__name__)


class DecomposeAgent(BaseAgent):
    """辅助需求分解 Agent：调用 auxiliary_requirement_service.generate(db, project_id)。"""

    name = "decompose"

    def run(self, ctx: WorkflowContext, db) -> WorkflowContext:
        from app.services.auxiliary_requirement_service import auxiliary_requirement_service

        created = auxiliary_requirement_service.generate(db=db, project_id=ctx.project_id)
        new_items = []
        for req in created:
            new_items.append({
                "id": req.id,
                "content": req.content,
                "category": req.category,
                "priority": req.priority,
                "status": req.status,
                "source_ref": req.source_ref,
            })
        ctx.metadata["decomposed_count"] = len(new_items)
        # 注意：stages_done 由 Orchestrator 统一追加，agent 内不再重复 append
        logger.info(
            "[DecomposeAgent] project=%d generated %d auxiliary requirements",
            ctx.project_id, len(new_items),
        )
        return ctx
