import os
import uuid
from pathlib import Path
from typing import Tuple

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import ValidationException, BusinessException


class FileStorageService:
    def __init__(self):
        self.base_dir = settings.UPLOAD_DIR
        self.allowed_extensions = settings.ALLOWED_EXTENSIONS

    def _get_safe_extension(self, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in self.allowed_extensions:
            raise ValidationException(
                message=f"不支持的文件格式，仅支持：{', '.join(self.allowed_extensions)}"
            )
        return ext

    def _sanitize_filename(self, filename: str) -> str:
        name = filename.replace("..", "").replace("/", "").replace("\\", "")
        return name

    def save_file(self, project_id: int, user_id: int, file: UploadFile) -> Tuple[str, str]:
        original_filename = self._sanitize_filename(file.filename or "upload")
        ext = self._get_safe_extension(original_filename)

        user_dir = self.base_dir / f"user_{user_id}" / f"project_{project_id}"
        user_dir.mkdir(parents=True, exist_ok=True)

        unique_name = f"{uuid.uuid4().hex}.{ext}"
        file_path = user_dir / unique_name

        try:
            with open(file_path, "wb") as f:
                content = file.file.read()
                if len(content) > settings.MAX_UPLOAD_SIZE:
                    raise ValidationException(message=f"文件大小超过限制，最大 {settings.MAX_UPLOAD_SIZE // 1024 // 1024}MB")
                f.write(content)
        except ValidationException:
            raise
        except Exception as e:
            raise BusinessException(message=f"文件保存失败: {str(e)}")

        return str(file_path), original_filename

    def delete_file(self, file_path: str) -> bool:
        try:
            path = Path(file_path)
            if not path.exists():
                return True
            if not str(path.resolve()).startswith(str(self.base_dir.resolve())):
                raise BusinessException(message="非法文件路径")
            path.unlink()
            return True
        except BusinessException:
            raise
        except Exception as e:
            raise BusinessException(message=f"文件删除失败: {str(e)}")

    def get_file_extension(self, filename: str) -> str:
        return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


file_storage_service = FileStorageService()
