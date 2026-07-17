"""页面一：文件上传和解析。"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import streamlit as st

from ai.company_extract import extract_company
from ai.module_extract import build_modules
from ai.strategy_extract import extract_strategies
from config.config import MAX_UPLOAD_MB, SUPPORTED_EXTENSIONS, UPLOAD_DIR
from database.database import save_modules
from file_parser import assign_image_ids, assign_source_ids, extract_source_images, parse_files
from ui import go_to, render_header


def render() -> None:
    """渲染材料上传、保存与解析页面。"""
    render_header(1)
    st.subheader("上传私募材料")
    st.caption("无需填写公司或策略，系统将从文件名和材料正文中自动识别。")
    uploaded_files = st.file_uploader(
        "拖拽文件到此处，或点击选择文件",
        type=[item.lstrip(".") for item in sorted(SUPPORTED_EXTENSIONS)],
        accept_multiple_files=True,
        help=f"支持 Word、PPT、Excel、PDF、TXT、ZIP；单文件建议不超过 {MAX_UPLOAD_MB}MB。",
    )
    if uploaded_files:
        st.markdown("#### 待处理文件")
        for item in uploaded_files:
            st.write(f"✓ {item.name}　`{item.size / 1024:.1f} KB`")
        if st.button("解析材料并进入第二步", type="primary", use_container_width=True):
            _process_uploads(uploaded_files)
    elif st.session_state.get("chunks"):
        st.success(f"已解析 {len(st.session_state.chunks)} 个内容片段。")
        if st.button("查看识别结果", type="primary", use_container_width=True):
            go_to("analysis")


def _process_uploads(uploaded_files) -> None:
    """保存上传文件、解析内容并执行识别。"""
    too_large = [item.name for item in uploaded_files if item.size > MAX_UPLOAD_MB * 1024 * 1024]
    if too_large:
        st.error(f"文件超过 {MAX_UPLOAD_MB}MB：{'、'.join(too_large)}")
        return
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    progress = st.progress(0, text="正在保存材料…")
    for index, uploaded in enumerate(uploaded_files, start=1):
        data = uploaded.getvalue()
        name = _safe_upload_name(uploaded.name)
        digest = hashlib.sha256(data).hexdigest()[:8]
        path = UPLOAD_DIR / f"{digest}_{name}"
        path.write_bytes(data)
        paths.append(path)
        progress.progress(index / (len(uploaded_files) + 1), text=f"已保存：{uploaded.name}")
    progress.progress(0.82, text="正在提取文字、原始图表并识别公司、策略…")
    chunks, errors = parse_files(paths)
    source_images, image_errors = extract_source_images(paths)
    errors.extend(image_errors)
    if not chunks:
        progress.empty()
        st.error("未提取到有效文字。扫描版 PDF 请先进行 OCR，或检查文件是否损坏。")
        for error in errors:
            st.warning(error)
        return
    source_names = {path.name: uploaded.name for path, uploaded in zip(paths, uploaded_files)}
    for chunk in chunks:
        for saved_name, original_name in source_names.items():
            if chunk.source_file == saved_name or chunk.source_file.startswith(f"{saved_name} /"):
                chunk.source_file = original_name + chunk.source_file[len(saved_name) :]
                break
    for item in source_images:
        for saved_name, original_name in source_names.items():
            if item.source_file == saved_name or item.source_file.startswith(f"{saved_name} /"):
                item.source_file = original_name + item.source_file[len(saved_name) :]
                break
    source_images = assign_image_ids(source_images)
    chunks = assign_source_ids(chunks)
    company = extract_company(chunks)
    strategies = extract_strategies(chunks)
    modules = build_modules(chunks)
    st.session_state.chunks = [chunk.to_dict() for chunk in chunks]
    st.session_state.source_images = [item.to_dict() for item in source_images]
    st.session_state.company = company.__dict__
    st.session_state.strategies = strategies
    st.session_state.modules = [module.to_dict() for module in modules]
    st.session_state.uploaded_names = [item.name for item in uploaded_files]
    st.session_state.parse_errors = errors
    st.session_state.generated = {}
    st.session_state.generated_results = {}
    st.session_state.selected_strategies = strategies[:1]
    st.session_state.pop("active_strategy", None)
    save_modules(company.name, strategies, modules)
    progress.progress(1.0, text="解析完成，正在进入审核页…")
    go_to("analysis")


def _safe_upload_name(name: str) -> str:
    """移除上传文件名中的路径和不安全字符。"""
    base_name = Path(name).name
    return re.sub(r"[^\w\-.（）()\u4e00-\u9fff]", "_", base_name)
