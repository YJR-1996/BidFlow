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


# Payload schemas used by ResponseController
class DraftResponsePayload(BaseModel):
    """响应草稿 Payload（用于 Controller 内部数据传输）"""
    content: str
    source_refs: Optional[list] = None
    status: str
    message: str = ""


class UpdateResponsePayload(BaseModel):
    """更新响应 Payload（用于 Controller 内部数据传输）"""
    content: Optional[str] = None
    status: Optional[str] = None
