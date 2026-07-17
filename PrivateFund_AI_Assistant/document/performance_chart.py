"""从上传材料的原始表格文本中提取时间序列并绘制代表产品表现图。"""

from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from models import GeneratedResearch, SourceChunk, SourceImage


DATE_PATTERNS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y年%m月%d日",
)
DATE_RE = re.compile(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?")
NUMBER_RE = re.compile(r"^\(?\s*[-+]?\d[\d,]*(?:\.\d+)?\s*%?\s*\)?$")
EXCLUDED_HEADERS = ("序号", "编号", "规模", "金额", "份额", "持仓数量", "成交额")
SERIES_HINTS = ("净值", "超额", "基准", "指数", "产品", "累计收益")
COLORS = ("#1F3864", "#D4A72C", "#C15C3B")


def build_performance_chart(
    chunks: list[SourceChunk],
    strategy: str,
    research: GeneratedResearch,
) -> dict[str, Any] | None:
    """选择与关注策略最相关且不少于 8 个观测点的时间序列。"""
    product_name = _representative_product(research)
    candidates: list[dict[str, Any]] = []
    for chunk in chunks:
        candidate = _extract_candidate(chunk, strategy, product_name)
        if candidate:
            candidates.append(candidate)
    if not candidates:
        return None
    selected = max(candidates, key=lambda item: (item["score"], item["point_count"], item["source_id"]))
    selected["product_name"] = product_name
    selected["title"] = "代表产品表现"
    selected["visual_type"] = "generated_chart"
    selected["image_data"] = render_chart_png(selected)
    return selected


def build_performance_visual(
    images: list[SourceImage],
    chunks: list[SourceChunk],
    strategy: str,
    research: GeneratedResearch,
) -> dict[str, Any] | None:
    """优先选择原材料中的业绩图片，找不到时再按原始时间序列绘图。"""
    product_name = _representative_product(research)
    candidates: list[dict[str, Any]] = []
    for item in images:
        context = "\n".join((item.source_file, item.source_page or "", item.context_text))
        score = _source_image_score(item, context, strategy, product_name)
        if score < 24:
            continue
        candidates.append(
            {
                "visual_type": "source_image",
                "image_id": item.image_id,
                "image_data": item.image_data,
                "source_file": item.source_file,
                "source_page": item.source_page or "未标注位置",
                "context_text": item.context_text,
                "width": item.width,
                "height": item.height,
                "product_name": product_name,
                "title": "代表产品表现",
                "score": score,
            }
        )
    if candidates:
        return max(
            candidates,
            key=lambda item: (
                item["score"],
                int(item.get("width", 0)) * int(item.get("height", 0)),
                item.get("image_id", ""),
            ),
        )
    return build_performance_chart(chunks, strategy, research)


def render_chart_png(chart: dict[str, Any]) -> bytes:
    """用 Pillow 绘制报告内嵌静态折线图，避免依赖外部服务。"""
    width, height = 1600, 720
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    font_regular = _load_font(28)
    font_small = _load_font(22)
    font_title = _load_font(36, bold=True)
    font_legend = _load_font(24)

    left, right, top, bottom = 125, 70, 150, 105
    plot_left, plot_top = left, top
    plot_right, plot_bottom = width - right, height - bottom
    series = chart["series"]
    all_points = [point for item in series for point in item["points"]]
    dates = [datetime.fromisoformat(point[0]) for point in all_points]
    values = [float(point[1]) for point in all_points]
    min_date, max_date = min(dates), max(dates)
    min_value, max_value = min(values), max(values)
    if min_value == max_value:
        min_value -= 1
        max_value += 1
    padding = (max_value - min_value) * 0.08
    y_min, y_max = min_value - padding, max_value + padding
    date_span = max((max_date - min_date).days, 1)

    def x_coord(value: datetime) -> float:
        return plot_left + ((value - min_date).days / date_span) * (plot_right - plot_left)

    def y_coord(value: float) -> float:
        return plot_bottom - ((value - y_min) / (y_max - y_min)) * (plot_bottom - plot_top)

    draw.text((left, 32), chart["title"], font=font_title, fill="#1F2937")
    product = chart.get("product_name") or "代表产品"
    subtitle = (
        f"{product}｜{min_date:%Y-%m-%d} 至 {max_date:%Y-%m-%d}｜"
        f"{chart['point_count']} 个观测点｜上传材料原始口径"
    )
    draw.text((left, 86), subtitle, font=font_small, fill="#667085")

    for tick in range(6):
        value = y_min + (y_max - y_min) * tick / 5
        y = y_coord(value)
        draw.line((plot_left, y, plot_right, y), fill="#E4E7EC", width=2)
        label = f"{value:.2f}{'%' if chart['unit'] == '%' else ''}"
        box = draw.textbbox((0, 0), label, font=font_small)
        draw.text((plot_left - 18 - (box[2] - box[0]), y - 13), label, font=font_small, fill="#667085")

    for tick in range(6):
        date = min_date + (max_date - min_date) * tick / 5
        x = x_coord(date)
        draw.line((x, plot_top, x, plot_bottom), fill="#F2F4F7", width=1)
        label = f"{date:%Y-%m}"
        box = draw.textbbox((0, 0), label, font=font_small)
        draw.text((x - (box[2] - box[0]) / 2, plot_bottom + 20), label, font=font_small, fill="#667085")

    draw.line((plot_left, plot_top, plot_left, plot_bottom), fill="#98A2B3", width=2)
    draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill="#98A2B3", width=2)

    legend_x = plot_right
    legend_items: list[tuple[str, str, int]] = []
    for index, item in enumerate(series):
        color = COLORS[index % len(COLORS)]
        points = [(x_coord(datetime.fromisoformat(date)), y_coord(float(value))) for date, value in item["points"]]
        if len(points) >= 2:
            draw.line(points, fill=color, width=5, joint="curve")
        for x, y in (points[0], points[-1]):
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill="#FFFFFF", outline=color, width=3)
        text_width = draw.textbbox((0, 0), item["name"], font=font_legend)[2]
        legend_items.append((item["name"], color, text_width))
    total_legend_width = sum(item[2] + 70 for item in legend_items)
    legend_x -= total_legend_width
    for name, color, text_width in legend_items:
        draw.line((legend_x, 124, legend_x + 34, 124), fill=color, width=5)
        draw.text((legend_x + 43, 107), name, font=font_legend, fill="#344054")
        legend_x += text_width + 70

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def chart_for_session(chart: dict[str, Any] | None) -> dict[str, Any] | None:
    """返回可直接存入 Streamlit 会话的图表结构。"""
    if chart is None:
        return None
    return {key: value for key, value in chart.items()}


