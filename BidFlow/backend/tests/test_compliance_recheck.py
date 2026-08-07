"""compliance_recheck 服务层测试：轻量规则核查闭环

覆盖：
- 无需求短路
- 无响应 → 生成规则 issue（P0 资料缺失）
- 补响应（内容 + source_refs + 完成态）→ 对应 issue 消失（remediate 闭环核心）
- 保留 semantic 来源与已处理 issue（H2 契约）
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.db.base import Base  # noqa: E402
from app.models.bid_project import BidProject  # noqa: E402
from app.models.requirement import Requirement  # noqa: E402
from app.models.response import Response as BidResponse  # noqa: E402
from app.models.compliance_issue import ComplianceIssue  # noqa: E402

from app.services.compliance_recheck import recheck_rule_issues  # noqa: E402
from app.models.match_analysis import MatchAnalysisRun, MatchAnalysisDetail  # noqa: E402


@pytest.fixture
def db_session():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    yield session
    session.close()
    engine.dispose()
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except PermissionError:
        pass


def _make_project(db, name="测试项目"):
    p = BidProject(name=name, owner_id="u1", status="进行中")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_requirement(db, project_id, content="投标人须提供有效的营业执照", category="资格", priority="P0"):
    r = Requirement(
        project_id=project_id,
        content=content,
        category=category,
        priority=priority,
        status="未处理",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _rule_codes(result: dict) -> set:
    return {i["rule_code"] for i in result["issues"]}


class TestRecheckRuleIssues:
    def test_no_requirements_returns_error(self, db_session):
        """无需求项时返回 error，不抛异常"""
        result = recheck_rule_issues(999, db_session)
        assert "error" in result

    def test_missing_response_produces_p0_source_missing(self, db_session):
        """P0 需求无响应 → 规则引擎报 P0_SOURCE_MISSING"""
        p = _make_project(db_session)
        _make_requirement(db_session, p.id)

        result = recheck_rule_issues(p.id, db_session)

        assert result["checked"] == 1
        assert result["rule_issue_count"] >= 1
        assert "P0_SOURCE_MISSING" in _rule_codes(result)

    def test_response_completed_clears_p0_issue(self, db_session):
        """闭环核心：补上「内容 + 可引用资料 + 完成态」后重跑，P0 issue 应消失"""
        p = _make_project(db_session)
        req = _make_requirement(db_session, p.id)
        recheck_rule_issues(p.id, db_session)
        assert db_session.query(ComplianceIssue).filter(
            ComplianceIssue.requirement_id == req.id
        ).count() >= 1

        # 补响应：内容 + source_refs（json.dumps 产物）+ 完成态
        db_session.add(BidResponse(
            requirement_id=req.id,
            ai_content="我方具备有效的营业执照，见附件扫描件。",
            status="completed",
            source_refs=json.dumps([
                {"content": "营业执照", "filename": "license.pdf", "source_ref": "p1", "score": 0.95}
            ], ensure_ascii=False),
        ))
        req.status = "已完成"
        db_session.commit()

        result = recheck_rule_issues(p.id, db_session)
        assert "P0_SOURCE_MISSING" not in _rule_codes(result)
        assert "P0_RESPONSE_MISSING" not in _rule_codes(result)

        remaining = db_session.query(ComplianceIssue).filter(
            ComplianceIssue.requirement_id == req.id
        ).all()
        assert all(i.rule_code not in ("P0_SOURCE_MISSING", "P0_RESPONSE_MISSING") for i in remaining)

    def test_preserves_semantic_and_processed(self, db_session):
        """轻量核查保留 semantic 来源与已处理 issue（H2 契约），只重建规则引擎未处理部分"""
        p = _make_project(db_session)
        req = _make_requirement(db_session, p.id)
        db_session.add(ComplianceIssue(
            project_id=p.id, requirement_id=req.id, level="高",
            rule_code="SEMANTIC_TEST", description="语义风险", suggestion="请检查",
            status="未处理", source="semantic",
        ))
        db_session.add(ComplianceIssue(
            project_id=p.id, requirement_id=req.id, level="高",
            rule_code="OLD_RULE", description="旧规则问题", suggestion="已人工处理",
            status="已处理", source="rule",
        ))
        db_session.commit()

        recheck_rule_issues(p.id, db_session)

        remains = db_session.query(ComplianceIssue).filter(
            ComplianceIssue.project_id == p.id
        ).all()
        codes = {i.rule_code for i in remains}
        assert "SEMANTIC_TEST" in codes   # 语义保留
        assert "OLD_RULE" in codes        # 已处理保留

    def test_latest_response_wins_over_old_pending_review(self, db_session):
        """L13：同一需求存在多条响应时，只取最新一条（id 降序）。
        历史遗留场景：旧响应 pending_review + 新响应 approved → 必须按 approved 判定，
        否则对已批准的 P0 误报「P0 响应项尚未完成」（与前端显示矛盾）。"""
        p = _make_project(db_session)
        req = _make_requirement(db_session, p.id)  # P0
        refs = json.dumps([{"content": "营业执照", "filename": "license.pdf", "source_ref": "p1", "score": 0.95}])

        # 旧响应：有内容+引用，但状态 pending_review（先插入，id 小）
        db_session.add(BidResponse(
            requirement_id=req.id,
            ai_content="旧版本响应内容（待评审）",
            status="pending_review",
            source_refs=refs,
        ))
        db_session.flush()
        # 新响应：approved（后插入，id 大）
        db_session.add(BidResponse(
            requirement_id=req.id,
            ai_content="最新版响应内容（已批准）",
            status="approved",
            source_refs=refs,
        ))
        db_session.commit()

        result = recheck_rule_issues(p.id, db_session)
        codes = _rule_codes(result)
        assert "P0_RESPONSE_MISSING" not in codes
        assert "P0_SOURCE_MISSING" not in codes

    def test_unmatched_with_source_refs_flags_stale(self, db_session):
        """L14：响应有 source_refs 且状态 approved，但最新比对分析显示未匹配（has_match=false）
        → 引用资料可能失效（RESPONSE_SOURCE_STALE, medium）。
        这是老板在截图2里看到「未匹配但合规报告无风险」的根因。"""
        p = _make_project(db_session)
        # 普通优先级（P2，避免 P0_RESPONSE_MISSING/P0_SOURCE_MISSING 抢占判定）
        req = _make_requirement(db_session, p.id, content="提供仓储与配送能力", category="商务", priority="P2")
        refs = json.dumps([{"content": "配送案例", "filename": "case.pdf", "source_ref": "p1", "score": 0.8}])

        # 响应有内容 + source_refs + approved 状态（按现行规则本应"通过"）
        db_session.add(BidResponse(
            requirement_id=req.id,
            ai_content="我方在采购人所在地设有仓储与配送点，保证 15 天内到货。",
            status="approved",
            source_refs=refs,
        ))
        db_session.commit()

        # 插入最新一次比对分析：此需求 has_match=False（未匹配）
        run = MatchAnalysisRun(project_id=p.id)
        db_session.add(run)
        db_session.flush()
        db_session.add(MatchAnalysisDetail(
            run_id=run.id, requirement_id=req.id, has_match=False,
        ))
        db_session.commit()

        result = recheck_rule_issues(p.id, db_session)
        codes = _rule_codes(result)
        assert "RESPONSE_SOURCE_STALE" in codes
        # 应写入 compliance_issues 表（medium）
        issue = db_session.query(ComplianceIssue).filter(
            ComplianceIssue.project_id == p.id,
            ComplianceIssue.rule_code == "RESPONSE_SOURCE_STALE",
        ).first()
        assert issue is not None
        assert issue.level == "中"

    def test_matched_with_source_refs_no_stale_issue(self, db_session):
        """L14 反向：响应有 source_refs 且最新比对分析显示已匹配 → 不报 STALE"""
        p = _make_project(db_session)
        req = _make_requirement(db_session, p.id, content="仓储配送", category="商务", priority="P2")
        refs = json.dumps([{"content": "案例", "filename": "f.pdf", "source_ref": "p1", "score": 0.8}])
        db_session.add(BidResponse(
            requirement_id=req.id, ai_content="我方具备...", status="approved", source_refs=refs,
        ))
        db_session.commit()
        run = MatchAnalysisRun(project_id=p.id)
        db_session.add(run)
        db_session.flush()
        db_session.add(MatchAnalysisDetail(
            run_id=run.id, requirement_id=req.id, has_match=True,
        ))
        db_session.commit()

        result = recheck_rule_issues(p.id, db_session)
        codes = _rule_codes(result)
        assert "RESPONSE_SOURCE_STALE" not in codes

    def test_stale_p0_escalates_to_high(self, db_session):
        """L14 增强：P0 优先级 + 未匹配 → RESPONSE_SOURCE_STALE 升级为 high（资格类否决项被无效引用等同被否决）"""
        p = _make_project(db_session)
        req = _make_requirement(db_session, p.id, content="否决项", category="资格", priority="P0")
        refs = json.dumps([{"content": "营业执照", "filename": "f.pdf", "source_ref": "p1", "score": 0.8}])
        db_session.add(BidResponse(
            requirement_id=req.id, ai_content="我方具备...", status="approved", source_refs=refs,
        ))
        db_session.commit()
        run = MatchAnalysisRun(project_id=p.id)
        db_session.add(run)
        db_session.flush()
        db_session.add(MatchAnalysisDetail(run_id=run.id, requirement_id=req.id, has_match=False))
        db_session.commit()

        recheck_rule_issues(p.id, db_session)
        issue = db_session.query(ComplianceIssue).filter(
            ComplianceIssue.project_id == p.id,
            ComplianceIssue.rule_code == "RESPONSE_SOURCE_STALE",
        ).first()
        assert issue is not None
        assert issue.level == "高"
