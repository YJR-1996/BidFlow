from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse


class BaseAppException(Exception):
    """应用基础异常"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


class NotFoundException(BaseAppException):
    """资源未找到 - 404"""

    def __init__(self, message: str = "Resource not found"):
        super().__init__("NOT_FOUND", message)


class ValidationException(BaseAppException):
    """参数校验失败 - 422"""

    def __init__(self, message: str = "Validation failed"):
        super().__init__("VALIDATION_ERROR", message)


class ConflictException(BaseAppException):
    """资源冲突（如重复注册）- 409"""

    def __init__(self, message: str = "Resource conflict"):
        super().__init__("CONFLICT", message)


class DatabaseException(BaseAppException):
    """数据库操作失败 - 500"""

    def __init__(self, message: str = "Database error"):
        super().__init__("DATABASE_ERROR", message)


class ForbiddenException(BaseAppException):
    """无权限 - 403"""

    def __init__(self, message: str = "Forbidden"):
        super().__init__("FORBIDDEN", message)


async def app_exception_handler(request: Request, exc: BaseAppException) -> JSONResponse:
    """统一异常处理器"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


def http_exception(exc: BaseAppException) -> HTTPException:
    """将 BaseAppException 转换为 HTTPException，用于内部抛出"""
    status_map = {
        "NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "VALIDATION_ERROR": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "CONFLICT": status.HTTP_409_CONFLICT,
        "DATABASE_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "FORBIDDEN": status.HTTP_403_FORBIDDEN,
    }
    return HTTPException(
        status_code=status_map.get(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY),
        detail={"code": exc.code, "message": exc.message},
    )
