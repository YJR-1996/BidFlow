"""标书导出服务 - 把项目下所有需求响应合并生成投标文件（A 方案：合并导出，不做 AI 通稿）。

设计：
- 数据源：项目全部需求 + 每个需求最新响应（edited_content 优先于 ai_content）
- 分组：按类别固定章节顺序（资格/商务/技术/评分/其他）
- 输出：Markdown 文本 / PDF 字节（reportlab + STSong-Light 中文）
- 附录：未生成响应的需求清单（待补充提醒），保证导出的完整性可见
- 边界：零需求/零响应也能导出（只含统计与附录），不抛异常
"""

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

# 固定章节顺序与中文名
CATEGORY_ORDER = ["资格", "商务", "技术", "评分"]
CATEGORY_CHAPTER = {
    "资格": "资格响应",
    "商务": "商务响应",
    "技术": "技术响应",
    "评分": "评分响应",
}
CATEGORY_FALLBACK = "其他"


@dataclass
class BidRequirement:
    """单条需求及其响应（导出用视图对象）"""
    requirement_id: int
    content: str
    category: str
    priority: str
    risk_level: str
    response_content: str = ""   # 已编辑优先，其次 AI 内容
    response_status: str = ""
    source_refs: List[dict] = field(default_factory=list)


def _parse_source_refs(raw) -> List[dict]:
    from app.services.text_utils import parse_source_refs
    refs = parse_source_refs(raw)
    return [r for r in refs if isinstance(r, dict)]


def _source_display(src: dict) -> str:
    """来源展示：文件名（+ 相关度）"""
    name = src.get("filename") or src.get("source") or src.get("source_ref") or "未知来源"
    score = src.get("rerank_score") if isinstance(src.get("rerank_score"), (int, float)) else src.get("score")
    if isinstance(score, (int, float)):
        return f"{name}（相关度 {score:.2f}）"
    return name


