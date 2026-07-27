from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import decode_access_token
from app.core.exceptions import UnauthorizedException, NotFoundException, ForbiddenException
from app.models.user import User
from app.models.bid_project import BidProject

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    user_id = decode_access_token(token)
    if user_id is None:
        raise UnauthorizedException(message="无效的访问令牌")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise UnauthorizedException(message="用户不存在")

    return user


def get_project_or_404(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BidProject:
    project = db.query(BidProject).filter(BidProject.id == project_id).first()
    if project is None:
        raise NotFoundException(message="项目不存在")
    if project.owner_id != current_user.id:
        raise ForbiddenException(message="无权限访问该项目")
    return project
