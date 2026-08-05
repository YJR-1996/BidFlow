"""LLM 客户端、语义合规 Agent、企业资料服务单元测试

通过 mock openai 库与向量存储，覆盖：
- llm_client: 初始化校验、重试、JSON 解析、Embedding
- semantic_compliance_agent: 启用开关、置信度过滤、黑名单、等级封顶、降级
- company_material_service: 上传成功/失败、列表、删除
"""
import json
import sys
from unittest.mock import patch, MagicMock, mock_open

import pytest


# ---------------------------------------------------------------------------
# llm_client
# ---------------------------------------------------------------------------
class TestOpenAIChatClient:
    def test_no_api_key_raises(self):
        from app.services.llm_client import OpenAIChatClient, LlmServiceError
        client = OpenAIChatClient(api_key="")
        with pytest.raises(LlmServiceError, match="未配置"):
            client._ensure_client()

    def test_chat_success(self):
        from app.services.llm_client import OpenAIChatClient
        client = OpenAIChatClient(api_key="fake_key")
        # mock openai 库
        mock_openai_mod = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="LLM 回复"))]
        mock_openai_mod.OpenAI.return_value.chat.completions.create.return_value = mock_resp
        with patch.dict(sys.modules, {"openai": mock_openai_mod}):
            client._client = None  # 重置缓存
            result = client.chat([{"role": "user", "content": "hi"}])
        assert result == "LLM 回复"

    def test_chat_empty_content_raises(self):
        from app.services.llm_client import OpenAIChatClient, LlmServiceError
        client = OpenAIChatClient(api_key="fake_key")
        mock_openai_mod = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content=""))]
        mock_openai_mod.OpenAI.return_value.chat.completions.create.return_value = mock_resp
        with patch.dict(sys.modules, {"openai": mock_openai_mod}):
            client._client = None
            with pytest.raises(LlmServiceError, match="未返回文本"):
                client.chat([{"role": "user", "content": "hi"}])

    def test_chat_retries_then_fails(self):
        from app.services.llm_client import OpenAIChatClient, LlmServiceError
        client = OpenAIChatClient(api_key="fake_key", max_retries=2)
        mock_openai_mod = MagicMock()
        mock_openai_mod.OpenAI.return_value.chat.completions.create.side_effect = Exception("网络错误")
        with patch.dict(sys.modules, {"openai": mock_openai_mod}):
            client._client = None
            with pytest.raises(LlmServiceError, match="调用失败"):
                client.chat([{"role": "user", "content": "hi"}])
        # 应重试 max_retries+1 次
        assert mock_openai_mod.OpenAI.return_value.chat.completions.create.call_count == 3

    def test_chat_json_success(self):
        from app.services.llm_client import OpenAIChatClient
        client = OpenAIChatClient(api_key="fake_key")
        mock_openai_mod = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content='{"key": "value"}'))]
        mock_openai_mod.OpenAI.return_value.chat.completions.create.return_value = mock_resp
        with patch.dict(sys.modules, {"openai": mock_openai_mod}):
            client._client = None
            result = client.chat_json([{"role": "user", "content": "hi"}])
        assert result == {"key": "value"}

    def test_chat_json_decode_error_raises(self):
        from app.services.llm_client import OpenAIChatClient, LlmServiceError
        client = OpenAIChatClient(api_key="fake_key")
        mock_openai_mod = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="not json"))]
        mock_openai_mod.OpenAI.return_value.chat.completions.create.return_value = mock_resp
        with patch.dict(sys.modules, {"openai": mock_openai_mod}):
            client._client = None
            with pytest.raises(LlmServiceError, match="非 JSON"):
                client.chat_json([{"role": "user", "content": "hi"}])


