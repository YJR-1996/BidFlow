# BidFlow Agent 架构详解

> 版本：2026-08-06 · 基于 `backend/app/agents/` 与 `backend/app/services/` 实际代码梳理
> 定位：系统采用**编排式多 Agent（Orchestrator Pattern）**架构，另有一条独立的语义合规 Agent 通道。

---

## 1. 架构总览

BidFlow 中存在**两套 Agent 体系**：

| 体系 | 位置 | 角色 | 运行方式 |
|---|---|---|---|
| **主编排链路** | `backend/app/agents/` | Orchestrator + 4 个 Sub-Agent | 固定流水线 `parse → decompose → rag → compliance`，后台线程执行，支持人工审核中断/恢复 |
| **独立语义 Agent** | `backend/app/services/semantic_compliance_agent.py` | SemanticComplianceAgent | 不参与编排，作为合规检查的"后置增强"，独立按条调用 |

设计哲学（`agents/__init__.py` 原注释）：**Agent 均为薄壳，只做编排与状态传递，业务逻辑全部委托复用现有 Service，不重写。**

```mermaid
flowchart TB
    subgraph 入口["入口层 (api/routes/workflow.py)"]
        POST["POST /run-workflow<br/>POST /workflow/{id}/resume"]
        DB[(WorkflowRun 表<br/>context_json 持久化)]
    end

    subgraph 编排层["编排层 (app/agents/)"]
        ORCH["Orchestrator 编排器<br/>STAGE_ORDER = parse→decompose→rag→compliance"]
        CTX["WorkflowContext<br/>共享上下文 (dataclass)"]
        TOOL["ToolRegistry<br/>统一 LLM / 检索入口"]
        P["ParseAgent"] --> D["DecomposeAgent"] --> R["RAGAgent"] --> C["ComplianceAgent"]
    end

    subgraph 服务层["服务层 (app/services/) —— 业务委托"]
        S1["document_parser<br/>tender_requirement_extractor"]
        S2["auxiliary_requirement_service"]
        S3["batch_task_service<br/>retrieval_service + ResponseGenerationService"]
        S4["compliance_checker<br/>+ semantic_compliance_agent"]
    end

    subgraph 底座["模型底座 (app/services/llm_client.py)"]
        LLM["OpenAIChatClient<br/>qwen 系列 (DashScope 兼容接口)"]
        EMB["EmbeddingClient<br/>text-embedding-v3"]
    end

    POST --> ORCH
    ORCH --> CTX
    ORCH --> TOOL
    P --> S1
    D --> S2
    R --> S3
    C --> S4
    TOOL --> LLM
    S1 --> EMB
    S3 --> LLM
    S3 --> EMB
    S4 --> LLM
    ORCH --> DB
    DB -. 断点续跑 .-> POST
```

---

## 2. 核心机制

### 2.1 WorkflowContext —— 阶段间共享状态

定义于 `app/agents/base.py`，是贯穿全流水线的**单一数据载体**：

```python
@dataclass
class WorkflowContext:
    project_id: int
    owner_id: str
    stages_done: List[str]              # 已完成的阶段（Orchestrator 统一追加）
    requirements: List[Dict]            # parse 阶段产出，下游消费
    retrieval_task_id: Optional[str]    # rag 阶段的异步批处理任务号
    compliance_issues: List[Dict]       # compliance 阶段产出
    human_review_required: bool         # 人工审核开关（合规高风险置 True）
    review_reason: str
    metadata: Dict[str, Any]
```

**数据流**：`ParseAgent` 填 `requirements` → `RAGAgent` 填 `retrieval_task_id` → `ComplianceAgent` 填 `compliance_issues`，一个对象贯穿全程。

### 2.2 ToolRegistry —— 统一能力入口

所有 Agent 通过 `ToolRegistry` 获取模型能力，避免各自实例化：

```python
class ToolRegistry:
    def llm(self):
        """返回 LLM 客户端（lazy 实例化）"""
        return OpenAIChatClient(api_key=..., model=settings.LLM_MODEL_NAME)
    # self.retrieval_service 也挂在注册表上
```

### 2.3 编排调度与人工审核中断（Human-in-the-loop）

`app/agents/orchestrator.py` 顺序调用各 Agent，**发现高风险合规问题立即中断**：

```python
for stage_name in self.STAGE_ORDER[start_index:]:
    new_ctx = agent.run(ctx, db)
    new_ctx.stages_done.append(stage_name)
    if new_ctx.human_review_required:   # ← ComplianceAgent 置位
        break                            # 立即中断后续阶段
```

