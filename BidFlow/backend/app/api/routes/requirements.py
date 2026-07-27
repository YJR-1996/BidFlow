from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.schemas.requirement import RequirementUpdate, RequirementResponse
from app.schemas.common import ApiResponse
from app.api.deps import get_current_user, get_project_or_404
from app.core.exceptions import NotFoundException

router = APIRouter()


@router.get("/projects/{project_id}/requirements", response_model=ApiResponse[List[RequirementResponse]])
def list_requirements(
    project: BidProject = Depends(get_project_or_404),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Requirement).filter(Requirement.project_id == project.id)

    if category:
        query = query.filter(Requirement.category == category)
    if status:
        query = query.filter(Requirement.status == status)
    if priority:
        query = query.filter(Requirement.priority == priority)
    if keyword:
        query = query.filter(Requirement.content.contains(keyword))

    requirements = query.order_by(Requirement.priority, Requirement.created_at.desc()).all()
    return ApiResponse(data=requirements)


@router.get("/requirements/{requirement_id}", response_model=ApiResponse[RequirementResponse])
def get_requirement(
    requirement_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise NotFoundException(message="需求项不存在")

    project = db.query(BidProject).filter(BidProject.id == req.project_id).first()
    if not project or project.owner_id != current_user.id:
        raise NotFoundException(message="需求项不存在")

    return ApiResponse(data=req)


@router.patch("/requirements/{requirement_id}", response_model=ApiResponse[RequirementResponse])
def update_requirement(
    requirement_id: int,
    request: RequirementUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise NotFoundException(message="需求项不存在")

    project = db.query(BidProject).filter(BidProject.id == req.project_id).first()
    if not project or project.owner_id != current_user.id:
        raise NotFoundException(message="需求项不存在")

    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(req, key, value)

    db.commit()
    db.refresh(req)
    return ApiResponse(data=req)
