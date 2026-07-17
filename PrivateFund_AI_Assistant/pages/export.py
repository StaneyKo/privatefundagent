"""页面四：结果预览与下载。"""

from __future__ import annotations

import streamlit as st

from pages.result_state import get_generated_results, set_active_strategy
from ui import go_to, render_header


def render() -> None:
    """展示已生成材料，并提供下载或重新生成入口。"""
    results = get_generated_results(st.session_state)
    if not results:
        go_to("generate")
        return
    render_header(5)
    strategies = list(results)
    active = st.session_state.get("active_strategy")
    if active not in results:
        active = strategies[0]
    if st.session_state.get("export_strategy_choice") not in results:
        st.session_state.export_strategy_choice = active
    if len(strategies) > 1:
        selected_strategy = st.selectbox(
            "选择需要预览和下载的策略",
            strategies,
            key="export_strategy_choice",
        )
        st.caption(f"本次共生成 {len(strategies)} 个策略，每个策略分别提供 TXT 和 Word。")
    else:
        selected_strategy = strategies[0]
    generated = set_active_strategy(st.session_state, selected_strategy)
    selected_strategies = generated.get("strategies", [generated.get("strategy")])
    if len(selected_strategies) > 1:
        st.info(f"本次已将以下策略合并为一份材料：{'、'.join(selected_strategies)}")
    st.success(f"{generated['company']}｜{generated['strategy']} 材料已生成")

    st.subheader("简版介绍材料")
    if generated.get("brief"):
        st.text_area("简版正文", generated["brief"], height=220, label_visibility="collapsed")
        st.caption("可在文本框内全选复制，或下载 TXT。")
        st.download_button(
            "下载 TXT",
            data=generated["txt_data"],
            file_name=generated["txt_name"],
            mime="text/plain; charset=utf-8",
            use_container_width=True,
        )
    else:
        st.info("本次未选择简版材料。返回生成设置可补充生成。")

    st.divider()
    st.subheader("详细研究材料")
    if generated.get("detail"):
        with st.expander("预览详细正文", expanded=True):
            st.markdown(generated["detail"])
        st.download_button(
            "下载 Word",
            data=generated["docx_data"],
            file_name=generated["docx_name"],
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )
    else:
        st.info("本次未选择详细研究材料。返回生成设置可补充生成。")

    left, middle, right = st.columns(3)
    with left:
        if st.button("重新生成", use_container_width=True):
            go_to("generate")
    with middle:
        if st.button("返回引用核验", use_container_width=True):
            go_to("citations")
    with right:
        if st.button("处理新材料", type="primary", use_container_width=True):
            for key in (
                "chunks",
                "source_images",
                "company",
                "strategies",
                "modules",
                "generated",
                "generated_results",
                "active_strategy",
                "selected_strategies",
                "uploaded_names",
            ):
                st.session_state.pop(key, None)
            go_to("upload")
