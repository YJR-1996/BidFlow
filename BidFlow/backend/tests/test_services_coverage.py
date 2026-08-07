"""服务层覆盖率补充测试

覆盖：
- document_parser: txt 解析、空文件、不支持类型、fallback 路径
- retrieval_service: 空查询、mock 向量检索、低分过滤
- readiness_service: 就绪度三维计算、提交门槛
- file_storage: 保存/删除/非法路径/扩展名校验
"""
import builtins
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.requirement import Requirement
from app.models.response import Response as BidResponse
from app.models.compliance_issue import ComplianceIssue
from app.models.bid_project import BidProject
from app.models.user import User


# ---------------------------------------------------------------------------
# document_parser
# ---------------------------------------------------------------------------
class TestDocumentParser:
    def test_parse_txt_utf8(self, tmp_path):
        from app.services.document_parser import document_parser_service
        f = tmp_path / "test.txt"
        f.write_text("第一段。\n\n第二段。", encoding="utf-8")

        result = document_parser_service.parse(str(f), "txt")
        assert len(result) == 2
        assert result[0]["text"] == "第一段。"
        assert result[1]["text"] == "第二段。"
        assert result[0]["page"] == 1
        assert "段落" in result[0]["source_ref"]

    def test_parse_txt_gbk_fallback(self, tmp_path):
        """UTF-8 解码失败时回退 GBK"""
        from app.services.document_parser import document_parser_service
        f = tmp_path / "gbk.txt"
        f.write_bytes("中文内容".encode("gbk"))

        result = document_parser_service.parse(str(f), "txt")
        assert len(result) >= 1
        assert "中文内容" in result[0]["text"]

    def test_parse_txt_single_line(self, tmp_path):
        """无空行（无双换行）时整段保留为单个段落"""
        from app.services.document_parser import document_parser_service
        f = tmp_path / "line.txt"
        f.write_text("行1\n行2", encoding="utf-8")

        result = document_parser_service.parse(str(f), "txt")
        # 无 "\n\n" → split("\n\n") 产出一个非空整体，不触发单行回退
        assert len(result) == 1
        assert "行1" in result[0]["text"]

    def test_parse_empty_txt_raises(self, tmp_path):
        from app.services.document_parser import document_parser_service
        from app.core.exceptions import BusinessException
        f = tmp_path / "empty.txt"
        f.write_text("   \n\n  ", encoding="utf-8")

        with pytest.raises(BusinessException):
            document_parser_service.parse(str(f), "txt")

    def test_unsupported_file_type_raises(self, tmp_path):
        from app.services.document_parser import document_parser_service
        from app.core.exceptions import BusinessException
        with pytest.raises(BusinessException):
            document_parser_service.parse(str(tmp_path / "x.jpg"), "jpg")

    def test_parse_nonexistent_file_raises(self):
        from app.services.document_parser import document_parser_service
        from app.core.exceptions import BusinessException
        with pytest.raises(BusinessException):
            document_parser_service.parse("/nonexistent/path.txt", "txt")

    def test_parse_pdf_fallback_when_no_pypdf2(self, tmp_path):
        """未安装 PyPDF2 时走 fallback，返回占位文本"""
        from app.services.document_parser import document_parser_service
        f = tmp_path / "fake.pdf"
        f.write_bytes(b"%PDF-1.4 fake content")

        # 打补丁前先捕获真正的 __import__；注意模块内 __builtins__ 是 dict，
        # 不能写 __builtins__.__import__（会 AttributeError）
        orig_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "PyPDF2":
                raise ImportError("No module named 'PyPDF2'")
            return orig_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = document_parser_service._parse_pdf(str(f))
        assert len(result) == 1
        assert "PDF" in result[0]["text"]

    def test_parse_docx_fallback_when_no_docx(self, tmp_path):
        from app.services.document_parser import document_parser_service
        f = tmp_path / "fake.docx"
        f.write_bytes(b"fake docx")

        orig_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "docx":
                raise ImportError("No module named 'docx'")
            return orig_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = document_parser_service._parse_docx(str(f))
        assert len(result) == 1
        assert "DOCX" in result[0]["text"]


