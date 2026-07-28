from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanyDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: str | None
    status: str
    created_at: datetime


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=10)


class RetrievedChunk(BaseModel):
    content: str
    filename: str
    source_ref: str
    score: float
