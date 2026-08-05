import logging
from datetime import datetime

from app.core.config import settings
from app.services.llm_client import OpenAIChatClient, LlmServiceError
from app.services.prompt_templates import build_semantic_compliance_messages

logger = logging.getLogger(__name__)


class SemanticComplianceAgent:
    """语义合规 Agent：在规则引擎之后用 LLM 检测语义级风险。
    任何 LLM 失败均静默降级为仅规则引擎，不影响主流程。
    """

    # 第 3 层：后处理黑名单——命中这些关键词的语义风险直接丢弃（防 LLM 误报）
    # 覆盖：时间范围、业绩案例、质量承诺等容易被 LLM 过度泛化为"风险"的内容
    #
    # ⚠️ 关键保护：若描述包含「否定/缺失」词（如"未提供""缺少"），说明是真实风险，
    # 即使命中黑名单关键词也不抑制（见 _should_suppress）。
    SUPPRESS_KEYWORDS = [
        "质量保证", "质保", "售后服务", "技术支持",
        "业绩案例", "业绩", "近三年", "时间范围",
        "2023", "2024", "2025", "2026", "2027",
    ]

    # 否定/缺失词：命中即视为真实风险，跳过黑名单抑制
    NEGATION_KEYWORDS = [
        "未提供", "未承诺", "未包含", "未覆盖", "未满足", "未响应", "未完成",
        "缺少", "缺失", "没有", "无法", "不能", "不足", "不满足",
        "待补充", "待完善", "尚未",
    ]

    # 第 4 层：置信度阈值——LLM 不确定（<0.6）的风险不输出
    CONFIDENCE_THRESHOLD = 0.6

    def analyze(
        self,
        requirement_id: int,
        requirement_content: str,
        response_content: str,
        source_refs: list,
    ) -> list[dict]:
        """对单条需求响应进行语义风险分析，返回风险列表。

        Returns:
            list[dict]: 每个风险包含 rule_code, level, description, suggestion。
            失败时返回空列表。
        """
        if not getattr(settings, "SEMANTIC_COMPLIANCE_ENABLED", True):
            return []

        if not response_content or not response_content.strip():
            return []

        if not settings.DASHSCOPE_API_KEY:
            logger.info("[semantic_compliance] DASHSCOPE_API_KEY 未配置，跳过语义分析")
            return []

        try:
            client = OpenAIChatClient(
                api_key=settings.DASHSCOPE_API_KEY,
                model=settings.LLM_MODEL_NAME,
            )
            messages = build_semantic_compliance_messages(
                requirement_content, response_content, source_refs,
                today=datetime.now().strftime("%Y-%m-%d"),
            )
            data = client.chat_json(messages)

            out = []
            for it in (data.get("risks") or []):
                if not isinstance(it, dict):
                    continue
                code = str(it.get("rule_code", "SEMANTIC_UNKNOWN"))
                if not code.startswith("SEMANTIC_"):
                    code = "SEMANTIC_" + code
                level = it.get("level", "medium")
                if level not in ("high", "medium", "low"):
                    level = "medium"
                description = str(it.get("description", ""))

                # 第 4 层：置信度过滤
                try:
                    conf = float(it.get("confidence") or 0.0)
                except (TypeError, ValueError):
                    conf = 0.0
                if conf < self.CONFIDENCE_THRESHOLD:
                    continue

                # 第 3 层：黑名单过滤（防时间/业绩/质保类误报）
                if self._should_suppress(description):
                    continue

                # 第 4 层：等级封顶——语义 Agent 最高只能报 medium，
                # high 只由规则引擎（确定性判罚）产出，保证高风险可信度
                if level == "high":
                    level = "medium"

                out.append({
                    "rule_code": code,
                    "level": level,
                    "description": description,
                    "suggestion": str(it.get("suggestion", "")),
                })
            return out

        except Exception as e:
            logger.warning("[semantic_compliance] LLM 不可用，跳过语义分析：%s", e)
            return []

    def _should_suppress(self, description: str) -> bool:
        """黑名单判定：描述命中关键词则丢弃（防误报）。

        保护规则：若描述包含「否定/缺失」词（未提供/缺少/无法…），
        说明是真风险（如"未提供售后服务方案"），不抑制，保留上报。
        """
        if not description:
            return False
        if any(neg in description for neg in self.NEGATION_KEYWORDS):
            return False
        return any(kw in description for kw in self.SUPPRESS_KEYWORDS)


semantic_compliance_agent = SemanticComplianceAgent()
