# BidFlow 架构级修复提示词集（5 份，精简版，可直接喂 AI coding）

> 每份提示词自包含、独立可执行。根：`D:\code\FastAPI_Models\Project\BidFlow\backend`
> 技术栈：FastAPI + SQLAlchemy + Milvus + DashScope(qwen)。新增端点如需后台跑（防 30s 超时）用 `threading`+内存字典（同 `batch_task_service.py`）。

---

## 提示词 1：Agent 编排架构（Orchestrator + 4 Sub-Agent）

**目标**：新增轻量编排层（`app/agents/`），Sub-Agent 全部**委托复用**现有 Service，不重写业务逻辑；支持人工审核暂停/恢复。现有路由行为不变。

**上下文**：
- 无 `app/agents/` 包；LLM 由 `OpenAIChatClient`（`app/services/llm_client.py`）在 Service 层扁平直调。
- 可复用：`tender_requirement_extractor.py`（解析+抽取）、`auxiliary_requirement_service.py`（`generate(db, project_id)`）、`batch_task_service.py`（`start_batch(project_id, requirement_ids, owner_id)`→task_id）、`retrieval_service.py`（`search(query, project_id, top_k)`）、`compliance_checker.py`（`ComplianceChecker.check(snapshots)`）。
- 建表走 `Base.metadata.create_all`（新模型免 migration）。

**约束**：① 仅新增文件+1 模型+2~3 端点，不改现有 Service 内部；② Sub-Agent 禁止重写 LLM/检索/解析；③ 编排端点异步化（立即返 run_id+后台线程）；④ HITL：某 Agent 置 `human_review_required=True` 则持久化状态提前返回，提供 resume；⑤ 不引入 Celery/Redis。

**改动**：

`app/agents/base.py`：
```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class WorkflowContext:
    project_id: int
    owner_id: str
    stages_done: list = field(default_factory=list)
    requirements: list = field(default_factory=list)
    retrieval_task_id: Optional[str] = None
    compliance_issues: list = field(default_factory=list)
    human_review_required: bool = False
    review_reason: str = ""
    metadata: dict = field(default_factory=dict)

class ToolRegistry:
    def __init__(self):
        from app.core.config import settings
        from app.services.retrieval_service import retrieval_service
        self.settings = settings
        self.retrieval_service = retrieval_service
    def llm(self):
        from app.services.llm_client import OpenAIChatClient
        return OpenAIChatClient(api_key=self.settings.DASHSCOPE_API_KEY, model=self.settings.LLM_MODEL_NAME)

class BaseAgent:
    name = "base"
    def __init__(self, tools): self.tools = tools
    def run(self, ctx, db): raise NotImplementedError
```

`app/agents/parse_agent.py`（ParseAgent）：遍历项目未解析 `TenderDocument`，复用 `document_parser`+`TenderRequirementExtractorService.extract` 写 requirements，填 `ctx.requirements`。
`app/agents/decompose_agent.py`（DecomposeAgent）：`ctx` 调 `auxiliary_requirement_service.generate(db, ctx.project_id)`。
`app/agents/rag_agent.py`（RAGAgent）：取需生成响应的需求 ID，调 `batch_task_service.start_batch(ctx.project_id, req_ids, ctx.owner_id)`，存 task_id 到 `ctx.retrieval_task_id`。
`app/agents/compliance_agent.py`（ComplianceAgent，可选）：取 requirements→`build_snapshots(db, requirements)`（建议从 `compliance.py` 抽出）→`ComplianceChecker().check(snapshots)`，存 `ctx.compliance_issues`；有 `level=="high"` 则置 `ctx.human_review_required=True`。

`app/agents/orchestrator.py`：
```python
class Orchestrator:
    STAGE_ORDER = ["parse", "decompose", "rag", "compliance"]
    def __init__(self):
        from app.agents.base import ToolRegistry
        from app.agents.parse_agent import ParseAgent
        from app.agents.decompose_agent import DecomposeAgent
        from app.agents.rag_agent import RAGAgent
        from app.agents.compliance_agent import ComplianceAgent
        self.tools = ToolRegistry()
        self.agents = {"parse": ParseAgent(self.tools), "decompose": DecomposeAgent(self.tools),
                       "rag": RAGAgent(self.tools), "compliance": ComplianceAgent(self.tools)}
    def run(self, ctx, db, start_stage="parse"):
        for stage in self.STAGE_ORDER[self.STAGE_ORDER.index(start_stage):]:
            ctx = self.agents[stage].run(ctx, db)
            ctx.stages_done.append(stage)
            if ctx.human_review_required:
                break
        return ctx
```

