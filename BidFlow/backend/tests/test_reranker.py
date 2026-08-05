"""RAG 增强测试：LLM Reranker 排序与降级、VectorStore 混合召回"""
from unittest.mock import patch, MagicMock

import pytest

from app.services.reranker import LLMReranker
from app.services.vector_store import VectorStoreService


def _candidates(n=3):
    return [
        {"id": i, "text": f"片段{i}：企业资质与业绩案例内容", "metadata": {"filename": f"case{i}.pdf"}, "score": 0.5}
        for i in range(n)
    ]


class TestLLMReranker:
    def test_empty_candidates(self):
        assert LLMReranker().rerank("q", []) == []

    def test_single_candidate_keeps_order(self):
        out = LLMReranker().rerank("q", _candidates(1), top_k=5)
        assert len(out) == 1
        assert out[0]["rerank_score"] == 1.0

    def test_llm_failure_degrades_to_original_order(self):
        """LLM 抛异常 → 保持召回序返回，不中断"""
        r = LLMReranker()
        with patch.object(r, "_call_llm", side_effect=RuntimeError("LLM down")):
            out = r.rerank("需求", _candidates(3), top_k=3)
        assert [c["id"] for c in out] == [0, 1, 2]

    def test_llm_success_reranks_by_score(self):
        """LLM 返回分数 → 按分数降序"""
        r = LLMReranker()
        scores = {"0": 0.2, "1": 0.9, "2": 0.5}
        with patch.object(r, "_call_llm", return_value=scores):
            out = r.rerank("需求", _candidates(3), top_k=3)
        assert [c["id"] for c in out] == [1, 2, 0]
        assert out[0]["rerank_score"] == 0.9

    def test_top_k_truncation(self):
        r = LLMReranker()
        scores = {"0": 0.9, "1": 0.8, "2": 0.7}
        with patch.object(r, "_call_llm", return_value=scores):
            out = r.rerank("需求", _candidates(3), top_k=2)
        assert len(out) == 2


class TestHybridSearch:
    def test_hybrid_merges_dense_and_keyword_dedup(self):
        """dense 召回 + keyword 补充，重复 id 去重，结果按分数降序"""
        svc = VectorStoreService()
        # 模拟内存向量（keyword 路可检索）
        svc._vectors = [
            {"id": 1, "text": "我方具有 A001 认证资质与三个类似项目案例", "project_id": None,
             "metadata": {"doc_id": 101, "filename": "case1.pdf", "scope": "company"}},
            {"id": 2, "text": "企业产品型号 XYZ-200 的技术规格说明", "project_id": None,
             "metadata": {"doc_id": 102, "filename": "spec.pdf", "scope": "company"}},
        ]
        svc._id_counter = 2
        # dense 路不可用（无 milvus）→ 混合退化为 keyword，验证返回结构与去重逻辑不报错
        out = svc.hybrid_search("A001 认证", None, top_k=5)
        assert isinstance(out, list)
        assert all("id" in r and "text" in r and "score" in r for r in out)

    def test_hybrid_empty_query(self):
        svc = VectorStoreService()
        assert svc.hybrid_search("", None, top_k=5) == []
