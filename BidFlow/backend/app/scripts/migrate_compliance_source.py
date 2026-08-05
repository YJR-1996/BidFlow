"""迁移脚本：为 compliance_issues 表添加 source 列

运行方式: python -m app.scripts.migrate_compliance_source

该脚本:
  1. 检查 source 列是否存在
  2. 不存在则添加 (source VARCHAR(20) DEFAULT 'rule')
  3. 用于区分合规问题来源：rule=规则引擎, semantic=语义合规Agent
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.config import settings
from sqlalchemy import create_engine


def run_migration():
    """执行迁移（使用同步引擎）"""
    sync_url = settings.DATABASE_URL.replace("+aiomysql", "+pymysql")
    engine = create_engine(sync_url, pool_pre_ping=False)

    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'compliance_issues' "
            "AND COLUMN_NAME = 'source'"
        ))
        source_exists = result.scalar() > 0

        if not source_exists:
            print("[migrate] Adding 'source' column to compliance_issues...")
            conn.execute(text(
                "ALTER TABLE compliance_issues "
                "ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'rule' "
                "COMMENT 'rule=规则引擎, semantic=语义合规Agent'"
            ))
            print("[migrate] source column added successfully")
        else:
            print("[migrate] source column already exists, skipping")

        conn.commit()
        print("[migrate] Migration completed successfully")

    engine.dispose()


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"[migrate] ERROR: {e}")
        sys.exit(1)
