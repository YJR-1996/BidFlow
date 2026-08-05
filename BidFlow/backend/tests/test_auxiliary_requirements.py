"""测试辅助需求生成功能

运行: pytest tests/test_auxiliary_requirements.py -v
"""
import os
import sys
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.auxiliary_requirement_service import AuxiliaryRequirementService
from app.services.llm_client import LlmServiceError


def _make_req(id: int, content: str, category: str = "资格",
              priority: str = "P0", source: str = "parsed", tpl_id: int = None) -> MagicMock:
    """创建模拟 Requirement"""
    req = MagicMock()
    req.id = id
    req.content = content
    req.category = category
    req.priority = priority
    req.source = source
    req.tender_document_id = tpl_id
    return req


def _mock_query_chain(db, return_values_list):
    """设置 db.query() 链式调用的返回值（按顺序）"""
    mocks = []
    for val in return_values_list:
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.all.return_value = val
        mocks.append(q)
    db.query.side_effect = mocks


# ---------------------------------------------------------------------------
# Test防重复
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_skip_when_ai_aux_exists(self):
        svc = AuxiliaryRequirementService()
        existing = [_make_req(10, "已有辅助项", source="ai_aux")]

        db = MagicMock()
        _mock_query_chain(db, [existing])

        result = svc._check_existing_ai_aux(db, 1, None)
        assert result is not None
        assert len(result) == 1
        assert result[0].content == "已有辅助项"

    def test_return_none_when_no_ai_aux(self):
        svc = AuxiliaryRequirementService()
        db = MagicMock()
        _mock_query_chain(db, [[]])

        result = svc._check_existing_ai_aux(db, 1, None)
        assert result is None


# ---------------------------------------------------------------------------
# TestLLMResultParsing
# ---------------------------------------------------------------------------

class TestLLMResultParsing:
    def test_normal_items(self):
        svc = AuxiliaryRequirementService()
        raw = {
            "requirements": [
                {"content": "需要营业执照", "category": "资格", "priority": "P0", "risk_level": "低"},
                {"content": "需要 ISO9001", "category": "资格", "priority": "P1"},
            ]
        }
        result = svc._parse_llm_result(raw, max_items=10)
        assert len(result) == 2
        assert result[0]["content"] == "需要营业执照"
        assert result[0]["category"] == "资格"
        assert result[0]["priority"] == "P0"
        assert result[0]["source"] == "ai_aux"

    def test_max_items_limit(self):
        svc = AuxiliaryRequirementService()
        raw = {"requirements": [{"content": f"需求 {i}", "category": "资格", "priority": "P2"} for i in range(20)]}
        result = svc._parse_llm_result(raw, max_items=5)
        assert len(result) == 5

    def test_invalid_category_falls_back(self):
        svc = AuxiliaryRequirementService()
        raw = {"requirements": [{"content": "test", "category": "无效分类", "priority": "P2"}]}
        result = svc._parse_llm_result(raw, max_items=10)
        assert result[0]["category"] == "其他"

    def test_invalid_priority_falls_back(self):
        svc = AuxiliaryRequirementService()
        raw = {"requirements": [{"content": "test", "category": "资格", "priority": "P9"}]}
        result = svc._parse_llm_result(raw, max_items=10)
        assert result[0]["priority"] == "P2"

    def test_empty_response(self):
        svc = AuxiliaryRequirementService()
        result = svc._parse_llm_result({"requirements": []}, max_items=10)
        assert result == []

    def test_invalid_json(self):
        svc = AuxiliaryRequirementService()
        result = svc._parse_llm_result({"error": "bad"}, max_items=10)
        assert result == []

    def test_content_missing_skipped(self):
        svc = AuxiliaryRequirementService()
        raw = {
            "requirements": [
                {"content": "", "category": "资格", "priority": "P0"},
                {"content": "有效需求", "category": "资格", "priority": "P0"},
            ]
        }
        result = svc._parse_llm_result(raw, max_items=10)
        assert len(result) == 1
        assert result[0]["content"] == "有效需求"


# ---------------------------------------------------------------------------
# TestDegradation - 降级测试
# ---------------------------------------------------------------------------

