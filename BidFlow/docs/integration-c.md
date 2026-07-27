# 成员 C 交付说明（企业资料知识库 / 向量化与检索）

> 本文档供组长(成员A)与成员D整合时阅读。成员C的完整代码在 `backend/app/` 下。

## 一、成员C负责的文件清单

| 文件 | 说明 |
|---|---|
| `backend/app/models/company_document.py` | 企业资料 ORM 模型 |
| `backend/app/schemas/company_document.py` | 接口出入参 Schema |
| `backend/app/services/text_chunker.py` | 文本切分 |
| `backend/app/services/vector_store.py` | Chroma 封装 + Embedding（本地/OpenAI 可切换） |
| `backend/app/services/retrieval_service.py` | 检索服务（成员D调用入口） |
| `backend/app/services/company_material_service.py` | 上传入库/删除/列表编排 |
| `backend/app/api/routes/knowledge.py` | **全部HTTP接口（单文件）** |
| `backend/tests/test_retrieval.py` | 单元测试 |
| `docs/data-samples.md` | 示例企业资料（与成员B共用） |

## 二、接口（全部在 `knowledge.py`，前缀 `/api`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/company-documents` | 上传资料(form: file, project_id?, owner_id?) → 入库，返回片段数 |
| GET | `/api/company-documents` | 列表(project_id? 过滤) |
| DELETE | `/api/company-documents/{id}` | 删除资料 + 其全部向量 |
| POST | `/api/retrieval/search` | 检索(query, project_id?, top_k=5) → 相关片段(带来源) |
| GET | `/api/health` | 健康检查（自测入口 main_c.py 提供） |

## 三、成员A如何整合

1. 把成员C的 `app/` 下文件并入工程（路由文件只多了一个 `knowledge.py`）。
2. 在 `app/main.py` 中加入：
   ```python
   from app.api.routes.knowledge import router as knowledge_router
   app.include_router(knowledge_router)
   ```
3. 成员C自带的 `core/config.py`、`db/base.py`、`db/session.py`、`app/main_c.py` 仅为独立运行/自测用，
   并入后以成员A的底座版本为准（结构与导入路径保持一致，不会冲突）。
4. 向量库目录 `backend/data/chroma` 与数据库 `backend/data/bidflow.db` 会自动创建。

## 四、成员D如何调用检索

生成响应草稿时，直接复用成员C的检索服务即可，无需关心 Chroma 细节：

```python
from app.services.retrieval_service import RetrievalService

retrieval = RetrievalService()
chunks = retrieval.search(query=requirement.content, project_id=project_id, top_k=5)
# chunks: [{document_id, filename, chunk_index, content, source_ref, score}, ...]
# 把 chunks 作为 RAG 上下文传给大模型，并保留 source_ref 作为引用来源
```

## 五、Embedding 方案切换

- 默认 `local`：零依赖、可离线，字符 bigram 哈希（演示足够）。
- 如需更好语义效果：设置环境变量
  `EMBEDDING_PROVIDER=openai`、`OPENAI_API_KEY=xxx`（需 `pip install openai`）。
- ⚠️ 切换后旧向量维度不一致，删除 `backend/data/chroma` 重新入库。

## 六、本地运行（自测）

```bash
cd backend
python -m venv venv && source venv/bin/activate   # 或用本机 python
pip install -r requirements.txt
uvicorn app.main_c:app --reload --port 8000
# 健康检查
curl http://127.0.0.1:8000/api/health
```

## 七、测试

```bash
cd backend
pip install pytest
pytest tests/test_retrieval.py -q
```
