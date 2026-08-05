# BidFlow 缺失流程修复提示词集

> 本文件包含 8 个独立、可直接提交给 AI 编码工具执行的修复提示词。
> 每个提示词统一采用四段式：**明确目标 / 上下文信息 / 约束条件 / 输出规范**。
> 文档内已将流程图中所有节点标记（如"节点④"）、步骤编号、以及提示词之间的字母交叉引用，全部替换为完整、自包含的实际内容，AI 可直接理解，无需额外推断。
> 后端代码根目录约定为 `backend/`，所有相对路径均基于此。

---

## 提示词 1 — 角色权限模型（RBAC）

### 明确目标
为系统引入基于角色的访问控制（RBAC），在数据库中定义并落地三种业务角色——**招标负责人(owner)**、**资料整理员(librarian)**、**合规审核员(auditor)**——使权限校验从当前的"仅判断当前用户是否为资源所有者"升级为"角色 + 所有权"双维度。落地后需能支撑以下业务流程约束：企业资料上传仅允许 owner 或 librarian 操作；合规审核与风险确认仅允许 auditor（或 owner）执行；普通生成/编辑操作 owner 即可。

### 上下文信息
- 项目为 FastAPI 后端，位于 `backend/`。
- 现有用户模型文件 `backend/app/models/user.py` 中 `User` 类仅有以下列：`id`（CHAR(36) UUID 主键）、`username`（String(50) 唯一索引）、`password_hash`（String(255)）、`is_active`（Boolean 默认 True）、`created_at`、`updated_at`。**不存在任何角色/权限字段**。
- 现有所有权限校验均为"所有权判定"，典型代码模式为 `project.owner_id == current_user.id`，出现在以下文件：`backend/app/api/deps.py`（`get_project_or_404_sync`）、`backend/app/api/routes/projects.py`、`requirements.py`、`responses.py`、`knowledge.py`、`tender_documents.py`、`stats.py`。
- 认证体系：`backend/app/core/security.py` 使用 JWT（生成/校验 token）+ bcrypt（密码哈希）；当前登录用户对象由 `backend/app/api/deps.py:get_current_user` 依赖注入到各路由处理函数。
- 业务角色职责（来自流程图"角色"定义）：
  - 招标负责人(owner)：创建/管理投标项目、上传招标文件、查看整体进度。
  - 资料整理员(librarian)：上传并整理企业资料（资质/产品/方案等）、识别空资料。
  - 合规审核员(auditor)：执行合规审核、风险确认、纠错，对应流程图中"人工审核/风险确认"环节（该环节规定 owner/auditor 审核草稿、可确认/驳回/标记，AI Agent 不予审批）。

### 约束条件
1. 在 `User` 模型新增 `role` 列：MySQL `VARCHAR(20)`，取值固定为 `owner` / `librarian` / `auditor`，默认值 `owner`。存量用户记录自动视为 `owner`，保证向后兼容。
2. 在 `backend/app/api/deps.py` 中新增依赖 `get_current_user_role(current_user: User = Depends(get_current_user)) -> str`（直接返回 `current_user.role`）与 `require_role(*allowed_roles: str)`，后者在角色不在允许列表时抛出 403（复用现有 `BusinessException` 或 FastAPI `HTTPException`）。
3. **不得修改** `backend/app/core/security.py` 的 JWT 签发与校验逻辑，也不得修改 `get_current_user` 的现有行为。
4. 提供集中式权限矩阵常量（如 `ROLE_PERMISSIONS: dict[str, set[str]]`），以"角色 → 允许的动作标识集合"形式定义各角色可访问的路由动作。
5. **保留**现有 `owner_id` 所有权校验逻辑；新角色校验为叠加层（角色不满足或不是所有者均拒绝，具体依矩阵而定）。
6. 不引入任何新的第三方依赖（角色用 SQLAlchemy 列 + Python 枚举/常量即可实现）。
7. 数据库变更须提供 Alembic 迁移脚本，或在 `backend/app/db/session.py:init_db()` 的 `create_all` 机制下给出兼容说明（当前用 `create_all` 建表，新增列后需手工 migrate 或重建）。

### 输出规范
- 修改文件清单与具体改法：
  - `backend/app/models/user.py`：新增 `role` 列。
  - `backend/app/api/deps.py`：新增 `get_current_user_role` 与 `require_role`。
  - `backend/app/core/security.py`：新增角色枚举/常量（如 `class UserRole`）。