def chart_for_json(chart: dict[str, Any] | None) -> dict[str, Any] | None:
    """移除二进制图片，供引用核验 JSON 下载。"""
    if chart is None:
        return None
    return {key: value for key, value in chart.items() if key != "image_data"}


def _source_image_score(item: SourceImage, context: str, strategy: str, product_name: str) -> int:
    lowered = context.casefold()
    score = sum(9 for hint in ("净值", "超额", "业绩", "收益", "回撤", "夏普", "表现", "累计") if hint in lowered)
    strategy_tokens = [token for token in re.findall(r"\d+|[A-Za-z]+|[\u4e00-\u9fff]{2,}", strategy) if len(token) >= 2]
    score += sum(7 for token in strategy_tokens if token.casefold() in lowered)
    if product_name and product_name.casefold() in lowered:
        score += 45
    ratio = item.width / max(item.height, 1)
    if 1.15 <= ratio <= 3.8:
        score += 12
    if item.width * item.height >= 600_000:
        score += 8
    if "原页截图" in (item.source_page or ""):
        score += 5
    return score


def _extract_candidate(chunk: SourceChunk, strategy: str, product_name: str) -> dict[str, Any] | None:
    lines = [line.strip() for line in chunk.text.splitlines() if line.strip()]
    rows = [[cell.strip() for cell in re.split(r"\s*\|\s*|\t+", line)] for line in lines]
    rows = [row for row in rows if len(row) >= 2]
    if len(rows) < 9:
        return None
    max_columns = min(max(len(row) for row in rows), 20)
    best: dict[str, Any] | None = None
    for date_column in range(max_columns):
        dated_rows = [(index, _parse_date(row[date_column])) for index, row in enumerate(rows) if len(row) > date_column]
        dated_rows = [(index, value) for index, value in dated_rows if value is not None]
        if len(dated_rows) < 8:
            continue
        first_data_index = dated_rows[0][0]
        header_index = _find_header_row(rows, first_data_index, date_column)
        header = rows[header_index] if header_index is not None else []
        extracted_series: list[dict[str, Any]] = []
        for value_column in range(max_columns):
            if value_column == date_column:
                continue
            label = header[value_column].strip() if value_column < len(header) else ""
            if not label or _parse_date(label) or _parse_number(label)[0] is not None:
                continue
            if any(keyword in label for keyword in EXCLUDED_HEADERS):
                continue
            points: list[list[Any]] = []
            percent_cells = 0
            for row_index, date in dated_rows:
                row = rows[row_index]
                if len(row) <= value_column:
                    continue
                number, is_percent = _parse_number(row[value_column])
                if number is None:
                    continue
                points.append([date.date().isoformat(), number])
                percent_cells += int(is_percent)
            if len(points) < 8 or len(points) < len(dated_rows) * 0.6:
                continue
            unit = "%" if percent_cells >= len(points) * 0.8 else "原始数值"
            extracted_series.append({"name": label[:12], "points": points, "unit": unit})
        if not extracted_series:
            continue
        preferred_unit = _preferred_unit(extracted_series)
        same_unit = [item for item in extracted_series if item["unit"] == preferred_unit]
        same_unit.sort(key=lambda item: (_series_score(item["name"], product_name), len(item["points"])), reverse=True)
        selected_series = same_unit[:3]
        point_count = max(len(item["points"]) for item in selected_series)
        score = point_count + sum(_series_score(item["name"], product_name) for item in selected_series)
        strategy_tokens = [token for token in re.findall(r"\d+|[A-Za-z]+|[\u4e00-\u9fff]{2,}", strategy) if len(token) >= 2]
        if any(token.lower() in chunk.text.lower() for token in strategy_tokens):
            score += 20
        if product_name and product_name in chunk.text:
            score += 30
        candidate = {
            "source_id": chunk.source_id,
            "source_file": chunk.source_file,
            "source_page": chunk.source_page or "未标注位置",
            "series": selected_series,
            "unit": preferred_unit,
            "point_count": point_count,
            "score": score,
            "chart_type": "line",
        }
        if best is None or (candidate["score"], candidate["point_count"]) > (best["score"], best["point_count"]):
            best = candidate
    return best


