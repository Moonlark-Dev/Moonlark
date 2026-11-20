"""online-timer 的在线概率热力时间轴。

``ghot`` 用一条色带表达「群里哪段时间热闹」；这里用同一套色带语言回答另一个问题：某个
时间点（星期几的几点）在记录下来的数据里，这个人在线的概率是多少。

统计口径是把记录切成 (星期, 小时) 单元格：

    单元格概率 = 单元格内处于在线状态的总秒数 / 单元格在统计窗口内的总秒数

分母按单元格在窗口里实际覆盖的时长计算，所以窗口两端（30 天前的那个半天、今天还没走完的
那个小时）都按实际长度折算，概率天然落在 0-1 之间，不需要给边界写特例。
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Sequence

from PIL import ImageDraw, ImageFont

from .constants import PROBABILITY_WINDOW_DAYS

WEEKDAY_COUNT = 7
HOURS_PER_DAY = 24

Interval = tuple[datetime, datetime]
"""一段在线区间 ``(start, end)``，两端都是不带时区的本地时间。"""

# 色阶：0% 是接近白纸的灰（好和「有数据但没在线」区分），越接近 100% 越深。
_HEAT_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.0, (240, 243, 246)),
    (0.25, (253, 216, 170)),
    (0.5, (247, 177, 102)),
    (0.75, (232, 130, 51)),
    (1.0, (196, 66, 20)),
)
_NO_DATA_COLOR = (214, 218, 224)
_LEGEND_PROBABILITIES = (0.15, 0.35, 0.55, 0.75, 0.95)
_LEGEND_SWATCH_SIZE = 12
_LEGEND_GAP = 4

_TEXT_COLOR = (0, 0, 0)
_SUB_TEXT_COLOR = (120, 120, 120)
_NOW_COLOR = (37, 99, 235)


@dataclass(frozen=True)
class ProbabilityGrid:
    """统计窗口内的在线概率矩阵，``probabilities[weekday][hour]`` 取值 0-1。"""

    probabilities: list[list[float]]
    covered_seconds: list[list[float]]
    window_start: datetime
    window_end: datetime

    def probability_at(self, moment: datetime) -> float:
        """``moment`` 所在单元格（星期 + 小时）的在线概率。"""
        return self.probabilities[moment.weekday()][moment.hour]

    def has_data(self, weekday: int, hour: int) -> bool:
        """该单元格是否落在统计窗口里（窗口短于一周时，缺的那几个星期没有数据）。"""
        return self.covered_seconds[weekday][hour] > 0


def merge_intervals(intervals: Iterable[Interval], window_start: datetime, window_end: datetime) -> list[Interval]:
    """把区间裁剪到 ``[window_start, window_end]``，再合并重叠或首尾相接的部分。

    记录本身通常不重叠（同一用户的记录是往后延长的），但异常数据、正好跨窗口边界的记录
    都可能让同一秒被数两次；先合并才能保证概率不会超过 1。
    """
    clipped: list[Interval] = []
    for start, end in intervals:
        start = max(start, window_start)
        end = min(end, window_end)
        if end > start:
            clipped.append((start, end))
    clipped.sort()
    merged: list[Interval] = []
    for start, end in clipped:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _online_seconds_by_cell(
    intervals: Iterable[Interval], window_start: datetime, window_end: datetime
) -> list[list[float]]:
    """每个单元格里处于在线状态的秒数。"""
    seconds = [[0.0] * HOURS_PER_DAY for _ in range(WEEKDAY_COUNT)]
    for start, end in merge_intervals(intervals, window_start, window_end):
        cursor = start
        while cursor < end:
            hour_end = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            chunk_end = min(hour_end, end)
            seconds[cursor.weekday()][cursor.hour] += (chunk_end - cursor).total_seconds()
            cursor = chunk_end
    return seconds


def covered_seconds_by_cell(window_start: datetime, window_end: datetime) -> list[list[float]]:
    """每个单元格在窗口内实际存在的秒数，作为概率的分母。"""
    seconds = [[0.0] * HOURS_PER_DAY for _ in range(WEEKDAY_COUNT)]
    day = window_start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < window_end:
        for hour in range(HOURS_PER_DAY):
            cell_start = day + timedelta(hours=hour)
            if cell_start >= window_end:
                break
            cell_end = cell_start + timedelta(hours=1)
            overlap = (min(cell_end, window_end) - max(cell_start, window_start)).total_seconds()
            if overlap > 0:
                seconds[day.weekday()][hour] += overlap
        day += timedelta(days=1)
    return seconds


def compute_probability_grid(
    intervals: Iterable[Interval],
    now: datetime,
    window_days: int = PROBABILITY_WINDOW_DAYS,
) -> ProbabilityGrid:
    """按 ``[now - window_days, now]`` 的窗口算出 7×24 的在线概率矩阵。"""
    window_end = now
    window_start = now - timedelta(days=window_days)
    covered = covered_seconds_by_cell(window_start, window_end)
    online = _online_seconds_by_cell(intervals, window_start, window_end)
    probabilities = [
        [
            round(min(1.0, online[weekday][hour] / covered[weekday][hour]), 4) if covered[weekday][hour] > 0 else 0.0
            for hour in range(HOURS_PER_DAY)
        ]
        for weekday in range(WEEKDAY_COUNT)
    ]
    return ProbabilityGrid(
        probabilities=probabilities,
        covered_seconds=covered,
        window_start=window_start,
        window_end=window_end,
    )


def heat_color(probability: float) -> tuple[int, int, int]:
    """把 0-1 的概率映射成色阶上的颜色，越靠 1 越深。"""
    ratio = min(1.0, max(0.0, probability))
    for (left_ratio, left_color), (right_ratio, right_color) in itertools.pairwise(_HEAT_STOPS):
        if ratio <= right_ratio:
            span = right_ratio - left_ratio
            weight = 0.0 if span <= 0 else (ratio - left_ratio) / span
            return (
                round(left_color[0] + (right_color[0] - left_color[0]) * weight),
                round(left_color[1] + (right_color[1] - left_color[1]) * weight),
                round(left_color[2] + (right_color[2] - left_color[2]) * weight),
            )
    return _HEAT_STOPS[-1][1]


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def _draw_text_left_middle(
    draw: ImageDraw.ImageDraw,
    x: float,
    center_y: float,
    text: str,
    font: ImageFont.ImageFont,
    color: tuple[int, int, int],
) -> None:
    """以 ``(x, center_y)`` 为左侧中点绘制一行文字。"""
    _, top, _, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text((x, center_y - (top + bottom) / 2), text, fill=color, font=font)


def draw_heatmap(
    draw: ImageDraw.ImageDraw,
    grid: ProbabilityGrid,
    now: datetime,
    weekday_labels: Sequence[str],
    hour_labels: Sequence[str],
    low_label: str,
    high_label: str,
    label_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
    left: float,
    top: float,
    label_width: float,
    cell_width: float,
    cell_height: float,
) -> float:
    """把概率矩阵画成热力时间轴，返回绘制内容的下边界 y。

    布局：左列是星期标签，右侧是 24 个 1 小时单元格，单元格之间留 1px 白缝；「现在」所在的
    单元格用蓝框标出。网格上方右对齐一条「低 ▢▢▢▢▢ 高」色阶图例，下方一行小时刻度。
    """
    grid_left = left + label_width
    grid_right = grid_left + HOURS_PER_DAY * cell_width
    grid_bottom = top + WEEKDAY_COUNT * cell_height

    # 图例：右对齐到网格右边缘，单独占网格上方那一行
    legend_width = (
        _text_width(draw, low_label, small_font)
        + _LEGEND_GAP
        + len(_LEGEND_PROBABILITIES) * (_LEGEND_SWATCH_SIZE + 2)
        + _LEGEND_GAP
        + _text_width(draw, high_label, small_font)
    )
    legend_y = top - _LEGEND_SWATCH_SIZE - 8
    cursor_x = grid_right - legend_width
    draw.text((cursor_x, legend_y), low_label, fill=_SUB_TEXT_COLOR, font=small_font)
    cursor_x += _text_width(draw, low_label, small_font) + _LEGEND_GAP
    for probability in _LEGEND_PROBABILITIES:
        draw.rectangle(
            [cursor_x, legend_y, cursor_x + _LEGEND_SWATCH_SIZE, legend_y + _LEGEND_SWATCH_SIZE],
            fill=heat_color(probability),
        )
        cursor_x += _LEGEND_SWATCH_SIZE + 2
    draw.text((cursor_x - 2 + _LEGEND_GAP, legend_y), high_label, fill=_SUB_TEXT_COLOR, font=small_font)

    for weekday in range(WEEKDAY_COUNT):
        row_top = top + weekday * cell_height
        _draw_text_left_middle(
            draw,
            left,
            row_top + cell_height / 2,
            weekday_labels[weekday],
            label_font,
            _TEXT_COLOR,
        )
        for hour in range(HOURS_PER_DAY):
            cell_left = grid_left + hour * cell_width
            fill = heat_color(grid.probabilities[weekday][hour]) if grid.has_data(weekday, hour) else _NO_DATA_COLOR
            draw.rectangle(
                [cell_left + 0.5, row_top + 0.5, cell_left + cell_width - 0.5, row_top + cell_height - 0.5],
                fill=fill,
            )

    current_left = grid_left + now.hour * cell_width
    current_top = top + now.weekday() * cell_height
    draw.rectangle(
        [current_left - 1, current_top - 1, current_left + cell_width + 1, current_top + cell_height + 1],
        outline=_NOW_COLOR,
        width=2,
    )

    label_y = grid_bottom + 8
    for index, label in enumerate(hour_labels):
        if len(hour_labels) <= 1:
            position = grid_left
        else:
            position = grid_left + (grid_right - grid_left) * index / (len(hour_labels) - 1)
        width = _text_width(draw, label, small_font)
        # 首尾刻度会被夹回内容区，避免「24:00」跑出卡片右边
        draw.text(
            (min(max(position - width / 2, left), grid_right - width), label_y),
            label,
            fill=_SUB_TEXT_COLOR,
            font=small_font,
        )
    return label_y + 14