class TestDegradation:
    def test_llm_error_returns_empty_list(self):
        svc = AuxiliaryRequirementService()
        parsed = [_make_req(1, "已解析需求", source="parsed")]

        mock_chat = MagicMock()
        mock_chat.chat_json.side_effect = LlmServiceError("LLM 宕机")

        db = MagicMock()
        _mock_query_chain(db, [[], parsed])

        with patch.object(svc, '_get_chat_client', return_value=mock_chat):
            result = svc.generate(db, project_id=1)
            assert result == []

    def test_no_parsed_reqs_returns_empty(self):
        svc = AuxiliaryRequirementService()
        db = MagicMock()
        _mock_query_chain(db, [[], []])

        result = svc.generate(db, project_id=1)
        assert result == []

    def test_no_api_key_returns_empty(self):
        svc = AuxiliaryRequirementService()
        parsed = [_make_req(1, "已解析需求", source="parsed")]

        db = MagicMock()
        _mock_query_chain(db, [[], parsed])

        with patch.object(svc, '_get_chat_client', return_value=None):
            result = svc.generate(db, project_id=1)
            assert result == []


# ---------------------------------------------------------------------------
# TestIntegration
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_generation_flow(self):
        svc = AuxiliaryRequirementService()
        parsed = [
            _make_req(1, "投标人须具备建筑工程施工总承包资质", "资格", "P0", "parsed"),
            _make_req(2, "近三年无重大违法记录", "资格", "P0", "parsed"),
        ]

        mock_chat = MagicMock()
        mock_chat.chat_json.return_value = {
            "requirements": [
                {"content": "需提供有效的营业执照副本", "category": "资格", "priority": "P0"},
                {"content": "需提供近三年财务审计报告", "category": "商务", "priority": "P1"},
            ]
        }

        created_items = [
            _make_req(100, "需提供有效的营业执照副本", "资格", "P0", "ai_aux"),
            _make_req(101, "需提供近三年财务审计报告", "商务", "P1", "ai_aux"),
        ]

        db = MagicMock()
        _mock_query_chain(db, [[], parsed])

        written_items = []

        def capture_write(*args, **kwargs):
            # patch.object 已绑定 self，args 为 (db, project_id, tender_document_id, items)
            written_items.extend(args[3])
            return created_items

        with patch.object(svc, '_write_aux_requirements', side_effect=capture_write):
            with patch.object(svc, '_get_chat_client', return_value=mock_chat):
                result = svc.generate(db, project_id=1)
                assert len(result) == 2
                assert len(written_items) == 2
                for item in written_items:
                    assert item["source"] == "ai_aux"

    def test_skip_on_duplicate_call(self):
        svc = AuxiliaryRequirementService()
        existing = [_make_req(10, "已有辅助项", "资格", "P0", "ai_aux")]

        db = MagicMock()
        _mock_query_chain(db, [existing])

        result = svc.generate(db, project_id=1)
        assert len(result) == 1
        assert result[0].content == "已有辅助项"

    def test_llm_returns_empty_list(self):
        svc = AuxiliaryRequirementService()
        parsed = [_make_req(1, "已解析需求", source="parsed")]

        mock_chat = MagicMock()
        mock_chat.chat_json.return_value = {"requirements": []}

        db = MagicMock()
        _mock_query_chain(db, [[], parsed])

        with patch.object(svc, '_get_chat_client', return_value=mock_chat):
            result = svc.generate(db, project_id=1)
            assert result == []


# ---------------------------------------------------------------------------
# TestPromptTemplate
# ---------------------------------------------------------------------------

class TestPromptTemplate:
    def test_build_messages_structure(self):
        from app.services.prompt_templates import build_aux_requirement_messages
        reqs = [
            {"content": "需求A", "category": "资格", "priority": "P0"},
            {"content": "需求B", "category": "技术", "priority": "P1"},
        ]
        messages = build_aux_requirement_messages(reqs, max_items=5)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "严格约束" in messages[0]["content"]
        assert "JSON" in messages[0]["content"]
        assert "需求A" in messages[1]["content"]
        assert "5" in messages[1]["content"]

    def test_build_messages_max_items(self):
        from app.services.prompt_templates import build_aux_requirement_messages
        messages = build_aux_requirement_messages([], max_items=3)
        assert "3" in messages[1]["content"]

    def test_input_requirements_format(self):
        from app.services.prompt_templates import build_aux_requirement_messages
        reqs = [{"content": "资质要求", "category": "资格", "priority": "P0"}]
        messages = build_aux_requirement_messages(reqs, max_items=3)
        user_content = messages[1]["content"]
        assert "[P0]" in user_content
        assert "[资格]" in user_content
        assert "资质要求" in user_content