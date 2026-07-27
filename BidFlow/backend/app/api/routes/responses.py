"""成员 D 的响应草稿控制器；A 接入 FastAPI 时只需调用这些方法。"""

from typing import Any, Protocol

from app.models.response import BidResponse
from app.schemas.response import DraftResponsePayload, UpdateResponsePayload
from app.services.response_generation_service import ResponseGenerationService


class ResponseRepository(Protocol):
    def save(self, response: BidResponse) -> BidResponse: ...

    def get_by_requirement_id(self, requirement_id: int) -> BidResponse | None: ...


class ResponseController:
    def __init__(self, generator: ResponseGenerationService, repository: ResponseRepository) -> None:
        self._generator = generator
        self._repository = repository

    def generate(self, requirement: dict[str, Any], sources: list[dict[str, Any]]) -> DraftResponsePayload:
        result = self._generator.generate(requirement, sources)
        saved = self._repository.save(BidResponse(requirement_id=requirement["requirement_id"], ai_content=result.content, source_refs=result.sources, status=result.status))
        return DraftResponsePayload(saved.content, saved.source_refs, saved.status, result.message)

    def get(self, requirement_id: int) -> DraftResponsePayload | None:
        response = self._repository.get_by_requirement_id(requirement_id)
        if response is None:
            return None
        return DraftResponsePayload(response.content, response.source_refs, response.status, "已获取草稿。")

    def update(self, requirement_id: int, payload: UpdateResponsePayload) -> DraftResponsePayload:
        response = self._repository.get_by_requirement_id(requirement_id)
        if response is None:
            raise LookupError("未找到该需求项的响应草稿。")
        if payload.content is not None:
            response.edited_content = payload.content.strip()
        if payload.status is not None:
            response.update_status(payload.status)
        saved = self._repository.save(response)
        return DraftResponsePayload(saved.content, saved.source_refs, saved.status, "草稿已保存。")
