"""对话编排服务 - 将 BidFlow 现有能力封装为可对话调用的 Agent。

架构：
- 会话内存（{project_id}:{owner_id} → 消息列表，滑动窗口 + TTL 清理）
- 工具注册表：把现有业务能力（需求/合规/比对/草稿/补救/核查）封装为 function calling 工具
- LLM 意图路由：qwen-max function calling 选择工具 → 执行 → 回填 → 综合回复
- 无 tools 支持时自动降级为纯文本对话（不中断使用）

设计约束：
- 工具实现复用现有 service / 模型查询，不重复造轮子
- 所有查询只读；写操作（remediate/recheck）返回动作说明，不静默执行高风险动作
"""

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 会话保留：最多 30 条消息，空闲 2 小时清理
_MAX_HISTORY = 30
_SESSION_TTL_SECONDS = 2 * 3600

# 工具执行轮次上限（防止 LLM 死循环调工具）
_MAX_TOOL_ROUNDS = 4


class ChatService:
    """对话编排服务（进程内单例，会话存内存——MVP 方案，重启即清）。"""

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()  # M2：会话 dict 并发读写互斥

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------

    def _session_key(self, project_id: int, owner_id: str) -> str:
        return f"{project_id}:{owner_id}"

    def _get_history(self, project_id: int, owner_id: str) -> List[Dict[str, str]]:
        key = self._session_key(project_id, owner_id)
        now = time.time()
        with self._lock:
            # TTL 过期清理
            expired = [k for k, v in self._sessions.items() if now - v.get("ts", 0) > _SESSION_TTL_SECONDS]
            for k in expired:
                self._sessions.pop(k, None)

            sess = self._sessions.get(key)
            if not sess:
                sess = {"messages": [], "ts": now}
                self._sessions[key] = sess
            sess["ts"] = now
            return sess["messages"]

    def _append(self, project_id: int, owner_id: str, role: str, content: str) -> None:
        history = self._get_history(project_id, owner_id)
        with self._lock:
            history.append({"role": role, "content": content})
            # 滑动窗口：只保留最近 N 条
            if len(history) > _MAX_HISTORY:
                del history[: len(history) - _MAX_HISTORY]

    # ------------------------------------------------------------------
    # 工具定义
    # ------------------------------------------------------------------

    @property
    def tools(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_project_overview",
                    "description": "获取项目整体概览：需求总数、已生成响应数、响应率、合规就绪度。适合回答「项目怎么样」「进展如何」等概括性问题。",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_requirements",
                    "description": "查询项目的需求清单，可按类别(category)、优先级(priority)、状态(status)、关键词(keyword)过滤。适合回答「有哪些需求」「某类需求有多少」等问题。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string", "description": "类别：技术/商务/资质/评分"},
                            "priority": {"type": "string", "description": "优先级：P0/P1/P2"},
                            "status": {"type": "string", "description": "响应状态：editing/review/approved/rejected"},
                            "keyword": {"type": "string", "description": "需求内容关键词"},
                            "limit": {"type": "integer", "description": "返回条数上限，默认 20"},
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_compliance",
                    "description": "获取项目合规报告：核查总项/已通过/待人工审核/风险数，以及高/中/低风险清单。适合回答「有什么风险」「合规怎么样」等问题。",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_match",
                    "description": "获取项目比对分析结果：匹配/未匹配统计与逐条详情（has_match、来源、覆盖率）。适合回答「哪些需求没匹配到资料」「匹配情况如何」等问题。",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_draft_status",
                    "description": "查询指定需求的响应草稿状态（审核状态、内容摘要）。参数 requirement_id 必填。",
                    "parameters": {
                        "type": "object",
                        "properties": {"requirement_id": {"type": "integer", "description": "需求 ID"}},
                        "required": ["requirement_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "recheck_compliance",
                    "description": "重新运行合规规则核查（规则引擎，不含语义 LLM，秒级返回），并返回最新统计与风险清单。用户要求「重新核查」「再检查一遍」时调用。",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "remediate_risks",
                    "description": "为当前项目的未处理风险生成补救计划（缺资料→引导上传，响应缺失→触发重新生成，其余→人工）。用户要求「修复风险」「应用修复建议」「补救」时调用。返回动作清单与统计。",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]

    # ------------------------------------------------------------------
    # 工具实现
    # ------------------------------------------------------------------

    def _exec_tool(self, name: str, arguments: dict, project_id: int, owner_id: str, db) -> str:
        """执行工具，返回给 LLM 的 JSON 字符串结果（截断到 ~3000 字符）。"""
        try:
            payload = self._dispatch(name, arguments, project_id, owner_id, db)
        except Exception as exc:  # 工具失败不能中断对话
            logger.exception("[chat] tool %s failed", name)
            payload = {"error": str(exc)[:200], "hint": "工具执行失败，请告知用户稍后重试"}
        text = json.dumps(payload, ensure_ascii=False, default=str)
        return text[:3000]

    def _dispatch(self, name: str, arguments: dict, project_id: int, owner_id: str, db) -> Dict[str, Any]:
        if name == "get_project_overview":
            return self._tool_overview(project_id, db)
        if name == "query_requirements":
            return self._tool_requirements(arguments, project_id, db)
        if name == "query_compliance":
            return self._tool_compliance(project_id, db)
        if name == "query_match":
            return self._tool_match(project_id, db)
        if name == "get_draft_status":
            return self._tool_draft(arguments, project_id, owner_id, db)
        if name == "recheck_compliance":
            return self._tool_recheck(project_id, owner_id, db)
        if name == "remediate_risks":
            return self._tool_remediate(project_id, owner_id, db)
        return {"error": f"未知工具: {name}"}

    def _tool_overview(self, project_id: int, db) -> Dict[str, Any]:
        from app.models.requirement import Requirement
        from app.models.response import Response as BidResponse

        reqs = db.query(Requirement).filter(Requirement.project_id == project_id).all()
        total = len(reqs)
        resp_ids = set()
        for r in reqs:
            if r.responses:
                resp_ids.add(r.id)
        try:
            from app.services.readiness_service import readiness_service
            rd = readiness_service.calculate(project_id, db)
            readiness = {
                "overall": rd.overall,
                "basis": rd.base_rate,
                "quality": rd.quality_rate,
                "compliance": rd.compliance_rate,
            }
        except Exception as e:  # noqa: BLE001 - 就绪度为增强信息，失败不应阻断概览
            logger.warning("readiness calc failed for project %s: %s", project_id, e)
            readiness = {}
        return {
            "project_id": project_id,
            "total_requirements": total,
            "has_response": len(resp_ids),
            "response_rate": round(len(resp_ids) / total * 100, 1) if total else 0,
            "readiness": readiness,
        }

    def _tool_requirements(self, arguments: dict, project_id: int, db) -> Dict[str, Any]:
        from app.models.requirement import Requirement

        q = db.query(Requirement).filter(Requirement.project_id == project_id)
        if arguments.get("category"):
            q = q.filter(Requirement.category == arguments["category"])
        if arguments.get("priority"):
            q = q.filter(Requirement.priority == arguments["priority"])
        if arguments.get("keyword"):
            q = q.filter(Requirement.content.contains(arguments["keyword"]))
        limit = min(int(arguments.get("limit") or 20), 50)
        items = []
        for r in q.limit(limit).all():
            resp_status = None
            for resp in (r.responses or []):
                if resp.edited_content or resp.ai_content:
                    resp_status = resp.status
                    break
            items.append({
                "id": r.id,
                "category": r.category,
                "priority": r.priority,
                "status": r.status,
                "response_status": resp_status,
                "risk_level": r.risk_level,
                "content": (r.content or "")[:60],
            })
        return {"count": len(items), "items": items}

    def _tool_compliance(self, project_id: int, db) -> Dict[str, Any]:
        from app.models.compliance_issue import ComplianceIssue

        issues = db.query(ComplianceIssue).filter(ComplianceIssue.project_id == project_id).all()
        high = [i for i in issues if i.level == "高"]
        medium = [i for i in issues if i.level == "中"]
        low = [i for i in issues if i.level == "低"]
        pending = [i for i in issues if i.status == "未处理"]
        return {
            "total_issues": len(issues),
            "unresolved": len(pending),
            "by_level": {"high": len(high), "medium": len(medium), "low": len(low)},
            "high_risk_list": [
                {"requirement_id": i.requirement_id, "rule_code": i.rule_code, "description": (i.description or "")[:50]}
                for i in high[:10]
            ],
        }

    def _tool_match(self, project_id: int, db) -> Dict[str, Any]:
        from app.models.match_analysis import MatchAnalysisRun, MatchAnalysisDetail

        run = (
            db.query(MatchAnalysisRun)
            .filter(MatchAnalysisRun.project_id == project_id)
            .order_by(MatchAnalysisRun.id.desc())
            .first()
        )
        if not run:
            return {"has_run": False, "message": "尚未执行比对分析"}
        details = (
            db.query(MatchAnalysisDetail)
            .filter(MatchAnalysisDetail.run_id == run.id)
            .all()
        )
        unmatched = [
            {"requirement_id": d.requirement_id, "coverage": d.coverage, "content": (d.content or "")[:40]}
            for d in details if not d.has_match
        ]
        return {
            "has_run": True,
            "run_id": run.id,
            "total": run.total,
            "matched": run.matched,
            "unmatched": run.unmatched,
            "match_rate": round(run.match_rate, 1),
            "unmatched_list": unmatched[:10],
        }

    def _tool_draft(self, arguments: dict, project_id: int, owner_id: str, db) -> Dict[str, Any]:
        from app.models.requirement import Requirement
        from app.models.response import Response as BidResponse

        req_id = int(arguments.get("requirement_id") or 0)
        req = db.query(Requirement).filter(Requirement.id == req_id, Requirement.project_id == project_id).first()
        if not req:
            return {"error": "需求不存在或无权限"}
        resp = (
            db.query(BidResponse)
            .filter(BidResponse.requirement_id == req_id)
            .order_by(BidResponse.id.desc())
            .first()
        )
        return {
            "requirement_id": req_id,
            "content": (req.content or "")[:60],
            "has_draft": bool(resp and (resp.edited_content or resp.ai_content)),
            "status": resp.status if resp else None,
            "content_preview": ((resp.edited_content or resp.ai_content) or "")[:120] if resp else "",
        }

    def _tool_recheck(self, project_id: int, owner_id: str, db) -> Dict[str, Any]:
        """轻量规则核查（规则引擎，不含语义 LLM，秒级）。复用公共函数 compliance_recheck.recheck_rule_issues。"""
        from app.services.compliance_recheck import recheck_rule_issues
        return recheck_rule_issues(project_id, db)

    def _tool_remediate(self, project_id: int, owner_id: str, db) -> Dict[str, Any]:
        """生成补救计划（与 POST /remediate 同逻辑的精简版，不触发后台批量任务，仅返回动作说明）。"""
        from app.models.compliance_issue import ComplianceIssue
        from app.models.remediation_action import RemediationAction
        from app.models.requirement import Requirement as RequirementModel

        issues = db.query(ComplianceIssue).filter(
            ComplianceIssue.project_id == project_id,
            ComplianceIssue.status == "未处理",
        ).all()
        if not issues:
            return {"message": "无未处理风险，无需补救"}

        req_ids = list({i.requirement_id for i in issues if i.requirement_id})
        req_content_map = {}
        if req_ids:
            for r in db.query(RequirementModel).filter(RequirementModel.id.in_(req_ids)).all():
                req_content_map[r.id] = (r.content or "").strip().replace("\n", " ")[:40]

        plan = []
        for iss in issues:
            code = iss.rule_code or ""
            req_content = req_content_map.get(iss.requirement_id, "")
            if code in ("RESPONSE_SOURCE_MISSING", "MANUAL_MATERIAL_REQUIRED", "P0_SOURCE_MISSING"):
                action, stage = "upload_materials", "节点⑤"
                detail = f"为需求「{req_content or iss.requirement_id}」上传资质/案例/技术资料后重新生成"
            elif code in ("P0_RESPONSE_MISSING", "RESPONSE_CONTENT_EMPTY"):
                action, stage = "regenerate", "节点⑨"
                detail = f"需求「{req_content or iss.requirement_id}」响应缺失，需触发重新生成"
            else:
                action, stage = "manual_review", "人工"
                detail = f"需求「{req_content or iss.requirement_id}」存在未处理风险，需人工复核"
            db.add(RemediationAction(
                project_id=project_id, issue_id=iss.id, requirement_id=iss.requirement_id,
                action=action, target_stage=stage, detail=detail,
            ))
            plan.append({"issue_id": iss.id, "rule_code": code, "action": action, "target_stage": stage})

        db.commit()
        return {
            "total": len(plan),
            "plan": plan,
            "hint": "缺资料类请前往「企业资料库」上传；响应缺失类可在响应清单触发重新生成",
        }

    # ------------------------------------------------------------------
    # 对话主流程
    # ------------------------------------------------------------------

    def chat(self, project_id: int, owner_id: str, user_message: str, db) -> Dict[str, Any]:
        """处理一轮用户消息，返回 {reply, tool_calls_used}。"""
        from app.services.llm_client import OpenAIChatClient, LlmServiceError
        from app.core.config import settings

        self._append(project_id, owner_id, "user", user_message)
        history = self._get_history(project_id, owner_id)

        system_prompt = (
            "你是 BidFlow 投标项目管理系统的 AI 助手。你可以通过工具查询项目的需求、合规风险、"
            "比对分析和响应草稿等实时数据，并据此回答用户问题。回答用中文，简洁直接，"
            "涉及数据时引用实际查询结果；若工具返回空/无数据，如实说明，不要编造。"
            "用户可能询问：项目进展、需求清单、风险情况、未匹配项、响应状态、重新核查、修复建议等。"
        )
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-_MAX_HISTORY:])

        client = OpenAIChatClient(api_key=settings.DASHSCOPE_API_KEY, model=settings.LLM_MODEL_NAME)
        tool_calls_used: List[str] = []
        final_reply: Optional[str] = None

        for _round in range(_MAX_TOOL_ROUNDS):
            try:
                content, tool_calls = client.chat_with_tools(messages, self.tools)
            except LlmServiceError:
                # 模型/端点不支持 tools → 降级纯文本对话
                try:
                    reply = client.chat(messages)
                except LlmServiceError:
                    reply = "抱歉，AI 服务暂时不可用，请稍后再试。"
                self._append(project_id, owner_id, "assistant", reply)
                return {"reply": reply, "tool_calls_used": tool_calls_used, "degraded": True}

            if not tool_calls:
                final_reply = content or "已完成处理，请查看上方数据。"
                break

            # 记录并执行工具调用
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_calls_used.append(name)
                result_text = self._exec_tool(name, args, project_id, owner_id, db)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_text,
                })

        if final_reply is None:
            final_reply = "已完成处理，请查看上方数据。"
        self._append(project_id, owner_id, "assistant", final_reply)
        return {"reply": final_reply, "tool_calls_used": tool_calls_used, "degraded": False}


# 进程内单例
chat_service = ChatService()
