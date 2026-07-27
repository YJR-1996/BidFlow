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
