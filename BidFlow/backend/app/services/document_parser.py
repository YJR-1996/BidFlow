import os
from typing import List, Dict, Tuple

from app.core.exceptions import BusinessException


class DocumentParserService:
    def __init__(self):
        pass

    def parse(self, file_path: str, file_type: str) -> List[Dict]:
        try:
            if file_type == "txt":
                return self._parse_txt(file_path)
            elif file_type == "pdf":
                return self._parse_pdf(file_path)
            elif file_type == "docx":
                return self._parse_docx(file_path)
            else:
                raise BusinessException(message=f"不支持的文件类型: {file_type}")
        except BusinessException:
            raise
        except Exception as e:
            raise BusinessException(message=f"文件解析失败: {str(e)}")

    def _parse_txt(self, file_path: str) -> List[Dict]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="gbk") as f:
                content = f.read()

        if not content.strip():
            raise BusinessException(message="文件内容为空")

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in content.split("\n") if p.strip()]

        result = []
        for i, para in enumerate(paragraphs):
            result.append({
                "text": para,
                "page": 1,
                "paragraph_index": i,
                "source_ref": f"段落 {i + 1}",
            })

        return result

    def _parse_pdf(self, file_path: str) -> List[Dict]:
        """PDF 解析：① PyMuPDF 提取文字层 → ② 无文字（扫描件）走 qwen-vl-ocr → ③ PyPDF2 兜底。"""
        # ① 优先 PyMuPDF：文字层提取更稳（中文 CID 字体、阅读顺序）
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(file_path)
            if doc.page_count > 0:
                result = []
                for page_num in range(doc.page_count):
                    page = doc[page_num]
                    text = page.get_text("text", sort=True) or ""
                    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                    if not paragraphs:
                        paragraphs = [line.strip() for line in text.split("\n") if line.strip()]
                    for i, para in enumerate(paragraphs):
                        result.append({
                            "text": para,
                            "page": page_num + 1,
                            "paragraph_index": i,
                            "source_ref": f"第 {page_num + 1} 页 段落 {i + 1}",
                        })
                doc.close()
                if result:
                    return result
                doc.close()
        except Exception:
            pass  # PyMuPDF 失败 → 继续尝试 OCR / PyPDF2

        # ② 图片型扫描件：PyMuPDF 渲染每页 → qwen-vl-ocr 识别
        ocr_result = self._ocr_scan_pdf(file_path)
        if ocr_result:
            return ocr_result

        # ③ PyPDF2 兜底
        try:
            import PyPDF2
        except ImportError:
            return self._fallback_parse(file_path, "pdf")

        try:
            result = []
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                    if not paragraphs:
                        paragraphs = [text.strip()] if text.strip() else []
                    for i, para in enumerate(paragraphs):
                        result.append({
                            "text": para,
                            "page": page_num + 1,
                            "paragraph_index": i,
                            "source_ref": f"第 {page_num + 1} 页 段落 {i + 1}",
                        })

            if not result:
                raise BusinessException(message="PDF文件内容为空或无法提取")
            return result
        except BusinessException:
            raise
        except Exception as e:
            raise BusinessException(message=f"PDF解析失败: {str(e)}")

    def _ocr_scan_pdf(self, file_path: str) -> List[Dict]:
        """图片型 PDF：渲染每页 → qwen-vl-ocr 识别文字。任何失败返回 []，不阻断。"""
        try:
            from app.core.config import settings
            if not settings.OCR_ENABLED or not settings.DASHSCOPE_API_KEY:
                return []
            import fitz
            from app.services.llm_client import OpenAIChatClient

            client = OpenAIChatClient(
                api_key=settings.DASHSCOPE_API_KEY,
                model=settings.OCR_MODEL,
                timeout=60.0,
            )
            doc = fitz.open(file_path)
            result = []
            for page_num in range(doc.page_count):
                page = doc[page_num]
                pix = page.get_pixmap(dpi=settings.OCR_DPI)
                import base64
                import io
                buf = io.BytesIO()
                pix.save(buf, format="png")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                # 单页调用一次视觉模型
                text = client.chat_vision(
                    [b64],
                    "请识别这张招标文件扫描页中的所有文字，按阅读顺序输出，保留章节与条款结构。只输出识别到的文字，不要任何解释。",
                ).strip()
                # 用分号/句号分割为段落（OCR 文本通常无 \n\n）
                paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
                if not paragraphs and text:
                    paragraphs = [text]
                for i, para in enumerate(paragraphs):
                    result.append({
                        "text": para,
                        "page": page_num + 1,
                        "paragraph_index": i,
                        "source_ref": f"OCR 第 {page_num + 1} 页 段落 {i + 1}",
                    })
            doc.close()
            return result
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("[ocr] PDF OCR 失败，回退 PyPDF2/占位：%s", e)
            return []

    def _parse_docx(self, file_path: str) -> List[Dict]:
        try:
            import docx
        except ImportError:
            return self._fallback_parse(file_path, "docx")

        try:
            result = []
            doc = docx.Document(file_path)
            for i, para in enumerate(doc.paragraphs):
                text = para.text.strip()
                if text:
                    result.append({
                        "text": text,
                        "page": 1,
                        "paragraph_index": i,
                        "source_ref": f"段落 {i + 1}",
                    })

            # 表格内容补充：真实招标文件的资格/评分表常以表格承载，逐行转段落
            table_offset = len(doc.paragraphs)
            for ti, table in enumerate(doc.tables):
                for ri, row in enumerate(table.rows):
                    cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
                    if cells:
                        result.append({
                            "text": " | ".join(cells),
                            "page": 1,
                            "paragraph_index": table_offset + ti * 100 + ri,
                            "source_ref": f"表格 {ti + 1} 行 {ri + 1}",
                        })

            if not result:
                raise BusinessException(message="DOCX文件内容为空")
            return result
        except BusinessException:
            raise
        except Exception as e:
            raise BusinessException(message=f"DOCX解析失败: {str(e)}")

    def _fallback_parse(self, file_path: str, file_type: str) -> List[Dict]:
        file_size = os.path.getsize(file_path)
        result = [{
            "text": f"[已上传 {file_type.upper()} 文件，大小 {file_size} 字节。请安装 PyPDF2 或 python-docx 以支持内容解析。当前使用模拟数据演示。]",
            "page": 1,
            "paragraph_index": 0,
            "source_ref": f"{file_type.upper()} 文件",
        }]
        return result


document_parser_service = DocumentParserService()
