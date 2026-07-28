from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """ORM 基类，所有模型继承此类"""
    pass


__all__ = ["Base"]
