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


def get_db():
    """同步数据库会话生成器"""
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine
    from app.core.config import settings

    sync_url = settings.DATABASE_URL.replace("+aiomysql", "+pymysql")
    sync_engine = create_engine(sync_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(sync_engine, autocommit=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


async def init_db() -> None:
    """初始化数据库表（导入所有模型后调用）"""
    # 导入所有模型以注册到 Base.metadata
    from app.models.user import User  # noqa: F401
    from app.models.bid_project import BidProject  # noqa: F401
    from app.models.tender_document import TenderDocument  # noqa: F401
    from app.models.requirement import Requirement  # noqa: F401
    from app.models.company_document import CompanyDocument  # noqa: F401
    from app.models.response import Response  # noqa: F401
    from app.models.compliance_issue import ComplianceIssue  # noqa: F401

    from app.db.base import Base  # noqa: F401
    from sqlalchemy import create_engine

    sync_url = settings.DATABASE_URL.replace("+aiomysql", "+pymysql")
    sync_engine = create_engine(sync_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=sync_engine)
    sync_engine.dispose()
