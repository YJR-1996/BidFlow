"""标书导出测试：服务层（Markdown/PDF 生成）+ 端点权限"""
import io

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.models.response import Response as BidResponse
from app.services.bid_document_service import bid_document_service


@pytest.fixture
def bid_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    user = User(id="u1", username="biduser", password_hash="x")
    db.add(user)
    project = BidProject(id=1, name="测试标书项目", owner_id="u1")
    db.add(project)
    # 资格需求：有响应（人工编辑优先）
    db.add(Requirement(id=1, project_id=1, content="提供营业执照与法人资格证明", category="资格", priority="P0", status="已完成"))
    db.add(BidResponse(requirement_id=1, ai_content="AI 草稿内容", edited_content="我方持有有效营业执照。", status="approved"))
    # 技术需求：无响应（走待补充附录）
    db.add(Requirement(id=2, project_id=1, content="系统需支持 1000 并发，采用 B/S 架构", category="技术", priority="P1", status="未处理"))
    db.commit()
    yield db
    db.close()
    engine.dispose()


class TestBidDocumentService:
    def test_build_markdown_content(self, bid_db):
        md = bid_document_service.build_markdown(bid_db, 1, "测试标书项目")
        # 封面与统计
        assert "测试标书项目 投标响应文件" in md
        assert "需求总数：2" in md and "已响应：1" in md and "待补充：1" in md
        # 章节：资格响应（有内容）+ 技术响应
        assert "第一章　资格响应" in md
        assert "第二章　技术响应" in md
        # 响应内容：人工编辑优先（不是 AI 草稿）
        assert "我方持有有效营业执照。" in md
        assert "AI 草稿内容" not in md
        # 待补充附录
        assert "附录　待补充项清单" in md
        assert "尚未生成响应" in md

    def test_build_markdown_empty_project(self, bid_db):
        md = bid_document_service.build_markdown(bid_db, 1, "测试标书项目")
        assert md  # 不抛异常

    def test_build_pdf_bytes(self, bid_db):
        data = bid_document_service.build_pdf_bytes(bid_db, 1, "测试标书项目")
        assert data[:5] == b"%PDF-", "PDF 头校验失败"
        assert len(data) > 1000

    def test_edited_content_priority(self, bid_db):
        """edited_content 优先于 ai_content"""
        items = bid_document_service.load_requirements(bid_db, 1)
        by_id = {i.requirement_id: i for i in items}
        assert by_id[1].response_content == "我方持有有效营业执照。"


def _setup_project(client, headers):
    r = client.post("/api/projects", json={"name": "导出权限项目"}, headers=headers)
    return r.json()["data"]["id"]


class TestBidDocumentRoute:
    def test_markdown_requires_auth(self, client):
        r = client.get("/api/projects/1/bid-document/markdown")
        assert r.status_code in (401, 403)

    def test_markdown_other_user_denied(self, client, auth_headers):
        pid = _setup_project(client, auth_headers)
        client.post("/api/auth/register", json={"username": "bid_user_b", "password": "pass123456"})
        resp = client.post("/api/auth/login", json={"username": "bid_user_b", "password": "pass123456"})
        other = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        r = client.get(f"/api/projects/{pid}/bid-document/markdown", headers=other)
        assert r.status_code in (403, 404)

    def test_markdown_returns_stream(self, client, auth_headers):
        pid = _setup_project(client, auth_headers)
        r = client.get(f"/api/projects/{pid}/bid-document/markdown", headers=auth_headers)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith(("text/", "application/"))
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_pdf_returns_stream(self, client, auth_headers):
        pid = _setup_project(client, auth_headers)
        r = client.get(f"/api/projects/{pid}/bid-document/pdf", headers=auth_headers)
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"

    def test_bid_package_returns_zip(self, client, auth_headers):
        """打包投递包：zip 包含标书 md/pdf + 合规报告 md/pdf + README"""
        import io
        import zipfile

        pid = _setup_project(client, auth_headers)
        r = client.get(f"/api/projects/{pid}/bid-package", headers=auth_headers)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/zip")
        assert "attachment" in r.headers.get("content-disposition", "")

        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert "投标响应文件.md" in names
        assert "投标响应文件.pdf" in names
        assert "合规审查报告.md" in names
        assert "合规审查报告.pdf" in names
        assert "README.txt" in names
        # 标书 md 非空、PDF 合法头
        assert len(zf.read("投标响应文件.md")) > 100
        assert zf.read("投标响应文件.pdf")[:5] == b"%PDF-"

    def test_bid_package_other_user_denied(self, client, auth_headers):
        """越权用户不能打包他人项目"""
        pid = _setup_project(client, auth_headers)
        client.post("/api/auth/register", json={"username": "bid_user_c", "password": "pass123456"})
        resp = client.post("/api/auth/login", json={"username": "bid_user_c", "password": "pass123456"})
        other = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        r = client.get(f"/api/projects/{pid}/bid-package", headers=other)
        assert r.status_code in (403, 404)

    def test_bid_package_marks_project_completed(self, client, auth_headers):
        """打包投递包成功 → 项目自动流转为"已完成" """
        pid = _setup_project(client, auth_headers)
        r = client.get(f"/api/projects/{pid}/bid-package", headers=auth_headers)
        assert r.status_code == 200
        proj = client.get(f"/api/projects/{pid}", headers=auth_headers).json()["data"]
        assert proj["status"] == "已完成"
