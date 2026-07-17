"""Streamlit 应用入口。"""

from __future__ import annotations

import streamlit as st

from config.config import ensure_directories
from database.database import init_database
from pages import analysis, citations, export, generate, upload
from ui import apply_theme


def main() -> None:
    """初始化应用并根据会话状态渲染四步流程。"""
    st.set_page_config(page_title="私募材料智能整理工具", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")
    ensure_directories()
    init_database()
    apply_theme()
    st.session_state.setdefault("current_page", "upload")
    routes = {
        "upload": upload.render,
        "analysis": analysis.render,
        "generate": generate.render,
        "citations": citations.render,
        "export": export.render,
    }
    routes.get(st.session_state.current_page, upload.render)()


if __name__ == "__main__":
    main()
