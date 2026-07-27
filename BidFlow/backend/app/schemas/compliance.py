"""D 模块的合规报告结构化 JSON 契约。"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ComplianceIssuePayload:
    requirement_id: int
    rule_code: str
    level: str
    description: str
    suggestion: str


@dataclass(frozen=True)
class ComplianceReportPayload:
    total_requirements: int
    completed_requirements: int
    completion_rate: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    issues: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
