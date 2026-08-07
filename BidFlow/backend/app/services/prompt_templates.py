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


def build_aux_requirement_messages(
    requirements: list[dict[str, str]],
    max_items: int = 10,
) -> list[dict[str, str]]:
    """基于已解析的招标需求，构建 LLM 辅助需求生成的 Prompt

    Args:
        requirements: 已解析的需求列表，每项含 content/category/priority
        max_items: 最多生成条数

    Returns:
        OpenAI 兼容的 messages 列表
    """
    req_text = "\n".join(
        f"[{r.get('priority', 'P2')}][{r.get('category', '其他')}] {r.get('content', '')}"
        for r in requirements
    )
    return [
        {
            "role": "system",
            "content": (
                "你是招投标专家助手。你的任务是基于已抽取的招标需求，合理派生/补全辅助需求项。\n"
                "可派生的范围仅包括：\n"
                "  1. 隐性合规点（如：虽然招标未明确要求，但行业惯例需具备的资质/许可证）\n"
                "  2. 常见投标易漏项（如：投标保证金、履约保函、人员证书有效期）\n"
                "  3. 资格衍生要求（如：法人资格、近三年无重大违法记录、财务审计报告）\n"
                "  4. 商务补全项（如：交货期、付款条件、质保期、售后服务）\n"
                "  5. 技术补全项（如：性能参数、标准规范、环境条件）\n\n"
                "严格约束：\n"
                "- 仅基于输入需求做合理派生，不得臆造与招标无关的条目\n"
                "- 不得与输入需求完全重复，应有增值价值\n"
                "- category 仅可使用：资格/商务/技术/评分/其他\n"
                "- priority 仅可使用：P0/P1/P2\n"
                f"- 最多生成 {max_items} 条\n\n"
                "输出严格使用 JSON 格式，结构为：\n"
                '{"requirements": [{"content": "需求描述", "category": "分类", "priority": "优先级", "risk_level": "低/中/高"}]}\n'
                "若无法合理派生，返回 {\"requirements\": []}"
            ),
        },
        {
            "role": "user",
            "content": (
                "以下是已从招标文件中抽取的需求项：\n\n"
                f"{req_text}\n\n"
                f"请基于这些需求，派生/补全 {max_items} 条以内的辅助需求项。"
                "这些辅助需求应是投标中容易遗漏或需要重点关注的隐性要求。"
            ),
        },
    ]


def build_semantic_compliance_messages(
    requirement_content: str,
    response_content: str,
    source_refs: list[dict[str, Any]],
    today: str = "",
) -> list[dict[str, str]]:
    """构建语义合规审查的 Prompt messages。

    Args:
        requirement_content: 招标要求原文
        response_content: 投标响应草稿
        source_refs: 引用的企业资料列表
        today: 当前日期（YYYY-MM-DD），用于时间类判断锚点，避免 LLM 无日期参照误判

    Returns:
        OpenAI 兼容的 messages 列表
    """
    refs = "\n".join(
        f"- {s.get('filename', '?')}：{str(s.get('content', ''))[:120]}"
        for s in (source_refs or [])[:5]
    )
    date_line = f"今天是 {today}。" if today else "今天是当前日期。"
    return [
        {
            "role": "system",
            "content": (
                "你是投标语义合规审查专家。识别规则引擎抓不到的语义级风险："
                "与招标要求的实质矛盾、明显无法履行的承诺、关键条款遗漏、"
                "与规范或评分标准不一致。\n"
                f"{date_line}\n"
                "【时间判断以今天为准】'近三年'指今天往前推三年；只有今天之后的年份才算'未来年份'。\n"
                "【以下情况不视为风险】\n"
                "- 承诺提供质量保证/售后服务/技术支持等（除非有明显无法履行的证据）\n"
                "- 提及具体项目名称、业绩案例、时间范围（如 2023-2025 年业绩）本身\n"
                "- 引用了企业资料中的资质、证书、案例（视为有来源支持）\n"
                "只有在与招标要求实质矛盾、明显无法履行、或缺少必要资格时才报风险。\n"
                "每条风险必须给出 confidence（0.0~1.0），低于 0.6 视为不确定，不要输出。\n"
                "只输出 JSON，不作法律结论。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"招标要求：\n{requirement_content}\n\n"
                f"投标响应草稿：\n{response_content}\n\n"
                f"可引用资料：\n{refs}\n\n"
                '请输出 JSON：{"risks":[{"rule_code":"SEMANTIC_xxx","level":"high|medium|low","confidence":0.6,"description":"风险描述","suggestion":"处理建议"}]}'
                '，无风险则 {"risks":[]}'
            ),
        },
    ]


