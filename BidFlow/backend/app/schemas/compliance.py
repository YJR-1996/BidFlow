from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class ComplianceIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    requirement_id: Optional[int]
    level: str
    rule_code: Optional[str]
    description: Optional[str]
    suggestion: Optional[str]
    status: str
    created_at: datetime


class ComplianceReportResponse(BaseModel):
    project_id: int
    total_requirements: int
    completed_count: int
    pending_review_count: int
    risk_count: int
    completion_rate: float
    high_risks: List[ComplianceIssueResponse] = []
    medium_risks: List[ComplianceIssueResponse] = []
    low_risks: List[ComplianceIssueResponse] = []
