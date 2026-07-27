from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class TenderDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    filename: str
    file_type: Optional[str]
    file_size: Optional[int]
    status: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class ParseResultResponse(BaseModel):
    document_id: int
    status: str
    requirement_count: int = 0
    error_message: Optional[str] = None
