from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.projects import router as projects_router
from app.api.routes.tender_documents import router as tender_documents_router
from app.api.routes.requirements import router as requirements_router
from app.api.routes.company_documents import router as company_documents_router
from app.api.routes.retrieval import router as retrieval_router
from app.api.routes.responses import router as responses_router
from app.api.routes.compliance import router as compliance_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router, prefix="/auth", tags=["认证"])
api_router.include_router(projects_router, prefix="/projects", tags=["投标项目"])
api_router.include_router(tender_documents_router, prefix="", tags=["招标文件"])
api_router.include_router(requirements_router, prefix="", tags=["响应清单"])
api_router.include_router(company_documents_router, prefix="/company-documents", tags=["企业资料"])
api_router.include_router(retrieval_router, prefix="", tags=["检索"])
api_router.include_router(responses_router, prefix="", tags=["响应草稿"])
api_router.include_router(compliance_router, prefix="", tags=["合规核查"])
