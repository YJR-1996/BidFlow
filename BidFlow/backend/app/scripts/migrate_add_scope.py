"""迁移脚本：为 company_documents 表添加 scope 列

运行方式: python -m app.scripts.migrate_add_scope

该脚本:
  1. 检查 scope 列是否存在
  2. 不存在则添加 (scope VARCHAR(20) DEFAULT 'company')
  3. 同时回补 project_id 列 (用于项目级资料绑定)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from sqlalchemy import text, create_engine


def run_migration():
    """执行迁移（使用同步引擎）"""
    sync_url = settings.DATABASE_URL.replace("+aiomysql", "+pymysql")
    engine = create_engine(sync_url, pool_pre_ping=False)

    with engine.connect() as conn:
        # 检查 scope 列是否存在
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'company_documents' "
            "AND COLUMN_NAME = 'scope'"
        ))
        scope_exists = result.scalar() > 0

        if not scope_exists:
            print("[migrate] Adding 'scope' column to company_documents...")
            conn.execute(text(
                "ALTER TABLE company_documents "
                "ADD COLUMN scope VARCHAR(20) NOT NULL DEFAULT 'company' "
                "COMMENT 'company=公司级共享, project=项目级专属'"
            ))
            print("[migrate] scope column added successfully")
        else:
            print("[migrate] scope column already exists, skipping")

        # 检查 project_id 列是否存在
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'company_documents' "
            "AND COLUMN_NAME = 'project_id'"
        ))
        pid_exists = result.scalar() > 0

        if not pid_exists:
            print("[migrate] Adding 'project_id' column to company_documents...")
            conn.execute(text(
                "ALTER TABLE company_documents "
                "ADD COLUMN project_id INT NULL "
                "COMMENT '绑定的项目ID，scope=project时必填'"
            ))
            print("[migrate] project_id column added successfully")
        else:
            print("[migrate] project_id column already exists, skipping")

        conn.commit()
        print("[migrate] Migration completed successfully")

    engine.dispose()


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"[migrate] ERROR: {e}")
        sys.exit(1)
