"""页面三：API、策略和版本设置。"""

from __future__ import annotations

import streamlit as st

from ai.deepseek_api import DeepSeekClient, MODEL_MAP
from ai.research_combiner import combine_strategy_research
from config.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from document.performance_chart import build_performance_visual
from models import SourceChunk, SourceImage
from pages.result_state import store_generated_results
from research_output import build_generated_result
from ui import go_to, render_header


def render() -> None:
    """渲染生成参数并调用 DeepSeek。"""
    if not st.session_state.get("chunks"):
        go_to("upload")
        return
    render_header(3)
    st.subheader("AI 模型与接口")
    model_label = st.radio("AI 模型", list(MODEL_MAP), horizontal=True)
    if "兼容模式" in model_label:
        st.warning("该旧模型名将于 2026-07-24 停用，建议选择 DeepSeek-V4。")
    api_key = st.text_input(
        "API Key",
        value=st.session_state.get("api_key", DEEPSEEK_API_KEY),
        type="password",
        placeholder="sk-...",
        help="仅用于当前会话请求，不写入代码或数据库。建议通过 DEEPSEEK_API_KEY 环境变量配置。",
    )
    base_url = st.text_input("接口地址", value=st.session_state.get("base_url", DEEPSEEK_BASE_URL))
    st.session_state.api_key = api_key
    st.session_state.base_url = base_url
    if st.button("测试连接"):
        _test_connection(api_key, base_url, model_label)

    st.divider()
    st.subheader("关注策略")
    strategies = st.session_state.strategies
    selected = [item for item in st.session_state.get("selected_strategies", []) if item in strategies]
    if not selected and strategies:
        selected = strategies[:1]
    st.session_state.selected_strategies = selected
    selected_strategies = st.multiselect(
        "请选择本次需要生成的策略（可多选）",
        strategies,
        key="selected_strategies",
        placeholder="选择一个或多个策略",
    )
    if selected_strategies:
        if len(selected_strategies) == 1:
            st.caption("将生成一份 TXT、一份 Word 和一份引用核验结果。")
        else:
            st.caption(f"将整理 {len(selected_strategies)} 项策略，并合并生成一份 TXT 和一份 Word。")
    else:
        st.warning("请至少选择一个策略。")

    st.divider()
    st.subheader("固定版本与输出")
    st.info("每次同时生成一份客户简版 TXT 和一份详细 Word。相同材料、策略、模型与模板默认复用同一版内容。")
    force_refresh = st.checkbox(
        "忽略固定缓存并重新调用模型",
        value=False,
        help="一般不要勾选。勾选后会用新结果覆盖该组材料的固定版本。",
    )
    st.caption("Word 不限制页数；正文最后优先放入原材料中的代表产品业绩图，未发现合适原图时再按原始时间序列绘图。")
    back, generate = st.columns([1, 2])
    with back:
        if st.button("返回审核", use_container_width=True):
            go_to("analysis")
    with generate:
        if st.button("开始生成", type="primary", use_container_width=True):
            if not selected_strategies:
                st.error("请至少选择一个策略。")
            else:
                _generate(api_key, base_url, model_label, selected_strategies, force_refresh)


def _test_connection(api_key: str, base_url: str, model_label: str) -> None:
    """测试当前 DeepSeek 配置。"""
    try:
        client = DeepSeekClient(api_key, base_url, model_label)
        with st.spinner("正在测试连接…"):
            success, message = client.test_connection()
        (st.success if success else st.error)(message)
    except ValueError as exc:
        st.error(str(exc))


def _generate(
    api_key: str,
    base_url: str,
    model_label: str,
    strategies: list[str],
    force_refresh: bool,
) -> None:
    """逐个生成所选策略，分别保存可核验、可导出的客户版文件。"""
    try:
        chunks = [SourceChunk.from_dict(item) for item in st.session_state.chunks]
        source_images = [SourceImage.from_dict(item) for item in st.session_state.get("source_images", [])]
        company = st.session_state.company["name"]
        client = DeepSeekClient(api_key, base_url, model_label)
        progress = st.progress(0, text="正在准备多策略生成…")
        research_items = []
        errors: list[str] = []
        for index, strategy in enumerate(strategies, start=1):
            progress.progress((index - 1) / len(strategies), text=f"正在生成：{strategy}（{index}/{len(strategies)}）")
            try:
                research = client.generate(company, strategy, chunks, force_refresh=force_refresh)
                research_items.append((strategy, research))
            except Exception as exc:
                errors.append(f"{strategy}：{exc}")
        progress.progress(1.0, text="所选策略处理完成。")
        if not research_items:
            raise RuntimeError("；".join(errors) or "没有策略生成成功")
        completed_strategies = [strategy for strategy, _ in research_items]
        combined_strategy = "、".join(completed_strategies)
        combined_research = combine_strategy_research(research_items)
        performance_chart = build_performance_visual(
            source_images,
            chunks,
            combined_strategy,
            combined_research,
        )
        generated = build_generated_result(
            company,
            combined_strategy,
            combined_research,
            chunks,
            performance_chart,
            selected_strategies=completed_strategies,
        )
        store_generated_results(st.session_state, {combined_strategy: generated}, combined_strategy)
        st.session_state.generation_errors = errors
        go_to("citations")
    except Exception as exc:
        st.error(f"生成失败：{exc}")
        st.info("上传和识别结果已保留。请检查 API Key、接口地址、网络或账户余额后重试。")
