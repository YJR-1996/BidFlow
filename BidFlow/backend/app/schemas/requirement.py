from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class RequirementUpdate(BaseModel):
    content: Optional[str] = Field(None, description="需求内容")
    category: Optional[str] = Field(None, description="类别")
    priority: Optional[str] = Field(None, description="优先级")
    status: Optional[str] = Field(None, description="状态")
    assignee_id: Optional[int] = Field(None, description="负责人ID")
    source_text: Optional[str] = Field(None, description="原文片段")
    source_ref: Optional[str] = Field(None, description="来源引用")


class RequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    tender_document_id: Optional[int]
    category: str
    content: str
    source_text: Optional[str]
    source_ref: Optional[str]
    source: Optional[str] = None
    priority: str
    status: str
    assignee_id: Optional[int]
    risk_level: str
    response_status: Optional[str] = None
    has_response: bool = False
    created_at: datetime
    updated_at: datetime


class AuxGenerateRequest(BaseModel):
    """辅助需求生成请求"""
    tender_document_id: Optional[int] = Field(None, description="招标文件ID（可选，仅生成该文档关联需求的辅助项）")
    max_items: int = Field(10, ge=1, le=30, description="最多生成条数")


class AuxGenerateItem(BaseModel):
    """辅助需求生成结果项"""
    id: int
    content: str
    category: str
    priority: str
    source: str = "ai_aux"


class AuxGenerateResponse(BaseModel):
    """辅助需求生成响应"""
    generated_count: int
    skipped_existing: bool = False
    items: list[AuxGenerateItem]


class RequirementListQuery(BaseModel):
    category: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[int] = None
    keyword: Optional[str] = None
