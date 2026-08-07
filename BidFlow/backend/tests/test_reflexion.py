"""Reflexion 质量闭环测试

覆盖：
- ReflexionEvaluator.evaluate：通过/不通过/空响应/LLM 失败降级（视为通过）
- ReflexionEvaluator.refine：重写成功/失败（保留原草稿）
- batch_task_service._process_one 闭环：评估通过不再重写；不通过触发重写；
  重写后仍不达标按轮数上限结束；检索 top_k 在重写轮扩大
"""
from unittest.mock import MagicMock, patch

from app.services.batch_task_service import BatchTaskService
from app.services.reflexion_evaluator import ReflexionEvaluator, ReflexionVerdict


def _make_service():
    return BatchTaskService()


def _mock_session(req, existing=None):
    session = MagicMock()
    session.query.return_value.filter.return_value.order_by.return_value.first.return_value = existing
    session.query.return_value.filter.return_value.first.return_value = req
    return session


def _make_req(content="需求", category="技术"):
    req = MagicMock()
    req.id = 10
    req.content = content
    req.category = category
    req.status = "未处理"
    return req


def _make_gen_result(content="响应内容", status="pending_review"):
    r = MagicMock()
    r.content = content
    r.status = status
    return r


# ---------------------------------------------------------------------------
# ReflexionEvaluator.evaluate
# ---------------------------------------------------------------------------
class TestEvaluator:
    def test_empty_response_is_not_passed(self):
        """空响应直接判不通过（不调 LLM）"""
        ev = ReflexionEvaluator(llm_client=None)
        v = ev.evaluate("需求", "   ", [])
        assert v.passed is False

    def test_no_llm_available_passes_through(self):
        """无 LLM 客户端（无 API Key）→ 视为通过，不阻断主流程"""
        ev = ReflexionEvaluator(llm_client=None)
        with patch("app.services.reflexion_evaluator.settings.DASHSCOPE_API_KEY", ""):
            v = ev.evaluate("需求", "正常响应内容", [{"filename": "a.pdf"}])
        assert v.passed is True

    def test_llm_says_passed(self):
        client = MagicMock()
        client.chat_json.return_value = {"passed": True, "feedback": "", "missing_points": []}
        ev = ReflexionEvaluator(llm_client=client)
        v = ev.evaluate("需求", "响应", [])
        assert v.passed is True
        assert v.feedback == ""

    def test_llm_says_not_passed(self):
        client = MagicMock()
        client.chat_json.return_value = {
            "passed": False,
            "feedback": "缺少资质承诺",
            "missing_points": ["未提及营业执照"],
        }
        ev = ReflexionEvaluator(llm_client=client)
        v = ev.evaluate("需求", "响应", [])
        assert v.passed is False
        assert v.feedback == "缺少资质承诺"
        assert v.missing_points == ["未提及营业执照"]

    def test_llm_failure_degrades_to_passed(self):
        """LLM 调用异常 → 视为通过（评估器永不阻断生成链路）"""
        client = MagicMock()
        client.chat_json.side_effect = RuntimeError("LLM down")
        ev = ReflexionEvaluator(llm_client=client)
        v = ev.evaluate("需求", "响应", [])
        assert v.passed is True

    def test_llm_bad_json_degrades_to_passed(self):
        client = MagicMock()
        client.chat_json.return_value = {"unexpected": "shape"}
        ev = ReflexionEvaluator(llm_client=client)
        v = ev.evaluate("需求", "响应", [])
        assert v.passed is True  # passed 缺失默认 True


# ---------------------------------------------------------------------------
# ReflexionEvaluator.refine
# ---------------------------------------------------------------------------
class TestRefine:
    def test_refine_returns_refined_content(self):
        client = MagicMock()
        client.chat.return_value = "  重写后的响应  "
        ev = ReflexionEvaluator(llm_client=client)
        out = ev.refine("需求", "旧草稿", [], "反馈", ["遗漏点"])
        assert out == "重写后的响应"

    def test_refine_failure_returns_none(self):
        client = MagicMock()
        client.chat.side_effect = RuntimeError("down")
        ev = ReflexionEvaluator(llm_client=client)
        assert ev.refine("需求", "旧草稿", [], "反馈", []) is None

    def test_refine_no_llm_returns_none(self):
        ev = ReflexionEvaluator(llm_client=None)
        with patch("app.services.reflexion_evaluator.settings.DASHSCOPE_API_KEY", ""):
            assert ev.refine("需求", "旧草稿", [], "反馈", []) is None


