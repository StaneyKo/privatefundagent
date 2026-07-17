"""跨模块共享的数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


@dataclass
class SourceChunk:
    """表示一段带来源定位的原始文本。"""

    text: str
    source_file: str
    source_page: str | None = None
    file_type: str = ""
    source_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceChunk":
        """从字典恢复对象。"""
        return cls(**data)


@dataclass
class SourceImage:
    """表示从上传材料中直接提取的原始图片或页面截图。"""

    image_data: bytes
    source_file: str
    source_page: str | None = None
    context_text: str = ""
    width: int = 0
    height: int = 0
    file_type: str = ""
    image_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为可直接存入会话的字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceImage":
        """从会话字典恢复对象。"""
        return cls(**data)


@dataclass
class ModuleInfo:
    """表示一个可审核的信息模块。"""

    title: str
    summary: str
    sources: list[SourceChunk]

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典。"""
        return {"title": self.title, "summary": self.summary, "sources": [item.to_dict() for item in self.sources]}


@dataclass
class CitationRef:
    """模型事实引用的一段逐字原文。"""

    source_id: str
    quote: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CitationRef":
        return cls(source_id=str(data.get("source_id", "")), quote=str(data.get("quote", "")))


@dataclass
class ResearchClaim:
    """一条可独立核验的研究事实。"""

    text: str
    citations: list[CitationRef]

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "citations": [item.to_dict() for item in self.citations]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchClaim":
        return cls(
            text=str(data.get("text", "")),
            citations=[CitationRef.from_dict(item) for item in data.get("citations", []) if isinstance(item, dict)],
        )

    @property
    def source_ids(self) -> list[str]:
        return list(dict.fromkeys(item.source_id for item in self.citations if item.source_id))


@dataclass
class ResearchFact:
    """元数据或表格中的“标签—数值”事实。"""

    label: str
    value: str
    citations: list[CitationRef]

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "value": self.value, "citations": [item.to_dict() for item in self.citations]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchFact":
        return cls(
            label=str(data.get("label", "")),
            value=str(data.get("value", "")),
            citations=[CitationRef.from_dict(item) for item in data.get("citations", []) if isinstance(item, dict)],
        )

    @property
    def source_ids(self) -> list[str]:
        return list(dict.fromkeys(item.source_id for item in self.citations if item.source_id))


@dataclass
class ResearchSection:
    """模板中的固定报告章节。"""

    key: str
    title: str
    claims: list[ResearchClaim]

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "title": self.title, "claims": [item.to_dict() for item in self.claims]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchSection":
        return cls(
            key=str(data.get("key", "")),
            title=str(data.get("title", "")),
            claims=[ResearchClaim.from_dict(item) for item in data.get("claims", []) if isinstance(item, dict)],
        )