```mermaid
flowchart LR
    START(["run-workflow"]) --> S0{"start_stage<br/>是否合法?"}
    S0 -- 否 --> ERR["抛 ValueError"]
    S0 -- 是 --> S1["parse<br/>解析招标文件→抽取需求"]
    S1 --> CHK1{"human_review<br/>required?"}
    CHK1 -- 是 --> PAUSE["暂停 awaiting_review"]
    CHK1 -- 否 --> S2["decompose<br/>生成辅助需求"]
    S2 --> CHK2{"human_review<br/>required?"}
    CHK2 -- 是 --> PAUSE
    CHK2 -- 否 --> S3["rag<br/>检索+生成响应 (异步)"]
    S3 --> CHK3{"human_review<br/>required?"}
    CHK3 -- 是 --> PAUSE
    CHK3 -- 否 --> S4["compliance<br/>规则引擎合规检查"]
    S4 --> CHK4{"high 风险 > 0?"}
    CHK4 -- 是 --> PAUSE
    CHK4 -- 否 --> DONE(["completed"])
    PAUSE --> RESUME["人工审核通过 →<br/>POST /resume?next_stage=..."]
    RESUME --> S2
```

**WorkflowRun 状态机**：

```mermaid
stateDiagram-v2
    [*] --> running: 创建 WorkflowRun
    running --> awaiting_review: 合规高风险中断
    running --> completed: 全部阶段完成
    running --> failed: 异常（先回滚再标记）
    awaiting_review --> running: resume（清除 review 标记）
    failed --> [*]
    completed --> [*]
```

---

## 3. 四个 Sub-Agent 详解

### 3.1 ParseAgent —— 招标文件解析

```mermaid
flowchart LR
    A["查 TenderDocument<br/>project_id=ctx.project_id<br/>status != 'parsed'"] --> B["document_parser.parse()<br/>PDF三级降级/TXT/DOCX"]
    B --> C["extractor.extract()<br/>抽取需求写 requirements 表"]
    C --> D["doc.status = 'parsed'"]
    D --> E["填 ctx.requirements<br/>(id/content/category/priority/...)"]
    B -. 单文档异常 .-> F["logger.exception + continue<br/>跳过继续下一个"]
```

- 遍历是 **DB 驱动**（`db.query(...).filter(...).all()`），非文件系统递归
- 单文档失败**静默跳过**（`except Exception: continue`），不标记 failed，下次 run 会重试

### 3.2 DecomposeAgent —— 需求分解

- 委托 `auxiliary_requirement_service.generate(db, project_id)` 生成辅助需求
- 数量记入 `ctx.metadata["decomposed_count"]`

### 3.3 RAGAgent —— 检索增强生成（异步）+ Reflexion 质量闭环

```mermaid
flowchart LR
    A["查未生成响应的需求<br/>status NOT IN (待评审/已完成/completed)"] --> B["batch_task_service.start_batch()<br/>起后台线程"]
    B --> C["ctx.retrieval_task_id = task_id"]
    B -. 线程内 .-> D["retrieval_service.search()<br/>top_k=5 混合召回(带降级)"]
    D --> E["ResponseGenerationService.generate()<br/>LLM 生成响应"]
    E --> F["reflexion_evaluator.evaluate()<br/>LLM 质量评估"]
    F --> G{"passed?"}
    G -- 是 --> H["写 response 表<br/>(pending_review)"]
    G -- 否 --> I["reflexion_evaluator.refine()<br/>带反馈重写<br/>+ 检索扩到 top_k=8"]
    I --> F
```

- **编排不等待**：批处理任务逐步递进写库，编排侧只需拿到 `task_id`
- 批处理实现：`threading + 内存字典`（单实例足够，无 Celery/Redis 依赖）
- **Reflexion 质量闭环（2026-08-06 新增）**：生成后 LLM 评估响应是否充分满足招标要求；不达标则带评估反馈重写（重写轮检索扩到 `top_k=8` 提供更多素材），最多 `REFLEXION_MAX_ROUNDS`（默认 2）轮。评估/重写任何失败**静默降级为通过**，绝不阻断生成链路。配置：`REFLEXION_ENABLED` / `REFLEXION_MAX_ROUNDS` / `REFLEXION_RETRY_TOP_K`
- 实现位置在 `batch_task_service._process_one`（公共通道），**RAGAgent 与主 UI 批量生成两条路径同时受益**

### 3.4 ComplianceAgent —— 合规检查

- 查项目全部需求 → `build_snapshots_from_requirements()` 构建快照（取每条需求**最新响应**的 status/content）
- 委托 `ComplianceChecker().check(snapshots)`（**确定性规则引擎**）
- 产出 `ctx.compliance_issues`；**high 风险 > 0 → 置 `human_review_required=True` 中断流水线**

---

## 4. 入口与持久化（workflow.py 路由）

