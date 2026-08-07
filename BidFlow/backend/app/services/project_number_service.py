"""项目编号生成服务

规则：BF-{年}-U{用户序号}-{当年流水}，示例：BF-2026-U3-001
- {年}：项目创建年份（YYYY）
- U{用户序号}：该用户在全部用户中按注册时间排序的序号（1 起），保证跨用户不重号
- {当年流水}：该用户当年创建的第 N 个项目（001 起，3 位补零）

唯一性保障：
- tender_no 列建有唯一索引（数据库层兜底）
- 并发下 count+1 可能拿到同一流水 → 调用方捕获 IntegrityError 后重试
  （见 routes/projects.py create_project 的实现）
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def generate_tender_no(db: Session, owner_id: str, created_at: datetime | None = None) -> str:
    """生成项目编号。

    Args:
        db: 数据库会话
        owner_id: 项目归属用户 ID
        created_at: 项目创建时间（用于确定年份；默认取当前时间）
    """
    from app.models.bid_project import BidProject
    from app.models.user import User

    now = created_at or datetime.utcnow()
    year = now.year

    # 用户序号：按注册时间排序的排名（1 起）
    user_seq = _calc_user_seq(db, owner_id)

    # 当年流水：该用户当年已有项目数 + 1
    seq = _calc_year_seq(db, BidProject, owner_id, year)

    return f"BF-{year}-U{user_seq}-{seq:03d}"


def _calc_user_seq(db: Session, owner_id: str) -> int:
    """用户序号 = 注册时间早于该用户的用户数 + 1。"""
    from app.models.user import User

    user = db.query(User).filter(User.id == owner_id).first()
    if user is None:
        return 1  # 用户不存在时兜底为 1（正常流程不会走到）

    earlier = (
        db.query(User)
        .filter(
            User.created_at < user.created_at
            if user.created_at is not None
            else False
        )
        .count()
    )
    return earlier + 1


def _calc_year_seq(db: Session, model, owner_id: str, year: int) -> int:
    """该用户当年已有项目数 + 1（流水号）。"""
    from sqlalchemy import func

    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1)

    count = (
        db.query(model)
        .filter(
            model.owner_id == owner_id,
            model.created_at >= start,
            model.created_at < end,
        )
        .count()
    )
    return count + 1
