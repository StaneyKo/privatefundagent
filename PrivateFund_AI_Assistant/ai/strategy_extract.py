"""投资策略自动识别。"""

from __future__ import annotations

from collections import OrderedDict

from models import SourceChunk


STRATEGY_KEYWORDS: OrderedDict[str, tuple[str, ...]] = OrderedDict(
    {
        "中证500指数增强": ("中证500指数增强", "500指数增强", "500指增", "中证500增强"),
        "沪深300指数增强": ("沪深300指数增强", "300指数增强", "300指增", "沪深300增强"),
        "中证1000指数增强": ("中证1000指数增强", "1000指数增强", "1000指增", "中证1000增强"),
        "市场中性": ("市场中性", "股票市场中性", "量化中性"),
        "CTA": ("CTA", "管理期货", "趋势跟踪"),
        "多策略": ("多策略", "复合策略"),
        "主观多头": ("主观多头", "股票多头"),
        "量化选股": ("量化选股", "量化多头"),
    }
)


def extract_strategies(chunks: list[SourceChunk]) -> list[str]:
    """根据文件名及正文关键词识别策略并按预设顺序返回。"""
    text = "\n".join(f"{chunk.source_file}\n{chunk.text}" for chunk in chunks).lower()
    results: list[str] = []
    for strategy, keywords in STRATEGY_KEYWORDS.items():
        if any(keyword.lower() in text for keyword in keywords):
            results.append(strategy)
    return results or ["其他/未明确"]

