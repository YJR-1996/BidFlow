"""项目编号生成服务测试

覆盖：
- 编号格式：BF-{年}-U{序号}-{流水:03d}
- 用户隔离：不同用户各自从 001 数起
- 当年流水递增：同一用户同年内项目 001、002…
- 跨年重置：不同年份流水重新从 001 数
- 用户序号：按注册时间排名，跨用户不重号
- 创建接口：真实走 generate + 落库
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.user import User
from app.models.bid_project import BidProject
from app.services.project_number_service import generate_tender_no


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()

    u1 = User(id="u1", username="user_a", password_hash="x", created_at=datetime(2026, 1, 1))
    u2 = User(id="u2", username="user_b", password_hash="x", created_at=datetime(2026, 2, 1))
    u3 = User(id="u3", username="user_c", password_hash="x", created_at=datetime(2026, 3, 1))
    s.add_all([u1, u2, u3])
    s.commit()
    yield s
    s.close()
    engine.dispose()


def _add_project(s, owner_id, created_at, tender_no=None):
    p = BidProject(owner_id=owner_id, name="项目", created_at=created_at, tender_no=tender_no)
    s.add(p)
    s.commit()
    return p


class TestNumberFormat:
    def test_format(self, db):
        """编号格式：BF-{年}-U{序号}-{流水:03d}"""
        no = generate_tender_no(db, "u1", created_at=datetime(2026, 5, 1))
        assert no == "BF-2026-U1-001"

    def test_user_seq_by_registration_order(self, db):
        """用户序号按注册时间排名：u3 是第 3 个注册 → U3"""
        no = generate_tender_no(db, "u3", created_at=datetime(2026, 5, 1))
        assert no == "BF-2026-U3-001"


class TestUserIsolation:
    def test_each_user_starts_at_001(self, db):
        """不同用户各自从 001 数起"""
        n1 = generate_tender_no(db, "u1", created_at=datetime(2026, 5, 1))
        n2 = generate_tender_no(db, "u2", created_at=datetime(2026, 5, 1))
        assert n1 == "BF-2026-U1-001"
        assert n2 == "BF-2026-U2-001"  # 同一年各自第一个项目
        assert n1 != n2  # 用户序号段不同 → 全局不重号


class TestYearSeq:
    def test_increments_within_year(self, db):
        """同一用户同年内项目流水递增 001、002"""
        _add_project(db, "u1", datetime(2026, 1, 10))
        n = generate_tender_no(db, "u1", created_at=datetime(2026, 5, 1))
        assert n == "BF-2026-U1-002"

    def test_resets_across_years(self, db):
        """跨年流水重新从 001 数"""
        _add_project(db, "u1", datetime(2025, 12, 31))  # 2025 年项目
        n = generate_tender_no(db, "u1", created_at=datetime(2026, 5, 1))
        assert n == "BF-2026-U1-001"  # 2026 年重新从 001 数

    def test_seq_counts_other_users_ignored(self, db):
        """流水只数自己的项目，其他用户的项目不影响"""
        _add_project(db, "u2", datetime(2026, 1, 10))  # u2 的项目
        n = generate_tender_no(db, "u1", created_at=datetime(2026, 5, 1))
        assert n == "BF-2026-U1-001"


class TestCreateProjectRoute:
    def test_create_project_sets_tender_no(self, client, auth_headers):
        """创建项目后 tender_no 自动生成并落库"""
        resp = client.post(
            "/api/projects",
            json={"name": "测试项目"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["tender_no"]
        assert data["tender_no"].startswith("BF-")
        assert data["tender_no"].endswith("-001")