@dataclass
class GeneratedResearch:
    """经本地原文核验后允许进入导出文件的完整研究结果。"""

    brief: str
    brief_claims: list[ResearchClaim]
    metadata: list[ResearchFact]
    sections: list[ResearchSection]
    performance: list[ResearchFact]
    audit: list[dict[str, Any]]
    raw: str = ""
    cache_key: str = ""
    from_cache: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "brief": self.brief,
            "brief_claims": [item.to_dict() for item in self.brief_claims],
            "metadata": [item.to_dict() for item in self.metadata],
            "sections": [item.to_dict() for item in self.sections],
            "performance": [item.to_dict() for item in self.performance],
            "audit": self.audit,
            "raw": self.raw,
            "cache_key": self.cache_key,
            "from_cache": self.from_cache,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GeneratedResearch":
        return cls(
            brief=str(data.get("brief", "")),
            brief_claims=[ResearchClaim.from_dict(item) for item in data.get("brief_claims", []) if isinstance(item, dict)],
            metadata=[ResearchFact.from_dict(item) for item in data.get("metadata", []) if isinstance(item, dict)],
            sections=[ResearchSection.from_dict(item) for item in data.get("sections", []) if isinstance(item, dict)],
            performance=[ResearchFact.from_dict(item) for item in data.get("performance", []) if isinstance(item, dict)],
            audit=[item for item in data.get("audit", []) if isinstance(item, dict)],
            raw=str(data.get("raw", "")),
            cache_key=str(data.get("cache_key", "")),
            from_cache=bool(data.get("from_cache", False)),
        )

    def detail_markdown(
        self,
        *,
        include_citations: bool = False,
        strategies: list[str] | None = None,
    ) -> str:
        """生成供 Streamlit 预览的稳定 Markdown；客户预览默认不显示引用编号。"""
        strategy_names = [item.strip() for item in (strategies or []) if item.strip()]
        if len(strategy_names) > 1:
            return self._multi_strategy_markdown(strategy_names, include_citations=include_citations)
        lines: list[str] = []
        has_detail_claims = any(
            section.claims
            for section in self.sections
            if section.key not in {"performance", "internal_business", "follow_up", "other_information"}
        )
        if not has_detail_claims and self.brief_claims:
            lines.append("## 产品核心信息")
            for claim in self.brief_claims:
                refs = _format_source_ids(claim.source_ids) if include_citations else ""
                lines.append(f"- {claim.text}{refs}")
        for section in self.sections:
            if section.key in {"internal_business", "follow_up", "other_information"}:
                continue
            if section.key == "performance" and self.performance:
                lines.append(f"## {section.title}")
                for fact in self.performance:
                    refs = _format_source_ids(fact.source_ids) if include_citations else ""
                    lines.append(f"- **{fact.label}**：{fact.value}{refs}")
                continue
            if not section.claims:
                continue
            lines.append(f"## {section.title}")
            for claim in section.claims:
                refs = _format_source_ids(claim.source_ids) if include_citations else ""
                lines.append(f"- {claim.text}{refs}")
        return "\n\n".join(lines)

    def _multi_strategy_markdown(
        self,
        strategies: list[str],
        *,
        include_citations: bool,
    ) -> str:
        """多策略预览与导出保持同一阅读顺序。"""
        lines: list[str] = []
        sections = [
            item
            for item in self.sections
            if item.key not in {"internal_business", "follow_up", "other_information"}
        ]
        common_found = False
        for section in sections:
            claims = _claims_for_markdown_group(section.claims, "共同信息", strategies, include_unmarked=True)
            if not claims:
                continue
            if not common_found:
                lines.append("## 公司与共同信息")
                common_found = True
            lines.append(f"### {_clean_markdown_section_title(section.title)}")
            for claim in claims:
                refs = _format_source_ids(claim.source_ids) if include_citations else ""
                lines.append(f"- {claim.text}{refs}")

        for strategy in strategies:
            lines.append(f"## {strategy}")
            for section in sections:
                claims = _claims_for_markdown_group(section.claims, strategy, strategies)
                if not claims:
                    continue
                lines.append(f"### {_clean_markdown_section_title(section.title)}")
                for claim in claims:
                    refs = _format_source_ids(claim.source_ids) if include_citations else ""
                    lines.append(f"- {claim.text}{refs}")
            facts = _facts_for_markdown_group(self.performance, strategy, strategies)
            if facts:
                lines.append("### 代表产品关键指标")
                for fact in facts:
                    refs = _format_source_ids(fact.source_ids) if include_citations else ""
                    lines.append(f"- **{fact.label}**：{fact.value}{refs}")
        return "\n\n".join(lines)


def _format_source_ids(source_ids: list[str]) -> str:
    return f" `[{', '.join(source_ids)}]`" if source_ids else ""


def _split_markdown_group(text: str, strategies: list[str]) -> tuple[str | None, str]:
    value = re.sub(r"\s+", " ", str(text)).strip()
    for group in ["共同信息", *strategies]:
        match = re.match(rf"^{re.escape(group)}[：:]\s*(.*)$", value)
        if match:
            return group, match.group(1).strip()
    return None, value


def _claims_for_markdown_group(
    claims: list[ResearchClaim],
    target: str,
    strategies: list[str],
    *,
    include_unmarked: bool = False,
) -> list[ResearchClaim]:
    results: list[ResearchClaim] = []
    for claim in claims:
        group, text = _split_markdown_group(claim.text, strategies)
        if group == target or (include_unmarked and group is None):
            results.append(ResearchClaim(text, claim.citations))
    return results


def _facts_for_markdown_group(
    facts: list[ResearchFact],
    target: str,
    strategies: list[str],
) -> list[ResearchFact]:
    results: list[ResearchFact] = []
    for fact in facts:
        group, value = _split_markdown_group(fact.value, strategies)
        if group == target:
            results.append(ResearchFact(fact.label, value, fact.citations))
    return results


def _clean_markdown_section_title(title: str) -> str:
    return re.sub(r"^[一二三四五六七八九十]+、", "", title).strip()
