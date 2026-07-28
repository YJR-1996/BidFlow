from fastapi import APIRouter

from app.api.routes import auth  # noqa: F401  # 导入以注册路由
from app.api.routes import projects  # noqa: F401
from app.api.routes import tender_documents  # noqa: F401
from app.api.routes import requirements  # noqa: F401
from app.api.routes import compliance  # noqa: F401
from app.api.routes import responses  # noqa: F401
from app.api.routes import knowledge  # noqa: F401

router = APIRouter(prefix="/api", tags=["统一入口"])
router.include_router(auth.router)
router.include_router(projects.router, prefix="/projects", tags=["项目"])
router.include_router(tender_documents.router, tags=["招标文件"])
router.include_router(requirements.router, tags=["需求项"])
router.include_router(compliance.router, tags=["合规核查"])
router.include_router(responses.router, prefix="/requirements", tags=["响应草稿"])
router.include_router(knowledge.router)
