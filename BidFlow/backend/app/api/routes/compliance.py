"""合规核查路由 - 项目合规检查与报告"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.models.compliance_issue import ComplianceIssue
from app.schemas.common import ApiResponse
from app.schemas.compliance import ComplianceReportResponse
from app.api.deps import get_current_user, get_project_or_404_sync
from app.core.exceptions import BusinessException
from app.services.compliance_checker import ComplianceChecker, RequirementSnapshot
from app.services.report_service import ReportService
from app.services.semantic_compliance_agent import semantic_compliance_agent

router = APIRouter()


@router.post("/{project_id}/compliance-check", response_model=ApiResponse[dict])
def run_compliance_check(
    project_id: int,
    project: BidProject = Depends(get_project_or_404_sync),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """运行合规核查，将问题写入 compliance_issues 表"""
    # 获取所有需求项
    requirements = db.query(Requirement).filter(
        Requirement.project_id == project_id
    ).all()

    if not requirements:
        raise BusinessException(message="该项目暂无需求项，请先解析招标文件")

    # 构建快照（L1：source_refs 解析统一走公共函数）
    from app.services.text_utils import parse_source_refs
    from app.models.match_analysis import MatchAnalysisRun, MatchAnalysisDetail

    # L14：预取最新一次比对分析的未匹配集合（has_match=false），
    # 用于快照 match_unmatched 字段，规则引擎据此判定「引用资料可能失效」。
    latest_run = (
        db.query(MatchAnalysisRun)
        .filter(MatchAnalysisRun.project_id == project_id)
        .order_by(MatchAnalysisRun.created_at.desc())
        .first()
    )
    unmatched_req_ids: set[int] = set()
    if latest_run:
        for d in db.query(MatchAnalysisDetail).filter(
            MatchAnalysisDetail.run_id == latest_run.id,
            MatchAnalysisDetail.has_match.is_(False),
        ).all():
            unmatched_req_ids.add(d.requirement_id)

    snapshots: list[RequirementSnapshot] = []
    for req in requirements:
        resp_content = ""
        source_refs: list = []
        resp_status = None
        # L13：只取「最新一条」响应（id 降序）——与 requirements.py:98 / readiness_service / 比对逻辑口径一致。
        # 原实现 for r in responses（ORM 默认 id 升序）取到第一条：历史遗留多条响应时（旧版每次生成都新建），
        # 会取到旧的 pending_review/草稿状态 → 对已批准的 P0 误报「P0 响应项尚未完成」（与前端「已批准」矛盾）。
        responses = sorted(getattr(req, "responses", None) or [], key=lambda r: (r.id or 0), reverse=True)
        if responses:
            latest = responses[0]
            resp_content = latest.edited_content or latest.ai_content or ""
            if getattr(latest, "source_refs", None):
                source_refs = parse_source_refs(latest.source_refs)
            if resp_content:
                resp_status = latest.status
        snapshot_status = resp_status or req.status or "未处理"
        # 双重保险：needs_manual 状态下 source_refs 必有历史残留，强制清空
        # （generate_response_draft 已写入时清空，但旧数据可能仍残留），
        # 避免规则误判「有资料」导致 P0 报成「响应缺失」而非「资料缺失」
        if snapshot_status == "needs_manual" or resp_content.startswith("待人工补充"):
            source_refs = []
        snapshots.append(RequirementSnapshot(
            requirement_id=req.id,
            content=req.content or "",
            priority=req.priority or "P2",
            response_content=resp_content,
            source_refs=source_refs,
            status=snapshot_status,
            match_unmatched=req.id in unmatched_req_ids,
        ))

    # 执行核查（规则引擎）
    checker = ComplianceChecker()
    rule_issues = checker.check(snapshots)

    # 语义合规 Agent（LLM 语义风险检测，静默降级）
    semantic_issues = []
    for snap in snapshots:
        if not snap.response_content.strip():
            continue
        try:
            for r in semantic_compliance_agent.analyze(
                snap.requirement_id, snap.content, snap.response_content, snap.source_refs
            ):
                semantic_issues.append(ComplianceIssue(
                    project_id=project_id,
                    requirement_id=snap.requirement_id,
                    level={"high": "高", "medium": "中", "low": "低"}.get(r["level"], "中"),
                    rule_code=r["rule_code"],
                    description=r["description"],
                    suggestion=r["suggestion"],
                    status="未处理",
                    source="semantic",
                ))
        except Exception:
            pass

    # 第 5 层：跨需求去重——同一项目内 description 相似（前 20 字相同）
    # 只保留第一条，避免同一个语义问题在多个需求下重复报
    seen_keys = set()
    deduped_semantic = []
    for ci in semantic_issues:
        key = (ci.description or "")[:20]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_semantic.append(ci)
    semantic_issues = deduped_semantic

    report = ReportService().build(snapshots, rule_issues)

    # 使用 readiness_service 统一计算完成度（单一数据源）
    from app.services.readiness_service import readiness_service
    readiness = readiness_service.calculate(project_id, db)

    # M6：清理旧的合规问题，防止重复——但保留用户已处置（status="已处理"）的记录，
    # 避免每次核查把处置进度抹回"未处理"
    db.query(ComplianceIssue).filter(
        ComplianceIssue.project_id == project_id,
        ComplianceIssue.status != "已处理",
    ).delete(synchronize_session=False)
    db.flush()

    # 持久化规则引擎问题
    for issue in report.issues:
        ci = ComplianceIssue(
            project_id=project_id,
            requirement_id=issue.requirement_id,
            level={"high": "高", "medium": "中", "low": "低"}.get(issue.level, "低"),
            rule_code=issue.rule_code,
            description=issue.description,
            suggestion=issue.suggestion,
            status="未处理",
            source="rule",
        )
        db.add(ci)

    # 追加语义合规问题
    for ci in semantic_issues:
        db.add(ci)
    db.commit()

    return ApiResponse(data={
        "message": "合规核查完成",
        "total_requirements": readiness.total,
        "completed_requirements": readiness.has_response,
        "completion_rate": readiness.overall,
        "high_risk_count": report.high_risk_count,
        "medium_risk_count": report.medium_risk_count,
        "low_risk_count": report.low_risk_count,
        "rule_issue_count": len(report.issues),
        "semantic_issue_count": len(semantic_issues),
        "issue_count": len(report.issues) + len(semantic_issues),
    })


@router.get("/{project_id}/compliance-report", response_model=ApiResponse[ComplianceReportResponse])
def get_compliance_report(
    project_id: int,
    project: BidProject = Depends(get_project_or_404_sync),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取项目的合规报告"""
    from sqlalchemy.orm import joinedload
    from app.services.readiness_service import readiness_service

    issues = db.query(ComplianceIssue).options(
        joinedload(ComplianceIssue.requirement)
    ).filter(
        ComplianceIssue.project_id == project_id
    ).all()

    # 给每个 issue 附带需求内容摘要（前端展示用，不再只显示裸 ID）
    for issue in issues:
        content = getattr(issue.requirement, "content", None) if issue.requirement else None
        if content:
            issue.requirement_content = content.strip().replace("\n", " ")[:80]
        else:
            issue.requirement_content = None

    # P0-2：风险列表与卡片数字口径统一——仅展示未处理项（risk_count 只统计"未处理"高/中）
    high_risks = [i for i in issues if i.level == "高" and i.status == "未处理"]
    medium_risks = [i for i in issues if i.level == "中" and i.status == "未处理"]
    low_risks = [i for i in issues if i.level == "低" and i.status == "未处理"]

    # === 4 个卡片数字统一到「需求维度」（每个需求只属于 1 个状态，互斥自洽）===
    # 解决之前「已通过 19」（已生成响应数）+「核查风险 11/14」（issue 数）+「待人工 0」（硬编码）
    #   → 4 个数字加起来 ≠ 总数 19 的不自洽问题
    from app.models.response import Response as BidResponse
    from app.models.requirement import Requirement

    requirements = db.query(Requirement).filter(
        Requirement.project_id == project_id
    ).all()
    req_ids = {r.id for r in requirements}

    # 每个需求的「最高未处理风险」level（高 优先 中）
    risk_level_by_req: dict = {}
    for i in issues:
        if i.requirement_id is None or i.requirement_id not in req_ids:
            continue
        if i.level not in ("高", "中") or i.status != "未处理":
            continue
        cur = risk_level_by_req.get(i.requirement_id)
        if cur == "高":
            continue  # 高保持
        risk_level_by_req[i.requirement_id] = i.level  # 中 或新赋值

    # 每个需求的最新一条 response 状态
    latest_resp_status_by_req: dict = {}
    for r in requirements:
        resp = (
            db.query(BidResponse)
            .filter(BidResponse.requirement_id == r.id)
            .order_by(BidResponse.id.desc())
            .first()
        )
        latest_resp_status_by_req[r.id] = (resp.status if resp else "未生成")

    # 三段互斥统计：
    # 1) 核查风险 = 命中任何高/中未处理风险 issue 的需求数
    risk_req_ids = set(risk_level_by_req.keys())
    risk_count = len(risk_req_ids)
    # 2) 已通过 = 剩余需求中有响应 且 状态非 pending_review
    # 3) 待人工审核 = 剩余需求中有响应 且 状态 pending_review
    passed_count = 0
    pending_review_count = 0
    for r in requirements:
        if r.id in risk_req_ids:
            continue  # 已计入「核查风险」
        status = latest_resp_status_by_req.get(r.id, "未生成")
        if status == "pending_review":
            pending_review_count += 1
        elif status in ("editing", "completed", "rejected", "needs_manual"):
            passed_count += 1
        # status == "未生成" 不计入任何卡片（响应清单显示「未生成」标签）

    total_req = len(requirements)

    # 使用 readiness_service 统一计算就绪度（单一数据源，三维加权）
    r = readiness_service.calculate(project_id, db)
    completion_rate = r.overall

    return ApiResponse(data=ComplianceReportResponse(
        project_id=project_id,
        total_requirements=total_req,
        completed_count=passed_count,
        pending_review_count=pending_review_count,
        risk_count=risk_count,
        completion_rate=completion_rate,
        base_rate=r.base_rate,
        quality_rate=r.quality_rate,
        compliance_rate=r.compliance_rate,
        high_risk_pending=r.high_risk_pending,
        high_risks=high_risks,
        medium_risks=medium_risks,
        low_risks=low_risks,
    ))


