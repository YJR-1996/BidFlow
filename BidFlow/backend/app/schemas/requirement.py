from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class RequirementUpdate(BaseModel):
    content: Optional[str] = Field(None, description="需求内容")
    category: Optional[str] = Field(None, description="类别")
    priority: Optional[str] = Field(None, description="优先级")
    status: Optional[str] = Field(None, description="状态")
    assignee_id: Optional[str] = Field(None, description="负责人ID")
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
    priority: str
    status: str
    assignee_id: Optional[str]
    risk_level: str
    created_at: datetime
    updated_at: datetime


class RequirementListQuery(BaseModel):
    category: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[str] = None
    keyword: Optional[str] = None
