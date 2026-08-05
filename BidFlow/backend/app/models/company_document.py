from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.types import UTCDateTime


class CompanyDocument(Base):
    __tablename__ = "company_documents"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(20))
    category = Column(String(50), nullable=True)
    tags = Column(String(500), nullable=True)
    status = Column(String(20), default="pending")
    error_message = Column(Text, nullable=True)
    created_at = Column(UTCDateTime, default=datetime.utcnow)

    # ---- 两级隔离模型 ----
    # scope: "company" = 公司级共享资料，所有项目可见
    #         "project" = 项目级专属资料，仅绑定 project_id 可见
    scope = Column(String(20), nullable=False, default="company", index=True)
    # 当 scope="project" 时绑定的项目 ID
    project_id = Column(Integer, nullable=True, index=True)

    owner = relationship("User", back_populates="company_documents")