def _find_header_row(rows: list[list[str]], first_data_index: int, date_column: int) -> int | None:
    start = max(0, first_data_index - 5)
    for index in range(first_data_index - 1, start - 1, -1):
        row = rows[index]
        if len(row) > date_column and any(keyword in row[date_column] for keyword in ("日期", "时间", "净值日")):
            return index
    return first_data_index - 1 if first_data_index > 0 else None


def _parse_date(value: str) -> datetime | None:
    text = value.strip()
    match = DATE_RE.search(text)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    for pattern in DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _parse_number(value: str) -> tuple[float | None, bool]:
    text = value.strip().replace("，", ",")
    if not NUMBER_RE.fullmatch(text):
        return None, False
    negative_parentheses = text.startswith("(") and text.endswith(")")
    is_percent = "%" in text or "％" in text
    cleaned = text.strip("() ").replace(",", "").replace("%", "").replace("％", "")
    try:
        number = float(cleaned)
    except ValueError:
        return None, False
    return (-number if negative_parentheses else number), is_percent


def _preferred_unit(series: list[dict[str, Any]]) -> str:
    non_percent = [item for item in series if item["unit"] != "%" and any(hint in item["name"] for hint in SERIES_HINTS)]
    if non_percent:
        return "原始数值"
    counts: dict[str, int] = {}
    for item in series:
        counts[item["unit"]] = counts.get(item["unit"], 0) + len(item["points"])
    return max(counts, key=counts.get)


def _series_score(label: str, product_name: str) -> int:
    score = sum(8 for hint in SERIES_HINTS if hint in label)
    if "净值" in label:
        score += 15
    if product_name and (product_name in label or label in product_name):
        score += 25
    return score


def _representative_product(research: GeneratedResearch) -> str:
    for fact in research.performance:
        if "代表产品" in fact.label or fact.label == "产品名称":
            return fact.value
    return ""


def _load_font(size: int, bold: bool = False):
    candidates = [
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size, index=0)
            except OSError:
                continue
    return ImageFont.load_default()
