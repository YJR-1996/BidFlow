from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """请求级数据库会话生成器"""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """初始化数据库表（导入所有模型后调用）"""
    from app.db.base import Base  # noqa: F401
    await engine.create_all()
