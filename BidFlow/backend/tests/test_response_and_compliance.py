from app.services.compliance_checker import ComplianceChecker, RequirementSnapshot
from app.services.report_service import ReportService
from app.services.response_generation_service import ResponseGenerationService


class FakeLlmClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        return "根据企业案例材料，建议提供对应项目案例。"


def test_returns_needs_manual_without_sources_and_does_not_call_llm():
    client = FakeLlmClient()
    result = ResponseGenerationService(client).generate(
        requirement={"requirement_id": 1, "content": "提供类似项目案例"},
        sources=[],
    )

    assert result.status == "needs_manual"
    assert result.content == "待人工补充：未检索到可引用的企业资料。"
    assert result.sources == []
    assert client.calls == 0


def test_generates_pending_review_draft_with_sources():
    client = FakeLlmClient()
    sources = [{"content": "我方已完成某信息化项目。", "filename": "案例材料.pdf", "source_ref": "第 2 页", "score": 0.92}]
    result = ResponseGenerationService(client).generate(
        requirement={"requirement_id": 2, "content": "提供类似项目案例"}, sources=sources
    )

    assert result.status == "pending_review"
    assert result.content == "根据企业案例材料，建议提供对应项目案例。"
    assert result.sources == sources
    assert client.calls == 1


def test_marks_empty_p0_requirement_as_high_risk():
    issue = ComplianceChecker().check(
        [RequirementSnapshot(1, "必须提供营业执照", "P0", "", [], "pending_review")]
    )[0]

    assert issue.rule_code == "P0_RESPONSE_MISSING"
    assert issue.level == "high"


def test_marks_response_without_sources_as_medium_risk():
    issue = ComplianceChecker().check(
        [RequirementSnapshot(2, "提供案例", "P1", "已有案例", [], "pending_review")]
    )[0]

    assert issue.rule_code == "RESPONSE_SOURCE_MISSING"
    assert issue.level == "medium"


def test_report_counts_completion_and_risk_levels():
    requirements = [
        RequirementSnapshot(1, "营业执照", "P0", "", [], "pending_review"),
        RequirementSnapshot(2, "案例", "P1", "已有案例", ["案例.pdf#1"], "completed"),
    ]
    report = ReportService().build(requirements, ComplianceChecker().check(requirements))

    assert report.total_requirements == 2
    assert report.completed_requirements == 1
    assert report.completion_rate == 50
    assert report.high_risk_count == 1
