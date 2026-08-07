"""轻量合规核查公共函数

与完整 run_compliance_check（compliance.py）区分：
- 完整核查：规则引擎 + 语义 LLM + 全量重建，适合用户主动"重新核查"
- 轻量核查（本模块）：仅规则引擎，秒级，重建时**保留**语义(semantic)与用户已处理(已处理)的
  issue，适合批量重新生成响应后的自动收尾（避免把语义核查成果与处置进度抹掉）。

复用方：
- chat_service._tool_recheck（AI 助手"重新核查"工具）
- batch_task_service._run_batch 收尾（remediate 触发的批量重生成完成后自动重建风险清单）
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


def recheck_rule_issues(project_id: int, db) -> Dict:
    """轻量规则核查（规则引擎，不含语义 LLM，秒级）。与完整 run_compliance_check 行为对齐口径。

    重建策略：
    - 只删除「非 semantic 且非已处理」的 issue（即旧的规则引擎未处理 issue）
    - 保留 semantic 来源与 status="已处理" 的记录（H2：避免轻量核查抹掉完整核查的成果）
    - 基于当前响应快照重新生成规则 issue（status="未处理", source="rule"）

    无需求时返回 {"error": "..."}，与 chat_service 调用约定一致。
    """
    from app.models.requirement import Requirement
    from app.models.compliance_issue import ComplianceIssue
    from app.models.match_analysis import MatchAnalysisRun, MatchAnalysisDetail
    from app.services.compliance_checker import ComplianceChecker, RequirementSnapshot
    from app.services.text_utils import parse_source_refs  # L1：公共解析

    reqs = db.query(Requirement).filter(Requirement.project_id == project_id).all()
    if not reqs:
        return {"error": "该项目暂无需求项，请先解析招标文件"}

    # L14：预取最新一次比对分析的未匹配集合（has_match=false），用于快照 match_unmatched 字段。
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

    snapshots = []
    for req in reqs:
        resp_content, source_refs, resp_status = "", [], None
        # L13：只取「最新一条」响应（id 降序）——与 requirements.py:98 / readiness_service / 比对逻辑口径一致。
        # 原实现 for r in responses（ORM 默认 id 升序）会取到历史遗留的旧响应（如 pending_review/草稿），
        # 对已批准（approved）的 P0 误报「P0 响应项尚未完成」。
        responses = sorted(getattr(req, "responses", None) or [], key=lambda r: (r.id or 0), reverse=True)
        if responses:
            latest = responses[0]
            resp_content = latest.edited_content or latest.ai_content or ""
            if getattr(latest, "source_refs", None):
                source_refs = parse_source_refs(latest.source_refs)
            if resp_content:
                resp_status = latest.status
        snapshot_status = resp_status or req.status or "未处理"
        # 双重保险：needs_manual 状态下 source_refs 必有历史残留，强制清空，
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

    issues = ComplianceChecker().check(snapshots)

    # 只重建「规则引擎 + 未处理」部分；保留语义合规(semantic)与用户已处理(已处理)记录
    keep = db.query(ComplianceIssue).filter(
        ComplianceIssue.project_id == project_id,
        (ComplianceIssue.source == "semantic") | (ComplianceIssue.status == "已处理"),
    ).all()
    keep_ids = {i.id for i in keep}
    db.query(ComplianceIssue).filter(
        ComplianceIssue.project_id == project_id,
        ComplianceIssue.id.notin_(keep_ids) if keep_ids else ComplianceIssue.id.isnot(None),
    ).delete(synchronize_session=False)
    for it in issues:
        db.add(ComplianceIssue(
            project_id=project_id,
            requirement_id=it.requirement_id,
            # H1：ComplianceChecker 返回英文 level，必须中文化入库（下游按"高/中/低"统计）
            level={"high": "高", "medium": "中", "low": "低"}.get(it.level, it.level),
            rule_code=it.rule_code,
            description=it.description,
            suggestion=it.suggestion,
            status="未处理",
            source="rule",
        ))
    db.commit()

    return {
        "checked": len(snapshots),
        "rule_issue_count": len(issues),
        # issues 来自 ComplianceChecker（英文 level），统计按英文判断
        "high": sum(1 for i in issues if i.level == "high"),
        "medium": sum(1 for i in issues if i.level == "medium"),
        "low": sum(1 for i in issues if i.level == "low"),
        "issues": [
            {
                "requirement_id": i.requirement_id,
                "rule_code": i.rule_code,
                "description": i.description,
            }
            for i in issues[:10]
        ],
    }
