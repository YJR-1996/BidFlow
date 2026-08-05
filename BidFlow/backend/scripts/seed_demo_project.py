"""一次性种子脚本：为指定用户创建「标书导出演示项目」用于验收导出功能。

内容（11 条需求，全部已生成响应且审核通过 status=approved）：
- 资格 3 条（P0） / 商务 3 条（P1） / 技术 3 条（P1） / 评分 2 条（P2）
- 每条需求一条 BidResponse：ai_content + edited_content（人工编辑版优先）+ source_refs
- 少量 ComplianceIssue（高/中/低）供合规报告与风险概览展示

幂等：同名项目已存在则删除重建（不影响其他项目）。
用法：python scripts/seed_demo_project.py <username>
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import _SyncSessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.bid_project import BidProject  # noqa: E402
from app.models.requirement import Requirement  # noqa: E402
from app.models.response import Response as BidResponse  # noqa: E402
from app.models.compliance_issue import ComplianceIssue  # noqa: E402

PROJECT_NAME = "标书导出演示项目"

# (需求内容, 类别, 优先级, 风险等级, 响应内容)
DEMO_DATA = [
    ("提供有效的营业执照副本及法人身份证明，投标人须为依法注册的独立法人。", "资格", "P0", "高",
     "我方为依法注册的独立法人，营业执照注册号 9133XXXXXXXXXXXX，注册资本 5000 万元，经营范围覆盖本次采购全部类别，营业执照与法人身份证明见附件。"),
    ("近三年内具有至少 3 个同类项目成功案例，需提供合同与验收证明。", "资格", "P0", "高",
     "我方近三年已完成 5 个同类项目（见业绩表），其中 3 个为同规模智慧园区类项目，均提供合同复印件及验收合格证明，可随时配合核验。"),
    ("具备 ISO9001 质量管理体系认证及 ISO14001 环境管理体系认证。", "资格", "P0", "高",
     "我方已通过 ISO9001:2015 质量管理体系与 ISO14001:2015 环境管理体系认证，认证证书在有效期内，证书编号见附件。"),
    ("项目总预算为人民币 300 万元，报价须包含全部实施费用。", "商务", "P1", "中",
     "我方投标总报价 285 万元，已包含硬件、软件、实施、培训及三年运维全部费用，分项报价明细见投标价格表。"),
    ("合同签订后 60 个日历日内完成全部交付，逾期按日扣款。", "商务", "P1", "中",
     "我方承诺合同签订后 55 个日历日内完成交付，预留 5 天缓冲期，并接受合同约定的逾期扣款条款。"),
    ("提供不少于 3 年的免费质保及 7×24 小时售后服务响应。", "商务", "P1", "中",
     "我方承诺提供 5 年免费质保（超出要求 2 年），售后 7×24 小时响应，4 小时内到场，提供专属服务团队与备件库。"),
    ("系统需支持至少 1000 个并发用户同时在线访问，采用 B/S 架构。", "技术", "P1", "中",
     "我方平台采用微服务 + B/S 架构，经压测支持 5000 并发在线（超出要求 4 倍），提供负载均衡与弹性扩容能力。"),
    ("系统需提供数据加密存储与传输，通过等保三级要求。", "技术", "P1", "中",
     "系统采用 AES-256 加密存储、TLS1.3 加密传输，已通过等保三级测评，提供完整的审计日志与权限管控。"),
    ("平台需开放标准 API 接口，支持与业主现有 OA 系统集成。", "技术", "P1", "中",
     "平台提供 RESTful 标准 API 与 SDK 文档，已与主流 OA/ERP 系统完成对接案例，可开放 50+ 标准接口，支持定制集成。"),
    ("技术方案评分满分 40 分，方案完整性与创新性各占 20 分。", "评分", "P2", "低",
     "我方技术方案完整覆盖需求全部技术点，并引入 AI 智能分析、可视化大屏等创新功能，可提供方案 Demo 现场演示。"),
    ("售后服务方案评分满分 10 分，响应时效与服务网点为评分重点。", "评分", "P2", "低",
     "我方售后方案含 4 小时到场、全国 200+ 服务网点、专属 7×24 热线，响应时效承诺优于评标要求，附服务网点分布图。"),
]

# (rule_code, level, description, suggestion)
DEMO_ISSUES = [
    ("MANUAL_MATERIAL_REQUIRED", "高", "P0 资格类条款引用资料不足：建议补充最新版营业执照扫描件", "上传最新版营业执照后重新核查"),
    ("RESPONSE_CONTENT_EMPTY", "中", "商务类报价条款响应为生成稿，尚未人工复核报价金额", "人工复核报价金额后重新核查"),
    ("SEMANTIC_VALID", "中", "技术方案中 API 接口数量表述建议与需求一一对应核对", "补充接口清单明细后重新核查"),
    ("SEMANTIC_TIME", "低", "质保承诺超出要求的年限部分建议明确费用归属", "在响应中补充费用归属说明"),
]


def seed(username: str):
    db = _SyncSessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"用户不存在: {username}")
            return

        # 幂等：同名项目删除重建
        old = db.query(BidProject).filter(BidProject.name == PROJECT_NAME, BidProject.owner_id == user.id).all()
        for p in old:
            db.query(ComplianceIssue).filter(ComplianceIssue.project_id == p.id).delete()
            db.query(Requirement).filter(Requirement.project_id == p.id).delete()
            db.delete(p)
        db.flush()

        project = BidProject(
            name=PROJECT_NAME,
            owner_id=user.id,
            status="审核中",
            description="自动生成的标书导出验收项目（响应全部审核通过）",
            deadline=datetime.utcnow() + timedelta(days=14),
        )
        db.add(project)
        db.flush()

        for content, category, priority, risk_level, response in DEMO_DATA:
            req = Requirement(
                project_id=project.id,
                content=content,
                category=category,
                priority=priority,
                risk_level=risk_level,
                status="已完成",  # 已审核通过 → 已完成（与统计口径一致）
                source_text=content,
                source_ref="演示条款",
            )
            db.add(req)
            db.flush()

            source_refs = json.dumps([
                {"filename": "企业资质材料.pdf", "source_ref": "第 3 页", "score": 0.92, "content": content[:50]},
                {"filename": "成功案例集.docx", "source_ref": "第 8 页", "score": 0.85, "content": "同类项目实施经验"},
            ], ensure_ascii=False)
            resp = BidResponse(
                requirement_id=req.id,
                ai_content=f"AI 草稿：{response[:60]}……",
                edited_content=response,  # 人工编辑版优先（导出用）
                source_refs=source_refs,
                status="approved",
            )
            db.add(resp)

        for rule_code, level, desc, sugg in DEMO_ISSUES:
            db.add(ComplianceIssue(
                project_id=project.id,
                requirement_id=None,
                rule_code=rule_code,
                level=level,
                description=desc,
                suggestion=sugg,
                status="未处理",
            ))

        db.commit()
        print(f"✅ 已创建演示项目：id={project.id} name={PROJECT_NAME}")
        print(f"   需求 {len(DEMO_DATA)} 条（资格3/商务3/技术3/评分2），响应全部 approved")
        print(f"   合规问题 {len(DEMO_ISSUES)} 条（高1/中2/低1）")
        print(f"   登录账号: {username}")
        print(f"   建议验证：项目详情 → 导出标书（Markdown/PDF）→ 导出合规报告")
    finally:
        db.close()


if __name__ == "__main__":
    seed(sys.argv[1] if len(sys.argv) > 1 else "yjr123")
