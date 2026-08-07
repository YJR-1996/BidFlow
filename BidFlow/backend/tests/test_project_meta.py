"""方案乙：项目元数据分流测试（正则快筛 + LLM 兜底）

覆盖：
- 强信号正则剥离：项目编号 / 预算（万元换算）/ 投标截止时间
- 剥离后不生成需求，写回 BidProject 字段
- 交付周期等真实条款不被误剥，仍生成需求
- 弱命中（采购人/招标人）走 LLM 兜底：置信度≥0.8 剥离 / 低置信度保留
- LLM 失败 → 弱命中行保持原样
- 无 LLM（无 API Key）→ 弱命中行保持原样
- 已有值不被覆盖（只填空值）
"""
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.tender_document import TenderDocument
from app.models.requirement import Requirement
from app.services.tender_requirement_extractor import TenderRequirementExtractorService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(User(id="u1", username="meta_user", password_hash="x"))
    s.add(BidProject(id=1, name="农药采购项目", owner_id="u1"))
    s.add(TenderDocument(id=1, project_id=1, filename="t.pdf", file_path="/tmp/t.pdf", file_type="txt"))
    s.commit()
    yield s
    s.close()
    engine.dispose()


def _blocks(*texts):
    """构造 _group_text 风格的块"""
    return [
        {"text": t, "source_ref": f"段落 {i+1}", "section": ""}
        for i, t in enumerate(texts)
    ]


def _extract(db, blocks):
    svc = TenderRequirementExtractorService()
    return svc.extract(db, project_id=1, tender_document_id=1, parsed_paragraphs=blocks)


class TestStrongPatterns:
    def test_project_ref_no_stripped(self, db):
        """项目编号强命中 → 不生成需求（写入项目字段），元数据不进需求表"""
        reqs = _extract(db, _blocks("项目编号：ZB2026-NY-015"))
        proj = db.query(BidProject).filter(BidProject.id == 1).first()
        assert proj.tender_ref_no == "ZB2026-NY-015"
        # 整块都是元数据 → 无真需求；即使触发 demo 兜底也不含编号内容
        assert all("项目编号" not in r.content for r in reqs)

    def test_budget_wan_conversion(self, db):
        """预算「360万元」→ budget=360（单位万）"""
        _extract(db, _blocks("预算金额：360万元"))
        proj = db.query(BidProject).filter(BidProject.id == 1).first()
        assert proj.budget == 360

    def test_budget_without_unit(self, db):
        """预算「500」→ 视为万元，budget=500"""
        _extract(db, _blocks("预算金额：500"))
        proj = db.query(BidProject).filter(BidProject.id == 1).first()
        assert proj.budget == 500

    def test_deadline_parsed(self, db):
        """投标截止时间 → deadline 解析为 datetime"""
        _extract(db, _blocks("投标截止：2026-09-15 10:00（北京时间）"))
        proj = db.query(BidProject).filter(BidProject.id == 1).first()
        assert proj.deadline is not None
        assert proj.deadline.year == 2026 and proj.deadline.month == 9

    def test_delivery_term_not_stripped(self, db):
        """交付周期是真实商务条款 → 不剥离，生成需求"""
        reqs = _extract(db, _blocks("交付周期：合同签订后15日历天内完成配送到指定乡镇"))
        assert len(reqs) >= 1
        assert "交付周期" in reqs[0].content

    def test_mixed_block_only_meta_stripped(self, db):
        """混合块：只剥元数据行，保留真实条款行"""
        reqs = _extract(db, _blocks(
            "项目编号：ZB2026-NY-015\n采购人：XX县农业农村局\n预算金额：360万元\n"
            "交付周期：合同签订后15日历天内完成"
        ))
        proj = db.query(BidProject).filter(BidProject.id == 1).first()
        assert proj.tender_ref_no == "ZB2026-NY-015"
        # 采购人是弱命中（LLM 不可用）→ 保留，但仍生成需求的是交付周期
        assert len(reqs) >= 1
        assert all("交付周期" in r.content for r in reqs)


class TestWeakLinesLLM:
    def test_weak_line_kept_without_llm(self, db):
        """无 LLM（API Key 为空）→ 弱命中行（采购人）保持原样，不剥离"""
        with patch("app.core.config.settings.DASHSCOPE_API_KEY", ""):
            reqs = _extract(db, _blocks("采购人：XX县农业农村局"))
        proj = db.query(BidProject).filter(BidProject.id == 1).first()
        assert proj.tenderer is None  # 未写回
        assert len(reqs) >= 1  # 作为需求保留（原逻辑）

    def test_weak_line_llm_high_confidence(self, db):
        """LLM 判采购人为元数据且置信度高 → 剥离写回"""
        fake_data = {"results": [{"index": 0, "is_meta": True, "field": "tenderer",
                                  "value": "XX县农业农村局", "confidence": 0.95}]}
        with patch("app.core.config.settings.DASHSCOPE_API_KEY", "sk-test"):
            with patch("app.services.llm_client.OpenAIChatClient") as mock_cls:
                client = MagicMock()
                client.chat_json.return_value = fake_data
                mock_cls.return_value = client
                reqs = _extract(db, _blocks("采购人：XX县农业农村局"))
        proj = db.query(BidProject).filter(BidProject.id == 1).first()
        assert proj.tenderer == "XX县农业农村局"
        # 剥离成功 → 采购人内容不进需求表（即使 demo 兜底也不含"采购人"）
        assert all("采购人" not in r.content for r in reqs)

    def test_weak_line_llm_low_confidence_kept(self, db):
        """LLM 置信度 < 0.8 → 不剥离，保留为需求"""
        fake_data = {"results": [{"index": 0, "is_meta": True, "field": "tenderer",
                                  "value": "XX县农业农村局", "confidence": 0.5}]}
        with patch("app.core.config.settings.DASHSCOPE_API_KEY", "sk-test"):
            with patch("app.services.llm_client.OpenAIChatClient") as mock_cls:
                client = MagicMock()
                client.chat_json.return_value = fake_data
                mock_cls.return_value = client
                reqs = _extract(db, _blocks("采购人：XX县农业农村局"))
        proj = db.query(BidProject).filter(BidProject.id == 1).first()
        assert proj.tenderer is None
        assert len(reqs) >= 1

    def test_weak_line_llm_failure_kept(self, db):
        """LLM 调用异常 → 弱命中行保持原样"""
        with patch("app.core.config.settings.DASHSCOPE_API_KEY", "sk-test"):
            with patch("app.services.llm_client.OpenAIChatClient") as mock_cls:
                client = MagicMock()
                client.chat_json.side_effect = RuntimeError("LLM down")
                mock_cls.return_value = client
                reqs = _extract(db, _blocks("采购人：XX县农业农村局"))
        proj = db.query(BidProject).filter(BidProject.id == 1).first()
        assert proj.tenderer is None
        assert len(reqs) >= 1


class TestWriteBack:
    def test_existing_value_not_overwritten(self, db):
        """项目已有 budget 时，解析结果不覆盖"""
        proj = db.query(BidProject).filter(BidProject.id == 1).first()
        proj.budget = 999
        db.commit()
        _extract(db, _blocks("预算金额：360万元"))
        proj = db.query(BidProject).filter(BidProject.id == 1).first()
        assert proj.budget == 999  # 保持用户输入

    def test_normal_requirement_unaffected(self, db):
        """普通资格需求不受元数据分流影响"""
        reqs = _extract(db, _blocks("投标人必须具有独立法人资格，持有有效的营业执照"))
        assert len(reqs) == 1
        assert reqs[0].priority == "P0"
