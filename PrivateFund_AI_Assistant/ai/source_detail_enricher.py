"""当模型详版过少时，从上传原文中确定性补齐并书面化核心章节。"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from models import CitationRef, GeneratedResearch, ResearchClaim, SourceChunk


SECTION_TARGETS = {
    "core_overview": 3,
    "strategy_framework": 8,
    "risk_control": 2,
    "performance": 1,
}
SECTION_TERMS = {
    "core_overview": ("公司概况", "投资团队", "基金经理", "创始人", "投研", "策略条线", "管理规模", "投顾资质"),
    "strategy_framework": ("选股池", "持仓", "因子", "信号", "模型", "组合优化", "调仓", "换手率", "交易方式", "Alpha"),
    "risk_control": ("风控", "风险", "回撤", "行业偏离", "风格暴露", "个股上限", "Barra", "清仓"),
    "performance": ("代表产品", "业绩上", "统计区间", "累计收益", "超额收益", "最大回撤", "夏普"),
    "other_information": ("管理费", "业绩报酬", "费率", "起投", "开放日", "封盘", "收费"),
}
EXCLUDED_TEXT = (
    "过往业绩不预示",
    "不构成投资建议",
    "不构成对本产品",
    "仅供内部参考",
    "请勿外传",
    "风险悉知",
    "资料来源：",
    "参考材料中",
    "修改后请删除",
)
OTHER_STRATEGIES = ("A500", "中证1000", "1000指增", "1000指数增强", "量化择时", "市场中性", "中性策略", "CTA策略", "转债策略")
PARAGRAPH_RE = re.compile(r"段落\s*(\d+)")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?(?:%|％)?")


def enrich_research_from_sources(
    research: GeneratedResearch,
    chunks: list[SourceChunk],
    strategy: str,
) -> GeneratedResearch:
    """用原文补齐薄弱章节；仅整理语言，数字与逐字引文保持可核验。"""
    candidates = [item for item in chunks if _is_narrative_chunk(item)]
    header_map = _preceding_strategy_headers(chunks)
    section_map = {section.key: section for section in research.sections}
    existing = {_normalize(claim.text) for section in research.sections for claim in section.claims}
    aliases = _strategy_aliases(strategy)

    for section_key, target in SECTION_TARGETS.items():
        section = section_map.get(section_key)
        if section is None or len(section.claims) >= target:
            continue
        scored: list[tuple[int, SourceChunk]] = []
        for chunk in candidates:
            if _normalize(chunk.text) in existing:
                continue
            score = _score_candidate(section_key, chunk, strategy, aliases, header_map.get(_chunk_key(chunk), ""))
            if score >= _minimum_score(section_key):
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-item[0], _location_number(item[1]), item[1].source_id))
        scored = _deduplicate_scored(section_key, scored)
        needed = target - len(section.claims)
        chosen = [chunk for _, chunk in scored[:needed]]
        chosen.sort(key=lambda chunk: (_content_order(section_key, chunk.text), _location_number(chunk), chunk.source_id))
        for chunk in chosen:
            quote = chunk.text.strip()
            polished = _polish_source_claim(section_key, quote)
            if _numbers(polished) != _numbers(quote):
                polished = _finish_sentence(_strip_source_label(section_key, quote))
            claim = ResearchClaim(polished, [CitationRef(chunk.source_id, quote)])
            section.claims.append(claim)
            existing.add(_normalize(claim.text))
            research.audit.append(
                {
                    "scope": "本地原文补充",
                    "section": section.title,
                    "label": "",
                    "text": claim.text,
                    "status": "通过",
                    "included": True,
                    "reasons": [],
                    "citations": [
                        {
                            "source_id": chunk.source_id,
                            "quote": chunk.text.strip(),
                            "source_file": chunk.source_file,
                            "source_page": chunk.source_page or "",
                            "exact_match": True,
                        }
                    ],
                }
            )
    return research


def _polish_source_claim(section_key: str, text: str) -> str:
    """对常见尽调速记做保守的确定性改写，不添加来源之外的事实。"""
    value = _strip_source_label(section_key, re.sub(r"\s+", " ", text).strip())

    replacements = (
        ("，投研模式是", "，投研采用"),
        ("投研核心是", "核心投研方向为"),
        ("投研核心人员重点介绍：", "核心人员方面，"),
        ("，有投顾资质", "，具备投顾资质"),
        ("分策略来看，其中", "按策略划分，"),
        ("以树模型为主，90%树模型，10%神经网络", "模型以树模型为主，其中树模型占90%，神经网络占10%"),
        ("有10+市场风格模型，可以看作子模型", "组合包含10个以上市场风格模型，可视为不同子模型"),
        ("不同模型筛选再等权组合", "不同模型经筛选后再进行等权组合"),
        ("因子全部依靠人工挖掘，转化率比较高，从经济学底层逻辑上及国内外研报上获取", "因子由团队人工挖掘，主要依据经济学底层逻辑和国内外研究报告，因子转化率较高"),
        ("库内因子8000+", "因子库包含8000个以上因子"),
        ("实盘使用1000+", "实盘使用1000个以上因子"),
        ("底层因子会做分类", "底层因子按类别管理"),
        ("最底层最少有几十个", "最细分类至少包含数十个因子"),
        ("通用配比为", "通用因子配比为"),
        ("预测周期平均在", "平均预测周期为"),
        ("，截面信号", "，并采用截面信号"),
        ("年化双边换手", "年化双边换手率为"),
        ("不包含T0", "不含T0交易"),
        ("行业和风格不做单项硬控", "行业与风格暴露不设置单项硬性约束"),
        ("基于中国Barra和自研中国风险因子进行组合约束", "组合以中国Barra和自研中国风险因子为约束基础"),
        ("通过行业矩阵动态管理", "通过行业矩阵进行动态管理"),
        ("行业矩阵动态管理", "以行业矩阵进行动态管理"),
        ("风险控制集中在最终组合优化阶段", "风险控制集中在最终的组合优化环节"),
        ("风格暴露小", "风格暴露较小"),
        ("事前层面，", "事前，"),
        ("事中层面，", "事中，"),
        ("事后层面，", "事后，"),
        ("持仓变ST即清仓", "持仓标的变为ST后即清仓"),
        ("作为底层兜底", "作为基础风险缓冲"),
    )
    for source, target in replacements:
        value = value.replace(source, target)

    value = re.sub(r"^总人数(\d+人)，", r"公司共有\1，", value)
    value = re.sub(r"^([^，。]{2,12})，创始人，(\d+年以上从业经验)", r"公司创始人\1拥有\2", value)
    value = re.sub(r"核心人员方面，([^，。]{2,12})，创始人，(\d+年以上从业经验)", r"核心人员方面，公司创始人\1拥有\2", value)
    value = value.replace("中科大少年班毕业，东京大学物理学博士", "其毕业于中科大少年班，并获东京大学物理学博士学位")
    value = value.replace("2017年开始独立管理产品", "其于2017年开始独立管理产品")
    value = value.replace("2018年策略开始在天演资本实盘", "相关策略于2018年开始在天演资本实盘运行")
    value = value.replace("前百亿私募股票Alpha策略负责人", "曾任百亿私募股票Alpha策略负责人")
    value = value.replace("市场少数管理过400亿资金的PM之一", "其是市场上少数管理过400亿资金的投资经理之一")
    value = value.replace("博士学位，其于", "博士学位。其于")
    value = value.replace("实盘运行，曾任", "实盘运行。其曾任")
    value = value.replace("策略负责人，其是", "策略负责人，也是")
    value = value.replace("10%，因子采用", "10%。因子采用")
    value = value.replace("可视为不同子模型，不同模型经筛选后再进行等权组合来分散风险", "可视为不同子模型。不同模型经筛选后再进行等权组合，以分散风险")
    value = value.replace("，例如部分模型", "。例如，部分模型")
    value = value.replace("，通过不同维度模型组合贡献超额收益", "。不同维度的模型组合共同贡献超额收益")
    value = value.replace("因子转化率较高，因子库", "因子转化率较高。因子库")
    value = value.replace("实盘使用1000个以上因子，底层因子", "实盘使用1000个以上因子。底层因子")
    value = value.replace("在2025年8月风格切换时只有0.52的回撤", "2025年8月风格切换期间的回撤为0.52")
    value = value.replace("通过非线性模型和以行业矩阵进行动态管理整体组合风险", "通过非线性模型和行业矩阵对整体组合风险进行动态管理")
    value = value.replace("该策略的选股池与量化选股底层Alpha能力一致，剔除", "该策略沿用量化选股的底层Alpha能力，选股池剔除")
    value = value.replace("风险控制方面，事前，", "管理流程分为事前、事中和事后。事前，")
    value = value.replace("在组合约束上，事前，", "管理流程分为事前、事中和事后。事前，")
    value = re.sub(r"([\u4e00-\u9fffA-Za-z]+)，(\d{4}年\d{1,2}月)成立", r"\1成立于\2", value, count=1)
    value = re.sub(r"([。；])([^\s])", r"\1\2", value)
    return _finish_sentence(value)


def _strip_source_label(section_key: str, text: str) -> str:
    prefixes = {
        "core_overview": ("公司概况：", "投资团队：", "策略条线："),
        "strategy_framework": ("选股池：", "股票持仓分布：", "股票持仓：", "持仓：", "交易方式模型层面：", "因子层面：", "信号层面：", "交易方式：", "换手率："),
        "risk_control": ("交易风控：", "风控方面：", "风险控制："),
        "performance": ("产品情况：", "代表产品：", "业绩上，"),
    }
    value = text.strip()
    for prefix in prefixes.get(section_key, ()):
        if value.startswith(prefix):
            value = value[len(prefix) :].lstrip()
            break
    lead_ins = {
        "strategy_framework": {
            "选股池：": "该策略的选股池",
            "股票持仓分布：": "持仓分布为",
            "股票持仓：": "持仓方面，",
            "持仓：": "持仓方面，",
            "交易方式模型层面：": "在模型与组合构建上，",
            "因子层面：": "在因子研究上，",
            "信号层面：": "在信号设计上，",
            "交易方式：": "在交易执行上，",
            "换手率：": "在交易频率上，",
        },
        "risk_control": {
            "交易风控：": "在组合约束上，",
            "风控方面：": "在组合约束上，",
            "风险控制：": "风险控制方面，",
        },
    }
    for prefix, replacement in lead_ins.get(section_key, {}).items():
        if text.strip().startswith(prefix):
            return replacement + value
    return value


def _finish_sentence(text: str) -> str:
    value = text.strip().rstrip("；;")
    return value if value.endswith(("。", "！", "？")) else value + "。"


def _numbers(text: str) -> list[str]:
    return NUMBER_RE.findall(unicodedata.normalize("NFKC", text))


def _is_narrative_chunk(chunk: SourceChunk) -> bool:
    text = chunk.text.strip()
    if len(text) < 16 or len(text) > 900 or text.count("\n") > 8:
        return False
    if any(marker in text for marker in EXCLUDED_TEXT):
        return False
    if _is_strategy_heading(text):
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _is_strategy_heading(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return len(compact) < 60 and "策略" in compact and not any(
        term in compact for term in ("选股池", "持仓", "因子", "信号", "模型", "风控", "代表产品", "公司概况", "投资团队")
    )


def _preceding_strategy_headers(chunks: list[SourceChunk]) -> dict[tuple[str, str], str]:
    grouped: dict[str, list[SourceChunk]] = defaultdict(list)
    for chunk in chunks:
        if PARAGRAPH_RE.search(chunk.source_page or ""):
            grouped[chunk.source_file].append(chunk)
    result: dict[tuple[str, str], str] = {}
    for items in grouped.values():
        items.sort(key=_location_number)
        header = ""
        for item in items:
            if _is_strategy_heading(item.text):
                header = item.text.strip()
            result[_chunk_key(item)] = header
    return result


def _score_candidate(
    section_key: str,
    chunk: SourceChunk,
    strategy: str,
    aliases: tuple[str, ...],
    preceding_header: str,
) -> int:
    text = chunk.text.strip()
    term_hits = sum(1 for term in SECTION_TERMS[section_key] if term.casefold() in text.casefold())
    if term_hits == 0:
        return -1_000
    score = term_hits * 12
    if "私募基金投顾推荐报告" in chunk.source_file:
        score += 30
    direct = _contains_alias(text, aliases)
    header_direct = _contains_alias(preceding_header, aliases)
    other_strategy_hits = sum(1 for term in OTHER_STRATEGIES if term not in strategy and term in text)

    if section_key == "core_overview":
        if text.startswith("综合评价"):
            return -1_000
        if text.startswith("公司概况"):
            score += 120
        if text.startswith("投资团队"):
            score += 115
        if text.startswith("策略条线"):
            score += 55
        return score

    if section_key == "strategy_framework":
        if text.startswith(("风控", "交易风控")):
            return -1_000
        if direct:
            score += 85
        if header_direct:
            score += 110
        elif _is_underlying_alpha_context(strategy, preceding_header):
            if text.startswith(("股票持仓", "持仓")):
                return -1_000
            score += 42
        elif preceding_header:
            score -= 100
        score -= other_strategy_hits * 70
        if text.startswith(("选股池", "持仓", "股票持仓", "因子", "信号", "交易方式", "换手率")):
            score += 25
        return score

    if section_key == "risk_control":
        if "代表产品" in text and not any(term in text for term in ("风控", "风险")):
            return -1_000
        if text.startswith("交易风控"):
            score += 125
        if direct or header_direct:
            score += 80
        elif _is_underlying_alpha_context(strategy, preceding_header):
            score += 35
        elif preceding_header and "交易风控" not in text:
            score -= 70
        score -= other_strategy_hits * 30
        if "回撤" in text and "只有" in text and not re.search(r"\d+(?:\.\d+)?[%％]", text):
            score -= 120
        return score

    if section_key == "performance":
        if "代表产品" in text:
            score += 110
        if direct:
            score += 105
        score -= other_strategy_hits * 55
        return score

    if section_key == "other_information":
        if any(term in text for term in ("管理费", "业绩报酬", "费率", "起投")):
            score += 75
        return score
    return score


def _strategy_aliases(strategy: str) -> tuple[str, ...]:
    compact = re.sub(r"\s+", "", strategy)
    aliases = [compact]
    numbers = re.findall(r"\d{3,4}", compact)
    for number in numbers:
        aliases.extend((f"中证{number}", f"{number}指数增强", f"{number}指增"))
    if "指数增强" in compact or "指增" in compact:
        aliases.append("指数增强策略")
    return tuple(dict.fromkeys(alias for alias in aliases if alias))


def _contains_alias(text: str, aliases: tuple[str, ...]) -> bool:
    compact = re.sub(r"\s+", "", text)
    for alias in aliases:
        if alias == "指数增强策略":
            if alias in compact or "指增策略" in compact:
                return True
            continue
        if alias and alias[0].isdigit():
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}", compact):
                return True
        elif alias in compact:
            return True
    return False


def _is_underlying_alpha_context(strategy: str, header: str) -> bool:
    return ("指数增强" in strategy or "指增" in strategy) and "量化选股策略" in header


def _minimum_score(section_key: str) -> int:
    return {"core_overview": 45, "strategy_framework": 50, "risk_control": 50, "performance": 95}[section_key]


def _deduplicate_scored(section_key: str, scored: list[tuple[int, SourceChunk]]) -> list[tuple[int, SourceChunk]]:
    result: list[tuple[int, SourceChunk]] = []
    seen_text: set[str] = set()
    seen_roles: set[int] = set()
    for score, chunk in scored:
        normalized = _normalize(chunk.text)
        if normalized in seen_text:
            continue
        role = _content_order(section_key, chunk.text)
        if section_key == "strategy_framework" and role < 99 and role in seen_roles:
            continue
        result.append((score, chunk))
        seen_text.add(normalized)
        if role < 99:
            seen_roles.add(role)
    return result


def _content_order(section_key: str, text: str) -> int:
    orders = {
        "core_overview": ("公司概况", "投资团队", "策略条线"),
        "strategy_framework": ("选股池", "股票持仓", "持仓", "因子", "信号", "交易方式", "换手率"),
        "risk_control": ("风控方面", "交易风控", "风险"),
        "performance": ("代表产品", "业绩"),
        "other_information": ("起投", "费率", "管理费"),
    }
    for index, prefix in enumerate(orders.get(section_key, ()), start=1):
        if prefix in text:
            return index
    return 99


def _location_number(chunk: SourceChunk) -> int:
    match = PARAGRAPH_RE.search(chunk.source_page or "")
    return int(match.group(1)) if match else 100_000


def _chunk_key(chunk: SourceChunk) -> tuple[str, str]:
    return chunk.source_file, chunk.source_page or ""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
