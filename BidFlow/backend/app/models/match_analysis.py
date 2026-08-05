"""比对分析持久化数据模型

每次"开始比对分析"产生一条 MatchAnalysisRun 记录；
逐条匹配结果拆到 MatchAnalysisDetail 表，便于复用和增量更新。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.types import UTCDateTime


class MatchAnalysisRun(Base):
    __tablename__ = "match_analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("bid_projects.id"), nullable=False, index=True)

    # 汇总指标（与前端 summary 对齐）
    total = Column(Integer, default=0)
    matched = Column(Integer, default=0)
    unmatched = Column(Integer, default=0)
    match_rate = Column(Float, default=0.0)

    # 谁触发（owner_id），便于权限校验；类型必须与 users.id 一致（CHAR(36) UUID）
    triggered_by = Column(CHAR(36), ForeignKey("users.id"))

    created_at = Column(UTCDateTime, default=datetime.utcnow, index=True)

    project = relationship("BidProject", back_populates="match_analysis_runs")
    details = relationship(
        "MatchAnalysisDetail",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MatchAnalysisDetail(Base):
    __tablename__ = "match_analysis_details"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("match_analysis_runs.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False, index=True)

    # 需求快照（避免后续修改/删除 Requirement 时丢数据）
    content = Column(Text)
    category = Column(String(50))
    priority = Column(String(10))
    req_status = Column(String(20))

    # 比对结果
    has_match = Column(Boolean, default=False)
    match_count = Column(Integer, default=0)
    match_score = Column(Float, default=0.0)
    matched_sources = Column(Text)  # JSON 字符串：[{filename, score, content_preview}]

    # LLM 语义分析字段
    coverage = Column(String(20))   # full/partial/missing
    gap = Column(Text)
    confidence = Column(Float, default=0.0)
    pending_review = Column(Boolean, default=False)

    # 响应状态（用于卡片 UI）
    has_response = Column(Boolean, default=False)
    response_status = Column(String(20))

    created_at = Column(UTCDateTime, default=datetime.utcnow)

    run = relationship("MatchAnalysisRun", back_populates="details")
    requirement = relationship("Requirement")