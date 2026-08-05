import json
import uuid
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from app.db.base import Base
from app.models.types import UTCDateTime


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(Integer, nullable=False, index=True)
    current_stage = Column(String(20), default="parse")
    status = Column(String(20), default="running")  # running / awaiting_review / completed / failed
    context_json = Column(Text)
    created_at = Column(UTCDateTime, default=datetime.utcnow)
    updated_at = Column(UTCDateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