class TestEmbeddingClient:
    def test_no_api_key_raises(self):
        from app.services.llm_client import EmbeddingClient, LlmServiceError
        client = EmbeddingClient(api_key="")
        with pytest.raises(LlmServiceError, match="未配置"):
            client._ensure_client()

    def test_embed_success(self):
        from app.services.llm_client import EmbeddingClient
        client = EmbeddingClient(api_key="fake_key")
        mock_openai_mod = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [MagicMock(embedding=[0.1, 0.2]), MagicMock(embedding=[0.3, 0.4])]
        mock_openai_mod.OpenAI.return_value.embeddings.create.return_value = mock_resp
        with patch.dict(sys.modules, {"openai": mock_openai_mod}):
            client._client = None
            result = client.embed(["text1", "text2"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]

    def test_embed_retries_then_fails(self):
        from app.services.llm_client import EmbeddingClient, LlmServiceError
        client = EmbeddingClient(api_key="fake_key", max_retries=1)
        mock_openai_mod = MagicMock()
        mock_openai_mod.OpenAI.return_value.embeddings.create.side_effect = Exception("net error")
        with patch.dict(sys.modules, {"openai": mock_openai_mod}):
            client._client = None
            with pytest.raises(LlmServiceError):
                client.embed(["text"])


# ---------------------------------------------------------------------------
# semantic_compliance_agent
# ---------------------------------------------------------------------------
class TestSemanticComplianceAgent:
    def test_no_response_content_returns_empty(self):
        from app.services.semantic_compliance_agent import SemanticComplianceAgent
        result = SemanticComplianceAgent().analyze(1, "需求", "", [])
        assert result == []

    def test_no_api_key_returns_empty(self):
        from app.services.semantic_compliance_agent import SemanticComplianceAgent
        with patch("app.services.semantic_compliance_agent.settings") as mock_settings:
            mock_settings.SEMANTIC_COMPLIANCE_ENABLED = True
            mock_settings.DASHSCOPE_API_KEY = ""
            result = SemanticComplianceAgent().analyze(1, "需求", "响应", [])
        assert result == []

    def test_disabled_returns_empty(self):
        from app.services.semantic_compliance_agent import SemanticComplianceAgent
        with patch("app.services.semantic_compliance_agent.settings") as mock_settings:
            mock_settings.SEMANTIC_COMPLIANCE_ENABLED = False
            mock_settings.DASHSCOPE_API_KEY = "key"
            result = SemanticComplianceAgent().analyze(1, "需求", "响应", [])
        assert result == []

    def test_analyze_returns_filtered_risks(self):
        from app.services.semantic_compliance_agent import SemanticComplianceAgent
        agent = SemanticComplianceAgent()
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "risks": [
                {"rule_code": "VAGUE_RESPONSE", "level": "medium", "description": "响应含糊",
                 "suggestion": "补充细节", "confidence": 0.8},
                # 置信度不足，应被过滤
                {"rule_code": "LOW_CONF", "level": "low", "description": "低置信",
                 "suggestion": "x", "confidence": 0.3},
            ]
        }
        with patch("app.services.semantic_compliance_agent.settings") as mock_settings, \
             patch("app.services.semantic_compliance_agent.OpenAIChatClient", return_value=mock_llm):
            mock_settings.SEMANTIC_COMPLIANCE_ENABLED = True
            mock_settings.DASHSCOPE_API_KEY = "key"
            mock_settings.LLM_MODEL_NAME = "model"
            result = agent.analyze(1, "需求", "响应内容", [])

        assert len(result) == 1
        assert result[0]["rule_code"] == "SEMANTIC_VAGUE_RESPONSE"
        assert result[0]["level"] == "medium"

    def test_high_level_capped_to_medium(self):
        """语义 Agent 最高只能报 medium，high 被降级"""
        from app.services.semantic_compliance_agent import SemanticComplianceAgent
        agent = SemanticComplianceAgent()
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "risks": [
                {"rule_code": "RISK", "level": "high", "description": "高风险",
                 "suggestion": "x", "confidence": 0.9},
            ]
        }
        with patch("app.services.semantic_compliance_agent.settings") as mock_settings, \
             patch("app.services.semantic_compliance_agent.OpenAIChatClient", return_value=mock_llm):
            mock_settings.SEMANTIC_COMPLIANCE_ENABLED = True
            mock_settings.DASHSCOPE_API_KEY = "key"
            mock_settings.LLM_MODEL_NAME = "model"
            result = agent.analyze(1, "需求", "响应", [])

        assert len(result) == 1
        assert result[0]["level"] == "medium"  # high 被封顶

    def test_suppress_keywords_filter(self):
        """命中黑名单关键词的风险应被丢弃"""
        from app.services.semantic_compliance_agent import SemanticComplianceAgent
        agent = SemanticComplianceAgent()
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "risks": [
                {"rule_code": "TIME", "level": "medium", "description": "近三年业绩案例完整",
                 "suggestion": "x", "confidence": 0.9},
                {"rule_code": "VALID", "level": "medium", "description": "技术方案不完整",
                 "suggestion": "x", "confidence": 0.9},
            ]
        }
        with patch("app.services.semantic_compliance_agent.settings") as mock_settings, \
             patch("app.services.semantic_compliance_agent.OpenAIChatClient", return_value=mock_llm):
            mock_settings.SEMANTIC_COMPLIANCE_ENABLED = True
            mock_settings.DASHSCOPE_API_KEY = "key"
            mock_settings.LLM_MODEL_NAME = "model"
            result = agent.analyze(1, "需求", "响应", [])

        # 命中黑名单且无否定词（"近三年业绩案例完整"）→ 被过滤；
        # "技术方案不完整"（无黑名单词）→ 保留
        assert len(result) == 1
        assert "技术方案" in result[0]["description"]

    def test_llm_failure_returns_empty(self):
        """LLM 异常时静默降级返回空列表"""
        from app.services.semantic_compliance_agent import SemanticComplianceAgent
        agent = SemanticComplianceAgent()
        mock_llm = MagicMock()
        mock_llm.chat_json.side_effect = Exception("LLM down")
        with patch("app.services.semantic_compliance_agent.settings") as mock_settings, \
             patch("app.services.semantic_compliance_agent.OpenAIChatClient", return_value=mock_llm):
            mock_settings.SEMANTIC_COMPLIANCE_ENABLED = True
            mock_settings.DASHSCOPE_API_KEY = "key"
            mock_settings.LLM_MODEL_NAME = "model"
            result = agent.analyze(1, "需求", "响应", [])
        assert result == []

    def test_should_suppress(self):
        from app.services.semantic_compliance_agent import SemanticComplianceAgent
        agent = SemanticComplianceAgent()
        # 命中黑名单关键词且无否定词 → 抑制（防 LLM 过度泛化为风险）
        assert agent._should_suppress("近三年业绩案例") is True
        assert agent._should_suppress("质保期不明确") is True
        # 否定/缺失词保护：描述含"不足/缺失"等 → 是真风险，不抑制
        assert agent._should_suppress("近三年业绩不足") is False
        assert agent._should_suppress("技术方案缺失") is False
        assert agent._should_suppress("") is False


