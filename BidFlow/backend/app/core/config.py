import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，从 .env 文件加载环境变量"""

    # 应用
    APP_NAME: str = "BidFlow"
    DEBUG: bool = False

    # MySQL
    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_DATABASE: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Milvus
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION_NAME: str = "bidflow_entities"

    # LLM / DashScope
    DASHSCOPE_API_KEY: str = ""
    LLM_MODEL_NAME: str = "qwen-max"
    EMBEDDING_MODEL: str = "text-embedding-v3"

    # 目录
    BASE_DIR: Path = Path(__file__).resolve().parents[2]
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    DATA_DIR: Path = BASE_DIR / "data"
    CHROMA_DIR: Path = BASE_DIR / "chroma"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+asyncmy://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# 确保数据目录存在
for d in (settings.UPLOAD_DIR, settings.DATA_DIR, settings.CHROMA_DIR):
    d.mkdir(parents=True, exist_ok=True)
