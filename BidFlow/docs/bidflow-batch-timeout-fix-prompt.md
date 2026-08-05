# 任务提示词：修复 BidFlow「为已匹配需求批量生成响应」批量接口超时

> 以下提示词可直接整体复制到 Trae（或任意 AI 编码工具）执行，无需补充任何其他背景。

---

## 一、明确目标

将后端批量生成接口从「单次 HTTP 请求内同步串行完成所有需求的 LLM 生成」改造为「提交即返回任务 ID、后台线程逐条生成、前端轮询进度」的异步模式，彻底解决：点击「为已匹配需求批量生成响应」按钮后，前端在 30 秒超时断开、但后端其实还在慢慢跑的问题。

顺带修正两个已知缺陷（与本次超时同源，一并处理）：
1. **语义修正**：批量生成只处理「已匹配企业资料」的需求；未匹配的需求跳过并标注，不再生成占位内容计入。
2. **LLM 失败降级**：单条生成接口有 LLM 失败的模板降级，批量接口没有——改为在后台任务中捕获 LLM 异常并写入 `needs_manual` 占位内容、继续下一条，不再因一次 LLM 超时把整批卡死。

---

## 二、上下文信息（现有实现，请勿破坏）

### 2.1 超时根因（为什么现在必然超时）

- **前端硬墙**：`frontend/src/api/client.js` 第 6 行 `timeout: 30000`（axios 全局 30 秒）。任何请求 30 秒没响应就被前端断开并提示「超过响应时间」。
- **后端同步串行**：`backend/app/api/routes/responses.py` 中的 `batch_generate_responses`（路由 `POST /projects/{project_id}/batch-generate`）在**同一个请求里 for 循环**处理项目全部需求，每条需求依次执行：
  1. `retrieval_service.search(...)` —— Milvus 向量检索，约 0.5–2 秒（快）；
  2. 若有命中 → `ResponseGenerationService.generate(...)` → 内部 `OpenAIChatClient.chat(...)` 调用 DashScope `qwen` 模型。
- **单次 LLM 调用最坏耗时**：`backend/app/services/llm_client.py` 中 `OpenAIChatClient(timeout=30.0, max_retries=2)`，单次调用最坏 = `30s × (1 + 2次重试) = 90 秒`。
- **数学结论**：8 个已匹配需求 ×（最快 5s / 最坏 90s）= 40~720 秒，**前端在第 30 秒必然断开**。截图按钮显示「(8)」即 8 个已匹配需求。

### 2.2 现有关键代码（改之前请先读）

文件 `backend/app/api/routes/responses.py`（路由前缀为 `/requirements`，由 main.py 挂载；前端调用路径为 `/api/requirements/projects/{id}/batch-generate`）：

```python
@router.post("/projects/{project_id}/batch-generate")
def batch_generate_responses(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """为项目所有未生成响应的需求批量生成AI响应"""
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id,
    ).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")

    requirements = db.query(Requirement).filter(
        Requirement.project_id == project_id
    ).all()
    if not requirements:
        raise BusinessException(message="该项目暂无需求项")

    from app.services.retrieval_service import retrieval_service
    from app.core.config import settings
    from app.services.llm_client import OpenAIChatClient
    from app.services.response_generation_service import ResponseGenerationService

    llm_client = OpenAIChatClient(api_key=settings.DASHSCOPE_API_KEY)
    gen_service = ResponseGenerationService(llm_client)

    results = {"generated": 0, "skipped": 0, "failed": 0, "items": []}

    for req in requirements:                       # ← 同步串行，是超时根源
        existing = db.query(BidResponse).filter(
            BidResponse.requirement_id == req.id).first()
        if existing and (existing.ai_content or existing.edited_content):
            results["skipped"] += 1
            results["items"].append({"requirement_id": req.id, "status": "skipped", "message": "已有响应，跳过"})
            continue
        try:
            sources = retrieval_service.search(query=req.content or "", project_id=project_id, top_k=5)
            source_dicts = list(sources) if sources else []
            if not source_dicts:
                resp = BidResponse(requirement_id=req.id,
                                   ai_content="待人工补充：未检索到可引用的企业资料。",
                                   status="needs_manual")
                db.add(resp)
                results["generated"] += 1
                results["items"].append({"requirement_id": req.id, "status": "needs_manual", "message": "未检索到企业资料，需人工补充"})
                continue
            result = gen_service.generate(
                requirement={"content": req.content or "", "category": req.category or ""},
                sources=source_dicts)
            resp = BidResponse(requirement_id=req.id, ai_content=result.content,
                               source_refs=str(source_dicts), status=result.status)
            db.add(resp)
            results["generated"] += 1
            results["items"].append({"requirement_id": req.id, "status": result.status, "message": result.message})
        except Exception as e:
            results["failed"] += 1
            results["items"].append({"requirement_id": req.id, "status": "failed", "message": str(e)})

    db.commit()
    return ApiResponse(data=results)
```

