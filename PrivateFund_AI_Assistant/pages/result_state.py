"""多策略生成结果的 Streamlit 会话状态兼容层。"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


def get_generated_results(state: MutableMapping[str, Any]) -> dict[str, dict[str, Any]]:
    """读取多策略结果，并兼容旧版单个 generated 结构。"""
    results = state.get("generated_results")
    if isinstance(results, dict) and results:
        return {str(key): value for key, value in results.items() if isinstance(value, dict)}
    generated = state.get("generated")
    if isinstance(generated, dict) and generated.get("strategy"):
        return {str(generated["strategy"]): generated}
    return {}


def store_generated_results(
    state: MutableMapping[str, Any],
    results: dict[str, dict[str, Any]],
    active_strategy: str | None = None,
) -> None:
    """保存多策略结果，同时维护旧版 generated 活动结果。"""
    state["generated_results"] = results
    if not results:
        state["generated"] = {}
        state.pop("active_strategy", None)
        return
    strategy = active_strategy if active_strategy in results else next(iter(results))
    state["active_strategy"] = strategy
    state["generated"] = results[strategy]


def set_active_strategy(state: MutableMapping[str, Any], strategy: str) -> dict[str, Any]:
    """切换当前查看的策略，并返回对应结果。"""
    results = get_generated_results(state)
    if strategy not in results:
        raise KeyError(f"未找到策略结果：{strategy}")
    state["active_strategy"] = strategy
    state["generated"] = results[strategy]
    return results[strategy]
