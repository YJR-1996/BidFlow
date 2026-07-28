"""合规核查路由 - 项目合规检查与报告"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.models.compliance_issue import ComplianceIssue
from app.schemas.common import ApiResponse
from app.schemas.compliance import ComplianceReportResponse
from app.schemas.requirement import RequirementResponse
from app.api.deps import get_current_user, get_project_or_404_sync
from app.core.exceptions import NotFoundException, BusinessException
from app.services.compliance_checker import ComplianceChecker, RequirementSnapshot
from app.services.report_service import ReportService

router = APIRouter()


@router.post("/{project_id}/compliance-check", response_model=ApiResponse[dict])
def run_compliance_check(
    project_id: int,
    project: BidProject = Depends(get_project_or_404_sync),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """运行合规核查，将问题写入 compliance_issues 表"""
    # 先清除旧的合规问题
    db.query(ComplianceIssue).filter(
        ComplianceIssue.project_id == project_id
    ).delete()
    db.commit()

    # 获取所有需求项
    requirements = db.query(Requirement).filter(
        Requirement.project_id == project_id
    ).all()

    if not requirements:
        raise BusinessException(message="该项目暂无需求项，请先解析招标文件")

    # 构建快照
    snapshots: list[RequirementSnapshot] = []
    for req in requirements:
        # 尝试获取响应内容（优先 edited_content，其次 ai_content）
        resp_content = ""
        if hasattr(req, 'responses') and req.responses:
            for r in req.responses:
                if r.edited_content:
                    resp_content = r.edited_content
                    break
                if r.ai_content:
                    resp_content = r.ai_content
                    break
            # 兼容 ORM 中 responses 可能是 lazy-loaded 列表
            try:
                src = r.source_refs or ""
            except Exception:
                src = ""
        snapshots.append(RequirementSnapshot(
            requirement_id=req.id,
            content=req.content or "",
            priority=req.priority or "P2",
            response_content=resp_content,
            source_refs=[],
            status=req.status or "pending",
        ))

    # 执行核查
    checker = ComplianceChecker()
    report_service = ReportService()
    report = report_service.build(snapshots, checker.check(snapshots))

    # 持久化合规问题
    for issue in report.issues:
        ci = ComplianceIssue(
            project_id=project_id,
            requirement_id=issue.requirement_id,
            level={"high": "高", "medium": "中", "low": "低"}.get(issue.level, "低"),
            rule_code=issue.rule_code,
            description=issue.description,
            suggestion=issue.suggestion,
            status="未处理",
        )
        db.add(ci)
    db.commit()

    return ApiResponse(data={
        "message": "合规核查完成",
        "total_requirements": report.total_requirements,
        "completed_requirements": report.completed_requirements,
        "completion_rate": report.completion_rate,
        "high_risk_count": report.high_risk_count,
        "medium_risk_count": report.medium_risk_count,
        "low_risk_count": report.low_risk_count,
        "issue_count": len(report.issues),
    })


@router.get("/{project_id}/compliance-report", response_model=ApiResponse[ComplianceReportResponse])
def get_compliance_report(
    project_id: int,
    project: BidProject = Depends(get_project_or_404_sync),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取项目的合规报告"""
    issues = db.query(ComplianceIssue).filter(
        ComplianceIssue.project_id == project_id
    ).all()

    high_risks = [i for i in issues if i.level == "高"]
    medium_risks = [i for i in issues if i.level == "中"]
    low_risks = [i for i in issues if i.level == "低"]

    total_req = db.query(Requirement).filter(
        Requirement.project_id == project_id
    ).count()

    completed_req = db.query(Requirement).filter(
        Requirement.project_id == project_id,
        Requirement.status == "已完成",
    ).count()

    completion_rate = round(completed_req / total_req * 100, 1) if total_req > 0 else 0.0

    pending_review = db.query(Requirement).filter(
        Requirement.project_id == project_id,
        Requirement.status == "待评审",
    ).count()

    return ApiResponse(data=ComplianceReportResponse(
        project_id=project_id,
        total_requirements=total_req,
        completed_count=completed_req,
        pending_review_count=pending_review,
        risk_count=len(issues),
        completion_rate=completion_rate,
        high_risks=high_risks,
        medium_risks=medium_risks,
        low_risks=low_risks,
    ))
