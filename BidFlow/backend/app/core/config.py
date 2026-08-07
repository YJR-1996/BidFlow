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
    # token 有效期 8 小时（覆盖一工作日，避免长时间编辑被踢）；.env 可覆盖
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Milvus
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION_NAME: str = "bidflow_entities"

    # LLM / DashScope
    DASHSCOPE_API_KEY: str = ""
    LLM_MODEL_NAME: str = "qwen-max"
    EMBEDDING_MODEL: str = "text-embedding-v3"
    SEMANTIC_COMPLIANCE_ENABLED: bool = True

    # OCR - 图片型 PDF 识别
    OCR_ENABLED: bool = True
    OCR_MODEL: str = "qwen-vl-ocr"
    OCR_DPI: int = 200

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        """解析 CORS_ORIGINS 为列表"""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # 文件上传
    ALLOWED_EXTENSIONS: set = {"pdf", "docx", "txt"}
    MAX_FILE_SIZE: int = 25 * 1024 * 1024  # 25MB
    MAX_UPLOAD_SIZE: int = 25 * 1024 * 1024  # 25MB (兼容 file_storage.py 使用)

    # Reflexion 质量闭环（响应生成后 LLM 评估，不达标带反馈重写）
    REFLEXION_ENABLED: bool = True
    REFLEXION_MAX_ROUNDS: int = 2        # 最多几轮（1 = 只生成不重写；2 = 生成+1次重写）
    REFLEXION_RETRY_TOP_K: int = 8       # 重写轮检索扩到 top_k（首轮用 5）

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
