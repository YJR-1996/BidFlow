from sqlalchemy.orm import DeclarativeBase

from app.models.user import User  # noqa: F401  # 导入以注册到 Base._decl_class_registry


class Base(DeclarativeBase):
    """ORM 基类，所有模型继承此类"""
    pass
