from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.models.compliance_issue import ComplianceIssue
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectListItem, ProjectDetail
from app.schemas.common import ApiResponse
from app.api.deps import get_current_user, get_project_or_404_sync

router = APIRouter()


@router.get("", response_model=ApiResponse[List[ProjectListItem]])
def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(BidProject).filter(BidProject.owner_id == current_user.id)
    if status:
        query = query.filter(BidProject.status == status)

    total = query.count()
    projects = query.order_by(BidProject.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for project in projects:
        req_count = db.query(Requirement).filter(Requirement.project_id == project.id).count()
        risk_count = db.query(ComplianceIssue).filter(
            ComplianceIssue.project_id == project.id,
            ComplianceIssue.level.in_(["高", "中"]),
        ).count()
        completed = db.query(Requirement).filter(
            Requirement.project_id == project.id,
            Requirement.status == "已完成",
        ).count()
        completion_rate = round(completed / req_count * 100, 1) if req_count > 0 else 0.0

        item = ProjectListItem.model_validate(project)
        item.requirement_count = req_count
        item.risk_count = risk_count
        item.completion_rate = completion_rate
        result.append(item)

    return ApiResponse(data=result)


@router.post("", response_model=ApiResponse[ProjectDetail])
def create_project(
    request: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = BidProject(
        owner_id=current_user.id,
        name=request.name,
        tenderer=request.tenderer,
        deadline=request.deadline,
        budget=request.budget,
        description=request.description,
        status="准备中",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return ApiResponse(data=project)


@router.get("/{project_id}", response_model=ApiResponse[ProjectDetail])
def get_project(project: BidProject = Depends(get_project_or_404_sync)):
    return ApiResponse(data=project)


@router.patch("/{project_id}", response_model=ApiResponse[ProjectDetail])
def update_project(
    request: ProjectUpdate,
    project: BidProject = Depends(get_project_or_404_sync),
    db: Session = Depends(get_db),
):
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return ApiResponse(data=project)


@router.delete("/{project_id}", response_model=ApiResponse[dict])
def delete_project(
    project: BidProject = Depends(get_project_or_404_sync),
    db: Session = Depends(get_db),
):
    db.delete(project)
    db.commit()
    return ApiResponse(data={"message": "删除成功"})
