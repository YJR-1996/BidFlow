"""D 模块的结构化响应契约；可直接映射到 FastAPI/Pydantic Schema。"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SourceReference:
    content: str
    filename: str
    source_ref: str
    score: float | None = None


@dataclass(frozen=True)
class DraftResponsePayload:
    content: str
    sources: list[dict[str, Any]]
    status: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UpdateResponsePayload:
    content: str | None = None
    status: str | None = None
