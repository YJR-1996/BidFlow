from app.services.vector_store import vector_store


class RetrievalService:
    def search(self, owner_id: str, query: str, top_k: int) -> list[dict]:
        return vector_store.search(owner_id=owner_id, query=query, top_k=top_k)
