from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.api.deps import get_current_user

router = APIRouter()


@router.get("", response_model=ApiResponse[list])
def list_company_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ApiResponse(data=[])
