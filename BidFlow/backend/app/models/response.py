"""成员 D 的响应草稿领域模型；后续由 A 接入 SQLAlchemy 表。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


VALID_RESPONSE_STATUSES = {"draft", "pending_review", "completed", "needs_manual"}


@dataclass
class BidResponse:
    requirement_id: int
    ai_content: str
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending_review"
    edited_content: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def content(self) -> str:
        return self.edited_content if self.edited_content is not None else self.ai_content

    def update_status(self, status: str) -> None:
        if status not in VALID_RESPONSE_STATUSES:
            raise ValueError("不支持的响应状态。")
        if status == "completed" and not self.source_refs:
            raise ValueError("没有来源的草稿不能标记为已完成。")
        self.status = status
        self.updated_at = datetime.now(timezone.utc)
