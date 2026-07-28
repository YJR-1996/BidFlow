import os
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_project_or_404
from app.core.exceptions import BusinessException
from app.db.session import get_session
from app.models.bid_project import BidProject
from app.models.tender_document import TenderDocument
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.tender_document import ParseResultResponse, TenderDocumentResponse
from app.services.document_parser import document_parser_service
from app.services.file_storage import file_storage_service
from app.services.tender_requirement_extractor import tender_requirement_extractor_service

router = APIRouter()


async def _get_document_or_404(document_id: int, current_user: User, session: AsyncSession) -> TenderDocument:
    result = await session.execute(
        select(TenderDocument).join(BidProject).where(
            TenderDocument.id == document_id,
            BidProject.owner_id == str(current_user.id),
        )
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "招标文件不存在"})
    return document


@router.post("/projects/{project_id}/tender-documents", response_model=ApiResponse[TenderDocumentResponse])
async def upload_tender_document(
    file: UploadFile = File(...),
    project: BidProject = Depends(get_project_or_404),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    file_path, original_filename = file_storage_service.save_file(project.id, str(current_user.id), file)
    document = TenderDocument(
        project_id=project.id,
        filename=original_filename,
        file_path=file_path,
        file_type=file_storage_service.get_file_extension(original_filename),
        file_size=os.path.getsize(file_path),
        status="pending",
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return ApiResponse(data=document)


@router.post("/tender-documents/{document_id}/parse", response_model=ApiResponse[ParseResultResponse])
async def parse_tender_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    document = await _get_document_or_404(document_id, current_user, session)
    document.status = "processing"
    await session.commit()
    try:
        paragraphs = document_parser_service.parse(document.file_path, document.file_type or "txt")
        requirements = await tender_requirement_extractor_service.extract(
            db=session,
            project_id=document.project_id,
            tender_document_id=document.id,
            parsed_paragraphs=paragraphs,
        )
        document.status = "success"
        await session.commit()
        return ApiResponse(data=ParseResultResponse(document_id=document.id, status="success", requirement_count=len(requirements)))
    except Exception as exc:
        await session.rollback()
        document.status = "failed"
        document.error_message = str(exc)
        await session.commit()
        raise BusinessException(message=f"解析失败: {exc}")


@router.get("/projects/{project_id}/tender-documents", response_model=ApiResponse[List[TenderDocumentResponse]])
async def list_tender_documents(
    project: BidProject = Depends(get_project_or_404),
    session: AsyncSession = Depends(get_session),
):
    documents = (await session.execute(select(TenderDocument).where(TenderDocument.project_id == project.id).order_by(TenderDocument.created_at.desc()))).scalars().all()
    return ApiResponse(data=documents)


@router.get("/tender-documents/{document_id}", response_model=ApiResponse[TenderDocumentResponse])
async def get_tender_document(document_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return ApiResponse(data=await _get_document_or_404(document_id, current_user, session))


@router.delete("/tender-documents/{document_id}", response_model=ApiResponse[dict])
async def delete_tender_document(document_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    document = await _get_document_or_404(document_id, current_user, session)
    file_storage_service.delete_file(document.file_path)
    await session.delete(document)
    await session.commit()
    return ApiResponse(data={"message": "删除成功"})
