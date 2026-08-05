"""标书导出路由 - 合并项目全部需求响应生成投标文件（Markdown / PDF）"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.bid_project import BidProject
from app.api.deps import get_current_user
from app.api.deps import get_project_or_404_sync
from app.services.bid_document_service import bid_document_service

router = APIRouter()


def _download_headers(project_name: str, project_id: int, ext: str, media_type: str) -> dict:
    """RFC 5987 中文文件名（HTTP header 仅支持 latin-1，提供 ASCII 回退名）"""
    from urllib.parse import quote
    ascii_name = f"bid-document-{project_id}.{ext}"
    utf8_name = quote(f"{project_name}-投标响应文件-{project_id}.{ext}")
    return {
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}",
        "Content-Type": media_type,
    }


@router.get("/projects/{project_id}/bid-document/markdown")
def export_bid_document_markdown(
    project_id: int,
    project: BidProject = Depends(get_project_or_404_sync),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出投标响应文件（Markdown）"""
    from fastapi.responses import StreamingResponse
    md_content = bid_document_service.build_markdown(db, project_id, project.name)

    def iter_content():
        yield md_content.encode("utf-8")

    return StreamingResponse(
        iter_content(),
        headers=_download_headers(project.name, project_id, "md", "text/markdown; charset=utf-8"),
    )


@router.get("/projects/{project_id}/bid-document/pdf")
def export_bid_document_pdf(
    project_id: int,
    project: BidProject = Depends(get_project_or_404_sync),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出投标响应文件（PDF，reportlab 中文渲染）"""
    from fastapi.responses import StreamingResponse
    import io
    pdf_bytes = bid_document_service.build_pdf_bytes(db, project_id, project.name)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        headers=_download_headers(project.name, project_id, "pdf", "application/pdf"),
    )


def _build_compliance_report_md(db, project_id) -> str:
    """合规报告 Markdown（与 /compliance-report/markdown 同口径）"""
    from app.models.compliance_issue import ComplianceIssue
    from app.services.report_service import ReportService
    from app.services.readiness_service import readiness_service
    from app.services.compliance_checker import ComplianceIssue as CIssue

    issues = db.query(ComplianceIssue).filter(ComplianceIssue.project_id == project_id).all()
    r = readiness_service.calculate(project_id, db)
    level_map = {"高": "high", "中": "medium", "低": "low"}
    checker_issues = [
        CIssue(
            requirement_id=i.requirement_id, rule_code=i.rule_code,
            level=level_map.get(i.level, "low"),
            description=i.description, suggestion=i.suggestion,
        )
        for i in issues
    ]
    report = ReportService().build([], checker_issues)
    from dataclasses import replace
    report = replace(
        report,
        total_requirements=r.total,
        completed_requirements=r.has_response,
        completion_rate=int(r.overall),
        high_risk_count=sum(1 for i in issues if i.level == "高"),
        medium_risk_count=sum(1 for i in issues if i.level == "中"),
        low_risk_count=sum(1 for i in issues if i.level == "低"),
    )
    return ReportService().to_markdown(report)


def _build_compliance_report_pdf(db, project_id, project_name) -> bytes:
    """合规报告 PDF（reportlab + STSong-Light 中文，与 /compliance-report/pdf 同模式）"""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    from app.models.compliance_issue import ComplianceIssue
    from app.services.readiness_service import readiness_service

    issues = db.query(ComplianceIssue).filter(ComplianceIssue.project_id == project_id).all()
    r = readiness_service.calculate(project_id, db)

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    cn = ParagraphStyle("cn", parent=styles["Normal"], fontName="STSong-Light", fontSize=10, leading=14)
    title_style = ParagraphStyle("title", parent=styles["Title"], fontName="STSong-Light", fontSize=16)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    elems = [
        Paragraph("BidFlow 投标审查报告", title_style),
        Spacer(1, 6),
        Paragraph(f"项目：{project_name}（ID {project_id}）", cn),
        Paragraph(
            f"响应项总数：{r.total}　已完成：{r.has_response}　完成度：{int(r.overall)}%",
            cn,
        ),
        Paragraph(
            f"高风险：{sum(1 for i in issues if i.level == '高')}　"
            f"中风险：{sum(1 for i in issues if i.level == '中')}　"
            f"低风险：{sum(1 for i in issues if i.level == '低')}",
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
        table = Table(data, colWidths=[18 * mm, 38 * mm, 64 * mm, 50 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, (0.8, 0.8, 0.8)),
            ("BACKGROUND", (0, 0), (-1, 0), (0.93, 0.95, 0.98)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elems.append(table)

    doc.build(elems)
    data_bytes = buf.getvalue()
    buf.close()
    return data_bytes


@router.get("/projects/{project_id}/bid-package")
def export_bid_package(
    project_id: int,
    project: BidProject = Depends(get_project_or_404_sync),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """打包投递包（方案 A）：标书 md/pdf + 合规报告 md/pdf + README，一键下载 zip"""
    import io
    import zipfile
    from datetime import datetime

    from fastapi.responses import StreamingResponse
    from urllib.parse import quote

    md_bid = bid_document_service.build_markdown(db, project_id, project.name)
    pdf_bid = bid_document_service.build_pdf_bytes(db, project_id, project.name)
    md_report = _build_compliance_report_md(db, project_id)
    pdf_report = _build_compliance_report_pdf(db, project_id, project.name)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    readme = (
        f"{project.name} 投标投递包\n"
        f"==================\n"
        f"生成时间：{now}\n"
        f"项目 ID：{project_id}\n\n"
        f"包含文件：\n"
        f"  1. 投标响应文件.md   —— 全部需求响应合并（Markdown）\n"
        f"  2. 投标响应文件.pdf   —— 全部需求响应合并（PDF）\n"
        f"  3. 合规审查报告.md    —— 合规核查结果（Markdown）\n"
        f"  4. 合规审查报告.pdf    —— 合规核查结果（PDF）\n\n"
        f"说明：投标响应文件基于审核通过的响应（人工编辑版优先）合并生成；\n"
        f"      合规审查报告基于规则引擎 + 语义 AI 核查结果生成。\n"
        f"      正式投标请按招标要求核对后提交至对应电子招投标平台。\n"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("投标响应文件.md", md_bid.encode("utf-8"))
        zf.writestr("投标响应文件.pdf", pdf_bid)
        zf.writestr("合规审查报告.md", md_report.encode("utf-8"))
        zf.writestr("合规审查报告.pdf", pdf_report)
        zf.writestr("README.txt", readme.encode("utf-8"))

    # 方案 A：打包成功 = 投递就绪 → 项目标记为"已完成"
    from app.services.project_status import mark_project_completed
    mark_project_completed(db, project_id)

    ascii_name = f"bid-package-{project_id}.zip"
    utf8_name = quote(f"{project.name}-投标投递包-{project_id}.zip")
    return StreamingResponse(
        io.BytesIO(buf.getvalue()),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}",
        },
    )
