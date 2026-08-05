from dataclasses import dataclass, field

from app.models.response import BidResponse
from app.models.requirement import Requirement
from app.models.compliance_issue import ComplianceIssue
from app.models.match_analysis import MatchAnalysisRun, MatchAnalysisDetail
from app.services.text_utils import parse_source_refs  # L1：公共解析（原 _parse_source_refs 收口）


@dataclass
class ReadinessResult:
    """响应就绪度计算结果。

    三维加权：基础 50% + 质量 30% + 合规 20%
    """

    total: int = 0
    has_response: int = 0
    has_source: int = 0
    high_risk_pending: int = 0
    medium_risk_pending: int = 0   # 中风险待处理，与项目列表/合规报告统一口径
    total_risk_pending: int = 0    # 高+中 待处理总数（统一指标）

    # 三维分项百分比
    base_rate: float = 0.0         # 基础维度：有响应内容的需求占比
    quality_rate: float = 0.0      # 质量维度：有响应且有来源引用的需求占比
    compliance_rate: float = 0.0   # 合规维度：无高风险未处理需求的占比

    # 综合评分
    overall: float = 0.0
    can_submit: bool = False


class ReadinessService:
    """响应就绪度计算服务——单一数据源。

    权重固定：基础 0.5 / 质量 0.3 / 合规 0.2
    提交门槛：high_risk_pending == 0 and overall >= 95
    """

    def calculate(self, project_id: int, db) -> ReadinessResult:
        reqs = db.query(Requirement).filter(
            Requirement.project_id == project_id
        ).all()
        total = len(reqs)

        has_response = 0
        has_source = 0  # 仅用于兼容性统计；质量维度已改用真实匹配（见下方 matched_count）

        # 查询最近一次比对分析的「真实匹配」状态：避免 AI 编造 source_refs 导致质量假阳性 100%
        # （之前用 source_refs 非空判断：LLM 在未匹配时也会编造文件名+相似度 → 质量虚高）
        latest_run = (
            db.query(MatchAnalysisRun)
            .filter(MatchAnalysisRun.project_id == project_id)
            .order_by(MatchAnalysisRun.created_at.desc())
            .first()
        )
        matched_req_ids: set[int] = set()
        if latest_run:
            details = (
                db.query(MatchAnalysisDetail)
                .filter(
                    MatchAnalysisDetail.run_id == latest_run.id,
                    MatchAnalysisDetail.has_match.is_(True),
                )
                .all()
            )
            matched_req_ids = {d.requirement_id for d in details}
        # H5：历史 run 的 detail 可能含已删除需求 → 与当前需求求交集，保证 quality ≤ 100%
        current_req_ids = {r.id for r in reqs}
        matched_req_ids &= current_req_ids
        matched_count = len(matched_req_ids)  # 真正匹配的需求数

        for req in reqs:
            resp = (
                db.query(BidResponse)
                .filter(BidResponse.requirement_id == req.id)
                .order_by(BidResponse.id.desc())
                .first()
            )
            if resp and (resp.edited_content or resp.ai_content):
                has_response += 1
                refs = parse_source_refs(getattr(resp, "source_refs", None))
                if refs:
                    has_source += 1

        high_pending = (
            db.query(ComplianceIssue)
            .filter(
                ComplianceIssue.project_id == project_id,
                ComplianceIssue.level == "高",
                ComplianceIssue.status == "未处理",
            )
            .count()
        )
        medium_pending = (
            db.query(ComplianceIssue)
            .filter(
                ComplianceIssue.project_id == project_id,
                ComplianceIssue.level == "中",
                ComplianceIssue.status == "未处理",
            )
            .count()
        )
        total_pending = high_pending + medium_pending

        base = round(has_response / total * 100, 1) if total else 0.0
        # 质量维度：真正匹配（比对分析 has_match=true）而非 source_refs 非空
        quality = round(matched_count / total * 100, 1) if total else 0.0
        compliance = round((total - high_pending) / total * 100, 1) if total else 0.0
        overall = round(base * 0.5 + quality * 0.3 + compliance * 0.2, 1)

        return ReadinessResult(
            total=total,
            has_response=has_response,
            has_source=has_source,
            high_risk_pending=high_pending,
            medium_risk_pending=medium_pending,
            total_risk_pending=total_pending,
            base_rate=base,
            quality_rate=quality,
            compliance_rate=compliance,
            overall=overall,
            can_submit=(high_pending == 0 and overall >= 95),
        )


readiness_service = ReadinessService()
