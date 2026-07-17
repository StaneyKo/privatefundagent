"""应用配置，敏感信息只从环境变量读取。"""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
CACHE_DIR = BASE_DIR / "cache" / "research"
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "database" / "private_fund.db"))
CONTENT_TEMPLATE_PATH = BASE_DIR / "assets" / "私募基金投顾推荐报告模板.docx"
STYLE_TEMPLATE_PATH = BASE_DIR / "assets" / "详细介绍材料版式模板.docx"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "100000"))

SUPPORTED_EXTENSIONS = {".docx", ".pptx", ".xlsx", ".xlsm", ".pdf", ".txt", ".zip"}


def ensure_directories() -> None:
    """创建运行时需要的目录。"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
