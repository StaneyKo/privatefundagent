"""Streamlit 通用界面组件。"""

from __future__ import annotations

import streamlit as st


STEPS = ["1 上传材料", "2 审核识别", "3 生成设置", "4 引用核验", "5 结果导出"]


def apply_theme() -> None:
    """应用适合研究终端的简洁专业主题。"""
    st.markdown(
        """
        <style>
        .stApp { background: #f4f7fb; color: #172033; }
        .block-container { max-width: 1180px; padding-top: 2rem; padding-bottom: 3rem; }
        h1, h2, h3 { color: #17365d; letter-spacing: -0.02em; }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stSidebar"] { display: none; }
        .brand { font-size: 13px; font-weight: 700; color: #2b6cb0; letter-spacing: .08em; }
        .hero { padding: 26px 30px; border-radius: 16px; background: linear-gradient(135deg,#17365d,#265d91); color: white; margin-bottom: 22px; box-shadow: 0 10px 28px rgba(22,54,93,.14); }
        .hero h1 { color: white; margin: 2px 0 6px; font-size: 31px; }
        .hero p { opacity: .83; margin: 0; }
        .stepbar { display: grid; grid-template-columns: repeat(4,1fr); gap: 8px; margin: 0 0 22px; }
        .step { padding: 10px 12px; border-radius: 8px; background: #e8edf4; color: #667085; text-align: center; font-size: 13px; font-weight: 600; }
        .step.active { background: #d9e9f8; color: #174f82; box-shadow: inset 0 -3px #2f75b5; }
        .panel { border: 1px solid #dce3ec; background: white; border-radius: 12px; padding: 18px 20px; margin: 8px 0 16px; box-shadow: 0 2px 8px rgba(16,24,40,.04); }
        .source-label { font-size: 12px; color: #667085; }
        .stButton > button, .stDownloadButton > button { border-radius: 8px; font-weight: 650; }
        @media(max-width: 700px) { .stepbar { grid-template-columns: repeat(2,1fr); } .hero { padding:20px; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(step: int) -> None:
    """绘制统一标题和步骤导航。"""
    st.markdown(
        """<div class="hero"><div class="brand">PRIVATE FUND RESEARCH ASSISTANT</div>
        <h1>私募材料智能整理工具</h1><p>上传材料、核验来源、聚焦策略并生成研究材料</p></div>""",
        unsafe_allow_html=True,
    )
    routes = ["upload", "analysis", "generate", "citations", "export"]
    columns = st.columns(5)
    for index, (column, label, route) in enumerate(zip(columns, STEPS, routes), start=1):
        with column:
            if st.button(
                label,
                key=f"step_nav_{step}_{index}",
                type="primary" if index == step else "secondary",
                disabled=index == step,
                use_container_width=True,
            ):
                _navigate_from_header(route)


def _navigate_from_header(route: str) -> None:
    """校验流程数据后执行顶部步骤导航，并给出明确提示。"""
    if route in {"analysis", "generate", "citations", "export"} and not st.session_state.get("chunks"):
        st.warning("请先在下方点击“解析材料并进入第二步”。")
        return
    if route in {"citations", "export"} and not (
        st.session_state.get("generated") or st.session_state.get("generated_results")
    ):
        st.warning("尚未生成研究材料，请先完成第三步。")
        return
    go_to(route)


def go_to(step: str) -> None:
    """切换应用流程页面并刷新。"""
    st.session_state.current_page = step
    st.rerun()
