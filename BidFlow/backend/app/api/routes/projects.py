import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.models.compliance_issue import ComplianceIssue
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectListItem, ProjectDetail
from app.schemas.common import ApiResponse
from app.api.deps import get_current_user, get_project_or_404_sync
from app.services.readiness_service import readiness_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=ApiResponse[List[ProjectListItem]])
def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(BidProject).filter(BidProject.owner_id == current_user.id)
    if status:
        query = query.filter(BidProject.status == status)

    total = query.count()
    projects = query.order_by(BidProject.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for project in projects:
        req_count = db.query(Requirement).filter(Requirement.project_id == project.id).count()

        try:
            # 统一口径：待处理风险 = 高/中 + status='未处理'
            # 与合规报告、详情顶部 high_risk_pending 语义一致
            risk_count = db.query(ComplianceIssue).filter(
                ComplianceIssue.project_id == project.id,
                ComplianceIssue.level.in_(["高", "中"]),
                ComplianceIssue.status == "未处理",
            ).count()
        except OperationalError as e:
            if "Unknown column" in str(e):
                logger.warning(
                    "[projects] 数据库表结构缺失列: %s。"
                    "请运行 python -m app.scripts.migrate_compliance_source 修复", e
                )
                risk_count = 0
            else:
                raise

        # 使用 readiness_service 计算综合就绪度（单一数据源）
        try:
            r = readiness_service.calculate(project.id, db)
            completion_rate = r.overall
        except OperationalError as e:
            if "Unknown column" in str(e):
                logger.warning("[projects] 就绪度计算遇到缺列问题: %s", e)
                completion_rate = 0.0
            else:
                raise

        item = ProjectListItem.model_validate(project)
        item.requirement_count = req_count
        item.risk_count = risk_count
        item.completion_rate = completion_rate
        result.append(item)

    return ApiResponse(data=result)


@router.post("", response_model=ApiResponse[ProjectDetail])
def create_project(
    request: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = BidProject(
        owner_id=current_user.id,
        name=request.name,
        tenderer=request.tenderer,
        deadline=request.deadline,
        budget=request.budget,
        description=request.description,
        status="准备中",
    )

    # 生成项目编号（BF-2026-U3-001）：并发下唯一索引冲突则重试
    from app.services.project_number_service import generate_tender_no
    from sqlalchemy.exc import IntegrityError

    for attempt in range(3):
        project.tender_no = generate_tender_no(db, current_user.id)
        db.add(project)
        try:
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if attempt == 2:
                raise
            # 唯一冲突 → 重新计算流水号再试
    db.refresh(project)

    return ApiResponse(data=project)


@router.get("/{project_id}", response_model=ApiResponse[ProjectDetail])
def get_project(
    project: BidProject = Depends(get_project_or_404_sync),
    db: Session = Depends(get_db),
):
    """获取项目详情，含三维就绪度数据"""
    r = readiness_service.calculate(project.id, db)
    detail = ProjectDetail.model_validate(project)
    detail.completion_rate = r.overall
    detail.readiness = {
        "base_rate": r.base_rate,
        "quality_rate": r.quality_rate,
        "compliance_rate": r.compliance_rate,
        "overall": r.overall,
        "has_response": r.has_response,
        "has_source": r.has_source,
        "high_risk_pending": r.high_risk_pending,
        "medium_risk_pending": r.medium_risk_pending,
        "total_risk_pending": r.total_risk_pending,
        "can_submit": r.can_submit,
    }
    return ApiResponse(data=detail)


@router.patch("/{project_id}", response_model=ApiResponse[ProjectDetail])
def update_project(
    request: ProjectUpdate,
    project: BidProject = Depends(get_project_or_404_sync),
    db: Session = Depends(get_db),
):
    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return ApiResponse(data=project)


@router.delete("/{project_id}", response_model=ApiResponse[dict])
def delete_project(
    project: BidProject = Depends(get_project_or_404_sync),
    db: Session = Depends(get_db),
):
    db.delete(project)
    db.commit()
    return ApiResponse(data={"message": "删除成功"})
