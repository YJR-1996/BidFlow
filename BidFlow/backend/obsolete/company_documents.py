"""[OBSOLETE] 本文件已迁移至 knowledge.py 路由。
保留仅供历史参考，不再被主路由引用。"""
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db, get_current_user
from app.models.user import User
from app.models.company_document import CompanyDocument
from app.schemas.company_document import CompanyDocumentResponse
from app.schemas.common import ApiResponse
from app.services.company_material_service import CompanyMaterialService

router = APIRouter()


@router.post("", response_model=ApiResponse[CompanyDocumentResponse])
async def upload_material(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传公司资料"""
    svc = CompanyMaterialService()
    doc = svc.upload_and_process(db=db, user=current_user, file=file)
    return ApiResponse(data=doc)


@router.get("", response_model=ApiResponse[List[CompanyDocumentResponse]])
def list_materials(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出公司资料"""
    svc = CompanyMaterialService()
    docs = svc.list_by_owner(db=db, user=current_user)
    return ApiResponse(data=docs)


@router.delete("", response_model=ApiResponse[dict])
def delete_material(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除公司资料"""
    svc = CompanyMaterialService()
    doc = db.query(CompanyDocument).filter(
        CompanyDocument.id == id,
        CompanyDocument.owner_id == current_user.id,
    ).first()
    if not doc:
        from app.core.exceptions import NotFoundException
        raise NotFoundException(message="资料不存在")
    svc.delete(db=db, doc=doc)
    return ApiResponse(data={"message": "删除成功"})
