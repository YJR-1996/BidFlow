"""LLM Reranker - 用大模型对检索候选片段精排（RAG 增强）。

- 零新依赖：复用 OpenAIChatClient（qwen-max），无需下载本地 rerank 模型。
- 候选片段截断后交给 LLM 打分（0.0~1.0），按分数降序返回 top_k。
- LLM 失败 / 候选过少时降级为原序，绝不阻塞主流程。
- 预留接口：后续可替换为 bge-reranker 或 DashScope rerank API（实现相同签名）。
"""

import json
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

_MAX_CANDIDATES = 15
_CHUNK_PREVIEW = 300


class LLMReranker:
    """基于 LLM 的检索结果重排器。"""

    def __init__(self):
        self._client = None  # 懒加载

    def _get_client(self):
        from app.core.config import settings
        from app.services.llm_client import OpenAIChatClient
        if self._client is None:
            self._client = OpenAIChatClient(
                api_key=settings.DASHSCOPE_API_KEY,
                model=settings.LLM_MODEL_NAME,
            )
        return self._client

    def rerank(
        self,
        query: str,
        candidates: List[Dict],
        top_k: int = 5,
    ) -> List[Dict]:
        """对候选片段重排，返回带 rerank_score 的排序列表（保持原字段）。"""
        if not candidates:
            return []
        if len(candidates) == 1:
            candidates[0]["rerank_score"] = 1.0
            return candidates[:top_k]

        # 上下文控制：最多 15 条、每条截断 300 字符
        subset = candidates[:_MAX_CANDIDATES]
        try:
            scores = self._call_llm(query, subset)
        except Exception as exc:
            logger.warning("[rerank] LLM 重排失败，降级原序: %s", exc)
            return candidates[:top_k]

        # 分数回填 + 降序排序（M5：逐值容错——LLM 返回非数值时按 0 处理，不回填异常）
        for i, cand in enumerate(subset):
            try:
                cand["rerank_score"] = float(scores.get(str(i), scores.get(i, 0.0)) or 0.0)
            except (TypeError, ValueError):
                cand["rerank_score"] = 0.0
        ranked = sorted(subset, key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        logger.info("[rerank] %d candidates → top %d (llm scored=%d)",
                    len(subset), min(len(ranked), top_k), len(scores))
        return ranked[:top_k]

    def _call_llm(self, query: str, candidates: List[Dict]) -> Dict:
        """调用 LLM 返回 {index: score} 映射，失败抛异常由调用方降级。"""
        client = self._get_client()

        items = []
        for i, cand in enumerate(candidates):
            meta = cand.get("metadata", {})
            source = meta.get("source_ref", meta.get("filename", f"片段{i + 1}"))
            text = (cand.get("text") or cand.get("content") or "")[:_CHUNK_PREVIEW]
            items.append(f'[{i}] 来源: {source}\n内容: {text}')

        system_prompt = (
            "你是招投标资料相关性打分器。请评估每个企业资料片段与招标需求的相关性，"
            "只输出 JSON：{\"scores\": {\"0\": 0.9, \"1\": 0.3, ...}}，score 取 0.0~1.0。"
            "相关（能直接佐证/覆盖需求内容）给高分，弱相关给低分，完全无关给 0。"
            "必须覆盖所有候选编号，不要编造片段中没有的信息。"
        )
        user_prompt = (
            f"## 招标需求\n{query}\n\n"
            f"## 候选资料片段\n" + "\n\n".join(items) +
            "\n\n请按相关性打分，JSON 返回 {\"scores\":{...}}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        data = client.chat_json(messages)
        raw = data.get("scores") or {}
        if not isinstance(raw, dict):
            raise ValueError(f"rerank 返回结构异常: {data}")
        return raw


# 进程内单例
llm_reranker = LLMReranker()
