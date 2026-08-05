"""成员 D 的零依赖业务测试；运行：python -m unittest tests.test_d_domain。"""

import unittest

from app.services.compliance_checker import ComplianceChecker, RequirementSnapshot
from app.services.report_service import ReportService
from app.services.response_generation_service import ResponseGenerationService


class FakeLlmClient:
    def __init__(self):
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        return "根据企业案例材料，建议提供对应项目案例。"


class ResponseAndComplianceTests(unittest.TestCase):
    def test_returns_needs_manual_without_sources(self):
        client = FakeLlmClient()
        result = ResponseGenerationService(client).generate(
            {"requirement_id": 1, "content": "提供类似项目案例"}, []
        )
        self.assertEqual("needs_manual", result.status)
        self.assertEqual("待人工补充：未检索到可引用的企业资料。", result.content)
        self.assertEqual([], result.sources)
        self.assertEqual(0, client.calls)

    def test_generates_draft_with_sources(self):
        client = FakeLlmClient()
        sources = [{"content": "我方已完成某信息化项目。", "filename": "案例材料.pdf", "source_ref": "第 2 页", "score": 0.92}]
        result = ResponseGenerationService(client).generate(
            {"requirement_id": 2, "content": "提供类似项目案例"}, sources
        )
        self.assertEqual("pending_review", result.status)
        self.assertEqual(sources, result.sources)
        self.assertEqual(1, client.calls)

    def test_p0_empty_response_is_high_risk(self):
        # P0 + 无资料来源 → 按新规则拆分为 P0_SOURCE_MISSING（先补资料），仍为 high
        issue = ComplianceChecker().check(
            [RequirementSnapshot(1, "必须提供营业执照", "P0", "", [], "pending_review")]
        )[0]
        self.assertEqual("P0_SOURCE_MISSING", issue.rule_code)
        self.assertEqual("high", issue.level)

    def test_report_counts_completion_and_risks(self):
        requirements = [
            RequirementSnapshot(1, "营业执照", "P0", "", [], "pending_review"),
            RequirementSnapshot(2, "案例", "P1", "已有案例", ["案例.pdf#1"], "completed"),
        ]
        report = ReportService().build(requirements, ComplianceChecker().check(requirements))
        self.assertEqual(2, report.total_requirements)
        self.assertEqual(1, report.completed_requirements)
        self.assertEqual(50, report.completion_rate)
        self.assertEqual(1, report.high_risk_count)


if __name__ == "__main__":
    unittest.main()
