"""向量存储服务 - 支持 Milvus ANN + 中文 n-gram 降级匹配 + LLM 比对分析"""
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Protocol

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scope 常量 — 两级隔离模型
# ---------------------------------------------------------------------------
COMPANY_SCOPE = "company"   # 公司级共享资料，所有项目可见
PROJECT_SCOPE = "project"   # 项目级专属资料，仅绑定项目可见
VALID_SCOPES = {COMPANY_SCOPE, PROJECT_SCOPE}

# ---------------------------------------------------------------------------
# MatchResult dataclass — 需求-资料比对的标准输出结构
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    """需求与企业资料的比对结果"""
    requirement_id: int
    coverage: str           # "full" | "partial" | "missing"
    confidence: float       # 0.0 ~ 1.0
    material_covered: bool  # True=已覆盖, False=未覆盖
    evidence: List[Dict] = field(default_factory=list)  # [{chunk_id, quote, source_ref}]
    gap: Optional[str] = None  # 缺失/待补充说明
    pending_review: bool = False  # 是否需要人工复核
    method: str = "hybrid_v1"

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# 协议定义 — 便于测试时注入 mock
# ---------------------------------------------------------------------------

class EmbeddingClientProto(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChatClientProto(Protocol):
    def chat_json(self, messages: list[dict[str, str]]) -> dict: ...


# ---------------------------------------------------------------------------
# 主服务类
# ---------------------------------------------------------------------------

class VectorStoreService:
    """向量存储和检索服务

    双路径设计:
      1) Milvus ANN 向量检索 (已部署环境)
      2) 内存 JSON + 字符 n-gram 降级匹配 (开发/离线环境)

    新增 match_requirement_to_materials 方法实现需求-资料比对闭环。
    """

    def __init__(
        self,
        milvus_client: Any = None,
        embedding_client: EmbeddingClientProto = None,
        chat_client: ChatClientProto = None,
    ):
        # --- 内存存储 (保留，作为降级路径) ---
        self._vectors: List[Dict] = []
        self._id_counter = 0
        self._persist_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "..", "data", "vector_store"
        )
        os.makedirs(self._persist_dir, exist_ok=True)
        self._load_from_disk()

        # --- Milvus 相关 (延迟初始化) ---
        self._milvus_client = milvus_client
        from app.core.config import settings as _cfg
        self._collection_name: str = os.getenv("MILVUS_COLLECTION_NAME", _cfg.MILVUS_COLLECTION_NAME)
        self._embedding_dim: int = int(os.getenv("EMBEDDING_DIM", "1024"))
        self._milvus_available: bool = False
        self._milvus_initialized: bool = False

        # --- LLM / Embedding 客户端 ---
        self._embedding_client = embedding_client
        self._chat_client = chat_client

        # --- 比对缓存 ---
        self._match_cache: Dict[str, dict] = {}

        # --- 语料版本号 (用于缓存键) ---
        self._corpus_version: int = self._id_counter

        # 注意：不在构造函数中连接 Milvus，改为首次使用时延迟初始化

    # ------------------------------------------------------------------
    # Milvus 连接管理 (延迟初始化)
    # ------------------------------------------------------------------

    def _ensure_milvus(self) -> None:
        """首次使用时初始化 Milvus 连接，失败时仅记录日志"""
        if self._milvus_initialized:
            return
        self._milvus_initialized = True

        # 如果外部已注入 client，直接标记可用
        if self._milvus_client is not None:
            self._milvus_available = True
            return

        try:
            from pymilvus import MilvusClient
            from app.core.config import settings

            # 优先系统环境变量，其次 .env（settings 已从 .env 加载）
            host = os.getenv("MILVUS_HOST", settings.MILVUS_HOST)
            port = int(os.getenv("MILVUS_PORT", str(settings.MILVUS_PORT)))
            uri = f"http://{host}:{port}"
            self._milvus_client = MilvusClient(uri=uri)

            # _build_collection_schema() 现在返回 CollectionSchema 对象，
            # 字段名从 .fields[i].name 读取
            expected_fields = {f.name for f in self._build_collection_schema().fields}

            # collection 已存在时校验 schema 是否与当前代码一致
            # 历史遗留：早期版本创建过只有 id/vector 两字段的 collection，
            # 与代码期望（id/text/project_id/metadata_json/vector）不匹配 →
            # _upsert_to_milvus 插入必然失败（字段不存在），向量永远写不进去。
            # 因此 schema 不匹配时 drop 重建（旧 collection 无有效数据，无损失）。
            if self._milvus_client.has_collection(self._collection_name):
                try:
                    desc = self._milvus_client.describe_collection(self._collection_name)
                    actual_fields = {f.get("name") for f in (desc.get("fields") or [])}
                except Exception:
                    actual_fields = set()
                if actual_fields and actual_fields != expected_fields:
                    logger.warning(
                        "[vector_store] collection '%s' schema 不匹配 (got=%s, want=%s)，drop 重建",
                        self._collection_name, sorted(actual_fields), sorted(expected_fields),
                    )
                    self._milvus_client.drop_collection(self._collection_name)

            # 检查 collection 是否存在，不存在则创建
            # pymilvus 2.5.x: schema 模式下不再传 dimension=（向量维度由 schema 中的
            # FieldSchema(dim=...) 提供）；传 dimension 在 fast-create 路径才会用到，
            # 与 schema= 同时传会冲突。
            if not self._milvus_client.has_collection(self._collection_name):
                self._milvus_client.create_collection(
                    collection_name=self._collection_name,
                    schema=self._build_collection_schema(),
                )
                logger.info("Milvus collection '%s' created with dim=%d",
                            self._collection_name, self._embedding_dim)

            # 创建索引
            # pymilvus 2.5.x: create_index 第二个参数要求 IndexParams 对象，
            # 不能再传 dict；先 prepare_index_params() 再 add_index()。
            index_params = self._milvus_client.prepare_index_params()
            index_params.add_index(
                field_name="vector",
                index_type="IVF_FLAT",
                metric_type="COSINE",
                params={"nlist": 128},
            )
            self._milvus_client.create_index(
                collection_name=self._collection_name,
                index_params=index_params,
            )

            # 加载 collection 到内存，否则后续 search/query 会报 "collection not loaded"
            self._milvus_client.load_collection(self._collection_name)

            self._milvus_available = True
            logger.info("Milvus connected: %s/%s", uri, self._collection_name)
        except Exception as e:
            logger.warning("Milvus connection failed, falling back to in-memory mode: %s", e)
            self._milvus_available = False

    def _build_collection_schema(self):
        """构建 Milvus collection schema

        pymilvus 2.5.x 的 MilvusClient.create_collection(schema=...) 要求
        传入 CollectionSchema 对象（内部会调用 schema.verify()），
        早期版本传 dict 会导致 'dict' object has no attribute 'verify'，
        collection 创建失败 → 整个 _ensure_milvus 被吞异常 → 向量永远写不进去。
        """
        from pymilvus import DataType, FieldSchema, CollectionSchema
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="project_id", dtype=DataType.INT64),
            FieldSchema(name="metadata_json", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=self._embedding_dim),
        ]
        return CollectionSchema(fields=fields, description="BidFlow 企业资料向量集合")

    def _get_collection(self) -> Optional[str]:
        """确保 Milvus 已初始化并返回 collection 名称，不可用返回 None"""
        self._ensure_milvus()
        if not self._milvus_available or self._milvus_client is None:
            return None
        return self._collection_name

    # ------------------------------------------------------------------
    # 持久化 (保留原有逻辑)
    # ------------------------------------------------------------------

    def _get_store_path(self) -> str:
        return os.path.join(self._persist_dir, "vectors.json")

    def _save_to_disk(self) -> None:
        """将向量数据持久化到磁盘"""
        try:
            data = {
                "id_counter": self._id_counter,
                "vectors": [
                    {
                        "id": v["id"],
                        "text": v["text"],
                        "project_id": v["project_id"],
                        "metadata": v.get("metadata", {}),
                    }
                    for v in self._vectors
                ],
            }
            with open(self._get_store_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_from_disk(self) -> None:
        """从磁盘加载向量数据"""
        try:
            path = self._get_store_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._id_counter = data.get("id_counter", 0)
                self._vectors = data.get("vectors", [])
                # 启动时自动清理孤儿数据（无 doc_id 的测试/残留数据）
                self._cleanup_orphan_vectors()
        except Exception:
            self._vectors = []
            self._id_counter = 0

    def _cleanup_orphan_vectors(self) -> None:
        """清理无 doc_id 的孤儿向量（测试/残留数据）

        真实上传的资料在 upsert 时会设置 metadata.doc_id。
        没有 doc_id 的向量视为无效数据，启动时自动清理。
        """
        before_count = len(self._vectors)
        self._vectors = [
            v for v in self._vectors
            if v.get("metadata", {}).get("doc_id") is not None
        ]
        if self._vectors:
            self._id_counter = max(v["id"] for v in self._vectors)
        else:
            self._id_counter = 0
        removed = before_count - len(self._vectors)
        if removed > 0:
            logger.info("[vector_store] cleaned up %d orphan vectors (no doc_id)", removed)
            self._save_to_disk()

    # ------------------------------------------------------------------
    # 原有公开 API — 保持行为不变
    # ------------------------------------------------------------------

    def upsert(
        self,
        chunks: List[Dict],
        project_id: Optional[int] = None,
        metadata: Optional[Dict] = None,
        scope: str = COMPANY_SCOPE,
    ) -> List[int]:
        """批量插入或更新向量（保留原有行为 + 写入 Milvus）

        Args:
            chunks: 文本块列表，每个含 text 字段
            project_id: 项目 ID（company 级资料为 None）
            metadata: 元数据字典（doc_id, filename 等）
            scope: 资料作用域 "company" 或 "project"
        """
        if scope not in VALID_SCOPES:
            raise ValueError(f"scope must be one of {VALID_SCOPES}, got '{scope}'")
        if scope == PROJECT_SCOPE and project_id is None:
            raise ValueError("project scope requires project_id")

        # scope=company 时强制 project_id=None，忽略传入值
        effective_project_id = None if scope == COMPANY_SCOPE else project_id

        ids = []
        meta = metadata or {}
        # 将 scope 注入 metadata，供检索过滤使用
        meta_with_scope = {**meta, "scope": scope}
        for chunk in chunks:
            self._id_counter += 1
            ids.append(self._id_counter)
            entry = {
                "id": self._id_counter,
                "text": chunk["text"],
                "project_id": effective_project_id,
                "metadata": meta_with_scope,
            }
            self._vectors.append(entry)

            # 同步写入 Milvus (若可用)
            self._upsert_to_milvus(entry)

        self._corpus_version = self._id_counter
        self._save_to_disk()
        logger.info("[upsert] inserted %d chunks, scope=%s, project_id=%s",
                     len(chunks), scope, effective_project_id)
        return ids

    def search(
        self,
        query: str,
        project_id: Optional[int] = None,
        top_k: int = 5,
    ) -> List[Dict]:
        """按文本相似度搜索，支持中文 n-gram + 英文单词匹配

        Scope 过滤规则:
          - project_id 有值: scope=company OR (scope=project AND project_id 匹配)
          - project_id 为 None: 仅 scope=company

        若 Milvus 可用则优先使用向量检索，降级到 n-gram。
        """
        scope_filter = self._build_scope_filter(project_id)
        logger.info("[search] query_len=%d, project_id=%s, scope_filter=%s",
                     len(query), project_id, scope_filter)

        # 优先尝试 Milvus 向量检索
        self._ensure_milvus()
        if self._milvus_available and self._embedding_client is not None:
            try:
                results = self._milvus_search(query, project_id, top_k)
                logger.info("[search] Milvus returned %d chunks", len(results))
                return results
            except Exception as e:
                logger.warning("Milvus search failed, falling back to n-gram: %s", e)

        # 降级到原有的 n-gram 匹配
        results = self._ngram_search(query, project_id, top_k)
        logger.info("[search] n-gram returned %d chunks", len(results))
        return results

    def hybrid_search(
        self,
        query: str,
        project_id: Optional[int] = None,
        top_k: int = 5,
    ) -> List[Dict]:
        """混合召回（RAG 增强）：Milvus dense 结果 + n-gram 关键词补充，合并去重后取 top_k。

        - 无 schema 变更：两路结果按记录 id 去重（memory 与 Milvus 共用同一 id 体系），
          重复项保留 dense 分数（dense 优先写入 merged）。
        - dense 不可用时自动退化为纯 keyword。
        - 返回结构与 _milvus_search / _ngram_search 兼容（含 id/text/project_id/metadata/score）。
        """
        if not query or not query.strip():
            return []
        self._ensure_milvus()
        merged: Dict[int, Dict] = {}

        # 1) dense 路（Milvus 可用时优先写入，保留其分数）
        if self._milvus_available and self._embedding_client is not None:
            try:
                for r in self._milvus_search(query, project_id, top_k * 3):
                    r["retrieval_type"] = "dense"  # 语义相似召回
                    merged[r["id"]] = r
            except Exception as e:
                logger.warning("[hybrid] dense search failed, keyword only: %s", e)

        # 2) keyword 路（补充 dense 没召回的片段）
        for r in self._ngram_search(query, project_id, top_k * 3):
            if r["id"] not in merged:
                r["retrieval_type"] = "keyword"  # 关键词命中补充
                merged[r["id"]] = r

        # M3：分数量纲归一化后再排序——dense 余弦 0~1，ngram 0~15（phrase +10 / overlap / word +2）。
        # 启发式：score<=1 视为 dense（保持原值）；>1 视为 ngram（压缩到 0~1），避免 keyword 分数恒压过 dense。
        def _norm_score(r: Dict) -> float:
            s = r.get("score", 0.0) or 0.0
            return min(s, 1.0) if s <= 1.0 else min(s / 15.0, 1.0)

        items = sorted(merged.values(), key=_norm_score, reverse=True)
        logger.info("[hybrid] merged=%d → top_k=%d (dense=%s)",
                    len(items), min(len(items), top_k), self._milvus_available)
        return items[:top_k]

    @staticmethod
    def _build_scope_filter(project_id: Optional[int]) -> str:
        """构建 scope 过滤规则描述（用于日志和注释）"""
        if project_id is not None:
            return f'scope=company OR (scope=project AND project_id={project_id})'
        return 'scope=company ONLY'

    @staticmethod
    def _matches_scope(entry: Dict, project_id: Optional[int]) -> bool:
        """判断单条记录是否满足 scope 隔离规则

        scope 存储在 metadata 中（key='scope'），兼容旧数据（无 scope 字段视为 company）。
        """
        meta = entry.get("metadata", {})
        scope = meta.get("scope", COMPANY_SCOPE)
        if scope == COMPANY_SCOPE:
            return True
        if scope == PROJECT_SCOPE:
            entry_pid = entry.get("project_id")
            return project_id is not None and entry_pid == project_id
        # 未知 scope 默认放行（向后兼容）
        return True

    def delete_by_doc_id(self, doc_id: int) -> None:
        """按文档 ID 删除所有关联向量（内存 + Milvus 同步删除，并失效比对缓存）"""
        # 先收集要删除的记录 id（内存与 Milvus 共用同一 id 体系）
        deleted_ids = [
            v["id"] for v in self._vectors
            if v.get("metadata", {}).get("doc_id") == doc_id
        ]
        self._vectors = [
            v for v in self._vectors
            if v.get("metadata", {}).get("doc_id") != doc_id
        ]
        if self._vectors:
            self._id_counter = max(v["id"] for v in self._vectors)
        else:
            self._id_counter = 0
        self._save_to_disk()

        # M4：同步删除 Milvus 中对应记录（按主键 id 批量删），防止检索残留
        if deleted_ids:
            self._ensure_milvus()
            if self._milvus_available and self._milvus_client is not None:
                try:
                    collection = self._get_collection()
                    if collection:
                        self._milvus_client.delete(collection_name=collection, ids=deleted_ids)
                except Exception as e:
                    logger.warning("[vector_store] Milvus delete by doc_id=%s failed: %s", doc_id, e)

        # 语料变更 → 版本号自增 + 失效比对缓存（M4：避免 match 返回已删资料的旧命中）
        self._corpus_version = self._id_counter
        self.invalidate_match_cache()

    def update_doc_scope(self, doc_id: int, scope: str, project_id: Optional[int]) -> None:
        """变更文档归属（scope/project_id），内存 + Milvus 同步更新 metadata。

        用于前端"改归属"功能：用户可把项目级资料转给其他项目，或转公司级共享。
        检索过滤（_matches_scope）读取 entry.project_id 与 metadata.scope，
        必须两处都更新，否则变更后检索仍按旧归属过滤。
        """
        effective_project_id = None if scope == COMPANY_SCOPE else project_id
        # 该文档向量 id（Milvus 主键与内存共用同一 id 体系）
        doc_ids = [
            v["id"] for v in self._vectors
            if v.get("metadata", {}).get("doc_id") == doc_id
        ]

        # 1) 内存：更新 project_id + metadata.scope（保留其余 metadata 字段）
        for v in self._vectors:
            if v.get("metadata", {}).get("doc_id") == doc_id:
                v["project_id"] = effective_project_id
                v["metadata"]["scope"] = scope
        self._save_to_disk()

        # 2) Milvus：删除旧记录后按新 metadata 重插（复用 upsert 主键 id 体系）
        if doc_ids:
            self._ensure_milvus()
            if self._milvus_available and self._milvus_client is not None:
                try:
                    collection = self._get_collection()
                    if collection:
                        self._milvus_client.delete(collection_name=collection, ids=doc_ids)
                        for v in self._vectors:
                            if v.get("metadata", {}).get("doc_id") == doc_id:
                                self._upsert_to_milvus(v)
                except Exception as e:
                    logger.warning("[vector_store] Milvus update scope doc_id=%s failed: %s", doc_id, e)

        # 3) 语料归属变更 → 版本号自增 + 失效比对缓存（避免 match 返回旧归属命中）
        self._corpus_version = self._id_counter
        self.invalidate_match_cache()
        logger.info("[vector_store] updated doc_id=%s scope=%s project_id=%s", doc_id, scope, effective_project_id)

    def _has_valid_materials(self) -> bool:
        """检查是否有有效的企业资料向量（具有 doc_id 的真实上传数据）

        区分真实上传的资料（带 doc_id）与测试/残留数据（metadata 为空）。
        只有真实上传的资料才参与比对。
        """
        return any(
            v.get("metadata", {}).get("doc_id") is not None
            for v in self._vectors
        )

    def _get_valid_vectors(self) -> List[Dict]:
        """返回所有有效向量（带 doc_id 的真实上传资料）"""
        return [
            v for v in self._vectors
            if v.get("metadata", {}).get("doc_id") is not None
        ]

    def clear(self) -> None:
        """清空所有向量（用于测试或重置）"""
        self._vectors = []
        self._id_counter = 0
        self._corpus_version = 0
        self._save_to_disk()

    def get_stats(self) -> Dict:
        """获取向量存储统计信息"""
        doc_ids = set()
        for v in self._vectors:
            did = v.get("metadata", {}).get("doc_id")
            if did:
                doc_ids.add(did)
        return {
            "total_vectors": len(self._vectors),
            "total_documents": len(doc_ids),
            "id_counter": self._id_counter,
            "milvus_available": self._milvus_available,
            "corpus_version": self._corpus_version,
        }

    # ------------------------------------------------------------------
    # n-gram 关键词预过滤 (保留原 _compute_similarity 逻辑)
    # ------------------------------------------------------------------

    def _extract_ngrams(self, text: str, n: int = 2) -> set:
        """提取文本的字符 n-gram 集合"""
        ngrams = set()
        clean = "".join(text.split())
        for i in range(len(clean) - n + 1):
            ngrams.add(clean[i : i + n])
        return ngrams

    def _compute_similarity(self, text: str, query_ngrams: set, query_words: set) -> float:
        """计算文本与查询的综合相似度（保留原签名，不改变调用方行为）"""
        score = 0.0

        # 1. 精确短语匹配权重最高
        if text and text.strip():
            query_clean = "".join(query_ngrams) if query_ngrams else ""
            if query_clean and query_clean in "".join(text.split()):
                score += 10.0

        # 2. 字符 n-gram 重叠匹配
        text_ngrams = self._extract_ngrams(text)
        if query_ngrams and text_ngrams:
            overlap = query_ngrams & text_ngrams
            union = query_ngrams | text_ngrams
            if union:
                score += (len(overlap) / len(union)) * 5.0
            score += len(overlap) * 0.5

        # 3. 英文单词匹配
        text_words = set(text.split())
        if query_words and text_words:
            word_overlap = query_words & text_words
            if word_overlap:
                score += len(word_overlap) * 2.0

        return score

    def _keyword_prefilter(self, query: str, project_id: Optional[int], top_k: int) -> List[Dict]:
        """基于 n-gram 的关键词预过滤（对外暴露的降级路径）"""
        return self._ngram_search(query, project_id, top_k)

    def _ngram_search(self, query: str, project_id: Optional[int], top_k: int) -> List[Dict]:
        """n-gram 搜索实现（带 scope 隔离过滤 + 有效资料过滤）"""
        # 只使用有效向量（带 doc_id 的真实上传资料）
        results = self._get_valid_vectors()

        # 先用 scope 规则过滤
        results = [v for v in results if self._matches_scope(v, project_id)]

        if not query or not query.strip():
            for r in results:
                r["score"] = 0.0
            return results[:top_k]

        query_ngrams = self._extract_ngrams(query.lower())
        query_words = set(query.lower().split())

        for r in results:
            text_lower = r["text"].lower()
            r["score"] = self._compute_similarity(text_lower, query_ngrams, query_words)

        results = [r for r in results if r["score"] > 0]
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Milvus 向量检索 (内部)
    # ------------------------------------------------------------------

    def _upsert_to_milvus(self, entry: Dict) -> None:
        """将单条向量写入 Milvus，失败静默"""
        self._ensure_milvus()
        if not self._milvus_available or self._embedding_client is None:
            return
        try:
            vecs = self._embedding_client.embed([entry["text"]])
            if not vecs:
                return
            collection_name = self._get_collection()
            if collection_name is None:
                return
            data = [{
                "id": entry["id"],
                "text": entry["text"],
                "project_id": entry["project_id"] if entry["project_id"] is not None else 0,
                "metadata_json": json.dumps(entry.get("metadata", {}), ensure_ascii=False),
                "vector": vecs[0],
            }]
            self._milvus_client.insert(collection_name=collection_name, data=data)
        except Exception as e:
            logger.warning("Milvus upsert failed for id=%d: %s", entry["id"], e)

    def _milvus_search(self, query: str, project_id: Optional[int], top_k: int) -> List[Dict]:
        """Milvus ANN 检索，返回与 _ngram_search 格式兼容的结果列表

        Scope 隔离:
          - Milvus 层: 先按 project_id 做粗筛 (company 级=0, project 级=实际 ID)
          - Python 层: 解析 metadata_json 中的 scope，精确过滤
        """
        self._ensure_milvus()
        if not self._milvus_available or self._embedding_client is None:
            return []
        if not query or not query.strip():
            return []

        try:
            vecs = self._embedding_client.embed([query])
        except Exception as e:
            logger.warning("Embedding failed: %s", e)
            return []
        if not vecs:
            return []

        collection_name = self._get_collection()
        if collection_name is None:
            return []

        # Milvus 层粗筛: project_id 匹配或全局 (0=全局)
        filter_expr = None
        if project_id is not None:
            filter_expr = f'(project_id == {project_id} or project_id == 0)'
        else:
            filter_expr = 'project_id == 0'

        try:
            # pymilvus 2.5.x: MilvusClient.search 直接接收关键字参数，
            # 没有 prepare_search_params 方法（旧代码用了不存在的方法，
            # 被 except 吞掉 → 搜索永远走不通，降级到 n-gram）。
            # 过滤表达式参数名为 filter（不是 expr）。
            results = self._milvus_client.search(
                collection_name=collection_name,
                data=[vecs[0]],
                anns_field="vector",
                search_params={"metric_type": "COSINE", "params": {"nprobe": 10}},
                limit=top_k * 3,  # 多取一些留足 scope 过滤余量
                filter=filter_expr,
                output_fields=["text", "project_id", "metadata_json"],
            )
        except Exception as e:
            logger.warning("Milvus search error: %s", e)
            return []

        # 格式转换 + scope 精过滤
        formatted = []
        if results and len(results) > 0:
            for hit in results[0]:
                entity = hit.get("entity", {})
                metadata = {}
                raw_meta = entity.get("metadata_json", "{}")
                if isinstance(raw_meta, str):
                    try:
                        metadata = json.loads(raw_meta)
                    except Exception:
                        pass
                entry = {
                    "id": entity.get("id", hit.get("id", 0)),
                    "text": entity.get("text", ""),
                    "project_id": entity.get("project_id"),
                    "metadata": metadata,
                    "score": float(hit.get("distance", hit.get("score", 0))),
                }
                # Scope 精过滤
                if self._matches_scope(entry, project_id):
                    formatted.append(entry)
                    if len(formatted) >= top_k:
                        break
        return formatted

    def _get_all_corpus_text(self, project_id: Optional[int] = None) -> str:
        """获取语料库全量文本（用于关键词覆盖检查）

        仅返回当前项目可见的有效资料文本 (scope=company + scope=project AND project_id 匹配)
        """
        valid = self._get_valid_vectors()
        visible = [v for v in valid if self._matches_scope(v, project_id)]
        texts = [v["text"] for v in visible]
        return " ".join(texts)

    # ------------------------------------------------------------------
    # 需求-资料比对 (核心新入口)
    # ------------------------------------------------------------------

    def match_requirement_to_materials(
        self,
        requirement: Dict,
        project_id: int,
        top_k: int = 5,
    ) -> MatchResult:
        """比对单个需求项与企业资料，返回 MatchResult

        流程严格按规范:
          a) 向量化 requirement.content → Milvus ANN 检索
          b) 若 Milvus 不可用 → 关键词预过滤
          c) 强制关键词覆盖检查 → 缺失则直接返回 missing
          d) LLM 结构化 JSON 输出
          e) 决策逻辑
          f) 缓存 (key=requirement_id + corpus_version)
          g) 返回 MatchResult

        约束: 企业资料库为空时，直接返回 coverage=missing，绝不编造结果。
        """
        req_id = requirement.get("id", 0)
        req_content = requirement.get("content", "")
        req_category = requirement.get("category", "")
        req_priority = requirement.get("priority", "")

        # --- (f) 缓存检查 ---
        cache_key = f"{req_id}_{self._corpus_version}"
        if cache_key in self._match_cache:
            logger.info("[match] cache hit: req_id=%s", req_id)
            cached = self._match_cache[cache_key]
            return MatchResult(**cached)

        started = time.monotonic()
        logger.info("[match] start: req_id=%s, project_id=%d, content_len=%d",
                     req_id, project_id, len(req_content))

        # ========== (0) 语料库空检查 ==========
        # 检查是否有有效的企业资料（带 doc_id 的真实上传数据）
        valid_vectors = self._get_valid_vectors()
        if not valid_vectors:
            logger.warning("[match] corpus empty: req_id=%s, no valid materials available (total_vectors=%d)",
                          req_id, len(self._vectors))
            result = MatchResult(
                requirement_id=req_id,
                coverage="missing",
                confidence=0.0,
                material_covered=False,
                evidence=[],
                gap="待人工补充: 企业资料库为空，请先上传企业资质资料",
                pending_review=True,
            )
            self._log_and_cache(result, cache_key, started)
            return result

        # ========== (a+b) 混合召回（dense + keyword）/ 关键词预过滤 ==========
        # RAG 增强：两路召回合并去重，覆盖向量相似与关键词命中（编号/型号/金额等精确信号）
        chunks = []
        try:
            chunks = self.hybrid_search(req_content, project_id, top_k * 2)
        except Exception as e:
            logger.warning("[match] hybrid search failed, fallback to keyword: %s", e)

        # 混合检索无结果 → 关键词预过滤兜底
        if not chunks:
            chunks = self._keyword_prefilter(req_content, project_id, top_k)

        # 检索无结果 → 直接返回 missing（不再使用兜底数据）
        if not chunks:
            logger.info("[match] no chunks retrieved: req_id=%s", req_id)
            result = MatchResult(
                requirement_id=req_id,
                coverage="missing",
                confidence=0.0,
                material_covered=False,
                evidence=[],
                gap="待人工补充: 未检索到相关企业资料",
                pending_review=True,
            )
            self._log_and_cache(result, cache_key, started)
            return result

        logger.info("[match] retrieved %d chunks for req_id=%s", len(chunks), req_id)

        # ========== (c) 强制关键词覆盖检查 ==========
        mandatory_keywords = self._extract_mandatory_keywords(req_content)
        corpus_text = self._get_all_corpus_text(project_id=project_id)
        missing_keywords = [kw for kw in mandatory_keywords if kw not in corpus_text]

        # 若存在强制关键词缺失 → 直接返回 missing，跳过 LLM
        if missing_keywords:
            gap_msg = f"待人工补充: 企业资料中未找到关键词 {missing_keywords}"
            evidence = self._build_evidence_from_chunks(chunks)
            result = MatchResult(
                requirement_id=req_id,
                coverage="missing",
                confidence=0.0,
                material_covered=False,
                evidence=evidence,
                gap=gap_msg,
                pending_review=True,
            )
            self._log_and_cache(result, cache_key, started)
            return result

        # ========== (d) LLM 结构化输出 ==========
        llm_result = None
        if self._chat_client is not None:
            try:
                llm_result = self._call_match_llm(
                    requirement=requirement,
                    chunks=chunks,
                    mandatory_missing=[],  # 已通过关键词检查
                )
            except Exception as e:
                logger.warning("[match] LLM failed for req_id=%s: %s", req_id, e)

        # ========== (e) 决策 ==========
        coverage = "missing"
        confidence = 0.0
        evidence = []
        gap = None
        pending_review = True
        material_covered = False

        if llm_result is not None:
            # LLM 返回有效结果
            coverage = llm_result.get("coverage", "missing")
            confidence = float(llm_result.get("confidence", 0.0))
            evidence = llm_result.get("evidence", [])
            gap = llm_result.get("gap")

            if coverage == "full" and confidence >= 0.70:
                material_covered = True
                pending_review = False
            elif coverage == "partial" or 0.40 <= confidence < 0.70:
                material_covered = False
                pending_review = True
            else:
                material_covered = False
                pending_review = True
                if not gap:
                    gap = "待人工补充: 未检索到相关企业资料"
        else:
            # LLM 不可用 → 基于检索结果做降级判断
            evidence = self._build_evidence_from_chunks(chunks)
            if chunks:
                coverage = "partial"
                confidence = 0.40
                gap = "LLM 不可用，基于关键词匹配的初步判断，建议人工复核"
            else:
                coverage = "missing"
                confidence = 0.0
                gap = "待人工补充: 未检索到相关企业资料"

        result = MatchResult(
            requirement_id=req_id,
            coverage=coverage,
            confidence=confidence,
            material_covered=material_covered,
            evidence=evidence,
            gap=gap,
            pending_review=pending_review,
        )

        self._log_and_cache(result, cache_key, started)
        return result

    def _build_evidence_from_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """从检索结果构建 evidence 列表（含 source_ref，保证可追溯）"""
        evidence = []
        for c in chunks[:5]:
            meta = c.get("metadata", {})
            evidence.append({
                "chunk_id": str(c.get("id", "")),
                "quote": c.get("text", "")[:200],
                "source_ref": meta.get("source_ref", meta.get("filename", "未知来源")),
            })
        return evidence

    def _log_and_cache(self, result: MatchResult, cache_key: str, started: float) -> None:
        """记录日志并写入缓存"""
        elapsed = time.monotonic() - started
        logger.info("[match] done: req_id=%s, coverage=%s, confidence=%.2f, "
                     "covered=%s, pending=%s, evidence_count=%d, elapsed=%.2fs",
                     result.requirement_id, result.coverage, result.confidence,
                     result.material_covered, result.pending_review,
                     len(result.evidence), elapsed)
        self._match_cache[cache_key] = result.to_dict()

    # ------------------------------------------------------------------
    # LLM 比对辅助方法
    # ------------------------------------------------------------------

    def _extract_mandatory_keywords(self, text: str) -> List[str]:
        """从需求文本提取强制关键词（具体编号/型号/金额/期限等标识性内容）

        只提取具体可查证的标识，不提取泛化描述：
        - 证书编号/资质编号 (如 "A001"、"CN-2024-12345")
        - 产品型号 (如 "XYZ-200")
        - 具体金额 (如 "3000 万元")
        - 具体期限 (如 "3 年")
        """
        import re
        keywords = []

        # 证书/资质编号 (编号标识，如 "编号：XXX" 或 "编号 XXX")
        cert_id_patterns = [
            r'(?:证书|资质|许可证)\s*(?:编号|号)?[：:]\s*([A-Za-z0-9\-]+)',
            r'(?:编号|号)\s*[：:]?\s*([A-Za-z]{1,5}-?\d{3,})',
            r'\b[A-Z]{1,5}-?\d{3,}[A-Z0-9-]*\b',  # 如 CN-2024-12345
        ]
        for pat in cert_id_patterns:
            matches = re.findall(pat, text)
            if isinstance(matches, list) and matches and isinstance(matches[0], tuple):
                # findall with groups returns tuples
                for m in matches:
                    keywords.extend(m if isinstance(m, tuple) else [m])
            else:
                keywords.extend(matches if isinstance(matches, list) else [matches])

        # 金额 (具体金额值)
        amount_pattern = r'\d+[.,]?\d*\s*(?:万元|亿元|元)'
        keywords.extend(re.findall(amount_pattern, text))

        # 期限/年限 (具体时长)。L11：限 1~3 位数字，避免把"2024 年"等年份当强制关键词
        # （4 位年份是时间描述而非可查证的强制标识，误判会导致语料未命中即 missing）
        term_pattern = r'\d{1,3}\s*(?:年|个月|天|日)'
        keywords.extend(re.findall(term_pattern, text))

        # 产品型号 (字母+数字组合，排除纯中文)
        model_pattern = r'\b[A-Z]+\d+[A-Z\d-]*\b'
        keywords.extend(re.findall(model_pattern, text))

        # 去重、去空、过滤掉太短或纯标点的
        result = []
        seen = set()
        for kw in keywords:
            kw = kw.strip()
            if kw and len(kw) >= 2 and kw not in seen:
                seen.add(kw)
                result.append(kw)
        return result

    def _call_match_llm(
        self,
        requirement: Dict,
        chunks: List[Dict],
        mandatory_missing: List[str],
    ) -> Optional[Dict]:
        """调用 LLM 进行需求-资料比对，返回结构化 dict，失败返回 None"""
        if self._chat_client is None:
            logger.info("[match] chat_client not available, skip LLM")
            return None

        req_content = requirement.get("content", "")
        req_category = requirement.get("category", "")
        req_priority = requirement.get("priority", "")

        # 构建证据文本
        evidence_parts = []
        for i, chunk in enumerate(chunks):
            meta = chunk.get("metadata", {})
            source_ref = meta.get("source_ref", meta.get("filename", "未知来源"))
            text_preview = chunk.get("text", "")[:300]
            evidence_parts.append(
                f"[Chunk {i+1}] 来源: {source_ref}\n内容: {text_preview}"
            )
        evidence_text = "\n\n".join(evidence_parts) if evidence_parts else "（无可用资料）"

        missing_hint = ""
        if mandatory_missing:
            missing_hint = f"\n\n⚠️ 以下强制关键词未在企业资料中找到: {mandatory_missing}"

        system_prompt = (
            "你是招投标资料比对专家。请严格根据提供的企业资料片段，"
            "判断当前招标需求是否被企业资料覆盖。"
            "规则: coverage 只能是 full(完全覆盖)/partial(部分覆盖)/missing(完全缺失)。"
            "confidence 取值 0.0~1.0。"
            "evidence 必须列出支撑判断的资料片段及其来源(source_ref)。"
            "gap 填写缺失内容或 null。"
            "不得编造资料，若无资料则返回 missing。"
        )

        user_prompt = (
            f"## 招标需求\n"
            f"- 类别: {req_category}\n"
            f"- 优先级: {req_priority}\n"
            f"- 内容: {req_content}\n"
            f"{missing_hint}\n\n"
            f"## 企业资料片段\n"
            f"{evidence_text}\n\n"
            f"请判断覆盖情况，以 JSON 返回，格式:\n"
            f'{{"coverage":"full|partial|missing","confidence":0.0~1.0,'
            f'"evidence":[{{"chunk_id":"","quote":"","source_ref":""}}],'
            f'"gap":"缺失说明或null","reason":"判断理由"}}'
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = self._chat_client.chat_json(messages)
            logger.info("[match] LLM returned coverage=%s, confidence=%.2f",
                         result.get("coverage"), result.get("confidence", 0))
            return result
        except Exception as e:
            logger.warning("[match] LLM call failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # 缓存管理
    # ------------------------------------------------------------------

    def invalidate_match_cache(self) -> None:
        """手动清空比对缓存（资料更新后调用）"""
        self._match_cache.clear()
        logger.info("[match] match cache invalidated")

    def set_corpus_version(self, version: int) -> None:
        """设置语料版本号（资料全量更新后调用）"""
        self._corpus_version = version
        self._match_cache.clear()


# ---------------------------------------------------------------------------
# 单例 — 注入 EmbeddingClient / ChatClient 以接通真实 RAG 向量链路
# ---------------------------------------------------------------------------
from app.core.config import settings
from app.services.llm_client import EmbeddingClient, OpenAIChatClient

_embedding_client = None
_chat_client = None
if getattr(settings, "DASHSCOPE_API_KEY", None):
    try:
        _embedding_client = EmbeddingClient(
            api_key=settings.DASHSCOPE_API_KEY,
            model=getattr(settings, "EMBEDDING_MODEL", "text-embedding-v3"),
        )
        logger.info("[vector_store] EmbeddingClient 已初始化")
    except Exception as _exc:
        logger.warning("[vector_store] EmbeddingClient 初始化失败，将降级为 n-gram 匹配: %s", _exc)
        _embedding_client = None
    try:
        _chat_client = OpenAIChatClient(
            api_key=settings.DASHSCOPE_API_KEY,
            model=settings.LLM_MODEL_NAME,
        )
        logger.info("[vector_store] OpenAIChatClient 已初始化")
    except Exception as _exc:
        logger.warning("[vector_store] OpenAIChatClient 初始化失败，LLM 比对不可用: %s", _exc)
        _chat_client = None

vector_store_service = VectorStoreService(
    embedding_client=_embedding_client,
    chat_client=_chat_client,
)