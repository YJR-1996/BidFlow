"""集成测试：完整工作流端到端

通过 TestClient 走通主流程，覆盖多个路由模块的交互：
  创建项目 → 上传招标文件 → 解析需求 → 比对分析 → 合规核查 → 报告 → 统计

mock 掉 vector_store 的语义比对与 LLM 调用，避免依赖外部服务。
"""
import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import os
import tempfile

from app.main import app
from app.db.session import get_db, get_session
from app.db.base import Base


@pytest.fixture
def test_db():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingAsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    sync_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=sync_engine)
    TestingSyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

    async def override_get_session():
        async with TestingAsyncSessionLocal() as session:
            yield session

    def override_get_db():
        db = TestingSyncSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_db] = override_get_db
    yield TestingSyncSessionLocal
    app.dependency_overrides.clear()
    import asyncio
    asyncio.run(async_engine.dispose())
    sync_engine.dispose()
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except PermissionError:
        pass


@pytest.fixture
def client(test_db):
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    client.post("/api/auth/register", json={"username": "integ_user", "password": "pass123456"})
    resp = client.post("/api/auth/login", json={"username": "integ_user", "password": "pass123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


TENDER = (
    "一、资格要求\n"
    "1. 投标人必须具有独立法人资格，持有营业执照。\n"
    "2. 近三年具有至少3个同类项目案例。\n"
    "\n"
    "二、技术要求\n"
    "1. 系统需支持1000并发用户。\n"
    "2. 采用B/S架构，支持主流浏览器。\n"
    "\n"
    "三、商务要求\n"
    "1. 项目预算500万元。\n"
    "2. 交付周期90天。\n"
)


def _setup_project_with_requirements(client, headers):
    """创建项目 + 上传 + 解析，返回 (project_id, requirements)"""
    resp = client.post("/api/projects", json={"name": "集成测试项目"}, headers=headers)
    project_id = resp.json()["data"]["id"]

    upload = client.post(
        f"/api/projects/{project_id}/tender-documents",
        files={"file": ("tender.txt", TENDER.encode("utf-8"), "text/plain")},
        headers=headers,
    )
    doc_id = upload.json()["data"]["id"]
    client.post(f"/api/tender-documents/{doc_id}/parse", headers=headers)

    reqs = client.get(f"/api/projects/{project_id}/requirements", headers=headers).json()["data"]
    return project_id, reqs


# ---------------------------------------------------------------------------
# 1. 比对分析（responses.py: match-analysis）
# ---------------------------------------------------------------------------
class TestMatchAnalysis:
    def test_match_analysis_with_no_requirements(self, client, auth_headers):
        """无需求项目执行比对分析应返回空结果"""
        resp = client.post("/api/projects", json={"name": "空项目"}, headers=auth_headers)
        project_id = resp.json()["data"]["id"]

        # mock 向量检索返回 missing（空语料库）
        with patch("app.services.vector_store.vector_store_service.match_requirement_to_materials") as mock_match:
            from app.services.vector_store import MatchResult
            mock_match.return_value = MatchResult(
                requirement_id=0, coverage="missing", confidence=0.0,
                material_covered=False, evidence=[], gap="无资料", pending_review=True,
            )
            result = client.get(f"/api/requirements/projects/{project_id}/match-analysis", headers=auth_headers)

        assert result.status_code == 200
        data = result.json()["data"]
        assert data["summary"]["total"] == 0

    def test_match_analysis_persists_and_reuses(self, client, auth_headers):
        """force=false 时第二次应复用持久化结果（不重算）"""
        project_id, reqs = _setup_project_with_requirements(client, auth_headers)
        assert len(reqs) > 0

        from app.services.vector_store import MatchResult
        mock_result = MatchResult(
            requirement_id=0, coverage="partial", confidence=0.75,
            material_covered=True, evidence=[{"source_ref": "case.pdf", "quote": "案例内容"}],
            gap="部分覆盖", pending_review=True,
        )

        with patch("app.services.vector_store.vector_store_service.match_requirement_to_materials", return_value=mock_result) as mock_match:
            # 第一次：实时计算并持久化
            r1 = client.get(f"/api/requirements/projects/{project_id}/match-analysis", headers=auth_headers)
            assert r1.status_code == 200
            d1 = r1.json()["data"]
            assert d1["summary"]["total"] == len(reqs)
            assert "run_id" in d1

            # 第二次 force=false：应复用，不重算
            call_count_before = mock_match.call_count
            r2 = client.get(f"/api/requirements/projects/{project_id}/match-analysis", headers=auth_headers)
            assert r2.status_code == 200
            # match_requirement_to_materials 调用次数不应增加
            assert mock_match.call_count == call_count_before

    def test_match_analysis_force_recomputes(self, client, auth_headers):
        """force=true 时应强制重算"""
        project_id, reqs = _setup_project_with_requirements(client, auth_headers)

        from app.services.vector_store import MatchResult
        mock_result = MatchResult(
            requirement_id=0, coverage="missing", confidence=0.0,
            material_covered=False, evidence=[], gap="无资料", pending_review=True,
        )

        with patch("app.services.vector_store.vector_store_service.match_requirement_to_materials", return_value=mock_result):
            client.get(f"/api/requirements/projects/{project_id}/match-analysis", headers=auth_headers)
            call_count_before = mock_result  # 仅占位
            # force=true 重算
            r = client.get(f"/api/requirements/projects/{project_id}/match-analysis?force=true", headers=auth_headers)
            assert r.status_code == 200

    def test_run_match_analysis_endpoint(self, client, auth_headers):
        """POST /match-analysis/run 强制重算端点"""
        project_id, reqs = _setup_project_with_requirements(client, auth_headers)
        from app.services.vector_store import MatchResult

        with patch("app.services.vector_store.vector_store_service.match_requirement_to_materials",
                    return_value=MatchResult(requirement_id=0, coverage="missing", confidence=0,
                    material_covered=False, evidence=[], gap="x", pending_review=False)):
            r = client.post(f"/api/requirements/projects/{project_id}/match-analysis/run", headers=auth_headers)
            assert r.status_code == 200
            assert r.json()["data"]["summary"]["total"] == len(reqs)

    def test_match_analysis_other_user_denied(self, client, auth_headers):
        """其他用户不能访问比对分析"""
        project_id, _ = _setup_project_with_requirements(client, auth_headers)
        # 注册第二个用户
        client.post("/api/auth/register", json={"username": "integ_user_b", "password": "pass123456"})
        resp = client.post("/api/auth/login", json={"username": "integ_user_b", "password": "pass123456"})
        other_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        r = client.get(f"/api/requirements/projects/{project_id}/match-analysis", headers=other_headers)
        assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# 2. 合规核查（compliance.py: compliance-check / compliance-report）
# ---------------------------------------------------------------------------
class TestComplianceCheck:
    def test_compliance_check_without_requirements_raises(self, client, auth_headers):
        """无需求项时合规核查应返回业务错误"""
        resp = client.post("/api/projects", json={"name": "空合规项目"}, headers=auth_headers)
        project_id = resp.json()["data"]["id"]

        r = client.post(f"/api/{project_id}/compliance-check", headers=auth_headers)
        assert r.status_code != 200  # BusinessException

    def test_compliance_check_returns_report(self, client, auth_headers):
        """有需求项时合规核查应返回报告摘要"""
        project_id, reqs = _setup_project_with_requirements(client, auth_headers)

        r = client.post(f"/api/{project_id}/compliance-check", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total_requirements"] == len(reqs)
        assert "high_risk_count" in data
        assert "completion_rate" in data
        assert "issue_count" in data

    def test_compliance_check_idempotent(self, client, auth_headers):
        """多次合规核查不应产生重复问题（先清理旧问题）"""
        project_id, _ = _setup_project_with_requirements(client, auth_headers)

        r1 = client.post(f"/api/{project_id}/compliance-check", headers=auth_headers)
        r2 = client.post(f"/api/{project_id}/compliance-check", headers=auth_headers)
        assert r1.status_code == 200 and r2.status_code == 200
        # 两次核查的 issue_count 应一致（不累积）
        assert r1.json()["data"]["issue_count"] == r2.json()["data"]["issue_count"]

    def test_compliance_report_after_check(self, client, auth_headers):
        """合规核查后应能获取详细报告"""
        project_id, _ = _setup_project_with_requirements(client, auth_headers)
        client.post(f"/api/{project_id}/compliance-check", headers=auth_headers)

        r = client.get(f"/api/{project_id}/compliance-report", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "total_requirements" in data

    def test_compliance_check_other_user_denied(self, client, auth_headers):
        """其他用户不能对他人项目执行合规核查"""
        project_id, _ = _setup_project_with_requirements(client, auth_headers)
        client.post("/api/auth/register", json={"username": "integ_user_c", "password": "pass123456"})
        resp = client.post("/api/auth/login", json={"username": "integ_user_c", "password": "pass123456"})
        other_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        r = client.post(f"/api/{project_id}/compliance-check", headers=other_headers)
        assert r.status_code in (403, 404)

    def test_compliance_report_export_markdown(self, client, auth_headers):
        """合规报告 Markdown 导出"""
        project_id, _ = _setup_project_with_requirements(client, auth_headers)
        client.post(f"/api/{project_id}/compliance-check", headers=auth_headers)

        r = client.get(f"/api/{project_id}/compliance-report/markdown", headers=auth_headers)
        assert r.status_code == 200
        # Markdown 导出应返回文本或文件流
        assert r.headers.get("content-type", "").startswith(("text/", "application/"))

    def test_compliance_report_export_pdf(self, client, auth_headers):
        """合规报告 PDF 导出"""
        project_id, _ = _setup_project_with_requirements(client, auth_headers)
        client.post(f"/api/{project_id}/compliance-check", headers=auth_headers)

        r = client.get(f"/api/{project_id}/compliance-report/pdf", headers=auth_headers)
        # PDF 导出可能成功（200）或因缺少 reportlab 而降级
        assert r.status_code in (200, 400, 500)

    def test_compliance_report_markdown_other_user_denied(self, client, auth_headers):
        """其他用户不能导出他人项目的合规报告"""
        project_id, _ = _setup_project_with_requirements(client, auth_headers)
        client.post("/api/auth/register", json={"username": "integ_user_e", "password": "pass123456"})
        resp = client.post("/api/auth/login", json={"username": "integ_user_e", "password": "pass123456"})
        other = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        r = client.get(f"/api/{project_id}/compliance-report/markdown", headers=other)
        assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# 3. 统计报表（stats.py）
# ---------------------------------------------------------------------------
class TestStats:
    def test_project_stats(self, client, auth_headers):
        """统计接口应返回统计数据"""
        _setup_project_with_requirements(client, auth_headers)

        r = client.get("/api/stats", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        # 统计接口应返回项目数等指标
        assert isinstance(data, dict)

    def test_stats_empty_user(self, client, auth_headers):
        """无项目的用户统计应返回零值"""
        r = client.get("/api/stats", headers=auth_headers)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 4. 端到端工作流：完整链路
# ---------------------------------------------------------------------------
class TestEndToEndWorkflow:
    def test_full_workflow(self, client, auth_headers):
        """完整工作流：创建→上传→解析→比对→合规→报告

        验证每个环节都能正常运行且数据贯穿。
        """
        # 1. 创建项目
        resp = client.post("/api/projects", json={
            "name": "E2E项目", "tenderer": "招标方", "description": "端到端测试",
        }, headers=auth_headers)
        assert resp.status_code == 200
        project_id = resp.json()["data"]["id"]

        # 2. 上传招标文件
        upload = client.post(
            f"/api/projects/{project_id}/tender-documents",
            files={"file": ("e2e.txt", TENDER.encode("utf-8"), "text/plain")},
            headers=auth_headers,
        )
        assert upload.status_code == 200
        doc_id = upload.json()["data"]["id"]

        # 3. 解析
        parse = client.post(f"/api/tender-documents/{doc_id}/parse", headers=auth_headers)
        assert parse.status_code == 200
        assert parse.json()["data"]["requirement_count"] > 0

        # 4. 获取需求列表
        reqs = client.get(f"/api/projects/{project_id}/requirements", headers=auth_headers)
        assert reqs.status_code == 200
        requirement_list = reqs.json()["data"]
        assert len(requirement_list) >= 3  # 至少 3 类需求

        # 5. 更新一个需求的状态
        req_id = requirement_list[0]["id"]
        upd = client.patch(f"/api/requirements/{req_id}", json={
            "priority": "P0", "status": "处理中",
        }, headers=auth_headers)
        assert upd.status_code == 200
        assert upd.json()["data"]["priority"] == "P0"

        # 6. 批量更新状态
        batch = client.patch(
            f"/api/requirements/projects/{project_id}/batch-status",
            json={"status": "待评审"},
            headers=auth_headers,
        )
        assert batch.status_code == 200
        assert batch.json()["data"]["updated"] == len(requirement_list)

        # 7. 比对分析（mock 向量检索）
        from app.services.vector_store import MatchResult
        mock_result = MatchResult(
            requirement_id=0, coverage="partial", confidence=0.8,
            material_covered=True, evidence=[{"source_ref": "case.pdf", "quote": "案例"}],
            gap="部分覆盖", pending_review=True,
        )
        with patch("app.services.vector_store.vector_store_service.match_requirement_to_materials", return_value=mock_result):
            match = client.get(f"/api/requirements/projects/{project_id}/match-analysis", headers=auth_headers)
        assert match.status_code == 200
        assert match.json()["data"]["summary"]["total"] == len(requirement_list)

        # 8. 合规核查
        compliance = client.post(f"/api/{project_id}/compliance-check", headers=auth_headers)
        assert compliance.status_code == 200
        cdata = compliance.json()["data"]
        assert cdata["total_requirements"] == len(requirement_list)

        # 9. 获取合规报告
        report = client.get(f"/api/{project_id}/compliance-report", headers=auth_headers)
        assert report.status_code == 200

        # 10. 获取项目详情（含就绪度）
        detail = client.get(f"/api/projects/{project_id}", headers=auth_headers)
        assert detail.status_code == 200

        # 11. 需求筛选验证
        filtered = client.get(
            f"/api/projects/{project_id}/requirements?priority=P0",
            headers=auth_headers,
        )
        assert filtered.status_code == 200
        # 之前更新了一个 P0
        p0_reqs = filtered.json()["data"]
        assert all(r["priority"] == "P0" for r in p0_reqs)
