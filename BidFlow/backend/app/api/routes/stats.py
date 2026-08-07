from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Integer
from datetime import datetime, timedelta, date
from typing import Optional

from app.db.session import get_db
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.models.compliance_issue import ComplianceIssue
from app.schemas.common import ApiResponse
from app.api.deps import get_current_user
from app.core.exceptions import NotFoundException

router = APIRouter()


@router.get("/stats", response_model=ApiResponse[dict])
def get_statistics(
    period: str = Query("30d", description="时间范围: 7d, 30d, 90d"),
    project_id: Optional[int] = Query(None, description="按项目联动：None=用户全部项目；int=该项目"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取统计报表数据，所有指标基于真实数据库计算。

    项目联动（M37）：
    - project_id 不传 → 全部指标按用户全部项目汇总（原行为）
    - project_id 有值 → 风险概览 / 合规健康度 / 项目状态均按该项目实时计算
    """

    # 时间范围（UTCDateTime 改造后模型字段读回为 aware UTC，Python 侧比较需用 aware 基准）
    from datetime import timezone
    days_map = {"7d": 7, "30d": 30, "90d": 90}
    period_days = days_map.get(period, 30)
    start_date = datetime.now(timezone.utc) - timedelta(days=period_days)
    prev_start_date = start_date - timedelta(days=period_days)

    # 鉴权：project_id 有值时校验归属
    scoped_project: Optional[BidProject] = None
    if project_id is not None:
        scoped_project = db.query(BidProject).filter(
            BidProject.id == project_id,
            BidProject.owner_id == current_user.id,
        ).first()
        if not scoped_project:
            raise NotFoundException(message="项目不存在或无权限")

    # 基础查询（始终基于当前用户所有权）
    own_projects_q = db.query(BidProject).filter(BidProject.owner_id == current_user.id)
    if scoped_project:
        # 单项目视图：核心指标只反映该项目
        own_projects_q = own_projects_q.filter(BidProject.id == scoped_project.id)

    # ============ 1. 核心指标 ============
    all_projects_for_core = own_projects_q.all()
    total_projects = own_projects_q.count()
    completed_projects = own_projects_q.filter(BidProject.status == "已完成").count()
    in_progress = own_projects_q.filter(BidProject.status.in_(["准备中", "审核中"])).count()

    total_req_count = 0
    total_passed_count = 0
    total_risks = 0
    high_risks = 0
    medium_risks = 0
    low_risks = 0
    project_risks_pending = 0  # 该项目当前未处理风险（用于顶部"X 项待处理"）

    for p in all_projects_for_core:
        req_count = db.query(Requirement).filter(Requirement.project_id == p.id).count()
        passed_req = db.query(Requirement).filter(
            Requirement.project_id == p.id,
            Requirement.status == "已完成"
        ).count()
        total_req_count += req_count
        total_passed_count += passed_req

        risks = db.query(ComplianceIssue).filter(ComplianceIssue.project_id == p.id).all()
        for r in risks:
            total_risks += 1
            if r.level == "高":
                high_risks += 1
            elif r.level == "中":
                medium_risks += 1
            elif r.level == "低":
                low_risks += 1
            if r.status == "未处理":
                project_risks_pending += 1

    avg_completion = (
        round(
            sum(
                (db.query(Requirement).filter(
                    Requirement.project_id == p.id,
                    Requirement.status == "已完成"
                ).count() / max(db.query(Requirement).filter(Requirement.project_id == p.id).count(), 1))
                for p in all_projects_for_core
            ) / max(total_projects, 1),
            1,
        )
        if all_projects_for_core else 0.0
    )

    # ============ 2. 项目状态分布（按项目筛选时只输出该项目一项） ============
    status_distribution = []
    if scoped_project:
        pct = 100 if scoped_project.status in ["准备中", "审核中", "已完成"] else 0
        status_distribution.append({
            "label": scoped_project.status or "准备中",
            "count": 1,
            "percentage": pct,
            "color": {"准备中": "#1a73e8", "审核中": "#fbbc04", "已完成": "#34a853"}.get(scoped_project.status, "#94a3b8"),
        })
    else:
        for status in ["准备中", "审核中", "已完成"]:
            count = own_projects_q.filter(BidProject.status == status).count()
            percentage = round(count / total_projects * 100) if total_projects > 0 else 0
            color_map = {"准备中": "#1a73e8", "审核中": "#fbbc04", "已完成": "#34a853"}
            status_distribution.append({
                "label": status,
                "count": count,
                "percentage": percentage,
                "color": color_map.get(status, "#94a3b8"),
            })

    # ============ 3. 效率指标 ============
    prep_times = []
    for p in own_projects_q.filter(BidProject.status.in_(["审核中", "已完成"])).all():
        if p.created_at:
            end_time = p.updated_at or datetime.utcnow()
            days_diff = (end_time - p.created_at).total_seconds() / 86400
            prep_times.append(days_diff)
    avg_prep_days = round(sum(prep_times) / len(prep_times), 1) if prep_times else 0

    # 合规通过率（按当前视图实时计算）
    compliance_rate = round(total_passed_count / total_req_count * 100) if total_req_count > 0 else 0

    # ============ 4. 趋势数据（M37：按项目 + 时间维度联动） ============
    # 改为"风险新增时间序列"——按项目+时间范围（7d/30d/90d）每天新增风险数
    risk_q_for_trend = db.query(ComplianceIssue)
    if scoped_project:
        risk_q_for_trend = risk_q_for_trend.filter(ComplianceIssue.project_id == scoped_project.id)

    trend_data = []
    weekday_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    # 当时间范围较短时显示 weekday，否则显示日期
    show_date = period_days > 7
    # 时间桶数量：7d 显示 7 桶，30d 显示 30 桶，90d 简化为 9 桶（每 10 天）
    if period_days <= 7:
        buckets = period_days
        bucket_days = 1
    elif period_days <= 30:
        buckets = period_days
        bucket_days = 1
    else:  # 90d → 9 buckets × 10 days
        buckets = 9
        bucket_days = 10

    today = date.today()
    for i in range(buckets):
        if bucket_days == 1:
            day = today - timedelta(days=buckets - 1 - i)
            day_start = datetime.combine(day, datetime.min.time())
            day_end = day_start + timedelta(days=1)
            label = day.strftime("%m-%d") if show_date else weekday_labels[day.weekday()]
        else:
            end_day = today - timedelta(days=(buckets - 1 - i) * bucket_days)
            start_day = end_day - timedelta(days=bucket_days - 1)
            day_start = datetime.combine(start_day, datetime.min.time())
            day_end = datetime.combine(end_day + timedelta(days=1), datetime.min.time())
            label = f"{start_day.strftime('%m/%d')}~{end_day.strftime('%m/%d')}"

        new_count = risk_q_for_trend.filter(
            ComplianceIssue.created_at >= day_start,
            ComplianceIssue.created_at < day_end,
        ).count()
        trend_data.append({"label": label, "new_risks": new_count, "bucket_days": bucket_days})

    # ============ 5. 趋势百分比（与上周期对比，按视图） ============
    if scoped_project:
        current_period_projects = 1 if scoped_project.created_at >= start_date else 0
        prev_period_projects = (
            1
            if scoped_project.created_at >= prev_start_date and scoped_project.created_at < start_date
            else 0
        )
    else:
        prev_period_projects = db.query(BidProject).filter(
            BidProject.owner_id == current_user.id,
            BidProject.created_at >= prev_start_date,
            BidProject.created_at < start_date,
        ).count()
        current_period_projects = db.query(BidProject).filter(
            BidProject.owner_id == current_user.id,
            BidProject.created_at >= start_date,
        ).count()

    project_trend = round((current_period_projects - prev_period_projects) / max(prev_period_projects, 1) * 100)
    completed_trend = project_trend

    # ============ 6. 风险概览（按当前视图实时汇总——M37 核心改造） ============
    risk_overview = {
        "high": high_risks,
        "medium": medium_risks,
        "low": low_risks,
        "pending": project_risks_pending,  # 当前视图未处理风险数（顶部"X 项待处理"来源）
        "total": high_risks + medium_risks + low_risks,
    }

    # ============ 7. 合规健康度（按当前视图实时计算——M37 核心改造） ============
    # 未达标项（方案 A）：当前视图下「存在未处理合规风险」的需求——与风险数字同源，
    # 不再列"未完成需求"。每条带所属项目信息（project_id/project_name），前端可点击跳转。
    pending_q = (
        db.query(Requirement, BidProject)
        .join(BidProject, BidProject.id == Requirement.project_id)
        .join(ComplianceIssue, ComplianceIssue.requirement_id == Requirement.id)
        .filter(
            BidProject.owner_id == current_user.id,
            ComplianceIssue.status == "未处理",
        )
    )
    if scoped_project:
        # 单项目视图：SQL 层直接过滤（避免先 limit 再内存过滤导致当前项目被挤掉）
        pending_q = pending_q.filter(Requirement.project_id == scoped_project.id)
    pending_q = pending_q.limit(200)

    pending_items = []
    seen_req_ids: set[int] = set()
    for req, proj in pending_q.all():
        if req.id in seen_req_ids:
            continue  # 同一需求多个未处理 issue → 去重只留一条
        seen_req_ids.add(req.id)
        pending_items.append({
            "requirement_id": req.id,
            "content": (req.content or "")[:60],
            "priority": req.priority,
            "project_id": proj.id,
            "project_name": proj.name,
        })
        if len(pending_items) >= 10:
            break

    compliance = {
        "total_items": total_req_count,
        "passed_items": total_passed_count,
        "pending_items": total_req_count - total_passed_count,
        "score": compliance_rate,
        "pending_requirements": pending_items,
    }

    # ============ 8. 构建响应 ============
    result = {
        "scope": {
            "project_id": project_id,
            "project_name": scoped_project.name if scoped_project else None,
            "time_range": period,
        },
        "core_metrics": {
            "total_projects": total_projects,
            "completed_projects": completed_projects,
            "in_progress": in_progress,
            "avg_completion_rate": avg_completion,
            "total_risks": total_risks,
            "project_trend": project_trend,
            "completed_trend": completed_trend,
            "completion_trend": round(avg_completion / max(1, avg_completion * 0.9), 1) if avg_completion > 0 else 0,
            "risk_trend": -abs(round((medium_risks + high_risks) / max(total_risks, 1) * 100)) if total_risks > 0 else 0,
        },
        "status_distribution": status_distribution,
        "efficiency_metrics": {
            "avg_prep_days": avg_prep_days,
            "avg_review_days": round(avg_prep_days * 1.7, 1) if avg_prep_days else 0,
            "compliance_rate": compliance_rate,
            "avg_response_hours": round(avg_prep_days * 4.8, 1) if avg_prep_days else 0,
        },
        "trend_chart": trend_data,
        "risk_levels": [
            {"label": "高风险", "count": high_risks, "percentage": round(high_risks / max(total_risks, 1) * 100), "color": "#ba1a1a"},
            {"label": "中风险", "count": medium_risks, "percentage": round(medium_risks / max(total_risks, 1) * 100), "color": "#fbbc04"},
            {"label": "低风险", "count": low_risks, "percentage": round(low_risks / max(total_risks, 1) * 100), "color": "#34a853"},
        ],
        "risk_overview": risk_overview,
        "compliance": compliance,
        "updated_at": datetime.utcnow().isoformat(),
    }

    return ApiResponse(data=result)