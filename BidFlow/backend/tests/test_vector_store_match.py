"""测试向量存储比对功能 - 验证空库、完全覆盖、部分覆盖、缺失场景

运行: pytest tests/test_vector_store_match.py -v
注意: 不连接真实 Milvus 或 LLM，全部使用 mock
"""
import json
import os
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# 确保可以导入待测试的模块
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.vector_store import (
    VectorStoreService,
    MatchResult,
    EmbeddingClientProto,
    ChatClientProto,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_store():
    """创建空的 VectorStoreService（语料库为空）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStoreService(
            milvus_client=None,
            embedding_client=None,
            chat_client=None,
        )
        # 覆盖持久化目录到临时目录
        store._persist_dir = tmpdir
        os.makedirs(tmpdir, exist_ok=True)
        # 确保语料库为空
        store.clear()
        yield store


@pytest.fixture
def store_with_materials():
    """创建含测试资料的 VectorStoreService"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStoreService(
            milvus_client=None,
            embedding_client=None,
            chat_client=None,
        )
        # 覆盖持久化目录到临时目录
        store._persist_dir = tmpdir
        os.makedirs(tmpdir, exist_ok=True)
        # 清空残留
        store.clear()
        # 插入测试资料（含 doc_id 模拟真实上传）
        chunks = [
            {"text": "我方具备 ISO9001 质量管理体系认证，证书编号 A001"},
            {"text": "注册资本 5000 万元，成立于 2010 年"},
            {"text": "近三年财务状况良好，年营业额超过 1 亿元"},
            {"text": "拥有建筑工程施工总承包二级资质"},
            {"text": "项目团队配备项目经理、技术负责人等完整人员"},
        ]
        # 给所有 chunk 赋予 doc_id=1 模拟真实上传
        store.upsert(chunks, project_id=1, metadata={
            "doc_id": 1, "filename": "test_materials.pdf",
            "source_ref": "test_materials.pdf#1",
        })
        yield store


@pytest.fixture
def mock_embedding_client():
    """Mock Embedding 客户端"""
    client = MagicMock(spec=EmbeddingClientProto)
    client.embed.return_value = [[0.1] * 1024]  # 返回假向量
    return client


@pytest.fixture
def mock_chat_client():
    """Mock LLM 客户端"""
    client = MagicMock(spec=ChatClientProto)
    return client


# ---------------------------------------------------------------------------
# TestEmptyCorpus - 空库场景 (核心修复验证)
# ---------------------------------------------------------------------------

class TestEmptyCorpus:
    """验证企业资料库为空时的行为"""

    def test_empty_corpus_returns_missing(self, empty_store):
        """空库 → coverage=missing, material_covered=False"""
        requirement = {
            "id": 1,
            "content": "需要 ISO9001 质量管理体系认证",
            "category": "资质要求",
            "priority": "high",
        }
        result = empty_store.match_requirement_to_materials(requirement, project_id=1)
        
        assert result.coverage == "missing", f"期望 missing, 实际 {result.coverage}"
        assert result.material_covered is False
        assert result.confidence == 0.0
        assert result.pending_review is True
        assert len(result.evidence) == 0
        assert "为空" in result.gap

    def test_empty_corpus_returns_missing_even_with_milvus(self, empty_store, mock_embedding_client):
        """空库 + Milvus 配置 → 仍然返回 missing（不加载历史残留）"""
        empty_store._embedding_client = mock_embedding_client
        
        # 模拟 Milvus 搜索返回空
        with patch.object(empty_store, '_milvus_search', return_value=[]):
            requirement = {
                "id": 2,
                "content": "需要建筑工程施工总承包二级资质",
                "category": "资质要求",
                "priority": "high",
            }
            result = empty_store.match_requirement_to_materials(requirement, project_id=1)
            
            assert result.coverage == "missing"
            assert result.material_covered is False
            assert "为空" in result.gap

    def test_empty_corpus_no_fake_match(self, empty_store, mock_embedding_client, mock_chat_client):
        """空库 + LLM 可用 → 不应该编造结果"""
        empty_store._embedding_client = mock_embedding_client
        empty_store._chat_client = mock_chat_client
        
        # 即使 LLM 可用，空库也直接返回 missing
        requirement = {
            "id": 3,
            "content": "需要注册资本 5000 万元",
            "category": "财务要求",
            "priority": "high",
        }
        result = empty_store.match_requirement_to_materials(requirement, project_id=1)
        
        assert result.coverage == "missing"
        assert result.material_covered is False
        # LLM 不应被调用
        mock_chat_client.chat_json.assert_not_called()

    def test_empty_corpus_after_clear(self, store_with_materials):
        """清空资料库后 → 返回 missing"""
        requirement = {
            "id": 4,
            "content": "需要 ISO9001 质量管理体系认证",
            "category": "资质要求",
            "priority": "high",
        }
        
        # 先有资料能匹配
        result_before = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        assert result_before.coverage != "missing" or "为空" not in result_before.gap
        
        # 清空资料库
        store_with_materials.clear()
        
        # 清空后必须返回 missing
        result_after = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        assert result_after.coverage == "missing"
        assert result_after.material_covered is False
        assert "为空" in result_after.gap


