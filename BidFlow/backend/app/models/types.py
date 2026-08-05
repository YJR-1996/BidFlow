"""UTC 时间戳类型 - 解决服务端 datetime 无时区序列化导致的时区偏移问题。

背景：模型原用 Column(DateTime, default=datetime.utcnow) 存 naive UTC，
      Pydantic 序列化输出无 tz 后缀（如 2026-08-05T11:45:38），
      前端 new Date() 按本地时区（UTC+8）解析 → 偏差 8 小时。

方案：TypeDecorator 包装 DateTime——
      - 写入：aware datetime 转成 UTC naive 存储（MySQL DATETIME 无时区）
      - 读取：naive datetime 附加 timezone.utc → Pydantic 输出带 +00:00 → 前端正确解析
"""

from datetime import datetime, timezone
from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """存 naive UTC、读回 aware UTC 的 DateTime 类型（自动附加时区信息）。"""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        # 写入：aware → 转成 UTC naive；naive 视为 UTC 原样
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        # 读取：naive（MySQL DATETIME 无时区）→ 附加 UTC，输出带 +00:00
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
