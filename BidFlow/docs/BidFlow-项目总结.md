# BidFlow 投标项目管理系统 — 模块详解（v3）

> 版本：v3（2026-08-05）｜ 前序 v2 为综合总结，本版按"模块名称 → 功能说明 → 工作流 → 底层逻辑"统一格式逐一详解，内容与实码一一对应。
> 覆盖模块：认证 · 项目 · 招标文件 · 需求拆解 · 企业资料库 · 向量检索(RAG) · 比对分析 · 响应生成 · 合规检查 · 补救 · 标书导出 · AI 助手 · Agent 编排 · 统计报表

---

## 0. 项目全貌

- **定位**：投标响应的 AI 全流程助手——从招标文件到可交付投标文件，全程"解析 → 匹配 → 起草 → 审核 → 合规 → 打包"。
- **技术栈**：FastAPI + SQLAlchemy 2.0 + MySQL + Milvus + DashScope(通义千问/embedding/OCR) + Vue3 + Element Plus + Vite。
- **核心机制**：全链路异步任务、三级数据降级（Milvus→n-gram→纯关键词）、需求/响应状态主从联动、项目状态自动流转。

---

## 1. 认证与权限模块

### 功能说明
- 注册 / 登录 / 获取当前用户，JWT 无状态鉴权；所有业务路由统一经 `get_current_user` 依赖注入。
- 职责边界：只做"你是谁"；"你能动什么"由各模块的 owner 校验承担（项目/资料/文档均校验归属）。

### 工作流
```
注册(POST /auth/register) → 密码 bcrypt 哈希 → 写入 users
登录(POST /auth/login)    → 校验密码 → 签发 JWT(HS256, sub=user_id, exp)
请求(/me 等)             → Authorization: Bearer <jwt> → get_current_user 解析 → 注入 current_user
```

### 底层逻辑
- **数据结构**：`users(id=UUID-str, username, password_hash, created_at/updated_at)`。
- **哈希**：passlib[bcrypt]；注意 passlib 1.7.4 与新版 bcrypt(≥4.1) 存在 `__about__` 兼容问题（测试环境曾触发）。
- **JWT**：python-jose `create_access_token`，HS256，secret 来自 `settings.SECRET_KEY`。
- **异常**：密码错误 401、用户不存在 404、token 过期/非法 401；401 时前端拦截器清 token 跳登录。
- **外部依赖**：无第三方；纯标准库 + jose + passlib。

---

## 2. 项目管理模块

### 功能说明
- 项目 CRUD、列表（状态/关键词过滤、风险数、完成度聚合）、详情（含就绪度）、项目状态自动流转。
- 职责边界：项目是业务数据的**根容器**（招标文件/需求/响应/合规/资料归属都挂在 project_id 上）。

### 工作流
```
创建(POST /projects)      → status="准备中"，owner_id=当前用户
列表(GET /projects)       → 按 owner 过滤 + 状态/关键词 + 聚合 risk_count/completion
详情(GET /projects/{id})  → 项目 + readiness 三维就绪度
更新/删除(PATCH/DELETE)   → 校验 owner → 级联清理（需求→比对/补救）或 403/404
状态流转(自动)            → 需求全"已完成"→"审核中"；打包投递包→"已完成"（services/project_status.py）
```

### 底层逻辑
- **数据结构**：`bid_projects(id, owner_id, name, description, deadline, status, created_at, updated_at)`；时间戳用 `UTCDateTime`（存 naive UTC、读回 aware、序列化带 +00:00）。
- **状态机**：`准备中 → 审核中 → 已完成`，由 `sync_project_status`（需求全完成判定，含 `db.flush()` 关键步骤）与 `mark_project_completed`（打包触发）驱动——修复了 status 字段曾为 dead code 的问题。
- **完成度聚合**：`completed_req / total_req`；风险数 = 该项目的 `ComplianceIssue` 未处理数。
- **异常**：owner 不匹配 404；删除项目级联清理需求 → 比对详情/补救动作（避免孤儿数据）。
- **外部依赖**：MySQL。

---

## 3. 招标文件模块

