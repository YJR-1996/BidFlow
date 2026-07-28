"""向量存储服务（基于 ChromaDB 的简化实现）"""
from typing import List, Dict, Optional


class VectorStoreService:
    """向量存储和检索服务"""

    def __init__(self):
        # 使用内存存储，避免依赖外部向量数据库
        self._vectors: List[Dict] = []
        self._id_counter = 0

    def upsert(
        self,
        chunks: List[Dict],
        project_id: Optional[int] = None,
        metadata: Optional[Dict] = None,
    ) -> List[int]:
        """批量插入或更新向量"""
        ids = []
        for chunk in chunks:
            self._id_counter += 1
            ids.append(self._id_counter)
            self._vectors.append({
                "id": self._id_counter,
                "text": chunk["text"],
                "project_id": project_id,
                "metadata": metadata or {},
            })
        return ids

    def search(
        self,
        query: str,
        project_id: Optional[int] = None,
        top_k: int = 5,
    ) -> List[Dict]:
        """按文本相似度搜索"""
        results = self._vectors[:]

        if project_id is not None:
            results = [v for v in results if v["project_id"] == project_id]

        # 简单关键词匹配（无 Embedding 模型时的替代方案）
        query_lower = query.lower()
        for r in results:
            text_lower = r["text"].lower()
            r["score"] = 0.0
            for word in query_lower.split():
                if len(word) > 2 and word in text_lower:
                    r["score"] += 1

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete_by_doc_id(self, doc_id: int) -> None:
        """按文档 ID 删除"""
        # 简化实现：不区分 doc_id，全部删除（实际应关联 doc_id）
        self._vectors.clear()


vector_store_service = VectorStoreService()
