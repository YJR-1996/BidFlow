from app.db.session import Base

from app.models.user import User
from app.models.bid_project import BidProject
from app.models.tender_document import TenderDocument
from app.models.requirement import Requirement
from app.models.company_document import CompanyDocument
from app.models.response import Response
from app.models.compliance_issue import ComplianceIssue

__all__ = ["Base"]
from sqlalchemy.orm import DeclarativeBase

from app.models.user import User  # noqa: F401  # 导入以注册到 Base._decl_class_registry


class Base(DeclarativeBase):
    """ORM 基类，所有模型继承此类"""
    pass
