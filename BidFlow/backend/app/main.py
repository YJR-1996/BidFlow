from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.db.session import init_db
from app.api.router import api_router
from app.schemas.common import ApiResponse

app = FastAPI(
    title=settings.APP_NAME,
    description="BidFlow：AI 招投标文件智能编制与合规核查平台",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router)


@app.on_event("startup")
def startup_event():
    init_db()
    print(f"✅ {settings.APP_NAME} 启动成功")


@app.get("/api/health", tags=["健康检查"])
def health_check():
    return ApiResponse(data={
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "app_name": settings.APP_NAME,
    })
