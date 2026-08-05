from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class ComplianceIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    requirement_id: Optional[int]
    requirement_content: Optional[str] = None  # 关联需求内容摘要（前80字），供前端展示
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
    # 三维健康度分项（与 readiness_service 对齐，前端"综合健康度"卡片展示分解）
    base_rate: float = 0.0          # 基础维度：有响应内容的需求占比
    quality_rate: float = 0.0       # 质量维度：有响应且有来源引用的需求占比
    compliance_rate: float = 0.0    # 合规维度：无高风险未处理需求的占比
    high_risk_pending: int = 0      # 高风险未处理数（与项目详情顶部一致）
    high_risks: List[ComplianceIssueResponse] = []
    medium_risks: List[ComplianceIssueResponse] = []
    low_risks: List[ComplianceIssueResponse] = []


# Payload schemas used by ComplianceController
class ComplianceIssuePayload(BaseModel):
    """合规问题 Payload（用于 Controller 内部数据传输）"""
    requirement_id: int
    rule_code: str
    level: str
    description: str
    suggestion: str


class ComplianceReportPayload(BaseModel):
    """合规报告 Payload（用于 Controller 内部数据传输）"""
    total_requirements: int
    completed_requirements: int
    completion_rate: float
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    issues: List[dict]
