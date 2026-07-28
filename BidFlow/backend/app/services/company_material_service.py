from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_document import CompanyDocument
from app.services.document_parser import document_parser_service
from app.services.file_storage import file_storage_service
from app.services.vector_store import vector_store


class CompanyMaterialService:
    async def upload_and_index(self, session: AsyncSession, owner_id: str, file: UploadFile) -> tuple[CompanyDocument, int]:
        file_path, filename = file_storage_service.save_file(project_id=0, user_id=owner_id, file=file)
        document = CompanyDocument(owner_id=owner_id, filename=filename, file_path=file_path, file_type=file_storage_service.get_file_extension(filename), status="processing")
        session.add(document)
        await session.commit()
        await session.refresh(document)
        try:
            paragraphs = document_parser_service.parse(file_path, document.file_type or "txt")
            chunks = [{"content": item["text"][:1200], "source_ref": item["source_ref"]} for item in paragraphs if item.get("text", "").strip()]
            count = vector_store.upsert_chunks(document.id, owner_id, filename, chunks)
            document.status = "success"
            await session.commit()
            await session.refresh(document)
            return document, count
        except Exception as exc:
            document.status = "failed"
            await session.commit()
            Path(file_path).unlink(missing_ok=True)
            raise exc

    async def list_documents(self, session: AsyncSession, owner_id: str) -> list[CompanyDocument]:
        return (await session.execute(select(CompanyDocument).where(CompanyDocument.owner_id == owner_id).order_by(CompanyDocument.created_at.desc()))).scalars().all()

    async def delete_document(self, session: AsyncSession, owner_id: str, document_id: int) -> bool:
        document = (await session.execute(select(CompanyDocument).where(CompanyDocument.id == document_id, CompanyDocument.owner_id == owner_id))).scalar_one_or_none()
        if document is None:
            return False
        vector_store.delete_document(document.id)
        Path(document.file_path).unlink(missing_ok=True)
        await session.delete(document)
        await session.commit()
        return True
