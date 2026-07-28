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
    ) -> List[Dict]:
        """
        检索相关企业资料片段

        Args:
            query: 检索关键词
            project_id: 项目 ID（可选，用于过滤）
            top_k: 返回结果数量

        Returns:
            检索结果列表，包含 content, score, filename, material_type, source_ref
        """
        if not query or not query.strip():
            return []

        top_k = min(top_k, self.max_results)

        # 调用向量存储进行检索
        from app.services.vector_store import vector_store_service
        raw_results = vector_store_service.search(query, project_id, top_k)

        # 转换为统一格式
        results = []
        for r in raw_results:
            if r.get("score", 0) > 0:  # 过滤低相关结果
                results.append({
                    "content": r["text"],
                    "score": r["score"],
                    "filename": r["metadata"].get("filename", ""),
                    "material_type": "company_document",
                    "source_ref": r["metadata"].get("source_ref", ""),
                })

        return results


retrieval_service = RetrievalService()
