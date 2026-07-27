from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    """统一成功响应格式"""
    code: int = 0
    message: str = "success"
    data: T | None = None


class ListResponse(BaseModel, Generic[T]):
    """统一列表响应格式"""
    code: int = 0
    message: str = "success"
    data: list[T] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """统一错误响应格式"""
    detail: ErrorDetail
