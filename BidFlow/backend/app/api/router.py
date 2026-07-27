from fastapi import APIRouter

from app.api.routes import auth  # noqa: F401  # 导入以注册路由

# 预留其他业务路由导入
# from app.api.routes import projects
# from app.api.routes import tender_documents
# from app.api.routes import requirements

router = APIRouter(prefix="/api", tags=["统一入口"])
router.include_router(auth.router)
