from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.models.response import Response as BidResponse
from app.models.compliance_issue import ComplianceIssue
from app.schemas.requirement import (
    RequirementUpdate, RequirementResponse,
    AuxGenerateRequest, AuxGenerateResponse, AuxGenerateItem,
)
from app.schemas.common import ApiResponse
from app.api.deps import get_current_user, get_project_or_404_sync
from app.core.exceptions import NotFoundException, BusinessException
from app.services.auxiliary_requirement_service import auxiliary_requirement_service

router = APIRouter()


@router.get("/projects/{project_id}/requirements", response_model=ApiResponse[List[RequirementResponse]])
def list_requirements(
    project: BidProject = Depends(get_project_or_404_sync),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Requirement).filter(Requirement.project_id == project.id)

    if category:
        query = query.filter(Requirement.category == category)
    if status:
        query = query.filter(Requirement.status == status)
    if priority:
        query = query.filter(Requirement.priority == priority)
    if keyword:
        query = query.filter(Requirement.content.contains(keyword))

    requirements = query.order_by(Requirement.priority, Requirement.created_at.desc()).all()

    # 批量获取每个需求的最新响应状态，避免 N+1 查询
    if requirements:
        req_ids = [r.id for r in requirements]
        # 对每个需求取最新一条响应
        from sqlalchemy import func
        latest_resp_subquery = db.query(
            BidResponse.requirement_id,
            func.max(BidResponse.id).label('max_id')
        ).filter(
            BidResponse.requirement_id.in_(req_ids)
        ).group_by(BidResponse.requirement_id).subquery()

        latest_resps = db.query(BidResponse).filter(
            BidResponse.id.in_(
                db.query(latest_resp_subquery.c.max_id)
            )
        ).all()

        resp_status_map = {r.requirement_id: r.status for r in latest_resps}
        resp_content_map = {r.requirement_id: (r.edited_content or r.ai_content or "") for r in latest_resps}

        result = []
        for req in requirements:
            resp_status = resp_status_map.get(req.id)
            resp_content = resp_content_map.get(req.id, "")
            setattr(req, 'response_status', resp_status)
            setattr(req, 'has_response', bool(resp_content))
            result.append(req)
        return ApiResponse(data=result)

    return ApiResponse(data=requirements)