### 功能说明
- 招标文件上传（PDF/DOCX/TXT，限 25MB 前后端双重校验）、文本解析（含扫描件 OCR 降级）、列表/详情/删除。
- 职责边界：只负责"把文件变成结构化段落"，条款拆解交给需求模块。

### 工作流
```
上传(POST /projects/{pid}/tender-documents)
  → 校验类型/大小 → file_storage_service 落盘 uploads/ → 建 TenderDocument(status=pending)
解析(POST /tender-documents/{id}/parse)
  → status=processing → document_parser.parse(file_path, file_type)
  → ① txt: UTF-8→GBK 回退，\n\n 分段
  → ② pdf: PyMuPDF 文字层 → 无文字层走 qwen-vl-ocr → PyPDF2 兜底
  → ③ docx: python-docx 段落遍历
  → tender_requirement_extractor.extract() 生成需求 → status=success
删除(DELETE) → 删文件 + 级联删需求（级联清比对/补救）
```

### 底层逻辑
- **数据结构**：`tender_documents(id, project_id, filename, file_path, file_type, file_size, status, error_message, created_at, updated_at)`。
- **解析降级链**：PyMuPDF → qwen-vl-OCR → PyPDF2（三层，缺依赖不崩溃）。
- **状态**：pending → processing → success/failed；失败记录 `error_message`。
- **异常**：类型不符 422、空文件 400、解析失败 BusinessException（doc.status=failed）。
- **外部依赖**：PyMuPDF、python-docx、PyPDF2、DashScope OCR。

---

## 4. 需求拆解模块

### 功能说明
- 把招标文档段落切块为**逐条需求项**，标注类别（资格/商务/技术/评分）、优先级（P0/P1/P2）、风险等级、来源定位。
- 职责边界：产出的 `requirements` 是比对/响应/合规的共同主体。

### 工作流
```
extract(db, project_id, doc_id, parsed_paragraphs)
  → _group_text(段落) → 按"章节标题/独立条款"逐行切块（段落内 \n 逐行判定）
  → 每条块: _classify_category(章节上下文+条款文本) → 类别
  → _classify_priority(类别+文本) → P0/P1/P2 → risk_level(高/中/低)
  → 空结果兜底 _generate_demo_requirements
  → 批量写 requirements(project_id, category, priority, status="未处理", ...)
```

### 底层逻辑
- **切块算法（核心）**：`_group_text` 遍历段落，逐行判定：
  - `_is_heading`（"一、/第X章/1." 前缀且 ≤50 字符）→ 新章节上下文
  - `_is_clause`（编号前缀/动词开头+标点结尾）→ 独立条款新块
  - 其余 → 并入当前块
  - **关键修复**：段落内"标题行+多条条款行"混排时逐行拆分，否则整段被并入说明文字导致需求丢失（曾静默丢 80% 需求）。
- **分类算法**：`category_keywords` 词表打分（资格/商务/技术/评分），取最高分；继承章节标题上下文防误判。
- **优先级**：`p0_keywords`（必须/否决/废标…）、`p1_keywords`（技术/商务/工期…）→ 映射 P0/P1/P2。
- **数据结构**：`requirements(id, project_id, tender_document_id, content, category, priority, risk_level, status, source_text, source_ref, created_at, updated_at)`。
- **外部依赖**：无（纯规则引擎，不调 LLM——保证确定性）。

---

## 5. 企业资料库模块

### 功能说明
- 企业资料上传（公司级/项目级两级归属）、列表（作用域筛选、归属项目名显示）、详情预览、删除（同步向量）、**改归属**（公司级 ⇄ 项目级 + 指定项目）。
- 职责边界：资料的存取与归属管理；向量化由向量检索模块负责。

### 工作流
```
上传(POST /company-documents, Form: scope+project_id+file)
  → 校验 scope 合法性、项目级必填 project_id 且归属当前用户
  → company_material_service.upload: 解析+切片+向量化+写 CompanyDocument
  → 返回 id/片段数
列表(GET /company-documents) → owner 过滤 + 批量 JOIN 项目名(project_names) + 向量计数
改归属(PATCH /company-documents/{id}/scope)
  → 校验资料归属 + 目标项目归属 → 更新 DB → vector_store.update_doc_scope(内存+Milvus 同步)
删除(DELETE /{id}) → 删记录 + vector_store.delete_by_doc_id(内存+Milvus+缓存失效)
检索(POST /retrieval/search) → RetrievalService（见模块 6）
```

