"""迁移脚本：为 bid_projects 表添加 tender_no 列，并回填存量项目编号

运行方式: python -m app.scripts.migrate_add_tender_no

规则：BF-{年}-U{用户序号}-{当年流水}
- 用户序号：按注册时间排序（与 project_number_service._calc_user_seq 一致）
- 当年流水：按 owner_id + 年份分组计数

存量项目没有"创建时刻的用户排名"快照，这里以当前排名为准回填；
新项目在创建时由 project_number_service.generate_tender_no 生成。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from sqlalchemy import text, create_engine


def _user_rank_map(conn):
    """返回 {user_id: 注册排名(1起)}"""
    rows = conn.execute(text(
        "SELECT id, created_at FROM users ORDER BY created_at ASC, id ASC"
    )).fetchall()
    return {r[0]: i + 1 for i, r in enumerate(rows)}


def run_migration():
    sync_url = settings.DATABASE_URL.replace("+aiomysql", "+pymysql")
    engine = create_engine(sync_url, pool_pre_ping=False)

    with engine.connect() as conn:
        # 1. 检查列是否存在
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'bid_projects' "
            "AND COLUMN_NAME = 'tender_no'"
        ))
        col_exists = result.scalar() > 0

        if not col_exists:
            print("[migrate] Adding 'tender_no' column to bid_projects...")
            conn.execute(text(
                "ALTER TABLE bid_projects "
                "ADD COLUMN tender_no VARCHAR(50) NULL COMMENT '项目编号（如 BF-2026-U3-001）'"
            ))
            print("[migrate] tender_no column added successfully")
        else:
            print("[migrate] tender_no column already exists, skipping")

        # 2. 唯一索引（防止并发重号；创建接口已有重试兜底）
        idx_name = "ix_bid_projects_tender_no"
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'bid_projects' "
            "AND INDEX_NAME = :idx"
        ), {"idx": idx_name})
        idx_exists = result.scalar() > 0
        if not idx_exists:
            conn.execute(text(
                f"ALTER TABLE bid_projects ADD UNIQUE INDEX {idx_name} (tender_no)"
            ))
            print("[migrate] unique index created")
        else:
            print("[migrate] unique index already exists, skipping")

        # 3. 回填存量项目（只处理 tender_no 为空的行）
        user_rank = _user_rank_map(conn)
        projects = conn.execute(text(
            "SELECT id, owner_id, created_at FROM bid_projects WHERE tender_no IS NULL ORDER BY created_at ASC"
        )).fetchall()

        # 统计各用户各年份已用流水
        seq_map = {}  # (owner_id, year) -> count
        filled = 0
        for pid, owner_id, created_at in projects:
            rank = user_rank.get(owner_id, 1)
            year = created_at.year
            key = (owner_id, year)
            seq_map[key] = seq_map.get(key, 0) + 1
            no = f"BF-{year}-U{rank}-{seq_map[key]:03d}"
            conn.execute(text(
                "UPDATE bid_projects SET tender_no = :no WHERE id = :id"
            ), {"no": no, "id": pid})
            filled += 1

        conn.commit()
        print(f"[migrate] backfilled {filled} existing projects")
        print("[migrate] Migration completed successfully")

    engine.dispose()


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"[migrate] ERROR: {e}")
        sys.exit(1)
