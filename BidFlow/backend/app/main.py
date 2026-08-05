from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库，关闭时释放连接池"""
    try:
        await init_db()
        print("[BidFlow] 数据库初始化成功")
    except Exception as e:
        print(f"[BidFlow] 数据库初始化失败: {e}")
    yield
    # 关闭时释放模块级引擎的连接池，避免 reload/停机时连接泄漏
    try:
        from app.db.session import engine, _sync_engine
        await engine.dispose()
        _sync_engine.dispose()
        print("[BidFlow] 数据库连接池已释放")
    except Exception as e:
        print(f"[BidFlow] 数据库连接池释放失败: {e}")


from app.api.router import router as api_router
from app.core.config import settings
from app.core.exceptions import BaseAppException, app_exception_handler

app = FastAPI(
    title="BidFlow API",
    description="AI招投标文件智能编制与合规核查平台",
    version="0.1.0",
    lifespan=lifespan,
)

# 统一异常处理器
app.add_exception_handler(BaseAppException, app_exception_handler)

# CORS - 使用具体 Origin 列表（allow_credentials=True 时不得使用 "*"）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载业务路由
app.include_router(api_router)


@app.get("/api/health")
async def health_check():
    """健康检查"""
    from datetime import datetime
    from sqlalchemy import text

    try:
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "ok",
        "db": db_status,
        "timestamp": datetime.utcnow().isoformat(),
    }