### 底层逻辑
- **归属模型**：`company_documents(id, owner_id, filename, file_type, scope, project_id, category, tags, status, created_at)`。
  - `scope=company`：全项目共享（检索时 project_id 参与但 company 资料恒可见）
  - `scope=project`：仅绑定 project_id 的项目检索可见
- **归属变更同步（关键）**：DB 与向量库必须**双写**——`update_doc_scope` 更新内存 `_vectors`（entry.project_id + metadata.scope）+ Milvus 删旧重插 + corpus_version 自增 + 失效比对缓存；漏同步会导致"改了归属但检索仍按旧归属过滤"。
- **孤儿资料**：绑定项目被删 → 前端弹窗检测 `project_id ∈ projects` 失效则置空提示重选。
- **异常**：越权 404、项目级缺 project_id 400。
- **外部依赖**：MySQL + 向量存储（模块 6）。

---

## 6. 向量检索与 RAG 增强模块

### 功能说明
- 企业资料切片向量化入库（Milvus）与混合检索：**dense（语义）+ keyword（n-gram 关键词）双路召回**、分数量纲归一化、LLM Reranker 精排、检索模式标记（dense/keyword 可视化）。
- 职责边界：把"文本 → 可检索片段"；比对/响应/AI 助手都依赖它。

### 工作流
```
upsert(chunks, scope, project_id)
  → 逐 chunk: 内存 _vectors + Milvus upsert（embedding: text-embedding-v3）
hybrid_search(query, project_id, top_k)
  → ① dense 路: 需求 embed → Milvus ANN 检索（保留 cosine 分）→ 标记 retrieval_type="dense"
  → ② keyword 路: 中文 n-gram 关键词匹配（补充 dense 未召回）→ 标记 "keyword"
  → 合并去重 → 分数量纲归一化（dense≤1 保持 / ngram>1 除 15）→ 排序取 top_k
search(query, project_id, top_k)  ← 纯关键词兜底（hybrid 整体失败时）
rerank: LLM Reranker 对候选重打分（失败降级原序）
```

### 底层逻辑
- **数据结构**：内存 `_vectors: [{id, text, project_id, metadata:{doc_id, scope, filename, source_ref, ...}}]`；Milvus collection `bidflow_entities`（IVF_FLAT + COSINE，主键 id 与内存共用）。
- **降级链（三层）**：Milvus 连接失败 → `_milvus_available=False` → 全程内存 n-gram；embedding 调用失败 → dense 路 try/except → keyword only；hybrid 整体异常 → `retrieval_service` 降级纯关键词。**任一层失败不 500**。
- **检索隔离（_matches_scope）**：`project_id=None` 只匹配 company；`project_id=X` 匹配 company + project_id=X。
- **Reranker**：qwen-max 打分排序，非数值分数逐值容错为 0（M5），失败保持召回序。
- **版本与缓存**：`_corpus_version`（=id_counter）自增 + `invalidate_match_cache()`——删除资料/改归属后失效比对缓存，避免返回已删/旧归属命中。
- **外部依赖**：Milvus（pymilvus）、DashScope embedding。

---

## 7. 比对分析模块

### 功能说明
- 需求 ↔ 资料匹配分析：每条需求判定匹配状态（有匹配/部分/缺口）、置信度、引用片段；结果持久化供响应生成与就绪度使用。
- 职责边界：决定"AI 起草时能引用哪些资料"。

### 工作流
```
GET /projects/{pid}/match-analysis        → 有历史直接返回（含 summary）
POST /projects/{pid}/match-analysis/run   → 立即返回 task_id → 后台线程执行
  后台: 逐需求 hybrid_search → LLM 判定 has_match/confidence → 写 MatchAnalysisRun+Details
GET /projects/{pid}/match-analysis/status → 轮询进度（前端 AbortSignal 防泄漏）
比对结果失效 → corpus_version 变化 → invalidate_match_cache → 下次自动重跑
```

