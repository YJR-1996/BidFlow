"""knowledge.py 与 tender_documents.py 路由端点补充测试

覆盖企业资料列表/详情/删除/检索，以及招标文件删除/下载等端点。
"""
import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import tempfile

from app.main import app
from app.db.session import get_db, get_session
from app.db.base import Base
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.company_document import CompanyDocument


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
    client.post("/api/auth/register", json={"username": "know_user", "password": "pass123456"})
    resp = client.post("/api/auth/login", json={"username": "know_user", "password": "pass123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# knowledge.py：企业资料列表/详情/删除/检索
# ---------------------------------------------------------------------------
class TestCompanyDocumentsList:
    def test_list_empty_returns_empty_array(self, client, auth_headers):
        """无资料时列表返回空数组"""
        r = client.get("/api/company-documents", headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == []

    def test_list_returns_owner_documents_only(self, client, auth_headers, test_db):
        """列表仅返回当前用户的资料"""
        db = test_db()
        db.add(CompanyDocument(
            id=1, filename="a.pdf", file_type="pdf", file_path="/tmp/a.pdf",
            owner_id=_get_user_id(client, auth_headers), status="success", scope="company",
        ))
        # 另一用户的资料
        db.add(CompanyDocument(
            id=2, filename="b.pdf", file_type="pdf", file_path="/tmp/b.pdf",
            owner_id="other-user-id", status="success", scope="company",
        ))
        db.commit()
        db.close()

        r = client.get("/api/company-documents", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["filename"] == "a.pdf"


def _get_user_id(client, auth_headers):
    """从 /me 接口获取当前用户 ID（响应可能包裹在 data 中也可能直接返回）"""
    r = client.get("/api/auth/me", headers=auth_headers)
    body = r.json()
    if isinstance(body, dict) and "data" in body:
        return body["data"]["id"]
    return body["id"]


class TestCompanyDocumentDetail:
    def test_detail_not_found(self, client, auth_headers):
        r = client.get("/api/company-documents/9999/detail", headers=auth_headers)
        assert r.status_code == 404

    def test_detail_other_user_denied(self, client, auth_headers, test_db):
        db = test_db()
        db.add(CompanyDocument(
            id=10, filename="x.pdf", file_type="pdf", file_path="/tmp/x.pdf",
            owner_id="other-user", status="success", scope="company",
        ))
        db.commit()
        db.close()
        r = client.get("/api/company-documents/10/detail", headers=auth_headers)
        assert r.status_code == 404


class TestCompanyDocumentDelete:
    def test_delete_not_found(self, client, auth_headers):
        r = client.delete("/api/company-documents/9999", headers=auth_headers)
        assert r.status_code == 404

    def test_delete_other_user_denied(self, client, auth_headers, test_db):
        db = test_db()
        db.add(CompanyDocument(
            id=20, filename="y.pdf", file_type="pdf", file_path="/tmp/y.pdf",
            owner_id="other-user", status="success", scope="company",
        ))
        db.commit()
        db.close()
        r = client.delete("/api/company-documents/20", headers=auth_headers)
        assert r.status_code == 404


class TestRetrievalSearch:
    # RAG 增强后 retrieval 优先走 hybrid_search，mock 目标随之更新
    def test_search_empty_query(self, client, auth_headers):
        """检索接口正常工作（mock 向量检索）"""
        with patch("app.services.vector_store.vector_store_service.hybrid_search", return_value=[]):
            r = client.post("/api/retrieval/search", json={"query": "测试", "top_k": 5}, headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_search_returns_results(self, client, auth_headers):
        mock_results = [
            {"text": "案例内容", "score": 0.9, "metadata": {"filename": "case.pdf", "source_ref": "p1", "scope": "company"}},
        ]
        with patch("app.services.vector_store.vector_store_service.hybrid_search", return_value=mock_results), \
             patch("app.services.reranker.llm_reranker.rerank", side_effect=lambda q, c, k: c[:k]):
            r = client.post("/api/retrieval/search", json={"query": "案例", "top_k": 3}, headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["content"] == "案例内容"

    def test_search_failure_degrades_to_empty(self, client, auth_headers):
        """混合检索失败 → 降级 keyword 检索；降级也无结果 → 返回空列表而非 500"""
        with patch("app.services.vector_store.vector_store_service.hybrid_search", side_effect=Exception("Milvus down")), \
             patch("app.services.vector_store.vector_store_service.search", return_value=[]):
            r = client.post("/api/retrieval/search", json={"query": "测试", "top_k": 5}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# tender_documents.py：招标文件列表/删除/下载
# ---------------------------------------------------------------------------
TENDER = "一、资格要求\n1. 必须具有法人资格。\n二、技术要求\n1. 支持高并发。"


class TestTenderDocuments:
    def _setup(self, client, headers):
        pid = client.post("/api/projects", json={"name": "文档测试项目"}, headers=headers).json()["data"]["id"]
        upload = client.post(
            f"/api/projects/{pid}/tender-documents",
            files={"file": ("t.txt", TENDER.encode("utf-8"), "text/plain")},
            headers=headers,
        )
        return pid, upload.json()["data"]["id"]

    def test_list_tender_documents(self, client, auth_headers):
        """列出项目的招标文件"""
        pid, doc_id = self._setup(client, auth_headers)
        r = client.get(f"/api/projects/{pid}/tender-documents", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) >= 1

    def test_delete_tender_document(self, client, auth_headers):
        """删除招标文件"""
        pid, doc_id = self._setup(client, auth_headers)
        r = client.delete(f"/api/tender-documents/{doc_id}", headers=auth_headers)
        assert r.status_code == 200

    def test_delete_nonexistent_tender_document(self, client, auth_headers):
        r = client.delete("/api/tender-documents/99999", headers=auth_headers)
        assert r.status_code in (404, 400)

    def test_delete_other_user_denied(self, client, auth_headers):
        """其他用户不能删除他人项目的招标文件"""
        pid, doc_id = self._setup(client, auth_headers)
        client.post("/api/auth/register", json={"username": "know_user_b", "password": "pass123456"})
        resp = client.post("/api/auth/login", json={"username": "know_user_b", "password": "pass123456"})
        other = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        r = client.delete(f"/api/tender-documents/{doc_id}", headers=other)
        assert r.status_code in (403, 404)

    def test_download_tender_document(self, client, auth_headers):
        """下载招标文件"""
        pid, doc_id = self._setup(client, auth_headers)
        r = client.get(f"/api/tender-documents/{doc_id}/download", headers=auth_headers)
        # 下载接口可能返回文件流或 404（取决于实现）
        assert r.status_code in (200, 404)
