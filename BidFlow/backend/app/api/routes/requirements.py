from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_project_or_404
from app.db.session import get_session
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.requirement import RequirementResponse, RequirementUpdate

router = APIRouter()


async def _get_requirement_or_404(requirement_id: int, current_user: User, session: AsyncSession) -> Requirement:
    result = await session.execute(
        select(Requirement).join(BidProject).where(
            Requirement.id == requirement_id,
            BidProject.owner_id == str(current_user.id),
        )
    )
    requirement = result.scalar_one_or_none()
    if requirement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "需求项不存在"})
    return requirement


@router.get("/projects/{project_id}/requirements", response_model=ApiResponse[List[RequirementResponse]])
async def list_requirements(
    project: BidProject = Depends(get_project_or_404),
    category: str | None = Query(None),
    status: str | None = Query(None),
    priority: str | None = Query(None),
    keyword: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Requirement).where(Requirement.project_id == project.id)
    if category:
        stmt = stmt.where(Requirement.category == category)
    if status:
        stmt = stmt.where(Requirement.status == status)
    if priority:
        stmt = stmt.where(Requirement.priority == priority)
    if keyword:
        stmt = stmt.where(Requirement.content.contains(keyword))
    requirements = (await session.execute(stmt.order_by(Requirement.priority, Requirement.created_at.desc()))).scalars().all()
    return ApiResponse(data=requirements)


@router.get("/requirements/{requirement_id}", response_model=ApiResponse[RequirementResponse])
async def get_requirement(
    requirement_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return ApiResponse(data=await _get_requirement_or_404(requirement_id, current_user, session))


@router.patch("/requirements/{requirement_id}", response_model=ApiResponse[RequirementResponse])
async def update_requirement(
    requirement_id: int,
    request: RequirementUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    requirement = await _get_requirement_or_404(requirement_id, current_user, session)
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(requirement, key, value)
    await session.commit()
    await session.refresh(requirement)
    return ApiResponse(data=requirement)
