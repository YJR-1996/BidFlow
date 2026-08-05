import uuid
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from app.db.base import Base
from app.models.types import UTCDateTime


class RemediationAction(Base):
    """补救动作留痕表：记录合规风险对应的回退/补救动作。

    用于：
    - 闭环 A（资料齐全回退）：realign 后未匹配需求需上传资料
    - 闭环 B（风险回退）：按 rule_code 映射为 upload_materials / regenerate / manual_review
    - 防止死循环：仅对 status="未处理" 的 issue 生成动作，每次留痕
    """

    __tablename__ = "remediation_actions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    issue_id = Column(Integer, nullable=True, index=True)
    requirement_id = Column(Integer, nullable=True, index=True)
    action = Column(String(30))         # upload_materials / regenerate / manual_review
    target_stage = Column(String(20))    # 对应的节点或阶段标识
    status = Column(String(20), default="created")  # created / executing / done / failed
    detail = Column(Text)
    created_at = Column(UTCDateTime, default=datetime.utcnow)