# ---------------------------------------------------------------------------
# company_material_service
# ---------------------------------------------------------------------------
class TestCompanyMaterialService:
    def test_upload_and_process_success(self, tmp_path):
        from app.services.company_material_service import CompanyMaterialService
        from app.core.config import settings
        svc = CompanyMaterialService()
        svc.base_dir = tmp_path

        db = MagicMock()
        user = MagicMock()
        user.id = "u1"
        file = MagicMock()
        file.filename = "test.txt"
        file.file.read.return_value = "文件内容".encode("utf-8")

        # mock 解析、切块、向量存储
        with patch("app.services.document_parser.document_parser_service.parse", return_value=[{"text": "段落"}]), \
             patch("app.services.text_chunker.text_chunker_service.chunk", return_value=[{"text": "段落", "chunk_id": 0}]), \
             patch("app.services.vector_store.vector_store_service.upsert"):
            doc = svc.upload_and_process(db=db, user=user, file=file, scope="company")

        assert doc.status == "success"
        db.add.assert_called()
        db.commit.assert_called()

    def test_upload_parse_failure_marks_failed(self, tmp_path):
        from app.services.company_material_service import CompanyMaterialService
        from app.core.exceptions import BusinessException
        svc = CompanyMaterialService()
        svc.base_dir = tmp_path

        db = MagicMock()
        user = MagicMock()
        user.id = "u1"
        file = MagicMock()
        file.filename = "bad.txt"
        file.file.read.return_value = "内容".encode("utf-8")

        with patch("app.services.document_parser.document_parser_service.parse", side_effect=Exception("解析失败")):
            with pytest.raises(BusinessException):
                svc.upload_and_process(db=db, user=user, file=file)

    def test_upload_empty_filename_raises(self, tmp_path):
        from app.services.company_material_service import CompanyMaterialService
        from app.core.exceptions import ValidationException
        svc = CompanyMaterialService()
        svc.base_dir = tmp_path

        file = MagicMock()
        file.filename = ""
        with pytest.raises(ValidationException):
            svc.upload_and_process(db=MagicMock(), user=MagicMock(), file=file)

    def test_upload_invalid_extension_raises(self, tmp_path):
        from app.services.company_material_service import CompanyMaterialService
        from app.core.exceptions import ValidationException
        svc = CompanyMaterialService()
        svc.base_dir = tmp_path

        file = MagicMock()
        file.filename = "virus.exe"
        with pytest.raises(ValidationException):
            svc.upload_and_process(db=MagicMock(), user=MagicMock(), file=file)

    def test_list_by_owner(self):
        from app.services.company_material_service import CompanyMaterialService
        svc = CompanyMaterialService()
        db = MagicMock()
        user = MagicMock()
        user.id = "u1"
        # mock query chain
        db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        result = svc.list_by_owner(db=db, user=user)
        assert result == []

    def test_delete_removes_file_and_record(self, tmp_path):
        from app.services.company_material_service import CompanyMaterialService
        svc = CompanyMaterialService()
        db = MagicMock()
        # 创建临时文件模拟资料文件
        f = tmp_path / "doc.txt"
        f.write_text("内容")
        doc = MagicMock()
        doc.file_path = str(f)
        doc.id = 1

        with patch("app.services.vector_store.vector_store_service.delete_by_doc_id"):
            svc.delete(db=db, doc=doc)

        db.delete.assert_called_with(doc)
        db.commit.assert_called()
        assert not f.exists()  # 文件应被删除

    def test_get_safe_extension_valid(self):
        from app.services.company_material_service import CompanyMaterialService
        svc = CompanyMaterialService()
        assert svc._get_safe_extension("a.txt") == "txt"