### 底层逻辑
- **异步任务模式（项目核心模式）**：POST 立即返回 task_id → `threading.Thread` 后台自建 Session 执行 → 内存 dict `MATCH_TASKS` 存状态 → 前端轮询 `/status`。
- **数据结构**：`match_analysis_runs(id, project_id, status, total_requirements, ...)` + `match_analysis_details(run_id, requirement_id, has_match, confidence, source_refs, ...)`——持久化保证刷新后仍可见。
- **缓存失效**：`invalidate_match_cache` 使"资料变更后比对结果过期"。
- **外部依赖**：模块 6 检索 + DashScope LLM。

---

## 8. 响应生成与审核模块

### 功能说明
- 单条/批量 AI 响应生成、人工编辑、审核状态流（待评审/已批准/已驳回）、强制重新生成、需求状态主从联动、项目状态流转。
- 职责边界：核心业务产出——"AI 起草 + 人工负责"。

### 工作流
```
单条生成 POST /{req_id}/response/generate
  → RetrievalService.search(需求) → 有资料 → LLM 生成草稿(status=pending_review)
  → 无资料 → 返回 needs_manual("待人工补充…") + 清空 source_refs 残留
  → 写 BidResponse + req.status="待评审"
批量生成 POST /projects/{pid}/batch-generate → 异步任务 + /batch-status 轮询
审核 PATCH /{req_id}/response {status}
  → approved: BidResponse.status=approved + req.status="已完成"
  → rejected: resp.status=rejected + req.status="待评审"（强制重新生成闭环）
  → 主从联动 + sync_project_status（全完成→审核中）
仅编辑 edited_content → 不动审核状态
强制重新生成(force) → 清 edited_content 防旧稿优先返回
```

### 底层逻辑
- **数据结构**：`bid_responses(id, requirement_id, ai_content, edited_content, source_refs(JSON), status, updated_at)`；同需求可多版本，取最新（id desc）。
- **内容优先级**：导出/展示用 `edited_content || ai_content`（人工编辑版优先）。
- **状态主从联动（关键修复）**：此前审核只改 BidResponse.status，Requirement.status 停留"待评审"→ 统计"已通过 0/N"；修复后 approved/rejected 双向同步。
- **source_refs 残留防护**：无资料生成时必须 `source_refs=[]`，否则合规扫描误判 P0_RESPONSE_MISSING。
- **LLM 降级**：生成失败/无 Key → 模板默认响应（不 500）。
- **外部依赖**：模块 6/7 + DashScope LLM。

---

## 9. 合规检查模块

### 功能说明
- 合规核查（规则引擎 + 语义 AI 双层）、就绪度三维加权（基础/质量/合规）、合规报告（Markdown/PDF）、历史处置保留。
- 职责边界：质量把关 + 风险量化 + 补救触发。

### 工作流
```
POST /{pid}/compliance-check（异步，180s 超时）
  → 规则引擎: P0 缺失资料/响应空/来源缺失 → ComplianceIssue（level 中文化 高/中/低）
  → 语义 Agent: LLM 逐条检测 + 三层防误报 → 补充 issue
  → 只删"未处理"保留"已处理"（M6）→ 重建 → 统计
GET /{pid}/compliance-report → 风险摘要 + 三维就绪度（基础50%+质量30%+合规20%）
导出 markdown/pdf → ReportService/readiness_service 同一口径
```

### 底层逻辑
- **规则引擎**：确定性判定（P0 无资料→P0_SOURCE_MISSING / 响应空→P0_RESPONSE_MISSING…），level 入库用中文（与前端显示一致）。
- **语义 Agent 三层防误报**：① 黑名单关键词命中丢弃；② **否定词保护**（"未提供/不足/缺失"=真风险不抑制）；③ 置信度阈值 0.6。
- **就绪度**：`readiness_service.calculate` 三维加权；质量维度基于真实匹配记录（与当前需求求交集，≤100% 防虚高）。
- **统计口径一致性**：报告统计用 readiness 单一数据源（`replace(report, ...)` 覆盖）。
- **外部依赖**：DashScope LLM + 规则代码。

