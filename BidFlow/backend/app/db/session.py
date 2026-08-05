from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    # 注意：不要给 aiomysql 开 pool_pre_ping！
    # SQLAlchemy 2.0.36 + aiomysql 0.3.2（PyPI 最新）存在兼容 bug：
    # AsyncAdapt_aiomysql_connection.ping() 缺少 reconnect 参数 → TypeError 500。
    # 靠 pool_recycle=3600 每小时回收连接即可防公网断连。
    pool_pre_ping=False,
    pool_recycle=3600,
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# 模块级单例：同步引擎与 sessionmaker，避免每次请求新建引擎导致连接泄漏
_sync_url = settings.DATABASE_URL.replace("+aiomysql", "+pymysql")
_sync_engine = create_engine(
    _sync_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
)
_SyncSessionLocal = sessionmaker(_sync_engine, autocommit=False, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """请求级数据库会话生成器"""
    async with async_session_factory() as session:
        yield session


def get_db():
    """同步数据库会话生成器（使用模块级单例连接池）"""
    db = _SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


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
    from app.models.workflow_run import WorkflowRun  # noqa: F401
    from app.models.remediation_action import RemediationAction  # noqa: F401
    from app.models.match_analysis import MatchAnalysisRun, MatchAnalysisDetail  # noqa: F401

    from app.db.base import Base  # noqa: F401

    # 启动自检：强制解析所有 relationship 字符串引用，
    # 若存在模型未导入/类名拼错，这里会立即抛 InvalidRequestError，
    # 而不是在首个请求时才 500。
    from sqlalchemy.orm import configure_mappers
    configure_mappers()

    sync_url = settings.DATABASE_URL.replace("+aiomysql", "+pymysql")
    # 一次性建表引擎也启用 pre_ping，避免启动期遇 stale 连接建表失败
    sync_engine = create_engine(sync_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=sync_engine)

    # 启动时检查模型与数据库 schema 是否一致，提前发现缺列问题
    _check_schema_consistency(sync_engine, Base)

    sync_engine.dispose()


def _check_schema_consistency(sync_engine, base) -> int:
    """检查所有模型表的列是否与数据库一致，缺失列时输出警告。返回缺失列数量。

    使用 SQLAlchemy 反射(inspect)做方言无关检测，兼容 MySQL/SQLite/PostgreSQL，
    避免 DESCRIBE 这类 MySQL 专有语法在其它库上静默失败。
    """
    import logging
    from sqlalchemy import inspect

    logger = logging.getLogger("bidflow.schema_check")
    missing_count = 0

    # inspect 自行管理连接，反射不到的表返回空列表
    inspector = inspect(sync_engine)
    for table_name, table in base.metadata.tables.items():
        model_cols = {col.name for col in table.columns}
        try:
            db_cols = {col["name"] for col in inspector.get_columns(table_name)}
        except Exception as e:
            logger.warning("[schema_check] 无法检查表 '%s': %s", table_name, e)
            continue

        missing = model_cols - db_cols
        if missing:
            missing_count += len(missing)
            # 仅陈述缺失列，不硬编码列类型与迁移脚本名（不同表迁移方式不同）
            logger.warning(
                "[schema_check] 表 '%s' 缺少列: %s。请运行 app/scripts/ 下相应迁移脚本，"
                "或手动: ALTER TABLE %s ADD COLUMN <列名> <类型>;",
                table_name, sorted(missing), table_name,
            )

    if missing_count > 0:
        logger.warning(
            "[schema_check] 共发现 %d 个缺失列，建议运行 app/scripts/ 下的迁移脚本或手动迁移",
            missing_count,
        )

    return missing_count
