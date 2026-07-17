"""信息模块的本地可追溯整理。"""

from __future__ import annotations

import re
from collections import OrderedDict

from models import ModuleInfo, SourceChunk


MODULE_KEYWORDS: OrderedDict[str, tuple[str, ...]] = OrderedDict(
    {
        "公司基本情况": ("成立", "公司", "管理人", "注册", "规模", "股东"),
        "策略信息": ("策略", "指数增强", "市场中性", "cta", "多策略"),
        "投研团队": ("团队", "基金经理", "研究员", "投资经理", "从业"),
        "策略逻辑": ("策略逻辑", "多因子", "选股", "组合优化", "模型"),
        "超额收益来源": ("超额", "alpha", "收益来源", "因子", "选股收益"),
        "风险控制": ("风险", "风控", "敞口", "止损", "行业偏离"),
        "回撤与业绩特征": ("回撤", "收益率", "净值", "夏普", "业绩", "波动"),
        "产品和规模信息": ("产品", "规模", "管理规模", "存续", "备案"),
        "投资流程": ("投资流程", "研究流程", "交易", "组合构建", "调仓"),
        "模型框架": ("模型", "因子", "机器学习", "优化器", "框架"),
        "风险提示": ("风险提示", "风险", "回撤", "不保证", "波动"),
    }
)


def _matching_sentences(text: str, keywords: tuple[str, ...], limit: int = 4) -> list[str]:
    """提取包含关键词的句子或短段。"""
    parts = re.split(r"(?<=[。！？；;])|\n+", text)
    matched = [part.strip() for part in parts if any(word.lower() in part.lower() for word in keywords)]
    return [item[:240] for item in matched[:limit] if item]


def build_modules(chunks: list[SourceChunk]) -> list[ModuleInfo]:
    """生成包含摘要、来源和原文的模块列表。"""
    modules: list[ModuleInfo] = []
    for title, keywords in MODULE_KEYWORDS.items():
        source_pairs: list[tuple[SourceChunk, list[str]]] = []
        for chunk in chunks:
            sentences = _matching_sentences(chunk.text, keywords)
            if sentences:
                source_pairs.append((chunk, sentences))
        selected = source_pairs[:3]
        sentences = [sentence for _, items in selected for sentence in items]
        summary = "".join(sentences)[:500] if sentences else "资料未披露"
        sources = [
            SourceChunk("\n".join(items), chunk.source_file, chunk.source_page, chunk.file_type, chunk.source_id)
            for chunk, items in selected
        ]
        modules.append(ModuleInfo(title, summary, sources))
    return modules
