import asyncio
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.db.session import Base, get_session


@pytest.fixture
def test_db():
    """认证测试使用独立 SQLite，不能依赖本机 MySQL 的历史数据和连接状态。"""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def create_tables():
        from app.db import base  # noqa: F401
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(test_db):
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def auth_headers(client: TestClient, request):
    """通过注册/登录获取测试 token"""
    username = request.node.name.replace("test_", "").replace("_", "")[:20]
    password = "testpassword123"

    # 先注册
    client.post("/api/auth/register", json={"username": username, "password": password})

    # 再登录获取 token
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestAuth:
    """认证模块测试"""

    def test_register_success(self, client: TestClient):
        """测试注册新用户"""
        username = "test_register_user"
        resp = client.post("/api/auth/register", json={"username": username, "password": "password123"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == username
        assert "id" in data
        assert "created_at" in data

    def test_register_duplicate_username(self, client: TestClient):
        """测试重复用户名注册失败"""
        username = "test_dup_user"
        client.post("/api/auth/register", json={"username": username, "password": "password123"})
        resp = client.post("/api/auth/register", json={"username": username, "password": "password123"})
        assert resp.status_code == 409

    def test_register_short_password(self, client: TestClient):
        """测试短密码注册失败"""
        resp = client.post("/api/auth/register", json={"username": "shortpwd", "password": "abc"})
        assert resp.status_code == 422

    def test_login_success(self, client: TestClient):
        """测试正确密码登录成功"""
        username = "test_login_user"
        password = "password123"
        client.post("/api/auth/register", json={"username": username, "password": password})
        resp = client.post("/api/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client: TestClient):
        """测试错误密码登录失败"""
        username = "test_wrongpwd_user"
        client.post("/api/auth/register", json={"username": username, "password": "password123"})
        resp = client.post("/api/auth/login", json={"username": username, "password": "wrongpassword"})
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client: TestClient):
        """测试不存在的用户登录失败"""
        resp = client.post("/api/auth/login", json={"username": "nonexistent_user", "password": "password123"})
        assert resp.status_code == 401

    def test_get_me_without_token(self, client: TestClient):
        """测试无 Token 获取当前用户失败"""
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_get_me_with_forged_token(self, client: TestClient):
        """测试伪造 Token 获取当前用户失败"""
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer forged.token.here"})
        assert resp.status_code == 401

    def test_get_me_success(self, client: TestClient, auth_headers: dict):
        """测试携带正确 Token 获取当前用户成功"""
        resp = client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "username" in data
        assert "is_active" in data
