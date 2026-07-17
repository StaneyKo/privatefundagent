"""页面二：AI 识别与来源审核。"""

from __future__ import annotations

import streamlit as st

from ui import go_to, render_header


def render() -> None:
    """展示公司识别、策略与十一类信息模块。"""
    if not st.session_state.get("chunks"):
        go_to("upload")
        return
    render_header(2)
    if st.session_state.get("parse_errors"):
        with st.expander("部分文件未能解析", expanded=False):
            for error in st.session_state.parse_errors:
                st.warning(error)
    company = st.session_state.company
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.caption("AI 自动识别公司")
    st.header(company["name"])
    st.write(f"识别依据：**{company['evidence']}**")
    st.caption(f"来源：{company['source_file']}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("#### 已识别策略")
    st.write("　".join(f"`{item}`" for item in st.session_state.strategies))
    st.markdown("#### 信息模块（点击展开审核）")
    for module in st.session_state.modules:
        with st.expander(module["title"]):
            st.markdown("**AI 整理**")
            st.write(module["summary"])
            st.markdown("**信息来源与原始文本**")
            if not module["sources"]:
                st.info("资料未披露")
            for source in module["sources"]:
                st.caption(
                    f"{source.get('source_id') or '未编号'}　｜　{source['source_file']}　｜　"
                    f"{source.get('source_page') or '未标注位置'}"
                )
                st.code(source["text"], language=None, wrap_lines=True)

    back, next_step = st.columns(2)
    with back:
        if st.button("返回重新上传", use_container_width=True):
            go_to("upload")
    with next_step:
        if st.button("下一步：生成设置", type="primary", use_container_width=True):
            go_to("generate")
