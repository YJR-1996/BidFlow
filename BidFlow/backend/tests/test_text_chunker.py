"""text_chunker 服务单元测试

覆盖段落切分、边界条件（空输入、超长段落、单段、元数据继承）等场景。
"""
from app.services.text_chunker import TextChunkerService


def test_empty_paragraphs_returns_empty():
    """空段落列表应返回空切片列表"""
    service = TextChunkerService()
    assert service.chunk([]) == []


def test_paragraphs_with_empty_text_are_skipped():
    """text 为空字符串的段落应被跳过"""
    service = TextChunkerService()
    paragraphs = [
        {"text": "", "page": 1, "paragraph_index": 0, "source_ref": "p1"},
        {"text": "   ", "page": 1, "paragraph_index": 1, "source_ref": "p2"},
    ]
    # 全部空白，最终 current_chunk 仍为空，不产生切片
    assert service.chunk(paragraphs) == []


def test_single_short_paragraph_produces_one_chunk():
    """单条短段落应整合为一个切片"""
    service = TextChunkerService()
    paragraphs = [{"text": "这是一段短文本。", "page": 1, "paragraph_index": 0, "source_ref": "p1"}]
    chunks = service.chunk(paragraphs)

    assert len(chunks) == 1
    assert chunks[0]["text"] == "这是一段短文本。"
    assert chunks[0]["chunk_id"] == 0
    # 元数据应继承自最后一段
    assert chunks[0]["metadata"]["page"] == 1
    assert chunks[0]["metadata"]["source_ref"] == "p1"


def test_multiple_short_paragraphs_merged_into_one_chunk():
    """多条短段落合计未超阈值时应合并为一个切片"""
    service = TextChunkerService()
    paragraphs = [
        {"text": "第一段。", "page": 1, "paragraph_index": 0, "source_ref": "p1"},
        {"text": "第二段。", "page": 1, "paragraph_index": 1, "source_ref": "p2"},
    ]
    chunks = service.chunk(paragraphs)

    assert len(chunks) == 1
    # 两段都被包含，且以换行分隔
    assert "第一段。" in chunks[0]["text"]
    assert "第二段。" in chunks[0]["text"]
    # 最后一段的元数据被继承
    assert chunks[0]["metadata"]["paragraph_index"] == 1


def test_long_paragraphs_split_into_multiple_chunks():
    """超过 max_chunk_size 的段落应被切分为多个切片"""
    service = TextChunkerService()
    # 构造 3 段，每段 300 字，合计 900 > 512，应产生多个切片
    long_text = "A" * 300
    paragraphs = [
        {"text": long_text, "page": 1, "paragraph_index": i, "source_ref": f"p{i}"}
        for i in range(3)
    ]
    chunks = service.chunk(paragraphs)

    assert len(chunks) >= 2
    # 每个 chunk 不应超过 max_chunk_size（加换行符容差）
    for c in chunks:
        assert len(c["text"]) <= service.max_chunk_size + 10
    # chunk_id 单调递增
    ids = [c["chunk_id"] for c in chunks]
    assert ids == sorted(ids)
    assert ids[0] == 0


def test_chunk_inherits_metadata_from_paragraph():
    """切片元数据应继承自触发切分的段落（page/paragraph_index/source_ref）"""
    service = TextChunkerService()
    big = "B" * 600  # 单段即超过阈值
    paragraphs = [
        {"text": big, "page": 5, "paragraph_index": 12, "source_ref": "ref-5"},
    ]
    chunks = service.chunk(paragraphs)
    # 单段超阈值：第一次进入循环 current_chunk 为空，不会立即切分，而是累加；
    # 循环结束后 current_chunk 非空，保存为最后一个块
    assert len(chunks) >= 1
    last = chunks[-1]
    assert last["metadata"]["page"] == 5
    assert last["metadata"]["source_ref"] == "ref-5"


def test_missing_metadata_fields_use_defaults():
    """段落缺少 page/paragraph_index/source_ref 时应使用默认值"""
    service = TextChunkerService()
    paragraphs = [{"text": "只有文本的段落。"}]
    chunks = service.chunk(paragraphs)

    assert len(chunks) == 1
    assert chunks[0]["metadata"]["page"] == 1
    assert chunks[0]["metadata"]["paragraph_index"] == 0
    assert chunks[0]["metadata"]["source_ref"] == ""


def test_missing_text_field_skipped():
    """段落缺少 text 字段时应被跳过，不报错"""
    service = TextChunkerService()
    paragraphs = [
        {"page": 1},  # 无 text
        {"text": "有效段落。", "page": 2},
    ]
    chunks = service.chunk(paragraphs)
    assert len(chunks) == 1
    assert "有效段落。" in chunks[0]["text"]


def test_singleton_instance_exists():
    """模块级单例 text_chunker_service 应可用"""
    from app.services.text_chunker import text_chunker_service
    assert text_chunker_service is not None
    assert isinstance(text_chunker_service, TextChunkerService)
