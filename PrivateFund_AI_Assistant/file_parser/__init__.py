"""材料解析模块。"""

from .image_extractor import assign_image_ids, extract_source_images
from .parser_factory import assign_source_ids, parse_file, parse_files

__all__ = [
    "assign_image_ids",
    "assign_source_ids",
    "extract_source_images",
    "parse_file",
    "parse_files",
]
