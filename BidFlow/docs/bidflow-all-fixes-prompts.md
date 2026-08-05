# BidFlow 全面审查修复提示词集（16 份，每份 ≤6000 字符，可直接喂 Trae/Cursor）

> 对应审查报告 `docs/bidflow-comprehensive-review.md` 的 F1–F18。每份提示词独立可执行、边界清晰。建议顺序：P1 → P14 → P2 → P3 → P10 → P9 → 其余。F4 并入 P1，F18 并入 P10/P17。

---

### 提示词 P1（对应 F1 + F4）：修复合规核查 500 且清空历史数据

**目标**：修复 `POST /{project_id}/compliance-check` 必 500 并清空 `compliance_issues` 表的问题。
**上下文**：`backend/app/api/routes/compliance.py`。第 23 行仅导入类 `ReportService`；第 120 行却调用未定义的实例 `report_service.build(...)` → `NameError` → 500。第 37–41 行在崩溃前已 `delete()+commit()` 清空旧数据，且第 122–124 行又重复 delete 一次。
**改动**：
1. 把第 120 行 `report = report_service.build(snapshots, rule_issues)` 改为 `report = ReportService().build(snapshots, rule_issues)`。
2. 删除第 37–41 行的提前 `delete()+commit()`（保留第 122–124 行在 build 之后的唯一删除点），使旧数据只在成功构建后才被替换，彻底消除中途异常丢数据风险。
3. 原第 48 行 `if not requirements: raise BusinessException(...)` 必须在删除旧数据之前执行（现因第 37–41 删除已移除，确认该检查位于构建快照前即可，无需移动）。
**约束**：只改 `compliance.py`；不动模型/前端/API 路径；删除与新增在同一事务（第 143 行 commit）不变。
**验证**：对项目点「合规核查」→ 返回统计且 `compliance_issues` 表有数据；连点两次数据不丢、不重复。

---

### 提示词 P2（对应 F2）：修复 get_db 每请求新建引擎导致连接泄漏

