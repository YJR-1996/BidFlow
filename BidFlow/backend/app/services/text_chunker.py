"""文本块切分服务"""
from typing import List, Dict


class TextChunkerService:
    """将长文档切分为适合 Embedding 的小文本块"""

    def __init__(self):
        self.max_chunk_size = 512  # 每块最大字符数
        self.chunk_overlap = 50    # 重叠字符数

    def chunk(self, paragraphs: List[Dict]) -> List[Dict]:
        """将段落列表切分为文本块"""
        chunks = []
        current_chunk = ""
        chunk_id = 0

        for para in paragraphs:
            text = para.get("text", "")
            if not text:
                continue

            # 如果当前块加上这个段落超过限制
            if len(current_chunk) + len(text) > self.max_chunk_size and current_chunk:
                # 保存当前块
                chunks.append({
                    "text": current_chunk.strip(),
                    "chunk_id": chunk_id,
                    "metadata": {
                        "page": para.get("page", 1),
                        "paragraph_index": para.get("paragraph_index", 0),
                        "source_ref": para.get("source_ref", ""),
                    },
                })
                chunk_id += 1
                current_chunk = ""

            current_chunk += text + "\n"

        # 保存最后一个块
        if current_chunk.strip():
            chunks.append({
                "text": current_chunk.strip(),
                "chunk_id": chunk_id,
                "metadata": {
                    "page": paragraphs[-1].get("page", 1) if paragraphs else 1,
                    "paragraph_index": paragraphs[-1].get("paragraph_index", 0) if paragraphs else 0,
                    "source_ref": paragraphs[-1].get("source_ref", "") if paragraphs else "",
                },
            })

        return chunks


text_chunker_service = TextChunkerService()
