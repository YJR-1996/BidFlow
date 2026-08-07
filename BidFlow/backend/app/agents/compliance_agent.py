import logging
from typing import List, Dict

from app.agents.base import BaseAgent, WorkflowContext
from app.services.compliance_checker import ComplianceChecker, RequirementSnapshot, ComplianceIssue
from app.models.requirement import Requirement
from app.models.response import Response as BidResponse
from sqlalchemy import func

logger = logging.getLogger(__name__)


def build_snapshots_from_requirements(db, requirements: List[Dict]) -> List[RequirementSnapshot]:
    """从 project 的 requirements 及其当前响应状态构建合规检查快照。"""
    from app.services.text_utils import parse_source_refs

    req_ids = [r["id"] for r in requirements]

    latest_resp_map: Dict[int, Dict] = {}
    if req_ids:
        subquery = (
            db.query(
                BidResponse.requirement_id,
                func.max(BidResponse.id).label("max_id"),
            )
            .filter(BidResponse.requirement_id.in_(req_ids))
            .group_by(BidResponse.requirement_id)
            .subquery()
        )
        resp_rows = (
            db.query(BidResponse)
            .filter(BidResponse.id.in_(db.query(subquery.c.max_id)))
            .all()
        )
        resp_status_map = {r.requirement_id: r.status for r in resp_rows}
        resp_content_map = {
            r.requirement_id: (r.edited_content or r.ai_content or "") for r in resp_rows
        }
        resp_source_map = {
            r.requirement_id: parse_source_refs(getattr(r, "source_refs", None))
            for r in resp_rows
        }
        latest_resp_map = {
            rid: {
                "status": resp_status_map.get(rid) or "",
                "content": resp_content_map.get(rid, ""),
                "source_refs": resp_source_map.get(rid, []),
            }
            for rid in req_ids
        }

    snapshots: List[RequirementSnapshot] = []
    for req in requirements:
        resp = latest_resp_map.get(req["id"], {})
        resp_content = resp.get("content", "")
        source_refs = resp.get("source_refs", [])
        status = resp.get("status") or req.get("status") or "未处理"
        # 与主通道 compliance.py 同款双重保险：needs_manual / 待人工补充 状态下
        # source_refs 必有历史残留，强制清空，避免规则误判「有资料」导致 P0 报成
        # 「响应缺失」而非「资料缺失」
        if status == "needs_manual" or resp_content.startswith("待人工补充"):
            source_refs = []
        snapshots.append(
            RequirementSnapshot(
                requirement_id=req["id"],
                content=req.get("content", ""),
                priority=req.get("priority", "P2"),
                response_content=resp_content,
                source_refs=source_refs,
                status=status,
            )
        )
    return snapshots


class ComplianceAgent(BaseAgent):
    """合规检查 Agent：对当前阶段的需求做合规核查。"""

    name = "compliance"

    def run(self, ctx: WorkflowContext, db) -> WorkflowContext:
        checker = ComplianceChecker()

        all_reqs = (
            db.query(Requirement)
            .filter(Requirement.project_id == ctx.project_id)
            .all()
        )

        serialized = [
            {
                "id": r.id,
                "content": r.content,
                "priority": r.priority,
                "status": r.status,
                "source_ref": r.source_ref,
            }
            for r in all_reqs
        ]
        snapshots = build_snapshots_from_requirements(db, serialized)
        issues = checker.check(snapshots)

        ctx.compliance_issues = [
            {
                "requirement_id": issue.requirement_id,
                "rule_code": issue.rule_code,
                "level": issue.level,
                "description": issue.description,
                "suggestion": issue.suggestion,
            }
            for issue in issues
        ]

        high_count = sum(1 for i in ctx.compliance_issues if i["level"] == "high")
        if high_count > 0:
            ctx.human_review_required = True
            ctx.review_reason = "检测到高风险合规问题，需人工审核后继续。"

        ctx.requirements = serialized
        logger.info(
            "[ComplianceAgent] project=%d issues=%d high=%d review_needed=%s",
            ctx.project_id,
            len(ctx.compliance_issues),
            high_count,
            ctx.human_review_required,
        )
        return ctx