| 接口 | 作用 |
|---|---|
| `POST /{project_id}/run-workflow?start_stage=parse` | 创建 `WorkflowRun`（running）→ 启动 daemon 线程执行编排，立即返回 `{run_id, status}` |
| `GET /{project_id}/workflow/{run_id}` | 查询运行状态与上下文摘要 |
| `POST /{project_id}/workflow/{run_id}/resume?next_stage=rag` | 仅 `awaiting_review` 状态可调用，清除 review 标记后从指定阶段续跑 |
| `GET /{project_id}/workflow-runs` | 列出项目全部运行记录 |

**关键实现细节**：

- **后台线程自建独立数据库会话**：`create_engine(sync_url)` + 独立 `sessionmaker`，不占用主请求的 DB 会话（长任务隔离）
- `finally` 中 `local_engine.dispose()` 释放连接池，避免每次运行泄漏一池连接
- 上下文序列化 JSON 存 `WorkflowRun.context_json` → **断点续跑**（resume 时从 JSON 恢复 ctx）
- 状态落库：`running / awaiting_review / completed / failed`，`current_stage = stages_done[-1]`

---

## 5. 独立通道：SemanticComplianceAgent

不参与编排，在**规则引擎之后**对每条「需求-响应」调用 LLM 做语义级风险检测，带四层防御：

```mermaid
flowchart TD
    A["规则引擎判罚后<br/>单条需求-响应"] --> B{"SEMANTIC_COMPLIANCE_ENABLED<br/>且 API Key 已配置?"}
    B -- 否 --> Z["直接返回空列表"]
    B -- 是 --> C["LLM chat_json<br/>qwen 系列语义风险分析"]
    C --> D{"confidence<br/>&lt; 0.6?"}
    D -- 是 --> Z
    D -- 否 --> E{"命中黑名单关键词?<br/>(质量保证/业绩/近三年/年份...)"}
    E -- 含否定词(未提供/缺少/无法...) --> F["保留上报<br/>(真实风险不抑制)"]
    E -- 无否定词 --> Z
    E -- 未命中 --> G["等级封顶: high→medium<br/>high 只由规则引擎产出"]
    G --> H["输出 SEMANTIC_* 风险"]
    F --> H
```

| 防御层 | 规则 | 目的 |
|---|---|---|
| 1. 开关与 Key 检查 | `SEMANTIC_COMPLIANCE_ENABLED` + `DASHSCOPE_API_KEY` | 未配置直接跳过 |
| 2. 置信度过滤 | `confidence < 0.6` 丢弃 | LLM 不确定的不报 |
| 3. 黑名单抑制 | 命中"质量保证/业绩案例/近三年/年份"等词丢弃；**含否定词（未提供/缺少/无法）不抑制** | 防时间/业绩/质保类误报 |
| 4. 等级封顶 | 语义 Agent 最高 `medium`，`high` 仅由规则引擎产出 | 保证高风险可信度 |

任何 LLM 失败**静默降级**为仅规则引擎，不影响主流程。

---

## 6. 模型底座（llm_client.py）

| 客户端 | 模型 | 能力 |
|---|---|---|
| `OpenAIChatClient` | qwen 系列（`LLM_MODEL_NAME` 配置） | `chat` / `chat_vision`（OCR）/ `chat_json`（语义合规）/ `chat_with_tools`，OpenAI 兼容协议对接 DashScope |
| `EmbeddingClient` | `text-embedding-v3` | 文档向量化、检索召回 |

---

## 7. 已知风险与改进建议

1. ~~**ParseAgent 静默跳过**：单文档异常 `continue` 不写 `failed` 状态，导致"静默丢失 + 下次全量重试"。~~ ✅ **已修复（2026-08-06）**：失败置 `doc.status="failed" + error_message`；筛选白名单改为 `status.in_(["pending", "processing"])`，`failed`/`success` 不再重试；成功状态由 `parsed` 统一为 `success`（与路由/前端契约一致，前端兼容旧 `parsed`）。
2. ~~**ComplianceAgent `source_refs` 硬编码为空**：语义合规 Agent 拿不到来源引用。~~ ✅ **已修复（2026-08-06）**：`build_snapshots_from_requirements` 改用 `parse_source_refs(resp.source_refs)` 解析真实引用，并补 `needs_manual`/`待人工补充` 强制清空双保险（与主通道 `compliance.py` 对齐）。修复前 agent 通道对未完成 P0 会**误报 `P0_SOURCE_MISSING`（high）中断流水线**，且时有时无难排查。
3. **RAG 阶段与主 UI 通道的关系**：该编排标注 **Beta · 实验性**，正式使用以主 UI（需求列表 → 批量生成响应）为准，编排适合自动化测试 / 无人值守场景。
4. **`ctx.requirements` 被 ComplianceAgent 覆盖**：ComplianceAgent 把 `serialized`（全量需求）重新赋给 `ctx.requirements`，与 parse 阶段语义不同（全量 vs 新增），下游需注意。