# ---------------------------------------------------------------------------
# retrieval_service
# ---------------------------------------------------------------------------
class TestRetrievalService:
    def test_empty_query_returns_empty(self):
        from app.services.retrieval_service import retrieval_service
        assert retrieval_service.search("", project_id=1) == []
        assert retrieval_service.search("   ", project_id=1) == []
        assert retrieval_service.search(None, project_id=1) == []

    def test_search_returns_formatted_results(self):
        from app.services.retrieval_service import retrieval_service
        mock_results = [
            {"text": "案例内容", "score": 0.9, "metadata": {"filename": "case.pdf", "source_ref": "p2", "scope": "company"}, "retrieval_type": "dense"},
            {"text": "资质文件", "score": 0.7, "metadata": {"filename": "qual.pdf", "source_ref": "p1", "scope": "company"}, "retrieval_type": "keyword"},
        ]
        # RAG 增强后 retrieval 优先走 hybrid_search，mock 目标随之更新
        with patch("app.services.vector_store.vector_store_service.hybrid_search", return_value=mock_results) as mock_hybrid, \
             patch("app.services.reranker.llm_reranker.rerank", side_effect=lambda q, c, k: c[:k]):
            results = retrieval_service.search("查询", project_id=1, top_k=5)

        mock_hybrid.assert_called_once()
        assert len(results) == 2
        assert results[0]["content"] == "案例内容"
        assert results[0]["score"] == 0.9
        assert results[0]["filename"] == "case.pdf"
        assert results[0]["source_ref"] == "p2"
        assert results[0]["material_type"] == "company_document"
        # RAG 增强可视化：检索模式标记透传
        assert results[0]["retrieval_type"] == "dense"
        assert results[1]["retrieval_type"] == "keyword"

    def test_search_filters_zero_score(self):
        """score=0 的结果应被过滤"""
        from app.services.retrieval_service import retrieval_service
        mock_results = [
            {"text": "有效", "score": 0.8, "metadata": {"filename": "a.pdf"}},
            {"text": "无效", "score": 0, "metadata": {"filename": "b.pdf"}},
        ]
        with patch("app.services.vector_store.vector_store_service.hybrid_search", return_value=mock_results) as mock_hybrid, \
             patch("app.services.reranker.llm_reranker.rerank", side_effect=lambda q, c, k: c[:k]):
            results = retrieval_service.search("查询", top_k=5)
        assert mock_hybrid.called
        assert len(results) == 1
        assert (results[0]["text"] if "text" in results[0] else results[0]["content"]) == "有效"

    def test_top_k_capped_to_max_results(self):
        """top_k 不超过 max_results (10)；hybrid_search 接收 top_k*3 候选"""
        from app.services.retrieval_service import retrieval_service
        with patch("app.services.vector_store.vector_store_service.hybrid_search", return_value=[]) as mock_hybrid:
            retrieval_service.search("查询", top_k=100)
            # top_k=100 → cap 10 → hybrid_search 取 10*3=30 候选
            assert mock_hybrid.call_args[0][2] == 30