---

## 10. 补救与建议模块

### 功能说明
- 对合规风险生成可执行补救计划：缺资料→引导上传 / 响应缺失→自动重新生成（异步+轮询）/ 其余→人工处理；幂等防重复。
- 职责边界：合规闭环的"执行层"。

### 工作流
```
POST /projects/{pid}/remediate
  → 按项目全量未处理 issue 归类:
      需要资料 → remediation_action(upload) + 计上传项
      响应缺失 → 触发 regenerate 异步任务(regenerate_task_id) → 前端轮询 batch-status
      其他     → 人工处理
  → 幂等: 已存在的 (project_id, issue_id) 动作跳过，不重复建/重复触发生成
```

### 底层逻辑
- **数据结构**：`remediation_actions(id, project_id, issue_id, action_type, status, created_at)`；幂等键 = (project_id, issue_id)。
- **状态机**：pending → completed / manual。
- **异常**：重复触发防护（同一 issue 不二次生成）；LLM 生成失败降级默认模板。
- **外部依赖**：模块 8 生成链路 + MySQL。

---

## 11. 标书导出模块

### 功能说明
- 把项目全部需求响应**合并导出**为投标文件（Markdown/PDF 双格式）+ **一键打包投递包**（zip：标书 + 合规报告 + README）；打包即"投递就绪"→ 项目标记已完成。
- 职责边界：流水线终端产出——"AI 辅助、人工负责"的成品落点。

### 工作流
```
GET /bid-document/markdown → build_markdown: 需求+最新响应(edited 优先)按 资格/商务/技术/评分 章节合并
GET /bid-document/pdf      → build_pdf_bytes: reportlab + STSong-Light 中文渲染（XML 转义 &<>/换行）
GET /bid-package           → zip: 投标响应文件.md/pdf + 合规审查报告.md/pdf + README
  → mark_project_completed(项目→"已完成")
```

### 底层逻辑
- **章节组织**：固定序 资格/商务/技术/评分 + 附录"待补充项清单"（未响应需求提醒，保证完整性可见）。
- **引用来源**：每条响应标注资料文件名 + 相关度（溯源）。
- **PDF 中文**：reportlab `UnicodeCIDFont("STSong-Light")` 内置字体；Paragraph 需 XML 转义（& → &amp; 等）+ `\n` → `<br/>`。
- **中文文件名**：RFC 5987（`filename*=UTF-8''...`）+ ASCII 回退名。
- **零依赖**：zip 用标准库 zipfile；不引入 AI 通稿（保持"导出即审核内容"）。
- **外部依赖**：reportlab（PDF）。

---

## 12. AI 对话助手模块

### 功能说明
- 项目详情页悬浮聊天：自然语言提问/指挥，LLM function calling 路由到 7 个业务工具，多轮上下文。
- 职责边界：统一查询/指挥入口，不替代页面操作，但能触发核查/补救。

### 工作流
```
POST /projects/{pid}/chat {message}
  → ChatService: 会话(per-project) 加锁 → LLM(fn calling) 意图解析
  → 命中工具: 执行(概览/需求/合规/比对/草稿/核查/补救) → 结果回填 → 综合回复
  → 无 tools 支持 → 降级纯文本对话
```

### 底层逻辑
- **工具注册**：7 个 function（get_project_overview/get_requirements/get_compliance_issues/…run_compliance_check/remediate_project），schema 描述给 LLM。
- **并发防护**：`threading.Lock` 包裹会话 dict（M2 修复竞态）。
- **异常**：工具执行失败不中断对话（回填错误说明）；LLM 失败返回兜底文案。
- **前端**：Enter 防中文输入法误发（`isComposing`/229）。
- **外部依赖**：DashScope LLM（chat_with_tools）。

---

## 13. Agent 编排模块

### 功能说明
- Orchestrator 流水线编排：解析 → 拆解 → 比对 → 合规 分阶段执行，可暂停/恢复/查历史；Agent 采用 Pipeline/Blackboard 模式。
- 职责边界：把各业务服务组织成可编排的 Agent 工作流（增强演示价值）。

