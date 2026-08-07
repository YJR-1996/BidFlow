"""batch_task_service 单元测试

聚焦任务管理逻辑（start_batch / get_status / 状态记账 / 降级路径），
通过 mock 隔离 DB 引擎与 LLM 调用，避免依赖外部服务。

不测试 _run_batch 内部的引擎创建（依赖 settings.DATABASE_URL，难以在 SQLite 测试环境复用），
而是直接测试 _process_one（传入 mock session）和状态更新方法。
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.batch_task_service import BatchTaskService


# ---------------------------------------------------------------------------
# 任务生命周期：start_batch / get_status
# ---------------------------------------------------------------------------
class TestTaskLifecycle:
    def test_start_batch_returns_task_id_and_initial_status(self):
        """start_batch 应立即返回 task_id，初始状态为 running，计数器归零"""
        svc = BatchTaskService()
        # 跳过真实线程：patch threading.Thread.start 使其不执行后台逻辑
        with patch("app.services.batch_task_service.threading.Thread"):
            task_id = svc.start_batch(project_id=1, requirement_ids=[10, 11, 12], owner_id="u1")

        assert task_id.startswith("batch_")
        status = svc.get_status(task_id)
        assert status is not None
        assert status["status"] == "running"
        assert status["total"] == 3
        assert status["processed"] == 0
        assert status["succeeded"] == 0
        assert status["skipped"] == 0
        assert status["failed"] == 0
        assert status["items"] == []
        assert status["error"] is None
        assert status["finished_at"] is None

    def test_get_status_returns_none_for_unknown_task(self):
        """未知 task_id 应返回 None"""
        svc = BatchTaskService()
        assert svc.get_status("nonexistent") is None

    def test_get_status_returns_copy_not_reference(self):
        """get_status 应返回浅拷贝，外部修改不影响内部状态"""
        svc = BatchTaskService()
        with patch("app.services.batch_task_service.threading.Thread"):
            task_id = svc.start_batch(project_id=1, requirement_ids=[1], owner_id="u1")

        status = svc.get_status(task_id)
        status["items"].append({"tampered": True})
        status["processed"] = 999

        # 内部状态不应被影响
        fresh = svc.get_status(task_id)
        assert fresh["processed"] == 0
        assert fresh["items"] == []


# ---------------------------------------------------------------------------
# 状态记账：_record_item
# ---------------------------------------------------------------------------
class TestRecordItem:
    def test_skipped_status_increments_skipped_counter(self):
        svc = BatchTaskService()
        with patch("app.services.batch_task_service.threading.Thread"):
            task_id = svc.start_batch(project_id=1, requirement_ids=[1, 2], owner_id="u1")

        svc._record_item(task_id, {"requirement_id": 1, "status": "skipped", "message": "已有响应"})
        status = svc.get_status(task_id)
        assert status["skipped"] == 1
        assert status["processed"] == 1
        assert status["succeeded"] == 0
        assert len(status["items"]) == 1

    def test_needs_manual_status_counts_as_succeeded(self):
        """needs_manual 也算成功落库（有 ai_content），计入 succeeded"""
        svc = BatchTaskService()
        with patch("app.services.batch_task_service.threading.Thread"):
            task_id = svc.start_batch(project_id=1, requirement_ids=[1], owner_id="u1")

        svc._record_item(task_id, {"requirement_id": 1, "status": "needs_manual"})
        status = svc.get_status(task_id)
        assert status["succeeded"] == 1
        assert status["failed"] == 0

    def test_pending_review_status_counts_as_succeeded(self):
        svc = BatchTaskService()
        with patch("app.services.batch_task_service.threading.Thread"):
            task_id = svc.start_batch(project_id=1, requirement_ids=[1], owner_id="u1")

        svc._record_item(task_id, {"requirement_id": 1, "status": "pending_review"})
        assert svc.get_status(task_id)["succeeded"] == 1

    def test_unknown_status_increments_failed(self):
        """未知 status（如 error）计入 failed"""
        svc = BatchTaskService()
        with patch("app.services.batch_task_service.threading.Thread"):
            task_id = svc.start_batch(project_id=1, requirement_ids=[1], owner_id="u1")

        svc._record_item(task_id, {"requirement_id": 1, "status": "error"})
        assert svc.get_status(task_id)["failed"] == 1

    def test_record_item_on_unknown_task_is_noop(self):
        """对未知 task_id 记账应静默无操作"""
        svc = BatchTaskService()
        # 不应抛异常
        svc._record_item("unknown", {"status": "skipped"})
        assert svc.get_status("unknown") is None


# ---------------------------------------------------------------------------
# 完成与失败标记
# ---------------------------------------------------------------------------
class TestMarkCompletedFailed:
    def test_mark_completed_sets_status_and_finished_at(self):
        svc = BatchTaskService()
        with patch("app.services.batch_task_service.threading.Thread"):
            task_id = svc.start_batch(project_id=1, requirement_ids=[1], owner_id="u1")

        svc._mark_completed(task_id)
        status = svc.get_status(task_id)
        assert status["status"] == "completed"
        assert status["finished_at"] is not None

    def test_mark_failed_overrides_completed(self):
        """_mark_failed 应优先于 _mark_completed：先 failed 后 completed 仍保持 failed"""
        svc = BatchTaskService()
        with patch("app.services.batch_task_service.threading.Thread"):
            task_id = svc.start_batch(project_id=1, requirement_ids=[1], owner_id="u1")

        svc._mark_failed(task_id, "DB 连接失败")
        svc._mark_completed(task_id)  # 后续完成标记不应覆盖 failed

        status = svc.get_status(task_id)
        assert status["status"] == "failed"
        assert status["error"] == "DB 连接失败"
        assert status["finished_at"] is not None

    def test_mark_on_unknown_task_is_noop(self):
        svc = BatchTaskService()
        svc._mark_completed("unknown")
        svc._mark_failed("unknown", "err")
        assert svc.get_status("unknown") is None


# ---------------------------------------------------------------------------
# _process_one：单条需求处理（检索 → 生成 → 写库）
# 用 mock session + mock services 隔离外部依赖
# ---------------------------------------------------------------------------
class TestProcessOne:
    def _make_service(self):
        return BatchTaskService()

    def test_requirement_not_found_returns_skipped(self):
        """需求不存在时返回 skipped"""
        svc = self._make_service()
        session = MagicMock()
        # query 链式调用返回 None（需求不存在）
        session.query.return_value.filter.return_value.first.return_value = None

        result = svc._process_one(
            session=session,
            gen_service=MagicMock(),
            retrieval_service=MagicMock(),
            project_id=1,
            requirement_id=999,
        )
        assert result["status"] == "skipped"
        assert result["requirement_id"] == 999

    def test_existing_response_with_content_is_skipped(self):
        """已有响应且含内容时跳过，不调 LLM"""
        svc = self._make_service()
        existing_resp = MagicMock()
        existing_resp.ai_content = "已有内容"
        existing_resp.edited_content = None

        req = MagicMock()
        req.id = 10
        req.content = "需求内容"
        req.category = "技术"

        session = MagicMock()
        # 第一次 query: Requirement → 返回 req
        # 第二次 query: BidResponse → 返回 existing_resp
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = existing_resp
        session.query.return_value.filter.return_value.first.return_value = req

        gen_service = MagicMock()
        result = svc._process_one(
            session=session, gen_service=gen_service,
            retrieval_service=MagicMock(), project_id=1, requirement_id=10,
        )
        assert result["status"] == "skipped"
        gen_service.generate.assert_not_called()

    def test_no_materials_produces_needs_manual_without_llm(self):
        """无检索资料时直接落库 needs_manual，不调 LLM（符合降级硬约束）"""
        svc = self._make_service()
        req = MagicMock()
        req.id = 10
        req.content = "需求"
        req.category = "技术"
        req.status = "未处理"

        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None  # 无已有响应
        session.query.return_value.filter.return_value.first.return_value = req  # 需求存在

        retrieval_service = MagicMock()
        retrieval_service.search.return_value = []  # 无资料

        gen_service = MagicMock()
        result = svc._process_one(
            session=session, gen_service=gen_service,
            retrieval_service=retrieval_service, project_id=1, requirement_id=10,
        )
        assert result["status"] == "needs_manual"
        gen_service.generate.assert_not_called()
        # 需求状态回写为"待评审"
        assert req.status == "待评审"
        # 应新建响应记录
        session.add.assert_called()

    def test_retrieval_failure_degrades_to_needs_manual(self):
        """检索异常时降级为无资料，落库 needs_manual，不抛异常"""
        svc = self._make_service()
        req = MagicMock()
        req.id = 10
        req.content = "需求"
        req.category = "技术"
        req.status = "未处理"

        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        session.query.return_value.filter.return_value.first.return_value = req

        retrieval_service = MagicMock()
        retrieval_service.search.side_effect = Exception("Milvus 不可用")

        gen_service = MagicMock()
        result = svc._process_one(
            session=session, gen_service=gen_service,
            retrieval_service=retrieval_service, project_id=1, requirement_id=10,
        )
        assert result["status"] == "needs_manual"
        gen_service.generate.assert_not_called()

    def test_llm_success_writes_pending_review_and_source_refs(self):
        """LLM 成功时写入 pending_review 状态与 JSON 源引用"""
        svc = self._make_service()
        req = MagicMock()
        req.id = 10
        req.content = "需求"
        req.category = "技术"
        req.status = "未处理"

        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        session.query.return_value.filter.return_value.first.return_value = req

        sources = [{"content": "案例", "filename": "case.pdf", "source_ref": "p2", "score": 0.9}]
        retrieval_service = MagicMock()
        retrieval_service.search.return_value = sources

        gen_result = MagicMock()
        gen_result.status = "pending_review"
        gen_result.content = "生成的响应内容"
        gen_service = MagicMock()
        gen_service.generate.return_value = gen_result

        with patch("app.services.batch_task_service.json.dumps", return_value="[]") as mock_dumps:
            # 关闭 Reflexion 闭环：本测试只验证「生成 + 写库」，避免评估器真调 LLM
            with patch("app.services.batch_task_service.settings.REFLEXION_ENABLED", False):
                result = svc._process_one(
                    session=session, gen_service=gen_service,
                    retrieval_service=retrieval_service, project_id=1, requirement_id=10,
                )

        assert result["status"] == "pending_review"
        gen_service.generate.assert_called_once()
        assert req.status == "待评审"

    def test_llm_failure_degrades_to_needs_manual(self):
        """LLM 抛 LlmServiceError 时降级为 needs_manual，不中断"""
        from app.services.llm_client import LlmServiceError

        svc = self._make_service()
        req = MagicMock()
        req.id = 10
        req.content = "需求"
        req.category = "技术"
        req.status = "未处理"

        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        session.query.return_value.filter.return_value.first.return_value = req

        retrieval_service = MagicMock()
        retrieval_service.search.return_value = [{"content": "x", "filename": "f", "source_ref": "p", "score": 0.9}]

        gen_service = MagicMock()
        gen_service.generate.side_effect = LlmServiceError("LLM 不可用")

        result = svc._process_one(
            session=session, gen_service=gen_service,
            retrieval_service=retrieval_service, project_id=1, requirement_id=10,
        )
        assert result["status"] == "needs_manual"

    def test_existing_empty_response_is_updated_not_duplicated(self):
        """已有空响应占位符时应更新而非新建"""
        svc = self._make_service()
        existing = MagicMock()
        existing.ai_content = None
        existing.edited_content = None
        existing.source_refs = None
        existing.status = "草稿"

        req = MagicMock()
        req.id = 10
        req.content = "需求"
        req.category = "技术"
        req.status = "未处理"

        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = existing
        session.query.return_value.filter.return_value.first.return_value = req

        retrieval_service = MagicMock()
        retrieval_service.search.return_value = []

        svc._process_one(
            session=session, gen_service=MagicMock(),
            retrieval_service=retrieval_service, project_id=1, requirement_id=10,
        )
        # 应更新 existing 的字段
        assert existing.ai_content  # 落库了 needs_manual 文案
        assert existing.status == "needs_manual"
        # 不应新增 Response 对象（session.add 仅用于 req）
        # session.add 会调用两次：req 和（若新建）resp；此处只应 add req
        add_calls = session.add.call_args_list
        # 确认没有新建 BidResponse（仅 add req）
        assert all(c.args[0] is req for c in add_calls)
