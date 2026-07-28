"""Milvus 向量存储：只保存企业资料切片及其可追溯来源。"""

from uuid import uuid4

from openai import OpenAI
from pymilvus import MilvusClient

from app.core.config import settings


class VectorStoreError(RuntimeError):
    pass


class MilvusVectorStore:
    def __init__(self) -> None:
        self._client: MilvusClient | None = None
        self._embedder: OpenAI | None = None

    @property
    def client(self) -> MilvusClient:
        if self._client is None:
            self._client = MilvusClient(uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
        return self._client

    @property
    def embedder(self) -> OpenAI:
        if not settings.DASHSCOPE_API_KEY:
            raise VectorStoreError("DASHSCOPE_API_KEY 未配置，无法生成资料向量。")
        if self._embedder is None:
            self._embedder = OpenAI(api_key=settings.DASHSCOPE_API_KEY, base_url=settings.DASHSCOPE_BASE_URL)
        return self._embedder

    def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            result = self.embedder.embeddings.create(model=settings.EMBEDDING_MODEL, input=texts, dimensions=settings.EMBEDDING_DIMENSION)
            return [item.embedding for item in result.data]
        except Exception as exc:
            raise VectorStoreError("向量模型调用失败，请检查 DashScope 配置。") from exc

    def _ensure_collection(self) -> None:
        try:
            if not self.client.has_collection(settings.MILVUS_COLLECTION_NAME):
                self.client.create_collection(
                    collection_name=settings.MILVUS_COLLECTION_NAME,
                    dimension=settings.EMBEDDING_DIMENSION,
                    metric_type="COSINE",
                    auto_id=False,
                )
        except Exception as exc:
            raise VectorStoreError("无法连接 Milvus，请确认服务已启动。") from exc

    def upsert_chunks(self, document_id: int, owner_id: str, filename: str, chunks: list[dict[str, str]]) -> int:
        if not chunks:
            return 0
        self._ensure_collection()
        vectors = self._embed([item["content"] for item in chunks])
        data = [
            {"id": uuid4().int % (2**63 - 1), "vector": vector, "document_id": document_id, "owner_id": owner_id, "filename": filename, "content": chunk["content"], "source_ref": chunk["source_ref"]}
            for vector, chunk in zip(vectors, chunks, strict=True)
        ]
        try:
            self.client.insert(collection_name=settings.MILVUS_COLLECTION_NAME, data=data)
        except Exception as exc:
            raise VectorStoreError("Milvus 写入失败。") from exc
        return len(data)

    def search(self, owner_id: str, query: str, top_k: int) -> list[dict]:
        self._ensure_collection()
        vector = self._embed([query])[0]
        try:
            results = self.client.search(
                collection_name=settings.MILVUS_COLLECTION_NAME,
                data=[vector],
                limit=top_k,
                filter=f'owner_id == "{owner_id}"',
                output_fields=["filename", "content", "source_ref"],
            )[0]
        except Exception as exc:
            raise VectorStoreError("Milvus 检索失败。") from exc
        return [{"content": item["entity"]["content"], "filename": item["entity"]["filename"], "source_ref": item["entity"]["source_ref"], "score": float(item["distance"])} for item in results]

    def delete_document(self, document_id: int) -> None:
        self._ensure_collection()
        try:
            self.client.delete(collection_name=settings.MILVUS_COLLECTION_NAME, filter=f"document_id == {document_id}")
        except Exception as exc:
            raise VectorStoreError("Milvus 删除失败。") from exc


vector_store = MilvusVectorStore()
