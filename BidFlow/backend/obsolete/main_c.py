"""
成员C 独立运行入口（仅用于自测/演示；并入 develop 时由成员A的 app/main.py 统一入口覆盖）。

运行方式（在 backend/ 目录下）：
    uvicorn app.main_c:app --reload --port 8000

成员A 整合时只需在其 main.py 中：
    from app.api.routes.knowledge import router as knowledge_router
    app.include_router(knowledge_router)
即可把成员C的全部接口挂到统一 app 上，无需改动本文件。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.knowledge import router as knowledge_router
from app.db.session import init_db

# 创建 FastAPI 应用
app = FastAPI(title="BidFlow - 企业资料知识库(成员C)", version="1.0")

# 允许跨域（前端联调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载成员C的全部接口（单一路由文件）
app.include_router(knowledge_router)


@app.get("/api/health")
def health():
    """健康检查：用于 Docker / 集成联调探测服务存活。"""
    return {"status": "ok", "module": "company-knowledge", "version": "1.0"}


# 启动时建表（SQLite 首次运行创建 company_documents 等表）
init_db()
