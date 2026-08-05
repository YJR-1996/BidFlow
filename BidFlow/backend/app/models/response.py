from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, String
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.types import UTCDateTime


class Response(Base):
    __tablename__ = "responses"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    ai_content = Column(Text)
    edited_content = Column(Text)
    source_refs = Column(Text)
    status = Column(String(20), default="草稿")
    updated_at = Column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    requirement = relationship("Requirement", back_populates="responses")


# BidResponse 是 Response 的别名，兼容不同文件中的导入
BidResponse = Response
