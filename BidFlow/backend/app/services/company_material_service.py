"""公司资料上传和检索服务"""
from pathlib import Path
from typing import Optional, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ValidationException, BusinessException
from app.models.company_document import CompanyDocument
from app.models.user import User


class CompanyMaterialService:
    """公司资料上传、解析和检索服务"""

    def __init__(self):
        self.base_dir = settings.UPLOAD_DIR
        self.allowed_extensions = settings.ALLOWED_EXTENSIONS

    def upload_and_process(
        self,
        db: Session,
        user: User,
        file,
    ) -> CompanyDocument:
        """上传公司资料并处理"""
        # 1. 验证文件
        original_filename = file.filename or ""
        if not original_filename:
            raise ValidationException(message="文件名不能为空")

        ext = self._get_safe_extension(original_filename)

        # 2. 保存文件
        import uuid
        import os
        file_id = str(uuid.uuid4())
        filename = f"{file_id}{ext}"
        save_dir = self.base_dir / "company"
        save_dir.mkdir(parents=True, exist_ok=True)
        file_path = save_dir / filename

        # 读取文件内容
        content = file.file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # 3. 创建数据库记录
        doc = CompanyDocument(
            owner_id=user.id,
            filename=original_filename,
            file_path=str(file_path),
            file_type=ext,
            status="pending",
        )
        db.add(doc)
        db.flush()

        # 4. 更新为 processing
        doc.status = "processing"
        db.flush()

        # 5. 解析和切块
        try:
            from app.services.document_parser import document_parser_service
            from app.services.text_chunker import text_chunker_service
            from app.services.vector_store import vector_store_service

            # 解析
            paragraphs = document_parser_service.parse(str(file_path), ext)

            # 切块
            chunks = text_chunker_service.chunk(paragraphs)

            # 写入向量存储
            if chunks:
                vector_store_service.upsert(
                    project_id=None,  # 全局资料
                    chunks=chunks,
                    metadata={
                        "doc_id": doc.id,
                        "filename": original_filename,
                    },
                )

            doc.status = "success"
        except Exception as e:
            doc.status = "failed"
            doc.error_message = str(e)
            db.flush()
            raise BusinessException(message=f"资料处理失败: {str(e)}")

        db.commit()
        db.refresh(doc)
        return doc

    def list_by_owner(
        self,
        db: Session,
        user: User,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> List[CompanyDocument]:
        """列出用户上传的资料"""
        query = db.query(CompanyDocument).filter(
            CompanyDocument.owner_id == user.id
        )
        if status:
            query = query.filter(CompanyDocument.status == status)
        return (
            query.order_by(CompanyDocument.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def delete(self, db: Session, doc: CompanyDocument) -> None:
        """删除资料及其向量"""
        # 1. 删除向量
        try:
            from app.services.vector_store import vector_store_service
            vector_store_service.delete_by_doc_id(doc.id)
        except Exception:
            pass  # 向量删除失败不影响整体

        # 2. 删除文件
        try:
            file_path = Path(doc.file_path)
            if file_path.exists():
                file_path.unlink()
        except Exception:
            pass  # 文件删除失败不影响整体

        # 3. 删除数据库记录
        db.delete(doc)
        db.commit()

    def _get_safe_extension(self, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in self.allowed_extensions:
            raise ValidationException(
                message=f"不支持的文件格式，仅支持：{', '.join(self.allowed_extensions)}"
            )
        return ext
