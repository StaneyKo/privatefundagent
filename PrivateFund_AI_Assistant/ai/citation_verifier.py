"""将模型结构化输出逐条绑定到原文，并拦截未落到原文的事实。"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from models import CitationRef, GeneratedResearch, ResearchClaim, ResearchFact, ResearchSection, SourceChunk


SECTION_SPECS: tuple[tuple[str, str, int], ...] = (
    ("core_overview", "一、产品速览", 5),
    ("strategy_framework", "二、策略怎么获取收益", 10),
    ("risk_control", "三、风险控制与主要风险", 5),
    ("performance", "四、代表产品表现", 2),
    ("evaluation", "五、客户决策要点", 4),
    ("market_environment", "六、适用与不利市场环境", 2),
    ("other_information", "七、其他信息", 2),
    ("internal_business", "八、内部商务信息", 2),
)
METADATA_LABELS = ("材料日期", "公司口径", "业绩截止")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?(?:%|％)?")


def verify_research_payload(payload: dict[str, Any], chunks: list[SourceChunk]) -> GeneratedResearch:
    """只返回通过逐字引文与数字一致性校验的事实。"""
    source_map = {item.source_id: item for item in chunks if item.source_id}
    audit: list[dict[str, Any]] = []

    metadata_input = {
        str(item.get("label", "")): item
        for item in payload.get("metadata", [])
        if isinstance(item, dict)
    }
    metadata: list[ResearchFact] = []
    for label in METADATA_LABELS:
        raw = metadata_input.get(label, {"label": label, "value": "资料未披露", "citations": []})
        fact = _verify_fact(raw, source_map, audit, scope="元数据", section="报告信息", forced_label=label)
        metadata.append(fact or ResearchFact(label, "资料未披露", []))

    brief_claims = _verify_claims(
        payload.get("brief_claims", []),
        source_map,
        audit,
        scope="简版",
        section="简版介绍材料",
        limit=6,
    )
    section_input = {
        str(item.get("key", "")): item
        for item in payload.get("sections", [])
        if isinstance(item, dict)
    }
    sections: list[ResearchSection] = []
    for key, title, limit in SECTION_SPECS:
        raw_claims = section_input.get(key, {}).get("claims", [])
        claims = _verify_claims(raw_claims, source_map, audit, scope="详版", section=title, limit=limit)
        sections.append(ResearchSection(key=key, title=title, claims=claims))

    performance: list[ResearchFact] = []
    seen_facts: set[tuple[str, str]] = set()
    for raw in payload.get("performance", []):
        if not isinstance(raw, dict) or len(performance) >= 18:
            continue
        fact = _verify_fact(raw, source_map, audit, scope="详版表格", section="四、代表产品表现")
        if fact is None or fact.value == "资料未披露":
            continue
        key = (_normalize(fact.label), _normalize(fact.value))
        if key in seen_facts:
            continue
        seen_facts.add(key)
        performance.append(fact)

    return GeneratedResearch(
        brief=_build_brief(brief_claims),
        brief_claims=brief_claims,
        metadata=metadata,
        sections=sections,
        performance=performance,
        audit=audit,
    )


def validate_edited_text(
    text: str,
    citations: list[dict[str, Any]],
    chunks: list[SourceChunk],
) -> tuple[list[str], list[dict[str, Any]]]:
    """校验人工修订事实是否仍由原引用支撑，尤其检查数字口径。"""
    source_map = {item.source_id: item for item in chunks if item.source_id}
    _, reasons, details = _verify_text_and_citations(_clean_text(text), citations, source_map)
    return reasons, details


def _verify_claims(
    raw_claims: Any,
    source_map: dict[str, SourceChunk],
    audit: list[dict[str, Any]],
    *,
    scope: str,
    section: str,
    limit: int,
) -> list[ResearchClaim]:
    results: list[ResearchClaim] = []
    seen: set[str] = set()
    if not isinstance(raw_claims, list):
        return results
    for raw in raw_claims:
        if not isinstance(raw, dict):
            continue
        text = _clean_text(str(raw.get("text", "")))
        if not text or text == "资料未披露":
            _append_audit(audit, scope, section, "", text or "资料未披露", "未披露", False, [], [])
            continue
        normalized = _normalize(text)
        if normalized in seen:
            continue
        claim, reasons, citation_details = _verify_text_and_citations(text, raw.get("citations", []), source_map)
        included = claim is not None and len(results) < limit
        status = "通过" if included else "拦截"
        if claim is not None and not included:
            reasons = [f"超过模板章节上限（{limit} 条）"]
        _append_audit(audit, scope, section, "", text, status, included, reasons, citation_details)
        if included and claim is not None:
            seen.add(normalized)
            results.append(claim)
    return results


def _verify_fact(
    raw: dict[str, Any],
    source_map: dict[str, SourceChunk],
    audit: list[dict[str, Any]],
    *,
    scope: str,
    section: str,
    forced_label: str | None = None,
) -> ResearchFact | None:
    label = _clean_text(forced_label or str(raw.get("label", "")))
    value = _clean_text(str(raw.get("value", "")))
    if not label or not value or value == "资料未披露":
        _append_audit(audit, scope, section, label, value or "资料未披露", "未披露", True, [], [])
        return ResearchFact(label or "未命名指标", "资料未披露", [])
    text = f"{label}：{value}"
    claim, reasons, citation_details = _verify_text_and_citations(text, raw.get("citations", []), source_map)
    included = claim is not None
    _append_audit(audit, scope, section, label, value, "通过" if included else "拦截", included, reasons, citation_details)
    if not included or claim is None:
        return None
    return ResearchFact(label, value, claim.citations)


def _verify_text_and_citations(
    text: str,
    raw_citations: Any,
    source_map: dict[str, SourceChunk],
) -> tuple[ResearchClaim | None, list[str], list[dict[str, Any]]]:
    reasons: list[str] = []
    details: list[dict[str, Any]] = []
    citations: list[CitationRef] = []
    if not isinstance(raw_citations, list) or not raw_citations:
        return None, ["没有提供原文引用"], []

    for raw in raw_citations:
        if not isinstance(raw, dict):
            reasons.append("引用格式无效")
            continue
        source_id = str(raw.get("source_id", "")).strip()
        quote = str(raw.get("quote", "")).strip()
        source = source_map.get(source_id)
        exact_match = bool(source and quote and _normalize(quote) in _normalize(source.text))
        detail = {
            "source_id": source_id,
            "quote": quote,
            "source_file": source.source_file if source else "",
            "source_page": source.source_page if source else "",
            "exact_match": exact_match,
        }
        details.append(detail)
        if source is None:
            reasons.append(f"来源编号不存在：{source_id or '空'}")
        elif not quote:
            reasons.append(f"{source_id} 没有逐字引文")
        elif not exact_match:
            reasons.append(f"{source_id} 引文不是该位置原文的连续片段")
        else:
            citations.append(CitationRef(source_id, quote))

    if reasons or not citations:
        return None, list(dict.fromkeys(reasons or ["没有有效引用"])), details

    quote_text = "".join(item.quote for item in citations)
    missing_numbers = [token for token in _numbers(text) if token not in _numbers(quote_text)]
    if missing_numbers:
        reasons.append(f"引文未覆盖数字：{'、'.join(dict.fromkeys(missing_numbers))}")

    normalized_text_length = len(_normalize(text))
    normalized_quote_length = sum(len(_normalize(item.quote)) for item in citations)
    minimum_support = max(8, min(40, normalized_text_length // 3))
    if normalized_quote_length < minimum_support:
        reasons.append("逐字引文过短，无法支撑整条事实")

    if reasons:
        return None, reasons, details
    return ResearchClaim(text, citations), [], details


def _append_audit(
    audit: list[dict[str, Any]],
    scope: str,
    section: str,
    label: str,
    text: str,
    status: str,
    included: bool,
    reasons: list[str],
    citations: list[dict[str, Any]],
) -> None:
    audit.append(
        {
            "scope": scope,
            "section": section,
            "label": label,
            "text": text,
            "status": status,
            "included": included,
            "reasons": reasons,
            "citations": citations,
        }
    )


def _build_brief(claims: Iterable[ResearchClaim], max_chars: int = 300) -> str:
    selected: list[str] = []
    for claim in claims:
        sentence = _as_sentence(claim.text)
        if len("".join(selected)) + len(sentence) > max_chars:
            continue
        selected.append(sentence)
    return "".join(selected) or "资料未披露。"


def _as_sentence(value: str) -> str:
    value = value.strip()
    return value if value.endswith(("。", "！", "？", ";", "；")) else value + "。"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", "", normalized)


def _numbers(value: str) -> list[str]:
    return NUMBER_PATTERN.findall(unicodedata.normalize("NFKC", value))
