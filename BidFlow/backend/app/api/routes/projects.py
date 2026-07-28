from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_project_or_404
from app.db.session import get_session
from app.models.bid_project import BidProject
from app.models.compliance_issue import ComplianceIssue
from app.models.requirement import Requirement
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectListItem, ProjectUpdate

router = APIRouter()


@router.get("", response_model=ApiResponse[List[ProjectListItem]])
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(BidProject).where(BidProject.owner_id == str(current_user.id))
    if status:
        stmt = stmt.where(BidProject.status == status)
    projects = (await session.execute(stmt.order_by(BidProject.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    result: list[ProjectListItem] = []
    for project in projects:
        requirement_count = await session.scalar(select(func.count()).select_from(Requirement).where(Requirement.project_id == project.id)) or 0
        completed = await session.scalar(select(func.count()).select_from(Requirement).where(Requirement.project_id == project.id, Requirement.status == "已完成")) or 0
        risk_count = await session.scalar(select(func.count()).select_from(ComplianceIssue).where(ComplianceIssue.project_id == project.id, ComplianceIssue.level.in_(["高", "中"]))) or 0
        item = ProjectListItem.model_validate(project)
        item.requirement_count = requirement_count
        item.risk_count = risk_count
        item.completion_rate = round(completed / requirement_count * 100, 1) if requirement_count else 0.0
        result.append(item)
    return ApiResponse(data=result)


@router.post("", response_model=ApiResponse[ProjectDetail])
async def create_project(
    request: ProjectCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = BidProject(owner_id=str(current_user.id), **request.model_dump(), status="准备中")
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return ApiResponse(data=project)


@router.get("/{project_id}", response_model=ApiResponse[ProjectDetail])
async def get_project(project: BidProject = Depends(get_project_or_404)):
    return ApiResponse(data=project)


@router.patch("/{project_id}", response_model=ApiResponse[ProjectDetail])
async def update_project(
    request: ProjectUpdate,
    project: BidProject = Depends(get_project_or_404),
    session: AsyncSession = Depends(get_session),
):
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    await session.commit()
    await session.refresh(project)
    return ApiResponse(data=project)


@router.delete("/{project_id}", response_model=ApiResponse[dict])
async def delete_project(
    project: BidProject = Depends(get_project_or_404),
    session: AsyncSession = Depends(get_session),
):
    await session.delete(project)
    await session.commit()
    return ApiResponse(data={"message": "删除成功"})
