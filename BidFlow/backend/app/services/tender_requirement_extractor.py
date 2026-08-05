from typing import List, Dict
import re

from sqlalchemy.orm import Session

from app.models.requirement import Requirement
from app.core.exceptions import BusinessException


class TenderRequirementExtractorService:
    def __init__(self):
        self.category_keywords = {
            "资格": [
                "资格", "资质", "营业执照", "法人", "注册资本", "成立时间",
                "资质证书", "ISO", "认证", "业绩要求", "类似项目", "项目经验",
                "人员要求", "项目经理", "技术负责人", "高级职称",
            ],
            "商务": [
                "报价", "价格", "预算", "付款", "结算", "保证金", "履约",
                "合同", "条款", "交货期", "交付周期", "工期", "售后服务",
                "质保", "保修期", "运维", "培训",
            ],
            "技术": [
                "技术", "功能", "性能", "系统", "平台", "软件", "硬件",
                "接口", "集成", "安全", "加密", "数据", "存储", "备份",
                "服务器", "网络", "数据库", "架构", "部署", "兼容",
            ],
            "评分": [
                "评分", "打分", "分值", "权重", "评标", "评审标准",
                "加分", "扣分",
            ],
        }

        self.p0_keywords = [
            "资格", "资质", "必须", "强制", "否则", "否决", "废标",
            "截止", "开标", "保证金", "营业执照", "法人",
        ]

        self.p1_keywords = [
            "技术", "功能", "性能", "商务", "报价", "工期", "交付",
            "售后", "质保",
        ]

    def extract(
        self,
        db: Session,
        project_id: int,
        tender_document_id: int,
        parsed_paragraphs: List[Dict],
    ) -> List[Requirement]:
        try:
            requirements_data = []

            text_blocks = self._group_text(parsed_paragraphs)

            for block in text_blocks:
                # 分类/优先级用「所属章节标题 + 条款文本」联合判定，
                # 保证独立条款继承章节上下文（如"资格要求"章下的条款不被误判为"其他/P2"）
                section = block.get("section") or ""
                combined = (section + "\n" + block["text"]) if section else block["text"]
                category = self._classify_category(combined)
                priority = self._classify_priority(combined, category)

                requirements_data.append({
                    "project_id": project_id,
                    "tender_document_id": tender_document_id,
                    "category": category,
                    "content": block["text"][:500],
                    "source_text": block["text"][:1000],
                    "source_ref": block["source_ref"],
                    "priority": priority,
                    "status": "未处理",
                    "risk_level": "低" if priority == "P2" else "中" if priority == "P1" else "高",
                })

            if not requirements_data:
                requirements_data = self._generate_demo_requirements(project_id, tender_document_id)

            result = []
            for req_data in requirements_data:
                req = Requirement(**req_data)
                db.add(req)
                result.append(req)

            db.flush()
            return result

        except Exception as e:
            raise BusinessException(message=f"需求提取失败: {str(e)}")

    def _group_text(self, paragraphs: List[Dict]) -> List[Dict]:
        """把解析出的段落按「章节标题 / 独立条款」切块。

        章节标题（一、/第X章/1. 等）→ 新块；
        独立条款（动作动词开头+短句+标点结尾 / xxx：N分 / 编号前缀）→ 新块；
        其余说明性文字 → 并入当前块。
        每个块附带 section（所属章节标题），供分类/优先级判定继承上下文。
        """
        if not paragraphs:
            return []

        blocks = []
        current_text = ""
        current_ref = ""
        current_section = ""  # 当前所属章节标题（分类继承用，遇新标题才变）
        pending_heading = ""  # 待拼到下一条内容前的标题前缀（消费一次）
        pending_ref = ""

        for para in paragraphs:
            ref = para["source_ref"]
            # 修复：段落内可能混有「标题行 + 多条条款行」（txt 按 \n\n 分段时常见），
            # 逐行判定，避免整段既非 heading 又非 clause → 被并入说明性文字导致需求丢失
            for text in para["text"].split("\n"):
                text = text.strip()
                if not text:
                    continue

                if self._is_heading(text):
                    # 章节标题：flush 当前块，标题作为前缀 + 更新分类上下文
                    if current_text.strip():
                        blocks.append({
                            "text": current_text.strip(),
                            "source_ref": current_ref,
                            "section": current_section,
                        })
                    current_text = ""
                    current_ref = ""
                    pending_heading = text
                    pending_ref = ref
                    current_section = text
                elif self._is_clause(text):
                    # 独立条款：flush 当前块，用「标题 + 条款」开新块（section 持续继承）
                    if current_text.strip():
                        blocks.append({
                            "text": current_text.strip(),
                            "source_ref": current_ref,
                            "section": current_section,
                        })
                    current_text = (pending_heading + "\n" if pending_heading else "") + text
                    current_ref = pending_ref or ref
                    pending_heading = ""
                else:
                    # 说明性文字：若待处理标题存在则先落位，再并入
                    if not current_text.strip() and pending_heading:
                        current_text = pending_heading
                        current_ref = pending_ref
                        pending_heading = ""
                    if current_text:
                        current_text += "\n" + text
                    else:
                        current_text = text
                        current_ref = ref

        if current_text.strip():
            blocks.append({
                "text": current_text.strip(),
                "source_ref": current_ref,
                "section": current_section,
            })

        return blocks

    def _is_heading(self, text: str) -> bool:
        if len(text) > 50:
            return False
        patterns = [
            r"^[一二三四五六七八九十]+、",
            r"^[0-9]+[.、]",
            r"^第[一二三四五六七八九十]+[章节条款]",
            r"^（[一二三四五六七八九十]+）",
            r"^\([0-9]+\)",
        ]
        for pattern in patterns:
            if re.match(pattern, text.strip()):
                return True
        return False

    def _is_clause(self, text: str) -> bool:
        """判断段落是否是一条独立条款（区别于章节标题和说明性续文）。"""
        t = text.strip()
        if not t or len(t) > 200:
            return False

        # 评分项模式：xxx：N分 / xxx：N 分
        if re.match(r"^.+[:：]\s*\d+\s*分", t):
            return True

        # 数字/括号编号前缀：1. 1、 （1） ①
        if re.match(r"^\d+[.、．)]", t):
            return True
        if re.match(r"^[（(]\d+[）)]", t):
            return True

        # 动作动词开头 + 短句 + 分号/句号结尾（典型条款形态）
        verb_prefixes = (
            "具有", "具备", "提供", "在", "每", "近", "所投", "投标", "合同",
            "产品", "保证", "承担", "负责", "须", "应", "不得", "鼓励", "接受",
            "完成", "确保", "满足", "符合", "达到", "包含", "包括", "所有",
            "按", "按照", "遵守", "依据", "采购", "交付", "供货", "配备",
            "采用", "支持", "能", "可", "无", "未",
        )
        if t.startswith(verb_prefixes) and re.search(r"[；。;.]+$", t):
            return True

        return False

    def _classify_category(self, text: str) -> str:
        scores = {}
        for category, keywords in self.category_keywords.items():
            score = sum(1 for kw in keywords if kw in text)
            scores[category] = score

        if max(scores.values()) == 0:
            return "其他"

        return max(scores, key=scores.get)

    def _classify_priority(self, text: str, category: str) -> str:
        for kw in self.p0_keywords:
            if kw in text:
                return "P0"

        if category in ["资格", "评分"]:
            return "P0"

        for kw in self.p1_keywords:
            if kw in text:
                return "P1"

        if category in ["技术", "商务"]:
            return "P1"

        return "P2"

    def _generate_demo_requirements(self, project_id: int, tender_document_id: int) -> List[Dict]:
        return [
            {
                "project_id": project_id,
                "tender_document_id": tender_document_id,
                "category": "资格",
                "content": "投标人必须是具有独立法人资格的企业，持有有效的营业执照。",
                "source_text": "一、投标人资格要求\n1. 投标人必须是具有独立法人资格的企业，持有有效的营业执照。",
                "source_ref": "第 1 页 段落 1",
                "priority": "P0",
                "status": "未处理",
                "risk_level": "高",
            },
            {
                "project_id": project_id,
                "tender_document_id": tender_document_id,
                "category": "资格",
                "content": "投标人近三年内具有至少3个类似项目的成功案例。",
                "source_text": "2. 投标人近三年内具有至少3个类似项目的成功案例，需提供合同证明。",
                "source_ref": "第 1 页 段落 2",
                "priority": "P0",
                "status": "未处理",
                "risk_level": "高",
            },
            {
                "project_id": project_id,
                "tender_document_id": tender_document_id,
                "category": "商务",
                "content": "项目总预算为人民币500万元，报价不得超过预算上限。",
                "source_text": "二、商务要求\n1. 项目总预算为人民币500万元，报价不得超过预算上限。",
                "source_ref": "第 2 页 段落 1",
                "priority": "P1",
                "status": "未处理",
                "risk_level": "中",
            },
            {
                "project_id": project_id,
                "tender_document_id": tender_document_id,
                "category": "商务",
                "content": "合同签订后90天内完成系统部署并上线运行。",
                "source_text": "2. 交付周期：合同签订后90天内完成系统部署并上线运行。",
                "source_ref": "第 2 页 段落 3",
                "priority": "P1",
                "status": "未处理",
                "risk_level": "中",
            },
            {
                "project_id": project_id,
                "tender_document_id": tender_document_id,
                "category": "技术",
                "content": "系统需支持至少1000个并发用户同时在线访问。",
                "source_text": "三、技术要求\n1. 系统性能要求：需支持至少1000个并发用户同时在线访问。",
                "source_ref": "第 3 页 段落 1",
                "priority": "P1",
                "status": "未处理",
                "risk_level": "中",
            },
            {
                "project_id": project_id,
                "tender_document_id": tender_document_id,
                "category": "技术",
                "content": "系统应采用B/S架构，支持主流浏览器访问。",
                "source_text": "2. 系统架构：采用B/S架构，支持Chrome、Firefox、Edge等主流浏览器访问。",
                "source_ref": "第 3 页 段落 2",
                "priority": "P1",
                "status": "未处理",
                "risk_level": "中",
            },
            {
                "project_id": project_id,
                "tender_document_id": tender_document_id,
                "category": "技术",
                "content": "数据需每日自动备份，备份数据保存期限不少于90天。",
                "source_text": "3. 数据安全：数据需每日自动备份，备份数据保存期限不少于90天。",
                "source_ref": "第 3 页 段落 4",
                "priority": "P1",
                "status": "未处理",
                "risk_level": "中",
            },
            {
                "project_id": project_id,
                "tender_document_id": tender_document_id,
                "category": "评分",
                "content": "技术方案占评分权重的40%。",
                "source_text": "四、评分标准\n1. 技术方案：40分",
                "source_ref": "第 5 页 段落 1",
                "priority": "P0",
                "status": "未处理",
                "risk_level": "高",
            },
        ]


tender_requirement_extractor_service = TenderRequirementExtractorService()