@router.get("/requirements/{requirement_id}", response_model=ApiResponse[RequirementResponse])
def get_requirement(
    requirement_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise NotFoundException(message="需求项不存在")

    project = db.query(BidProject).filter(BidProject.id == req.project_id).first()
    if not project or project.owner_id != current_user.id:
        raise NotFoundException(message="需求项不存在")

    # 获取最新响应状态
    from sqlalchemy import func
    latest_resp = db.query(BidResponse).filter(
        BidResponse.requirement_id == requirement_id
    ).order_by(BidResponse.id.desc()).first()

    if latest_resp:
        setattr(req, 'response_status', latest_resp.status)
        setattr(req, 'has_response', bool(latest_resp.edited_content or latest_resp.ai_content))
    else:
        setattr(req, 'response_status', None)
        setattr(req, 'has_response', False)

    return ApiResponse(data=req)


@router.patch("/requirements/{requirement_id}", response_model=ApiResponse[RequirementResponse])
def update_requirement(
    requirement_id: int,
    request: RequirementUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise NotFoundException(message="需求项不存在")

    project = db.query(BidProject).filter(BidProject.id == req.project_id).first()
    if not project or project.owner_id != current_user.id:
        raise NotFoundException(message="需求项不存在")

    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(req, key, value)

    db.commit()
    db.refresh(req)
    return ApiResponse(data=req)


@router.post(
    "/projects/{project_id}/requirements/aux-generate",
    response_model=ApiResponse[AuxGenerateResponse],
)
def generate_auxiliary_requirements(
    project: BidProject = Depends(get_project_or_404_sync),
    request: AuxGenerateRequest = ...,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """基于已解析的需求项，AI 派生辅助需求项

    仅项目所有者可调用（通过 get_project_or_404_sync 已校验 owner_id）。
    预留 require_role 接入点（如需后续引入 RBAC）。
    """
    aux_items = auxiliary_requirement_service.generate(
        db=db,
        project_id=project.id,
        tender_document_id=request.tender_document_id,
        max_items=request.max_items,
    )

    items = [
        AuxGenerateItem(
            id=r.id,
            content=r.content,
            category=r.category,
            priority=r.priority,
            source="ai_aux",
        )
        for r in aux_items
    ]

    # 判断是否为跳过已有项的场景
    skipped_existing = len(aux_items) > 0 and all(
        r.source == "ai_aux" and hasattr(r, "source_ref") and r.source_ref == "ai_aux"
        for r in aux_items
    )

    return ApiResponse(
        data=AuxGenerateResponse(
            generated_count=len(items),
            skipped_existing=skipped_existing,
            items=items,
        )
    )


@router.delete("/requirements/projects/{project_id}/batch", response_model=ApiResponse)
def batch_delete_requirements(
    project_id: int,
    payload: dict = Body(..., description="批量删除请求体，包含 ids 列表"),
    project: BidProject = Depends(get_project_or_404_sync),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批量删除指定项目下的需求项

    仅项目所有者可调用（通过 get_project_or_404_sync 已校验 owner_id）。
    同时级联删除关联的响应草稿。
    """
    ids = payload.get("ids", [])
    if not ids:
        raise BusinessException(message="请选择要删除的需求项")

    # 安全校验：只保留属于当前项目的 id，防止越权删除他人项目的关联数据
    valid_ids = [
        r.id for r in db.query(Requirement.id).filter(
            Requirement.project_id == project.id,
            Requirement.id.in_(ids),
        ).all()
    ]
    if not valid_ids:
        raise BusinessException(message="未找到可删除的需求项")

    # 级联删除关联响应草稿（仅限本项目下的需求）
    db.query(BidResponse).filter(
        BidResponse.requirement_id.in_(valid_ids),
    ).delete(synchronize_session=False)

    # 级联删除合规问题
    db.query(ComplianceIssue).filter(
        ComplianceIssue.requirement_id.in_(valid_ids),
    ).delete(synchronize_session=False)

    # H4：级联删除比对分析详情（FK 无 ondelete，必须先删，否则删需求时 IntegrityError 500）
    from app.models.match_analysis import MatchAnalysisDetail
    db.query(MatchAnalysisDetail).filter(
        MatchAnalysisDetail.requirement_id.in_(valid_ids),
    ).delete(synchronize_session=False)

    # 清理补救动作孤儿记录（无 FK 约束不会报错，但避免脏数据残留）
    from app.models.remediation_action import RemediationAction
    db.query(RemediationAction).filter(
        RemediationAction.requirement_id.in_(valid_ids),
    ).delete(synchronize_session=False)

    # 删除需求项
    db.query(Requirement).filter(
        Requirement.project_id == project.id,
        Requirement.id.in_(valid_ids),
    ).delete(synchronize_session=False)

    db.commit()
    return ApiResponse(data={"deleted": len(valid_ids)})


@router.patch("/requirements/projects/{project_id}/batch-status", response_model=ApiResponse)
def batch_update_status(
    project_id: int,
    payload: dict = Body(..., description="批量更新请求体，包含 status 和可选 ids"),
    project: BidProject = Depends(get_project_or_404_sync),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批量更新指定项目下需求项的状态

    仅项目所有者可调用（通过 get_project_or_404_sync 已校验 owner_id）。
    可选传入 ids 列表（为空则更新全项目的需求）。
    """
    new_status = payload.get("status")
    if not new_status:
        raise BusinessException(message="请指定目标状态")

    ids = payload.get("ids")

    query = db.query(Requirement).filter(Requirement.project_id == project.id)
    if ids:
        query = query.filter(Requirement.id.in_(ids))

    n = query.update({"status": new_status}, synchronize_session=False)
    db.commit()
    return ApiResponse(data={"updated": n})
