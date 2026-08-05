# BidFlow - AI招投标文件智能编制与合规核查平台

面向企业投标团队的 AI 协同平台。系统将招标文件中的关键要求结构化为响应清单，结合企业资质、历史案例与产品资料生成投标响应草稿，并通过规则引擎和大模型辅助发现遗漏、矛盾与风险项。

**MVP 闭环**：上传招标文件 → 解析需求 → 关联企业资料 → 生成响应草稿 → 合规核查 → 导出审查报告

## 技术栈

| 组件 | 技术选型 |
|------|----------|
| 后端框架 | FastAPI (Python 3.11+) |
| 业务数据库 | MySQL (阿里云RDS) |
| 向量数据库 | Milvus (阿里云) |
| LLM | 通义千问 (DashScope SDK) |
| 认证方式 | JWT Token |
| 前端框架 | Vue 3 + Vite |
| 状态管理 | Pinia |
| HTTP客户端 | Axios |
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

# 编辑 .env 填写真实配置（MySQL、Milvus、DashScope API Key 等）
```

### 2. 启动服务

```bash
# 方式一：Docker 一键启动
docker compose up --build

# 方式二：本地开发
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 前端（另一个终端）
cd frontend
npm install
npm run dev
```

### 3. 访问应用

- 前端页面: http://localhost:5173
- 后端 API 文档 (Swagger): http://localhost:8000/docs
- 后端 API 文档 (ReDoc): http://localhost:8000/redoc
- 健康检查: http://localhost:8000/api/health

## 接口概览

| 模块 | 前缀 | 说明 |
|------|------|------|
| 认证 | /api/auth/* | 注册、登录、当前用户 |
| 项目 | /api/projects/* | 投标项目增删改查、统计 |
| 招标文件 | /api/tender-documents/* | 文件上传、解析、状态查询、删除 |
| 需求清单 | /api/requirements/* | 查看、筛选、批量更新状态 |
| 响应草稿 | /api/requirements/* | AI 生成响应草稿、人工编辑、审核 |
| 企业资料 | /api/knowledge/* | 资质/案例/产品资料上传、检索、删除 |
| 合规核查 | /api/compliance/* | 规则引擎检查风险、报告导出 |
| 统计报表 | /api/stats/* | 项目完成度、风险统计 |
| Agent 编排 | /api/projects/*/workflow/* | AI Agent 工作流状态查询 |
| AI 助手 | /api/chat/* | 对话式 AI 助手 |
| 标书导出 | /api/bid-document/* | 合并导出最终标书 |

## 数据库模型

| 模型 | 说明 |
|------|------|
| User | 用户（id、username、password_hash、is_active、created_at、updated_at） |
| BidProject | 投标项目（owner_id、项目名称、招标单位、截止日期、状态） |
| TenderDocument | 招标文件（project_id、文件名、存储路径、类型、解析状态） |
| Requirement | 需求项（content、category、priority P0/P1/P2、status、source、project_id） |
| CompanyDocument | 企业资料（owner_id、资料类型、文件名、存储路径、处理状态、scope、project_id） |
| Response | 响应草稿（requirement_id、AI 草稿、人工编辑内容、source_refs、status） |
| ComplianceIssue | 合规风险项（project_id、requirement_id、rule_code、等级、说明、处理状态） |
| MatchAnalysis | 匹配分析记录（需求项与企业资料的匹配结果） |
| RemediationAction | 整改措施（针对合规风险的整改建议） |
| WorkflowRun | Agent 工作流运行记录 |

## 服务层

| 服务 | 说明 |
|------|------|
| document_parser | 统一解析 TXT/PDF/DOCX 三种格式为文本 |
| file_storage | 安全保存和删除用户上传的文件 |
| tender_requirement_extractor | 将解析文本转换为结构化需求项 |
| company_material_service | 企业资料处理全流程（上传→切块→向量化） |
| text_chunker | 长文本切分为适合 Embedding 的小文本块 |
| vector_store | Milvus 向量写入、检索、删除与 scope 隔离 |
| retrieval_service | 企业资料语义检索入口 |
| response_generation_service | AI 生成响应草稿 |
| compliance_checker | 规则引擎合规核查 |
| semantic_compliance_agent | 语义级合规风险检测（LLM） |
| prompt_templates | 集中管理所有 LLM 提示词 |
| llm_client | 通义千问调用封装（含 Embedding） |
| report_service | 生成 Markdown/PDF 格式审查报告 |
| readiness_service | 项目就绪度（完成率）计算 |
| batch_task_service | 批量异步生成响应草稿 |
| auxiliary_requirement_service | AI 辅助生成补充需求项 |
| reranker | 重排序服务 |

## Agent 编排

| Agent | 说明 |
|-------|------|
| BaseAgent | Agent 基类，定义工作流上下文 |
| RAGAgent | 检索增强生成 Agent |
| ComplianceAgent | 合规检查 Agent |
| ParseAgent | 智能解析 Agent |
| DecomposeAgent | 需求分解 Agent |
| Orchestrator | Agent 编排器 |

## 项目结构

```
BidFlow/
├── backend/                          # 后端代码
│   ├── app/
│   │   ├── main.py                   # FastAPI 主应用入口
│   │   ├── core/                     # 核心配置
│   │   │   ├── config.py             # 环境变量管理 (Pydantic Settings)
│   │   │   ├── security.py           # JWT 认证 / 密码哈希
│   │   │   └── exceptions.py        # 自定义异常 / 全局处理器
│   │   ├── db/                       # 数据库
│   │   │   ├── session.py            # SQLAlchemy 连接管理（同步+异步）
│   │   │   └── base.py               # ORM 基类
│   │   ├── models/                   # SQLAlchemy ORM 模型
│   │   │   ├── user.py
│   │   │   ├── bid_project.py
│   │   │   ├── tender_document.py
│   │   │   ├── requirement.py
│   │   │   ├── company_document.py
│   │   │   ├── response.py
│   │   │   ├── compliance_issue.py
│   │   │   ├── match_analysis.py
│   │   │   ├── remediation_action.py
│   │   │   └── workflow_run.py
│   │   ├── schemas/                  # Pydantic 请求/响应模型
│   │   │   ├── auth.py
│   │   │   ├── common.py
│   │   │   ├── project.py
│   │   │   ├── tender_document.py
│   │   │   ├── requirement.py
│   │   │   ├── company_document.py
│   │   │   ├── response.py
│   │   │   └── compliance.py
│   │   ├── api/                      # API 路由
│   │   │   ├── router.py             # 路由注册入口
│   │   │   ├── deps.py               # 依赖注入 (get_current_user)
│   │   │   └── routes/
│   │   │       ├── auth.py           # 认证接口
│   │   │       ├── projects.py       # 项目管理
│   │   │       ├── tender_documents.py # 招标文件
│   │   │       ├── requirements.py   # 需求清单
│   │   │       ├── responses.py      # 响应草稿
│   │   │       ├── knowledge.py      # 企业资料（含 scope 隔离）
│   │   │       ├── compliance.py     # 合规核查
│   │   │       ├── stats.py          # 统计报表
│   │   │       ├── workflow.py       # Agent 编排
│   │   │       ├── chat.py           # AI 助手对话
│   │   │       └── bid_document.py   # 标书导出
│   │   ├── agents/                   # Agent 编排层
│   │   │   ├── base.py               # Agent 基类
│   │   │   ├── rag_agent.py          # RAG Agent
│   │   │   ├── compliance_agent.py   # 合规 Agent
│   │   │   ├── parse_agent.py        # 解析 Agent
│   │   │   ├── decompose_agent.py    # 分解 Agent
│   │   │   └── orchestrator.py       # 编排器
│   │   ├── services/                 # 业务服务层
│   │   │   ├── document_parser.py    # 文档解析
│   │   │   ├── file_storage.py       # 文件存储
│   │   │   ├── tender_requirement_extractor.py # 需求提取
│   │   │   ├── company_material_service.py # 企业资料
│   │   │   ├── text_chunker.py       # 文本切块
│   │   │   ├── vector_store.py       # 向量存储（Milvus）
│   │   │   ├── retrieval_service.py  # 检索服务
│   │   │   ├── response_generation_service.py # 响应生成
│   │   │   ├── compliance_checker.py # 合规检查（规则引擎）
│   │   │   ├── semantic_compliance_agent.py # 语义合规（LLM）
│   │   │   ├── prompt_templates.py   # 提示词模板
│   │   │   ├── llm_client.py         # LLM 客户端
│   │   │   ├── report_service.py     # 报告生成
│   │   │   ├── readiness_service.py  # 就绪度计算
│   │   │   ├── batch_task_service.py # 批量任务
│   │   │   ├── auxiliary_requirement_service.py # 辅助需求生成
│   │   │   ├── chat_service.py       # 对话服务
│   │   │   ├── bid_document_service.py # 标书合并
│   │   │   └── reranker.py           # 重排序
│   │   ├── scripts/                  # 数据库迁移脚本
│   │   │   ├── migrate_add_scope.py
│   │   │   └── migrate_compliance_source.py
│   │   └── tests/                    # 测试代码（见 tests/）
│   ├── tests/                        # 测试用例
│   │   ├── conftest.py               # 测试配置
│   │   ├── test_auth.py
│   │   ├── test_projects_and_parser.py
│   │   ├── test_response_and_compliance.py
│   │   ├── test_security_fixes.py
│   │   ├── test_material_isolation.py
│   │   ├── test_vector_store_match.py
│   │   ├── test_agents.py
│   │   └── ...
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                         # 前端代码
│   ├── src/
│   │   ├── main.js                   # 应用入口
│   │   ├── App.vue                   # 根组件
│   │   ├── router/                   # 路由配置
│   │   │   └── index.js
│   │   ├── stores/                   # Pinia 状态管理
│   │   │   ├── auth.js               # 认证状态
│   │   │   └── project.js            # 项目状态
│   │   ├── api/                      # API 调用
│   │   │   ├── client.js             # Axios 实例
│   │   │   ├── auth.js               # 认证 API
│   │   │   ├── projects.js           # 项目 API
│   │   │   ├── compliance.js         # 合规 API
│   │   │   ├── materials.js          # 资料 API
│   │   │   ├── stats.js              # 统计 API
│   │   │   └── chat.js               # 对话 API
│   │   ├── views/                    # 页面视图
│   │   │   ├── LoginView.vue         # 登录
│   │   │   ├── RegisterView.vue      # 注册
│   │   │   ├── ProjectListView.vue   # 项目列表
│   │   │   ├── NewProjectView.vue    # 新建项目
│   │   │   ├── ProjectDetailView.vue # 项目详情
│   │   │   ├── CompanyMaterialsView.vue # 企业资料
│   │   │   ├── ComplianceReportView.vue # 合规报告
│   │   │   └── AnalyticsView.vue     # 分析统计
│   │   ├── components/               # 公共组件
│   │   │   ├── RequirementTable.vue   # 需求表格
│   │   │   ├── ResponseDraftPanel.vue # 响应草稿面板
│   │   │   ├── ComplianceReport.vue  # 合规报告组件
│   │   │   ├── RiskSummary.vue       # 风险摘要
│   │   │   └── AiChatPanel.vue       # AI 对话面板
│   │   ├── layouts/                  # 布局组件
│   │   │   └── AppLayout.vue
│   │   ├── composables/              # 组合式函数
│   │   │   └── usePagination.js
│   │   └── styles/                   # 样式
│   │       ├── global.css
│   │       └── utilities.css
│   ├── package.json
│   └── vite.config.js
├── docs/                             # 文档
│   ├── api-contract.md               # 接口契约
│   ├── architecture.md               # 系统架构
│   └── ...
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