class BidDocumentService:
    """投标文件合并导出服务"""

    def load_requirements(self, db, project_id: int) -> List[BidRequirement]:
        """加载项目需求与最新响应，组装为导出视图对象。"""
        from app.models.requirement import Requirement
        from app.models.response import Response as BidResponse

        reqs = db.query(Requirement).filter(Requirement.project_id == project_id).order_by(Requirement.id).all()
        items: List[BidRequirement] = []
        for r in reqs:
            resp = (
                db.query(BidResponse)
                .filter(BidResponse.requirement_id == r.id)
                .order_by(BidResponse.id.desc())
                .first()
            )
            content = ""
            status = ""
            refs: List[dict] = []
            if resp:
                content = (resp.edited_content or "").strip() or (resp.ai_content or "").strip()
                status = resp.status or ""
                refs = _parse_source_refs(getattr(resp, "source_refs", None))
            items.append(BidRequirement(
                requirement_id=r.id,
                content=(r.content or "").strip(),
                category=r.category or CATEGORY_FALLBACK,
                priority=r.priority or "P2",
                risk_level=r.risk_level or "低",
                response_content=content,
                response_status=status,
                source_refs=refs,
            ))
        return items

    def build_markdown(self, db, project_id: int, project_name: str) -> str:
        """生成投标文件 Markdown 文本。"""
        items = self.load_requirements(db, project_id)
        total = len(items)
        responded = [i for i in items if i.response_content]
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        lines = [
            f"# {project_name} 投标响应文件",
            "",
            f"> 生成时间：{now}　|　需求总数：{total}　|　已响应：{len(responded)}　|　待补充：{total - len(responded)}",
            "",
            "---",
            "",
        ]

        # 按固定章节顺序分组
        groups = {c: [] for c in CATEGORY_ORDER}
        groups[CATEGORY_FALLBACK] = []
        for it in items:
            groups.setdefault(it.category, groups[CATEGORY_FALLBACK]).append(it)

        chapter_no = 1
        for category in CATEGORY_ORDER + [CATEGORY_FALLBACK]:
            chapter_items = groups.get(category) or []
            if not chapter_items:
                continue
            lines.append(f"## 第{('一二三四五六七八九十')[chapter_no - 1]}章　{CATEGORY_CHAPTER.get(category, category + '响应')}")
            lines.append("")
            for idx, it in enumerate(chapter_items, 1):
                lines.append(f"### {chapter_no}.{idx}　{it.content[:50] or '（无需求标题）'}")
                lines.append("")
                lines.append(f"**优先级**：{it.priority}　|　**风险等级**：{it.risk_level}")
                if it.source_refs:
                    src_str = "；".join(_source_display(s) for s in it.source_refs[:5])
                    lines.append(f"**引用来源**：{src_str}")
                lines.append("")
                lines.append("**需求内容**：")
                lines.append("")
                lines.append(f"> {it.content}")
                lines.append("")
                lines.append("**响应内容**：")
                lines.append("")
                if it.response_content:
                    lines.append(it.response_content)
                else:
                    lines.append("> ⚠️ 待补充：该需求尚未生成响应。")
                lines.append("")
            chapter_no += 1

        # 附录：待补充清单
        pending = [i for i in items if not i.response_content]
        lines.append("---")
        lines.append("")
        lines.append("## 附录　待补充项清单")
        lines.append("")
        if pending:
            lines.append("以下需求尚未生成响应，请补充后重新导出：")
            lines.append("")
            for it in pending:
                lines.append(f"- 需求 {it.requirement_id}（{it.category}）：{it.content[:60]}")
        else:
            lines.append("全部需求均已生成响应。")
        lines.append("")

        return "\n".join(lines)

    def build_pdf_bytes(self, db, project_id: int, project_name: str) -> bytes:
        """生成投标文件 PDF 字节（reportlab + 中文 CID 字体）。"""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        styles = getSampleStyleSheet()
        cn = ParagraphStyle("cn", parent=styles["Normal"], fontName="STSong-Light", fontSize=10, leading=15)
        h1 = ParagraphStyle("h1", parent=styles["Title"], fontName="STSong-Light", fontSize=18, leading=24)
        h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="STSong-Light", fontSize=13, leading=18, spaceBefore=10)
        h3 = ParagraphStyle("h3", parent=styles["Heading3"], fontName="STSong-Light", fontSize=11, leading=15, spaceBefore=6)

        def esc(text: str) -> str:
            """reportlab Paragraph 是 XML 解析：转义 & < >，换行转 <br/>"""
            return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")

        items = self.load_requirements(db, project_id)
        total = len(items)
        responded = sum(1 for i in items if i.response_content)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
        story = [
            Paragraph(esc(f"{project_name} 投标响应文件"), h1),
            Spacer(1, 8),
            Paragraph(esc(f"需求总数：{total}　已响应：{responded}　待补充：{total - responded}"), cn),
            Spacer(1, 10),
        ]

        groups = {c: [] for c in CATEGORY_ORDER}
        groups[CATEGORY_FALLBACK] = []
        for it in items:
            groups.setdefault(it.category, groups[CATEGORY_FALLBACK]).append(it)

        chapter_no = 1
        for category in CATEGORY_ORDER + [CATEGORY_FALLBACK]:
            chapter_items = groups.get(category) or []
            if not chapter_items:
                continue
            story.append(Paragraph(esc(f"第{('一二三四五六七八九十')[chapter_no - 1]}章　{CATEGORY_CHAPTER.get(category, category + '响应')}"), h2))
            for idx, it in enumerate(chapter_items, 1):
                story.append(Paragraph(esc(f"{chapter_no}.{idx}　{it.content[:50]}"), h3))
                story.append(Paragraph(
                    esc(f"优先级：{it.priority}　风险等级：{it.risk_level}"), cn))
                if it.source_refs:
                    src_str = "；".join(_source_display(s) for s in it.source_refs[:5])
                    story.append(Paragraph(esc(f"引用来源：{src_str}"), cn))
                story.append(Paragraph(esc(f"需求内容：{it.content}"), cn))
                story.append(Spacer(1, 4))
                if it.response_content:
                    story.append(Paragraph(esc(it.response_content), cn))
                else:
                    story.append(Paragraph(esc("⚠️ 待补充：该需求尚未生成响应。"), cn))
                story.append(Spacer(1, 8))
            chapter_no += 1

        story.append(Spacer(1, 10))
        story.append(Paragraph("附录　待补充项清单", h2))
        pending = [i for i in items if not i.response_content]
        if pending:
            story.append(Paragraph(esc("以下需求尚未生成响应，请补充后重新导出："), cn))
            for it in pending:
                story.append(Paragraph(esc(f"- 需求 {it.requirement_id}（{it.category}）：{it.content[:60]}"), cn))
        else:
            story.append(Paragraph("全部需求均已生成响应。", cn))

        doc.build(story)
        data = buf.getvalue()
        buf.close()
        return data


bid_document_service = BidDocumentService()
