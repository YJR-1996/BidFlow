"""响应草稿路由 - AI 生成、获取、更新"""

import json
import threading
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.bid_project import BidProject
from app.models.requirement import Requirement
from app.models.response import Response as BidResponse
from app.models.compliance_issue import ComplianceIssue
from app.schemas.common import ApiResponse
from app.schemas.response import DraftResponseRequest, UpdateResponseRequest, ResponseResponse, DraftResponsePayload
from app.api.deps import get_current_user, get_project_or_404
from app.core.exceptions import NotFoundException, BusinessException

router = APIRouter()

# ------------------------------------------------------------------
# 比对分析异步任务（解决 30s 超时：同步串行 19 条 LLM 比对需 100s+）
# 内存字典 + 后台线程，模式与 batch_task_service 一致
# ------------------------------------------------------------------
_MATCH_TASKS: dict = {}
_MATCH_LOCK = threading.Lock()
_MATCH_RETENTION_HOURS = 6


def _start_match_task(project_id: int, owner_id: str) -> str:
    """启动比对分析后台任务，立即返回 task_id。"""
    task_id = f"match_{uuid.uuid4().hex[:12]}"
    with _MATCH_LOCK:
        _MATCH_TASKS[task_id] = {
            "task_id": task_id,
            "project_id": project_id,
            "owner_id": owner_id,
            "status": "running",   # running / completed / failed
            "started_at": datetime.utcnow().isoformat(),
            "finished_at": None,
            "error": None,
            "result": None,
        }
    thread = threading.Thread(
        target=_run_match_task,
        args=(task_id, project_id, owner_id),
        daemon=True,
        name=f"match-{task_id}",
    )
    thread.start()
    return task_id


def _get_match_task(task_id: str) -> Optional[dict]:
    """查询任务状态（线程安全快照 + 惰性 GC）。"""
    with _MATCH_LOCK:
        _gc_match_tasks()
        task = _MATCH_TASKS.get(task_id)
        if task is None:
            return None
        return dict(task)  # result 是已序列化的 dict，浅拷贝够用


def _gc_match_tasks() -> None:
    """清理超时保留期的已完成任务，防止内存无界增长。"""
    if not _MATCH_TASKS:
        return
    from datetime import timedelta
    deadline = datetime.utcnow() - timedelta(hours=_MATCH_RETENTION_HOURS)
    expired = [
        tid for tid, t in _MATCH_TASKS.items()
        if t.get("status") in ("completed", "failed")
        and t.get("finished_at")
        and _parse_match_iso(t["finished_at"]) < deadline
    ]
    for tid in expired:
        del _MATCH_TASKS[tid]


def _parse_match_iso(s: str):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime(1970, 1, 1)


def _run_match_task(task_id: str, project_id: int, owner_id: str) -> None:
    """后台线程：自建 DB Session，同步计算并持久化比对结果。"""
    # 延迟导入避免循环依赖
    from app.db.session import _SyncSessionLocal
    from app.models.match_analysis import MatchAnalysisRun

    db = _SyncSessionLocal()
    try:
        result = _compute_match_results(project_id, db)
        run = _persist_match_run(db, project_id, owner_id, result)
        db.commit()
        db.refresh(run)
        serialized = _serialize_run(run)
        with _MATCH_LOCK:
            _MATCH_TASKS[task_id]["status"] = "completed"
            _MATCH_TASKS[task_id]["result"] = serialized
            _MATCH_TASKS[task_id]["finished_at"] = datetime.utcnow().isoformat()
    except Exception as e:
        db.rollback()
        with _MATCH_LOCK:
            _MATCH_TASKS[task_id]["status"] = "failed"
            _MATCH_TASKS[task_id]["error"] = str(e)
            _MATCH_TASKS[task_id]["finished_at"] = datetime.utcnow().isoformat()
        import logging
        logging.getLogger(__name__).exception("[match-task] %s failed: %s", task_id, e)
    finally:
        db.close()


