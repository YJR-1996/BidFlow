import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.models.response import Response
from app.models.user import User
from app.schemas.response import ResponseResponse, SourceReference, UpdateResponseRequest
from app.services.llm_client import LlmServiceError, OpenAIChatClient
from app.services.response_generation_service import ResponseGenerationService

router = APIRouter(prefix="/responses", tags=["响应草稿"])


class GenerateDraftRequest(BaseModel):
    requirement_id: int
    sources: list[SourceReference] = Field(default_factory=list)


async def _owned_requirement(requirement_id: int, user: User, session: AsyncSession) -> Requirement:
    result = await session.execute(select(Requirement).join(BidProject).where(Requirement.id == requirement_id, BidProject.owner_id == str(user.id)))
    requirement = result.scalar_one_or_none()
    if requirement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "需求项不存在"})
    return requirement


@router.post("/generate", response_model=ResponseResponse)
async def generate_draft(body: GenerateDraftRequest, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    requirement = await _owned_requirement(body.requirement_id, user, session)
    sources = [item.model_dump() for item in body.sources]
    if not sources:
        content, draft_status = "待人工补充：未检索到可引用的企业资料。", "needs_manual"
    else:
        generator = ResponseGenerationService(OpenAIChatClient(settings.DASHSCOPE_API_KEY))
        try:
            generated = generator.generate({"requirement_id": requirement.id, "content": requirement.content}, sources)
        except LlmServiceError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "LLM_UNAVAILABLE", "message": str(exc)}) from exc
        content, draft_status = generated.content, generated.status
    response = (await session.execute(select(Response).where(Response.requirement_id == requirement.id))).scalar_one_or_none()
    if response is None:
        response = Response(requirement_id=requirement.id)
        session.add(response)
    response.ai_content = content
    response.source_refs = json.dumps(sources, ensure_ascii=False)
    response.status = draft_status
    await session.commit()
    await session.refresh(response)
    return response


@router.get("/{requirement_id}", response_model=ResponseResponse)
async def get_draft(requirement_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    requirement = await _owned_requirement(requirement_id, user, session)
    response = (await session.execute(select(Response).where(Response.requirement_id == requirement.id))).scalar_one_or_none()
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "尚未生成响应草稿"})
    return response


@router.patch("/{requirement_id}", response_model=ResponseResponse)
async def update_draft(requirement_id: int, body: UpdateResponseRequest, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    requirement = await _owned_requirement(requirement_id, user, session)
    response = (await session.execute(select(Response).where(Response.requirement_id == requirement.id))).scalar_one_or_none()
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "尚未生成响应草稿"})
    if body.edited_content is not None:
        response.edited_content = body.edited_content.strip()
    if body.status is not None:
        if body.status == "completed" and not response.source_refs:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "SOURCE_REQUIRED", "message": "没有来源的草稿不能标记为 completed"})
        response.status = body.status
    await session.commit()
    await session.refresh(response)
    return response
