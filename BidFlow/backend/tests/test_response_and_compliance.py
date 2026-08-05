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
    """P0 + 无可引用资料 → P0_SOURCE_MISSING（先补资料，而非误导"补充响应内容"）"""
    issue = ComplianceChecker().check(
        [RequirementSnapshot(1, "必须提供营业执照", "P0", "", [], "editing")]
    )[0]

    assert issue.rule_code == "P0_SOURCE_MISSING"
    assert issue.level == "high"
    assert "资料" in issue.description


def test_marks_p0_with_empty_content_as_high_risk_when_pending_review():
    """P0 未完成（pending_review 仍非已完成状态）且无资料 → P0_SOURCE_MISSING/high，
    且 not p0_incomplete 守卫会抑制 RESPONSE_CONTENT_EMPTY，避免对同一空响应重复告警。"""
    issue = ComplianceChecker().check(
        [RequirementSnapshot(1, "必须提供营业执照", "P0", "", [], "pending_review")]
    )[0]

    assert issue.rule_code == "P0_SOURCE_MISSING"
    assert issue.level == "high"


def test_marks_p0_with_sources_but_empty_content_as_response_missing():
    """P0 + 资料齐 + 响应空 → P0_RESPONSE_MISSING（瓶颈是响应，不是资料）"""
    issue = ComplianceChecker().check(
        [RequirementSnapshot(1, "必须提供营业执照", "P0", "", ["营业执照.pdf#1"], "pending_review")]
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
        RequirementSnapshot(1, "营业执照", "P0", "", [], "editing"),
        RequirementSnapshot(2, "案例", "P1", "已有案例", ["案例.pdf#1"], "completed"),
    ]
    report = ReportService().build(requirements, ComplianceChecker().check(requirements))

    assert report.total_requirements == 2
    assert report.completed_requirements == 1
    assert report.completion_rate == 50
    assert report.high_risk_count == 1


def test_report_does_not_count_pending_review_as_completed():
    """pending_review 是中间态（已起草待评审），不属于 COMPLETED_STATUSES，不应计入 completed。
    即便已有响应内容，status-based 回退口径仍只认已完成状态；生产接口用 readiness.has_response
    作为单一数据源，与此处单元测试的回退口径相互独立。"""
    requirements = [
        RequirementSnapshot(1, "营业执照", "P1", "已起草营业执照说明", ["案例.pdf#1"], "pending_review"),
        RequirementSnapshot(2, "案例", "P1", "已有案例", ["案例.pdf#1"], "completed"),
    ]
    report = ReportService().build(requirements, ComplianceChecker().check(requirements))

    assert report.total_requirements == 2
    assert report.completed_requirements == 1
    assert report.completion_rate == 50
