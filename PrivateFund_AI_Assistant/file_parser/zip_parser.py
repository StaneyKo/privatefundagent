"""ZIP 压缩包安全解压与递归解析。"""

from __future__ import annotations

import tempfile
import zipfile
import shutil
from pathlib import Path, PurePosixPath
from typing import Callable

from models import SourceChunk


def parse_zip(file_path: Path, parse_callback: Callable[[Path], list[SourceChunk]]) -> list[SourceChunk]:
    """安全解压 ZIP，并解析其中受支持的文件。"""
    chunks: list[SourceChunk] = []
    with tempfile.TemporaryDirectory(prefix="private_fund_zip_") as temp_dir:
        target = Path(temp_dir)
        with zipfile.ZipFile(file_path) as archive:
            for member in archive.infolist():
                decoded_name = decode_zip_member_name(member.filename)
                relative_path = PurePosixPath(decoded_name.replace("\\", "/"))
                if relative_path.is_absolute() or ".." in relative_path.parts:
                    raise ValueError(f"压缩包包含不安全路径：{decoded_name}")
                member_path = (target / Path(*relative_path.parts)).resolve()
                if target.resolve() not in member_path.parents and member_path != target.resolve():
                    raise ValueError(f"压缩包包含不安全路径：{decoded_name}")
                if member.is_dir():
                    member_path.mkdir(parents=True, exist_ok=True)
                    continue
                member_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, member_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        for nested_file in sorted(target.rglob("*")):
            if not nested_file.is_file():
                continue
            try:
                nested_chunks = parse_callback(nested_file)
            except (ValueError, OSError, zipfile.BadZipFile):
                continue
            for chunk in nested_chunks:
                chunk.source_file = f"{file_path.name} / {nested_file.relative_to(target).as_posix()}"
            chunks.extend(nested_chunks)
    return chunks


def decode_zip_member_name(name: str) -> str:
    """修复 Windows ZIP 中未标记编码的 GBK 中文文件名。"""
    if not name or all(ord(char) < 128 for char in name):
        return name
    try:
        candidate = name.encode("cp437").decode("gb18030")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name
    original_score = _chinese_readability_score(name)
    candidate_score = _chinese_readability_score(candidate)
    return candidate if candidate_score > original_score else name


def _chinese_readability_score(value: str) -> int:
    """计算中文可读性分数，避免误改正常的 UTF-8 文件名。"""
    chinese_count = sum("\u4e00" <= char <= "\u9fff" or char in "【】（）《》" for char in value)
    mojibake_count = sum(char in "╛┐║¡╡┬╣╔╞▒░µ┴╗»▓▀╘╚½░╜Γ╬÷" for char in value)
    return chinese_count * 3 - mojibake_count * 2