@router.get("/{project_id}/compliance-report/markdown")
def export_report_markdown(
    project_id: int,
    project: BidProject = Depends(get_project_or_404_sync),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出合规审查报告为 Markdown 文件"""
    from app.services.readiness_service import readiness_service

    issues = db.query(ComplianceIssue).filter(
        ComplianceIssue.project_id == project_id
    ).all()

    # 统一使用 readiness_service 计算完成度（单一数据源）
    r = readiness_service.calculate(project_id, db)
    total_req = r.total
    completed_req = r.has_response
    completion_rate = int(r.overall)

    high_count = sum(1 for i in issues if i.level == "高")
    medium_count = sum(1 for i in issues if i.level == "中")
    low_count = sum(1 for i in issues if i.level == "低")

    # 转换为 ComplianceIssue dataclass 列表
    from app.services.compliance_checker import ComplianceIssue as CIssue
    level_map = {"高": "high", "中": "medium", "低": "low"}
    checker_issues = [
        CIssue(
            requirement_id=i.requirement_id,
            rule_code=i.rule_code,
            level=level_map.get(i.level, "low"),
            description=i.description,
            suggestion=i.suggestion,
        )
        for i in issues
    ]
    report = ReportService().build([], checker_issues)
    # Override report stats with readiness_service 统一数据源
    from dataclasses import replace
    report = replace(
        report,
        total_requirements=total_req,
        completed_requirements=completed_req,
        completion_rate=completion_rate,
        high_risk_count=high_count,
        medium_risk_count=medium_count,
        low_risk_count=low_count,
    )

    md_content = ReportService().to_markdown(report)

    def iter_content():
        yield md_content.encode("utf-8")

    # HTTP header 仅支持 latin-1，中文项目名需用 RFC 5987 编码，并提供 ASCII 回退名
    from urllib.parse import quote
    ascii_name = f"compliance-report-{project_id}.md"
    utf8_name = quote(f"compliance-report-{project.name}-{project_id}.md")
    return StreamingResponse(
        iter_content(),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}",
        },
    )


@router.get("/{project_id}/compliance-report/pdf")
def export_report_pdf(
    project_id: int,
    project: BidProject = Depends(get_project_or_404_sync),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出合规审查报告为 PDF 文件"""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    from app.services.readiness_service import readiness_service

    # 与 Markdown 版保持一致：统一使用 readiness_service 计算完成度
    issues = db.query(ComplianceIssue).filter(
        ComplianceIssue.project_id == project_id
    ).all()

    r = readiness_service.calculate(project_id, db)
    total_req = r.total
    completed_req = r.has_response
    completion_rate = r.overall
    high_count = sum(1 for i in issues if i.level == "高")
    medium_count = sum(1 for i in issues if i.level == "中")
    low_count = sum(1 for i in issues if i.level == "低")

    # 注册中文 CID 字体（STSong-Light），内置无需外部文件
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    styles = getSampleStyleSheet()
    cn = ParagraphStyle(
        "cn", parent=styles["Normal"],
        fontName="STSong-Light", fontSize=10, leading=14,
    )
    title_style = ParagraphStyle(
        "title", parent=styles["Title"],
        fontName="STSong-Light", fontSize=16,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm,
    )

    elems = [
        Paragraph("BidFlow 投标审查报告", title_style),
        Spacer(1, 6),
        Paragraph(f"项目：{project.name}（ID {project_id}）", cn),
        Paragraph(
            f"响应项总数：{total_req}　已完成：{completed_req}　完成度：{completion_rate}%",
            cn,
        ),
        Paragraph(
            f"高风险：{high_count}　中风险：{medium_count}　低风险：{low_count}",
            cn,
        ),
        Spacer(1, 10),
    ]

    if not issues:
        elems.append(Paragraph("当前未发现待处理风险。", cn))
    else:
        data = [["等级", "规则码", "问题描述", "处理建议"]]
        for i in issues:
            data.append([
                Paragraph(i.level or "", cn),
                Paragraph(i.rule_code or "", cn),
                Paragraph(i.description or "", cn),
                Paragraph(i.suggestion or "", cn),
            ])
        table = Table(
            data,
            colWidths=[18 * mm, 38 * mm, 64 * mm, 50 * mm],
            repeatRows=1,
        )
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, (0.8, 0.8, 0.8)),
            ("BACKGROUND", (0, 0), (-1, 0), (0.93, 0.95, 0.98)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elems.append(table)

    doc.build(elems)
    pdf_bytes = buf.getvalue()
    buf.close()

    # HTTP header 仅支持 latin-1，中文项目名需用 RFC 5987 编码，并提供 ASCII 回退名
    from urllib.parse import quote
    ascii_name = f"compliance-report-{project_id}.pdf"
    utf8_name = quote(f"compliance-report-{project.name}-{project_id}.pdf")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'},
    )
