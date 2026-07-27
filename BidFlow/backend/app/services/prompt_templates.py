"""成员 D 使用的集中 Prompt 模板。"""

from typing import Any


def build_response_messages(requirement_content: str, sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    evidence = "\n\n".join(
        f"来源：{item.get('filename', '未知文件')}（{item.get('source_ref', '未知位置')}）\n材料：{item.get('content', '')}"
        for item in sources
    )
    return [
        {
            "role": "system",
            "content": "你是企业投标响应助手。只能依据提供的企业资料生成简洁响应。不得编造企业资质、案例、金额、合同或承诺；若资料不足，明确说明待人工补充。",
        },
        {"role": "user", "content": f"招标要求：\n{requirement_content}\n\n可引用企业资料：\n{evidence}\n\n请生成投标响应草稿。"},
    ]


def build_risk_explanation_messages(rule_code: str, description: str, suggestion: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "你是投标审查助手。只能解释已命中的规则，不改变风险等级，不作法律结论。"},
        {"role": "user", "content": f"规则：{rule_code}\n问题：{description}\n默认建议：{suggestion}\n请用一句话说明原因和下一步处理建议。"},
    ]
