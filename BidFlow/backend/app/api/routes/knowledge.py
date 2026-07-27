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
from app.schemas.company_document import (
    CompanyDocumentOut,
    RetrievalRequest,
    RetrievedChunk,
)
from app.services.company_material_service import CompanyMaterialService
from app.services.retrieval_service import RetrievalService

# 所有企业资料/检索相关接口统一前缀 /api
router = APIRouter(prefix="/api", tags=["company-materials"])


# ---------------------------------------------------------------------------
# 1) 上传企业资料并向量化入库
# ---------------------------------------------------------------------------
@router.post("/company-documents", response_model=dict)
async def upload_company_document(
    file: UploadFile = File(..., description="企业资料文件(TXT/PDF/DOCX)"),
    project_id: int = Form(None, description="归属投标项目id，可选"),
    owner_id: int = Form(None, description="上传者id，可选"),
    db: Session = Depends(get_db),
):
    """
    上传企业资质/案例/产品资料等 -> 解析 -> 切分 -> Embedding -> 写入 Chroma。
    返回资料 id、文件名、处理状态与切片数量。
    """
    svc = CompanyMaterialService()
    try:
        result = await svc.upload_and_index(
            db=db, file=file, project_id=project_id, owner_id=owner_id
        )
    except Exception as e:  # noqa: BLE001
        # 上传链路不应直接 500 崩溃，给出可读错误
        raise HTTPException(status_code=500, detail=f"资料入库失败: {e}")
    return result


# ---------------------------------------------------------------------------
# 2) 列出企业资料
# ---------------------------------------------------------------------------
@router.get("/company-documents", response_model=list[CompanyDocumentOut])
def list_company_documents(
    project_id: int = None,
    db: Session = Depends(get_db),
):
    """列出已上传资料；可附 project_id 只列出该项目资料。"""
    svc = CompanyMaterialService()
    return svc.list_documents(db=db, project_id=project_id)


# ---------------------------------------------------------------------------
# 3) 删除企业资料（含向量）
# ---------------------------------------------------------------------------
@router.delete("/company-documents/{doc_id}", response_model=dict)
def delete_company_document(doc_id: int, db: Session = Depends(get_db)):
    """删除某条资料记录，并同步删除 Chroma 中该资料的全部片段。"""
    svc = CompanyMaterialService()
    ok = svc.delete_document(db=db, doc_id=doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="资料不存在")
    return {"deleted": doc_id, "success": True}


# ---------------------------------------------------------------------------
# 4) 检索相关企业资料片段（成员D生成草稿时调用）
# ---------------------------------------------------------------------------
@router.post("/retrieval/search", response_model=list[RetrievedChunk])
def retrieval_search(req: RetrievalRequest, db: Session = Depends(get_db)):
    """
    给定查询文本，返回最相关的企业资料片段（含来源文件名/段落/相似度）。
    project_id 不传则全库检索。
    """
    svc = RetrievalService()
    try:
        chunks = svc.search(
            query=req.query, project_id=req.project_id, top_k=req.top_k
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"检索失败: {e}")
    return chunks
