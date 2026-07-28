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


# Knowledge base schemas used by knowledge.py
class CompanyDocumentOut(BaseModel):
    """企业资料输出"""
    id: int
    filename: str
    file_type: Optional[str]
    status: str
    created_at: datetime


class RetrievalRequest(BaseModel):
    """检索请求"""
    query: str
    project_id: Optional[int] = None
    top_k: int = 5


class RetrievedChunk(BaseModel):
    """检索返回的文本块"""
    content: str
    score: float
    filename: str
    source_ref: Optional[str] = None
    material_type: Optional[str] = None