`app/models/workflow_run.py`：
```python
import json, uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.db.base import Base
class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(Integer, nullable=False)
    current_stage = Column(String(20), default="parse")
    status = Column(String(20), default="running")  # running/awaiting_review/completed/failed
    context_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
```

`app/api/routes/workflow.py` 端点：
- `POST /api/projects/{project_id}/run-workflow`：建 `WorkflowRun`(running)，`BackgroundTasks` 起后台线程跑 `Orchestrator().run(ctx, db_sync)`（后台自建同步 Session：`from app.db.session import engine_sync; Session(engine_sync)`，同 `batch_task_service._run_batch`）；若 `human_review_required`→`awaiting_review` 并写 context_json，否则 `completed`。立即返 `{run_id, status}`。
- `GET /api/projects/{project_id}/workflow/{run_id}`：返状态+context_json 摘要。
- `POST /api/projects/{project_id}/workflow/{run_id}/resume`：仅 `status=="awaiting_review"` 可调用；置 `human_review_required=False` 后从下一阶段续跑（后台线程）。

`app/api/router.py` 增加：`from app.api.routes import workflow; router.include_router(workflow.router, prefix="/projects", tags=["Agent编排"])`。

**验证**：① `POST run-workflow` 立即拿 run_id；② 轮询 `GET workflow/{run_id}` 见 running→awaiting_review/completed；③ awaiting_review 时 `POST resume` 推进到 completed；④ 核对 requirements 增多、responses 新增、compliance_issues 有记录；⑤ 现有 `/tender-documents`、`/requirements/aux-generate`、`/batch-generate`、`/compliance-check` 行为不变。

---

## 提示词 2：语义合规 Agent（LLM 语义风险检测）

**目标**：在节点⑪补齐「语义合规 Agent」一轨——规则引擎之后用 LLM 检测语义级风险（与招标实质矛盾、过度承诺、关键条款遗漏、与规范/评分不一致、无法履行承诺），产出额外 `ComplianceIssue` 合并写入。LLM 失败**静默降级**为仅规则引擎。

**上下文**：
- 规则引擎：`compliance_checker.py`（`ComplianceChecker.check`，规则码 `P0_RESPONSE_MISSING`/`RESPONSE_CONTENT_EMPTY`/`RESPONSE_SOURCE_MISSING`/`MANUAL_MATERIAL_REQUIRED`）。
- 快照构建：`compliance.py` 的 `run_compliance_check`（约第 50–96 行）已正确解析 `source_refs`（`ast.literal_eval` 兜底）并以响应草稿状态为 `status`。
- LLM：`llm_client.py` 的 `OpenAIChatClient.chat_json(messages)`（失败抛 `LlmServiceError`）；配置 `settings.DASHSCOPE_API_KEY`/`settings.LLM_MODEL_NAME`。
- 模型 `ComplianceIssue`（`app/models/compliance_issue.py`）当前字段：`id, project_id, requirement_id, level, rule_code, description, suggestion, status(默认"未处理")`。**无 source 列**。

**约束**：① 不改规则引擎；② LLM 调用 try/except 包裹，任何异常返 `[]` 不影响规则写库；③ 新增 `ComplianceIssue.source` 列（默认 `"rule"`），语义写 `"semantic"`（create_all 自动建，免 migration）；④ 复用 `OpenAIChatClient`；⑤ LLM 输出严格 JSON：`rule_code`(前缀 `SEMANTIC_`)、`level`(high/medium/low)、`description`、`suggestion`；⑥ 加配置开关 `SEMANTIC_COMPLIANCE_ENABLED`（默认 True）。

**改动**：

`app/models/compliance_issue.py` 在 `status` 后加：
```python
source = Column(String(20), default="rule")  # rule=规则引擎, semantic=语义合规Agent
```

