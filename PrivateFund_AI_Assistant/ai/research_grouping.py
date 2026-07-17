"""多策略研究结果的分组标记与文本去重工具。"""

from __future__ import annotations

import re
from difflib import SequenceMatcher


COMMON_GROUP = "共同信息"


def split_strategy_names(value: str) -> list[str]:
    """按界面使用的连接符拆分策略名称，并保持原顺序。"""
    return [item.strip() for item in re.split(r"[、,，;/；]+", value) if item.strip()]


def split_grouped_text(text: str, strategies: list[str]) -> tuple[str | None, str]:
    """拆出内部的“共同信息/策略：正文”标记；普通冒号不会被误判。"""
    value = re.sub(r"\s+", " ", str(text)).strip()
    for group in [COMMON_GROUP, *strategies]:
        match = re.match(rf"^{re.escape(group)}[：:]\s*(.*)$", value)
        if match:
            return group, match.group(1).strip()
    return None, value


def strip_strategy_subject(text: str, strategy: str) -> str:
    """小标题已经给出策略名时，移除正文开头重复的策略主语。"""
    value = re.sub(r"\s+", " ", str(text)).strip()
    pattern = rf"^{re.escape(strategy)}(?:策略)?(?:方面|概况|介绍)?[：:,，]?\s*"
    stripped = re.sub(pattern, "", value, count=1).strip()
    return stripped or value


def mark_group(text: str, group: str, strategies: list[str]) -> str:
    """以稳定内部标记保存分组，同时避免正文再次写策略名称。"""
    _, body = split_grouped_text(text, strategies)
    if group != COMMON_GROUP:
        body = strip_strategy_subject(body, group)
    return f"{group}：{body}"


def normalize_for_match(text: str, strategies: list[str] | None = None) -> str:
    """生成只用于去重的稳定文本，不改动对外文字。"""
    _, body = split_grouped_text(text, strategies or [])
    for strategy in strategies or []:
        body = strip_strategy_subject(body, strategy)
    body = re.sub(r"[\s，。；：、,.!?！？:;（）()\[\]【】\-—]", "", body)
    return body.lower()


def near_duplicate(left: str, right: str, strategies: list[str] | None = None) -> bool:
    """判断两条原文事实是否为完全或高度近似重复。"""
    first = normalize_for_match(left, strategies)
    second = normalize_for_match(right, strategies)
    if not first or not second:
        return False
    if first == second:
        return True
    shorter, longer = sorted((first, second), key=len)
    if len(shorter) >= 12 and shorter in longer and len(shorter) / len(longer) >= 0.84:
        return True
    return min(len(first), len(second)) >= 10 and SequenceMatcher(None, first, second).ratio() >= 0.90


def ensure_sentence(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text)).strip()
    if not value:
        return ""
    return value if value.endswith(("。", "！", "？", "；", ";")) else value + "。"