**目标**：消除同步请求每次新建数据库引擎造成的连接池泄漏。
**上下文**：`backend/app/db/session.py` 第 20–34 行 `get_db()` 每次 `create_engine()` + `sessionmaker()`，仅 `db_session.close()`，从不 `engine.dispose()`，高并发下引擎累积耗尽连接。
**改动**：在模块级建单例同步引擎与 sessionmaker（参考文件已有的 async `engine`/`async_session_factory` 模式），替换 `get_db`：
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_sync_url = settings.DATABASE_URL.replace("+aiomysql", "+pymysql")
_sync_engine = create_engine(_sync_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
_SyncSessionLocal = sessionmaker(_sync_engine, autocommit=False, expire_on_commit=False)

def get_db():
    db = _SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()
```
**约束**：保留 `get_session()`（async）与 `init_db()` 不变；其余服务（如 `batch_task_service` 内部自建引擎）本提示词不改，但建议后续复用单例。需 `from app.core.config import settings` 已存在。
**验证**：启动后端，连续触发多次同步接口，MySQL `show processlist` 连接数稳定不增长。

---

### 提示词 P3（对应 F3）：生成响应后回写 Requirement.status

**目标**：批量/单条生成应答稿后回写 `Requirement.status`，使前端筛选与 Agent 重跑过滤器生效。
**上下文**：`backend/app/services/batch_task_service.py` 的 `_process_one` 与 `backend/app/api/routes/responses.py` 单条生成只写 `Response`（含 `Response.status`），从不更新 `Requirement.status`（恒为初始值 `"未处理"`）。导致 `agents/rag_agent.py` 用 `Requirement.status.notin_(["completed","已完成"])` 过滤重跑范围永远失效。
**改动**：
1. `batch_task_service._process_one` 写完/更新 `Response` 后，回写需求状态：
```python
req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
if req:
    req.status = "待评审"
    db.add(req)
```
（`_run_batch` 已每条约 commit，无需额外提交）
2. `responses.py` 单条 `generate_response_draft` 成功后同样 `req.status = "待评审"; db.add(req); db.commit()`。
3. 确认 `agents/rag_agent.py` 的重跑过滤集合包含 `"待评审"`（与回写值一致）。
**约束**：status 用中文 `"待评审"`（与 `Requirement` 默认 `"未处理"` 同语言）；不改动 `Response` 写入逻辑；不引入新字段。
**验证**：批量生成后查 `requirements` 表，已生成需求 `status` 不再是全部 `"未处理"`。

---

### 提示词 P5（对应 F5）：source_refs 统一为标准 JSON 存储

**目标**：消除 `source_refs` 以 `str(list)` 单引号字符串持久化导致的解析脆弱。
**上下文**：`batch_task_service.py`（约 200/205/221 行）与 `responses.py` 写入用 `str(source_dicts)`（Python 单引号字面量，非合法 JSON）；读取端 `compliance.py:_parse_source_refs`、`readiness_service.py` 用 `json.loads + ast.literal_eval` 双兜底。
**改动**：
1. 所有写入处将 `str(source_dicts)` 改为 `json.dumps(source_dicts, ensure_ascii=False)`（需 `import json`，通常已存在）。
2. 读取端（compliance.py `_parse_source_refs`、readiness_service 解析函数）简化为仅 `json.loads`，移除 `ast.literal_eval` 兜底分支。
**约束**：字段名/结构不变；确保前端 `source_refs` 解析兼容（字符串则 `JSON.parse`，对象则直接用）；仅改序列化格式，不改变业务含义。
**验证**：生成一个响应，查 DB `source_refs` 为合法 JSON；合规核查中风险判定正确。

---

### 提示词 P6（对应 F6）：统一「完成度」口径为单一数据源

**目标**：消除「完成率」与「就绪度」口径分裂（报告 API / markdown / pdf 算法重复）。
**上下文**：`compliance.py` 报告统计基于 `Requirement.status` 命中 `COMPLETED_STATUSES`；`readiness_service.calculate` 基于 `Response` 内容三维加权；`export_report_markdown`/`export_report_pdf` 又各自重算。同一项目出现两个不同数字。
**改动**：
1. 以 `readiness_service.ReadinessService().calculate(project_id, db)` 为唯一数据源。
2. `ReportService.build` 计算 `completion_rate` 时改为调用 `ReadinessService().calculate(...).overall`（或读取其 `has_response/total`）。
3. `export_report_markdown` 与 `export_report_pdf` 中的完成率统计改为复用 `ReadinessService().calculate(...)`，删除各自重算逻辑。
**约束**：不新增 API；保持 `ComplianceReportResponse` 字段不变；`readiness_service` 已存在且字段稳定（`overall`/`has_response`/`total`/`high_risk_pending` 等）。
**验证**：同一项目在报告页、markdown、pdf 三处的完成度数字一致。

---

### 提示词 P7（对应 F7）：空响应高风险降为中风险

**目标**：避免全新项目因「无响应内容」被全部判为高风险，导致提交门槛永远拦截。
**上下文**：`backend/app/services/compliance_checker.py` 第 43–44 行，需求无响应内容且非 P0 即报高风险 `RESPONSE_CONTENT_EMPTY`。新项目每条需求命中 → `high_risk_pending > 0` 恒真 → `can_submit` 几乎不可能。
**改动**：将 `RESPONSE_CONTENT_EMPTY` 的 `level` 从 `"high"` 改为 `"medium"`，并保持 `description="响应内容为空"`、`suggestion="补充可审核的响应内容。"`；高风险仅留给「已生成但内容/来源不合规」的情形（P0 未完成、缺来源等保持 high）。
**约束**：只改 `compliance_checker.py` 这一条规则的 level 值；不动其他规则与前端。
**验证**：对全新项目跑合规检查，空响应显示为「中」风险；已生成但不合规的仍显示「高」。

---

### 提示词 P8（对应 F8）：前端支持创建项目级（scope=project）资料

**目标**：让前端能上传项目级专属企业资料，使两级隔离（company/project）真正可用。
**上下文**：后端 `knowledge.py` 支持 `scope`/`project_id`，但前端 `materials.js` 上传仅传 `file/category/tags`（默认 company 级），`CompanyMaterialsView.vue` 无 scope 选择 → `project` scope 资料永远为空。
**改动**：
1. `frontend/src/api/materials.js` 上传函数增加可选参数 `scope`（默认 `"company"`）与 `projectId`，并在 `formData` 中带上 `scope` 与 `project_id`。
2. `CompanyMaterialsView.vue` 上传表单增加 `scope` 选择（公司级/项目级）；选「项目级」时显示项目选择器并传 `projectId`。
**约束**：后端接口签名已支持，无需改后端；不删除 company 级默认行为。
**验证**：上传一条 project 级资料，后端 `company_documents` 表 `scope='project'` 且 `project_id` 非空；检索时按 scope 隔离生效。

---

### 提示词 P9（对应 F9）：提交投标按钮明确未开放

**目标**：消除「提交投标」伪装成成功（"功能开发中"）的误导。
**上下文**：`frontend/src/views/ProjectDetailView.vue` `handleSubmitBid`（约 903 行）最后 `ElMessage.success('投标提交功能开发中')`，无后端接口。
**改动（保守方案，不新增后端）**：将末尾成功提示改为明确提示未开放，并 disable 按钮：
```js
// handleSubmitBid 末尾
ElMessage.info('投标提交功能暂未开放')
```
同时在模板 `<el-button ... @click="handleSubmitBid" :disabled="true">提交投标</el-button>` 加 `:disabled="true"`（或加 `disabled` 属性）。
**约束**：不新增后端端点；仅前端诚实化；高风险/就绪度校验逻辑保留在前面。
**验证**：点「提交投标」→ 提示「暂未开放」，按钮置灰，不再显示成功。

---

### 提示词 P10（对应 F10 + F18）：批量删除需求改为真实调用

**目标**：修复「批量删除需求」假成功（只弹提示不调接口，数据未删）的数据误导 bug。
**上下文**：`ProjectDetailView.vue:777 handleBatchDeleteRequirements` 仅 `ElMessage.success` 无 API 调用。后端 `requirements.router` 也无批量删除端点（现有 `projects.js` 有 `deleteRequirementApi` 单条 PATCH/DELETE 雏形但无批量）。
**改动**：
1. 后端新增端点（在 `requirements` 路由文件，如 `backend/app/api/routes/requirements.py` 或 `responses.py` 所属 router）：
```python
@router.delete("/projects/{project_id}/batch")
def batch_delete_requirements(project_id: int, payload: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    ids = payload.get("ids", [])
    if ids:
        db.query(Requirement).filter(Requirement.project_id == project_id, Requirement.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
    return ApiResponse(data={"deleted": len(ids)})
```
2. 前端 `frontend/src/api/projects.js` 增加 `batchDeleteRequirementsApi(projectId, ids)` → `api.delete(\`/requirements/projects/${projectId}/batch\`, { data: { ids } })`。
3. `handleBatchDeleteRequirements` 改为：
```js
const res = await batchDeleteRequirementsApi(projectId, ids)
if (res?.code === 0 || res?.success) ElMessage.success(`已删除 ${ids.length} 项需求`)
else ElMessage.error('批量删除失败')
await loadRequirements()
```
**约束**：路由前缀需与现有 `requirements` router 一致（现有接口用 `/requirements/...`）；确认 `projectId` 在组件作用域内可用；删除需校验 `owner_id`（复用 `get_project_or_404_sync` 或现有依赖）。
**验证**：勾选多条需求批量删除 → 列表真实移除；刷新后不再出现。

---

### 提示词 P11（对应 F11）：批量更新需求状态真实化

**目标**：修复「批量更新需求状态」Stub（"批量更新功能开发中"）。
**上下文**：`ProjectDetailView.vue:749 handleUpdateStatus` 中 `reqId === '_batch'` 分支直接 `ElMessage.info('批量更新功能开发中')` 返回，无后端接口。
**改动**：
1. 后端新增 `PATCH /requirements/projects/{project_id}/batch-status`，body `{"status": "待评审"}`：
```python
@router.patch("/projects/{project_id}/batch-status")
def batch_update_status(project_id: int, payload: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    new_status = payload.get("status")
    n = db.query(Requirement).filter(Requirement.project_id == project_id).update({"status": new_status}, synchronize_session=False)
    db.commit()
    return ApiResponse(data={"updated": n})
```
2. 前端 `projects.js` 增加 `batchUpdateStatusApi(projectId, status)` → `api.patch(\`/requirements/projects/${projectId}/batch-status\`, { status })`。
3. `handleUpdateStatus` 的 `_batch` 分支改为调用该 API 后 `loadRequirements()`。
**约束**：status 值需落在 `Requirement.status` 合法枚举（"未处理"/"待评审"/"已完成" 等）；路由前缀同 P10。
**验证**：在需求列表选「批量更新状态」→ 全部需求状态变更且前端刷新一致。

---

### 提示词 P12（对应 F12）：企业资料管理假按钮诚实化

**目标**：消除 `CompanyMaterialsView.vue` 中 `reindexDocument`/`handleRetryMaterial`/`handleLocateSource`/`handleSearch` 的假进度/假数据误导。
**上下文**：`reindexDocument` 仅刷新列表；`handleRetryMaterial` 仅延时刷新；`handleLocateSource` 弹「开发中」；`handleSearch` 用 `Math.random()` 造 `latency` 假数据。
**改动**（务实方案，二选一，推荐 A）：
- A（标注未实现，避免误导）：上述函数改为 `ElMessage.info('该功能暂未实现')`，并对应按钮加 `disabled` 或移除；`handleSearch` 改为对本地已加载列表做前端关键字过滤（真实可用），去掉 `Math.random()`。
- B（实现真实逻辑）：`reindexDocument` 调后端重新切分+Embedding 端点；`handleRetryMaterial` 调重新解析接口；`handleLocateSource` 打开该资料来源文档；需后端配合（超出本提示词范围，选 A 即可）。
**约束**：只改 `CompanyMaterialsView.vue`；不新增后端（选 A）；保持页面可正常加载。
**验证**：点击这些按钮不再显示虚假进度/随机延迟，提示明确或做真实前端过滤。

---

### 提示词 P13（对应 F13 + F15）：明确 Agent 编排流水线定位，避免重复生成

**目标**：解决主 UI（`routes/responses.py`+`routes/compliance.py`）与 `agents/` 编排层（`workflow.py`）两条平行流水线数据不互通、可能重复生成的问题。
**上下文**：`backend/app/api/routes/workflow.py` + `backend/app/agents/*` 仅由 `/projects/{id}/run-workflow` 触发，与主详情页走另一条线；因 P3 未回写 `Requirement.status`，`rag_agent` 重跑过滤器失效，两线并用时同需求可能生成两次。
**改动**（最小稳妥方案）：
1. 在 `workflow.py` 的 `run-workflow` 端点与前端 `run-workflow` 按钮处加注释/提示：「实验性编排流水线，与主 UI 生成通道并行；正式使用请以主 UI 为准」，并在前端将该按钮标记为「Beta」或默认隐藏。
2. 确保 `agents/rag_agent.py` 的重跑过滤使用 `Requirement.status.notin_(["待评审","已完成","completed"])`（依赖 P3 回写生效），作为去重依据。
**约束**：不删除 `agents/` 代码；不改动主 UI 生成逻辑；P3 须先落地才能让过滤生效。
**验证**：主 UI 批量生成后，`run-workflow` 仅处理 status 非「待评审/已完成」的需求，不重复生成。

---

### 提示词 P14（对应 F14 + 支撑 P16）：接通 RAG 真实向量链路（注入 EmbeddingClient）

**目标**：让 `VectorStoreService` 真正使用 Embedding 做 Milvus 向量写入/检索，而非永远走 n-gram 降级。
**上下文**：`backend/app/services/vector_store.py` 第 895 行 `vector_store_service = VectorStoreService()` 未注入 `embedding_client`（默认 `None`）→ `search()` 第 298 行 `_embedding_client is None` 恒真走 `_ngram_search`；`_upsert_to_milvus` 第 461 行因 `embedding_client is None` 直接 return，Milvus 从未写入。全应用从未实例化 `EmbeddingClient`。`EmbeddingClient(api_key, model="text-embedding-v3")` 已存在于 `llm_client.py`；配置 `settings.DASHSCOPE_API_KEY`、`settings.EMBEDDING_MODEL` 可用。
**改动**：修改 `vector_store.py` 末尾单例初始化，注入 embedding_client（与 chat_client 供 P16 使用）：
```python
from app.core.config import settings
from app.services.llm_client import EmbeddingClient, OpenAIChatClient

_embedding_client = None
_chat_client = None
if getattr(settings, "DASHSCOPE_API_KEY", None):
    try:
        _embedding_client = EmbeddingClient(api_key=settings.DASHSCOPE_API_KEY, model=settings.EMBEDDING_MODEL)
    except Exception:
        _embedding_client = None
    try:
        _chat_client = OpenAIChatClient(api_key=settings.DASHSCOPE_API_KEY)
    except Exception:
        _chat_client = None

vector_store_service = VectorStoreService(embedding_client=_embedding_client, chat_client=_chat_client)
```
**约束**：仅在 `DASHSCOPE_API_KEY` 存在时注入，缺失时仍走 n-gram 降级（不报错）；不改动 `VectorStoreService` 类其他方法；Milvus 连接保持延迟初始化。`requirements.txt` 需含 `openai`（EmbeddingClient 已依赖）。
**验证**：上传资料并触发切分后，查 Milvus/`vectors.json` 应有真实 embedding 向量；`search()` 走向量检索路径（日志或返回更语义化结果）。

---

### 提示词 P16（对应 F16）：资料对齐接口改用高级语义缺口分析

**目标**：让「资料对齐/缺口分析」接口真正调用已实现的 `match_requirement_to_materials`（LLM coverage/confidence/gap），而非简化版 `retrieval_service.search`。
**上下文**：`backend/app/api/routes/responses.py` 的 `analyze_requirement_matches` 用 `retrieval_service.search(top_k=3)` 简化匹配；而 `vector_store.py:568 match_requirement_to_materials` 已实现 LLM 结构化输出但未被任何路由接线。它依赖 `self._chat_client`（由 P14 注入单例后可用），失败有降级返回 `None`。
**改动**：在 `analyze_requirement_matches` 中，对每个需求调用：
```python
from app.services.vector_store import vector_store_service
result = vector_store_service.match_requirement_to_materials(req.content, materials_text)
# result: {"coverage":"full|partial|missing","confidence":float,"evidence":[...],"gap":str|null,"reason":str} 或 None
```
将 `result` 的 `coverage`/`gap`/`confidence` 合并进原返回结构（保留 `has_match`/`match_score`/`matched_sources` 字段，缺口信息补充到 `gap` 字段）。命中 `coverage=="missing"` 时 `has_match=False`。
**约束**：依赖 P14 先注入 `chat_client`；`match_requirement_to_materials` 需 `materials_text`（项目级+公司级资料文本拼接，可复用现有检索/加载逻辑）；LLM 失败（`None`）时回落到原 `retrieval_service.search` 结果，不阻断接口。
**验证**：对有/无资料的需求跑对齐接口，返回含 `coverage`/`gap`；缺失资料需求 `has_match=False` 且带 `gap` 说明。

---

### 提示词 P17（对应 F17）：清理死代码、修正 CORS 与失效配置

**目标**：消除死代码、生产不安全 CORS、失效配置项。
**上下文**：
- `api/routes/company_documents.py`、`api/routes/retrieval.py`、`main_c.py`、`components/TenderUploadPanel.vue` 未被引用（冗余）。
- `main.py` CORS `allow_origins=["*"] + allow_credentials=True` 违反规范（Starlette 会反射 Origin）。
- `core/config.py:LLM_MODEL_NAME="qwen-max"` 未被 `OpenAIChatClient` 使用（其默认 `qwen-flash-2025-07-28`）。
**改动**：
1. CORS：将 `allow_origins` 改为具体前端 origin 列表（如 `["http://localhost:5173"]`，从环境变量 `CORS_ORIGINS` 读取，逗号分隔），保留 `allow_credentials=True`；或若无需凭证则 `allow_credentials=False` 且可用 `"*"`。
2. 配置：删除或统一 `LLM_MODEL_NAME`——若想让它生效，在 `OpenAIChatClient(api_key=..., model=settings.LLM_MODEL_NAME)` 处引用；否则从 config 删除该字段。
3. 死代码：确认无 import 后，将未被引用的文件移入 `backend/obsolete/`（或加 `# noqa` 注释标明未使用），`TenderUploadPanel.vue` 同样移出或删除 `simulateUpload` 假进度函数。
**约束**：删除/移动文件前确认无跨模块 import（用全局搜索确认）；CORS 改动后前端本地调试 origin 需匹配；不改动业务逻辑。
**验证**：启动后端无 import 报错；CORS 预检返回具体 Origin 而非 `*`；`LLM_MODEL_NAME` 要么被引用要么已删除。

---

> 说明：F4（双重 delete）已并入 P1；F18（前端假删除/假进度）已并入 P10 与 P12/P17。所有提示词均只做最小必要改动、不破坏现有主流程，可直接分别提交给 AI 编码工具执行。