# ---------------------------------------------------------------------------
# batch_task_service._process_one Reflexion 闭环
# ---------------------------------------------------------------------------
class TestBatchReflexion:
    def test_passed_evaluation_no_refine(self):
        """首轮评估通过 → 不再重写，gen_service.generate 只调 1 次"""
        svc = _make_service()
        req = _make_req()
        session = _mock_session(req, existing=None)
        sources = [{"content": "案例", "filename": "case.pdf", "source_ref": "p2", "score": 0.9}]
        retrieval_service = MagicMock()
        retrieval_service.search.return_value = sources
        gen_service = MagicMock()
        gen_service.generate.return_value = _make_gen_result()

        with patch("app.services.batch_task_service.settings.REFLEXION_ENABLED", True):
            with patch("app.services.batch_task_service.settings.REFLEXION_MAX_ROUNDS", 2):
                with patch("app.services.reflexion_evaluator.reflexion_evaluator") as mock_ev:
                    mock_ev.evaluate.return_value = ReflexionVerdict(passed=True)
                    result = svc._process_one(
                        session=session, gen_service=gen_service,
                        retrieval_service=retrieval_service, project_id=1, requirement_id=10,
                    )

        assert result["status"] == "pending_review"
        gen_service.generate.assert_called_once()
        mock_ev.evaluate.assert_called_once()
        mock_ev.refine.assert_not_called()

    def test_failed_evaluation_triggers_refine(self):
        """首轮不达标 → 触发重写，且重写轮检索 top_k 扩大"""
        svc = _make_service()
        req = _make_req()
        session = _mock_session(req, existing=None)
        sources = [{"content": "案例", "filename": "case.pdf", "source_ref": "p2", "score": 0.9}]
        retrieval_service = MagicMock()
        retrieval_service.search.return_value = sources
        gen_service = MagicMock()
        gen_service.generate.return_value = _make_gen_result()

        with patch("app.services.batch_task_service.settings.REFLEXION_ENABLED", True):
            with patch("app.services.batch_task_service.settings.REFLEXION_MAX_ROUNDS", 2):
                with patch("app.services.batch_task_service.settings.REFLEXION_RETRY_TOP_K", 8):
                    with patch("app.services.reflexion_evaluator.reflexion_evaluator") as mock_ev:
                        mock_ev.evaluate.return_value = ReflexionVerdict(
                            passed=False, feedback="缺资质", missing_points=["缺营业执照"],
                        )
                        mock_ev.refine.return_value = "重写后的响应"
                        result = svc._process_one(
                            session=session, gen_service=gen_service,
                            retrieval_service=retrieval_service, project_id=1, requirement_id=10,
                        )

        # 首轮 top_k=5 + 重写轮 top_k=8
        assert retrieval_service.search.call_count == 2
        assert retrieval_service.search.call_args_list[1].kwargs["top_k"] == 8
        # refine 被调用，且内容被重写后的覆盖
        mock_ev.refine.assert_called_once()
        assert result["status"] == "pending_review"
        # 检查写库内容为重写后的响应
        session.add.assert_called()

    def test_max_rounds_bounds_loop(self):
        """重写后仍不达标 → 按轮数上限结束，不无限循环"""
        svc = _make_service()
        req = _make_req()
        session = _mock_session(req, existing=None)
        sources = [{"content": "案例", "filename": "case.pdf", "source_ref": "p2", "score": 0.9}]
        retrieval_service = MagicMock()
        retrieval_service.search.return_value = sources
        gen_service = MagicMock()
        gen_service.generate.return_value = _make_gen_result()

        with patch("app.services.batch_task_service.settings.REFLEXION_ENABLED", True):
            with patch("app.services.batch_task_service.settings.REFLEXION_MAX_ROUNDS", 3):
                with patch("app.services.reflexion_evaluator.reflexion_evaluator") as mock_ev:
                    mock_ev.evaluate.return_value = ReflexionVerdict(
                        passed=False, feedback="仍不达标", missing_points=["缺内容"],
                    )
                    mock_ev.refine.return_value = "重写仍不达标"
                    result = svc._process_one(
                        session=session, gen_service=gen_service,
                        retrieval_service=retrieval_service, project_id=1, requirement_id=10,
                    )

        # MAX_ROUNDS=3 → 最多 2 次重写（round 1、2 各评估一次后仍不过，round 2 结束退出）
        # range(1, 3) = [1, 2] → evaluate 2 次、refine 2 次，绝不无限循环
        assert mock_ev.evaluate.call_count == 2
        assert mock_ev.refine.call_count == 2
        assert result["status"] == "pending_review"

    def test_reflexion_disabled_skips_loop(self):
        """REFLEXION_ENABLED=False → 完全跳过闭环，不调评估器"""
        svc = _make_service()
        req = _make_req()
        session = _mock_session(req, existing=None)
        sources = [{"content": "案例", "filename": "case.pdf", "source_ref": "p2", "score": 0.9}]
        retrieval_service = MagicMock()
        retrieval_service.search.return_value = sources
        gen_service = MagicMock()
        gen_service.generate.return_value = _make_gen_result()

        with patch("app.services.batch_task_service.settings.REFLEXION_ENABLED", False):
            with patch("app.services.reflexion_evaluator.reflexion_evaluator") as mock_ev:
                result = svc._process_one(
                    session=session, gen_service=gen_service,
                    retrieval_service=retrieval_service, project_id=1, requirement_id=10,
                )

        assert result["status"] == "pending_review"
        mock_ev.evaluate.assert_not_called()
        mock_ev.refine.assert_not_called()

    def test_needs_manual_skips_reflexion(self):
        """生成降级为 needs_manual（如无资料）→ 不进 Reflexion 闭环"""
        svc = _make_service()
        req = _make_req()
        session = _mock_session(req, existing=None)
        retrieval_service = MagicMock()
        retrieval_service.search.return_value = []  # 无资料
        gen_service = MagicMock()

        with patch("app.services.batch_task_service.settings.REFLEXION_ENABLED", True):
            with patch("app.services.reflexion_evaluator.reflexion_evaluator") as mock_ev:
                result = svc._process_one(
                    session=session, gen_service=gen_service,
                    retrieval_service=retrieval_service, project_id=1, requirement_id=10,
                )

        assert result["status"] == "needs_manual"
        gen_service.generate.assert_not_called()
        mock_ev.evaluate.assert_not_called()