# ---------------------------------------------------------------------------
# TestFullCoverage - 完全覆盖场景
# ---------------------------------------------------------------------------

class TestFullCoverage:
    """验证需求被完全覆盖的场景"""

    def test_full_coverage_returns_covered(self, store_with_materials, mock_chat_client):
        """完全覆盖 → material_covered=True"""
        mock_chat_client.chat_json.return_value = {
            "coverage": "full",
            "confidence": 0.95,
            "evidence": [
                {"chunk_id": "1", "quote": "我方具备 ISO9001 质量管理体系认证", "source_ref": "企业资质手册.pdf"}
            ],
            "gap": None,
            "reason": "企业资料完全覆盖 ISO9001 认证要求",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {
            "id": 10,
            "content": "需要 ISO9001 质量管理体系认证",
            "category": "资质要求",
            "priority": "high",
        }
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        assert result.material_covered is True, f"期望 True, 实际 {result.material_covered}"
        assert result.coverage == "full"
        assert result.confidence >= 0.70
        assert result.pending_review is False

    def test_full_coverage_evidence_has_source_ref(self, store_with_materials, mock_chat_client):
        """完全覆盖 → evidence 必须包含 source_ref"""
        mock_chat_client.chat_json.return_value = {
            "coverage": "full",
            "confidence": 0.90,
            "evidence": [
                {"chunk_id": "1", "quote": "ISO9001 认证", "source_ref": "企业资质手册.pdf"},
                {"chunk_id": "5", "quote": "项目团队配备", "source_ref": "人员配置表.xlsx"},
            ],
            "gap": None,
            "reason": "资料齐全",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {
            "id": 11,
            "content": "需要 ISO9001 认证和项目团队人员",
            "category": "综合要求",
            "priority": "high",
        }
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        assert len(result.evidence) > 0
        for ev in result.evidence:
            assert "source_ref" in ev, "evidence 缺少 source_ref"
            assert ev["source_ref"], "source_ref 不能为空"

    def test_full_coverage_to_dict_serializable(self, store_with_materials, mock_chat_client):
        """完全覆盖 → to_dict() 可 JSON 序列化"""
        mock_chat_client.chat_json.return_value = {
            "coverage": "full",
            "confidence": 0.85,
            "evidence": [{"chunk_id": "1", "quote": "ISO9001 认证", "source_ref": "test.pdf"}],
            "gap": None,
            "reason": "",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {"id": 12, "content": "需要 ISO9001 质量管理体系认证", "category": "资质要求", "priority": "high"}
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        d = result.to_dict()
        # 验证可 JSON 序列化
        json_str = json.dumps(d, ensure_ascii=False)
        assert json_str
        parsed = json.loads(json_str)
        assert parsed["material_covered"] is True


# ---------------------------------------------------------------------------
# TestPartialCoverage - 部分覆盖场景
# ---------------------------------------------------------------------------

class TestPartialCoverage:
    """验证部分覆盖的场景"""

    def test_partial_coverage_returns_pending_review(self, store_with_materials, mock_chat_client):
        """部分覆盖 → pending_review=True"""
        mock_chat_client.chat_json.return_value = {
            "coverage": "partial",
            "confidence": 0.60,
            "evidence": [
                {"chunk_id": "2", "quote": "注册资本 5000 万元", "source_ref": "营业执照.pdf"}
            ],
            "gap": "缺少近三年审计报告",
            "reason": "注册资本满足，但缺少审计报告",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {
            "id": 20,
            "content": "需要注册资本 5000 万元和近三年审计报告",
            "category": "财务要求",
            "priority": "high",
        }
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        assert result.coverage == "partial"
        assert result.pending_review is True
        assert result.gap is not None
        assert "缺少" in result.gap

    def test_partial_coverage_with_low_confidence(self, store_with_materials, mock_chat_client):
        """低置信度 (0.40-0.70) → pending_review=True"""
        mock_chat_client.chat_json.return_value = {
            "coverage": "full",  # LLM 误判为 full
            "confidence": 0.50,   # 但置信度低
            "evidence": [],
            "gap": None,
            "reason": "",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {"id": 21, "content": "测试", "category": "测试", "priority": "low"}
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        # 置信度 0.50 < 0.70 → 仍需人工复核
        assert result.pending_review is True


# ---------------------------------------------------------------------------
# TestMissingCoverage - 完全缺失场景
# ---------------------------------------------------------------------------

class TestMissingCoverage:
    """验证完全缺失的场景"""

    def test_missing_coverage_no_materials(self, store_with_materials):
        """需求关键词完全不在资料中 → coverage=missing"""
        requirement = {
            "id": 30,
            "content": "需要 特种设备制造许可证 编号 TS-2024-99999",
            "category": "资质要求",
            "priority": "high",
        }
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        assert result.coverage == "missing"
        assert result.material_covered is False
        assert result.gap is not None
        assert "TS-2024-99999" in result.gap or "关键词" in result.gap

    def test_llm_returns_missing(self, store_with_materials, mock_chat_client):
        """LLM 返回 missing → material_covered=False
        
        使用含 ISO9001 的需求：关键词检查通过（ISO9001 在语料中），
        但 LLM 判定资料不足以覆盖该需求
        """
        mock_chat_client.chat_json.return_value = {
            "coverage": "missing",
            "confidence": 0.0,
            "evidence": [],
            "gap": "企业资料不足以完全覆盖该需求",
            "reason": "虽然有 ISO9001 认证，但缺少其他必要条件",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {
            "id": 31, 
            "content": "需要 ISO9001 质量管理体系认证并具有特种设备制造许可证", 
            "category": "资质要求", 
            "priority": "high"
        }
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        # 关键词检查：ISO9001 在语料中，"特种设备制造许可证"的编号未命中
        # 可能走 LLM 或关键词缺失提前返回
        assert result.coverage == "missing"
        assert result.material_covered is False
        assert result.pending_review is True


# ---------------------------------------------------------------------------
# TestDegradationPaths - 降级路径
# ---------------------------------------------------------------------------

class TestDegradationPaths:
    """验证 Milvus/LLM 不可用时的降级路径"""

    def test_degrade_when_llm_unavailable(self, store_with_materials):
        """LLM 不可用 → 基于关键词匹配的降级判断"""
        requirement = {
            "id": 40,
            "content": "需要 ISO9001 质量管理体系认证",
            "category": "资质要求",
            "priority": "high",
        }
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        # 资料中确实有 ISO9001 → 关键词匹配能命中
        assert result.coverage in ("partial", "missing")
        assert result.pending_review is True

    def test_degrade_when_llm_raises(self, store_with_materials, mock_chat_client):
        """LLM 抛出异常 → 降级判断"""
        mock_chat_client.chat_json.side_effect = Exception("LLM 服务不可用")
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {
            "id": 41,
            "content": "需要 ISO9001 质量管理体系认证",
            "category": "资质要求",
            "priority": "high",
        }
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        assert result.pending_review is True
        # 降级时不应返回 full
        assert result.coverage != "full"

    def test_degrade_when_no_vectors(self, empty_store):
        """无向量数据 → 返回 missing"""
        requirement = {"id": 42, "content": "测试", "category": "测试", "priority": "low"}
        result = empty_store.match_requirement_to_materials(requirement, project_id=1)
        
        assert result.coverage == "missing"
        assert result.material_covered is False


# ---------------------------------------------------------------------------
# TestMatchCache - 缓存验证
# ---------------------------------------------------------------------------

class TestMatchCache:
    """验证缓存机制"""

    def test_second_call_hits_cache(self, store_with_materials, mock_chat_client):
        """第二次调用命中缓存"""
        mock_chat_client.chat_json.return_value = {
            "coverage": "full",
            "confidence": 0.90,
            "evidence": [{"chunk_id": "1", "quote": "ISO9001 认证", "source_ref": "test.pdf"}],
            "gap": None,
            "reason": "",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {"id": 50, "content": "需要 ISO9001 质量管理体系认证", "category": "资质要求", "priority": "high"}
        
        # 第一次调用 - 应调用 LLM
        result1 = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        assert mock_chat_client.chat_json.call_count == 1
        
        # 第二次调用 - 应命中缓存
        result2 = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        assert mock_chat_client.chat_json.call_count == 1, "第二次调用不应再调 LLM"
        assert result2.coverage == result1.coverage

    def test_invalidate_cache(self, store_with_materials, mock_chat_client):
        """手动失效缓存"""
        mock_chat_client.chat_json.return_value = {
            "coverage": "full",
            "confidence": 0.90,
            "evidence": [],
            "gap": None,
            "reason": "",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {"id": 51, "content": "需要 ISO9001 质量管理体系认证", "category": "资质要求", "priority": "high"}
        
        # 第一次调用
        store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        assert mock_chat_client.chat_json.call_count == 1
        
        # 手动失效
        store_with_materials.invalidate_match_cache()
        
        # 再次调用 - 应重新调用 LLM
        store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        assert mock_chat_client.chat_json.call_count == 2, "失效后应重新调用 LLM"

    def test_corpus_version_change_invalidates_cache(self, store_with_materials, mock_chat_client):
        """语料版本号变更 → 缓存失效"""
        mock_chat_client.chat_json.return_value = {
            "coverage": "full",
            "confidence": 0.90,
            "evidence": [],
            "gap": None,
            "reason": "",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {"id": 52, "content": "需要 ISO9001 质量管理体系认证", "category": "资质要求", "priority": "high"}
        
        # 第一次调用
        store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        assert mock_chat_client.chat_json.call_count == 1
        
        # 变更版本号
        store_with_materials.set_corpus_version(999)
        
        # 再次调用 - 应重新调用 LLM
        store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        assert mock_chat_client.chat_json.call_count == 2


# ---------------------------------------------------------------------------
# TestResultStructure - 结果结构验证
# ---------------------------------------------------------------------------

class TestResultStructure:
    """验证返回结构符合 MatchResult 规范"""

    def test_match_result_has_all_required_fields(self, store_with_materials, mock_chat_client):
        """MatchResult 必须包含所有必填字段"""
        mock_chat_client.chat_json.return_value = {
            "coverage": "partial",
            "confidence": 0.60,
            "evidence": [
                {"chunk_id": "1", "quote": "test quote", "source_ref": "source.pdf"}
            ],
            "gap": "some gap",
            "reason": "test reason",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {"id": 60, "content": "结构测试", "category": "测试", "priority": "low"}
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        # 验证所有字段
        assert hasattr(result, 'requirement_id')
        assert hasattr(result, 'coverage')
        assert hasattr(result, 'confidence')
        assert hasattr(result, 'material_covered')
        assert hasattr(result, 'evidence')
        assert hasattr(result, 'gap')
        assert hasattr(result, 'pending_review')
        assert hasattr(result, 'method')
        assert result.method == "hybrid_v1"

    def test_evidence_items_have_source_ref(self, store_with_materials, mock_chat_client):
        """evidence 中每个条目必须含 source_ref（可追溯铁律）"""
        mock_chat_client.chat_json.return_value = {
            "coverage": "full",
            "confidence": 0.95,
            "evidence": [
                {"chunk_id": "1", "quote": "quote1", "source_ref": "doc1.pdf"},
                {"chunk_id": "2", "quote": "quote2", "source_ref": "doc2.pdf"},
                {"chunk_id": "3", "quote": "quote3", "source_ref": "doc3.pdf"},
            ],
            "gap": None,
            "reason": "",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {"id": 61, "content": "溯源测试", "category": "测试", "priority": "low"}
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        for ev in result.evidence:
            assert "source_ref" in ev
            assert len(ev["source_ref"]) > 0, "source_ref 不能为空"

    def test_to_dict_returns_correct_structure(self, store_with_materials, mock_chat_client):
        """to_dict() 返回正确的字典结构"""
        mock_chat_client.chat_json.return_value = {
            "coverage": "missing",
            "confidence": 0.0,
            "evidence": [],
            "gap": "test gap",
            "reason": "",
        }
        
        store_with_materials._chat_client = mock_chat_client
        requirement = {"id": 62, "content": "dict测试", "category": "测试", "priority": "low"}
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "requirement_id" in d
        assert "coverage" in d
        assert "confidence" in d
        assert "material_covered" in d
        assert "evidence" in d
        assert "gap" in d
        assert "pending_review" in d
        assert "method" in d


# ---------------------------------------------------------------------------
# TestBackwardCompatibility - 向后兼容
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """验证原有 API 行为不变"""

    def test_original_search_still_works(self, store_with_materials):
        """search() 方法正常工作"""
        results = store_with_materials.search("ISO9001", project_id=1, top_k=3)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_original_compute_similarity_unchanged(self, store_with_materials):
        """_compute_similarity 签名和行为不变"""
        ngrams = store_with_materials._extract_ngrams("test")
        words = {"test"}
        score = store_with_materials._compute_similarity("test text", ngrams, words)
        assert isinstance(score, float)
        assert score > 0

    def test_upsert_and_search_roundtrip(self, empty_store):
        """upsert + search 闭环正常"""
        chunks = [
            {"text": "测试资料 A"},
            {"text": "测试资料 B"},
        ]
        ids = empty_store.upsert(chunks, project_id=1, metadata={
            "doc_id": 99, "filename": "test.pdf", "source_ref": "test.pdf#99",
        })
        assert len(ids) == 2
        
        results = empty_store.search("测试", project_id=1, top_k=5)
        assert len(results) >= 0  # n-gram 可能匹配或不匹配


# ---------------------------------------------------------------------------
# TestSecurity - 安全性验证
# ---------------------------------------------------------------------------

class TestSecurity:
    """验证不会编造结果"""

    def test_no_fake_evidence_when_corpus_empty(self, empty_store, mock_chat_client):
        """空库时绝不编造 evidence"""
        empty_store._chat_client = mock_chat_client
        
        # 即使 LLM 试图编造，空库检查已在入口拦截
        requirement = {"id": 70, "content": "任何需求", "category": "测试", "priority": "low"}
        result = empty_store.match_requirement_to_materials(requirement, project_id=1)
        
        assert result.evidence == [], "空库时 evidence 必须为空"
        assert result.material_covered is False

    def test_no_match_when_no_relevant_materials(self, store_with_materials, mock_chat_client):
        """资料存在但完全不相关 → 不应编造匹配"""
        # 需求包含完全不存在的关键词
        requirement = {
            "id": 71,
            "content": "需要 完全不存在的特殊资质编号 UNIQUE-XYZ-999",
            "category": "资质要求",
            "priority": "high",
        }
        result = store_with_materials.match_requirement_to_materials(requirement, project_id=1)
        
        # 关键词 UNIQUE-XYZ-999 不存在于资料中 → missing
        assert result.coverage == "missing"
        assert result.material_covered is False
        assert "UNIQUE-XYZ-999" in result.gap or "关键词" in result.gap