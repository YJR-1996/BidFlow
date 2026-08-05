"""安全修复验证测试

验证关键安全修复的有效性：
1. requirements.py 批量删除越权防护（valid_ids 过滤）
2. workflow.py 接口鉴权（项目归属校验）
3. knowledge.py 项目级资料上传/检索的跨租户防护

每个场景模拟"用户 A 拥有项目，用户 B 尝试越权操作"，断言被拒绝。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db, get_session
from app.db.base import Base
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import os
import tempfile


# ---------------------------------------------------------------------------
# 复用 conftest 的 test_db / client / auth_headers 模式，但本文件需要两个用户
# 故自带 fixture 以便控制用户名
# ---------------------------------------------------------------------------
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


def _register_and_login(client, username: str) -> dict:
    """注册并登录，返回 Authorization header"""
    client.post("/api/auth/register", json={"username": username, "password": "pass123456"})
    resp = client.post("/api/auth/login", json={"username": username, "password": "pass123456"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_a_headers(client):
    return _register_and_login(client, "sec_user_a")


@pytest.fixture
def user_b_headers(client):
    return _register_and_login(client, "sec_user_b")


def _create_project(client, headers, name="A的项目"):
    resp = client.post("/api/projects", json={"name": name}, headers=headers)
    return resp.json()["data"]


def _upload_and_parse(client, headers, project_id, content="一、资格要求\n1. 必须具有法人资格。\n二、技术要求\n1. 支持高并发。"):
    """上传招标文件并解析，生成需求项"""
    upload = client.post(
        f"/api/projects/{project_id}/tender-documents",
        files={"file": ("t.txt", content.encode("utf-8"), "text/plain")},
        headers=headers,
    )
    doc_id = upload.json()["data"]["id"]
    client.post(f"/api/tender-documents/{doc_id}/parse", headers=headers)
    list_resp = client.get(f"/api/projects/{project_id}/requirements", headers=headers)
    return list_resp.json()["data"]


# ---------------------------------------------------------------------------
# 1. requirements.py 批量删除越权防护
# ---------------------------------------------------------------------------
class TestBatchDeleteSecurity:
    def test_other_user_cannot_delete_requirements(self, client, user_a_headers, user_b_headers):
        """用户 B 不能删除用户 A 项目的需求：get_project_or_404_sync 应返回 404"""
        project = _create_project(client, user_a_headers)
        reqs = _upload_and_parse(client, user_a_headers, project["id"])
        req_ids = [r["id"] for r in reqs]
        assert req_ids

        # 用户 B 尝试删除用户 A 项目的需求（TestClient.delete 不支持 json，用 request）
        resp = client.request(
            "DELETE",
            f"/api/requirements/projects/{project['id']}/batch",
            json={"ids": req_ids},
            headers=user_b_headers,
        )
        # 项目不属于 B，应被拒绝（404 项目不存在或无权限）
        assert resp.status_code in (403, 404)

        # 验证用户 A 的需求仍在
        verify = client.get(f"/api/projects/{project['id']}/requirements", headers=user_a_headers)
        assert len(verify.json()["data"]) == len(req_ids)

    def test_batch_delete_filters_to_valid_ids_only(self, client, user_a_headers):
        """传入混合 id（含不存在的）时，仅删除当前项目存在的需求，且级联删除响应"""
        project = _create_project(client, user_a_headers)
        reqs = _upload_and_parse(client, user_a_headers, project["id"])
        real_ids = [r["id"] for r in reqs]
        # 混入不存在的 id
        mixed_ids = real_ids + [999999, 999998]

        resp = client.request(
            "DELETE",
            f"/api/requirements/projects/{project['id']}/batch",
            json={"ids": mixed_ids},
            headers=user_a_headers,
        )
        assert resp.status_code == 200
        # 仅删除了真实存在的需求
        assert resp.json()["data"]["deleted"] == len(real_ids)

        # 验证已全部删除
        after = client.get(f"/api/projects/{project['id']}/requirements", headers=user_a_headers)
        assert after.json()["data"] == []

    def test_batch_delete_empty_ids_rejected(self, client, user_a_headers):
        """空 ids 列表应被拒绝"""
        project = _create_project(client, user_a_headers)
        resp = client.request(
            "DELETE",
            f"/api/requirements/projects/{project['id']}/batch",
            json={"ids": []},
            headers=user_a_headers,
        )
        assert resp.status_code != 200

    def test_batch_delete_no_matching_ids_rejected(self, client, user_a_headers):
        """传入的 id 全部不属于该项目时应被拒绝（valid_ids 为空）"""
        project = _create_project(client, user_a_headers)
        resp = client.request(
            "DELETE",
            f"/api/requirements/projects/{project['id']}/batch",
            json={"ids": [888888, 888889]},
            headers=user_a_headers,
        )
        assert resp.status_code != 200


# ---------------------------------------------------------------------------
# 2. workflow.py 鉴权
# ---------------------------------------------------------------------------
class TestWorkflowAuth:
    def test_other_user_cannot_get_workflow_status(self, client, user_a_headers, user_b_headers):
        """用户 B 不能查询用户 A 项目的工作流状态"""
        project = _create_project(client, user_a_headers)
        # 用户 A 启动工作流（路由挂载在 /api/projects 前缀下）
        run_resp = client.post(
            f"/api/projects/{project['id']}/run-workflow",
            headers=user_a_headers,
        )
        assert run_resp.status_code == 200
        run_id = run_resp.json()["run_id"]

        # 用户 B 尝试查询 → 应被拒绝
        resp = client.get(
            f"/api/projects/{project['id']}/workflow/{run_id}",
            headers=user_b_headers,
        )
        assert resp.status_code in (403, 404)

    def test_other_user_cannot_list_workflow_runs(self, client, user_a_headers, user_b_headers):
        """用户 B 不能列出用户 A 项目的工作流记录"""
        project = _create_project(client, user_a_headers)
        client.post(f"/api/projects/{project['id']}/run-workflow", headers=user_a_headers)

        resp = client.get(
            f"/api/projects/{project['id']}/workflow-runs",
            headers=user_b_headers,
        )
        assert resp.status_code in (403, 404)

    def test_other_user_cannot_start_workflow(self, client, user_a_headers, user_b_headers):
        """用户 B 不能在用户 A 的项目上启动工作流"""
        project = _create_project(client, user_a_headers)
        resp = client.post(
            f"/api/projects/{project['id']}/run-workflow",
            headers=user_b_headers,
        )
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# 3. knowledge.py 项目级资料跨租户防护
# ---------------------------------------------------------------------------
class TestKnowledgeSecurity:
    def test_other_user_cannot_upload_project_material(self, client, user_a_headers, user_b_headers):
        """用户 B 不能向用户 A 的项目上传项目级资料"""
        project = _create_project(client, user_a_headers)

        resp = client.post(
            "/api/company-documents",
            data={"scope": "project", "project_id": project["id"], "category": "案例"},
            files={"file": ("b.txt", b"B injects material", "text/plain")},
            headers=user_b_headers,
        )
        # 应被拒绝：403 无权向该项目上传资料
        assert resp.status_code in (400, 403, 404)

    def test_project_scope_without_project_id_rejected(self, client, user_a_headers):
        """scope=project 但未传 project_id 应被拒绝"""
        resp = client.post(
            "/api/company-documents",
            data={"scope": "project"},
            files={"file": ("x.txt", b"content", "text/plain")},
            headers=user_a_headers,
        )
        assert resp.status_code in (400, 422)

    def test_invalid_scope_rejected(self, client, user_a_headers):
        """非法 scope 值应被拒绝"""
        resp = client.post(
            "/api/company-documents",
            data={"scope": "invalid_scope"},
            files={"file": ("x.txt", b"content", "text/plain")},
            headers=user_a_headers,
        )
        assert resp.status_code in (400, 422)

    def test_other_user_cannot_retrieve_with_victim_project_id(self, client, user_a_headers, user_b_headers):
        """用户 B 不能用用户 A 的 project_id 检索资料"""
        project = _create_project(client, user_a_headers)

        resp = client.post(
            "/api/retrieval/search",
            json={"query": "测试", "project_id": project["id"], "top_k": 5},
            headers=user_b_headers,
        )
        # 应被拒绝：403 无权检索该项目资料
        assert resp.status_code in (403, 404)

    def test_company_scope_ignores_project_id(self, client, user_a_headers):
        """scope=company 时应强制忽略 project_id（公司级共享）"""
        # 上传 company 级资料，即便传了 project_id 也应被忽略
        project = _create_project(client, user_a_headers)
        resp = client.post(
            "/api/company-documents",
            data={"scope": "company", "project_id": project["id"], "category": "资质"},
            files={"file": ("co.txt", b"company material", "text/plain")},
            headers=user_a_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # company 级应强制 project_id=None
        assert data["scope"] == "company"
        assert data["project_id"] is None