@router.get("/projects/{project_id}/match-analysis")
def analyze_requirement_matches(
    project_id: int,
    force: bool = Query(False, description="是否强制重新计算；默认复用上次结果"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分析项目需求与企业资料的匹配情况（LLM 语义缺口分析 + 关键词降级）

    持久化策略：
    - force=false 时，复用该项目最新一次 MatchAnalysisRun 的结果（避免重复计算）
    - force=true 时，实时比对并写入新的 MatchAnalysisRun
    """
    from app.models.match_analysis import MatchAnalysisRun, MatchAnalysisDetail

    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    # 复用最近一次结果（避免重算）
    if not force:
        latest = db.query(MatchAnalysisRun).filter(
            MatchAnalysisRun.project_id == project_id
        ).order_by(MatchAnalysisRun.created_at.desc()).first()
        if latest:
            return ApiResponse(data=_serialize_run(latest))

    # 短路：项目无需求时直接返回空 summary，不启动异步任务
    # （0 需求不需要 LLM 比对，启动任务只会让前端轮询空转）
    req_count = db.query(Requirement).filter(
        Requirement.project_id == project_id
    ).count()
    if req_count == 0:
        return ApiResponse(data={
            "summary": {"total": 0, "matched": 0, "unmatched": 0, "match_rate": 0.0},
            "matches": [],
        })

    # 无历史结果：启动异步后台任务，立即返回 task_id（同步串行需 100s+ 会触发前端 30s 超时）
    task_id = _start_match_task(project_id, current_user.id)
    return ApiResponse(data={
        "task_id": task_id,
        "status": "running",
        "summary": None,
        "matches": [],
    })


@router.get("/projects/{project_id}/match-analysis/status")
def get_match_analysis_status(
    project_id: int,
    task_id: str = Query(..., description="比对分析任务 ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """轮询比对分析后台任务状态。completed 时附带完整结果。"""
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    task = _get_match_task(task_id)
    if task is None or task.get("project_id") != project_id:
        raise NotFoundException(message="比对分析任务不存在")

    payload = {
        "task_id": task["task_id"],
        "status": task["status"],
        "error": task.get("error"),
    }
    if task.get("result") is not None:
        payload.update(task["result"])
    return ApiResponse(data=payload)


@router.post("/projects/{project_id}/match-analysis/run")
def run_match_analysis(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """强制重新执行比对分析（用户主动触发按钮），异步执行避免 30s 超时。"""
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    # 0 需求短路：避免启动空任务（前端会显示「正在比对...」长时间转圈）
    if db.query(Requirement).filter(
        Requirement.project_id == project_id
    ).count() == 0:
        return ApiResponse(data={
            "summary": {"total": 0, "matched": 0, "unmatched": 0, "match_rate": 0.0},
            "matches": [],
        })

    task_id = _start_match_task(project_id, current_user.id)
    return ApiResponse(data={
        "task_id": task_id,
        "status": "running",
        "summary": None,
        "matches": [],
    })


# ------------------------------------------------------------------
# 比对分析辅助函数：纯计算 / 持久化 / 序列化
# ------------------------------------------------------------------

def _compute_match_results(project_id: int, db: Session) -> dict:
    """实时比对需求与资料，返回 {summary, matches}。不写库。"""
    from app.services.vector_store import vector_store_service
    from app.services.retrieval_service import retrieval_service

    requirements = db.query(Requirement).filter(
        Requirement.project_id == project_id
    ).all()

    if not requirements:
        return {
            "summary": {"total": 0, "matched": 0, "unmatched": 0, "match_rate": 0.0},
            "matches": [],
        }

    matches = []
    matched_count = 0

    for req in requirements:
        existing_resp = db.query(BidResponse).filter(
            BidResponse.requirement_id == req.id
        ).order_by(BidResponse.id.desc()).first()

        # --- 优先使用 LLM 语义比对 ---
        try:
            match_result = vector_store_service.match_requirement_to_materials(
                requirement={
                    "id": req.id,
                    "content": req.content or "",
                    "category": req.category or "",
                    "priority": req.priority or "",
                },
                project_id=project_id,
                top_k=5,
            )
            has_match = match_result.coverage != "missing"
            if has_match:
                matched_count += 1

            # 修复：未匹配时清空 sources/count，避免与 has_match 字段矛盾
            # （LLM 可能返回 confidence=0 的 evidence 但 coverage=missing，必须一致）
            if has_match:
                evidence_list = match_result.evidence or []
                matched_sources = [
                    {
                        "filename": e.get("source_ref", "未知来源"),
                        "score": round(match_result.confidence, 2),
                        "content_preview": e.get("quote", "")[:80],
                    }
                    for e in evidence_list[:2]
                ]
            else:
                evidence_list = []
                matched_sources = []

            matches.append({
                "requirement_id": req.id,
                "content": req.content[:100] if req.content else "",
                "category": req.category,
                "priority": req.priority,
                "status": req.status,
                "has_match": has_match,
                "match_count": len(evidence_list),
                "match_score": round(match_result.confidence, 2) if has_match else 0.0,
                "matched_sources": matched_sources,
                "has_response": existing_resp is not None,
                "response_status": existing_resp.status if existing_resp else None,
                "coverage": match_result.coverage,
                "gap": match_result.gap,
                "confidence": round(match_result.confidence, 2),
                "pending_review": match_result.pending_review,
            })
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "match_requirement_to_materials failed for req %s, fallback to retrieval: %s",
                req.id, e,
            )
            try:
                sources = retrieval_service.search(
                    query=req.content or "",
                    project_id=project_id,
                    top_k=3,
                )
            except Exception:
                sources = []

            has_match = len(sources) > 0
            if has_match:
                matched_count += 1

            matches.append({
                "requirement_id": req.id,
                "content": req.content[:100] if req.content else "",
                "category": req.category,
                "priority": req.priority,
                "status": req.status,
                "has_match": has_match,
                "match_count": len(sources),
                "match_score": sources[0].get("score", 0) if sources else 0,
                "matched_sources": [
                    {
                        "filename": s.get("filename", "未知文件"),
                        "score": s.get("score", 0),
                        "content_preview": s.get("content", "")[:80],
                    }
                    for s in sources[:2]
                ],
                "has_response": existing_resp is not None,
                "response_status": existing_resp.status if existing_resp else None,
                "coverage": "partial" if has_match else "missing",
                "gap": None if has_match else "LLM 比对不可用，基于关键词匹配",
                "confidence": sources[0].get("score", 0) if sources else 0,
                "pending_review": False,
            })

    total = len(requirements)
    return {
        "summary": {
            "total": total,
            "matched": matched_count,
            "unmatched": total - matched_count,
            "match_rate": round(matched_count / total * 100, 1) if total > 0 else 0.0,
        },
        "matches": matches,
    }


def _persist_match_run(db: Session, project_id: int, triggered_by: str, result: dict):
    """把比对结果写入 match_analysis_runs + match_analysis_details，返回 ORM 实例。

    仅做 add，不 commit —— 由调用方负责事务。
    """
    from app.models.match_analysis import MatchAnalysisRun, MatchAnalysisDetail

    summary = result["summary"]
    run = MatchAnalysisRun(
        project_id=project_id,
        triggered_by=triggered_by,
        total=summary["total"],
        matched=summary["matched"],
        unmatched=summary["unmatched"],
        match_rate=summary["match_rate"],
    )
    db.add(run)
    db.flush()  # 拿到 run.id 用于 detail 关联

    for m in result["matches"]:
        detail = MatchAnalysisDetail(
            run_id=run.id,
            requirement_id=m["requirement_id"],
            content=m.get("content", ""),
            category=m.get("category"),
            priority=m.get("priority"),
            req_status=m.get("status"),
            has_match=m.get("has_match", False),
            match_count=m.get("match_count", 0),
            match_score=m.get("match_score", 0.0),
            matched_sources=json.dumps(m.get("matched_sources") or [], ensure_ascii=False),
            coverage=m.get("coverage"),
            gap=m.get("gap"),
            confidence=m.get("confidence", 0.0),
            pending_review=m.get("pending_review", False),
            has_response=m.get("has_response", False),
            response_status=m.get("response_status"),
        )
        db.add(detail)

    return run


def _serialize_run(run) -> dict:
    """把 MatchAnalysisRun ORM 实例序列化为前端期望的 {summary, matches, last_analyzed_at}。"""
    matches = []
    for d in (run.details or []):
        try:
            sources = json.loads(d.matched_sources) if d.matched_sources else []
        except Exception:
            sources = []
        matches.append({
            "requirement_id": d.requirement_id,
            "content": d.content,
            "category": d.category,
            "priority": d.priority,
            "status": d.req_status,
            "has_match": bool(d.has_match),
            "match_count": d.match_count,
            "match_score": d.match_score,
            "matched_sources": sources,
            "has_response": bool(d.has_response),
            "response_status": d.response_status,
            "coverage": d.coverage,
            "gap": d.gap,
            "confidence": d.confidence,
            "pending_review": bool(d.pending_review),
        })
    return {
        "summary": {
            "total": run.total,
            "matched": run.matched,
            "unmatched": run.unmatched,
            "match_rate": run.match_rate,
        },
        "matches": matches,
        "last_analyzed_at": run.created_at.isoformat() if run.created_at else None,
        "run_id": run.id,
    }


@router.post("/projects/{project_id}/batch-generate")
def batch_generate_responses(
    project_id: int,
    requirement_ids: list[int] = Query(None, description="可选：仅处理指定需求 ID 列表"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """为项目未生成响应的需求批量生成AI响应（异步任务，立即返回 task_id）

    - requirement_ids 为空 → 全项目（仅已匹配的未响应需求）
    - requirement_ids 非空 → 仅处理列表内的需求（校验归属项目）
    解决前端 30s 超时硬墙：改为「立即返回 task_id → 前端轮询 batch-status」。
    """
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    # 仅取「已匹配」需求：避免为无资料匹配的需求调 LLM 浪费时间
    # （已匹配 = match-analysis 显示 has_match=true 的需求）
    from app.services.retrieval_service import retrieval_service

    requirements = db.query(Requirement).filter(
        Requirement.project_id == project_id
    ).all()

    if not requirements:
        raise BusinessException(message="该项目暂无需求项")

    # 指定 ids 时校验归属项目并只处理这些
    id_set = set(requirement_ids or [])
    if id_set:
        valid_ids = {r.id for r in requirements}
        unknown = id_set - valid_ids
        if unknown:
            raise NotFoundException(message=f"需求不存在或不属于该项目: {sorted(unknown)[:5]}")
        requirements = [r for r in requirements if r.id in id_set]

    matched_ids: list[int] = []
    for req in requirements:
        # 已有响应的跳过（取最新一条）
        existing = db.query(BidResponse).filter(
            BidResponse.requirement_id == req.id
        ).order_by(BidResponse.id.desc()).first()
        if existing and (existing.ai_content or existing.edited_content):
            continue
        # 检查是否「已匹配」
        try:
            # H3：预筛只需判断"有无资料"，跳过 LLM 精排（rerank=False），
            # 避免每条需求一次串行 LLM 调用把异步化拖回超时
            sources = retrieval_service.search(
                query=req.content or "",
                project_id=project_id,
                top_k=1,
                rerank=False,
            )
            if sources:
                matched_ids.append(req.id)
        except Exception:
            # 检索失败时仍纳入处理（_process_one 会降级为 needs_manual）
            matched_ids.append(req.id)

    if not matched_ids:
        return ApiResponse(data={
            "task_id": None,
            "status": "completed",
            "total": 0,
            "processed": 0,
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "items": [],
            "message": "没有待处理的已匹配需求",
        })

    # 启动后台任务，立即返回 task_id
    from app.services.batch_task_service import batch_task_service
    task_id = batch_task_service.start_batch(
        project_id=project_id,
        requirement_ids=matched_ids,
        owner_id=str(current_user.id),
    )

    return ApiResponse(data={
        "task_id": task_id,
        "status": "running",
        "total": len(matched_ids),
        "message": "批量生成任务已启动，请轮询 /batch-status 查询进度",
    })


@router.get("/projects/{project_id}/batch-status/{task_id}")
def get_batch_status(
    project_id: int,
    task_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询批量生成任务进度（前端每 2s 轮询）"""
    # 校验项目归属
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    from app.services.batch_task_service import batch_task_service
    status = batch_task_service.get_status(task_id)
    if not status:
        raise NotFoundException(message="任务不存在或已过期")

    # 安全校验：任务必须属于当前项目
    if status.get("project_id") != project_id:
        raise NotFoundException(message="任务不存在或无权限")

    return ApiResponse(data=status)


@router.post("/{requirement_id}/response/generate", response_model=ApiResponse[DraftResponsePayload])
def generate_response_draft(
    requirement_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    force: bool = Query(False, description="强制重新生成：跳过「已存在草稿」拦截，重新调用 LLM 覆盖旧稿"),
):
    """为指定需求项生成 AI 响应草稿。

    force=False（默认）：幂等——已有草稿直接返回旧稿（「AI 生成」入口）。
    force=True：忽略已有草稿，重新检索 + 重新生成，并清空旧 edited_content
    （「重新生成」入口专用，避免 edited_content 优先级导致新稿永不显示）。
    """
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise NotFoundException(message="需求项不存在")

    project = db.query(BidProject).filter(
        BidProject.id == req.project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="需求项不存在或无权限")

    # 先检查已有草稿（取最新一条）
    existing = db.query(BidResponse).filter(
        BidResponse.requirement_id == requirement_id
    ).order_by(BidResponse.id.desc()).first()

    # 幂等保护：仅非强制模式生效。force=True 时必须放行，
    # 否则「重新生成」按钮会被「已存在草稿」拦截误伤（表现为点了没反应/卡 loading）。
    if not force and existing and (existing.ai_content or existing.edited_content):
        return ApiResponse(data=DraftResponsePayload(
            content=existing.edited_content or existing.ai_content or "",
            source_refs=[],
            status=existing.status,
            message="已存在草稿，无需重新生成",
        ))

    # 尝试检索相关企业资料
    try:
        from app.services.retrieval_service import retrieval_service
        from app.core.config import settings

        sources = retrieval_service.search(
            query=req.content,
            project_id=project.id,
            top_k=5,
        )
        source_dicts = list(sources) if sources else []
    except Exception:
        # 如果检索失败，使用空 sources
        source_dicts = []

    if not source_dicts:
        # 没有可引用的资料，直接返回人工提示
        payload = DraftResponsePayload(
            content="待人工补充：未检索到可引用的企业资料。",
            source_refs=[],
            status="needs_manual",
            message="缺少可引用资料",
        )
        # Upsert：如已有响应（即使无内容），则更新
        if existing:
            existing.ai_content = payload.content
            existing.status = payload.status
            # 关键：无资料时必须清空 source_refs 残留。否则合规扫描 snapshot 看到旧资料
            # 会误判为「资料齐 + 响应空」（P0_RESPONSE_MISSING），应报「P0 资料缺失」。
            existing.source_refs = json.dumps([], ensure_ascii=False)
            if force:
                existing.edited_content = None  # 新稿取代旧稿，避免 edited_content 优先返回旧内容
        else:
            resp = BidResponse(
                requirement_id=requirement_id,
                ai_content=payload.content,
                status=payload.status,
            )
            db.add(resp)
        # 回写需求状态为"待评审"
        req.status = "待评审"
        db.add(req)
        db.commit()
        return ApiResponse(data=payload)

    # 调用 LLM 生成草稿（如未配置 API Key 则使用默认模板）
    try:
        from app.core.config import settings
        from app.services.llm_client import OpenAIChatClient
        from app.services.response_generation_service import ResponseGenerationService

        llm_client = OpenAIChatClient(
            api_key=settings.DASHSCOPE_API_KEY,
            model=settings.LLM_MODEL_NAME,
        )
        gen_service = ResponseGenerationService(llm_client)
        result = gen_service.generate(
            requirement={"content": req.content or "", "category": req.category or ""},
            sources=source_dicts,
        )
        content = result.content
        status = result.status
        message = result.message
    except Exception:
        # LLM 不可用时使用基于模板的默认响应
        content = (
            f"根据招标文件要求，我方完全响应该条款。\n\n"
            f"需求内容：{req.content}\n\n"
            f"具体方案：\n"
            f"1. 资质方面：我方具备符合要求的全部资质证明\n"
            f"2. 技术方面：采用行业领先的技术方案\n"
            f"3. 商务方面：报价合理，条款响应无偏差\n"
            f"4. 资料来源：已检索到 {len(source_dicts)} 条可引用企业资料"
        )
        status = "pending_review"
        message = "草稿已生成（默认模板），等待人工审核"

    payload = DraftResponsePayload(
        content=content,
        source_refs=source_dicts,
        status=status,
        message=message,
    )
    # Upsert：如已有响应（即使无内容），则更新；否则新建
    if existing:
        existing.ai_content = content
        existing.status = status
        existing.source_refs = json.dumps(source_dicts, ensure_ascii=False)
        if force:
            existing.edited_content = None  # 强制重新生成：清掉旧编辑，避免返回值仍命中旧稿
    else:
        resp = BidResponse(
            requirement_id=requirement_id,
            ai_content=content,
            source_refs=json.dumps(source_dicts, ensure_ascii=False),
            status=status,
        )
        db.add(resp)
    # 回写需求状态为"待评审"
    req.status = "待评审"
    db.add(req)
    db.commit()

    return ApiResponse(data=payload)


@router.get("/{requirement_id}/response", response_model=ApiResponse[DraftResponsePayload])
def get_response_draft(
    requirement_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定需求项的响应草稿（只读，与 PATCH 返回结构一致便于前端复用解析）"""
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise NotFoundException(message="需求项不存在")

    project = db.query(BidProject).filter(
        BidProject.id == req.project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="需求项不存在或无权限")

    resp = db.query(BidResponse).filter(
        BidResponse.requirement_id == requirement_id
    ).order_by(BidResponse.id.desc()).first()

    if not resp:
        raise NotFoundException(message="暂无响应草稿，请先生成")

    # 解析 source_refs（与 generate_response_draft 保持一致：str → list）
    try:
        source_refs = json.loads(resp.source_refs) if resp.source_refs else []
    except Exception:
        source_refs = []

    return ApiResponse(data=DraftResponsePayload(
        content=resp.edited_content or resp.ai_content or "",
        source_refs=source_refs,
        status=resp.status or "",
        message="加载成功",
    ))


@router.patch("/{requirement_id}/response", response_model=ApiResponse[DraftResponsePayload])
def update_response_draft(
    requirement_id: int,
    request: UpdateResponseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新响应草稿（编辑内容或审核状态）"""
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise NotFoundException(message="需求项不存在")

    project = db.query(BidProject).filter(
        BidProject.id == req.project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="需求项不存在或无权限")

    resp = db.query(BidResponse).filter(
        BidResponse.requirement_id == requirement_id
    ).order_by(BidResponse.id.desc()).first()

    if not resp:
        raise NotFoundException(message="暂无响应草稿")

    if request.edited_content is not None:
        resp.edited_content = request.edited_content.strip()
    if request.status is not None:
        resp.status = request.status
        # 主从联动：审核通过 → 需求"已完成"；驳回 → 回"待评审"（供强制重新生成闭环）
        # 修复：此前只更新 BidResponse.status，Requirement.status 一直停留在"待评审"，
        # 导致统计页"已通过 0/N"与列表"已生成"严重不一致
        if request.status == "approved":
            req.status = "已完成"
        elif request.status == "rejected":
            req.status = "待评审"
        # 方案 A：项目状态自动流转（需求全完成 → 审核中；有未完成 → 回退准备中）
        from app.services.project_status import sync_project_status
        sync_project_status(db, req.project_id)

    db.commit()
    db.refresh(resp)

    return ApiResponse(data=DraftResponsePayload(
        content=resp.edited_content or resp.ai_content or "",
        source_refs=[],
        status=resp.status,
        message="草稿已保存",
    ))


@router.post("/projects/{project_id}/realign", response_model=ApiResponse[dict])
def realign_requirements(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """闭环 A：重算需求-资料匹配（幂等）。

    重新对齐项目所有需求与企业资料的检索匹配，返回 matched/unmatched 统计。
    未匹配需求需回退到节点⑤「上传企业资料」补充后再次 realign。
    """
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    from app.services.retrieval_service import retrieval_service

    requirements = db.query(Requirement).filter(
        Requirement.project_id == project_id
    ).all()

    matched = 0
    for req in requirements:
        try:
            srcs = retrieval_service.search(
                query=req.content or "",
                project_id=project_id,
                top_k=1,
            )
        except Exception:
            srcs = []
        if srcs:
            matched += 1

    total = len(requirements)
    unmatched = total - matched
    msg = (
        "资料已齐全。"
        if unmatched == 0
        else "已重新对齐；未匹配请回「上传企业资料」补充后再次 realign。"
    )
    return ApiResponse(data={
        "total": total,
        "matched": matched,
        "unmatched": unmatched,
        "message": msg,
    })


@router.post("/projects/{project_id}/remediate", response_model=ApiResponse[dict])
def remediate_issues(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """闭环 B：按 rule_code 映射未处理 issue 为补救动作。

    映射规则：
    - RESPONSE_SOURCE_MISSING / MANUAL_MATERIAL_REQUIRED → upload_materials（引导上传企业资料）
    - P0_RESPONSE_MISSING / RESPONSE_CONTENT_EMPTY → regenerate（调 batch_task_service 重新生成）
    - 其他 → manual_review（人工处理）

    仅对 status="未处理" 的 issue 生成动作，所有动作留痕至 remediation_actions 表。
    """
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    issues = db.query(ComplianceIssue).filter(
        ComplianceIssue.project_id == project_id,
        ComplianceIssue.status == "未处理",
    ).all()

    if not issues:
        return ApiResponse(data={
            "message": "无未处理风险，无需补救。",
            "plan": [],
            "regenerate_task_id": None,
        })

    from app.models.remediation_action import RemediationAction
    from app.services.batch_task_service import batch_task_service

    plan = []
    regen_req_ids = []

    # 预取需求内容（AI 修复建议需要知道"缺的是哪条需求的资料"）
    from app.models.requirement import Requirement as RequirementModel
    req_content_map = {}
    if issues:
        req_ids = list({i.requirement_id for i in issues if i.requirement_id})
        if req_ids:
            for r in db.query(RequirementModel).filter(RequirementModel.id.in_(req_ids)).all():
                req_content_map[r.id] = (r.content or "").strip().replace("\n", " ")[:40]

    # M1：幂等保护——已存在同 (project_id, issue_id) 的补救动作则跳过重建，
    # 避免重复触发重新生成、重复堆积留痕记录
    existing_actions = {
        (a.project_id, a.issue_id)
        for a in db.query(RemediationAction).filter(
            RemediationAction.project_id == project_id,
            RemediationAction.issue_id.in_([i.id for i in issues]),
        ).all()
    }

    for iss in issues:
        if (project_id, iss.id) in existing_actions:
            continue  # 已补救过，跳过
        code = iss.rule_code or ""
        req_content = req_content_map.get(iss.requirement_id, "")
        if code in ("RESPONSE_SOURCE_MISSING", "MANUAL_MATERIAL_REQUIRED", "P0_SOURCE_MISSING"):
            action, stage = "upload_materials", "节点⑤"
            detail = (
                f"请为需求「{req_content or iss.requirement_id}」上传可引用的企业资料："
                "资质证书、类似项目案例、技术方案等（支持 PDF/Word，上传后点击重新生成）。"
            )
        elif code in ("P0_RESPONSE_MISSING", "RESPONSE_CONTENT_EMPTY"):
            action, stage = "regenerate", "节点⑨"
            detail = (
                f"需求「{req_content or iss.requirement_id}」响应内容缺失/未完成，"
                "已加入重新生成队列；完成后请审核并更新审核状态。"
            )
            if iss.requirement_id:
                regen_req_ids.append(iss.requirement_id)
        else:
            action, stage = "manual_review", "人工"
            detail = (
                f"需求「{req_content or iss.requirement_id}」存在未处理风险"
                f"（{iss.description or iss.rule_code}），请人工复核处理。"
            )

        db.add(RemediationAction(
            project_id=project_id,
            issue_id=iss.id,
            requirement_id=iss.requirement_id,
            action=action,
            target_stage=stage,
            detail=detail,
        ))

        plan.append({
            "issue_id": iss.id,
            "rule_code": code,
            "action": action,
            "target_stage": stage,
            "detail": detail,
        })

    # 触发重新生成（如有需要）
    task_id = None
    if regen_req_ids:
        task_id = batch_task_service.start_batch(
            project_id=project_id,
            requirement_ids=regen_req_ids,
            owner_id=str(current_user.id),
        )

    db.commit()

    return ApiResponse(data={
        "message": "已生成补救计划；缺资料类回上传企业资料，内容缺失类已触发重新生成。",
        "plan": plan,
        "regenerate_task_id": task_id,
    })
