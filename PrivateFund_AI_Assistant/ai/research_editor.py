"""人工修订已核验事实，并在保存前再次执行原文校验。"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from ai.citation_verifier import validate_edited_text
from ai.research_grouping import COMMON_GROUP, mark_group, split_grouped_text
from models import CitationRef, GeneratedResearch, ResearchClaim, ResearchFact, SourceChunk


def editable_facts(research: GeneratedResearch) -> list[dict[str, Any]]:
    """按客户输出顺序列出可人工修改或删除的事实。"""
    items: list[dict[str, Any]] = []
    strategies = _research_strategies(research)
    for index, fact in enumerate(research.metadata):
        if fact.value == "资料未披露" or not fact.citations:
            continue
        items.append(
            _record(
                ("metadata", index),
                "报告信息",
                fact.label,
                fact.value,
                fact.citations,
                value_kind="value",
            )
        )
    for index, claim in enumerate(research.brief_claims):
        group, value = split_grouped_text(claim.text, strategies)
        items.append(
            _record(
                ("brief", index),
                "简版介绍材料",
                f"简版事实 {index + 1}",
                value,
                claim.citations,
                value_kind="text",
                group_prefix=group,
            )
        )
    for section in research.sections:
        if section.key in {"internal_business", "follow_up"}:
            continue
        for index, claim in enumerate(section.claims):
            group, value = split_grouped_text(claim.text, strategies)
            items.append(
                _record(
                    ("section", section.key, index),
                    section.title,
                    f"正文事实 {index + 1}",
                    value,
                    claim.citations,
                    value_kind="text",
                    group_prefix=group,
                )
            )
    for index, fact in enumerate(research.performance):
        group, value = split_grouped_text(fact.value, strategies)
        items.append(
            _record(
                ("performance", index),
                "代表产品关键指标",
                fact.label,
                value,
                fact.citations,
                value_kind="value",
                group_prefix=group,
            )
        )
    return items


def apply_research_edit(
    research: GeneratedResearch,
    path: tuple[Any, ...],
    new_value: str,
    chunks: list[SourceChunk],
    *,
    delete: bool = False,
) -> GeneratedResearch:
    """修改指定事实；引用或数字校验失败时拒绝保存。"""
    updated = deepcopy(research)
    target = _research_target(updated, path)
    old_value = target.value if isinstance(target, ResearchFact) else target.text
    strategies = _research_strategies(updated)
    group, _ = split_grouped_text(old_value, strategies)
    edited_label = target.label if isinstance(target, ResearchFact) else ""
    if delete:
        _delete_research_target(updated, path)
    else:
        value = re.sub(r"\s+", " ", new_value).strip()
        _, value = split_grouped_text(value, strategies)
        if not value or value == "资料未披露":
            raise ValueError("修改后的事实不能为空；如需移除，请点击“删除此项”。")
        citations = [item.to_dict() for item in target.citations]
        edited_text = f"{edited_label}：{value}" if edited_label else value
        reasons, _ = validate_edited_text(edited_text, citations, chunks)
        if reasons:
            raise ValueError("；".join(reasons))
        stored_value = mark_group(value, group, strategies) if group else value
        if isinstance(target, ResearchFact):
            target.value = stored_value
        else:
            target.text = stored_value

    updated.brief = _join_sentences(claim.text for claim in updated.brief_claims)
    updated.from_cache = False
    saved_value = "" if delete else (target.value if isinstance(target, ResearchFact) else target.text)
    _update_audit(updated.audit, old_value, edited_label, saved_value, delete=delete)
    return updated


def promote_blocked_fact(
    research: GeneratedResearch,
    audit_index: int,
    new_value: str,
    source_ids: list[str],
    chunks: list[SourceChunk],
    destination: str,
) -> GeneratedResearch:
    """将被拦截事实经人工改写、重新选源和校验后加入指定客户输出位置。"""
    updated = deepcopy(research)
    if audit_index < 0 or audit_index >= len(updated.audit):
        raise IndexError("被拦截事实位置已失效，请刷新页面后重试。")
    entry = updated.audit[audit_index]
    if entry.get("status") != "拦截":
        raise ValueError("该事实已不在拦截状态。")
    value = re.sub(r"\s+", " ", new_value).strip()
    if not value or value == "资料未披露":
        raise ValueError("修改后的事实不能为空。")
    source_map = {item.source_id: item for item in chunks if item.source_id}
    selected_sources = [source_map[source_id] for source_id in source_ids if source_id in source_map]
    if not selected_sources:
        raise ValueError("请至少选择一段能够支撑该事实的上传原文。")
    citations = [CitationRef(item.source_id, item.text.strip()) for item in selected_sources if item.text.strip()]
    label = re.sub(r"\s+", " ", str(entry.get("label", ""))).strip()
    is_fact = destination == "performance" or destination.startswith("metadata:")
    validation_text = f"{label}：{value}" if is_fact and label else value
    reasons, details = validate_edited_text(
        validation_text,
        [item.to_dict() for item in citations],
        chunks,
    )
    if reasons:
        raise ValueError("；".join(reasons))

    strategies = _research_strategies(updated)
    entry_strategy = str(entry.get("strategy", "")).strip()
    group = ""
    if destination == "brief" or destination == "performance" or destination.startswith("section:"):
        if destination == "section:core_overview":
            group = COMMON_GROUP if strategies else ""
        elif entry_strategy in strategies:
            group = entry_strategy
    stored_value = mark_group(value, group, strategies) if group else value

    if destination == "brief":
        _append_unique_claim(updated.brief_claims, ResearchClaim(stored_value, citations))
    elif destination.startswith("section:"):
        section_key = destination.split(":", 1)[1]
        section = next((item for item in updated.sections if item.key == section_key), None)
        if section is None or section.key in {"internal_business", "follow_up"}:
            raise ValueError("所选正文章节不可用于客户材料。")
        _append_unique_claim(section.claims, ResearchClaim(stored_value, citations))
    elif destination == "performance":
        if not label:
            raise ValueError("加入关键指标表时必须保留指标名称。")
        if any(item.label == label and item.value == stored_value for item in updated.performance):
            raise ValueError("关键指标表中已经存在相同事实。")
        updated.performance.append(ResearchFact(label, stored_value, citations))
    elif destination.startswith("metadata:"):
        metadata_label = destination.split(":", 1)[1]
        fact = next((item for item in updated.metadata if item.label == metadata_label), None)
        if fact is None:
            updated.metadata.append(ResearchFact(metadata_label, value, citations))
        else:
            fact.value = value
            fact.citations = citations
    else:
        raise ValueError("请选择事实进入材料的位置。")

    updated.brief = _join_sentences(claim.text for claim in updated.brief_claims)
    updated.from_cache = False
    entry["text"] = stored_value
    entry["status"] = "通过"
    entry["included"] = True
    entry["reasons"] = []
    entry["citations"] = details
    entry["manual_edit"] = True
    entry["promoted_destination"] = destination
    return updated


def _record(
    path: tuple[Any, ...],
    section: str,
    label: str,
    value: str,
    citations,
    *,
    value_kind: str,
    group_prefix: str | None = None,
) -> dict[str, Any]:
    return {
        "path": path,
        "key": ":".join(str(item) for item in path),
        "section": section,
        "label": label,
        "value": value,
        "value_kind": value_kind,
        "group_prefix": group_prefix or "",
        "citations": [citation.to_dict() for citation in citations],
    }


def _research_target(research: GeneratedResearch, path: tuple[Any, ...]) -> ResearchFact | ResearchClaim:
    kind = path[0]
    if kind == "metadata":
        return research.metadata[int(path[1])]
    if kind == "brief":
        return research.brief_claims[int(path[1])]
    if kind == "performance":
        return research.performance[int(path[1])]
    if kind == "section":
        section = next(item for item in research.sections if item.key == path[1])
        return section.claims[int(path[2])]
    raise KeyError(f"未知事实位置：{path}")


def _delete_research_target(research: GeneratedResearch, path: tuple[Any, ...]) -> None:
    kind = path[0]
    if kind == "metadata":
        target = research.metadata[int(path[1])]
        target.value = "资料未披露"
        target.citations = []
        return
    if kind == "brief":
        research.brief_claims.pop(int(path[1]))
        return
    if kind == "performance":
        research.performance.pop(int(path[1]))
        return
    if kind == "section":
        section = next(item for item in research.sections if item.key == path[1])
        section.claims.pop(int(path[2]))
        return
    raise KeyError(f"未知事实位置：{path}")


def _update_audit(
    audit: list[dict[str, Any]],
    old_value: str,
    label: str,
    new_value: str,
    *,
    delete: bool,
) -> None:
    for item in audit:
        if not item.get("included") or item.get("text") != old_value:
            continue
        if label and item.get("label") != label:
            continue
        if delete:
            item["status"] = "人工删除"
            item["included"] = False
            item["reasons"] = ["用户在引用核验页从本次输出删除"]
        else:
            item["text"] = new_value
            item["manual_edit"] = True
        return


def _append_unique_claim(claims: list[ResearchClaim], claim: ResearchClaim) -> None:
    normalized = re.sub(r"\s+", "", claim.text)
    if any(re.sub(r"\s+", "", item.text) == normalized for item in claims):
        raise ValueError("所选章节中已经存在相同事实。")
    claims.append(claim)


def _research_strategies(research: GeneratedResearch) -> list[str]:
    """从合并研究的核验记录恢复策略顺序；单策略研究返回空列表。"""
    results: list[str] = []
    for entry in research.audit:
        strategy = str(entry.get("strategy", "")).strip()
        if not strategy or strategy == COMMON_GROUP or strategy in results:
            continue
        results.append(strategy)
    return results


def _join_sentences(values) -> str:
    sentences: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        sentences.append(text if text.endswith(("。", "！", "？", "；", ";")) else text + "。")
    return "".join(sentences) or "资料未披露。"
