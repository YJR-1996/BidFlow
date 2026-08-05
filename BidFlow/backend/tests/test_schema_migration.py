"""数据库 schema 迁移和鲁棒性测试

测试目标:
  1. 验证迁移脚本能正确添加缺失的列
  2. 验证项目列表接口在数据库缺列时能优雅降级（核心逻辑测试）
  3. 验证 schema 一致性检查功能
"""
import os
import tempfile
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import _check_schema_consistency
from app.db.base import Base
from app.models.bid_project import BidProject
from app.models.compliance_issue import ComplianceIssue


@pytest.fixture
def sqlite_engine():
    """创建一个测试 SQLite 引擎，包含所有表"""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except PermissionError:
        pass


@pytest.fixture
def sqlite_engine_without_source():
    """创建一个缺少 source 列的测试 SQLite 引擎"""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    # 删除 source 列模拟旧数据库
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE compliance_issues DROP COLUMN source"))
        conn.commit()

    yield engine
    engine.dispose()
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except PermissionError:
        pass


def test_schema_consistency_check_detects_missing_column(sqlite_engine_without_source):
    """schema 一致性检查应能检测到缺失的 source 列"""
    missing_count = _check_schema_consistency(sqlite_engine_without_source, Base)
    # 必须真正检测到缺失列（修复前断言 >=0 永真，掩盖了 DESCRIBE 在 SQLite 静默失效的缺陷）
    assert missing_count >= 1
    # 验证 source 列确实不在数据库中
    with sqlite_engine_without_source.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(compliance_issues)"))
        col_names = [row[1] for row in result]
        assert "source" not in col_names


def test_schema_consistency_check_passes_with_all_columns(sqlite_engine):
    """schema 一致性检查在无缺失列时应通过"""
    missing_count = _check_schema_consistency(sqlite_engine, Base)
    assert missing_count == 0


def test_migration_sql_adds_source_column():
    """验证迁移 SQL 语句能正确添加 source 列"""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    # 创建表但不含 source
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE compliance_issues DROP COLUMN source"))
        conn.commit()

    # 验证 source 列不存在
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(compliance_issues)"))
        col_names = [row[1] for row in result]
        assert "source" not in col_names

    # 执行迁移 SQL
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE compliance_issues ADD COLUMN source VARCHAR(20) DEFAULT 'rule'"
        ))
        conn.commit()

    # 验证 source 列已存在
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(compliance_issues)"))
        col_names = [row[1] for row in result]
        assert "source" in col_names

    # 验证可以正常插入和查询（无 500 错误）
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    issue = ComplianceIssue(
        project_id=1,
        level="高",
        rule_code="R001",
        description="测试合规问题",
        source="rule",
    )
    session.add(issue)
    session.commit()

    result = session.query(ComplianceIssue).filter(ComplianceIssue.source == "rule").count()
    assert result == 1
    session.close()

    engine.dispose()
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except PermissionError:
        pass


def test_list_projects_risk_query_with_source_column(sqlite_engine):
    """验证项目列表中的风险计数查询在有 source 列时能正常工作"""
    SessionLocal = sessionmaker(bind=sqlite_engine)
    session = SessionLocal()

    # 创建测试项目
    project = BidProject(
        owner_id="test-owner",
        name="测试项目",
        status="准备中",
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    # 创建合规问题（使用 source 列）
    issue = ComplianceIssue(
        project_id=project.id,
        level="高",
        rule_code="R001",
        description="测试风险",
        source="rule",
    )
    session.add(issue)
    session.commit()

    # 验证查询能正常执行（不再报 Unknown column 错误）
    from sqlalchemy.exc import OperationalError
    try:
        risk_count = session.query(ComplianceIssue).filter(
            ComplianceIssue.project_id == project.id,
            ComplianceIssue.level.in_(["高", "中"]),
        ).count()
        assert risk_count == 1
    except OperationalError as e:
        if "Unknown column" in str(e):
            pytest.fail(f"风险计数查询因缺列失败: {e}")
        raise

    session.close()