- 至少 3 处示例路由接入 `require_role` 的改法，分别覆盖 owner、librarian、auditor 各一种操作（例如：企业资料上传接口限制为 owner/librarian；合规审核接口限制为 auditor）。
- 一份权限矩阵文档（Markdown 表格：行=角色 owner/librarian/auditor，列=可操作端点动作，单元格=允许/拒绝）。
- 数据库迁移脚本（或 `init_db` 兼容变更说明）。
- 单元测试用例：正确角色放行、越权返回 403、存量用户默认 owner。
- 所有改动须可直接合并，且不应破坏现有 `pytest` 测试套件通过。

---

## 提示词 2 — 辅助需求生成（招标需求 LLM 派生）

### 明确目标
实现流程图中"生成辅助需求"环节：在"上传招标文件 → 文件解析 → 解析与需求抽取"完成之后，基于已抽取的需求项，调用大语言模型(LLM) **派生或补全可编辑的辅助需求项**（例如隐性合规点、常见投标易漏项、资格衍生要求），并支持人工接受/修改/删除/补充，最终写入需求表。当前系统仅有基于关键词分类的需求抽取，无任何 LLM 推导能力，此环节完全缺失。

### 上下文信息
- 流程图"生成辅助需求"节点完整定义：
  - 名称：生成辅助需求（requirements 辅助 / 模块0 辅助准备）
  - 输入：解析与需求抽取环节产出的招标需求项
  - 处理：根据结果 → 产出**可编辑需求项**，支持接受修改/补充/删除/人工修正
  - 输出：写入 `requirements` 表 → MySQL（存入需求明细）
- 现有实现链路：`backend/app/api/routes/tender_documents.py:parse_tender_document` 串行调用：
  1. `backend/app/services/document_parser.py:DocumentParserService.parse`（将招标文件解析为段落列表，每段含 `text` 与 `source_ref`）
  2. `backend/app/services/tender_requirement_extractor.py:TenderRequirementExtractorService.extract(db, project_id, tender_document_id, parsed_paragraphs)`（仅做关键词分类：资格/商务/技术/评分/其他 + 优先级 P0/P1/P2，写入 `Requirement` 表；当 `parsed_paragraphs` 为空时返回 `_generate_demo_requirements` 硬编码示例，**无 LLM 调用**）。
- `Requirement` 模型字段（`backend/app/models/requirement.py`）：`project_id`、`tender_document_id`、`category`、`content`、`source_text`、`source_ref`、`priority`（默认 P2）、`status`（默认"未处理"）、`risk_level`、`assignee_id`。
- LLM 客户端：`backend/app/services/llm_client.py:OpenAIChatClient.chat_json(messages, ...)`（底层调用 DashScope qwen 系列，API Key 取自 `backend/app/core/config.py:DASHSCOPE_API_KEY`）。
- Prompt 模板集中放在 `backend/app/services/prompt_templates.py`。

### 约束条件
1. **不得修改**现有 `extract()` 方法与解析流程；新增独立方法/服务 `generate_auxiliary_requirements(db, project_id, tender_document_id)`。
2. 复用 `extract()` 已产出的 `Requirement` 列表（按 `project_id` + `tender_document_id` 查询）作为 LLM 输入上下文。
3. 新增的需求项须带来源标记以区分：在 `Requirement` 模型新增 `source` 列（`VARCHAR(20)`，取值 `parsed` / `ai_aux`，存量记录默认 `parsed`），新派生项填 `ai_aux`，**不覆盖**已有解析项。
4. 新增端点 `POST /api/projects/{pid}/requirements/aux-generate`，仅项目所有者可调（本提示词不强制引入 RBAC，但代码应预留 `require_role` 接入点）。
5. LLM 调用失败时须降级：返回空列表 + 记录日志告警，**不中断**主流程、不抛 500。
6. 新需求项 `priority` 沿用现有 P0/P1/P2；`category` 沿用现有四类 + "其他"。

### 输出规范
- 新增/修改文件：
  - `backend/app/services/auxiliary_requirement_service.py`（或扩展 `tender_requirement_extractor.py`）：实现 `generate_auxiliary_requirements`。
  - `backend/app/services/prompt_templates.py`：新增 `build_aux_requirement_messages(requirements: list[dict]) -> list[dict]`，约束 LLM 输出结构化 JSON，字段对齐 `Requirement`（含 content/category/priority/source='ai_aux'）。
  - `backend/app/api/routes/requirements.py`：新增 `POST /api/projects/{pid}/requirements/aux-generate` 路由。
  - `backend/app/schemas/requirement.py`：新增请求/响应 schema。
  - `backend/app/models/requirement.py`：新增 `source` 列及迁移说明。