## 测试

```bash
# 后端单元测试（含覆盖率）
cd backend
pytest tests/ -v --cov=app --cov-report=term-missing

# 后端覆盖率报告（要求 >= 80%）
pytest tests/ --cov=app --cov-report=html

# 前端构建验证
cd frontend
npm run build
```

## 开发流程

1. **后端开发**：FastAPI + SQLAlchemy + pytest
2. **前端开发**：Vue 3 + Vite + Pinia
3. **AI 服务**：DashScope 大模型 + Milvus 向量检索
4. **代码质量**：静态分析 + 单元测试 + 集成测试

## 分支规范

- `main`：生产分支
- `feature/xxx`：功能分支
- `bugfix/xxx`：修复分支
- 合并前需通过代码审查和测试

## 安全与稳定性说明

### 已实现的安全措施

- **JWT 认证**：所有 API（除注册/登录外）均需 Token 验证
- **项目隔离**：用户只能访问自己的项目及其关联资源
- **Scope 隔离**：企业资料支持 company（公司级共享）和 project（项目级专属）两级隔离
- **权限校验**：批量删除、资料上传等敏感操作均校验项目归属

### 已修复的关键问题

- 数据库连接池泄漏：引擎在 shutdown 时正确释放
- Schema 一致性检查：使用 SQLAlchemy 反射替代 MySQL 专有语法
- 测试断言对齐：测试期望与实际逻辑行为一致
- 错误处理降级：LLM/Milvus 失败不抛 500，改为记录日志并返回安全值

## 配置说明

### 环境变量 (.env)

```
# 数据库
DATABASE_URL=mysql+aiomysql://user:password@host:port/bidflow

# JWT
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530

# DashScope (LLM)
DASHSCOPE_API_KEY=your-api-key
LLM_MODEL_NAME=qwen-flash-2025-07-28

# 文件上传
UPLOAD_DIR=./uploads
ALLOWED_EXTENSIONS=.txt,.pdf,.docx
```
