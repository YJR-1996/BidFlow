from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenException, NotFoundException, http_exception
from app.core.security import decode_access_token
from app.db.session import get_db, get_session
from app.models.user import User
from app.models.bid_project import BidProject


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """从 Authorization: Bearer Token 中解析当前用户"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing or invalid authorization header"},
        )

    token = auth_header.split(" ", 1)[1]
    try:
        user_id = decode_access_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid or expired token"},
        )

    stmt = select(User).where(User.id == str(user_id))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "User not found"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "User is inactive"},
        )
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """确保当前用户处于激活状态"""
    if not current_user.is_active:
        raise http_exception(ForbiddenException("User is inactive"))
    return current_user


async def get_project_or_404(
    project_id,  # FastAPI 从 URL 路径参数自动解析
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> BidProject:
    """获取项目或返回 404（异步版本，用于使用 get_session 的路由）"""
    stmt = select(BidProject).where(BidProject.id == project_id, BidProject.owner_id == current_user.id)
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise http_exception(NotFoundException("项目不存在或无权限"))
    return project


def get_project_or_404_sync(
    project_id,  # FastAPI 从 URL 路径参数自动解析
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BidProject:
    """获取项目或返回 404（同步版本，用于使用 get_db 的路由）"""
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise http_exception(NotFoundException("项目不存在或无权限"))
    return project
