# BidFlow - AI招投标文件智能编制与合规核查平台

面向企业投标团队的 AI 协同平台。系统将招标文件中的关键要求结构化为响应清单，结合企业资质、历史案例与产品资料生成投标响应草稿，并通过规则引擎和大模型辅助发现遗漏、矛盾与风险项。

**MVP 闭环**：上传招标文件 → 解析需求 → 关联企业资料 → 生成响应草稿 → 合规核查 → 导出审查报告

完整项目说明见：[docs/项目完整说明.md](docs/项目完整说明.md)。云服务器部署见：[docs/deployment.md](docs/deployment.md)。

## 技术栈

| 组件 | 技术选型 |
|------|----------|
| 后端框架 | FastAPI (Python 3.10+) |
| 业务数据库 | MySQL (阿里云RDS) |
| 向量数据库 | Milvus (阿里云) |
| LLM | 通义千问 (dashscope SDK) |
| 认证方式 | JWT Token |
| 部署方式 | Docker + Docker Compose |

## 用户角色

- **投标专员**：创建项目、上传文件、编辑响应项
- **技术负责人**：查看需求、补充技术材料、处理待办
- **审核负责人**：发现遗漏与风险，确认交付状态

## 快速开始

### 1. 环境准备

```bash
# 复制环境变量配置
cp .env.example .env

# 编辑 .env 填写真实配置（MySQL、JWT密钥等）
```

### 2. 启动服务

