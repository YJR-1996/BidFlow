"""集中导入模型，供 init_db 注册所有 ORM 表。"""

from app.db.session import Base
from app.models.user import User  # noqa: F401
from app.models.bid_project import BidProject  # noqa: F401
from app.models.tender_document import TenderDocument  # noqa: F401
from app.models.requirement import Requirement  # noqa: F401
from app.models.company_document import CompanyDocument  # noqa: F401
from app.models.response import Response  # noqa: F401
from app.models.compliance_issue import ComplianceIssue  # noqa: F401

__all__ = ["Base"]
