from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    bid_projects = relationship("BidProject", back_populates="owner", cascade="all, delete-orphan")
    company_documents = relationship("CompanyDocument", back_populates="owner", cascade="all, delete-orphan")