新增 `app/services/semantic_compliance_agent.py`：
```python
import logging
from app.core.config import settings
from app.services.llm_client import OpenAIChatClient, LlmServiceError
from app.services.prompt_templates import build_semantic_compliance_messages
logger = logging.getLogger(__name__)

class SemanticComplianceAgent:
    def analyze(self, requirement_id, requirement_content, response_content, source_refs):
        if not getattr(settings, "SEMANTIC_COMPLIANCE_ENABLED", True): return []
        if not response_content or not response_content.strip(): return []
        if not settings.DASHSCOPE_API_KEY: return []
        try:
            client = OpenAIChatClient(api_key=settings.DASHSCOPE_API_KEY, model=settings.LLM_MODEL_NAME)
            data = client.chat_json(build_semantic_compliance_messages(requirement_content, response_content, source_refs))
            out = []
            for it in (data.get("risks") or []):
                if not isinstance(it, dict): continue
                code = str(it.get("rule_code", "SEMANTIC_UNKNOWN"))
                code = code if code.startswith("SEMANTIC_") else "SEMANTIC_" + code
                level = it.get("level", "medium")
                if level not in ("high", "medium", "low"): level = "medium"
                out.append({"rule_code": code, "level": level,
                            "description": str(it.get("description", "")), "suggestion": str(it.get("suggestion", ""))})
            return out
        except Exception as e:
            logger.warning("[semantic_compliance] LLM 不可用，跳过：%s", e); return []

semantic_compliance_agent = SemanticComplianceAgent()
```

`app/services/prompt_templates.py` 新增：
```python
def build_semantic_compliance_messages(requirement_content, response_content, source_refs):
    refs = "\n".join(f"- {s.get('filename','?')}：{str(s.get('content',''))[:120]}" for s in (source_refs or [])[:5])
    return [
        {"role": "system", "content": "你是投标语义合规审查专家。识别规则引擎抓不到的语义级风险：与招标要求的实质矛盾、过度承诺/虚假陈述、关键条款遗漏、与规范或评分标准不一致、无法履行的承诺。只输出 JSON，不作法律结论。"},
        {"role": "user", "content": f"招标要求：\n{requirement_content}\n\n投标响应草稿：\n{response_content}\n\n可引用资料：\n{refs}\n\n请输出 JSON：{{\"risks\":[{{\"rule_code\":\"SEMANTIC_xxx\",\"level\":\"high|medium|low\",\"description\":\"风险描述\",\"suggestion\":\"处理建议\"}}]}}，无风险则 {{\"risks\":[]}}"},
    ]
```

`app/api/routes/compliance.py` 在 `checker.check(...)` 之后、写库前插入：
```python
from app.services.semantic_compliance_agent import semantic_compliance_agent
semantic_issues = []
for snap in snapshots:
    if not snap.response_content.strip(): continue
    for r in semantic_compliance_agent.analyze(snap.requirement_id, snap.content, snap.response_content, snap.source_refs):
        semantic_issues.append(ComplianceIssue(
            project_id=project_id, requirement_id=snap.requirement_id,
            level={"high":"高","medium":"中","low":"低"}.get(r["level"],"中"),
            rule_code=r["rule_code"], description=r["description"], suggestion=r["suggestion"],
            status="未处理", source="semantic"))
# 把 semantic_issues 并入现有写库循环（保持原写库逻辑不变，仅追加 source="semantic" 的 ORM 对象）
```

`app/core/config.py` 的 `Settings` 增加：`SEMANTIC_COMPLIANCE_ENABLED: bool = True`。

**验证**：① 有效 Key 跑 `POST /{project_id}/compliance-check`，`compliance_issues` 出现 `source="semantic"` 且 `rule_code` 以 `SEMANTIC_` 开头；② 设 `SEMANTIC_COMPLIANCE_ENABLED=False` 或清空 Key 重跑：检查仍完成仅无 semantic 记录（降级）；③ 原规则 issue 数量与改动前一致。

---

## 提示词 3：PDF 格式导出审查报告

**目标**：补齐节点⑭缺失的 PDF 导出，复用现有 `ReportService` 同一份数据，新增返回 `application/pdf` 端点。Markdown 导出不变。

**上下文**：
- Markdown 导出：`compliance.py` 的 `export_report_markdown`（约第 177–249 行）拼 `ComplianceReport` 后 `ReportService().to_markdown(report)`，`StreamingResponse` 返 `.md`。
- `ComplianceIssue` dataclass 字段：`requirement_id, rule_code, level, description, suggestion`。
- `requirements.txt` 无 PDF 库。路由 `compliance.router` 挂在 `/api`，路径形如 `/{project_id}/compliance-report/markdown`。

