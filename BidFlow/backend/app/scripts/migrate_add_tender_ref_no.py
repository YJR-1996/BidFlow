"""迁移脚本：为 bid_projects 表添加 tender_ref_no 列（招标方官方编号）

运行方式: python -m app.scripts.migrate_add_tender_ref_no

说明：
- tender_ref_no 存招标文件里的官方编号（如 ZB2026-NY-015），
  与系统自动生成的 tender_no（BF-2026-U3-001）是不同概念。
- 该列无唯一约束（官方编号可能重复，不需要系统级唯一）。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from sqlalchemy import text, create_engine


def run_migration():
    sync_url = settings.DATABASE_URL.replace("+aiomysql", "+pymysql")
    engine = create_engine(sync_url, pool_pre_ping=False)

    with engine.connect() as conn:
        # 检查列是否存在
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'bid_projects' "
            "AND COLUMN_NAME = 'tender_ref_no'"
        ))
        col_exists = result.scalar() > 0

        if not col_exists:
            print("[migrate] Adding 'tender_ref_no' column to bid_projects...")
            conn.execute(text(
                "ALTER TABLE bid_projects "
                "ADD COLUMN tender_ref_no VARCHAR(100) NULL "
                "COMMENT '招标方官方编号（如 ZB2026-NY-015，从招标文件抽取）'"
            ))
            print("[migrate] tender_ref_no column added successfully")
        else:
            print("[migrate] tender_ref_no column already exists, skipping")

        # 回填存量：从 requirements 表中内容形如「项目编号：xxx」的需求回填到项目
        # 正则匹配 source='parsed' 且 content 以编号类前缀开头的需求
        filled = 0
        rows = conn.execute(text(
            "SELECT r.project_id, r.content FROM requirements r "
            "WHERE r.tender_document_id IS NOT NULL "
            "AND (r.content LIKE '项目编号：%' OR r.content LIKE '招标编号：%' "
            "     OR r.content LIKE '采购编号：%' OR r.content LIKE '项目标号：%')"
        )).fetchall()

        import re
        no_pattern = re.compile(r"^(?:项目编号|招标编号|采购编号|项目标号)[：:]\s*([A-Za-z0-9][A-Za-z0-9\-—/_]{1,30})")
        for pid, content in rows:
            m = no_pattern.match(content or "")
            if not m:
                continue
            no = m.group(1)
            conn.execute(text(
                "UPDATE bid_projects SET tender_ref_no = :no WHERE id = :id AND tender_ref_no IS NULL"
            ), {"no": no, "id": pid})
            filled += 1

        conn.commit()
        print(f"[migrate] backfilled {filled} projects from parsed requirements")
        print("[migrate] Migration completed successfully")

    engine.dispose()


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"[migrate] ERROR: {e}")
        sys.exit(1)
