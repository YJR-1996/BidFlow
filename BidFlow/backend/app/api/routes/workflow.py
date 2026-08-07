import json
import threading
import uuid
from typing import Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.agents.base import WorkflowContext
from app.agents.orchestrator import Orchestrator
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.models.workflow_run import WorkflowRun

router = APIRouter(tags=["Agent编排 (Beta · 实验性)"])


def _orchestrate_background(
    project_id: int,
    run_id: str,
    owner_id: str,
    start_stage: str = "parse",
) -> None:
    """后台线程：执行整个编排流程，支持中断于人工审核。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    sync_url = settings.DATABASE_URL.replace("+aiomysql", "+pymysql")
    local_engine = create_engine(sync_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(local_engine, autocommit=False, expire_on_commit=False)
    session = SessionLocal()

    try:
        run = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if not run:
            return

        ctx_json = json.loads(run.context_json) if run.context_json else {}
        ctx = WorkflowContext(
            project_id=ctx_json.get("project_id", project_id),
            owner_id=ctx_json.get("owner_id", owner_id),
            stages_done=ctx_json.get("stages_done", []),
            requirements=ctx_json.get("requirements", []),
            retrieval_task_id=ctx_json.get("retrieval_task_id"),
            compliance_issues=ctx_json.get("compliance_issues", []),
            human_review_required=ctx_json.get("human_review_required", False),
            review_reason=ctx_json.get("review_reason", ""),
            metadata=ctx_json.get("metadata", {}),
        )

        orchestrator = Orchestrator()
        new_ctx = orchestrator.run(ctx, session, start_stage=start_stage)

        run.current_stage = new_ctx.stages_done[-1] if new_ctx.stages_done else start_stage
        if new_ctx.human_review_required:
            run.status = "awaiting_review"
        else:
            if len(new_ctx.stages_done) >= len(Orchestrator.STAGE_ORDER):
                run.status = "completed"
            else:
                run.status = "running"

        run.context_json = json.dumps({
            "project_id": new_ctx.project_id,
            "owner_id": new_ctx.owner_id,
            "stages_done": new_ctx.stages_done,
            "requirements": new_ctx.requirements,
            "retrieval_task_id": new_ctx.retrieval_task_id,
            "compliance_issues": new_ctx.compliance_issues,
            "human_review_required": new_ctx.human_review_required,
            "review_reason": new_ctx.review_reason,
            "metadata": new_ctx.metadata,
        }, ensure_ascii=False)

        run.updated_at = datetime.utcnow()
        session.commit()

    except Exception as exc:
        # 先回滚，确保上一事务（可能已失效）被清理，随后才能把状态标记为 failed
        try:
            session.rollback()
        except Exception:
            pass
        try:
            run = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if run:
                run.status = "failed"
                session.commit()
        except Exception:
            pass
    finally:
        session.close()
        # 释放本次后台任务自建的连接池，避免每次运行/恢复工作流都泄漏一池连接
        local_engine.dispose()


@router.post("/{project_id}/run-workflow", response_model=Dict[str, Any])
async def run_workflow(
    project_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
    start_stage: str = Query(default="parse", description="要开始的阶段，默认 parse"),
) -> Dict[str, Any]:
    """启动工作流编排（Beta · 实验性）
    
    与主 UI 生成通道并行的实验性编排流水线。
    正式使用请以主 UI（需求列表 → 批量生成响应）为准。
    本编排仅适合自动化测试或无人值守场景。
    
    若出现 high level 合规问题，会自动暂停在 awaiting_review 状态。
    """
    from app.models.bid_project import BidProject

    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    initial_stage = start_stage if start_stage in ["decompose", "rag", "compliance"] else "parse"

    run_id = str(uuid.uuid4())
    initial_context = {
        "project_id": project_id,
        "owner_id": current_user.id,
        "stages_done": [],
        "requirements": [],
        "retrieval_task_id": None,
        "compliance_issues": [],
        "human_review_required": False,
        "review_reason": "",
        "metadata": {},
    }

    run = WorkflowRun(
        id=run_id,
        project_id=project_id,
        current_stage=initial_stage,
        status="running",
        context_json=json.dumps(initial_context, ensure_ascii=False),
        created_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()

    thread = threading.Thread(
        target=_orchestrate_background,
        args=(project_id, run_id, current_user.id, initial_stage),
        daemon=True,
        name=f"workflow-{run_id}",
    )
    thread.start()

    return {"run_id": run_id, "status": "running", "start_stage": initial_stage}


@router.get("/{project_id}/workflow/{run_id}", response_model=Dict[str, Any])
async def get_workflow_status(
    project_id: int,
    run_id: str,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """查询工作流运行状态与上下文摘要。"""
    # 鉴权：校验项目归属当前用户
    from app.models.bid_project import BidProject
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    run = db.query(WorkflowRun).filter(
        WorkflowRun.id == run_id,
        WorkflowRun.project_id == project_id,
    ).first()
    if not run:
        raise NotFoundException(message="工作流记录不存在")

    ctx_json = json.loads(run.context_json) if run.context_json else {}
    return {
        "run_id": run.id,
        "project_id": run.project_id,
        "current_stage": run.current_stage,
        "status": run.status,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "context_summary": {
            "stages_done": ctx_json.get("stages_done", []),
            "has_response": bool(ctx_json.get("retrieval_task_id")),
            "has_compliance_issue": bool(ctx_json.get("compliance_issues")),
            "human_review_required": ctx_json.get("human_review_required", False),
            "review_reason": ctx_json.get("review_reason", ""),
        },
    }


@router.post("/{project_id}/workflow/{run_id}/resume", response_model=Dict[str, Any])
async def resume_workflow(
    project_id: int,
    run_id: str,
    next_stage: str = Query(default="rag", description="下一步要执行的阶段"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """恢复已暂停的工作流（status=="awaiting_review"），从指定阶段继续执行。"""
    from app.models.bid_project import BidProject

    run = db.query(WorkflowRun).filter(
        WorkflowRun.id == run_id,
        WorkflowRun.project_id == project_id,
        WorkflowRun.status == "awaiting_review",
    ).first()
    if not run:
        raise HTTPException(status_code=400, detail="只有在 awaiting_review 状态下才能 resume")

    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    ctx_json = json.loads(run.context_json) if run.context_json else {}
    ctx_json["human_review_required"] = False
    ctx_json["review_reason"] = ""
    run.context_json = json.dumps(ctx_json, ensure_ascii=False)
    run.status = "running"
    db.commit()

    thread = threading.Thread(
        target=_orchestrate_background,
        args=(project_id, run_id, current_user.id, next_stage),
        daemon=True,
        name=f"resume-{run_id}",
    )
    thread.start()

    return {"run_id": run_id, "resumed_at": str(datetime.utcnow()), "next_stage": next_stage}


@router.get("/{project_id}/workflow-runs", response_model=Dict[str, Any])
async def list_workflow_runs(
    project_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """列出项目的所有工作流运行记录。"""
    from app.models.bid_project import BidProject

    # 鉴权：校验项目归属当前用户
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    runs = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.project_id == project_id)
        .order_by(WorkflowRun.created_at.desc())
        .all()
    )

    results = []
    for r in runs:
        ctx_json = json.loads(r.context_json) if r.context_json else {}
        results.append({
            "run_id": r.id,
            "current_stage": r.current_stage,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "stages_done": ctx_json.get("stages_done", []),
            "human_review_required": ctx_json.get("human_review_required", False),
        })

    return {"total": len(results), "runs": results}