- 端点行为：返回本次生成的辅助需求项列表，每项含 `id`、`content`、`category`、`priority`、`source='ai_aux'`。
- Prompt 模板须明确约束 LLM 仅基于输入需求做合理派生，不臆造与招标无关的条目。
- 单元/集成测试：正常生成、LLM 不可用降级为空、重复调用不重复生成。
- 代码可直接合并，现有解析接口（`parse_tender_document`）行为不变。

---

## 提示词 3 — 语义合规 Agent（合规检查第二轨）

### 明确目标
在流程图中"合规检查"环节补齐**语义合规 Agent** 这一轨，使合规检查从当前的纯规则引擎升级为"规则引擎/判罚 + 语义合规 Agent"双轨并行：用 LLM 对响应稿与招标要求做语义级合规判定（是否满足、风险原因、严重度），与规则引擎结果合并写入合规问题表，弥补当前语义能力仅零散寄生在向量库覆盖度判断里的缺陷。

### 上下文信息
- 流程图"合规检查"节点完整定义：
  - 名称：合规检查（规则引擎/判罚 + 语义合规 Agent）
  - 处理：规则引擎做实时判罚（无法满足 PO 状态/违规/规则/评分不一等）；语义合规 Agent 仅做反馈说明
  - 输入：响应稿(response) + 规则/要求
  - 输出：报告 → LLM → Agent 反馈说明
  - 分支：若发现风险问题 → 触发补充材料/重新配置（回退链路，见提示词 6）
- 现有规则引擎：`backend/app/services/compliance_checker.py:ComplianceChecker.check(requirements: list[RequirementSnapshot]) -> list[ComplianceIssue]`，为**纯确定性规则**，仅 4 条：
  - `P0_RESPONSE_MISSING`：需求 priority=="P0" 且 status!="completed" → 严重度 high，描述"P0 响应项尚未完成"
  - `RESPONSE_CONTENT_EMPTY`：响应内容为空 → 严重度 high，描述"响应内容为空"
  - `RESPONSE_SOURCE_MISSING`：响应缺 source_refs → 严重度 medium，描述"响应内容缺少企业资料来源"
  - `MANUAL_MATERIAL_REQUIRED`：status=="needs_manual" → 严重度 medium，描述"资料不足，需要人工补充"
- 触发点：`backend/app/api/routes/compliance.py:run_compliance_check` 先 `DELETE` 旧 issue → 构建 `RequirementSnapshot` 列表（含 requirement_id/content/priority/response_content/source_refs/status）→ 调 `check()` → 写 `ComplianceIssue` 表。
- `ComplianceIssue` 模型字段（`backend/app/models/compliance_issue.py`）：`project_id`、`requirement_id`、`level`（高/中/低）、`rule_code`、`description`、`suggestion`、`status`（默认"未处理"）。
- 现有零散"语义"能力：位于 `backend/app/services/vector_store.py:match_requirement_to_materials` 内的 LLM 覆盖度调用（`_call_match_llm`），产出 coverage/confidence，**非独立合规 Agent**，且不产出可审计的合规结论。
- LLM 客户端：`OpenAIChatClient.chat_json`；现有 Prompt 模板惯例见 `backend/app/services/prompt_templates.py:build_risk_explanation_messages`。

### 约束条件
1. 新增独立服务 `backend/app/services/semantic_compliance_service.py:SemanticComplianceService`，**不修改** `ComplianceChecker` 规则逻辑。
2. 在 `run_compliance_check` 中，于 `check()` 之后调用语义服务，结果合并写入 `ComplianceIssue`。
3. `ComplianceIssue` 需区分检查类型：新增 `check_type` 列（`VARCHAR(20)`，取值 `rule` / `semantic`，存量默认 `rule`）；语义 issue 的 `rule_code` 统一前缀 `SEM_`。
4. 语义 Agent 输入：单条需求的 `content` + 对应 `Response` 的 `ai_content`/`edited_content` + `source_refs`；要求 LLM 输出结构化 JSON：`{compliant: bool, reason: str, severity: "high"|"medium"|"low", suggestion: str}`。
5. LLM 不可用须降级：跳过语义轨、记日志，规则轨结果照常落库，不影响主流程。
6. 语义判定须与规则引擎互补——规则引擎已覆盖的（如内容为空）交给规则引擎，语义轨只判定"有内容但不合规 / 答非所问 / 遗漏关键约束"等语义层面问题，避免重复 issue。

### 输出规范
- 新增文件：
  - `backend/app/services/semantic_compliance_service.py`：实现 `SemanticComplianceService.check_requirements(snapshots) -> list[SemanticIssue]`。
  - `backend/app/services/prompt_templates.py`：新增 `build_semantic_compliance_messages(requirement_content, response_content, source_refs) -> list[dict]`。