**约束**：① 用 **reportlab**（纯 Python），`requirements.txt` 追加 `reportlab==4.2.5`；② **关键坑**：reportlab 默认字体不渲染中文，必须 `pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))`（内置，无需外部字体），所有中文样式 `fontName='STSong-Light'`；③ 不改 `export_report_markdown`，新增 `GET /{project_id}/compliance-report/pdf`；④ 内容与 Markdown 版一致（汇总+每 issue 的 level/rule_code/description/suggestion）；⑤ 返回 `StreamingResponse(..., media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=..."})`。

**改动**：

`requirements.txt` 追加：`reportlab==4.2.5`

`app/api/routes/compliance.py` 在 `export_report_markdown` 后新增：
```python
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
import io

@app.get("/{project_id}/compliance-report/pdf")
def export_report_pdf(project_id: int,
                       project: BidProject = Depends(get_project_or_404_sync),
                       current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    issues = db.query(ComplianceIssue).filter(ComplianceIssue.project_id == project_id).all()
    all_reqs = db.query(Requirement).filter(Requirement.project_id == project_id).all()
    total_req = len(all_reqs)
    completed_req = 0
    for req in all_reqs:
        resp = db.query(BidResponse).filter(BidResponse.requirement_id == req.id).order_by(BidResponse.id.desc()).first()
        if resp and (resp.edited_content or resp.ai_content): completed_req += 1
    completion_rate = round(completed_req / total_req * 100, 1) if total_req else 0.0
    high_count = sum(1 for i in issues if i.level == "高")
    medium_count = sum(1 for i in issues if i.level == "中")
    low_count = sum(1 for i in issues if i.level == "低")

    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    styles = getSampleStyleSheet()
    cn = ParagraphStyle('cn', parent=styles['Normal'], fontName='STSong-Light', fontSize=10, leading=14)
    title = ParagraphStyle('title', parent=styles['Title'], fontName='STSong-Light', fontSize=16)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    elems = [Paragraph("BidFlow 投标审查报告", title), Spacer(1, 6),
             Paragraph(f"项目：{project.name}（ID {project_id}）", cn),
             Paragraph(f"响应项总数：{total_req}　已完成：{completed_req}　完成度：{completion_rate}%", cn),
             Paragraph(f"高风险：{high_count}　中风险：{medium_count}　低风险：{low_count}", cn), Spacer(1, 10)]
    if not issues:
        elems.append(Paragraph("当前未发现待处理风险。", cn))
    else:
        data = [["等级", "规则码", "问题描述", "处理建议"]]
        for i in issues:
            data.append([Paragraph(i.level, cn), Paragraph(i.rule_code or "", cn),
                         Paragraph(i.description or "", cn), Paragraph(i.suggestion or "", cn)])
        table = Table(data, colWidths=[18*mm, 38*mm, 64*mm, 50*mm], repeatRows=1)
        table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'STSong-Light'), ('FONTSIZE', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.4, (0.8,0.8,0.8)),
            ('BACKGROUND', (0,0), (-1,0), (0.93,0.95,0.98)), ('VALIGN', (0,0), (-1,-1), 'TOP')]))
        elems.append(table)
    doc.build(elems)
    pdf_bytes = buf.getvalue(); buf.close()
    filename = f"compliance-report-{project.name}-{project_id}.pdf"
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename=\"{filename}\""})
```

**验证**：① `pip install reportlab==4.2.5`；② 对某项目 `GET /{project_id}/compliance-report/pdf` 下载 `.pdf` 且**中文正常（非方块）**；③ 核对汇总数字与 Markdown 版一致、表格含四列；④ `.../compliance-report/markdown` 仍正常。

---

## 提示词 4：分支回退闭环（资料齐全回退 + 风险回退）

**目标**：实现两条红色虚线回退——**闭环 A**（资料齐全?→否→回退节点⑤上传企业资料）：提供 realign 端点，上传后可重算匹配；**闭环 B**（风险→回退前置）：提供 remediate 端点，按 `rule_code` 把 issue 映射为上游动作（缺资料→引导上传；内容缺失→调 `batch_task_service` 重生成），留痕防死循环。

**上下文**：
- 匹配分析：`responses.py` 的 `analyze_requirement_matches`（约第 20–104 行）返每需求 `has_match/match_score/matched_sources`。
- 批量生成：`batch_task_service.start_batch(project_id, requirement_ids, owner_id)`→task_id；进度 `responses.py:get_batch_status`。
- 检索：`retrieval_service.search(query, project_id, top_k)`。
- 企业资料上传（节点⑤）：`knowledge.py` 的 `POST /api/company-documents`（已存在，本任务不改，仅作回退目标）。
- 路由 `responses.router` 挂载前缀 `/requirements`，故新端点路径用 `/requirements/projects/{project_id}/...` 风格，无需改 `router.py`。

