"""SQLite 数据访问层。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from config.config import DATABASE_PATH
from models import ModuleInfo


def get_connection(db_path: Path | str = DATABASE_PATH) -> sqlite3.Connection:
    """创建启用字典行的数据库连接。"""
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def init_database(db_path: Path | str = DATABASE_PATH) -> None:
    """初始化公司信息表。"""
    with get_connection(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS company_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                strategy TEXT,
                content TEXT NOT NULL,
                source_file TEXT NOT NULL,
                source_page TEXT,
                created_time TEXT NOT NULL
            )
            """
        )
        connection.commit()


def save_modules(company_name: str, strategies: list[str], modules: list[ModuleInfo], db_path: Path | str = DATABASE_PATH) -> int:
    """保存识别后的模块及其来源，返回新增记录数。"""
    strategy = "、".join(strategies)
    created_time = datetime.now().isoformat(timespec="seconds")
    rows: list[tuple[str, str, str, str, str | None, str]] = []
    for module in modules:
        if not module.sources:
            rows.append((company_name, strategy, f"{module.title}：{module.summary}", "资料汇总", None, created_time))
            continue
        for source in module.sources:
            rows.append((company_name, strategy, f"{module.title}：{module.summary}", source.source_file, source.source_page, created_time))
    with get_connection(db_path) as connection:
        connection.executemany(
            """INSERT INTO company_info
            (company_name, strategy, content, source_file, source_page, created_time)
            VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        connection.commit()
    return len(rows)

