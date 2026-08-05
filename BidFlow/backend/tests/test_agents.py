"""agents 编排层测试

覆盖 Orchestrator 与各 Agent 的核心逻辑：
- RAGAgent：需求状态过滤（排除待评审/已完成/completed）
- ComplianceAgent：高风险触发 human_review_required
- DecomposeAgent：调用辅助需求生成
- Orchestrator：阶段顺序执行与中断
- build_snapshots_from_requirements：响应快照构建
"""
import json
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.bid_project import BidProject
from app.models.user import User
from app.models.requirement import Requirement
from app.models.response import Response as BidResponse
from app.agents.base import WorkflowContext, ToolRegistry


@pytest.fixture
def agent_db():
    """内存 SQLite + 同步 session，用于 agent 测试"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(User(id="u1", username="agent_user", password_hash="x"))
    db.add(BidProject(id=1, name="agent项目", owner_id="u1"))
    db.commit()
    yield db
    db.close()
    engine.dispose()


def _add_requirement(db, rid, status="未处理", priority="P2", content="需求内容"):
    db.add(Requirement(
        id=rid, project_id=1, content=content, priority=priority,
        status=status, category="技术",
    ))
    db.commit()


# ---------------------------------------------------------------------------
# RAGAgent：状态过滤
# ---------------------------------------------------------------------------
class TestRAGAgent:
    def test_excludes_processed_statuses(self, agent_db):
        """待评审/已完成/completed 状态的需求不应纳入批量生成"""
        from app.agents.rag_agent import RAGAgent
        _add_requirement(agent_db, 1, status="待评审")
        _add_requirement(agent_db, 2, status="已完成")
        _add_requirement(agent_db, 3, status="completed")
        _add_requirement(agent_db, 4, status="未处理")  # 仅这条应被处理

        agent = RAGAgent(ToolRegistry())
        ctx = WorkflowContext(project_id=1, owner_id="u1")

        with patch("app.services.batch_task_service.batch_task_service.start_batch", return_value="task_x") as mock_start:
            result = agent.run(ctx, agent_db)

        # 仅需求 4 被传入 start_batch
        mock_start.assert_called_once()
        call_kwargs = mock_start.call_args
        assert 4 in call_kwargs.kwargs.get("requirement_ids", call_kwargs.args[1] if len(call_kwargs.args) > 1 else [])
        assert 1 not in (call_kwargs.kwargs.get("requirement_ids", []))
        assert result.retrieval_task_id == "task_x"

    def test_no_pending_requirements_skips_batch(self, agent_db):
        """全部已处理时不启动批量任务"""
        from app.agents.rag_agent import RAGAgent
        _add_requirement(agent_db, 1, status="待评审")

        agent = RAGAgent(ToolRegistry())
        ctx = WorkflowContext(project_id=1, owner_id="u1")

        with patch("app.services.batch_task_service.batch_task_service.start_batch") as mock_start:
            result = agent.run(ctx, agent_db)

        mock_start.assert_not_called()
        assert result.retrieval_task_id is None


# ---------------------------------------------------------------------------
# ComplianceAgent：高风险中断
# ---------------------------------------------------------------------------
class TestComplianceAgent:
    def test_high_risk_triggers_human_review(self, agent_db):
        """存在 P0 空响应（高风险）时应触发 human_review_required"""
        from app.agents.compliance_agent import ComplianceAgent
        _add_requirement(agent_db, 1, status="未处理", priority="P0", content="必须提供营业执照")

        agent = ComplianceAgent(ToolRegistry())
        ctx = WorkflowContext(project_id=1, owner_id="u1")

        result = agent.run(ctx, agent_db)
        assert result.human_review_required is True
        assert "高风险" in result.review_reason
        assert len(result.compliance_issues) > 0

    def test_no_high_risk_no_review(self, agent_db):
        """无高风险时不触发人工审核"""
        from app.agents.compliance_agent import ComplianceAgent
        _add_requirement(agent_db, 1, status="已完成", priority="P1", content="普通需求")
        db_add_response(agent_db, requirement_id=1, content="已有响应", source_refs='[{"content":"x"}]')

        agent = ComplianceAgent(ToolRegistry())
        ctx = WorkflowContext(project_id=1, owner_id="u1")

        result = agent.run(ctx, agent_db)
        assert result.human_review_required is False


def db_add_response(db, requirement_id, content="响应", source_refs=None):
    db.add(BidResponse(
        requirement_id=requirement_id,
        ai_content=content,
        source_refs=source_refs,
        status="pending_review",
    ))
    db.commit()


# ---------------------------------------------------------------------------
# build_snapshots_from_requirements
# ---------------------------------------------------------------------------
class TestBuildSnapshots:
    def test_builds_snapshots_with_response_data(self, agent_db):
        from app.agents.compliance_agent import build_snapshots_from_requirements
        _add_requirement(agent_db, 1, status="未处理", priority="P1")
        db_add_response(agent_db, requirement_id=1, content="响应内容")

        requirements = [{"id": 1, "content": "需求", "priority": "P1", "status": "未处理"}]
        snapshots = build_snapshots_from_requirements(agent_db, requirements)

        assert len(snapshots) == 1
        assert snapshots[0].response_content == "响应内容"
        assert snapshots[0].status == "pending_review"

    def test_builds_snapshots_without_responses(self, agent_db):
        from app.agents.compliance_agent import build_snapshots_from_requirements
        _add_requirement(agent_db, 1, status="未处理")

        requirements = [{"id": 1, "content": "需求", "priority": "P2", "status": "未处理"}]
        snapshots = build_snapshots_from_requirements(agent_db, requirements)

        assert snapshots[0].response_content == ""
        assert snapshots[0].status == "未处理"

    def test_empty_requirements_returns_empty(self, agent_db):
        from app.agents.compliance_agent import build_snapshots_from_requirements
        assert build_snapshots_from_requirements(agent_db, []) == []


# ---------------------------------------------------------------------------
# DecomposeAgent
# ---------------------------------------------------------------------------
class TestDecomposeAgent:
    def test_decompose_calls_auxiliary_service(self, agent_db):
        from app.agents.decompose_agent import DecomposeAgent
        agent = DecomposeAgent(ToolRegistry())
        ctx = WorkflowContext(project_id=1, owner_id="u1")

        mock_req = MagicMock()
        mock_req.id = 99
        mock_req.content = "辅助需求"
        mock_req.category = "技术"
        mock_req.priority = "P2"
        mock_req.status = "未处理"
        mock_req.source_ref = "ai_aux"

        with patch("app.services.auxiliary_requirement_service.auxiliary_requirement_service.generate", return_value=[mock_req]):
            result = agent.run(ctx, agent_db)

        assert result.metadata["decomposed_count"] == 1
        # stages_done 由 Orchestrator 统一追加（agent 内不重复 append）——单测直调 agent.run 时不应断言它
        # （Orchestrator 的 stage 流转由 test_workflow_agents.py / TestOrchestrator 覆盖）

    def test_decompose_no_items_generated(self, agent_db):
        from app.agents.decompose_agent import DecomposeAgent
        agent = DecomposeAgent(ToolRegistry())
        ctx = WorkflowContext(project_id=1, owner_id="u1")

        with patch("app.services.auxiliary_requirement_service.auxiliary_requirement_service.generate", return_value=[]):
            result = agent.run(ctx, agent_db)

        assert result.metadata["decomposed_count"] == 0


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class TestOrchestrator:
    def test_invalid_start_stage_raises(self, agent_db):
        from app.agents.orchestrator import Orchestrator
        ctx = WorkflowContext(project_id=1, owner_id="u1")
        with pytest.raises(ValueError):
            Orchestrator().run(ctx, agent_db, start_stage="invalid")

    def test_stops_on_human_review(self, agent_db):
        """compliance 阶段触发 human_review 时应中断，不继续后续阶段"""
        from app.agents.orchestrator import Orchestrator
        _add_requirement(agent_db, 1, status="未处理", priority="P0")

        ctx = WorkflowContext(project_id=1, owner_id="u1")
        orch = Orchestrator()

        # 从 compliance 开始（跳过 parse/decompose/rag）
        with patch("app.services.batch_task_service.batch_task_service.start_batch", return_value="t"):
            result = orch.run(ctx, agent_db, start_stage="compliance")

        assert result.human_review_required is True
        assert "compliance" in result.stages_done

    def test_run_from_rag_stage(self, agent_db):
        """从 rag 阶段开始应执行 rag + compliance"""
        from app.agents.orchestrator import Orchestrator
        _add_requirement(agent_db, 1, status="未处理", priority="P1")

        ctx = WorkflowContext(project_id=1, owner_id="u1")
        orch = Orchestrator()

        with patch("app.services.batch_task_service.batch_task_service.start_batch", return_value="t"):
            result = orch.run(ctx, agent_db, start_stage="rag")

        assert "rag" in result.stages_done
        assert result.retrieval_task_id == "t"


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------
class TestToolRegistry:
    def test_tool_registry_initializes(self):
        reg = ToolRegistry()
        assert reg.settings is not None
        assert reg.retrieval_service is not None

    def test_tool_registry_llm_returns_client(self):
        reg = ToolRegistry()
        with patch("app.services.llm_client.OpenAIChatClient") as mock_client:
            client = reg.llm()
            mock_client.assert_called_once()