def build_reflexion_evaluate_messages(
    requirement_content: str,
    response_content: str,
    sources: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """构建 Reflexion 质量评估的 Prompt messages。

    让 LLM 判断"响应是否充分满足招标要求"，输出结构化 JSON：
    {"passed": true|false, "feedback": "改进方向", "missing_points": ["遗漏点"]}

    评估标准刻意偏宽（只拦实质不达标），避免过度重写增加成本：
    - 响应是否回应了招标要求的核心要点
    - 关键承诺/资质/数值是否能在引用资料中找到支撑（而非编造）
    - 是否明显答非所问或遗漏 P0/P1 关键条款
    """
    evidence = "\n".join(
        f"- {s.get('filename', '未知文件')}（{s.get('source_ref', '未知位置')}）：{str(s.get('content', ''))[:200]}"
        for s in (sources or [])[:8]
    )
    return [
        {
            "role": "system",
            "content": (
                "你是投标响应质量评估员。判断一份响应草稿是否充分满足对应的招标要求。\n"
                "判定标准（偏宽松，只拦实质不达标）：\n"
                "1. 响应是否覆盖招标要求的核心要点（尤其 P0 资格/资质类）；\n"
                "2. 响应中的承诺、资质、数值是否能在引用资料中找到支撑；\n"
                "3. 是否明显答非所问、空白或关键条款整条遗漏。\n"
                "只要实质达标就返回 passed=true；只有明显缺失、答非所问或关键信息无支撑时才返回 passed=false。\n"
                "只输出 JSON，结构为：{\"passed\": true|false, \"feedback\": \"简短改进方向（不超过 80 字）\", \"missing_points\": [\"具体遗漏点\"]}。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"招标要求：\n{requirement_content}\n\n"
                f"投标响应草稿：\n{response_content}\n\n"
                f"可引用资料：\n{evidence}\n\n"
                '请输出评估 JSON。'
            ),
        },
    ]


def build_reflexion_refine_messages(
    requirement_content: str,
    draft_content: str,
    sources: list[dict[str, Any]],
    feedback: str,
    missing_points: list[str],
) -> list[dict[str, str]]:
    """构建 Reflexion 重写 Prompt：基于评估反馈重写响应草稿。"""
    evidence = "\n".join(
        f"- {s.get('filename', '未知文件')}（{s.get('source_ref', '未知位置')}）：{str(s.get('content', ''))[:300]}"
        for s in (sources or [])[:8]
    )
    missing = "\n".join(f"- {p}" for p in (missing_points or [])) or "（无具体遗漏点，按反馈整体优化）"
    return [
        {
            "role": "system",
            "content": (
                "你是企业投标响应助手。你已生成过一版响应草稿，但质量评估认为它不达标。"
                "请根据评估反馈重写响应：补充遗漏的关键点、修正无支撑的内容，"
                "仍只能依据提供的企业资料作答，不得编造企业资质、案例、金额或承诺。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"招标要求：\n{requirement_content}\n\n"
                f"原草稿：\n{draft_content}\n\n"
                f"可引用资料：\n{evidence}\n\n"
                f"评估反馈：{feedback}\n"
                f"遗漏点：\n{missing}\n\n"
                "请输出重写后的完整响应草稿。"
            ),
        },
    ]


def build_project_meta_judge_messages(
    lines: list[str],
    section: str = "",
) -> list[dict[str, str]]:
    """构建「项目元数据 vs 需求条款」LLM 判定 Prompt。

    用于方案乙兜底层：正则快筛无法确定的行（弱命中）交给 LLM 判定。

    Args:
        lines: 待判定的行（弱命中行，含序号前缀）
        section: 所属章节标题（上下文辅助）

    Returns:
        OpenAI 兼容 messages
    """
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(lines))
    ctx = f"（所属章节：{section}）\n" if section else ""
    return [
        {
            "role": "system",
            "content": (
                "你是招标文件结构解析器。判断每一行属于「项目元数据」还是「需求条款」。\n"
                "【项目元数据】描述项目本身的信息：项目名称、项目/招标/采购编号、采购人/招标人/招标单位、"
                "预算金额、投标截止/开标时间等。特征是给出一个值，不构成对投标人的要求。\n"
                "【需求条款】对投标人的约束或要求：资质资格、技术参数、商务条款、交付、报价规则、"
                "评分标准等。特征是含有要求性表述（必须/应/不得/提供/具备…）或描述投标人义务。\n"
                "注意区分：'投标截止：2026-09-15' 是元数据；'投标截止时间不得晚于开标前15日' 是需求条款。\n"
                "只输出 JSON：{\"results\": [{\"index\": 0, \"is_meta\": true, \"field\": \"tender_ref_no|tenderer|budget|deadline|name|null\", \"value\": \"提取的值\", \"confidence\": 0.9}]}，"
                "confidence 为 0~1，不确定时给低分。"
            ),
        },
        {
            "role": "user",
            "content": f"{ctx}待判定行：\n{numbered}\n\n请输出判定 JSON。",
        },
    ]
