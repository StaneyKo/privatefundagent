"""私募公司名称自动识别。"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from models import SourceChunk


@dataclass
class CompanyResult:
    """公司识别结果。"""

    name: str
    confidence: int
    evidence: str
    source_file: str


LEGAL_COMPANY_PATTERN = re.compile(
    r"([\u4e00-\u9fffA-Za-z0-9（）()·]{2,30}?"
    r"(?:私募基金管理|基金管理|资产管理|投资管理|投资咨询|投资|资本)"
    r"(?:股份有限公司|有限公司|有限合伙))"
    r"(?=[\s，。,:：；;、/）)]|$)"
)
SHORT_PATTERN = re.compile(r"([\u4e00-\u9fff]{2,10}(?:投资|资本|资产|基金))")
NOISE_WORDS = {
    "公司投资",
    "策略投资",
    "组合投资",
    "基金投资",
    "证券投资",
    "投资管理",
    "资产管理",
    "基金管理",
    "长期投资",
    "价值投资",
}
LEADING_CUES = re.compile(r"^(?:资料来源|数据来源|公司名称|管理人名称|基金管理人|管理人|公司)[：:\s]*")
DOCUMENT_SUFFIX = re.compile(r"(?:年度)?(?:路演|介绍|材料|报告|产品资料)$")
LEGAL_SUFFIX = re.compile(r"(?:股份有限公司|有限公司|有限合伙)$")
BUSINESS_SUFFIX = re.compile(r"(?:私募基金管理|基金管理|资产管理|投资管理|投资咨询|投资|资本)$")
REGION_PREFIX = re.compile(
    r"^(?:北京|上海|深圳|广州|杭州|南京|苏州|天津|重庆|成都|武汉|宁波|厦门|珠海|青岛|西安|长沙|合肥|福州|济南)"
)


def normalize_company_name(name: str) -> str:
    """清理公司名称前后的文档噪声，同时完整保留法定名称。"""
    name = LEADING_CUES.sub("", name.strip())
    name = re.sub(r"^[\d\s_\-—年月日版]+", "", name)
    name = DOCUMENT_SUFFIX.sub("", name)
    return name.strip(" _-—：:（）()")


def company_core_name(name: str) -> str:
    """提取用于合并全称和简称的品牌核心名称。"""
    core = LEGAL_SUFFIX.sub("", name)
    core = BUSINESS_SUFFIX.sub("", core)
    core = REGION_PREFIX.sub("", core)
    return core.strip() or name


def extract_company(chunks: list[SourceChunk]) -> CompanyResult:
    """优先识别法定全称，并通过简称、来源数量和竞争候选校准可信度。"""
    legal_scores: Counter[str] = Counter()
    legal_sources: dict[str, set[tuple[str, str | None]]] = defaultdict(set)
    evidence_map: dict[str, tuple[str, str]] = {}
    cue_evidence: set[str] = set()
    filename_texts: list[str] = []

    for chunk in chunks:
        filename = re.sub(r"\.[^.]+$", "", chunk.source_file.split("/")[-1]).strip()
        filename_texts.append(filename)
        _add_legal_candidates(filename, chunk, 18, legal_scores, legal_sources, evidence_map, cue_evidence)

        for match in LEGAL_COMPANY_PATTERN.finditer(chunk.text):
            name = normalize_company_name(match.group(1))
            if not _is_valid_company(name):
                continue
            context = chunk.text[max(0, match.start() - 12) : match.end()]
            has_cue = any(cue in context for cue in ("资料来源", "数据来源", "公司名称", "管理人名称"))
            weight = 10 if has_cue else 6
            legal_scores[name] += weight
            legal_sources[name].add((chunk.source_file, chunk.source_page))
            evidence_map.setdefault(name, (match.group(1), chunk.source_file))
            if has_cue:
                cue_evidence.add(name)

    if legal_scores:
        return _select_legal_company(legal_scores, legal_sources, evidence_map, cue_evidence, filename_texts)
    return _select_short_company(chunks)


def _add_legal_candidates(
    text: str,
    chunk: SourceChunk,
    weight: int,
    scores: Counter[str],
    sources: dict[str, set[tuple[str, str | None]]],
    evidence_map: dict[str, tuple[str, str]],
    cue_evidence: set[str],
) -> None:
    """将文本中的法定公司名称加入候选池。"""
    for match in LEGAL_COMPANY_PATTERN.finditer(text):
        name = normalize_company_name(match.group(1))
        if not _is_valid_company(name):
            continue
        scores[name] += weight
        sources[name].add((chunk.source_file, chunk.source_page))
        evidence_map.setdefault(name, (match.group(1), chunk.source_file))
        if any(cue in text[max(0, match.start() - 12) : match.end()] for cue in ("资料来源", "数据来源", "公司名称", "管理人名称")):
            cue_evidence.add(name)


def _select_legal_company(
    scores: Counter[str],
    sources: dict[str, set[tuple[str, str | None]]],
    evidence_map: dict[str, tuple[str, str]],
    cue_evidence: set[str],
    filenames: list[str],
) -> CompanyResult:
    """选择法定全称，并按证据质量而非全部候选总量计算可信度。"""
    ranked = scores.most_common()
    name, top_score = ranked[0]
    core = company_core_name(name)
    source_count = len(sources[name])
    filename_support = sum(core in filename for filename in set(filenames) if len(core) >= 2)
    strong_competitors = sum(1 for _, score in ranked[1:] if score >= top_score * 0.6)

    confidence = 82
    confidence += min(8, max(0, source_count - 1) * 2)
    confidence += 5 if filename_support else 0
    confidence += 3 if name in cue_evidence else 0
    if len(ranked) == 1 or top_score >= ranked[1][1] * 1.8:
        confidence += 2
    confidence -= min(15, strong_competitors * 5)
    confidence = max(65, min(99, confidence))

    evidence, source_file = evidence_map[name]
    return CompanyResult(name, confidence, evidence, source_file)


def _select_short_company(chunks: list[SourceChunk]) -> CompanyResult:
    """没有法定全称时，使用文件名和正文中的简称进行保守识别。"""
    scores: Counter[str] = Counter()
    evidence_map: dict[str, tuple[str, str]] = {}
    for chunk in chunks:
        filename = re.sub(r"\.[^.]+$", "", chunk.source_file.split("/")[-1])
        for match in SHORT_PATTERN.findall(filename):
            name = normalize_company_name(match)
            if _is_valid_company(name):
                scores[name] += 6
                evidence_map.setdefault(name, (filename, chunk.source_file))
        for match in SHORT_PATTERN.findall(chunk.text[:5000]):
            name = normalize_company_name(match)
            if _is_valid_company(name):
                scores[name] += 1
                evidence_map.setdefault(name, (match, chunk.source_file))
    if not scores:
        return CompanyResult("未识别", 20, "上传材料中未发现明确公司名称", "资料汇总")
    name, score = scores.most_common(1)[0]
    confidence = min(79, 58 + min(21, score))
    evidence, source_file = evidence_map[name]
    return CompanyResult(name, confidence, evidence, source_file)


def _is_valid_company(name: str) -> bool:
    """过滤通用投资术语和长度异常候选。"""
    return 4 <= len(name) <= 40 and name not in NOISE_WORDS
