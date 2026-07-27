from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class CompanyDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: Optional[str]
    status: str
    created_at: datetime
