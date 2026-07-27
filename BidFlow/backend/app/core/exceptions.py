from typing import Any, Optional

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


class AppException(HTTPException):
    def __init__(
        self,
        code: int,
        message: str,
        detail: Optional[Any] = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(status_code=status_code, detail=message)


class NotFoundException(AppException):
    def __init__(self, message: str = "资源不存在", detail: Optional[Any] = None):
        super().__init__(code=404, message=message, detail=detail, status_code=status.HTTP_404_NOT_FOUND)


class ForbiddenException(AppException):
    def __init__(self, message: str = "无权限访问", detail: Optional[Any] = None):
        super().__init__(code=403, message=message, detail=detail, status_code=status.HTTP_403_FORBIDDEN)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "未授权访问", detail: Optional[Any] = None):
        super().__init__(code=401, message=message, detail=detail, status_code=status.HTTP_401_UNAUTHORIZED)


class ValidationException(AppException):
    def __init__(self, message: str = "参数校验失败", detail: Optional[Any] = None):
        super().__init__(code=422, message=message, detail=detail, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


class BusinessException(AppException):
    def __init__(self, message: str = "业务处理失败", detail: Optional[Any] = None):
        super().__init__(code=500, message=message, detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


def register_exception_handlers(app):
    @app.exception_handler(AppException)
    async def app_exception_handler(request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": exc.detail,
                "detail": None,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": 500,
                "message": "服务器内部错误",
                "detail": str(exc) if str(exc) else None,
            },
        )