**约束**：① 仅新增端点+1 轻量模型 `RemediationAction`，不改现有解析/生成/合规逻辑；② realign 幂等（仅重算匹配）；③ remediate 映射：`RESPONSE_SOURCE_MISSING`/`MANUAL_MATERIAL_REQUIRED`→`upload_materials`；`P0_RESPONSE_MISSING`/`RESPONSE_CONTENT_EMPTY`→`regenerate`（调 `start_batch`）；④ 防死循环：仅对 `status="未处理"` 的 issue 生成动作，`RemediationAction` 留痕；⑤ 不引入新依赖。

**改动**：

`app/models/remediation_action.py`：
```python
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.db.base import Base
class RemediationAction(Base):
    __tablename__ = "remediation_actions"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False)
    issue_id = Column(Integer, nullable=True)
    requirement_id = Column(Integer, nullable=True)
    action = Column(String(30))       # upload_materials / regenerate / manual_review
    target_stage = Column(String(20))
    status = Column(String(20), default="created")
    detail = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
```

`app/api/routes/responses.py` 末尾新增（`responses.router` 前缀为 `/requirements`，故路径如下）：
```python
from app.models.remediation_action import RemediationAction
from app.services.batch_task_service import batch_task_service

@app.post("/projects/{project_id}/realign", response_model=ApiResponse[dict])
def realign_requirements(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """闭环 A：重算需求-资料匹配（幂等）。"""
    project = db.query(BidProject).filter(BidProject.id == project_id, BidProject.owner_id == current_user.id).first()
    if not project: raise NotFoundException(message="项目不存在或无权限")
    from app.services.retrieval_service import retrieval_service
    requirements = db.query(Requirement).filter(Requirement.project_id == project_id).all()
    matched = 0
    for req in requirements:
        try: srcs = retrieval_service.search(query=req.content or "", project_id=project_id, top_k=1)
        except Exception: srcs = []
        if srcs: matched += 1
    total = len(requirements)
    return ApiResponse(data={"total": total, "matched": matched, "unmatched": total - matched,
        "message": ("已重新对齐；未匹配请回「上传企业资料」补充后再次 realign。" if (total - matched) else "资料已齐全。")})

@app.post("/requirements/projects/{project_id}/remediate", response_model=ApiResponse[dict])
def remediate_issues(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """闭环 B：按 rule_code 映射未处理 issue 为补救动作。"""
    project = db.query(BidProject).filter(BidProject.id == project_id, BidProject.owner_id == current_user.id).first()
    if not project: raise NotFoundException(message="项目不存在或无权限")
    issues = db.query(ComplianceIssue).filter(ComplianceIssue.project_id == project_id, ComplianceIssue.status == "未处理").all()
    if not issues: return ApiResponse(data={"message": "无未处理风险，无需补救。", "plan": []})
    plan, regen_req_ids = [], []
    for iss in issues:
        code = iss.rule_code or ""
        if code in ("RESPONSE_SOURCE_MISSING", "MANUAL_MATERIAL_REQUIRED"):
            action, stage = "upload_materials", "节点⑤"
        elif code in ("P0_RESPONSE_MISSING", "RESPONSE_CONTENT_EMPTY"):
            action, stage = "regenerate", "节点⑨"
            if iss.requirement_id: regen_req_ids.append(iss.requirement_id)
        else:
            action, stage = "manual_review", "人工"
        db.add(RemediationAction(project_id=project_id, issue_id=iss.id, requirement_id=iss.requirement_id,
                                 action=action, target_stage=stage, detail=iss.description or ""))
        plan.append({"issue_id": iss.id, "rule_code": code, "action": action, "target_stage": stage})
    task_id = batch_task_service.start_batch(project_id=project_id, requirement_ids=regen_req_ids, owner_id=str(current_user.id)) if regen_req_ids else None
    db.commit()
    return ApiResponse(data={"message": "已生成补救计划；缺资料类回上传企业资料，内容缺失类已触发重新生成。", "plan": plan, "regenerate_task_id": task_id})
```

