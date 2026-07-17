"""文件解析统一入口。"""

from __future__ import annotations

from pathlib import Path

from config.config import SUPPORTED_EXTENSIONS
from models import SourceChunk

from .excel_parser import parse_excel
from .pdf_parser import parse_pdf
from .ppt_parser import parse_ppt
from .txt_parser import parse_txt
from .word_parser import parse_word
from .zip_parser import parse_zip


def parse_file(file_path: Path) -> list[SourceChunk]:
    """根据扩展名选择解析器。"""
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支持的文件类型：{suffix or '无扩展名'}")
    parsers = {
        ".docx": parse_word,
        ".pptx": parse_ppt,
        ".xlsx": parse_excel,
        ".xlsm": parse_excel,
        ".pdf": parse_pdf,
        ".txt": parse_txt,
    }
    if suffix == ".zip":
        return parse_zip(file_path, parse_file)
    return parsers[suffix](file_path)


def parse_files(file_paths: list[Path]) -> tuple[list[SourceChunk], list[str]]:
    """批量解析文件，单个失败不影响其他文件。"""
    chunks: list[SourceChunk] = []
    errors: list[str] = []
    for file_path in file_paths:
        try:
            chunks.extend(parse_file(file_path))
        except Exception as exc:
            errors.append(f"{file_path.name}：{exc}")
    return chunks, errors


def assign_source_ids(chunks: list[SourceChunk]) -> list[SourceChunk]:
    """按稳定顺序分配引用编号，使上传顺序变化不影响生成结果。"""
    ordered = sorted(
        chunks,
        key=lambda item: (
            item.source_file.casefold(),
            (item.source_page or "").casefold(),
            item.file_type.casefold(),
            item.text,
        ),
    )
    for index, chunk in enumerate(ordered, start=1):
        chunk.source_id = f"S{index:04d}"
    return ordered
