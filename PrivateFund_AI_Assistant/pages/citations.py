"""页面四：逐条检查、人工修订生成事实及其上传原文。"""

from __future__ import annotations

import json

import streamlit as st

from ai.research_editor import apply_research_edit, editable_facts, promote_blocked_fact
from document.performance_chart import build_performance_visual, chart_for_json
from models import GeneratedResearch, SourceChunk, SourceImage
from pages.result_state import get_generated_results, set_active_strategy, store_generated_results
from research_output import build_generated_result
from ui import go_to, render_header


def render() -> None:
    """显示多策略核验结果，并允许逐项修改后重新生成客户文件。"""
    results = get_generated_results(st.session_state)
    if not results:
        go_to("generate")
        return
    render_header(4)
    st.subheader("引用核验与人工修订")
    st.caption("可直接修改与原文不一致的事实。保存前会重新检查原文引用和数字，保存后自动重建该策略的 TXT 与 Word。")

    strategies = list(results)
    active = st.session_state.get("active_strategy")
    if active not in results:
        active = strategies[0]
    if st.session_state.get("citation_strategy_choice") not in results:
        st.session_state.citation_strategy_choice = active
    if len(strategies) > 1:
        selected_strategy = st.selectbox(
            "正在核验的策略",
            strategies,
            key="citation_strategy_choice",
            help="每个策略分别维护事实、引用、TXT 和 Word。",
        )
        st.caption(f"已生成 {len(strategies)} 个策略，可逐一切换核验。")
    else:
        selected_strategy = strategies[0]
    generated = set_active_strategy(st.session_state, selected_strategy)
    selected_strategies = generated.get("strategies", [generated.get("strategy")])
    if len(selected_strategies) > 1:
        st.info(f"当前是一份合并材料，包含策略：{'、'.join(selected_strategies)}。所有修改都会同步到同一份 TXT 和 Word。")

    errors = st.session_state.get("generation_errors", [])
    if errors:
        with st.expander("部分策略生成失败", expanded=False):
            for error in errors:
                st.warning(error)
    notice = st.session_state.pop("edit_notice", None)
    if notice:
        st.success(notice)

    if generated.get("from_cache"):
        st.info(f"本策略复用了固定版本缓存：{str(generated.get('cache_key', ''))[:12]}")
    elif generated.get("edit_revision"):
        st.success(f"本策略已保存 {generated['edit_revision']} 次人工修订。")
    else:
        st.success(f"本策略已生成并保存固定版本：{str(generated.get('cache_key', ''))[:12]}")

    research = GeneratedResearch.from_dict(generated["research"])
    records = editable_facts(research)
    audit = generated.get("audit", [])
    blocked = sum(1 for item in audit if item.get("status") == "拦截")
    missing = sum(1 for item in audit if item.get("status") == "未披露")
    col1, col2, col3 = st.columns(3)
    col1.metric("进入输出的事实", len(records))
    col2.metric("被拦截", blocked)
    col3.metric("资料未披露", missing)

    _render_chart(generated)
    _render_editable_facts(generated, results, records)
    _render_blocked_facts(generated, results, research)

    audit_payload = {
        "company": generated.get("company"),
        "strategy": generated.get("strategy"),
        "cache_key": generated.get("cache_key"),
        "edit_revision": generated.get("edit_revision", 0),
        "research": generated.get("research"),
        "audit": generated.get("audit", []),
        "performance_chart": chart_for_json(generated.get("performance_chart")),
    }
    st.download_button(
        "下载当前策略引用核验 JSON",
        data=json.dumps(audit_payload, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=f"{generated.get('company', '产品')}_{generated.get('strategy', '策略')}_引用核验.json",
        mime="application/json",
        use_container_width=True,
    )

    back, next_step = st.columns(2)
    with back:
        if st.button("返回生成设置", use_container_width=True):
            go_to("generate")
    with next_step:
        if st.button("核验完成，查看导出", type="primary", use_container_width=True):
            go_to("export")


def _render_chart(generated: dict) -> None:
    chart = generated.get("performance_chart")
    st.markdown("#### 代表产品表现图")
    if not chart:
        st.info("上传材料中未发现与关注策略可靠对应的业绩原图，也未发现不少于 8 个观测点的日期—数值序列。")
        return
    st.image(chart["image_data"], use_container_width=True)
    if chart.get("visual_type") == "source_image":
        st.caption(f"原材料图片：{chart.get('image_id')}｜{chart.get('source_file')}｜{chart.get('source_page')}")
        with st.expander("查看图片所在位置的原文上下文"):
            st.code(chart.get("context_text", "未提取到相邻文字"), language=None, wrap_lines=True)
    else:
        st.caption(
            f"按原始时间序列绘制：{chart.get('source_id')}｜{chart.get('source_file')}｜"
            f"{chart.get('source_page')}｜{chart.get('point_count')} 个观测点"
        )
        source = generated.get("source_index", {}).get(chart.get("source_id"), {})
        with st.expander("查看图表对应的完整原始表格文本"):
            st.code(source.get("text", "未找到原文"), language=None, wrap_lines=True)


def _render_editable_facts(generated: dict, results: dict[str, dict], records: list[dict]) -> None:
    st.markdown("#### 逐条事实（可修改）")
    sections = list(dict.fromkeys(item["section"] for item in records))
    section_filter = st.selectbox(
        "章节",
        ["全部"] + sections,
        key=f"section_filter_{generated['strategy']}",
    )
    visible = [item for item in records if section_filter == "全部" or item["section"] == section_filter]
    if not visible:
        st.info("当前章节没有可编辑事实。")
        return

    revision = int(generated.get("edit_revision", 0))
    for item in visible:
        title = f"✅ {item['section']}｜{item['label']}"
        with st.expander(title, expanded=False):
            form_key = f"fact_form_{generated['strategy']}_{revision}_{item['key']}"
            with st.form(form_key):
                field_label = "修改后的数值" if item["value_kind"] == "value" else "修改后的事实"
                edited_value = st.text_area(
                    field_label,
                    value=item["value"],
                    height=88 if item["value_kind"] == "text" else 68,
                    key=f"fact_value_{generated['strategy']}_{revision}_{item['key']}",
                    help="请依据下方原文调整；数字必须能在当前引用中找到。",
                )
                st.markdown("**对应原文**")
                _render_citations(generated, item["citations"])
                save_col, delete_col = st.columns([2, 1])
                with save_col:
                    save = st.form_submit_button("保存修改并重建文件", type="primary", use_container_width=True)
                with delete_col:
                    delete = st.form_submit_button("从本次输出删除", use_container_width=True)
            if save or delete:
                _save_edit(generated, results, item, edited_value, delete=delete)


def _render_citations(generated: dict, citations: list[dict]) -> None:
    for index, citation in enumerate(citations, start=1):
        source_id = citation.get("source_id", "")
        source = generated.get("source_index", {}).get(source_id, {})
        st.markdown(f"**原文 {index}｜{source_id}**")
        st.caption(
            f"{source.get('source_file', '')}｜{source.get('source_page') or '未标注位置'}｜逐字匹配：是"
        )
        st.code(citation.get("quote", ""), language=None, wrap_lines=True)
        with st.expander(f"查看 {source_id} 该位置完整原文", expanded=False):
            st.code(source.get("text", "未找到原文"), language=None, wrap_lines=True)


def _save_edit(
    generated: dict,
    results: dict[str, dict],
    item: dict,
    edited_value: str,
    *,
    delete: bool,
) -> None:
    try:
        chunks = [SourceChunk.from_dict(value) for value in st.session_state.chunks]
        research = GeneratedResearch.from_dict(generated["research"])
        updated = apply_research_edit(research, tuple(item["path"]), edited_value, chunks, delete=delete)
        action = "删除" if delete else "修改"
        _rebuild_result(generated, results, updated, chunks, f"已{action}“{item['label']}”，并重新生成 TXT 和 Word。")
    except Exception as exc:
        st.error(f"未保存：{exc}")


def _render_blocked_facts(generated: dict, results: dict[str, dict], research: GeneratedResearch) -> None:
    blocked = [
        (index, item)
        for index, item in enumerate(generated.get("audit", []))
        if item.get("status") == "拦截"
    ]
    if not blocked:
        return
    st.markdown(f"#### 被拦截事实（可修订，共 {len(blocked)} 条）")
    st.caption("修改事实、选择能够支撑它的上传原文并指定进入位置；校验通过后会立即加入材料并重建文件。")
    source_index = generated.get("source_index", {})
    source_options = list(source_index)
    destinations, destination_labels = _promotion_destinations(research)
    revision = int(generated.get("edit_revision", 0))
    for audit_index, item in blocked:
        title = f"⛔ {item.get('section', '')}｜{item.get('label') or item.get('text', '')[:36]}"
        with st.expander(title, expanded=False):
            for reason in item.get("reasons", []):
                st.error(reason)
            form_key = f"blocked_form_{generated['strategy']}_{revision}_{audit_index}"
            existing_source_ids = [
                citation.get("source_id", "")
                for citation in item.get("citations", [])
                if citation.get("source_id", "") in source_index
            ]
            default_destination = _default_promotion_destination(item, research, destinations)
            if source_options:
                preview_default = existing_source_ids[0] if existing_source_ids else source_options[0]
                preview_source = st.selectbox(
                    "预览上传原文",
                    source_options,
                    index=source_options.index(preview_default),
                    format_func=lambda source_id: _source_option_label(source_id, source_index),
                    key=f"blocked_preview_{generated['strategy']}_{revision}_{audit_index}",
                )
                with st.expander(f"查看 {preview_source} 完整原文", expanded=False):
                    st.code(source_index.get(preview_source, {}).get("text", "未找到原文"), language=None, wrap_lines=True)
            with st.form(form_key):
                edited_value = st.text_area(
                    "核验修改后的事实",
                    value=item.get("text") or "",
                    height=92,
                    key=f"blocked_value_{generated['strategy']}_{revision}_{audit_index}",
                )
                destination = st.selectbox(
                    "校验通过后进入",
                    destinations,
                    index=destinations.index(default_destination),
                    format_func=lambda value: destination_labels[value],
                    key=f"blocked_destination_{generated['strategy']}_{revision}_{audit_index}",
                )
                selected_sources = st.multiselect(
                    "选择支撑原文（可多选）",
                    source_options,
                    default=existing_source_ids,
                    format_func=lambda source_id: _source_option_label(source_id, source_index),
                    key=f"blocked_sources_{generated['strategy']}_{revision}_{audit_index}",
                    help="保存时使用所选位置的完整原文重新核验，数字必须能在这些原文中找到。",
                )
                promote = st.form_submit_button("核验并加入材料", type="primary", use_container_width=True)
            if promote:
                _save_promoted_fact(
                    generated,
                    results,
                    audit_index,
                    edited_value,
                    selected_sources,
                    destination,
                )


def _promotion_destinations(research: GeneratedResearch) -> tuple[list[str], dict[str, str]]:
    values = ["brief"]
    labels = {"brief": "简版介绍材料（TXT）"}
    for section in research.sections:
        if section.key in {"internal_business", "follow_up"}:
            continue
        value = f"section:{section.key}"
        values.append(value)
        labels[value] = f"Word 正文｜{section.title}"
    values.append("performance")
    labels["performance"] = "Word｜代表产品关键指标表"
    for fact in research.metadata:
        value = f"metadata:{fact.label}"
        values.append(value)
        labels[value] = f"Word 报告信息｜{fact.label}"
    return values, labels


def _default_promotion_destination(item: dict, research: GeneratedResearch, destinations: list[str]) -> str:
    scope = item.get("scope")
    if scope == "简版":
        return "brief"
    if scope == "详版表格" and "performance" in destinations:
        return "performance"
    if scope == "元数据" and f"metadata:{item.get('label', '')}" in destinations:
        return f"metadata:{item.get('label', '')}"
    section_title = str(item.get("section", "")).split("｜")[-1]
    for section in research.sections:
        value = f"section:{section.key}"
        if section.title == section_title and value in destinations and section.key not in {"internal_business", "follow_up"}:
            return value
    return "brief"


def _source_option_label(source_id: str, source_index: dict) -> str:
    source = source_index.get(source_id, {})
    excerpt = " ".join(str(source.get("text", "")).split())[:60]
    return f"{source_id}｜{source.get('source_file', '')}｜{source.get('source_page') or '未标注位置'}｜{excerpt}"


def _save_promoted_fact(
    generated: dict,
    results: dict[str, dict],
    audit_index: int,
    edited_value: str,
    source_ids: list[str],
    destination: str,
) -> None:
    try:
        chunks = [SourceChunk.from_dict(value) for value in st.session_state.chunks]
        research = GeneratedResearch.from_dict(generated["research"])
        updated = promote_blocked_fact(
            research,
            audit_index,
            edited_value,
            source_ids,
            chunks,
            destination,
        )
        _rebuild_result(generated, results, updated, chunks, "该事实已通过人工核验并加入材料，TXT 和 Word 已重新生成。")
    except Exception as exc:
        st.error(f"未加入材料：{exc}")


def _rebuild_result(
    generated: dict,
    results: dict[str, dict],
    updated: GeneratedResearch,
    chunks: list[SourceChunk],
    notice: str,
) -> None:
    source_images = [SourceImage.from_dict(value) for value in st.session_state.get("source_images", [])]
    chart = (
        build_performance_visual(source_images, chunks, generated["strategy"], updated)
        if source_images
        else generated.get("performance_chart")
    )
    refreshed = build_generated_result(
        generated["company"],
        generated["strategy"],
        updated,
        chunks,
        chart,
        edit_revision=int(generated.get("edit_revision", 0)) + 1,
        selected_strategies=list(generated.get("strategies", [generated["strategy"]])),
    )
    updated_results = dict(results)
    updated_results[generated["strategy"]] = refreshed
    store_generated_results(st.session_state, updated_results, generated["strategy"])
    st.session_state.edit_notice = notice
    st.rerun()