- 修改文件：
  - `backend/app/api/routes/compliance.py`：`run_compliance_check` 接入语义服务并合并写库。
  - `backend/app/models/compliance_issue.py`：新增 `check_type` 列。
  - `backend/app/schemas/compliance.py`：响应含 `check_type`。
- `ComplianceIssue` 表新增列的迁移说明。
- 合并后报告须包含语义 issue 计数（按 severity 高/中/低分别统计）。
- 测试：语义命中正确写库（check_type='semantic', rule_code 以 SEM_ 开头）、LLM 降级时规则轨不受影响、与规则引擎不重复。
- 代码可直接合并。

---

## 提示词 4 — Agent 编排层（Orchestrator + Sub-Agent 封装）

### 明确目标
引入流程图中显式的 **Agent 编排层**：一个 `Orchestrator` 类 + 对现有 Service 的 **Sub-Agent 封装**（解析 Agent / 拆解 Agent / RAG Agent / 合规 Agent），统一管理管道状态、分支回退钩子与可观测性，替代当前散落在路由处理函数里的隐式顺序调用。该层为后续"资料齐全回退闭环"（提示词 5）与"风险问题回退链路"（提示词 6）提供承载框架。

### 上下文信息
- 流程图"Agent 编排层"定义：
  - 顶层：Orchestrator（编排器）+ 4 个 Sub-Agent（解析 Agent | 拆解 Agent | RAG Agent | 合规 Agent(可选)）
  - 统一工具调用：Milvus / MySQL / LLM
  - 兜底：Human-in-the-loop（人工介入）
- 当前**无 Orchestrator 类或 agent 包**；"编排"靠路由处理函数内部顺序调用 Service，例如：
  - `backend/app/api/routes/tender_documents.py:parse_tender_document` 调用 `document_parser.parse` → `tender_requirement_extractor.extract`
  - `backend/app/api/routes/responses.py:batch_generate_responses` 调用 `retrieval_service.search` → `response_generation_service.generate`
- 现有 Service 即事实上的子 Agent：
  - 文件解析：`backend/app/services/document_parser.py:DocumentParserService`
  - 需求抽取（拆解）：`backend/app/services/tender_requirement_extractor.py:TenderRequirementExtractorService`
  - 知识入库：`backend/app/services/company_material_service.py` + `backend/app/services/text_chunker.py` + `backend/app/services/vector_store.py`
  - 检索（RAG）：`backend/app/services/retrieval_service.py` + `backend/app/services/vector_store.py`
  - 应答生成（RAG）：`backend/app/services/response_generation_service.py`
  - 合规：`backend/app/services/compliance_checker.py`（语义轨见提示词 3）
  - 报告：`backend/app/services/report_service.py`
  - 基座：`backend/app/services/llm_client.py:OpenAIChatClient` / `EmbeddingClient`
- 路由装配点：`backend/app/api/router.py`；DB 会话：`backend/app/db/session.py`（async `get_session` + sync `get_db`）。

### 约束条件
1. 新建 `backend/app/agents/` 包（含 `__init__.py`），**仅做封装，不重新实现业务逻辑**——直接复用现有 Service 实例。
2. 定义统一 `BaseAgent` 接口：`run(input) -> AgentResult`；`AgentResult` 含 `output`、`status`（success/failed）、`metadata`（耗时、版本、日志）。
3. 封装至少 4 个 Sub-Agent：`ParseAgent`（解析）、`DecomposeAgent`（需求抽取/拆解）、`RagAgent`（检索+生成）、`ComplianceAgent`（规则+语义，语义见提示词 3）。
4. `Orchestrator` 管理一个**管道定义**（有序步骤 + 可选分支钩子），用轻量状态对象（pydantic `PipelineState`）在步骤间传递；提供 `register_step(name, agent, next_on_success, branch_hooks)` 与 `run_pipeline(initial_state)`。
5. **本提示词不实现具体分支回退逻辑**（那属于提示词 5 与提示词 6）；只提供分支钩子占位（`on_branch(name, condition_callable)`）与可注入的回退回调接口。
6. 现有 REST 路由**必须保持可用**；Orchestrator 作为可选新入口（例如 `POST /api/orchestrate`），不强行替换旧路由。
7. 不引入 LangGraph 等重框架；用 Python 标准库 + pydantic 实现，控制依赖体积。

### 输出规范
- 目录与文件结构：
  - `backend/app/agents/base.py`：`BaseAgent` / `AgentResult` / `PipelineState` 定义与 docstring。
  - `backend/app/agents/parse_agent.py`、`decompose_agent.py`、`rag_agent.py`、`compliance_agent.py`：4 个 Sub-Agent 封装（各 wrapping 对应 Service）。
  - `backend/app/agents/orchestrator.py`：`Orchestrator` 类含 `register_step`、`run_pipeline`、分支钩子占位。
  - `backend/app/api/routes/orchestrator.py`（可选）：最小编排示例端点。
