import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "BidFlow API"
    APP_ENV: str = "development"

    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent

    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'data' / 'bidflow.db'}"

    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024
    ALLOWED_EXTENSIONS: set = {"txt", "pdf", "docx"}

    CHROMA_DIR: Path = BASE_DIR / "data" / "chroma"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: str = "qwen-plus"

    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()

settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
(settings.BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
settings.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
