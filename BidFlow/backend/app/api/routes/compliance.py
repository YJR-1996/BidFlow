import json

from fastapi import APIRouter, Depends, HTTPException, Response as HttpResponse, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.bid_project import BidProject
from app.models.compliance_issue import ComplianceIssue
from app.models.requirement import Requirement
from app.models.response import Response
from app.models.user import User
from app.schemas.compliance import ComplianceReportResponse
from app.services.compliance_checker import ComplianceChecker, RequirementSnapshot
from app.services.report_service import ReportService

router = APIRouter(prefix="/compliance", tags=["合规核查"])


async def _owned_project(project_id: int, user: User, session: AsyncSession) -> BidProject:
    project = (await session.execute(select(BidProject).where(BidProject.id == project_id, BidProject.owner_id == str(user.id)))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "项目不存在"})
    return project


async def _check(project: BidProject, session: AsyncSession):
    rows = (await session.execute(select(Requirement, Response).outerjoin(Response, Response.requirement_id == Requirement.id).where(Requirement.project_id == project.id))).all()
    snapshots = []
    for requirement, response in rows:
        sources = []
        if response and response.source_refs:
            try:
                sources = json.loads(response.source_refs)
            except json.JSONDecodeError:
                sources = []
        snapshots.append(RequirementSnapshot(requirement.id, requirement.content, requirement.priority, (response.edited_content or response.ai_content) if response else "", sources, response.status if response else "needs_manual"))
    checker = ComplianceChecker()
    issues = checker.check(snapshots)
    await session.execute(delete(ComplianceIssue).where(ComplianceIssue.project_id == project.id))
    for issue in issues:
        session.add(ComplianceIssue(project_id=project.id, requirement_id=issue.requirement_id, level={"high": "高", "medium": "中", "low": "低"}[issue.level], rule_code=issue.rule_code, description=issue.description, suggestion=issue.suggestion, status="未处理"))
    await session.commit()
    return ReportService().build(snapshots, issues)


@router.post("/projects/{project_id}/run", response_model=ComplianceReportResponse)
async def run_check(project_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    project = await _owned_project(project_id, user, session)
    report = await _check(project, session)
    issues = (await session.execute(select(ComplianceIssue).where(ComplianceIssue.project_id == project.id))).scalars().all()
    return ComplianceReportResponse(project_id=project.id, total_requirements=report.total_requirements, completed_count=report.completed_requirements, pending_review_count=report.total_requirements - report.completed_requirements, risk_count=len(issues), completion_rate=report.completion_rate, high_risks=[x for x in issues if x.level == "高"], medium_risks=[x for x in issues if x.level == "中"], low_risks=[x for x in issues if x.level == "低"])


@router.get("/projects/{project_id}/report", response_model=ComplianceReportResponse)
async def get_report(project_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await run_check(project_id, user, session)


@router.get("/projects/{project_id}/report.md")
async def export_markdown(project_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    project = await _owned_project(project_id, user, session)
    report = await _check(project, session)
    return HttpResponse(ReportService().to_markdown(report), media_type="text/markdown; charset=utf-8")
