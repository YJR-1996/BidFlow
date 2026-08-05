"""项目状态自动流转（方案 A）。

规则：
- 创建项目 → "准备中"（默认）
- 项目下所有需求全部"已完成" → 自动流转 "审核中"
- 任一需求退回"待评审/未处理"（驳回/重新生成）→ 回退 "准备中"
- 打包投递包（导出完整投标文件）→ 自动流转 "已完成"

调用点：
- responses.py update_draft（审核通过/驳回后）
- bid_document.py export_bid_package（打包后）
"""

from sqlalchemy.orm import Session

from app.models.bid_project import BidProject
from app.models.requirement import Requirement


def sync_project_status(db: Session, project_id: int) -> str:
    """按需求完成度同步项目状态，返回同步后的状态。

    仅当项目已有需求时参与流转（无需求项目保持原状态）。
    """
    # 显式 flush：调用方（如 update_draft）刚改了 req.status 尚未落库，
    # 不 flush 则下方 count() 统计不到本次改动（count 前 autoflush 在部分 session 配置下不触发）
    db.flush()

    total = db.query(Requirement).filter(Requirement.project_id == project_id).count()
    if total <= 0:
        return "准备中"

    completed = db.query(Requirement).filter(
        Requirement.project_id == project_id,
        Requirement.status == "已完成",
    ).count()

    project = db.query(BidProject).filter(BidProject.id == project_id).first()
    if not project:
        return "准备中"

    if completed == total:
        # 全部完成 → 审核中（不回退"已完成"，打包后才算完成）
        if project.status != "已完成":
            project.status = "审核中"
            db.add(project)
            db.commit()
    elif project.status == "审核中":
        # 有需求未完成 → 回退准备中
        project.status = "准备中"
        db.add(project)
        db.commit()

    return project.status


def mark_project_completed(db: Session, project_id: int) -> str:
    """打包投递包后：项目标记为已完成（投递就绪）。"""
    project = db.query(BidProject).filter(BidProject.id == project_id).first()
    if not project:
        return "准备中"
    project.status = "已完成"
    db.add(project)
    db.commit()
    return project.status
