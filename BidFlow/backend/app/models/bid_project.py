from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.types import UTCDateTime


class BidProject(Base):
    __tablename__ = "bid_projects"

    id = Column(Integer, primary_key=True, index=True)
    tender_no = Column(String(50), unique=True, index=True, nullable=True, comment="系统项目编号（如 BF-2026-U3-001，自动生成）")
    tender_ref_no = Column(String(100), nullable=True, comment="招标方官方编号（如 ZB2026-NY-015，从招标文件抽取）")
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    tenderer = Column(String(200))
    deadline = Column(UTCDateTime)
    budget = Column(Integer)
    description = Column(Text)
    status = Column(String(20), default="准备中")
    created_at = Column(UTCDateTime, default=datetime.utcnow)
    updated_at = Column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="bid_projects")
    tender_documents = relationship("TenderDocument", back_populates="project", cascade="all, delete-orphan")
    requirements = relationship("Requirement", back_populates="project", cascade="all, delete-orphan")
    compliance_issues = relationship("ComplianceIssue", back_populates="project", cascade="all, delete-orphan")
    match_analysis_runs = relationship("MatchAnalysisRun", back_populates="project", cascade="all, delete-orphan")
