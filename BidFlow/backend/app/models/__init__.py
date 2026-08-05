from app.models.user import User
from app.models.bid_project import BidProject
from app.models.tender_document import TenderDocument
from app.models.requirement import Requirement
from app.models.company_document import CompanyDocument
from app.models.response import Response
from app.models.compliance_issue import ComplianceIssue
from app.models.workflow_run import WorkflowRun
from app.models.remediation_action import RemediationAction
# match_analysis 必须在包初始化时导入，否则 BidProject.relationship("MatchAnalysisRun")
# 的字符串引用无法解析，会导致整个 ORM mapper 配置失败
from app.models.match_analysis import MatchAnalysisRun, MatchAnalysisDetail

__all__ = [
    "User",
    "BidProject",
    "TenderDocument",
    "Requirement",
    "CompanyDocument",
    "Response",
    "ComplianceIssue",
    "WorkflowRun",
    "RemediationAction",
    "MatchAnalysisRun",
    "MatchAnalysisDetail",
]
