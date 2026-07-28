from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型继承的统一基类。"""

    pass

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    # asyncmy 0.2.9 的 ping 签名与 SQLAlchemy 的预检不兼容；连接失败由请求实际执行时返回。
    pool_pre_ping=False,
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """请求级数据库会话生成器"""
    async with async_session_factory() as session:
        yield session


async def get_db() -> AsyncSession:
    """兼容既有路由和测试使用的数据库会话依赖名称。"""
    async for session in get_session():
        yield session


async def init_db() -> None:
    """初始化数据库表（导入所有模型后调用）"""
    from app.db import base  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
