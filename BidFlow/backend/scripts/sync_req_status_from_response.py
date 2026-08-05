"""一次性数据迁移：同步 Requirement.status 与已审核的 BidResponse.status。

背景（2026-08-05 修复前）：update_draft 审核路径只更新 BidResponse.status，
Requirement.status 一直停留在"待评审"，导致统计页"已通过 0/N"与列表"已生成"不一致。

规则：
- 需求存在 BidResponse 且最新一条 status == "approved" → Requirement.status = "已完成"
- 需求存在 BidResponse 且最新一条 status == "rejected" → Requirement.status = "待评审"
- 其余保持原样（未生成/待评审）

幂等：可重复执行，已同步的不再改动。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func  # noqa: E402

from app.db.session import _SyncSessionLocal as SessionLocal  # noqa: E402
from app.models.requirement import Requirement  # noqa: E402
from app.models.response import Response as BidResponse  # noqa: E402


def sync():
    db = SessionLocal()
    updated = 0
    try:
        # 每个需求的最新一条响应（按 id 降序取最新）
        latest_resp_ids = (
            db.query(
                BidResponse.requirement_id,
                func.max(BidResponse.id).label("max_id"),
            )
            .group_by(BidResponse.requirement_id)
            .subquery()
        )
        latest = (
            db.query(BidResponse)
            .join(latest_resp_ids, BidResponse.id == latest_resp_ids.c.max_id)
            .filter(BidResponse.status.in_(["approved", "rejected"]))
            .all()
        )
        for resp in latest:
            req = db.query(Requirement).filter(Requirement.id == resp.requirement_id).first()
            if not req:
                continue
            target = "已完成" if resp.status == "approved" else "待评审"
            if req.status != target:
                req.status = target
                db.add(req)
                updated += 1
        db.commit()
        print(f"[sync_req_status] 已同步 {updated} 条需求的 status（共扫描 {len(latest)} 条已审核响应）")
    finally:
        db.close()


if __name__ == "__main__":
    sync()