```bash
# 方式一：Docker 一键启动
docker compose up --build

# 方式二：本地开发
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 访问接口文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- 健康检查: http://localhost:8000/api/health

## 接口概览

| 模块 | 前缀 | 负责人 | 说明 |
|------|------|--------|------|
| 认证 | /api/auth/* | A | 注册、登录、当前用户 |
| 项目 | /api/projects/* | B | 投标项目增删改查、统计 |
| 招标文件 | /api/tender-documents/* | B | 文件上传、解析、状态查询、删除 |
| 需求清单 | /api/requirements/* | B | 查看、筛选、人工修正 AI 提取的需求 |
| 企业资料 | /api/company-documents/* | C | 资质/案例/产品资料上传、查看、删除 |
| 检索 | /api/search/* | C | 企业资料语义检索 |
| 草稿生成 | /api/generate/* | D | AI 生成响应草稿、人工编辑、审核 |
| 合规核查 | /api/compliance/* | D | 规则引擎检查风险、报告导出 |

## 数据库模型

| 模型 | 说明 |
|------|------|
| User | 用户（id、username、password_hash、is_active、created_at、updated_at） |
| BidProject | 投标项目（owner_id、项目名称、招标单位、截止日期、状态） |
| TenderDocument | 招标文件（project_id、文件名、存储路径、类型、解析状态） |
| Requirement | 需求项（requirement_id、类别、内容、来源、优先级 P0/P1/P2、状态、负责人） |
| CompanyDocument | 企业资料（owner_id、资料类型、文件名、存储路径、处理状态） |
| Response | 响应草稿（requirement_id、AI 草稿、人工编辑内容、source_refs、状态） |
| ComplianceIssue | 合规风险项（project_id、rule_code、等级 high/medium/low、说明、处理状态） |

## 服务层

| 服务 | 负责人 | 说明 |
|------|--------|------|
| document_parser | B | 统一解析 TXT/PDF/DOCX 三种格式为文本 |
| file_storage | B | 安全保存和删除用户上传的文件 |
| tender_requirement_extractor | B | 将解析文本转换为结构化需求项 |
| company_material_service | C | 企业资料处理全流程（上传→切块→向量化） |
| text_chunker | C | 长文本切分为适合 Embedding 的小文本块 |
| vector_store | C | Chroma 向量写入、检索和删除 |
| retrieval_service | C | 企业资料语义检索入口 |
| response_generation_service | D | AI 生成响应草稿 |
| compliance_checker | D | 规则引擎合规核查 |
| prompt_templates | D | 集中管理所有 LLM 提示词 |
| llm_client | D | 通义千问调用封装 |
| report_service | D | 生成 Markdown 格式审查报告 |

## 认证模块 (模块一)

当前已完成认证模块，包含以下接口：

### 注册
```
POST /api/auth/register
Body: {"username": "string", "password": "string"}
Response: {"id": "uuid", "username": "string", "created_at": "datetime"}
```

### 登录
```
POST /api/auth/login
Body: {"username": "string", "password": "string"}
Response: {"access_token": "string", "token_type": "bearer"}
```

### 当前用户
```
GET /api/auth/me
Headers: Authorization: Bearer <token>
Response: {"id": "uuid", "username": "string", "is_active": true}
```

## 项目结构

```
BidFlow/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 主应用
│   │   ├── core/                    # 核心配置
│   │   │   ├── config.py            # 环境变量管理 (Pydantic Settings)
│   │   │   ├── security.py          # JWT 认证 / 密码哈希
│   │   │   └── exceptions.py        # 自定义异常 / 全局处理器
│   │   ├── db/                      # 数据库
│   │   │   ├── session.py           # 异步 SQLAlchemy 连接
│   │   │   └── base.py              # ORM 基类
│   │   ├── models/                  # SQLAlchemy 模型
│   │   │   ├── user.py
│   │   │   ├── bid_project.py
│   │   │   ├── tender_document.py
│   │   │   ├── requirement.py
│   │   │   ├── company_document.py
│   │   │   ├── response.py
│   │   │   └── compliance_issue.py
│   │   ├── schemas/                 # Pydantic 请求/响应模型
│   │   │   ├── auth.py
│   │   │   ├── common.py
│   │   │   ├── project.py
│   │   │   ├── tender_document.py
│   │   │   ├── requirement.py
│   │   │   ├── company_document.py
│   │   │   ├── response.py
│   │   │   └── compliance.py
│   │   ├── api/                     # API 路由
│   │   │   ├── router.py            # 路由注册入口
│   │   │   ├── deps.py              # 依赖注入 (get_current_user)
│   │   │   └── routes/
│   │   │       ├── auth.py
│   │   │       ├── projects.py
│   │   │       ├── tender_documents.py
│   │   │       ├── requirements.py
│   │   │       ├── company_documents.py
│   │   │       ├── retrieval.py
│   │   │       ├── responses.py
│   │   │       └── compliance.py
│   │   └── services/                # 业务服务层
│   │       ├── document_parser.py
│   │       ├── file_storage.py
│   │       ├── tender_requirement_extractor.py
│   │       ├── company_material_service.py
│   │       ├── text_chunker.py
│   │       ├── vector_store.py
│   │       ├── retrieval_service.py
│   │       ├── response_generation_service.py
│   │       ├── compliance_checker.py
│   │       ├── prompt_templates.py
│   │       ├── llm_client.py
│   │       └── report_service.py
│   ├── tests/
│   │   ├── conftest.py
│   │   └── test_auth.py
│   ├── requirements.txt
│   └── Dockerfile
├── docs/
│   ├── api-contract.md              # 接口契约
│   ├── architecture.md              # 系统架构图
│   ├── data-samples.md              # 数据样例
│   ├── demo-script.md               # 演示脚本
│   └── task-tree.md                 # 任务分解
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

## 开发流程

1. 成员 A：项目初始化、认证、数据库配置、启动服务
2. 成员 B：项目 CRUD、文件上传、文本解析、需求清单
3. 成员 C：企业资料上传、文本切分、向量化、语义检索
4. 成员 D：草稿生成、合规核查、报告导出
5. 前端：接口字段稳定后接入真实数据

## 测试

```bash
cd backend
pytest tests/ -v
```

## 分支规范

- `main`：生产分支
- `feature/xxx`：功能分支
- `bugfix/xxx`：修复分支
- 合并前需通过代码审查和测试
