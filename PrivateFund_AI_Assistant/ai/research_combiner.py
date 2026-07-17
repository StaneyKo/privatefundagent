"""把多个单策略研究结果确定性合并为一份同版式客户材料。"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from ai.research_grouping import COMMON_GROUP, mark_group, near_duplicate, split_grouped_text, strip_strategy_subject
from models import CitationRef, GeneratedResearch, ResearchClaim, ResearchFact, ResearchSection


def combine_strategy_research(items: list[tuple[str, GeneratedResearch]]) -> GeneratedResearch:
    """保留单策略结构，将多策略事实按原顺序合并到同一研究对象。"""
    if not items:
        raise ValueError("没有可合并的策略研究结果")
    if len(items) == 1:
        return deepcopy(items[0][1])

    strategies = [strategy for strategy, _ in items]
    citation_detail_map = _citation_detail_map(items)
    metadata = _merge_metadata(items)
    sections = _merge_sections(items, strategies)
    merged_brief = _merge_claims(
        [(strategy, claim) for strategy, research in items for claim in research.brief_claims],
        strategies,
    )
    core_claims = next((section.claims for section in sections if section.key == "core_overview"), [])
    brief_claims = _dedupe_claims([*core_claims, *merged_brief], strategies)
    performance = [
        ResearchFact(fact.label, f"{strategy}：{fact.value}", deepcopy(fact.citations))
        for strategy, research in items
        for fact in research.performance
    ]
    audit = _build_combined_audit(metadata, brief_claims, sections, performance, citation_detail_map, strategies)
    for strategy, research in items:
        for entry in research.audit:
            if entry.get("status") != "拦截":
                continue
            copied = deepcopy(entry)
            copied["strategy"] = strategy
            copied["section"] = f"{strategy}｜{entry.get('section', '')}"
            audit.append(copied)

    cache_seed = "|".join(f"{strategy}:{research.cache_key}" for strategy, research in items)
    return GeneratedResearch(
        brief=_join_sentences(claim.text for claim in brief_claims),
        brief_claims=brief_claims,
        metadata=metadata,
        sections=sections,
        performance=performance,
        audit=audit,
        raw="\n\n".join(f"[{strategy}]\n{research.raw}" for strategy, research in items if research.raw),
        cache_key=hashlib.sha256(cache_seed.encode("utf-8")).hexdigest(),
        from_cache=all(research.from_cache for _, research in items),
    )


def _merge_metadata(items: list[tuple[str, GeneratedResearch]]) -> list[ResearchFact]:
    labels = list(dict.fromkeys(fact.label for _, research in items for fact in research.metadata))
    merged: list[ResearchFact] = []
    for label in labels:
        values: list[tuple[str, ResearchFact]] = []
        for strategy, research in items:
            fact = next((item for item in research.metadata if item.label == label), None)
            if fact and fact.value and fact.value != "资料未披露":
                values.append((strategy, fact))
        if not values:
            merged.append(ResearchFact(label, "资料未披露", []))
            continue
        unique_values = list(dict.fromkeys(fact.value for _, fact in values))
        value = unique_values[0] if len(unique_values) == 1 else "；".join(
            f"{strategy}：{fact.value}" for strategy, fact in values
        )
        merged.append(ResearchFact(label, value, _merge_citations(fact.citations for _, fact in values)))
    return merged


def _merge_sections(
    items: list[tuple[str, GeneratedResearch]],
    strategies: list[str],
) -> list[ResearchSection]:
    definitions: list[tuple[str, str]] = []
    for _, research in items:
        for section in research.sections:
            if section.key not in {key for key, _ in definitions}:
                definitions.append((section.key, section.title))
    merged: list[ResearchSection] = []
    for key, title in definitions:
        claims = [
            (strategy, claim)
            for strategy, research in items
            for section in research.sections
            if section.key == key
            for claim in section.claims
        ]
        merged.append(
            ResearchSection(
                key,
                title,
                _merge_claims(claims, strategies, force_common=key == "core_overview"),
            )
        )
    return merged


def _merge_claims(
    items: list[tuple[str, ResearchClaim]],
    all_strategies: list[str],
    *,
    force_common: bool = False,
) -> list[ResearchClaim]:
    grouped: list[dict[str, Any]] = []
    for strategy, claim in items:
        _, unmarked = split_grouped_text(claim.text, all_strategies)
        body = strip_strategy_subject(unmarked, strategy)
        group = next(
            (item for item in grouped if near_duplicate(item["text"], body, all_strategies)),
            None,
        )
        if group is None:
            group = {"text": body, "strategies": [], "citations": []}
            grouped.append(group)
        if strategy not in group["strategies"]:
            group["strategies"].append(strategy)
        group["citations"].extend(claim.citations)
    results: list[ResearchClaim] = []
    for group in grouped:
        source_strategies = group["strategies"]
        prefix = COMMON_GROUP if force_common or len(source_strategies) > 1 else source_strategies[0]
        text = mark_group(group["text"], prefix, all_strategies)
        results.append(ResearchClaim(text, _merge_citations([group["citations"]])))
    return results


def _dedupe_claims(claims: list[ResearchClaim], strategies: list[str]) -> list[ResearchClaim]:
    """合并简版中来自公司概况与各策略提取结果的重复事实。"""
    results: list[ResearchClaim] = []
    for claim in claims:
        group, body = split_grouped_text(claim.text, strategies)
        duplicate = next(
            (
                item
                for item in results
                if split_grouped_text(item.text, strategies)[0] == group
                and near_duplicate(split_grouped_text(item.text, strategies)[1], body, strategies)
            ),
            None,
        )
        if duplicate is None:
            results.append(deepcopy(claim))
        else:
            duplicate.citations = _merge_citations([duplicate.citations, claim.citations])
    return results


def _merge_citations(groups) -> list[CitationRef]:
    results: list[CitationRef] = []
    seen: set[tuple[str, str]] = set()
    for citations in groups:
        for citation in citations:
            key = (citation.source_id, citation.quote)
            if key in seen:
                continue
            seen.add(key)
            results.append(deepcopy(citation))
    return results


def _citation_detail_map(items: list[tuple[str, GeneratedResearch]]) -> dict[tuple[str, str], dict[str, Any]]:
    details: dict[tuple[str, str], dict[str, Any]] = {}
    for _, research in items:
        for entry in research.audit:
            for citation in entry.get("citations", []):
                key = (str(citation.get("source_id", "")), str(citation.get("quote", "")))
                details[key] = deepcopy(citation)
    return details


def _build_combined_audit(
    metadata: list[ResearchFact],
    brief_claims: list[ResearchClaim],
    sections: list[ResearchSection],
    performance: list[ResearchFact],
    citation_details: dict[tuple[str, str], dict[str, Any]],
    strategies: list[str],
) -> list[dict[str, Any]]:
    audit: list[dict[str, Any]] = []
    for fact in metadata:
        status = "未披露" if fact.value == "资料未披露" else "通过"
        audit.append(_audit_entry("元数据", "报告信息", fact.label, fact.value, status, status == "通过", fact.citations, citation_details))
    for claim in brief_claims:
        entry = _audit_entry("简版", "简版介绍材料", "", claim.text, "通过", True, claim.citations, citation_details)
        entry["strategy"] = split_grouped_text(claim.text, strategies)[0] or ""
        audit.append(entry)
    for section in sections:
        for claim in section.claims:
            entry = _audit_entry("详版", section.title, "", claim.text, "通过", True, claim.citations, citation_details)
            entry["strategy"] = split_grouped_text(claim.text, strategies)[0] or ""
            audit.append(entry)
    for fact in performance:
        entry = _audit_entry("详版表格", "四、代表产品表现", fact.label, fact.value, "通过", True, fact.citations, citation_details)
        entry["strategy"] = split_grouped_text(fact.value, strategies)[0] or ""
        audit.append(entry)
    return audit


def _audit_entry(
    scope: str,
    section: str,
    label: str,
    text: str,
    status: str,
    included: bool,
    citations: list[CitationRef],
    citation_details: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    details = []
    for citation in citations:
        key = (citation.source_id, citation.quote)
        details.append(
            deepcopy(
                citation_details.get(
                    key,
                    {"source_id": citation.source_id, "quote": citation.quote, "exact_match": True},
                )
            )
        )
    return {
        "scope": scope,
        "section": section,
        "label": label,
        "text": text,
        "status": status,
        "included": included,
        "reasons": [],
        "citations": details,
    }


def _join_sentences(values) -> str:
    sentences: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        sentences.append(text if text.endswith(("。", "！", "？", "；", ";")) else text + "。")
    return "".join(sentences) or "资料未披露。"
