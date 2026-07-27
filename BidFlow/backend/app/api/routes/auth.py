from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.exceptions import ValidationException, UnauthorizedException
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from app.schemas.common import ApiResponse
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/register", response_model=ApiResponse[UserResponse])
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == request.username).first()
    if existing:
        raise ValidationException(message="用户名已存在")

    user = User(
        username=request.username,
        password_hash=hash_password(request.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return ApiResponse(data=user)


@router.post("/login", response_model=ApiResponse[TokenResponse])
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise UnauthorizedException(message="用户名或密码错误")

    access_token = create_access_token(user.id)
    return ApiResponse(data=TokenResponse(access_token=access_token))


@router.get("/me", response_model=ApiResponse[UserResponse])
def get_me(current_user: User = Depends(get_current_user)):
    return ApiResponse(data=current_user)
