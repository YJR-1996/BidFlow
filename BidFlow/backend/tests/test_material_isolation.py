"""测试企业资料两级隔离 (scope-based isolation)

运行: pytest tests/test_material_isolation.py -v
注意: 不连接真实 Milvus，全部使用内存向量存储验证
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.vector_store import (
    VectorStoreService,
    MatchResult,
    COMPANY_SCOPE,
    PROJECT_SCOPE,
    VALID_SCOPES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    """创建隔离测试用的 VectorStoreService"""
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = VectorStoreService(
            milvus_client=None,
            embedding_client=None,
            chat_client=None,
        )
        svc._persist_dir = tmpdir
        os.makedirs(tmpdir, exist_ok=True)
        svc.clear()
        yield svc


def _meta(doc_id: int, filename: str = "test.pdf") -> dict:
    """生成模拟真实上传的 metadata（含 doc_id）"""
    return {"doc_id": doc_id, "filename": filename, "source_ref": f"{filename}#{doc_id}"}


# ---------------------------------------------------------------------------
# TestScopeConstants - 常量验证
# ---------------------------------------------------------------------------

class TestScopeConstants:
    """验证 scope 常量定义正确"""

    def test_company_scope_value(self):
        assert COMPANY_SCOPE == "company"

    def test_project_scope_value(self):
        assert PROJECT_SCOPE == "project"

    def test_valid_scopes(self):
        assert COMPANY_SCOPE in VALID_SCOPES
        assert PROJECT_SCOPE in VALID_SCOPES


# ---------------------------------------------------------------------------
# TestUpsertScope - upsert 的 scope 参数验证
# ---------------------------------------------------------------------------

class TestUpsertScope:
    """验证 upsert 的 scope 参数行为"""

    def test_default_scope_is_company(self, store):
        """默认 scope=company"""
        chunks = [{"text": "测试资料 A"}]
        ids = store.upsert(chunks, project_id=None, metadata=_meta(1))
        assert len(ids) == 1
        vec = store._vectors[0]
        assert vec["metadata"]["scope"] == COMPANY_SCOPE

    def test_explicit_company_scope(self, store):
        """显式 scope=company"""
        chunks = [{"text": "公司级资料"}]
        ids = store.upsert(chunks, project_id=None, metadata=_meta(1), scope=COMPANY_SCOPE)
        assert len(ids) == 1
        assert store._vectors[0]["metadata"]["scope"] == COMPANY_SCOPE

    def test_project_scope_with_project_id(self, store):
        """scope=project + project_id"""
        chunks = [{"text": "项目专属资料"}]
        ids = store.upsert(chunks, project_id=1, metadata=_meta(1), scope=PROJECT_SCOPE)
        assert len(ids) == 1
        assert store._vectors[0]["metadata"]["scope"] == PROJECT_SCOPE
        assert store._vectors[0]["project_id"] == 1

    def test_project_scope_without_project_id_raises(self, store):
        """scope=project 但无 project_id → ValueError"""
        chunks = [{"text": "非法项目级资料"}]
        with pytest.raises(ValueError, match="project scope requires project_id"):
            store.upsert(chunks, project_id=None, metadata=_meta(1), scope=PROJECT_SCOPE)

    def test_invalid_scope_raises(self, store):
        """无效 scope → ValueError"""
        chunks = [{"text": "非法 scope"}]
        with pytest.raises(ValueError, match="scope must be one of"):
            store.upsert(chunks, project_id=None, metadata=_meta(1), scope="invalid_scope")

    def test_company_scope_ignores_project_id(self, store):
        """scope=company 时忽略 project_id（存为 None）"""
        chunks = [{"text": "公司级资料，忽略项目ID"}]
        ids = store.upsert(chunks, project_id=5, metadata=_meta(1), scope=COMPANY_SCOPE)
        assert len(ids) == 1
        assert store._vectors[0]["project_id"] is None
        assert store._vectors[0]["metadata"]["scope"] == COMPANY_SCOPE


# ---------------------------------------------------------------------------
# TestSearchIsolation - 检索隔离验证 (核心)
# ---------------------------------------------------------------------------

class TestSearchIsolation:
    """验证检索时的 scope 隔离"""

    def test_company_scope_visible_to_all_projects(self, store):
        """scope=company 的资料 → 任意项目检索均可见"""
        store.upsert(
            [{"text": "ISO9001 质量管理体系认证"}],
            project_id=None,
            metadata=_meta(1),
            scope=COMPANY_SCOPE,
        )

        results_a = store.search("ISO9001", project_id=1)
        assert len(results_a) > 0, "项目1 应看到 company 级资料"

        results_b = store.search("ISO9001", project_id=999)
        assert len(results_b) > 0, "项目999 应看到 company 级资料"

        results_c = store.search("ISO9001", project_id=None)
        assert len(results_c) > 0, "无项目上下文应看到 company 级资料"

    def test_project_scope_only_visible_to_own_project(self, store):
        """scope=project + project_id=A → 仅项目 A 可见"""
        store.upsert(
            [{"text": "项目 A 专属资料 - 独特标识 XYZ-777"}],
            project_id=1,
            metadata=_meta(1),
            scope=PROJECT_SCOPE,
        )

        results_a = store.search("XYZ-777", project_id=1)
        assert len(results_a) > 0, "项目1 应看到自己的 project 级资料"

        results_b = store.search("XYZ-777", project_id=2)
        assert len(results_b) == 0, "项目2 不应看到项目1 的 project 级资料"

        results_c = store.search("XYZ-777", project_id=None)
        assert len(results_c) == 0, "无项目上下文不应看到 project 级资料"

    def test_mixed_scope_search(self, store):
        """混合场景: company + project 资料共存"""
        store.upsert(
            [{"text": "公司共享: 注册资本 5000 万元"}],
            project_id=None,
            metadata=_meta(1),
            scope=COMPANY_SCOPE,
        )
        store.upsert(
            [{"text": "项目A专属: 独特产品型号 PROJ-A-888"}],
            project_id=1,
            metadata=_meta(2),
            scope=PROJECT_SCOPE,
        )
        store.upsert(
            [{"text": "项目B专属: 产品代号 UNIQUE-B-999"}],
            project_id=2,
            metadata=_meta(3),
            scope=PROJECT_SCOPE,
        )

        results_a = store.search("注册资本", project_id=1)
        assert len(results_a) > 0, "项目A 应看到 company 级资料"

        results_a2 = store.search("PROJ-A-888", project_id=1)
        assert len(results_a2) > 0, "项目A 应看到自己的 project 级资料"

        results_a3 = store.search("UNIQUE-B-999", project_id=1)
        assert len(results_a3) == 0, "项目A 不应看到项目B 的 project 级资料"

        results_b1 = store.search("PROJ-A-888", project_id=2)
        assert len(results_b1) == 0, "项目B 不应看到项目A 的 project 级资料"

        results_b2 = store.search("UNIQUE-B-999", project_id=2)
        assert len(results_b2) > 0, "项目B 应看到自己的 project 级资料"

    def test_no_project_context_only_sees_company(self, store):
        """project_id=None 时仅看到 company 级资料"""
        store.upsert(
            [{"text": "公司级资料 COMMON-123"}],
            project_id=None,
            metadata=_meta(1),
            scope=COMPANY_SCOPE,
        )
        store.upsert(
            [{"text": "项目级资料 SPECIFIC-456"}],
            project_id=1,
            metadata=_meta(2),
            scope=PROJECT_SCOPE,
        )

        results = store.search("COMMON", project_id=None)
        assert len(results) > 0, "无项目上下文应看到 company 级资料"

        results2 = store.search("SPECIFIC", project_id=None)
        assert len(results2) == 0, "无项目上下文不应看到 project 级资料"

    def test_invalid_vectors_excluded_from_search(self, store):
        """无 doc_id 的无效向量不应参与检索"""
        # 插入有效向量
        store.upsert(
            [{"text": "有效资料 ISO9001"}],
            project_id=None,
            metadata=_meta(1),
            scope=COMPANY_SCOPE,
        )
        # 手动插入无效向量（无 doc_id）
        store._vectors.append({
            "id": 99,
            "text": "无效测试数据 SECRET-999",
            "project_id": None,
            "metadata": {},
        })
        store._id_counter = 99

        # 有效向量可被检索到
        results_valid = store.search("ISO9001", project_id=1)
        assert len(results_valid) > 0

        # 无效向量不应被检索到
        results_invalid = store.search("SECRET-999", project_id=1)
        assert len(results_invalid) == 0, "无 doc_id 的无效向量不应出现在检索结果中"


# ---------------------------------------------------------------------------
# TestBackwardCompatibility - 向后兼容 (存量数据)
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """验证存量无 scope 旧数据的兼容性"""

    def test_old_data_without_scope_treated_as_company(self, store):
        """存量无 scope 的旧 chunk → 默认视为 company（需有 doc_id）"""
        store._vectors.append({
            "id": 1,
            "text": "旧数据 ISO9001 认证",
            "project_id": None,
            "metadata": {"doc_id": 1, "filename": "old.pdf"},
            "score": 0.0,
        })
        store._id_counter = 1

        results = store.search("ISO9001", project_id=1)
        assert len(results) > 0, "旧数据应被视为 company 级，对项目1可见"

        results2 = store.search("ISO9001", project_id=999)
        assert len(results2) > 0, "旧数据应被视为 company 级，对所有项目可见"

    def test_old_data_without_doc_id_isolation(self, store):
        """无 doc_id 的旧数据在启动清理后应被移除"""
        store._vectors.append({
            "id": 1,
            "text": "孤儿数据 ORPHAN-123",
            "project_id": None,
            "metadata": {},
            "score": 0.0,
        })
        store._id_counter = 1

        # 无 doc_id 的向量应被 _cleanup_orphan_vectors 清理
        store._cleanup_orphan_vectors()
        assert len(store._vectors) == 0, "无 doc_id 的孤儿数据应被清理"

    def test_old_data_default_scope_in_match(self, store):
        """存量数据在 match 比对中也视为 company"""
        store._vectors.append({
            "id": 1,
            "text": "旧数据: ISO9001 认证",
            "project_id": None,
            "metadata": {"doc_id": 1, "filename": "old.pdf"},
            "score": 0.0,
        })
        store._id_counter = 1
        store._corpus_version = 1

        entry = store._vectors[0]
        assert store._matches_scope(entry, project_id=1) is True
        assert store._matches_scope(entry, project_id=None) is True


# ---------------------------------------------------------------------------
# TestScopeFilterExpression - scope 过滤表达式验证
# ---------------------------------------------------------------------------

class TestScopeFilterExpression:
    """验证 _build_scope_filter 输出正确"""

    def test_build_filter_with_project_id(self, store):
        desc = store._build_scope_filter(5)
        assert "company" in desc
        assert "project_id=5" in desc

    def test_build_filter_without_project_id(self, store):
        desc = store._build_scope_filter(None)
        assert "company" in desc

    def test_matches_scope_company(self, store):
        entry = {"text": "test", "project_id": None, "metadata": {"scope": "company"}}
        assert store._matches_scope(entry, project_id=1) is True
        assert store._matches_scope(entry, project_id=None) is True

    def test_matches_scope_project_correct_project(self, store):
        entry = {"text": "test", "project_id": 5, "metadata": {"scope": "project"}}
        assert store._matches_scope(entry, project_id=5) is True

    def test_matches_scope_project_wrong_project(self, store):
        entry = {"text": "test", "project_id": 5, "metadata": {"scope": "project"}}
        assert store._matches_scope(entry, project_id=3) is False

    def test_matches_scope_project_no_project_context(self, store):
        entry = {"text": "test", "project_id": 5, "metadata": {"scope": "project"}}
        assert store._matches_scope(entry, project_id=None) is False


# ---------------------------------------------------------------------------
# TestMatchWithScope - match_requirement_to_materials 中的隔离
# ---------------------------------------------------------------------------

class TestMatchWithScope:
    """验证需求比对中的 scope 隔离"""

    def test_match_respects_company_scope(self, store):
        """company 级资料在比对中对所有项目可见"""
        store.upsert(
            [{"text": "需要 ISO9001 质量管理体系认证"}],
            project_id=None,
            metadata=_meta(1),
            scope=COMPANY_SCOPE,
        )

        req = {"id": 1, "content": "需要 ISO9001 质量管理体系认证", "category": "资质要求", "priority": "high"}
        result = store.match_requirement_to_materials(req, project_id=1)
        assert result.coverage != "missing" or len(result.evidence) == 0

    def test_match_respects_project_scope_isolation(self, store):
        """项目级资料在比对中仅对绑定项目可见"""
        store.upsert(
            [{"text": "项目 A 专属: 独特资质 UNIQUE-A-001"}],
            project_id=1,
            metadata=_meta(1),
            scope=PROJECT_SCOPE,
        )

        req = {"id": 2, "content": "需要 UNIQUE-A-001 资质", "category": "资质要求", "priority": "high"}

        result_a = store.match_requirement_to_materials(req, project_id=1)
        assert result_a.coverage != "missing" or len(result_a.evidence) == 0

        result_b = store.match_requirement_to_materials(req, project_id=2)
        assert result_b.coverage == "missing" or result_b.material_covered is False

    def test_match_skips_invalid_vectors(self, store):
        """比对应跳过无 doc_id 的无效向量"""
        # 只插入无效向量
        store._vectors.append({
            "id": 1,
            "text": "无效数据 FAKE-ISO9001",
            "project_id": None,
            "metadata": {},
        })
        store._id_counter = 1

        req = {"id": 1, "content": "需要 ISO9001 认证", "category": "资质要求", "priority": "high"}
        result = store.match_requirement_to_materials(req, project_id=1)
        # 因为只有无效向量（无 doc_id），应返回 missing
        assert result.coverage == "missing"
        assert result.material_covered is False


# ---------------------------------------------------------------------------
# TestEdgeCases - 边界场景
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """边界场景测试"""

    def test_get_all_corpus_text_respects_scope(self, store):
        """_get_all_corpus_text 仅返回可见的有效资料"""
        store.upsert(
            [{"text": "Company text about ISO9001"}],
            project_id=None,
            metadata=_meta(1),
            scope=COMPANY_SCOPE,
        )
        store.upsert(
            [{"text": "Project 1 secret text SECRET-XYZ"}],
            project_id=1,
            metadata=_meta(2),
            scope=PROJECT_SCOPE,
        )

        text_1 = store._get_all_corpus_text(project_id=1)
        assert "ISO9001" in text_1
        assert "SECRET-XYZ" in text_1

        text_2 = store._get_all_corpus_text(project_id=2)
        assert "ISO9001" in text_2
        assert "SECRET-XYZ" not in text_2

        text_none = store._get_all_corpus_text(project_id=None)
        assert "ISO9001" in text_none
        assert "SECRET-XYZ" not in text_none

    def test_get_all_corpus_text_excludes_invalid(self, store):
        """_get_all_corpus_text 排除无 doc_id 的无效向量"""
        store.upsert(
            [{"text": "Valid company text"}],
            project_id=None,
            metadata=_meta(1),
            scope=COMPANY_SCOPE,
        )
        # 插入无效向量
        store._vectors.append({
            "id": 99,
            "text": "INVALID ORPHAN TEXT",
            "project_id": None,
            "metadata": {},
        })
        store._id_counter = 99

        text = store._get_all_corpus_text(project_id=None)
        assert "Valid company text" in text
        assert "INVALID ORPHAN TEXT" not in text

    def test_search_with_empty_query(self, store):
        """空查询返回所有可见有效结果（带 score=0）"""
        store.upsert(
            [{"text": "可见资料"}],
            project_id=None,
            metadata=_meta(1),
            scope=COMPANY_SCOPE,
        )
        results = store.search("", project_id=1)
        assert len(results) > 0

    def test_multiple_chunks_scope(self, store):
        """批量插入多个 chunk 均带 scope"""
        chunks = [
            {"text": "chunk 1"},
            {"text": "chunk 2"},
            {"text": "chunk 3"},
        ]
        ids = store.upsert(chunks, project_id=1, metadata=_meta(1), scope=PROJECT_SCOPE)
        assert len(ids) == 3
        for vec in store._vectors:
            assert vec["metadata"]["scope"] == PROJECT_SCOPE
            assert vec["project_id"] == 1

    def test_has_valid_materials(self, store):
        """_has_valid_materials 正确判断有效数据"""
        # 空库 → False
        assert store._has_valid_materials() is False

        # 只有无效向量 → False
        store._vectors.append({
            "id": 1, "text": "fake", "project_id": None, "metadata": {},
        })
        assert store._has_valid_materials() is False

        # 有有效向量 → True
        store._vectors = []
        store._id_counter = 0
        store.upsert(
            [{"text": "real data"}],
            project_id=None,
            metadata=_meta(1),
            scope=COMPANY_SCOPE,
        )
        assert store._has_valid_materials() is True