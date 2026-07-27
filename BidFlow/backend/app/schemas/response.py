from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class ResponseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requirement_id: int
    content: Optional[str]
    source_refs: Optional[str]
    status: str
    updated_at: datetime
