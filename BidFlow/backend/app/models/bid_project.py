from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db.session import Base


class BidProject(Base):
    __tablename__ = "bid_projects"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    tenderer = Column(String(200))
    deadline = Column(DateTime)
    budget = Column(Integer)
    description = Column(Text)
    status = Column(String(20), default="准备中")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="bid_projects")
    tender_documents = relationship("TenderDocument", back_populates="project", cascade="all, delete-orphan")
    requirements = relationship("Requirement", back_populates="project", cascade="all, delete-orphan")
    compliance_issues = relationship("ComplianceIssue", back_populates="project", cascade="all, delete-orphan")
