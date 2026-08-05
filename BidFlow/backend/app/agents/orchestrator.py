from app.agents.base import ToolRegistry, BaseAgent, WorkflowContext
from app.agents.parse_agent import ParseAgent
from app.agents.decompose_agent import DecomposeAgent
from app.agents.rag_agent import RAGAgent
from app.agents.compliance_agent import ComplianceAgent


class Orchestrator:
    """编排器：调用各 Agent 顺序执行，遇到 human_review_required 时提前终止并返回。"""

    STAGE_ORDER = ["parse", "decompose", "rag", "compliance"]

    def __init__(self):
        self.tools = ToolRegistry()
        self.agents = {
            "parse": ParseAgent(self.tools),
            "decompose": DecomposeAgent(self.tools),
            "rag": RAGAgent(self.tools),
            "compliance": ComplianceAgent(self.tools),
        }

    def run(
        self,
        ctx: WorkflowContext,
        db,
        start_stage: str = "parse",
    ) -> WorkflowContext:
        """从指定阶段开始顺序运行，若当前阶段触发人工审核则暂停并返回。
        此函数对 ctx 进行了原地修改（添加 stages_done、setting human_review_required 等）。
        """
        if start_stage not in self.STAGE_ORDER:
            raise ValueError(f"start_stage must be one of {self.STAGE_ORDER}")

        start_index = self.STAGE_ORDER.index(start_stage)

        for stage_name in self.STAGE_ORDER[start_index:]:
            agent: BaseAgent = self.agents[stage_name]
            logger = __import__("logging").getLogger(__name__)
            logger.info(
                "[Orchestrator] Running stage=%s on project=%d",
                stage_name,
                ctx.project_id,
            )
            new_ctx = agent.run(ctx, db)
            new_ctx.stages_done.append(stage_name)

            # 如果此时已有人工审核需求，立即中断后续 stage
            if new_ctx.human_review_required:
                break

            ctx = new_ctx

        return ctx
