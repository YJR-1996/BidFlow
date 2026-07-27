"""成员 D 的合规核查控制器；A 接入 FastAPI 时只需调用这些方法。"""

from app.schemas.compliance import ComplianceIssuePayload, ComplianceReportPayload
from app.services.compliance_checker import ComplianceChecker, RequirementSnapshot
from app.services.report_service import ReportService


class ComplianceController:
    def __init__(self, checker: ComplianceChecker | None = None, reports: ReportService | None = None) -> None:
        self._checker = checker or ComplianceChecker()
        self._reports = reports or ReportService()

    def check(self, requirements: list[RequirementSnapshot]) -> ComplianceReportPayload:
        report = self._reports.build(requirements, self._checker.check(requirements))
        issues = [ComplianceIssuePayload(i.requirement_id, i.rule_code, i.level, i.description, i.suggestion).__dict__ for i in report.issues]
        return ComplianceReportPayload(report.total_requirements, report.completed_requirements, report.completion_rate, report.high_risk_count, report.medium_risk_count, report.low_risk_count, issues)

    def export_markdown(self, requirements: list[RequirementSnapshot]) -> str:
        report = self._reports.build(requirements, self._checker.check(requirements))
        return self._reports.to_markdown(report)
