from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.tender_document import TenderDocument
from app.models.requirement import Requirement
from app.schemas.tender_document import TenderDocumentResponse, ParseResultResponse
from app.schemas.common import ApiResponse
from app.api.deps import get_current_user, get_project_or_404_sync
from app.services.file_storage import file_storage_service
from app.services.document_parser import document_parser_service
from app.services.tender_requirement_extractor import tender_requirement_extractor_service
from app.core.exceptions import NotFoundException, BusinessException

router = APIRouter()


@router.post("/projects/{project_id}/tender-documents", response_model=ApiResponse[TenderDocumentResponse])
def upload_tender_document(
    file: UploadFile = File(...),
    project: BidProject = Depends(get_project_or_404_sync),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_path, original_filename = file_storage_service.save_file(
        project_id=project.id,
        user_id=current_user.id,
        file=file,
    )

    file_type = file_storage_service.get_file_extension(original_filename)
    import os
    file_size = os.path.getsize(file_path)

    doc = TenderDocument(
        project_id=project.id,
        filename=original_filename,
        file_path=file_path,
        file_type=file_type,
        file_size=file_size,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return ApiResponse(data=doc)


@router.post("/tender-documents/{document_id}/parse", response_model=ApiResponse[ParseResultResponse])
def parse_tender_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(TenderDocument).filter(TenderDocument.id == document_id).first()
    if not doc:
        raise NotFoundException(message="招标文件不存在")

    project = db.query(BidProject).filter(BidProject.id == doc.project_id).first()
    if not project or project.owner_id != current_user.id:
        raise NotFoundException(message="招标文件不存在")

    doc.status = "processing"
    db.commit()

    try:
        parsed_paragraphs = document_parser_service.parse(doc.file_path, doc.file_type or "txt")
        requirements = tender_requirement_extractor_service.extract(
            db=db,
            project_id=doc.project_id,
            tender_document_id=doc.id,
            parsed_paragraphs=parsed_paragraphs,
        )
        db.commit()

        doc.status = "success"
        db.commit()

        return ApiResponse(data=ParseResultResponse(
            document_id=doc.id,
            status="success",
            requirement_count=len(requirements),
        ))

    except Exception as e:
        doc.status = "failed"
        doc.error_message = str(e)
        db.commit()
        raise BusinessException(message=f"解析失败: {str(e)}")


@router.get("/projects/{project_id}/tender-documents", response_model=ApiResponse[List[TenderDocumentResponse]])
def list_tender_documents(
    project: BidProject = Depends(get_project_or_404_sync),
    db: Session = Depends(get_db),
):
    docs = db.query(TenderDocument).filter(
        TenderDocument.project_id == project.id
    ).order_by(TenderDocument.created_at.desc()).all()
    return ApiResponse(data=docs)


@router.get("/tender-documents/{document_id}", response_model=ApiResponse[TenderDocumentResponse])
def get_tender_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(TenderDocument).filter(TenderDocument.id == document_id).first()
    if not doc:
        raise NotFoundException(message="招标文件不存在")

    project = db.query(BidProject).filter(BidProject.id == doc.project_id).first()
    if not project or project.owner_id != current_user.id:
        raise NotFoundException(message="招标文件不存在")

    return ApiResponse(data=doc)


@router.delete("/tender-documents/{document_id}", response_model=ApiResponse[dict])
def delete_tender_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(TenderDocument).filter(TenderDocument.id == document_id).first()
    if not doc:
        raise NotFoundException(message="招标文件不存在")

    project = db.query(BidProject).filter(BidProject.id == doc.project_id).first()
    if not project or project.owner_id != current_user.id:
        raise NotFoundException(message="招标文件不存在")

    file_storage_service.delete_file(doc.file_path)
    db.delete(doc)
    db.commit()

    return ApiResponse(data={"message": "删除成功"})
