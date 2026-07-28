"""响应草稿路由 - AI 生成、获取、更新"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional, List

from app.db.session import get_db
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.models.response import Response as BidResponse
from app.schemas.common import ApiResponse
from app.schemas.response import DraftResponseRequest, UpdateResponseRequest, ResponseResponse, DraftResponsePayload
from app.api.deps import get_current_user, get_project_or_404
from app.core.exceptions import NotFoundException, BusinessException

router = APIRouter()


@router.post("/{requirement_id}/response/generate", response_model=ApiResponse[DraftResponsePayload])
def generate_response_draft(
    requirement_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """为指定需求项生成 AI 响应草稿"""
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise NotFoundException(message="需求项不存在")

    project = db.query(BidProject).filter(
        BidProject.id == req.project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="需求项不存在或无权限")

    # 先检查已有草稿
    existing = db.query(BidResponse).filter(
        BidResponse.requirement_id == requirement_id
    ).first()

    if existing:
        return ApiResponse(data=DraftResponsePayload(
            content=existing.edited_content or existing.ai_content or "",
            source_refs=[],
            status=existing.status,
            message="已存在草稿，无需重新生成",
        ))

    # 尝试检索相关企业资料
    try:
        from app.services.retrieval_service import retrieval_service
        from app.core.config import settings

        sources = retrieval_service.search(
            query=req.content,
            project_id=project.id,
            top_k=5,
        )
        source_dicts = [s.model_dump() for s in sources] if sources else []
    except Exception:
        # 如果检索失败，使用空 sources
        source_dicts = []

    if not source_dicts:
        # 没有可引用的资料，直接返回人工提示
        payload = DraftResponsePayload(
            content="待人工补充：未检索到可引用的企业资料。",
            source_refs=[],
            status="needs_manual",
            message="缺少可引用资料",
        )
        resp = BidResponse(
            requirement_id=requirement_id,
            ai_content=payload.content,
            status=payload.status,
        )
        db.add(resp)
        db.commit()
        return ApiResponse(data=payload)

    # TODO: 调用 LLM 生成草稿
    # 当前返回一个占位内容，实际项目中需要接入 LLM
    content = (
        f"根据招标文件要求，我方完全响应该条款。\n\n"
        f"需求内容：{req.content}\n\n"
        f"具体方案：\n"
        f"1. 资质方面：我方具备符合要求的全部资质证明\n"
        f"2. 技术方面：采用行业领先的技术方案\n"
        f"3. 商务方面：报价合理，条款响应无偏差\n"
        f"4. 资料来源：已检索到 {len(source_dicts)} 条可引用企业资料"
    )

    payload = DraftResponsePayload(
        content=content,
        source_refs=source_dicts,
        status="pending_review",
        message="草稿已生成，等待人工审核",
    )
    resp = BidResponse(
        requirement_id=requirement_id,
        ai_content=content,
        source_refs=str(source_dicts),
        status=payload.status,
    )
    db.add(resp)
    db.commit()

    return ApiResponse(data=payload)


@router.get("/{requirement_id}/response", response_model=ApiResponse[ResponseResponse])
def get_response_draft(
    requirement_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定需求项的响应草稿"""
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise NotFoundException(message="需求项不存在")

    project = db.query(BidProject).filter(
        BidProject.id == req.project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="需求项不存在或无权限")

    resp = db.query(BidResponse).filter(
        BidResponse.requirement_id == requirement_id
    ).first()

    if not resp:
        raise NotFoundException(message="暂无响应草稿，请先生成")

    return ApiResponse(data=resp)


@router.patch("/{requirement_id}/response", response_model=ApiResponse[DraftResponsePayload])
def update_response_draft(
    requirement_id: int,
    request: UpdateResponseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新响应草稿（编辑内容或审核状态）"""
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise NotFoundException(message="需求项不存在")

    project = db.query(BidProject).filter(
        BidProject.id == req.project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="需求项不存在或无权限")

    resp = db.query(BidResponse).filter(
        BidResponse.requirement_id == requirement_id
    ).first()

    if not resp:
        raise NotFoundException(message="暂无响应草稿")

    if request.edited_content is not None:
        resp.edited_content = request.edited_content.strip()
    if request.status is not None:
        resp.status = request.status

    db.commit()
    db.refresh(resp)

    return ApiResponse(data=DraftResponsePayload(
        content=resp.edited_content or resp.ai_content or "",
        source_refs=[],
        status=resp.status,
        message="草稿已保存",
    ))
