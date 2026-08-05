import logging

from app.agents.base import BaseAgent, WorkflowContext

logger = logging.getLogger(__name__)


class RAGAgent(BaseAgent):
    """RAG/生 成 Agent：取自须生成响应的需求 ID，调 batch_task_service.start_batch，把 task_id 写到 ctx.retrieval_task_id。"""

    name = "rag"

    def run(self, ctx: WorkflowContext, db) -> WorkflowContext:
        from app.models.requirement import Requirement
        from app.services.batch_task_service import batch_task_service

        # 找项目下所有"未生成响应"的需求
        # 排除已由主 UI 处理的需求（待评审/已完成），避免重复生成
        req_ids = [
            row[0]
            for row in db.query(Requirement.id)
            .filter(
                Requirement.project_id == ctx.project_id,
                Requirement.status.notin_(["待评审", "已完成", "completed"]),
            )
            .all()
        ]

        task_id = None
        if req_ids:
            task_id = batch_task_service.start_batch(
                project_id=ctx.project_id,
                requirement_ids=req_ids,
                owner_id=ctx.owner_id,
            )
            logger.info(
                "[RAGAgent] project=%d started batch task_id=%s requirements=%d",
                ctx.project_id, task_id, len(req_ids),
            )
        else:
            logger.info("[RAGAgent] project=%d no pending requirements", ctx.project_id)

        # 这里不做等待；批处理任务是逐步递进写的，由 run-workflow 之外的状态查看接口查看
        # 编排侧只需要知道已有批处理 task_id 即可
        ctx.retrieval_task_id = task_id
        # 注意：stages_done 由 Orchestrator 统一追加，agent 内不再重复 append
        return ctx
