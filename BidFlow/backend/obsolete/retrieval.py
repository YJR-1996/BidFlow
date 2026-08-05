"""检索路由 - 企业资料搜索接口"""
from fastapi import APIRouter, Depends

from app.schemas.common import ApiResponse
from app.api.deps import get_current_user
from app.schemas.company_document import RetrievalRequest, RetrievedChunk
from app.services.retrieval_service import retrieval_service

router = APIRouter()


@router.post("/search", response_model=ApiResponse[list[RetrievedChunk]])
async def search_knowledge(
    req: RetrievalRequest,
    current_user=Depends(get_current_user),
):
    """检索企业知识库"""
    results = retrieval_service.search(
        query=req.query,
        project_id=req.project_id,
        top_k=req.top_k,
    )
    return ApiResponse(data=results)

