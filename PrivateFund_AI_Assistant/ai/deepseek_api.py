"""DeepSeek OpenAI 兼容接口客户端与确定性本地缓存。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import httpx

from ai.citation_verifier import verify_research_payload
from ai.prompt_template import PROMPT_VERSION, build_research_prompt
from ai.source_detail_enricher import enrich_research_from_sources
from config.config import (
    CACHE_DIR,
    CONTENT_TEMPLATE_PATH,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    MAX_CONTEXT_CHARS,
    STYLE_TEMPLATE_PATH,
)
from models import GeneratedResearch, SourceChunk


MODEL_MAP: dict[str, tuple[str, str | None]] = {
    "DeepSeek-V4-Flash（推荐）": ("deepseek-v4-flash", "disabled"),
    "DeepSeek-V4-Pro（深度研究）": ("deepseek-v4-pro", "enabled"),
    "DeepSeek-V3（兼容模式）": ("deepseek-chat", None),
    "DeepSeek-R1（兼容模式）": ("deepseek-reasoner", None),
}


class DeepSeekClient:
    """封装连接测试、结构化生成、原文校验和固定版本缓存。"""

    def __init__(self, api_key: str, base_url: str = DEEPSEEK_BASE_URL, model: str = DEEPSEEK_MODEL) -> None:
        if not api_key.strip():
            raise ValueError("请先填写 DeepSeek API Key")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        mapped = MODEL_MAP.get(model)
        self.model = mapped[0] if mapped else model
        self.thinking = mapped[1] if mapped else None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def test_connection(self, timeout: float = 20.0) -> tuple[bool, str]:
        """使用最小请求测试接口连接。"""
        try:
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": [{"role": "user", "content": "请仅回复：连接成功"}],
                "max_tokens": 16,
            }
            if self.thinking:
                payload["thinking"] = {"type": self.thinking}
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return True, response.json()["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            return False, f"连接失败：{exc}"

    def generate(
        self,
        company: str,
        strategy: str,
        chunks: list[SourceChunk],
        timeout: float = 180.0,
        force_refresh: bool = False,
    ) -> GeneratedResearch:
        """同一输入默认复用同一缓存版本，并只返回通过原文核验的事实。"""
        ordered_chunks = _canonical_chunks(chunks)
        cache_key = generation_fingerprint(company, strategy, ordered_chunks, self.model, self.base_url)
        cache_path = CACHE_DIR / f"{cache_key}.json"
        if not force_refresh:
            cached = _read_cache(cache_path)
            if cached is not None:
                cached.cache_key = cache_key
                cached.from_cache = True
                return cached

        materials = format_materials(ordered_chunks, MAX_CONTEXT_CHARS)
        prompt = build_research_prompt(company, strategy, materials)
        request_payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 9000,
        }
        if self.thinking:
            request_payload["thinking"] = {"type": self.thinking}
        if self.thinking != "enabled":
            request_payload["temperature"] = 0
            request_payload["top_p"] = 1
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=request_payload,
            timeout=timeout,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"].strip()
        structured = parse_json_response(raw)
        research = verify_research_payload(structured, ordered_chunks)
        research = enrich_research_from_sources(research, ordered_chunks, strategy)
        research.raw = raw
        research.cache_key = cache_key
        research.from_cache = False
        _write_cache(cache_path, research)
        return research


def format_materials(chunks: list[SourceChunk], max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """按稳定编号格式化原始片段，并限制提交给模型的总长度。"""
    parts: list[str] = []
    used = 0
    for chunk in _canonical_chunks(chunks):
        header = (
            f"\n[{chunk.source_id} | 文件：{chunk.source_file} | "
            f"位置：{chunk.source_page or '未标注'} | 类型：{chunk.file_type or '未知'}]\n"
        )
        remaining = max_chars - used - len(header)
        if remaining <= 0:
            break
        body = chunk.text[:remaining]
        parts.append(header + body)
        used += len(header) + len(body)
    return "".join(parts)


def generation_fingerprint(
    company: str,
    strategy: str,
    chunks: list[SourceChunk],
    model: str,
    base_url: str,
) -> str:
    """计算包含提示词与模板版本的稳定生成指纹。"""
    payload = {
        "prompt_version": PROMPT_VERSION,
        "company": company.strip(),
        "strategy": strategy.strip(),
        "model": model,
        "base_url": base_url.rstrip("/"),
        "content_template_sha256": _file_sha256(CONTENT_TEMPLATE_PATH),
        "style_template_sha256": _file_sha256(STYLE_TEMPLATE_PATH),
        "chunks": [
            {
                "source_id": item.source_id,
                "source_file": item.source_file,
                "source_page": item.source_page,
                "file_type": item.file_type,
                "text": item.text,
            }
            for item in _canonical_chunks(chunks)
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_json_response(raw: str) -> dict[str, Any]:
    """兼容纯 JSON 与模型偶发的代码围栏包装。"""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型未返回可识别的 JSON 结果")
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"模型 JSON 格式无效：{exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("模型输出必须是 JSON 对象")
    return parsed


def _canonical_chunks(chunks: list[SourceChunk]) -> list[SourceChunk]:
    ordered = sorted(
        chunks,
        key=lambda item: (
            item.source_file.casefold(),
            (item.source_page or "").casefold(),
            item.file_type.casefold(),
            item.text,
        ),
    )
    for index, chunk in enumerate(ordered, start=1):
        chunk.source_id = f"S{index:04d}"
    return ordered


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"


def _read_cache(path: Path) -> GeneratedResearch | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return GeneratedResearch.from_dict(data) if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _write_cache(path: Path, research: GeneratedResearch) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(research.to_dict(), ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
