"""检索服务 - 给 D 提供统一的"从企业资料找证据"入口"""
from typing import List, Dict, Optional


class RetrievalService:
    """企业资料检索服务"""

    def __init__(self):
        self.max_results = 10

    def search(
        self,
        query: str,
        project_id: Optional[int] = None,
        top_k: int = 5,
        rerank: bool = True,
    ) -> List[Dict]:
        """
        检索相关企业资料片段

        Args:
            query: 检索关键词
            project_id: 项目 ID（可选，用于过滤）
            top_k: 返回结果数量
            rerank: 是否执行 LLM 精排（默认 True）。仅需判断"有无资料"的
                    批量预筛等场景传 False，避免每条需求触发一次串行 LLM 调用。

        Returns:
            检索结果列表，包含 content, score, filename, material_type, source_ref
        """
        if not query or not query.strip():
            return []

        top_k = min(top_k, self.max_results)

        # RAG 增强：混合召回（dense + keyword）→ LLM 精排 → top_k
        # 任何一环失败自动降级（hybrid 失败 → 纯向量/关键词；rerank 失败 → 保持召回序）
        from app.services.vector_store import vector_store_service
        try:
            raw_results = vector_store_service.hybrid_search(query, project_id, top_k * 3)
        except Exception:
            raw_results = vector_store_service.search(query, project_id, top_k * 3)

        # 转换为统一格式（过滤低相关结果）
        results = []
        for r in raw_results:
            if r.get("score", 0) > 0:
                meta = r["metadata"]
                results.append({
                    "content": r["text"],
                    "score": r["score"],
                    "rerank_score": r.get("rerank_score"),
                    "filename": meta.get("filename", ""),
                    "material_type": "company_document",
                    "source_ref": meta.get("source_ref", ""),
                    "scope": meta.get("scope", "company"),
                    # 检索模式标记：dense=语义 / keyword=关键词（RAG 增强可视化）
                    "retrieval_type": r.get("retrieval_type"),
                })

        # LLM 精排（对候选重新打分排序；失败降级保持召回序）
        # rerank=False 时跳过（批量预筛等场景：只判断有无资料，省掉每条一次 LLM 调用）
        if results and rerank:
            from app.services.reranker import llm_reranker
            ranked = llm_reranker.rerank(query, results, top_k)
            if ranked:
                results = ranked

        return results[:top_k]


retrieval_service = RetrievalService()
