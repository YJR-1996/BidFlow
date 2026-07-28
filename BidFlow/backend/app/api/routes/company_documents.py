from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.company_document import CompanyDocumentResponse, RetrievalRequest, RetrievedChunk
from app.services.company_material_service import CompanyMaterialService
from app.services.retrieval_service import RetrievalService
from app.services.vector_store import VectorStoreError

router = APIRouter(prefix="/company-documents", tags=["企业资料"])
service = CompanyMaterialService()
retrieval_service = RetrievalService()


@router.post("", response_model=dict)
async def upload_company_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        document, chunk_count = await service.upload_and_index(session, str(user.id), file)
        return {"document": CompanyDocumentResponse.model_validate(document), "chunk_count": chunk_count}
    except VectorStoreError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "VECTOR_UNAVAILABLE", "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "MATERIAL_UPLOAD_FAILED", "message": str(exc)}) from exc


@router.get("", response_model=list[CompanyDocumentResponse])
async def list_company_documents(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await service.list_documents(session, str(user.id))


@router.delete("/{document_id}")
async def delete_company_document(document_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    try:
        if not await service.delete_document(session, str(user.id), document_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "企业资料不存在"})
        return {"message": "资料已删除"}
    except VectorStoreError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "VECTOR_UNAVAILABLE", "message": str(exc)}) from exc


@router.post("/search", response_model=list[RetrievedChunk])
async def search_company_documents(body: RetrievalRequest, user: User = Depends(get_current_user)):
    try:
        return retrieval_service.search(str(user.id), body.query, body.top_k)
    except VectorStoreError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "VECTOR_UNAVAILABLE", "message": str(exc)}) from exc
