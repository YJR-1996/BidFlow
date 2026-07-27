"""成员 D 的合规问题领域模型；后续由 A 接入 SQLAlchemy 表。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class StoredComplianceIssue:
    project_id: int
    requirement_id: int | None
    rule_code: str
    level: str
    description: str
    suggestion: str
    status: str = "open"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