**最终端点**：`POST /api/requirements/projects/{project_id}/realign`、`POST /api/requirements/projects/{project_id}/remediate`。

**验证**：① 上传前 `realign`→`unmatched>0` 提示回退；② 上传资料后 `realign`→`unmatched` 下降（闭环 A）；③ 对 `P0_RESPONSE_MISSING`/`RESPONSE_CONTENT_EMPTY` 项目 `remediate`→plan 中 action=`regenerate` 且返 `regenerate_task_id`，用 `GET /api/requirements/projects/{id}/batch-status/{task_id}` 轮询确认重生成（闭环 B）；④ `RESPONSE_SOURCE_MISSING`→action=`upload_materials`；⑤ `remediation_actions` 表留有记录。

---

## 提示词 5：响应就绪度（三维加权 + 前端增强 + 提交门槛）

**目标**：修复「响应就绪度」恒为 0% 的数据断裂，升级为三维加权（基础 50%+质量 30%+合规 20%），详情页实时显示真实值、进度条展示三维分解、提交按钮按「高风险清零+综合分≥95%」放行。

**上下文（含 Bug）**：
- `projects.py` 列表（约第 34–48 行）用 `Requirement.status=="已完成"` 算完成率——批量生成只写 `BidResponse` 从不回写 `Requirement.status`→**恒 0%**。
- `projects.py` 详情 `get_project`（约第 76–78 行）直接返 ORM 行无 `completion_rate` 字段→前端 `undefined`→显示 0%。
- `compliance.py` 报告接口（约第 144–162 行）用正确算法（基于 `Response.edited_content or ai_content`），但仅此接口生效。
- 模型：`BidResponse`（`source_refs` 是 Text 列，存 `str(list)` 单引号字面量，必须用 `ast.literal_eval` 兜底，非 `json.loads`）；`Requirement`（status/priority）；`ComplianceIssue`（`level` 高/中/低，`status` 默认"未处理"）。
- 前端：`ProjectDetailView.vue` 第 31–34 行显示 `completionRate`+`el-progress`；`handleSubmitBid()`（第 895–903 行）`rate<100` 拦截；`stores/project.js` `normalizeProject()` 无三维字段；`api/project.js` `ProjectDetail` 类型需含 `completion_rate` 及 `readiness`。

**约束**：① 新建 `readiness_service.py` 单一数据源，列表/详情/报告统一调用；② 判定统一用「`BidResponse` 有内容/有来源」，不再用 `Requirement.status`；③ 不改三个模型定义，免迁移；④ 复用 `ast.literal_eval`；⑤ 权重固定 基础0.5/质量0.3/合规0.2，提交门槛 `high_risk_pending==0 and overall>=95`；⑥ 前端兼容旧数据（字段缺失降级为单值）。

**改动**：

新增 `app/services/readiness_service.py`：
```python
import ast
from dataclasses import dataclass
from app.models.response import BidResponse
from app.models.requirement import Requirement
from app.models.compliance_issue import ComplianceIssue

def _parse_source_refs(raw):
    if not raw: return []
    if isinstance(raw, list): return raw
    try:
        import json; d = json.loads(raw)
        if isinstance(d, list): return d
    except Exception: pass
    try:
        d = ast.literal_eval(raw); return d if isinstance(d, list) else []
    except Exception: return []

@dataclass
class ReadinessResult:
    total: int = 0; has_response: int = 0; has_source: int = 0; high_risk_pending: int = 0
    base_rate: float = 0.0; quality_rate: float = 0.0; compliance_rate: float = 0.0
    overall: float = 0.0; can_submit: bool = False

class ReadinessService:
    def calculate(self, project_id: int, db) -> ReadinessResult:
        reqs = db.query(Requirement).filter(Requirement.project_id == project_id).all()
        total = len(reqs); has_response = 0; has_source = 0
        for req in reqs:
            resp = db.query(BidResponse).filter(BidResponse.requirement_id == req.id).order_by(BidResponse.id.desc()).first()
            if resp and (resp.edited_content or resp.ai_content):
                has_response += 1
                if _parse_source_refs(getattr(resp, "source_refs", None)): has_source += 1
        high_pending = db.query(ComplianceIssue).filter(ComplianceIssue.project_id == project_id,
            ComplianceIssue.level == "高", ComplianceIssue.status == "未处理").count()
        base = round(has_response / total * 100, 1) if total else 0.0
        quality = round(has_source / total * 100, 1) if total else 0.0
        compliance = round((total - high_pending) / total * 100, 1) if total else 0.0
        overall = round(base * 0.5 + quality * 0.3 + compliance * 0.2, 1)
        return ReadinessResult(total=total, has_response=has_response, has_source=has_source,
            high_risk_pending=high_pending, base_rate=base, quality_rate=quality,
            compliance_rate=compliance, overall=overall, can_submit=(high_pending == 0 and overall >= 95))

readiness_service = ReadinessService()
```

