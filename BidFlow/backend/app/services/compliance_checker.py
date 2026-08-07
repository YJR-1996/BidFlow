"""确定性的投标响应合规规则，不依赖数据库或模型服务。"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RequirementSnapshot:
    requirement_id: int
    content: str
    priority: str
    response_content: str
    source_refs: list[Any]
    status: str
    # L14：最新一次比对分析中此未匹配（match_analysis_details.has_match=false）。
    # 用于判定「有 source_refs 但比对已无资料」→ 引用可能失效，单独风险。
    # 默认 False 保持向后兼容（不带此字段的旧调用方行为不变）。
    match_unmatched: bool = False


@dataclass(frozen=True)
class ComplianceIssue:
    requirement_id: int
    rule_code: str
    level: str
    description: str
    suggestion: str


class ComplianceChecker:
    """将规则判定与后续的数据库持久化分离，方便单元测试和重复核查。"""

    COMPLETED_STATUSES = {
            "completed", "已完成",
            "approved", "已通过", "reviewed",
        }

    def check(self, requirements: list[RequirementSnapshot]) -> list[ComplianceIssue]:
        issues: list[ComplianceIssue] = []
        for item in requirements:
            content = item.response_content.strip()
            p0_incomplete = item.priority == "P0" and item.status not in self.COMPLETED_STATUSES
            if p0_incomplete:
                if not item.source_refs:
                    # P0 + 无可引用资料：真正瓶颈是资料而非响应内容。
                    # 文案必须引导「先上传资料」，否则用户会困惑"为什么未匹配还报响应缺失"。
                    issues.append(self._issue(item, "P0_SOURCE_MISSING", "high",
                        "P0 资料缺失", "上传相关企业资质、案例或技术资料后重新生成。"))
                else:
                    # P0 + 资料齐但响应未完成：引导补响应内容
                    issues.append(self._issue(item, "P0_RESPONSE_MISSING", "high",
                        "P0 响应项尚未完成", "补充响应内容并完成审核。"))
            if not content and not p0_incomplete:
                issues.append(self._issue(item, "RESPONSE_CONTENT_EMPTY", "medium", "响应内容为空", "补充可审核的响应内容。"))
            elif not item.source_refs:
                issues.append(self._issue(item, "RESPONSE_SOURCE_MISSING", "medium", "响应内容缺少企业资料来源", "补充可追溯的企业资料引用。"))
            if item.status in ("needs_manual", "需要人工补充"):
                issues.append(self._issue(item, "MANUAL_MATERIAL_REQUIRED", "medium", "资料不足，需要人工补充", "上传相关资质、案例或技术资料。"))
            # L14：响应已有 source_refs 但当前比对分析显示未匹配（has_match=false），
            # 意味着引用指向的资料可能已删除/不再可检索 → 引用失效风险。
            # 仅在响应看起来「已通过」时触发：pending_review/needs_manual 会被前面的 P0_RESPONSE_MISSING / MANUAL 覆盖。
            # level 按需求优先级动态：P0 → high（资格类否决项被无效引用等同被否决），其他 → medium。
            elif (
                item.match_unmatched
                and item.source_refs
                and item.status in self.COMPLETED_STATUSES
            ):
                stale_level = "high" if item.priority == "P0" else "medium"
                issues.append(self._issue(item, "RESPONSE_SOURCE_STALE", stale_level,
                    "响应引用资料可能失效", "企业资料库中未检索到此引用的资料，建议上传新材料后重新生成。"))
        return self._deduplicate(issues)

    @staticmethod
    def _issue(item: RequirementSnapshot, code: str, level: str, description: str, suggestion: str) -> ComplianceIssue:
        return ComplianceIssue(item.requirement_id, code, level, description, suggestion)

    @staticmethod
    def _deduplicate(issues: list[ComplianceIssue]) -> list[ComplianceIssue]:
        unique: dict[tuple[int, str], ComplianceIssue] = {}
        for issue in issues:
            unique[(issue.requirement_id, issue.rule_code)] = issue
        return list(unique.values())
