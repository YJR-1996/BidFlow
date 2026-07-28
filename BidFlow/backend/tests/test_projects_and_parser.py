import asyncio
import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.db.session import Base, get_db, get_session


@pytest.fixture
def test_db():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def create_tables():
        from app.db import base  # noqa: F401
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())

    async def override_get_session():
        async with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_db] = override_get_session

    yield TestingSessionLocal

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except PermissionError:
        pass


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client, test_db):
    response = client.post("/api/auth/register", json={
        "username": "test_user_b",
        "password": "test123456",
    })
    assert response.status_code == 201

    response = client.post("/api/auth/login", json={
        "username": "test_user_b",
        "password": "test123456",
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_project(client, auth_headers):
    response = client.post("/api/projects", json={
        "name": "测试投标项目",
        "tenderer": "测试招标单位",
        "description": "这是一个测试项目",
    }, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "测试投标项目"
    assert data["tenderer"] == "测试招标单位"
    assert data["status"] == "准备中"
    assert "id" in data


def test_list_projects(client, auth_headers):
    client.post("/api/projects", json={
        "name": "项目1",
    }, headers=auth_headers)
    client.post("/api/projects", json={
        "name": "项目2",
    }, headers=auth_headers)

    response = client.get("/api/projects", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 2


def test_get_project_detail(client, auth_headers):
    create_resp = client.post("/api/projects", json={
        "name": "详情测试项目",
        "description": "测试详情",
    }, headers=auth_headers)
    project_id = create_resp.json()["data"]["id"]

    response = client.get(f"/api/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "详情测试项目"


def test_update_project(client, auth_headers):
    create_resp = client.post("/api/projects", json={
        "name": "待更新项目",
    }, headers=auth_headers)
    project_id = create_resp.json()["data"]["id"]

    response = client.patch(f"/api/projects/{project_id}", json={
        "name": "更新后的项目名",
        "status": "审核中",
    }, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "更新后的项目名"
    assert data["status"] == "审核中"


def test_delete_project(client, auth_headers):
    create_resp = client.post("/api/projects", json={
        "name": "待删除项目",
    }, headers=auth_headers)
    project_id = create_resp.json()["data"]["id"]

    response = client.delete(f"/api/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200

    response = client.get(f"/api/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 404


def test_cannot_access_other_user_project(client, auth_headers):
    create_resp = client.post("/api/projects", json={
        "name": "用户A的项目",
    }, headers=auth_headers)
    project_id = create_resp.json()["data"]["id"]

    client.post("/api/auth/register", json={
        "username": "test_user_c",
        "password": "test123456",
    })
    login_resp = client.post("/api/auth/login", json={
        "username": "test_user_c",
        "password": "test123456",
    })
    other_token = login_resp.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    response = client.get(f"/api/projects/{project_id}", headers=other_headers)
    assert response.status_code == 404


TENDER_CONTENT_1 = (
    "一、投标人资格要求\n"
    "1. 投标人必须是具有独立法人资格的企业，持有有效的营业执照。\n"
    "2. 投标人近三年内具有至少3个类似项目的成功案例。\n"
    "\n"
    "二、商务要求\n"
    "1. 项目总预算为人民币500万元。\n"
    "2. 交付周期：合同签订后90天内完成。\n"
    "\n"
    "三、技术要求\n"
    "1. 系统性能要求：需支持至少1000个并发用户。\n"
    "2. 系统采用B/S架构，支持主流浏览器访问。\n"
    "3. 数据需每日自动备份。"
)


def test_upload_txt_file(client, auth_headers):
    create_resp = client.post("/api/projects", json={
        "name": "文件上传测试项目",
    }, headers=auth_headers)
    project_id = create_resp.json()["data"]["id"]

    response = client.post(
        f"/api/projects/{project_id}/tender-documents",
        files={"file": ("test_tender.txt", TENDER_CONTENT_1.encode("utf-8"), "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["filename"] == "test_tender.txt"
    assert data["status"] == "pending"
    assert data["file_type"] == "txt"


def test_upload_invalid_file_type(client, auth_headers):
    create_resp = client.post("/api/projects", json={
        "name": "无效文件测试项目",
    }, headers=auth_headers)
    project_id = create_resp.json()["data"]["id"]

    response = client.post(
        f"/api/projects/{project_id}/tender-documents",
        files={"file": ("test.jpg", b"fake image data", "image/jpeg")},
        headers=auth_headers,
    )
    assert response.status_code == 422


TENDER_CONTENT_2 = (
    "一、投标人资格要求\n"
    "1. 投标人必须是具有独立法人资格的企业，持有有效的营业执照。\n"
    "2. 投标人近三年内具有至少3个类似项目的成功案例。\n"
    "\n"
    "二、商务要求\n"
    "1. 项目总预算为人民币500万元。\n"
    "\n"
    "三、技术要求\n"
    "1. 系统需支持至少1000个并发用户同时在线访问。\n"
    "2. 系统应采用B/S架构。"
)


def test_parse_tender_document(client, auth_headers):
    create_resp = client.post("/api/projects", json={
        "name": "解析测试项目",
    }, headers=auth_headers)
    project_id = create_resp.json()["data"]["id"]

    upload_resp = client.post(
        f"/api/projects/{project_id}/tender-documents",
        files={"file": ("test.txt", TENDER_CONTENT_2.encode("utf-8"), "text/plain")},
        headers=auth_headers,
    )
    document_id = upload_resp.json()["data"]["id"]

    parse_resp = client.post(
        f"/api/tender-documents/{document_id}/parse",
        headers=auth_headers,
    )
    assert parse_resp.status_code == 200
    parse_data = parse_resp.json()["data"]
    assert parse_data["status"] == "success"
    assert parse_data["requirement_count"] > 0

    list_resp = client.get(
        f"/api/projects/{project_id}/requirements",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    requirements = list_resp.json()["data"]
    assert len(requirements) > 0

    categories = set(r["category"] for r in requirements)
    assert "资格" in categories
    assert "技术" in categories
    assert "商务" in categories

    for req in requirements:
        assert req["source_text"] is not None
        assert req["source_ref"] is not None
        assert req["priority"] in ["P0", "P1", "P2"]


def test_update_requirement(client, auth_headers):
    create_resp = client.post("/api/projects", json={
        "name": "需求更新测试项目",
    }, headers=auth_headers)
    project_id = create_resp.json()["data"]["id"]

    content = "一、资格要求\n投标人必须具有独立法人资格。"
    upload_resp = client.post(
        f"/api/projects/{project_id}/tender-documents",
        files={"file": ("test.txt", content.encode("utf-8"), "text/plain")},
        headers=auth_headers,
    )
    document_id = upload_resp.json()["data"]["id"]
    client.post(f"/api/tender-documents/{document_id}/parse", headers=auth_headers)

    list_resp = client.get(f"/api/projects/{project_id}/requirements", headers=auth_headers)
    req_id = list_resp.json()["data"][0]["id"]

    update_resp = client.patch(
        f"/api/requirements/{req_id}",
        json={
            "content": "更新后的需求内容",
            "status": "处理中",
            "priority": "P0",
        },
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    data = update_resp.json()["data"]
    assert data["content"] == "更新后的需求内容"
    assert data["status"] == "处理中"
    assert data["priority"] == "P0"


TENDER_CONTENT_3 = (
    "一、资格要求\n"
    "1. 投标人必须具有独立法人资格。\n"
    "\n"
    "二、技术要求\n"
    "1. 系统支持高并发。\n"
    "\n"
    "三、商务要求\n"
    "1. 报价不得超过预算。"
)


def test_filter_requirements(client, auth_headers):
    create_resp = client.post("/api/projects", json={
        "name": "筛选测试项目",
    }, headers=auth_headers)
    project_id = create_resp.json()["data"]["id"]

    upload_resp = client.post(
        f"/api/projects/{project_id}/tender-documents",
        files={"file": ("test.txt", TENDER_CONTENT_3.encode("utf-8"), "text/plain")},
        headers=auth_headers,
    )
    document_id = upload_resp.json()["data"]["id"]
    client.post(f"/api/tender-documents/{document_id}/parse", headers=auth_headers)

    response = client.get(
        f"/api/projects/{project_id}/requirements?category=资格",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert all(r["category"] == "资格" for r in data)

    response = client.get(
        f"/api/projects/{project_id}/requirements?priority=P0",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert all(r["priority"] == "P0" for r in data)
