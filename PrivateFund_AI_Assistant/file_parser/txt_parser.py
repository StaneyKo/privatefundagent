"""纯文本材料解析器。"""

from __future__ import annotations

from pathlib import Path

from models import SourceChunk


def parse_txt(file_path: Path) -> list[SourceChunk]:
    """兼容常见中文编码读取文本。"""
    for encoding in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            text = file_path.read_text(encoding=encoding).strip()
            return [SourceChunk(text, file_path.name, "全文", "TXT")] if text else []
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别文本编码：{file_path.name}")

