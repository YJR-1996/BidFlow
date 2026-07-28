from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class TenderDocument(Base):
    __tablename__ = "tender_documents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("bid_projects.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(20))
    file_size = Column(Integer)
    status = Column(String(20), default="pending")
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("BidProject", back_populates="tender_documents")
    requirements = relationship("Requirement", back_populates="tender_document", cascade="all, delete-orphan")
