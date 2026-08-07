from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from datetime import datetime


def _coerce_deadline(v):
    """兼容前端日期控件只发 date-only 字符串（"YYYY-MM-DD"）的情况。

    Pydantic v2 的 datetime 字段不接受纯日期字符串（会直接 422），
    这里在类型强转前把 "YYYY-MM-DD" 补成 "YYYY-MM-DDT00:00:00"（当天零点）。
    已是完整 datetime（含 'T' 或空格分隔时间）或 datetime 对象的原样返回。
    """
    if isinstance(v, str):
        s = v.strip()
        if s and "T" not in s and " " not in s:
            s = f"{s}T00:00:00"
        return s
    return v


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    tenderer: Optional[str] = Field(None, max_length=200, description="招标单位")
    deadline: Optional[datetime] = Field(None, description="截止日期")
    budget: Optional[int] = Field(None, description="预算金额")
    description: Optional[str] = Field(None, description="项目描述")

    @field_validator("deadline", mode="before")
    @classmethod
    def _normalize_deadline(cls, v):
        return _coerce_deadline(v)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200, description="项目名称")
    tenderer: Optional[str] = Field(None, max_length=200, description="招标单位")
    deadline: Optional[datetime] = Field(None, description="截止日期")
    budget: Optional[int] = Field(None, description="预算金额")
    description: Optional[str] = Field(None, description="项目描述")
    status: Optional[str] = Field(None, description="项目状态")

    @field_validator("deadline", mode="before")
    @classmethod
    def _normalize_deadline(cls, v):
        return _coerce_deadline(v)


class ProjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tender_no: Optional[str] = None
    tender_ref_no: Optional[str] = None
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
    tender_no: Optional[str] = None
    tender_ref_no: Optional[str] = None
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
