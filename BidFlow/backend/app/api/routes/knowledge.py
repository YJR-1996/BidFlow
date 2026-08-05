"""
成员C —— 全部 HTTP 接口集中在此文件（按用户要求「接口在一个文件里」，便于整合）。

本文件合并了分工表中的两个路由职责：
    - 企业资料：company_documents.py
    - 检索：    retrieval.py
对外统一挂载在 /api 前缀下，成员A 整合时只需 include 这一个 router 即可。

提供的端点：
    POST   /api/company-documents          上传企业资料并入库（返回片段数）
    GET    /api/company-documents          列出企业资料（可按 project_id 过滤）
    DELETE /api/company-documents/{id}     删除资料及其全部向量
    POST   /api/retrieval/search           检索相关企业资料片段（供成员D生成草稿）

依赖：FastAPI 的 Depends(get_db) 由成员A的 db/session.py 提供，这里直接复用。
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.company_document import CompanyDocument
from app.api.deps import get_current_user
from app.schemas.company_document import (
    CompanyDocumentOut,
    RetrievalRequest,
    RetrievedChunk,
)
from app.services.company_material_service import CompanyMaterialService
from app.services.retrieval_service import RetrievalService

# 所有企业资料/检索相关接口统一前缀 /api（由 router.py 统一添加，这里不再重复）
router = APIRouter(tags=["company-materials"])


# ---------------------------------------------------------------------------
# 1) 上传企业资料并向量化入库
# ---------------------------------------------------------------------------
@router.post("/company-documents", response_model=dict)
async def upload_company_document(
    file: UploadFile = File(..., description="企业资料文件(TXT/PDF/DOCX)"),
    scope: str = Form("company", description="资料作用域: company=公司级共享, project=项目级专属"),
    project_id: int = Form(None, description="归属投标项目id（scope=project时必填）"),
    category: str = Form(None, description="文档类别"),
    tags: str = Form(None, description="标签(逗号分隔)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    上传企业资质/案例/产品资料等 -> 解析 -> 切分 -> Embedding -> 写入向量库。
    
    两级隔离:
      - scope=company: 公司级共享资料，所有项目可见（忽略 project_id）
      - scope=project: 项目级专属资料，仅绑定 project_id 的项目可见
      
    返回资料 id、文件名、处理状态与切片数量。
    """
    # scope 校验
    from app.services.vector_store import COMPANY_SCOPE, PROJECT_SCOPE, VALID_SCOPES
    if scope not in VALID_SCOPES:
        raise HTTPException(status_code=400, detail=f"scope 必须是 {VALID_SCOPES} 之一")
    if scope == PROJECT_SCOPE and project_id is None:
        raise HTTPException(status_code=400, detail="项目级资料必须绑定 project_id")
    if scope == PROJECT_SCOPE:
        # 鉴权：项目级资料必须归属当前用户，防止跨租户向他人项目注入资料
        from app.models.bid_project import BidProject
        if not db.query(BidProject).filter(
            BidProject.id == project_id, BidProject.owner_id == current_user.id
        ).first():
            raise HTTPException(status_code=403, detail="无权向该项目上传资料")
    if scope == COMPANY_SCOPE:
        project_id = None  # company 级强制忽略 project_id

    svc = CompanyMaterialService()
    try:
        doc = svc.upload_and_process(
            db=db, user=current_user, file=file,
            category=category, tags=tags, project_id=project_id,
            scope=scope,
        )
        return {
            "id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "status": doc.status,
            "scope": scope,
            "project_id": project_id,
            "message": "资料上传并处理成功",
        }
    except Exception as e:
        # 即使解析失败，文档记录已创建（状态为 failed）
        # 返回失败状态，而不是 500 错误
        error_msg = str(e)
        if hasattr(e, 'message'):
            error_msg = e.message
        raise HTTPException(status_code=400, detail=error_msg)