### 2.3 复用的现有模块（不要重写，直接 import 使用）

- `backend/app/services/retrieval_service.py` → `retrieval_service.search(query, project_id=None, top_k=5)`：返回 list[dict]，每项含 `content/score/filename/material_type/source_ref/scope`；空列表表示无命中。
- `backend/app/services/response_generation_service.py` → `ResponseGenerationService(llm_client).generate(requirement: dict, sources: list) -> GenerationResult(content, sources, status, message)`；`sources` 为空时直接返回 `needs_manual` 占位。
- `backend/app/services/llm_client.py` → `OpenAIChatClient(api_key, model="qwen-flash-2025-07-28", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", timeout=30.0, max_retries=2)`；异常类型 `LlmServiceError`（从 `app.services.llm_client` 导入）。
- 配置：`from app.core.config import settings`，API Key 为 `settings.DASHSCOPE_API_KEY`。
- 数据库：`from app.db.session import get_db`（请求作用域同步 Session）。后台线程**必须自建**同步 Session，使用 `app.db.session` 中导出的同步会话工厂（通常是 `SessionLocal()`，若不存在请在 `app/db/session.py` 中按现有引擎补一个 `SessionLocal = sessionmaker(...)`）；不要复用请求作用域的 `db` 依赖。
- 模型：`Requirement`（`app/models/requirement.py`，字段 `id, project_id, content, category, priority, status`）、`BidResponse`（`app/models/response.py`，字段 `requirement_id, ai_content, edited_content, source_refs, status`）、`BidProject`（`app/models/bid_project.py`，含 `owner_id`）。
- 统一返回封装：`from app.schemas.common import ApiResponse`；异常：`from app.core.exceptions import NotFoundException, BusinessException`。
- 单条生成接口 `POST /{requirement_id}/response/generate` 与 `GET /projects/{project_id}/match-analysis` **保持不变**。

### 2.4 前端现有调用（改之前请先读）

- `frontend/src/api/client.js`：`axios.create({ baseURL: '/api', timeout: 30000 })`，**本次不要改这个全局超时**。
- `frontend/src/api/compliance.js`：`batchGenerateResponses(projectId)` → `api.post('/requirements/projects/${projectId}/batch-generate')`。
- `frontend/src/views/ProjectDetailView.vue`：按钮「✨为已匹配需求批量生成响应 ({{ comparisonData.summary.matched }})」仅在 `comparisonData.summary.matched > 0` 时显示；点击调用 `handleBatchGenerateFromComparison()` → `batchGenerateResponsesApi(projectId.value)` → 成功后 `loadRequirements()`。
- `frontend/src/components/RequirementTable.vue`：另有「批量生成响应」按钮，采用同样接口；本次如需可一并按相同模式改造（非强制）。

---

## 三、约束条件

1. **不引入新依赖**：不要加 Celery / Redis / RabbitMQ / 数据库任务表。用进程内 `threading` + 内存字典保存任务状态即可（单实例部署足够；如未来多实例再升级）。
2. **复用现有服务**：检索、生成、LLM 客户端一律复用第二节列出的模块，不重写逻辑。
3. **后台线程自建 DB Session**：在 `_run_batch` 内 `db = SessionLocal()`，每条需求生成后 `db.commit()`，函数末尾 `db.close()`；严禁把请求作用域的 `db` 传进线程。
4. **不改动表结构**：`Requirement` / `BidResponse` / `BidProject` 字段保持不变。
5. **不破坏现有接口**：单条生成、match-analysis、前端其它功能保持可用。
6. **只处理已匹配需求**：用 `retrieval_service.search` 返回的列表是否非空判断「已匹配」；未匹配的计入 skipped（message="未匹配企业资料，跳过"），不写入 `needs_manual` 占位。
7. **LLM 调用须设边界**：后台任务内 `OpenAIChatClient(api_key=..., timeout=25.0, max_retries=1)`；用 `try/except LlmServiceError` 包裹，异常时写 `needs_manual` 占位「待人工补充：未检索到可引用的企业资料。」并继续下一条，不让单条失败中断整批。
8. **前端不改全局超时**：start 接口会 < 1 秒返回，不会触发 30s 墙；若想更稳，可对 start 调用单独 `timeout: 0`，但不要动 `client.js`。

---

## 四、输出规范（要交付的改动）

### 4.1 后端

**A. 任务状态存储**（在 `responses.py` 内新建，或新建 `backend/app/services/batch_task_manager.py` 再 import）：

