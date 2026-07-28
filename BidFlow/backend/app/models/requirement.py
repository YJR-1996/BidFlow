from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("bid_projects.id"), nullable=False)
    tender_document_id = Column(Integer, ForeignKey("tender_documents.id"))
    category = Column(String(50), default="other")
    content = Column(Text, nullable=False)
    source_text = Column(Text)
    source_ref = Column(String(200))
    priority = Column(String(10), default="P2")
    status = Column(String(20), default="未处理")
    assignee_id = Column(String(36), ForeignKey("users.id"))
    risk_level = Column(String(10), default="低")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("BidProject", back_populates="requirements")
    tender_document = relationship("TenderDocument", back_populates="requirements")
    responses = relationship("Response", back_populates="requirement", cascade="all, delete-orphan")
    compliance_issues = relationship("ComplianceIssue", back_populates="requirement", cascade="all, delete-orphan")
