"""审查报告统计与 Markdown 渲染。"""

from dataclasses import dataclass

from app.services.compliance_checker import ComplianceIssue, RequirementSnapshot


@dataclass(frozen=True)
class ComplianceReport:
    total_requirements: int
    completed_requirements: int
    completion_rate: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    issues: list[ComplianceIssue]


class ReportService:
    def build(self, requirements: list[RequirementSnapshot], issues: list[ComplianceIssue]) -> ComplianceReport:
        total = len(requirements)
        completed = sum(item.status == "completed" for item in requirements)
        return ComplianceReport(
            total_requirements=total,
            completed_requirements=completed,
            completion_rate=round(completed * 100 / total) if total else 0,
            high_risk_count=sum(issue.level == "high" for issue in issues),
            medium_risk_count=sum(issue.level == "medium" for issue in issues),
            low_risk_count=sum(issue.level == "low" for issue in issues),
            issues=issues,
        )

    @staticmethod
    def to_markdown(report: ComplianceReport) -> str:
        lines = ["# BidFlow 投标审查报告", "", f"- 响应项总数：{report.total_requirements}", f"- 已完成：{report.completed_requirements}", f"- 完成度：{report.completion_rate}%", f"- 高风险：{report.high_risk_count}", f"- 中风险：{report.medium_risk_count}", f"- 低风险：{report.low_risk_count}", "", "## 风险与待办"]
        if not report.issues:
            lines.append("- 当前未发现待处理风险。")
        for issue in report.issues:
            lines.append(f"- [{issue.level}] {issue.rule_code}：{issue.description}；建议：{issue.suggestion}")
        return "\n".join(lines)