```python
import threading, uuid, time
from typing import Dict, Any

TASKS: Dict[str, Dict[str, Any]] = {}
_TASK_LOCK = threading.Lock()

def _update_task(task_id: str, **fields):
    with _TASK_LOCK:
        TASKS.setdefault(task_id, {})
        TASKS[task_id].update(fields)
        TASKS[task_id]["updated_at"] = time.time()
```

每条任务记录字段：`task_id, project_id, status('pending'|'processing'|'completed'|'partial'|'failed'), total, processed, generated, skipped, failed, items(list), error, created_at, updated_at`。

**B. 改造 `batch_generate_responses`**：仅做项目存在 + 所有者校验（沿用 `BidProject.owner_id == current_user.id`），立即生成 `task_id = uuid.uuid4().hex`，写入初始记录，启动线程并返回：

```python
@router.post("/projects/{project_id}/batch-generate")
def batch_generate_responses(project_id: int,
                             current_user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")
    if not db.query(Requirement).filter(Requirement.project_id == project_id).first():
        raise BusinessException(message="该项目暂无需求项")

    task_id = uuid.uuid4().hex
    _update_task(task_id, task_id=task_id, project_id=project_id,
                 status="pending", total=0, processed=0,
                 generated=0, skipped=0, failed=0, items=[],
                 error=None, created_at=time.time())
    threading.Thread(target=_run_batch, args=(project_id, task_id),
                     daemon=True).start()
    return ApiResponse(data={"task_id": task_id, "status": "pending"})
```

**C. 新增后台函数 `_run_batch(project_id, task_id)`**：

```python
def _run_batch(project_id: int, task_id: str):
    from app.db.session import SessionLocal
    from app.services.retrieval_service import retrieval_service
    from app.core.config import settings
    from app.services.llm_client import OpenAIChatClient, LlmServiceError
    from app.services.response_generation_service import ResponseGenerationService
    from app.models.requirement import Requirement
    from app.models.response import Response as BidResponse

    db = SessionLocal()
    try:
        _update_task(task_id, status="processing")
        requirements = db.query(Requirement).filter(
            Requirement.project_id == project_id).all()
        _update_task(task_id, total=len(requirements))

        llm_client = OpenAIChatClient(api_key=settings.DASHSCOPE_API_KEY,
                                      timeout=25.0, max_retries=1)
        gen_service = ResponseGenerationService(llm_client)

        for req in requirements:
            try:
                sources = retrieval_service.search(query=req.content or "",
                                                   project_id=project_id, top_k=5)
                source_dicts = list(sources) if sources else []
                # 仅处理已匹配需求
                if not source_dicts:
                    _update_task(task_id, skipped=_TASKS_INC(task_id, "skipped"),
                                processed=_TASKS_INC(task_id, "processed"))
                    # 把 skipped 项追加进 items
                    _append_item(task_id, req.id, "skipped", "未匹配企业资料，跳过")
                    continue
                existing = db.query(BidResponse).filter(
                    BidResponse.requirement_id == req.id).first()
                if existing and (existing.ai_content or existing.edited_content):
                    _update_task(task_id, skipped=_TASKS_INC(task_id, "skipped"),
                                processed=_TASKS_INC(task_id, "processed"))
                    _append_item(task_id, req.id, "skipped", "已有响应，跳过")
                    continue
                try:
                    result = gen_service.generate(
                        requirement={"content": req.content or "",
                                     "category": req.category or ""},
                        sources=source_dicts)
                    resp = BidResponse(requirement_id=req.id,
                                       ai_content=result.content,
                                       source_refs=str(source_dicts),
                                       status=result.status)
                    db.add(resp)
                    db.commit()
                    _update_task(task_id, generated=_TASKS_INC(task_id, "generated"),
                                processed=_TASKS_INC(task_id, "processed"))
                    _append_item(task_id, req.id, result.status, result.message)
                except LlmServiceError as e:
                    resp = BidResponse(requirement_id=req.id,
                                       ai_content="待人工补充：未检索到可引用的企业资料。",
                                       status="needs_manual")
                    db.add(resp)
                    db.commit()
                    _update_task(task_id, failed=_TASKS_INC(task_id, "failed"),
                                processed=_TASKS_INC(task_id, "processed"))
                    _append_item(task_id, req.id, "needs_manual", f"LLM失败降级: {e}")
            except Exception as e:
                db.rollback()
                _update_task(task_id, failed=_TASKS_INC(task_id, "failed"),
                            processed=_TASKS_INC(task_id, "processed"))
                _append_item(task_id, getattr(req, "id", "?"), "failed", str(e))

        # 终态判定
        with _TASK_LOCK:
            t = TASKS.get(task_id, {})
            if t.get("failed", 0) == 0 and t.get("skipped", 0) == 0:
                final = "completed"
            elif t.get("generated", 0) > 0 or t.get("skipped", 0) > 0:
                final = "partial"
            else:
                final = "failed"
        _update_task(task_id, status=final)
    except Exception as e:
        _update_task(task_id, status="failed", error=str(e))
    finally:
        db.close()
```

