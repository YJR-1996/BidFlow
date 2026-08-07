"""清理重复响应数据（幂等）

背景：旧版 generate_draft 每次生成都新建响应，同一需求可能残留多条响应记录。
全系统（前端响应清单/就绪度/比对/合规快照修复后）均按「最新一条（id 降序）」读取，
旧响应不再被任何逻辑使用，属于脏数据。

策略：
- 每个 requirement_id 保留 id 最大的一条（与全系统读取口径一致）
- 其余旧响应先备份为 CSV（backend/data/backup/responses_dedupe_<ts>.csv）再删除
- 事务提交前打印统计，删除后自检：不应再存在重复

用法：python scripts/cleanup_duplicate_responses.py [--dry-run]
"""
import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql

from app.core.config import settings

CSV_HEADERS = ["id", "requirement_id", "ai_content", "edited_content", "source_refs", "status"]


def get_conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE,
        charset="utf8mb4",
        connect_timeout=10,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只统计与备份，不删除")
    args = parser.parse_args()

    conn = get_conn()
    cur = conn.cursor()

    # 1) 找出存在重复响应的需求
    cur.execute("""
        SELECT requirement_id, COUNT(*) AS cnt, MAX(id) AS keep_id
        FROM responses
        GROUP BY requirement_id
        HAVING COUNT(*) > 1
    """)
    dups = cur.fetchall()
    print(f"发现 {len(dups)} 个需求存在重复响应")

    if not dups:
        print("无需清理")
        conn.close()
        return

    # 2) 收集待删除的旧响应（id != keep_id）
    to_delete = []
    for req_id, cnt, keep_id in dups:
        cur.execute(
            "SELECT id, requirement_id, ai_content, edited_content, source_refs, status "
            "FROM responses WHERE requirement_id = %s AND id != %s",
            (req_id, keep_id),
        )
        rows = cur.fetchall()
        to_delete.extend(rows)

    total = len(to_delete)
    print(f"待删除旧响应：{total} 条（保留最新 {len(dups)} 条）")
    for req_id, cnt, keep_id in dups:
        print(f"  requirement_id={req_id}: {cnt} 条 → 保留 id={keep_id}，删 {cnt - 1} 条")

    # 3) 备份到 CSV
    backup_dir = settings.DATA_DIR / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"responses_dedupe_{ts}.csv"
    with open(backup_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        writer.writerows(to_delete)
    print(f"已备份到: {backup_path}")

    if args.dry_run:
        print("[dry-run] 未执行删除")
        conn.close()
        return

    # 4) 删除旧响应
    for row in to_delete:
        cur.execute("DELETE FROM responses WHERE id = %s", (row[0],))
    conn.commit()
    print(f"已删除 {total} 条旧响应")

    # 5) 自检：不应再存在重复
    cur.execute("""
        SELECT requirement_id, COUNT(*) AS cnt
        FROM responses
        GROUP BY requirement_id
        HAVING COUNT(*) > 1
    """)
    remain = cur.fetchall()
    if remain:
        print(f"[WARN] 仍存在重复响应: {remain}")
    else:
        print("自检通过：已无重复响应")

    conn.close()


if __name__ == "__main__":
    main()
