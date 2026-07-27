from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class ResponseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requirement_id: int
    ai_content: Optional[str]
    edited_content: Optional[str]
    source_refs: Optional[str]
    status: str
    updated_at: datetime


class DraftResponseRequest(BaseModel):
    requirement_id: int
    ai_content: str
    source_refs: Optional[list] = None
    status: str = "草稿"


class UpdateResponseRequest(BaseModel):
    edited_content: Optional[str] = None
    status: Optional[str] = None


class SourceReference(BaseModel):
    content: str
    filename: str
    source_ref: str
    score: Optional[float] = None
