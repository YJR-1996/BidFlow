from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    tenderer: Optional[str] = Field(None, max_length=200, description="招标单位")
    deadline: Optional[datetime] = Field(None, description="截止日期")
    budget: Optional[int] = Field(None, description="预算金额")
    description: Optional[str] = Field(None, description="项目描述")


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200, description="项目名称")
    tenderer: Optional[str] = Field(None, max_length=200, description="招标单位")
    deadline: Optional[datetime] = Field(None, description="截止日期")
    budget: Optional[int] = Field(None, description="预算金额")
    description: Optional[str] = Field(None, description="项目描述")
    status: Optional[str] = Field(None, description="项目状态")


class ProjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tenderer: Optional[str]
    deadline: Optional[datetime]
    status: str
    created_at: datetime
    requirement_count: int = 0
    risk_count: int = 0
    completion_rate: float = 0.0


class ProjectDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: str
    name: str
    tenderer: Optional[str]
    deadline: Optional[datetime]
    budget: Optional[int]
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    completion_rate: float = 0.0
    readiness: Optional[dict] = None