# ---------------------------------------------------------------------------
# 2) 列出企业资料
# ---------------------------------------------------------------------------
@router.get("/company-documents", response_model=list[CompanyDocumentOut])
def list_company_documents(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出当前用户上传的企业资料。"""
    svc = CompanyMaterialService()
    docs = svc.list_by_owner(db=db, user=current_user, skip=skip, limit=limit)

    # 批量获取项目级资料对应的真实项目名（一次性 JOIN，避免 N+1）
    from app.models.bid_project import BidProject
    project_ids = {d.project_id for d in docs if getattr(d, 'project_id', None)}
    project_names = {}
    if project_ids:
        projs = db.query(BidProject.id, BidProject.name).filter(
            BidProject.id.in_(project_ids)
        ).all()
        project_names = {pid: name for pid, name in projs}

    # 获取向量存储中各文档的向量数量
    from app.services.vector_store import vector_store_service
    vector_counts = {}
    for vec in vector_store_service._vectors:
        doc_id = vec.get("metadata", {}).get("doc_id")
        if doc_id:
            vector_counts[doc_id] = vector_counts.get(doc_id, 0) + 1

    return [
        CompanyDocumentOut(
            id=d.id,
            filename=d.filename,
            file_type=d.file_type,
            category=getattr(d, 'category', None),
            tags=getattr(d, 'tags', None),
            status=d.status,
            created_at=d.created_at,
            vector_count=vector_counts.get(d.id, 0) if d.status == "success" else None,
            error_message=getattr(d, 'error_message', None),
            scope=getattr(d, 'scope', 'company'),
            project_id=getattr(d, 'project_id', None),
            project_name=project_names.get(d.project_id) if getattr(d, 'project_id', None) else None,
        )
        for d in docs
    ]


# ---------------------------------------------------------------------------
# 3) 删除企业资料（含向量）
# ---------------------------------------------------------------------------
@router.delete("/company-documents/{doc_id}", response_model=dict)
def delete_company_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除某条资料记录，并同步删除向量库中该资料的全部片段。"""
    svc = CompanyMaterialService()
    doc = db.query(CompanyDocument).filter(
        CompanyDocument.id == doc_id,
        CompanyDocument.owner_id == current_user.id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="资料不存在或无权限")
    svc.delete(db=db, doc=doc)
    return {"deleted": doc_id, "success": True}


# ---------------------------------------------------------------------------
# 3.5) 修改资料归属（改归属功能：公司级 ⇄ 项目级 + 指定项目）
# ---------------------------------------------------------------------------
@router.patch("/company-documents/{doc_id}/scope", response_model=dict)
def update_document_scope(
    doc_id: int,
    scope: str = Form("company", description="company=公司级共享 / project=项目级专属"),
    project_id: int = Form(None, description="归属项目 id（scope=project 时必填）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改资料归属范围：公司级（全项目共享）⇄ 项目级（绑定指定项目）。

    - 校验：资料归属当前用户；scope=project 时目标项目也必须归属当前用户
    - 同步：DB 字段 + 向量库 metadata（内存/Milvus），检索过滤立即生效
    """
    from app.models.bid_project import BidProject

    doc = db.query(CompanyDocument).filter(
        CompanyDocument.id == doc_id,
        CompanyDocument.owner_id == current_user.id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="资料不存在或无权限")

    if scope not in ("company", "project"):
        raise HTTPException(status_code=400, detail="scope 必须是 company 或 project")
    if scope == "project":
        if project_id is None:
            raise HTTPException(status_code=400, detail="项目级资料必须绑定 project_id")
        proj = db.query(BidProject).filter(
            BidProject.id == project_id,
            BidProject.owner_id == current_user.id,
        ).first()
        if not proj:
            raise HTTPException(status_code=404, detail="目标项目不存在或无权限")
        doc.project_id = project_id
    else:
        doc.project_id = None
    doc.scope = scope
    db.commit()

    # 同步向量库归属（内存 + Milvus），变更后检索过滤立即按新归属生效
    from app.services.vector_store import vector_store_service
    vector_store_service.update_doc_scope(doc_id, scope, doc.project_id)

    return {
        "id": doc_id,
        "scope": scope,
        "project_id": doc.project_id,
        "success": True,
    }


# ---------------------------------------------------------------------------
# 4) 获取企业资料详情（含文件信息与内容预览）
# ---------------------------------------------------------------------------
@router.get("/company-documents/{doc_id}/detail", response_model=dict)
def get_company_document_detail(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取企业资料的详细信息，包括文件元数据和内容预览"""
    doc = db.query(CompanyDocument).filter(
        CompanyDocument.id == doc_id,
        CompanyDocument.owner_id == current_user.id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="资料不存在或无权限")

    import os
    file_path = doc.file_path
    file_size = 0
    content_preview = ""
    file_type = doc.file_type or ""

    if os.path.exists(file_path):
        file_size = os.path.getsize(file_path)

        # 读取文件内容预览（最多 5000 字符）
        try:
            if file_type == "txt":
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read(5000)
                    content_preview = content
            elif file_type == "docx":
                try:
                    import docx as docx_lib
                    document = docx_lib.Document(file_path)
                    paragraphs = [p.text for p in document.paragraphs[:50] if p.text.strip()]
                    content_preview = "\n".join(paragraphs)[:5000]
                except ImportError:
                    content_preview = "[需要安装 python-docx 以预览 DOCX 文件内容]"
            elif file_type == "pdf":
                try:
                    import PyPDF2
                    with open(file_path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        preview_pages = min(3, len(reader.pages))
                        for i in range(preview_pages):
                            text = reader.pages[i].extract_text() or ""
                            content_preview += text + "\n"
                        content_preview = content_preview[:5000]
                except ImportError:
                    content_preview = "[需要安装 PyPDF2 以预览 PDF 文件内容]"
            else:
                # 尝试以文本方式读取
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content_preview = f.read(5000)
                except Exception:
                    content_preview = "[此文件类型暂不支持内容预览]"
        except Exception as e:
            content_preview = f"[文件预览失败: {str(e)}]"

    # 获取向量切片统计
    from app.services.vector_store import vector_store_service
    stats = vector_store_service.get_stats()
    doc_vectors = [v for v in vector_store_service._vectors
                   if v.get("metadata", {}).get("doc_id") == doc_id]

    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_type": file_type,
        "file_size": file_size,
        "file_size_display": _format_file_size(file_size),
        "category": doc.category,
        "tags": doc.tags,
        "status": doc.status,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "error_message": doc.error_message,
        "vector_count": len(doc_vectors),
        "content_preview": content_preview,
        "content_preview_length": len(content_preview),
    }


def _format_file_size(size_bytes: int) -> str:
    """格式化文件大小为人类可读格式"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ---------------------------------------------------------------------------
# 5) 检索相关企业资料片段（成员D生成草稿时调用）
# ---------------------------------------------------------------------------
@router.post("/retrieval/search", response_model=list[RetrievedChunk])
def retrieval_search(
    req: RetrievalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    给定查询文本，返回最相关的企业资料片段（含来源文件名/段落/相似度）。
    project_id 不传则全库检索。
    """
    # 鉴权：指定 project_id 时必须归属当前用户
    if req.project_id is not None:
        from app.models.bid_project import BidProject
        if not db.query(BidProject).filter(
            BidProject.id == req.project_id, BidProject.owner_id == current_user.id
        ).first():
            raise HTTPException(status_code=403, detail="无权检索该项目资料")

    svc = RetrievalService()
    try:
        chunks = svc.search(
            query=req.query, project_id=req.project_id, top_k=req.top_k
        )
    except Exception as e:  # noqa: BLE001
        # 检索失败降级为空结果，不抛 500（符合"Milvus/检索失败 → 降级"硬约束）
        import logging
        logging.getLogger(__name__).warning("[retrieval] 检索失败，降级返回空列表: %s", e)
        return []
    return chunks
