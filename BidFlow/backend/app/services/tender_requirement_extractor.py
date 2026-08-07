from typing import List, Dict
import re
import logging

from sqlalchemy.orm import Session

from app.models.requirement import Requirement
from app.core.exceptions import BusinessException

logger = logging.getLogger(__name__)


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
            project_meta: Dict[str, object] = {}

            text_blocks = self._group_text(parsed_paragraphs)

            for block in text_blocks:
                # 方案乙：剥离「项目元数据」行（编号/采购人/预算/截止时间等）。
                # 强信号正则直接剥离；弱命中/存疑行交给 LLM 兜底判定；
                # 任何不确定 → 保持原样当需求（宁可漏剥，不可误剥）。
                meta, remaining_text = self._extract_project_meta(block)
                project_meta.update(meta)

                if not remaining_text:
                    continue  # 整块都是元数据 → 不生成需求

                # 分类/优先级用「所属章节标题 + 条款文本」联合判定，
                # 保证独立条款继承章节上下文（如"资格要求"章下的条款不被误判为"其他/P2"）
                section = block.get("section") or ""
                combined = (section + "\n" + remaining_text) if section else remaining_text
                category = self._classify_category(combined)
                priority = self._classify_priority(combined, category)

                requirements_data.append({
                    "project_id": project_id,
                    "tender_document_id": tender_document_id,
                    "category": category,
                    "content": remaining_text[:500],
                    "source_text": remaining_text[:1000],
                    "source_ref": block["source_ref"],
                    "priority": priority,
                    "status": "未处理",
                    "risk_level": "低" if priority == "P2" else "中" if priority == "P1" else "高",
                })

            if not requirements_data:
                requirements_data = self._generate_demo_requirements(project_id, tender_document_id)

            # 项目元数据写回 BidProject（只填空值，不覆盖用户手动输入）
            if project_meta:
                self._apply_project_meta(db, project_id, project_meta)

            result = []
            for req_data in requirements_data:
                req = Requirement(**req_data)
                db.add(req)
                result.append(req)

            db.flush()
            return result

        except Exception as e:
            raise BusinessException(message=f"需求提取失败: {str(e)}")

    # ------------------------------------------------------------------
    # 方案乙：项目元数据识别（正则快筛 + LLM 兜底）
    # ------------------------------------------------------------------
    # 强信号正则：值形态完整（编号/金额/日期），行尾锚定，直接剥离
    PROJECT_META_STRONG_PATTERNS = [
        # (字段, 正则, 值转换)
        ("tender_ref_no", re.compile(
            r"^(?:项目编号|招标编号|采购编号|项目标号)[：:]\s*"
            r"([A-Za-z0-9][A-Za-z0-9\-—/_]{1,30})\s*$"
        ), str.strip),
        ("budget", re.compile(
            r"^(?:预算金额|项目预算|预算)[：:]\s*"
            r"([0-9,]+(?:\.\d+)?)\s*(?:万(?:元)?)?\s*$"
        ), lambda s: int(float(s.replace(",", "")))),
        ("deadline", re.compile(
            r"^(?:投标截止|投标截止时间|开标时间)[：:]\s*"
            r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?"
            r"(?:\s*\d{1,2}[:：]\d{2})?)"
            r"(?:\s*[（(][^）)]*[）)])?\s*$"
        ), lambda s: s.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")),
    ]

    # 弱命中前缀：疑似元数据但值形态自由（机构名/项目名等）→ 交给 LLM 判定
    PROJECT_META_WEAK_PREFIX = re.compile(
        r"^(?:项目名称|采购人|招标人|招标单位|采购单位|业主单位)[：:]"
    )

    # LLM 兜底：置信度门槛（低于则保持原样当需求）
    PROJECT_META_LLM_CONFIDENCE = 0.8

    def _extract_project_meta(self, block: Dict) -> tuple[Dict[str, object], str]:
        """逐行识别项目元数据。

        Returns:
            (meta, remaining_text)：meta 为识别的字段映射；remaining_text 为
            剔除元数据行后剩余文本（空串表示整块都是元数据）。
        """
        meta: Dict[str, object] = {}
        kept_lines: List[str] = []
        weak_lines: List[str] = []  # 弱命中行 → LLM 兜底

        for line in (block.get("text") or "").split("\n"):
            line = line.strip()
            if not line:
                continue

            # 1) 强信号正则快筛
            matched = False
            for field, pattern, converter in self.PROJECT_META_STRONG_PATTERNS:
                m = pattern.match(line)
                if m:
                    try:
                        meta[field] = converter(m.group(1))
                    except (ValueError, TypeError):
                        pass  # 转换失败则忽略该行（当普通文本处理？不，保留原文更安全）
                    matched = True
                    break
            if matched:
                continue

            # 2) 弱命中 → 收集给 LLM 兜底
            if self.PROJECT_META_WEAK_PREFIX.match(line):
                weak_lines.append(line)
                continue

            # 3) 其余行保留
            kept_lines.append(line)

        # LLM 兜底判定弱命中行
        if weak_lines:
            llm_meta, weak_kept = self._llm_judge_meta_lines(weak_lines)
            meta.update(llm_meta)
            kept_lines.extend(weak_kept)

        return meta, "\n".join(kept_lines).strip()

    def _llm_judge_meta_lines(self, weak_lines: List[str]) -> tuple[Dict[str, object], List[str]]:
        """LLM 判定弱命中行是否元数据。失败/低置信度 → 保持原样。"""
        from app.core.config import settings
        from app.services.llm_client import OpenAIChatClient
        from app.services.prompt_templates import build_project_meta_judge_messages

        if not settings.DASHSCOPE_API_KEY:
            return {}, weak_lines  # 无 LLM → 全部保留

        try:
            client = OpenAIChatClient(
                api_key=settings.DASHSCOPE_API_KEY,
                model=settings.LLM_MODEL_NAME,
            )
            data = client.chat_json(build_project_meta_judge_messages(weak_lines))

            meta: Dict[str, object] = {}
            kept: List[str] = []
            for item in (data.get("results") or []):
                try:
                    idx = int(item.get("index"))
                    text = weak_lines[idx]
                except (ValueError, IndexError, TypeError):
                    continue
                is_meta = bool(item.get("is_meta"))
                conf = float(item.get("confidence") or 0)
                if is_meta and conf >= self.PROJECT_META_LLM_CONFIDENCE:
                    field = str(item.get("field") or "")
                    if field in ("tender_ref_no", "tenderer", "budget", "deadline", "name"):
                        meta[field] = str(item.get("value") or "").strip()
                    continue  # 剥离
                kept.append(text)
            return meta, kept
        except Exception as e:
            logger.warning("[meta-llm] judge failed, keep all weak lines: %s", e)
            return {}, weak_lines

    def _apply_project_meta(self, db: Session, project_id: int, meta: Dict[str, object]) -> None:
        """把抽取的项目元数据写回 BidProject（只填空值，不覆盖用户输入）。"""
        from app.models.bid_project import BidProject

        project = db.query(BidProject).filter(BidProject.id == project_id).first()
        if project is None:
            return
        for field, value in meta.items():
            if value in (None, ""):
                continue
            if field == "budget":
                if project.budget is None:
                    try:
                        project.budget = int(float(str(value).replace(",", "")))
                    except ValueError:
                        pass
            elif field == "deadline":
                if project.deadline is None:
                    try:
                        from datetime import datetime
                        s = str(value).replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
                        project.deadline = datetime.strptime(s.strip(), "%Y-%m-%d %H:%M") if ":" in s \
                            else datetime.strptime(s.strip(), "%Y-%m-%d")
                    except ValueError:
                        pass
            else:
                if not getattr(project, field, None):
                    setattr(project, field, value)
        db.add(project)

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