- 一个最小编排示例（串联 解析 → 拆解 → RAG 生成）及对应调用代码。
- 单元测试：单 Agent 跑通、PipelineState 跨步骤传递、分支钩子可被注册与触发。
- 代码可直接合并，不破坏现有功能与测试。

---

## 提示词 5 — 资料齐全回退闭环（对齐阶段）

### 明确目标
实现流程图中"资料对齐/缺口分析"环节之后的**菱形判断「资料齐全？」及回退闭环**：聚合项目级"需求—企业资料"匹配结果，产出资料齐备度报告与**补齐建议清单**；当判定不齐全时，引导回退到"上传企业资料"环节，弥补当前 `match_requirement_to_materials` 只返回单需求结果、无任何工作流回退动作的缺口。

### 上下文信息
- 流程图相关节点完整定义：
  - "资料对齐/缺口分析"节点：选定 Milvus、规范、范围（增量/部分/全量），找缺口并针对补齐或提意见/策略；输入 requirements → Milvus → 查出差距分析 → 已归档；**分支条件：资料齐全？→ 否 → 回到"上传企业资料"节点**。
  - "上传企业资料"节点：调用资料上传接口，上传资质/产品/方案等多份资料 → 保存原始文件与元数据；输入企业资料文档 → tokenizer → document_docs（形式/文本）。其 API 为 `POST /api/company-documents`（`backend/app/api/routes/knowledge.py:upload_company_document`），支持 `scope`(company/project) 与 `project_id` 表单参数。
- 现有单需求匹配：`backend/app/services/vector_store.py:match_requirement_to_materials(requirement: dict, project_id: int, top_k: int=5) -> MatchResult`，`MatchResult` 字段：`requirement_id`、`coverage`(full/partial/missing)、`confidence`(float)、`material_covered`(bool)、`evidence`(list)、`gap`(str)、`pending_review`(bool)。
- 现有聚合端点：`backend/app/api/routes/responses.py:analyze_requirement_matches(project_id)` 遍历需求调 `retrieval_service.search` 得 `has_match`/`match_score`，但**只做统计，不生成补齐建议，不触发回退**。
- 需求表 `Requirement` 含 `category`（资格/商务/技术/评分/其他）与 `gap` 来源内容。

### 约束条件
1. 新增独立服务方法 `project_material_readiness(db, project_id) -> ReadinessReport`，**不改动** `match_requirement_to_materials` 与 `analyze_requirement_matches` 的现有行为。
2. `ReadinessReport` 须包含：
   - `overall_ready`（bool）：整体是否齐全
   - `readiness_rate`（float，0–100）：齐备率
   - `gaps`（list）：每条需求缺口明细，含 `requirement_id`、`coverage`、`gap`、`suggested_material_type`（基于 `category` 与 `gap` 关键词推导，如资格类→资质证书，技术类→技术方案文档）、`suggested_keywords`
3. 新增端点 `GET /api/projects/{pid}/material-readiness`，返回 `ReadinessReport`；项目所有者可调。
4. **不自动上传、不自动调用上传接口**——只产出分析与引导信息（回退动作由前端/人工或提示词 4 的 Orchestrator 驱动）。
5. 该服务可作为提示词 4 Orchestrator 的一个分支步骤接入；但本提示词**自身不依赖**提示词 4，须能独立运行。
6. 缺口"建议补充资料类型"必须基于需求 `category` 与 `gap` 关键词推导，不得调用 LLM（纯规则即可，保证性能与确定性）。

### 输出规范
- 新增/修改文件：
  - `backend/app/services/readiness_service.py`：实现 `project_material_readiness`。
  - `backend/app/api/routes/responses.py` 或 `projects.py`：新增 `GET /api/projects/{pid}/material-readiness`。
  - `backend/app/schemas/readiness.py`（新建）：定义 `ReadinessReport` 与 `GapItem` pydantic schema。
- `ReadinessReport` / `GapItem` 的完整字段定义与示例 JSON。
- 端点返回示例（含整体齐备率、各需求缺口、建议资料类型）。
- 测试：空资料库→齐备率 0% 且 `overall_ready=false`、部分匹配→对应缺口清单、全匹配→`overall_ready=true`。
- 代码可直接合并，不破坏现有端点。

---

## 提示词 6 — 风险问题回退链路（审核阶段）