# ---------------------------------------------------------------------------
# readiness_service
# ---------------------------------------------------------------------------
@pytest.fixture
def readiness_db():
    """内存 SQLite + 同步 session，用于 readiness_service 测试"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # 创建用户和项目
    user = User(id="u1", username="ruser", password_hash="x")
    db.add(user)
    project = BidProject(id=1, name="r项目", owner_id="u1")
    db.add(project)
    db.commit()
    yield db
    db.close()
    engine.dispose()


class TestReadinessService:
    def test_empty_project_returns_zero_rates(self, readiness_db):
        """无需求的项目：所有比率为 0，can_submit=False"""
        from app.services.readiness_service import readiness_service
        result = readiness_service_service_calculate(readiness_db, project_id=1)
        assert result.total == 0
        assert result.overall == 0.0
        assert result.can_submit is False

    def test_full_coverage_can_submit(self, readiness_db):
        """全部有响应+真实匹配+无高风险 → can_submit=True（质量维度基于比对 has_match）"""
        from app.services.readiness_service import readiness_service
        # 2 个需求，都有响应和来源
        for i in range(1, 3):
            req = Requirement(id=i, project_id=1, content=f"需求{i}", priority="P1", status="已完成")
            readiness_db.add(req)
            readiness_db.add(BidResponse(
                requirement_id=i, ai_content=f"响应{i}",
                source_refs=json.dumps([{"content": "x", "filename": "f.pdf"}], ensure_ascii=False),
                status="pending_review",
            ))
        # 构造一次比对分析 run，2 条 has_match=true 的 detail（质量维度的真实数据源）
        from app.models.match_analysis import MatchAnalysisRun, MatchAnalysisDetail
        run = MatchAnalysisRun(project_id=1, total=2, matched=2, unmatched=0, match_rate=100.0, triggered_by="u1")
        readiness_db.add(run)
        readiness_db.flush()
        for i in range(1, 3):
            readiness_db.add(MatchAnalysisDetail(
                run_id=run.id, requirement_id=i, content=f"需求{i}",
                has_match=True, match_count=1, match_score=0.9,
            ))
        readiness_db.commit()

        result = readiness_service.calculate(project_id=1, db=readiness_db)
        assert result.total == 2
        assert result.has_response == 2
        assert result.has_source == 2
        assert result.high_risk_pending == 0
        assert result.can_submit is True
        assert result.overall == 100.0

    def test_high_risk_blocks_submission(self, readiness_db):
        """存在高风险未处理合规问题 → can_submit=False"""
        from app.services.readiness_service import readiness_service
        req = Requirement(id=1, project_id=1, content="需求", priority="P0", status="已完成")
        readiness_db.add(req)
        readiness_db.add(BidResponse(
            requirement_id=1, ai_content="响应",
            source_refs=json.dumps([{"content": "x"}], ensure_ascii=False),
        ))
        readiness_db.add(ComplianceIssue(
            project_id=1, requirement_id=1, rule_code="P0_MISSING",
            level="高", status="未处理", description="x", suggestion="y",
        ))
        readiness_db.commit()

        result = readiness_service.calculate(project_id=1, db=readiness_db)
        assert result.high_risk_pending == 1
        assert result.can_submit is False

    def test_partial_response_lowers_base_rate(self, readiness_db):
        """部分需求有响应 → base_rate < 100"""
        from app.services.readiness_service import readiness_service
        for i in range(1, 5):
            readiness_db.add(Requirement(id=i, project_id=1, content=f"需求{i}", priority="P2"))
        # 仅 2 个有响应
        for i in range(1, 3):
            readiness_db.add(BidResponse(requirement_id=i, ai_content=f"响应{i}"))
        readiness_db.commit()

        result = readiness_service.calculate(project_id=1, db=readiness_db)
        assert result.total == 4
        assert result.has_response == 2
        assert result.base_rate == 50.0


def readiness_service_service_calculate(db, project_id):
    """辅助：直接调用 calculate"""
    from app.services.readiness_service import readiness_service
    return readiness_service.calculate(project_id=project_id, db=db)


# ---------------------------------------------------------------------------
# file_storage
# ---------------------------------------------------------------------------
class TestFileStorage:
    def test_get_safe_extension_valid(self):
        from app.services.file_storage import file_storage_service
        ext = file_storage_service._get_safe_extension("test.txt")
        assert ext == "txt"

    def test_get_safe_extension_invalid_raises(self):
        from app.services.file_storage import file_storage_service
        from app.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            file_storage_service._get_safe_extension("test.exe")

    def test_sanitize_filename_removes_path_traversal(self):
        from app.services.file_storage import file_storage_service
        assert file_storage_service._sanitize_filename("../etc/passwd") == "etcpasswd"
        assert file_storage_service._sanitize_filename("a\\b\\c") == "abc"

    def test_get_file_extension(self):
        from app.services.file_storage import file_storage_service
        assert file_storage_service.get_file_extension("a.PDF") == "pdf"
        assert file_storage_service.get_file_extension("noext") == ""

    def test_delete_nonexistent_file_returns_true(self, tmp_path):
        from app.services.file_storage import file_storage_service
        # 不存在的文件路径应返回 True（幂等）
        assert file_storage_service.delete_file(str(tmp_path / "nope.txt")) is True

    def test_delete_file_outside_base_dir_raises(self, tmp_path):
        """删除 base_dir 之外的文件应抛异常（路径穿越防护）"""
        from app.services.file_storage import file_storage_service
        from app.core.exceptions import BusinessException
        # /tmp 下的文件不在 UPLOAD_DIR 内
        f = tmp_path / "outside.txt"
        f.write_text("x")
        with pytest.raises(BusinessException):
            file_storage_service.delete_file(str(f))

    def test_save_and_delete_file_roundtrip(self, tmp_path):
        from app.services.file_storage import file_storage_service
        from app.core.config import settings
        # 将 base_dir 指向 tmp_path 以便测试
        original = file_storage_service.base_dir
        file_storage_service.base_dir = tmp_path
        try:
            upload = MagicMock()
            upload.filename = "roundtrip.txt"
            upload.file.read.return_value = b"hello"

            saved_path, original_name = file_storage_service.save_file(1, 1, upload)
            assert original_name == "roundtrip.txt"
            assert os.path.exists(saved_path)

            # 删除应成功
            assert file_storage_service.delete_file(saved_path) is True
            assert not os.path.exists(saved_path)
        finally:
            file_storage_service.base_dir = original

    def test_save_file_too_large_raises(self, tmp_path):
        from app.services.file_storage import file_storage_service
        from app.core.config import settings
        from app.core.exceptions import ValidationException
        original_dir = file_storage_service.base_dir
        original_max = settings.MAX_UPLOAD_SIZE
        file_storage_service.base_dir = tmp_path
        settings.MAX_UPLOAD_SIZE = 10  # 10 字节限制
        try:
            upload = MagicMock()
            upload.filename = "big.txt"
            upload.file.read.return_value = b"x" * 100
            with pytest.raises(ValidationException):
                file_storage_service.save_file(1, 1, upload)
        finally:
            file_storage_service.base_dir = original_dir
            settings.MAX_UPLOAD_SIZE = original_max
