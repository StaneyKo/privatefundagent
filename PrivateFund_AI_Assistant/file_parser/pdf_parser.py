"""PDF 材料解析器。"""

from __future__ import annotations

from pathlib import Path

import fitz

from models import SourceChunk


def parse_pdf(file_path: Path) -> list[SourceChunk]:
    """按页提取可复制的 PDF 文本。"""
    chunks: list[SourceChunk] = []
    with fitz.open(str(file_path)) as document:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            if text:
                chunks.append(SourceChunk(text, file_path.name, f"第 {page_number} 页", "PDF"))
    return chunks

