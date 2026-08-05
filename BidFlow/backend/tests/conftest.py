import os
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 将 backend 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.db.base import Base
from app.db.session import get_db, get_session
from app.main import app


@pytest.fixture
def event_loop():
    """为 pytest-asyncio 提供事件循环"""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_db():
    """创建 SQLite 内存数据库用于测试（使用 aiosqlite 异步引擎）"""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    # 使用 aiosqlite 异步引擎
    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingAsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    # 同步引擎用于创建表
    sync_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=sync_engine)

    async def override_get_session():
        async with TestingAsyncSessionLocal() as session:
            yield session

    def override_get_db():
        # 同步版本也用同步引擎
        TestingSyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
        db = TestingSyncSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_db] = override_get_db

    yield TestingAsyncSessionLocal

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
    """创建测试客户端（依赖 test_db 确保数据库已初始化）"""
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def auth_headers(client, test_db):
    """通过注册/登录获取测试 token"""
    # 使用测试函数名生成唯一用户名
    import inspect
    frame = inspect.currentframe()
    try:
        # 获取调用测试的函数名
        for f in inspect.getouterframes(frame):
            if f.function.startswith('test_'):
                username = f.function.replace("test_", "").replace("_", "")[:20]
                break
        else:
            username = "testuser"
    finally:
        del frame
    
    password = "testpassword123"

    # 先注册
    client.post("/api/auth/register", json={"username": username, "password": password})

    # 再登录获取 token
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
