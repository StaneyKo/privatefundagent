"""把经核验的研究对象转换为可下载的多格式结果。"""

from __future__ import annotations

from typing import Any

from document.performance_chart import chart_for_session
from document.txt_generator import compose_natural_brief, generate_txt
from document.word_generator import generate_word
from models import GeneratedResearch, SourceChunk


def build_generated_result(
    company: str,
    strategy: str,
    research: GeneratedResearch,
    chunks: list[SourceChunk],
    performance_chart: dict[str, Any] | None,
    *,
    edit_revision: int = 0,
    selected_strategies: list[str] | None = None,
) -> dict[str, Any]:
    """生成 TXT、Word 及其会话记录。"""
    strategies = list(selected_strategies or [strategy])
    polished_brief = compose_natural_brief(research.brief, strategies)
    txt_data, txt_path = generate_txt(company, strategy, research.brief)
    docx_data, docx_path = generate_word(
        company,
        strategy,
        research,
        source_chunks=chunks,
        performance_chart=performance_chart,
    )
    return {
        "company": company,
        "strategy": strategy,
        "strategies": strategies,
        "brief": polished_brief,
        "detail": research.detail_markdown(strategies=strategies),
        "research": research.to_dict(),
        "audit": research.audit,
        "source_index": {item.source_id: item.to_dict() for item in chunks},
        "performance_chart": chart_for_session(performance_chart),
        "txt_data": txt_data,
        "txt_name": txt_path.name,
        "docx_data": docx_data,
        "docx_name": docx_path.name,
        "cache_key": research.cache_key,
        "from_cache": research.from_cache,
        "edit_revision": edit_revision,
    }