### 明确目标
实现流程图中从"合规检查"环节出发的**红色虚线回退链路**：当合规检查发现风险问题时，自动生成"补救建议/下一步动作"并支持触发对应回退（补传资料 / 重新检索 / 重新生成应答稿），弥补当前 `ComplianceIssue` 仅落库、无任何回退驱动的缺口。

### 上下文信息
- 流程图相关节点完整定义：
  - "合规检查"节点分支：**若发现风险问题 → 补充材料 / 重新配置**（红色虚线回退箭头）。
  - "上传企业资料"节点（回退目标之一）：`POST /api/company-documents`（`scope`/`project_id` 参数，见提示词 5 上下文）。
  - "选择编排策略→RAG检索"节点（回退目标之二）：用户/RAG Agent 选择编排模式 → 检索 Milvus 关键企业资料 chunks；其检索入口为 `backend/app/services/retrieval_service.py:RetrievalService.search(query, project_id, top_k)`。
  - "生成应答稿"节点（回退目标之三）：调用 LLM → Prompt → LLM 反馈循环（多轮生成）→ 输出初稿；其生成入口为 `backend/app/api/routes/responses.py` 的 `generate_response_draft(requirement_id)` 与 `batch_generate_responses(project_id)`。
- 现有合规落库：`backend/app/api/routes/compliance.py:run_compliance_check` 写 `ComplianceIssue` 表，字段：`project_id`、`requirement_id`、`level`(高/中/低)、`rule_code`、`description`、`suggestion`、`status`(未处理)、`check_type`(见提示词 3)。
- 现有规则码（来自 `backend/app/services/compliance_checker.py`）：
  - `P0_RESPONSE_MISSING`：P0 需求且响应未完成
  - `RESPONSE_CONTENT_EMPTY`：响应内容为空
  - `RESPONSE_SOURCE_MISSING`：响应缺来源
  - `MANUAL_MATERIAL_REQUIRED`：状态 needs_manual（资料不足）
  - 语义轨规则码前缀 `SEM_`（见提示词 3）
- **与本提示词边界区分**：提示词 5 解决"资料对齐阶段、资料齐全？否 → 回退上传"的事前回退（数据源=需求—资料匹配结果 `MatchResult`）；本提示词解决"合规审核阶段、发现风险 → 补救"的事后回退（数据源=合规问题 `ComplianceIssue`）。二者数据源与触发时机不同，互不包含。

### 约束条件
1. 新增服务 `backend/app/services/remediation_service.py:build_remediation_plan(project_id) -> RemediationPlan`，输入为项目的 `ComplianceIssue` 列表，输出结构化补救计划。
2. 建立 `rule_code → 动作` 映射表（Python dict 常量），例如：
   - `MANUAL_MATERIAL_REQUIRED` 及资料类 `SEM_*`（如 `SEM_MATERIAL_GAP`）→ 动作 `upload_material`，`suggested_detail` 为建议资料类型
   - `RESPONSE_SOURCE_MISSING` → 动作 `re_retrieve`（重新检索企业资料）
   - `P0_RESPONSE_MISSING` / `RESPONSE_CONTENT_EMPTY` → 动作 `regenerate_response`（重新生成应答稿）
3. 新增端点：
   - `POST /api/projects/{pid}/remediation-plan`：返回补救计划（**不含**自动执行）
   - `POST /api/projects/{pid}/remediation/apply`：按 plan 触发对应回退调用，须请求体显式传 `confirm: true` 才执行，避免误执行
4. **不修改** `ComplianceChecker` 与 `run_compliance_check` 的落库逻辑；仅在其后调用 `build_remediation_plan`。
5. 与提示词 5 不冲突：本服务读取合规 issue，提示词 5 读取匹配结果；数据源完全隔离。
6. 不依赖 LLM（映射表驱动即可，保证确定性与性能）。

### 输出规范
- 新增文件：
  - `backend/app/services/remediation_service.py`：实现 `build_remediation_plan` 与 `RULE_CODE_TO_ACTION` 映射表。
  - `backend/app/schemas/remediation.py`：定义 `RemediationPlan` / `RemediationAction` pydantic schema，字段含 `rule_code`、`action`(upload_material/re_retrieve/regenerate_response)、`target_node`(描述回退目标，如"上传企业资料")、`suggested_detail`。
  - `backend/app/api/routes/compliance.py`：新增上述 2 个端点。
- `RULE_CODE_TO_ACTION` 映射表的完整代码（覆盖全部现有规则码 + SEM_ 前缀约定）。
- `apply` 端点仅在 `confirm=true` 时执行回退调用，并返回执行结果（成功/失败列表）。
- 测试：各 rule_code 映射正确、apply 端点确认保护（无 confirm 拒绝执行）、与提示词 5 数据源隔离。
- 代码可直接合并。

