"""TXT 文件生成器。"""

from __future__ import annotations

from pathlib import Path
import re
from difflib import SequenceMatcher

from ai.research_grouping import (
    ensure_sentence,
    near_duplicate,
    split_grouped_text,
    split_strategy_names,
    strip_strategy_subject,
)
from config.config import OUTPUT_DIR


def generate_txt(company: str, strategy: str, content: str, output_dir: Path = OUTPUT_DIR) -> tuple[bytes, Path]:
    """按简版范例生成一段式、文件名稳定的 UTF-8 BOM 文本。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_company = _safe_filename(company)
    path = output_dir / f"{safe_company}_{_safe_filename(strategy)}_简单介绍.txt"
    full_content = compose_natural_brief(content, _split_strategies(strategy)) + "\n"
    data = full_content.encode("utf-8-sig")
    path.write_bytes(data)
    return data, path


def compose_natural_brief(content: str, strategies: list[str] | None = None) -> str:
    """共同信息在前；多策略以一次性小标题分组，不重复策略名称。"""
    text = re.sub(r"[\t\r ]+", " ", content).strip()
    if not text:
        return "资料未披露。"
    strategy_names = [item.strip() for item in (strategies or []) if item.strip()]
    sentences = _split_sentences(text)
    common: list[str] = []
    grouped: dict[str, list[str]] = {name: [] for name in strategy_names}
    active_group: str | None = None
    for sentence in sentences:
        group, body = split_grouped_text(sentence, strategy_names)
        if group is not None:
            active_group = group
        target_group = group or active_group
        if target_group in grouped:
            body = strip_strategy_subject(body, target_group)
            _append_unique(grouped[target_group], body, strategy_names)
        else:
            _append_unique(common, body, strategy_names)

    if len(strategy_names) <= 1:
        single = strategy_names[0] if strategy_names else None
        values = list(common)
        if single:
            values.extend(grouped[single])
        return _clean_output("".join(ensure_sentence(item) for item in values) or "资料未披露。")

    _promote_cross_strategy_duplicates(common, grouped, strategy_names)
    common = _prune_repeated_clauses(common, [], strategy_names)
    for strategy in strategy_names:
        grouped[strategy] = _prune_repeated_clauses(grouped[strategy], common, strategy_names)
    blocks: list[str] = []
    common_text = "".join(ensure_sentence(item) for item in common)
    if common_text:
        blocks.append(common_text)
    for strategy in strategy_names:
        body = "".join(ensure_sentence(item) for item in grouped[strategy])
        if body:
            blocks.append(f"【{strategy}】\n{body}")
    return _clean_output("\n\n".join(blocks) or "资料未披露。")


def _split_sentences(text: str) -> list[str]:
    """同时识别内部标记和已经生成过的小标题，使整理过程可重复执行。"""
    heading_pattern = r"【([^】]+)】\s*"
    text = re.sub(heading_pattern, lambda match: f"\n{match.group(1)}：", text)
    return [item.strip() for item in re.split(r"(?<=[。！？；;])|\n+", text) if item.strip()]


def _append_unique(values: list[str], value: str, strategies: list[str]) -> None:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned or any(near_duplicate(cleaned, item, strategies) for item in values):
        return
    values.append(cleaned)


def _promote_cross_strategy_duplicates(
    common: list[str],
    grouped: dict[str, list[str]],
    strategies: list[str],
) -> None:
    """防御性处理：同一句若误落入多个策略，只在共同信息中保留一次。"""
    for index, strategy in enumerate(strategies):
        for value in list(grouped[strategy]):
            duplicate_groups = [
                other
                for other in strategies[index + 1 :]
                if any(near_duplicate(value, item, strategies) for item in grouped[other])
            ]
            if not duplicate_groups:
                continue
            _append_unique(common, value, strategies)
            grouped[strategy] = [item for item in grouped[strategy] if not near_duplicate(value, item, strategies)]
            for other in duplicate_groups:
                grouped[other] = [item for item in grouped[other] if not near_duplicate(value, item, strategies)]


def _prune_repeated_clauses(
    values: list[str],
    references: list[str],
    strategies: list[str],
) -> list[str]:
    """按逗号级事实片段去重，保留长句中尚未出现的策略独有信息。"""
    results: list[str] = []
    reference_windows = _clause_windows(references)
    for value in values:
        clauses = _split_clauses(value)
        kept: list[str] = []
        for clause in clauses:
            founder = re.match(r"^(?:公司)?核心人物为创始人([^，。；]+)$", clause)
            if founder and _merge_founder_fact(results, founder.group(1).strip()):
                continue
            if any(_clause_is_covered(clause, window, strategies) for window in reference_windows):
                continue
            kept.append(clause)
        if not kept:
            continue
        kept[0] = re.sub(r"^(其中|同时)[，,]?\s*", "", kept[0]).strip()
        rebuilt = "，".join(item for item in kept if item).strip()
        if not rebuilt:
            continue
        if any(near_duplicate(rebuilt, item, strategies) for item in results):
            continue
        results.append(rebuilt)
        reference_windows.extend(_clause_windows([rebuilt]))
    return results


def _merge_founder_fact(values: list[str], name: str) -> bool:
    """同一人物已介绍时，把“创始人”并入原句，避免再次整段介绍。"""
    for index in range(len(values) - 1, -1, -1):
        if name not in values[index]:
            continue
        if "公司创始人" not in values[index]:
            values[index] = re.sub(r"[。！？]+$", "", values[index]) + "，并为公司创始人"
        return True
    return False


def _split_clauses(text: str) -> list[str]:
    value = re.sub(r"[。！？；;]+$", "", str(text).strip())
    return [item.strip() for item in re.split(r"[，,；;]+", value) if item.strip()]


def _clause_windows(values: list[str]) -> list[str]:
    """相邻片段也作为参照，可识别有无逗号差异的同一事实。"""
    windows: list[str] = []
    for value in values:
        clauses = _split_clauses(value)
        for start in range(len(clauses)):
            for size in range(1, min(3, len(clauses) - start) + 1):
                windows.append("".join(clauses[start : start + size]))
    return windows


def _clause_is_covered(candidate: str, reference: str, strategies: list[str]) -> bool:
    first = _normalize_clause(candidate, strategies)
    second = _normalize_clause(reference, strategies)
    if not first or not second:
        return False
    first_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", first))
    second_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", second))
    if first_numbers - second_numbers:
        return False
    if first == second:
        return True
    shorter, longer = sorted((first, second), key=len)
    if len(shorter) >= 6 and shorter in longer:
        return True
    return min(len(first), len(second)) >= 8 and SequenceMatcher(None, first, second).ratio() >= 0.86


def _normalize_clause(text: str, strategies: list[str]) -> str:
    value = re.sub(r"[\s，。；：、,.!?！？:;（）()\[\]【】\-—]", "", str(text)).lower()
    for noise in ("本公司", "该公司", "公司", "相关", "方面", "策略", "规模", "其中", "同时"):
        value = value.replace(noise, "")
    value = value.replace("投资团队", "投研团队")
    return value


def _clean_output(text: str) -> str:
    result = re.sub(r"[ \t]*([，。；：！？])[ \t]*", r"\1", text)
    result = re.sub(r" *\n *", "\n", result)
    return result.strip()


def _split_strategies(strategy: str) -> list[str]:
    return split_strategy_names(strategy)


def _safe_filename(value: str) -> str:
    """替换 Windows 不允许的文件名字符。"""
    return "".join("_" if char in '<>:"/\\|?*' else char for char in value).strip() or "未命名"