### 工作流
```
POST /{pid}/run-workflow → Orchestrator.run(ctx, db, start_stage)
  → 逐 stage: ParseAgent → DecomposeAgent → RAGAgent → ComplianceAgent
  → stages_done 由 Orchestrator 统一追加（agent 内不重复）
  → WorkflowContext(blackboard) 传递 requirements/retrieval_task_id/compliance_issues
  → human_review_required 时暂停 → POST resume 继续
GET /{pid}/workflow-runs → 历史
```

### 底层逻辑
- **Blackboard 模式**：`WorkflowContext` 携带跨阶段数据（requirements、检索任务、合规结果）。
- **状态管理**：`workflow_runs(status, stages_done, metadata)`；resume 用 `start_stage` 续跑。
- **异常**：非法 start_stage → ValueError → 400。
- **外部依赖**：模块 3/4/6/9。

---

## 14. 统计报表模块

### 功能说明
- 全局统计 + **项目联动**（项目选择器 + 时间维度 7d/30d/90d）：核心指标、项目状态分布、效率指标、风险新增趋势、风险概览、合规健康度（需求交付进度）。
- 职责边界：多项目/单项目视图的决策面板。

### 工作流
```
GET /stats?project_id=X&period=7d/30d/90d
  → project_id=None: 当前用户全部项目聚合
  → project_id=X: 单项目视图（鉴权 404）+ scope 字段带项目名
  → 风险概览 risk_overview{high/medium/low/pending/total}（按视图实时）
  → 合规 compliance{total/passed/pending/score + pending_requirements 未达标清单}
  → trend_chart: 风险新增时间序列（7d=7桶/30d=30桶/90d=9桶×10天）
前端: watch([project, period]) 联动刷新 + scope-banner 视图标识
```

### 底层逻辑
- **口径（重要）**：`compliance.score = 已完成需求/总需求`（任务完成度）；与项目详情的"合规健康度（readiness 加权）"**不同口径**——统计页看交付、详情页看风险处置，已用命名区分（卡片"需求交付进度"）。
- **时间基准**：Python 侧比较用 `datetime.now(timezone.utc)`（UTCDateTime 改造后 aware 一致）。
- **前端**：风险概览等级卡（大数字+图标+构成条）、可访问性（role=img + aria-label）。
- **外部依赖**：MySQL。

---

## 15. 模块协作与整体架构

### 依赖链
```
认证 → 项目 → 招标文件 → 需求拆解 → 比对分析 → 响应生成 → 合规检查 → 补救
   ↘                    ↑                                  ↓
     企业资料库 → 向量检索(RAG) ←───────┘              标书导出/投递包
   AI 助手(编排全部只读+触发)            统计报表(只读聚合)
```

### 数据流转方向
```
文件流: 招标文件 → 段落 → 需求项 → 响应草稿 → 投标文件(zip)
资料流: 企业资料 → 向量 → 检索片段 → 匹配记录 → 响应引用 → 就绪度
风险流: 合规规则 → ComplianceIssue → 补救动作 → 处置记录
状态流: 需求(未处理→待评审→已完成) → 项目(准备中→审核中→已完成)
```

### 关键横切机制
1. **异步任务模式**：match-analysis / batch-generate / batch-status / compliance-check / regenerate——POST 立即返回 task_id + 后台线程 + 前端 AbortSignal 轮询。
2. **三级降级**：向量（Milvus→n-gram→纯关键词）、LLM（生成→模板）、OCR（PyMuPDF→VL→PyPDF2）、Reranker（失败→原序）。
3. **状态一致性**：BidResponse↔Requirement 主从联动；项目状态自动流转；UTCDateTime 全链路时区统一。
4. **数据强一致**：has_match 四字段、source_refs↔status 双重防护、合规统计三段互斥、就绪度≤100%。
5. **可观测**：检索降级/归属变更/状态流转均有 logger.warning/info；测试基线 270+（含 chat/reranker/bid-package/改归属/状态流转专项）。

---

*本文档与 v2 综合总结互补：v2 看全貌，v3 看模块。技术细节均落码可验证。*
