from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.tender_document import TenderDocument
from app.models.requirement import Requirement
from app.models.response import Response
from app.models.compliance_issue import ComplianceIssue
from app.models.match_analysis import MatchAnalysisDetail, MatchAnalysisRun
from sqlalchemy import select
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

    file_path = doc.file_path
    project_id = doc.project_id

    # 级联清理（按依赖顺序：先子后父）
    # bulk query.delete() 不触发 ORM cascade，必须手动按表清理
    # 1) 先按 project_id 清掉所有合规问题（避免需求删除时遗留 requirement_id 关联）
    db.query(ComplianceIssue).filter(
        ComplianceIssue.project_id == project_id
    ).delete(synchronize_session=False)

    # 2) 删除项目级的比对分析运行记录（details 通过 ORM cascade 自动清）
    #    必须在删 Requirement 前完成——否则历史 runs 会显示已删除的需求数据
    db.query(MatchAnalysisRun).filter(
        MatchAnalysisRun.project_id == project_id
    ).delete(synchronize_session=False)

    # 3) 找出关联需求的 id 子查询，删除其响应、合规细节和比对分析细节
    req_ids_subq = select(Requirement.id).where(
        Requirement.tender_document_id == document_id
    )
    db.query(Response).filter(
        Response.requirement_id.in_(req_ids_subq)
    ).delete(synchronize_session=False)
    db.query(ComplianceIssue).filter(
        ComplianceIssue.requirement_id.in_(req_ids_subq)
    ).delete(synchronize_session=False)
    db.query(MatchAnalysisDetail).filter(
        MatchAnalysisDetail.requirement_id.in_(req_ids_subq)
    ).delete(synchronize_session=False)

    # 4) 删除关联需求
    db.query(Requirement).filter(
        Requirement.tender_document_id == document_id
    ).delete(synchronize_session=False)

    # 先提交 DB 删除，再删物理文件：避免 commit 失败导致文件已丢而 DB 记录残留
    db.delete(doc)
    db.commit()
    try:
        file_storage_service.delete_file(file_path)
    except Exception:
        # 文件残留可由后台 GC 兜底，DB 一致性已由 commit 保证
        pass

    return ApiResponse(data={"message": "删除成功"})
