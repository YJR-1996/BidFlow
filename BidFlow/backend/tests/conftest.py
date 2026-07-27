import os
import sys
from pathlib import Path

import pytest

# 将 backend 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


@pytest.fixture
def event_loop():
    """为 pytest-asyncio 提供事件循环"""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