---

## 提示词 7 — 审查报告 PDF 导出

### 明确目标
在流程图中"导出审查报告"环节补齐 **PDF 格式导出**，与现有 Markdown 导出并列，满足流程图要求的"Markdown / PDF"双格式输出，弥补当前仅支持 `.md` 的缺口。

### 上下文信息
- 流程图"导出审查报告"节点完整定义：
  - 名称：导出审查报告（模块6 合规/报告）
  - 处理：最终审查报告 / 漏洞风险清单 / 整改建议
  - 输出格式：**Markdown / PDF**
  - 交付：报告文件下载
- 现有导出：`backend/app/api/routes/compliance.py:export_report_markdown(project_id)` 用 `StreamingResponse` 返回 Markdown 文本（调用 `backend/app/services/report_service.py:ReportService.to_markdown(report)`）。
- 报告数据来源：`ComplianceIssue` 表 + `Requirement` 统计（字段：`total_requirements`、`completed_requirements`、`completion_rate`、各 severity 计数 high/medium/low），由 `backend/app/services/report_service.py:ReportService.build(snapshots, issues) -> Report` 聚合；`Report` 含 `issues`（每条含 requirement_id/rule_code/level/description/suggestion/status）、统计字段、风险清单。
- 技术栈：FastAPI + SQLAlchemy(sync 会话)；Python 3.13；依赖写在 `backend/requirements.txt`。
- 报告内容含中文，**PDF 必须正确渲染中文字体**，否则会出现乱码或方块。

### 约束条件
1. 新增端点 `GET /api/{project_id}/compliance-report/pdf`，行为与 Markdown 端点一致，仅媒体类型改为 `application/pdf`，文件名 `compliance-report-{project.name}-{id}.pdf`。
2. PDF 生成优先用 `reportlab`（纯 Python，中文需注册 TTF 字体）；若选 `weasyprint` 等亦可，但须在 `backend/requirements.txt` 显式添加并注明系统依赖。
3. **必须处理中文字体**：内置或指定一个开源中文字体 TTF 路径（如 Noto Sans CJK / 思源黑体），注册到 PDF 引擎，避免乱码/方块。
4. 复用 `ReportService.build` 的聚合数据；新增 `ReportService.to_pdf(report) -> bytes`，与 `to_markdown` 并列，**不改动** `to_markdown`。
5. 不引入前端依赖；纯后端生成字节流返回 `StreamingResponse` 或 `Response`。
6. 新依赖须写入 `backend/requirements.txt` 并注明版本。

### 输出规范
- 新增/修改文件：
  - `backend/app/services/report_service.py`：新增 `to_pdf(report) -> bytes`。
  - `backend/app/api/routes/compliance.py`：新增 pdf 端点。
  - `backend/requirements.txt`：添加 PDF 依赖。
  - 字体文件放置说明（建议 `backend/assets/fonts/` 目录，或系统字体路径配置项）。
- `to_pdf` 输出 PDF 字节，内容须含：项目信息、完成率、各 severity 风险清单、合规问题明细表（rule_code / description / suggestion / status）。
- 端点返回示例（headers `Content-Disposition` + 媒体类型 `application/pdf`）。
- 字体注册代码片段与回退策略（字体缺失时记日志告警而非崩溃）。
- 测试：生成非空 PDF、中文不乱码、与 Markdown 内容一致。
- 代码可直接合并。

---

## 提示词 8 — Human-in-the-loop 审核流完善

### 明确目标
完善流程图中"人工审核/风险确认"环节的 Human-in-the-loop 工作流：补齐显式的**提交审核 / 通过 / 驳回(附原因) / 打回修订**动作、响应稿**版本管理(v1–v4)**，以及**合规问题状态更新端点**与**合规审核员(auditor)专属审核入口**，弥补当前仅有 `PATCH` 改内容/状态、无审核动作与版本、且 `ComplianceIssue.status` 无更新 API 的缺陷。

### 上下文信息
- 流程图"人工审核/风险确认"节点完整定义：
  - 名称：人工审核/风险确认（Human-in-the-loop）
  - 角色：招标负责人(owner) / 合规审核员(auditor) 审核草稿
  - 动作：可确认 / 确认 / 驳回 / 标记（AI Agent 不予审批）
  - 输出：v1–v4 版本 | 开放/关闭 → 即时响应 | 允许/否决