`projects.py` 列表（约第 34–48 行）改为调 `readiness_service.calculate(project.id, db)`，`item.completion_rate = r.overall`。
`projects.py` `get_project`（约第 76–78 行）改：
```python
from app.services.readiness_service import readiness_service
from app.schemas.project import ProjectDetail
r = readiness_service.calculate(project.id, db)
detail = ProjectDetail.model_validate(project)
detail.completion_rate = r.overall
detail.readiness = {"base_rate": r.base_rate, "quality_rate": r.quality_rate,
    "compliance_rate": r.compliance_rate, "overall": r.overall, "has_response": r.has_response,
    "has_source": r.has_source, "high_risk_pending": r.high_risk_pending, "can_submit": r.can_submit}
return ApiResponse(data=detail)
```
`app/schemas/project.py` 的 `ProjectDetail`（继承 `ProjectListItem`，已含 `completion_rate`）新增：`readiness: dict | None = None`。
`compliance.py` 报告接口（约第 144–162 行）改调 `readiness_service.calculate(project_id, db)`，`completion_rate = r.overall`，`total_req/completed_req` 改用 `r.total/r.has_response`。

前端：
- `api/project.js` 的 `ProjectDetail` 类型加 `readiness?: {...} | null`（含 base_rate/quality_rate/compliance_rate/overall/has_response/has_source/high_risk_pending/can_submit）。
- `stores/project.js` `normalizeProject()` 加 `readiness: item.readiness || null`。
- `ProjectDetailView.vue` 进度条区（第 28–40 行）改为：
```html
<div class="progress-section">
  <div class="progress-header"><span>响应就绪度</span>
    <span class="progress-pct">{{ readiness?.overall ?? projectStore.currentProject?.completionRate ?? 0 }}%</span></div>
  <el-progress :percentage="readiness?.overall ?? projectStore.currentProject?.completionRate ?? 0" :stroke-width="10" />
  <div class="readiness-breakdown" v-if="readiness">
    <span>基础 {{ readiness.base_rate }}%</span><span>引用 {{ readiness.quality_rate }}%</span>
    <span>合规 {{ readiness.compliance_rate }}%</span>
    <span v-if="readiness.high_risk_pending > 0" class="risk-tag">高风险 {{ readiness.high_risk_pending }}</span>
  </div>
</div>
```
（模板中取 `const readiness = projectStore.currentProject?.readiness`）
- `handleSubmitBid()`（第 895–903 行）改为：
```javascript
function handleSubmitBid() {
  const rd = projectStore.currentProject?.readiness
  if (rd && rd.high_risk_pending > 0) { ElMessage.error(`仍有 ${rd.high_risk_pending} 个高风险项未处理，请先解决`); activeTab.value = 'compliance'; return }
  const overall = rd?.overall ?? projectStore.currentProject?.completionRate ?? 0
  if (overall < 95) { ElMessage.warning(`响应就绪度 ${overall}%，建议达到 95% 后再提交`); activeTab.value = 'response'; return }
  ElMessage.success('投标提交功能开发中')
}
```

**验证**：① 已批量生成部分响应的项目详情页显示真实非 0 值（如 72%）+三维分解；② 列表页与详情页 `overall` 一致；③ 造一个 `level="高",status="未处理"` issue→合规分降、出现「高风险 N」、提交弹「仍有 N 个高风险项未处理」；④ 该 issue 改「已处理」→标签消失、合规分回升；⑤ 全响应+全来源+无未处理高风险→`overall≥95,can_submit=true`；⑥ 现有测试 `ProjectDetail` 序列化未破。

---

## 提交顺序
提示词 3（PDF）最独立安全，先做；提示词 5（就绪度）修明显 Bug 收益高，紧随；提示词 2（语义 Agent）与 5 共享 `compliance.py`，建议 5 先合、2 后合；提示词 4（回退）独立；提示词 1（编排）体量最大最后做。
