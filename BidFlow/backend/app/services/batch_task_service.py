"""批量响应生成任务服务

解决「前端 30s 超时硬墙」与「后端同步串行 RAG + LLM」之间的矛盾：
  - 单条 LLM 最坏 30s × (1+2 重试) = 90s，8 个需求 40~720s
  - 前端 axios 全局 timeout: 30000，第 30 秒必断

方案：内存任务字典 + 后台线程
  - start 接口立即返回 task_id
  - 后台线程自建 DB Session (SessionLocal())，每条生成即 commit，进度可见
  - LLM 失败降级为 needs_manual，不再卡死整批
  - 只处理「已匹配」需求（修语义偏差）
  - 不引入 Celery/Redis（threading + 内存字典，单实例足够）
"""
import json
import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, Optional

from app.core.config import settings
from app.services.llm_client import OpenAIChatClient, LlmServiceError
from app.services.response_generation_service import ResponseGenerationService

logger = logging.getLogger(__name__)


class BatchTaskService:
    """批量任务管理：内存字典 + 后台线程"""

    def __init__(self):
        self._tasks: Dict[str, dict] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def start_batch(
        self,
        project_id: int,
        requirement_ids: list[int],
        owner_id: str,
    ) -> str:
        """启动批量生成任务，立即返回 task_id

        Args:
            project_id: 项目 ID
            requirement_ids: 待处理需求 ID 列表
            owner_id: 任务发起人 ID（用于审计）
        """
        task_id = f"batch_{uuid.uuid4().hex[:12]}"
        total = len(requirement_ids)

        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "project_id": project_id,
                "owner_id": owner_id,
                "status": "running",            # running / completed / failed
                "total": total,
                "processed": 0,
                "succeeded": 0,
                "skipped": 0,
                "failed": 0,
                "items": [],                   # 每条处理结果
                "started_at": datetime.utcnow().isoformat(),
                "finished_at": None,
                "error": None,
            }

        thread = threading.Thread(
            target=self._run_batch,
            args=(task_id, project_id, requirement_ids),
            daemon=True,
            name=f"batch-{task_id}",
        )
        thread.start()
        logger.info(
            "[batch] task started: task_id=%s, project=%d, requirements=%d",
            task_id, project_id, total,
        )
        return task_id

    # 已完成任务的内存保留时长（小时），超过后自动清理，防止内存无界增长
    TASK_RETENTION_HOURS = 6

    def get_status(self, task_id: str) -> Optional[dict]:
        """查询任务状态（线程安全快照）"""
        with self._lock:
            self._gc_finished_tasks()
            task = self._tasks.get(task_id)
            if task is None:
                return None
            # 返回浅拷贝避免外部修改
            return dict(task, items=list(task["items"]))

    def _gc_finished_tasks(self) -> None:
        """清理已结束（completed/failed）且超过保留时长的任务，防止内存泄漏。

        在 get_status 调用时惰性触发，无需额外线程。
        """
        if not self._tasks:
            return
        from datetime import timedelta
        deadline = datetime.utcnow() - timedelta(hours=self.TASK_RETENTION_HOURS)
        expired = [
            tid for tid, t in self._tasks.items()
            if t.get("status") in ("completed", "failed")
            and t.get("finished_at") is not None
            and _parse_iso(t["finished_at"]) < deadline
        ]
        for tid in expired:
            del self._tasks[tid]
        if expired:
            logger.info("[batch] GC removed %d expired tasks", len(expired))

    # ------------------------------------------------------------------
    # 后台线程逻辑
    # ------------------------------------------------------------------
    def _run_batch(self, task_id: str, project_id: int, requirement_ids: list[int]) -> None:
        """后台线程：自建 DB Session，逐条生成"""
        # 延迟导入避免循环依赖
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.models.requirement import Requirement
        from app.models.response import Response as BidResponse
        from app.services.retrieval_service import retrieval_service

        sync_url = settings.DATABASE_URL.replace("+aiomysql", "+pymysql")
        engine = create_engine(sync_url, pool_pre_ping=True)
        SessionLocal = sessionmaker(engine, autocommit=False, expire_on_commit=False)

        # 复用现有 LLM 客户端（同单条生成路径）
        llm_client = OpenAIChatClient(
            api_key=settings.DASHSCOPE_API_KEY,
            model=settings.LLM_MODEL_NAME,
        )
        gen_service = ResponseGenerationService(llm_client)

        session = SessionLocal()
        try:
            for req_id in requirement_ids:
                item_result = self._process_one(
                    session=session,
                    gen_service=gen_service,
                    retrieval_service=retrieval_service,
                    project_id=project_id,
                    requirement_id=req_id,
                )
                # 每条立即 commit，进度可见、断点不丢
                session.commit()
                self._record_item(task_id, item_result)

            # 收尾：轻量重建风险清单（规则引擎，秒级；保留 semantic/已处理 issue）。
            # 让「remediate 触发的批量重生成」与风险报告闭环——重生成完成后风险项随新响应重建，
            # 无需用户再手动点「重新核查」。失败仅告警，不阻断任务状态。
            try:
                from app.services.compliance_recheck import recheck_rule_issues
                recheck_result = recheck_rule_issues(project_id, session)
                self._record_compliance_recheck(task_id, recheck_result)
            except Exception as e:
                logger.warning(
                    "[batch] compliance recheck failed: task_id=%s, project=%d, err=%s",
                    task_id, project_id, e,
                )
        except Exception as e:
            logger.exception("[batch] task crashed: task_id=%s", task_id)
            session.rollback()
            self._mark_failed(task_id, str(e))
        finally:
            session.close()
            engine.dispose()
            self._mark_completed(task_id)

    def _process_one(
        self,
        session,
        gen_service: ResponseGenerationService,
        retrieval_service,
        project_id: int,
        requirement_id: int,
    ) -> dict:
        """处理单条需求：检索 → 生成 → 写库。LLM 失败降级为 needs_manual。
        使用 upsert 模式：如已有响应则更新，否则新建，确保每个需求只有一条响应。
        """
        from app.models.requirement import Requirement
        from app.models.response import Response as BidResponse

        req = session.query(Requirement).filter(Requirement.id == requirement_id).first()
        if not req:
            return {
                "requirement_id": requirement_id,
                "status": "skipped",
                "message": "需求不存在",
            }

        # 查找已有响应（按 id 降序取最新一条）
        existing = session.query(BidResponse).filter(
            BidResponse.requirement_id == req.id
        ).order_by(BidResponse.id.desc()).first()

        # 已有响应且有内容 → 跳过
        if existing and (existing.ai_content or existing.edited_content):
            return {
                "requirement_id": req.id,
                "status": "skipped",
                "message": "已有响应，跳过",
            }

        # 检索相关企业资料
        try:
            sources = retrieval_service.search(
                query=req.content or "",
                project_id=project_id,
                top_k=5,
            )
            source_dicts = list(sources) if sources else []
        except Exception as e:
            logger.warning("[batch] retrieval failed: req_id=%s, err=%s", req.id, e)
            source_dicts = []

        # 准备生成的内容和状态
        ai_content = ""
        status = "needs_manual"
        source_refs_str = ""

        # 无资料 → 直接落库 needs_manual，不调 LLM
        if not source_dicts:
            ai_content = "待人工补充：未检索到可引用的企业资料。"
            status = "needs_manual"
        else:
            # 调 LLM 生成；失败降级不抛异常
            try:
                result = gen_service.generate(
                    requirement={"content": req.content or "", "category": req.category or ""},
                    sources=source_dicts,
                )
                ai_content = result.content
                status = result.status
                source_refs_str = json.dumps(source_dicts, ensure_ascii=False)
            except LlmServiceError as e:
                logger.warning("[batch] LLM failed, degrade to needs_manual: req_id=%s, err=%s", req.id, e)
                ai_content = "待人工补充：AI 服务暂时不可用，请稍后重试或手动填写。"
                status = "needs_manual"
                source_refs_str = json.dumps(source_dicts, ensure_ascii=False)
            except Exception as e:
                logger.exception("[batch] unexpected error: req_id=%s", req.id)
                ai_content = "待人工补充：生成过程中发生异常，请手动填写。"
                status = "needs_manual"

        # ---- Reflexion 质量闭环：生成 → LLM 评估 → 不达标带反馈重写（最多 N 轮）----
        if (
            settings.REFLEXION_ENABLED
            and status == "pending_review"          # 仅对已成功生成的响应做质量门
            and ai_content
        ):
            from app.services.reflexion_evaluator import reflexion_evaluator

            requirement_content = req.content or ""
            for round_idx in range(1, settings.REFLEXION_MAX_ROUNDS):
                verdict = reflexion_evaluator.evaluate(
                    requirement_content=requirement_content,
                    response_content=ai_content,
                    sources=source_dicts,
                )
                if verdict.passed:
                    break
                # 不达标：重写轮扩大检索（top_k 5 → RETRY_TOP_K），给重写更多素材
                logger.info(
                    "[batch][reflexion] round=%d req_id=%s not passed, refining... feedback=%s",
                    round_idx, req.id, verdict.feedback[:80],
                )
                try:
                    if round_idx == 1 and settings.REFLEXION_RETRY_TOP_K > 5:
                        sources = retrieval_service.search(
                            query=requirement_content,
                            project_id=project_id,
                            top_k=settings.REFLEXION_RETRY_TOP_K,
                        )
                        source_dicts = list(sources) if sources else source_dicts
                    refined = reflexion_evaluator.refine(
                        requirement_content=requirement_content,
                        draft_content=ai_content,
                        sources=source_dicts,
                        feedback=verdict.feedback,
                        missing_points=verdict.missing_points,
                    )
                    if refined:
                        ai_content = refined
                        source_refs_str = json.dumps(source_dicts, ensure_ascii=False)
                except Exception as e:
                    logger.warning("[batch][reflexion] refine round=%d failed: %s", round_idx, e)
                    break

        # Upsert：如已有响应记录（无内容的占位符），则更新；否则新建
        if existing:
            existing.ai_content = ai_content
            existing.status = status
            if source_refs_str:
                existing.source_refs = source_refs_str
        else:
            resp = BidResponse(
                requirement_id=req.id,
                ai_content=ai_content,
                source_refs=source_refs_str or None,
                status=status,
            )
            session.add(resp)

        # 回写需求状态为"待评审"，使前端筛选与 Agent 重跑过滤器生效
        req.status = "待评审"
        session.add(req)

        return {
            "requirement_id": req.id,
            "status": status,
            "message": f"响应已{'更新' if existing else '生成'}",
        }

    # ------------------------------------------------------------------
    # 状态更新（线程安全）
    # ------------------------------------------------------------------
    def _record_item(self, task_id: str, item: dict) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task["items"].append(item)
            task["processed"] += 1
            status = item.get("status", "")
            if status == "skipped":
                task["skipped"] += 1
            elif status == "needs_manual":
                # needs_manual 也算成功落库（有 ai_content）
                task["succeeded"] += 1
            elif status in ("pending_review", "draft"):
                task["succeeded"] += 1
            else:
                task["failed"] += 1

    def _record_compliance_recheck(self, task_id: str, result: dict) -> None:
        """把收尾的轻量合规核查结果写回任务快照，前端轮询 batch-status 可感知。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task["compliance_recheck"] = result

    def _mark_completed(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            # 仅当未标记 failed 时才置 completed
            if task["status"] != "failed":
                task["status"] = "completed"
            task["finished_at"] = datetime.utcnow().isoformat()
            logger.info(
                "[batch] task finished: task_id=%s, status=%s, processed=%d/%d, ok=%d, skip=%d, fail=%d",
                task_id, task["status"], task["processed"], task["total"],
                task["succeeded"], task["skipped"], task["failed"],
            )

    def _mark_failed(self, task_id: str, error: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task["status"] = "failed"
            task["error"] = error


# 全局单例
batch_task_service = BatchTaskService()


def _parse_iso(s: str):
    """把 ISO 时间字符串解析为 datetime，失败返回 epoch（立即过期）。"""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime(1970, 1, 1)