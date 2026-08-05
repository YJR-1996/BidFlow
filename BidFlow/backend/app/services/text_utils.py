"""通用文本/序列化工具函数"""

import json
from typing import Any, List


def parse_source_refs(raw: Any) -> List:
    """解析 BidResponse.source_refs（Text 列，存 json.dumps 产物）。

    兼容格式：
    - json.dumps 产物（双引号 JSON）
    - 已是 list（内存传递）
    - 空值 / 非法 → 返回 []

    L1：原三处重复实现（compliance.py / chat_service.py / readiness_service.py）统一收口。
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        d = json.loads(raw)
        return d if isinstance(d, list) else []
    except Exception:
        return []
