"""AI 对话路由 - 项目级 AI 助手（对话编排 / function calling / 工具调用）"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.bid_project import BidProject
from app.schemas.common import ApiResponse
from app.api.deps import get_current_user
from app.core.exceptions import NotFoundException
from app.services.chat_service import chat_service

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.post("/projects/{project_id}/chat", response_model=ApiResponse[dict])
def chat_with_agent(
    project_id: int,
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """与项目 AI 助手对话（多轮，会话按 项目+用户 内存保存）。"""
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    message = (request.message or "").strip()
    if not message:
        raise NotFoundException(message="消息不能为空")

    result = chat_service.chat(
        project_id=project_id,
        owner_id=str(current_user.id),
        user_message=message,
        db=db,
    )
    return ApiResponse(data=result)
