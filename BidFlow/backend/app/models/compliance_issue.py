from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.session import Base


class ComplianceIssue(Base):
    __tablename__ = "compliance_issues"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("bid_projects.id"), nullable=False)
    requirement_id = Column(Integer, ForeignKey("requirements.id"))
    level = Column(String(10), default="低")
    rule_code = Column(String(50))
    description = Column(Text)
    suggestion = Column(Text)
    status = Column(String(20), default="未处理")
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("BidProject", back_populates="compliance_issues")
    requirement = relationship("Requirement", back_populates="compliance_issues")