- 现有审核入口：`backend/app/api/routes/responses.py:update_response_draft(requirement_id, request)` 仅支持改 `edited_content` 与 `status`，无审核语义动作。
- `Response` 模型字段（`backend/app/models/response.py`）：`requirement_id`、`ai_content`、`edited_content`、`source_refs`、`status`（默认"草稿"，可流转 needs_manual / pending_review / completed）。
- `ComplianceIssue.status` 默认"未处理"，**当前无任何更新端点**（死代码 `backend/app/api/routes/company_documents.py` 未被注册，亦不含此功能）。
- 角色依赖：本环节需要 auditor 角色限制，依赖 RBAC（见提示词 1）。若提示词 1 尚未落地，代码中应以 owner 兼容并预留 `require_role('auditor')` 接入点（用注释明确标注 TODO）。
- 业务角色定义（来自流程图）：合规审核员(auditor) 负责审核权限/风险/纠错；招标负责人(owner) 可管理项目并参与审核。

### 约束条件
1. 新增审核动作端点（建议挂在 `backend/app/api/routes/responses.py`）：
   - `POST /{rid}/response/submit`：提交审核（draft → pending_review）
   - `POST /{rid}/response/approve`：通过（→ completed）
   - `POST /{rid}/response/reject`：驳回（请求体含 `reason: str`，→ rejected）
   - `POST /{rid}/response/revision`：打回修订（→ needs_revision）
2. 版本管理：在 `Response` 模型新增 `version`(int，默认 1) 与 `review_status`(str：draft/pending_review/approved/rejected/needs_revision) 列；每次 `approve` 或显著编辑后 `version + 1`；历史保留可用新表 `ResponseRevision`（存各版本 ai_content/edited_content/review_status/version/created_at）或简单递增版本号二选一，实现时须注明选择。
3. 新增 `PATCH /api/{project_id}/compliance-issues/{id}` 更新 `ComplianceIssue.status`（未处理 → 已处理/已忽略），auditor 可调（见提示词 1 角色约束）。
4. 新增 auditor 审核入口示例（如 `GET /api/auditor/pending-reviews`），用提示词 1 的 `require_role('auditor')`；若提示词 1 未落地，先以 owner 兼容并留 TODO 注释。
5. **保留**现有 `update_response_draft` PATCH 向后兼容。
6. 状态流转用显式枚举/常量集中管理，避免散落字符串。

### 输出规范
- 新增/修改文件：
  - `backend/app/api/routes/responses.py`：4 个审核动作端点。
  - `backend/app/api/routes/compliance.py`：合规问题状态更新端点。
  - `backend/app/models/response.py`：新增 `version` / `review_status` 列。
  - `backend/app/schemas/response.py`：审核请求/响应 schema（含 `reason` 等）。
  - 新建或扩展 `backend/app/models/response_revision.py`（版本历史，若采用）。
- 审核状态机说明（Markdown：状态 × 合法迁移表，例如 draft → pending_review → approved/rejected/needs_revision）。
- auditor 入口示例 + 角色接入点（依赖提示词 1）。
- `ComplianceIssue` 状态更新端点与 schema。
- 迁移说明（version / review_status 列）。
- 测试：各动作状态正确流转、版本自增、越权/非法迁移被拒。
- 代码可直接合并，不破坏现有 PATCH 行为。

---

## 各修复项目标与边界总览（无交叉引用，纯内容描述）

| 序号 | 修复目标 | 类型 | 关键边界（避免重叠） |
|------|---------|------|---------------------|
| 1 | 角色权限模型（owner/librarian/auditor） | 基础设施 | 仅做角色模型与依赖注入，不含任何业务逻辑实现 |
| 2 | 辅助需求 LLM 派生（对应"生成辅助需求"环节） | 节点功能 | 独立 LLM 派生，不触碰规则引擎/合规逻辑 |
| 3 | 语义合规 Agent（对应"合规检查"第二轨） | 节点功能 | 只新增语义判定轨，不改 `ComplianceChecker` 规则 |
| 4 | Agent 编排层（Orchestrator + Sub-Agent 封装） | 架构骨架 | 只做封装 + 分支钩子占位，不含具体回退实现 |
| 5 | 资料齐全回退闭环（对应"资料对齐/缺口分析"后的菱形判断） | 工作流分支 | 事前/对齐阶段回退，数据源=需求—资料匹配结果 `MatchResult` |
| 6 | 风险问题回退链路（对应"合规检查"红色虚线回退） | 工作流分支 | 事后/审核阶段回退，数据源=合规问题 `ComplianceIssue` |
| 7 | 审查报告 PDF 导出（对应"导出审查报告"PDF 格式） | 输出格式 | 仅加 PDF，不改现有 Markdown 导出 |
| 8 | 审核流完善（对应"人工审核/风险确认"环节） | 节点功能 | 审核动作 + 版本管理，角色实现依赖序号 1 |
