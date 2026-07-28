from fastapi import APIRouter

from app.api.routes import auth, company_documents, compliance, projects, requirements, responses, tender_documents

router = APIRouter(prefix="/api", tags=["统一入口"])
router.include_router(auth.router)
router.include_router(projects.router, prefix="/projects", tags=["项目"])
router.include_router(tender_documents.router, tags=["招标文件"])
router.include_router(requirements.router, tags=["需求项"])
router.include_router(responses.router)
router.include_router(compliance.router)
router.include_router(company_documents.router)
