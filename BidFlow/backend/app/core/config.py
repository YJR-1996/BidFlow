import os
from pathlib import Path
from pydantic_settings import BaseSettings


# 计算项目根目录（backend/）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"


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

    # 文件上传
    ALLOWED_EXTENSIONS: set = {"pdf", "docx", "txt"}
    MAX_FILE_SIZE: int = 25 * 1024 * 1024  # 25MB

    # 目录
    BASE_DIR: Path = _PROJECT_ROOT
    UPLOAD_DIR: Path = _PROJECT_ROOT / "uploads"
    DATA_DIR: Path = _PROJECT_ROOT / "data"
    CHROMA_DIR: Path = _PROJECT_ROOT / "chroma"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    model_config = {
        "env_file": str(_ENV_FILE),
        "env_file_encoding": "utf-8",
    }


settings = Settings()

# 确保数据目录存在
for d in (settings.UPLOAD_DIR, settings.DATA_DIR, settings.CHROMA_DIR):
    d.mkdir(parents=True, exist_ok=True)