> 说明：`_TASKS_INC` 与 `_append_item` 是你在 `batch_task_manager` 中实现的辅助函数（带锁地原子自增某字段 / 往 `items` 追加一条），按上面语义自行补全即可。

**D. 新增状态查询路由**：

```python
@router.get("/projects/{project_id}/batch-status")
def get_batch_status(project_id: int, task_id: str,
                     current_user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    project = db.query(BidProject).filter(
        BidProject.id == project_id,
        BidProject.owner_id == current_user.id).first()
    if not project:
        raise NotFoundException(message="项目不存在或无权限")
    with _TASK_LOCK:
        task = TASKS.get(task_id)
    if not task:
        raise NotFoundException(message="任务不存在或已过期")
    return ApiResponse(data=task)
```

### 4.2 前端

**E. `frontend/src/api/compliance.js`**：

```javascript
// 启动批量生成，立即返回 { task_id }
export async function startBatchGenerate(projectId) {
  const data = await api.post(`/requirements/projects/${projectId}/batch-generate`)
  return data
}
// 轮询任务进度
export async function getBatchStatus(projectId, taskId) {
  const data = await api.get(`/requirements/projects/${projectId}/batch-status`, {
    params: { task_id: taskId }
  })
  return data
}
```
（保留原 `batchGenerateResponses` 以兼容，或直接替换为上面两个函数。）

**F. `frontend/src/views/ProjectDetailView.vue` 的 `handleBatchGenerateFromComparison`**：

```javascript
import { startBatchGenerate as startBatchGenerateApi, getBatchStatus as getBatchStatusApi } from '@/api/compliance'

async function handleBatchGenerateFromComparison() {
  try {
    await ElMessageBox.confirm('确定要为已匹配的需求批量生成AI响应吗？此操作会调用AI服务，可能需要一些时间。', '批量生成确认', { type: 'warning' })
  } catch { return }

  batchGenerating.value = true
  let taskId = null
  let timer = null
  let ticks = 0
  const MAX_TICKS = 150   // 2s * 150 = 5 分钟兜底

  const stop = () => { if (timer) clearInterval(timer); timer = null; batchGenerating.value = false }

  try {
    const startRes = await startBatchGenerateApi(projectId.value)
    taskId = startRes.task_id
    timer = setInterval(async () => {
      ticks += 1
      if (ticks > MAX_TICKS) { stop(); ElMessage.warning('批量生成超时，请稍后刷新查看结果'); return }
      try {
        const st = await getBatchStatusApi(projectId.value, taskId)
        const { status, processed, total, generated, skipped, failed } = st
        if (['completed', 'partial', 'failed'].includes(status)) {
          stop()
          ElMessage.success(`批量生成完成：成功 ${generated}，跳过 ${skipped}，失败 ${failed}`)
          loadRequirements()
        } else {
          ElMessage.info(`生成中 ${processed}/${total}...`)
        }
      } catch (e) {
        stop(); ElMessage.error(e.message || '查询进度失败')
      }
    }, 2000)
  } catch (e) {
    stop(); ElMessage.error(e.message || '批量生成启动失败')
  }
}
```

### 4.3 验证

1. 启动后端 + 前端，进入项目详情页的「需求—资料对比」面板，点击「为已匹配需求批量生成响应 (N)」。
2. 预期：按钮立即进入 loading，界面持续显示「生成中 X/Y...」提示，**不再出现「超过响应时间」**；后台生成完毕后需求表出现应答稿，提示成功数/跳过数/失败数。
3. 未匹配需求被跳过（不写 `needs_manual` 占位）；LLM 不可用时整批不卡死、降级为 `needs_manual` 占位并继续。
4. 单条生成、match-analysis、其它页面功能不受影响。
5. 后端启动无报错；如项目有 pytest 用例，`python -m pytest` 通过。

---

## 五、交付清单（自检）

- [ ] `backend/app/api/routes/responses.py`：`batch_generate_responses` 改为异步提交 + 新增 `_run_batch` + 新增 `get_batch_status` 路由 + 任务状态存储/辅助函数（或抽到 `batch_task_manager.py`）。
- [ ] `app/db/session.py`：确认存在 `SessionLocal` 同步会话工厂（无则补）。
- [ ] `frontend/src/api/compliance.js`：新增 `startBatchGenerate` 与 `getBatchStatus`。
- [ ] `frontend/src/views/ProjectDetailView.vue`：`handleBatchGenerateFromComparison` 改为「启动 → 轮询 → 完成刷新」模式。
- [ ] 未改动 `Requirement`/`BidResponse`/`BidProject` 表结构；未改动单条生成与 match-analysis 接口；未改动前端全局 30s 超时。
