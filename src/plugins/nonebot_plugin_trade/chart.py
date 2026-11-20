from __future__ import annotations

import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:
    from datetime import date

    from matplotlib.axes import Axes

from matplotlib import font_manager, rcParams
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

_FONT_PATH = Path(__file__).resolve().parents[2] / "static" / "SarasaGothicSC-Regular.ttf"
_RENDER_LOCK = threading.Lock()

try:
    font_manager.fontManager.addfont(str(_FONT_PATH))
    rcParams["font.family"] = ["Sarasa Gothic SC", "DejaVu Sans"]
except (FileNotFoundError, RuntimeError):
    rcParams["font.family"] = ["DejaVu Sans"]
rcParams["axes.unicode_minus"] = False

_UP_COLOR = "#E74C3C"
_DOWN_COLOR = "#2ECC71"
_BACKGROUND = "#F8F9FA"
_TEXT_COLOR = "#2D3436"
_MUTED_COLOR = "#7F8C8D"

# 固定展示的蜡烛数量；不足时左侧留白、最新一根靠右，右侧预留参考价标签的位置
VISIBLE_CANDLES = 120
# 前一交易日 K 线用高透明度弱化，与当日 K 线区分
_PREVIOUS_DAY_BODY_ALPHA = 0.22
_PREVIOUS_DAY_WICK_ALPHA = 0.32


@dataclass(frozen=True)
class CandlePoint:
    day: date
    slot: int
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


@dataclass(frozen=True)
class DailyCandlePoint:
    """一根日 K 线：由该交易日已落库的 5 分钟 K 线聚合而来"""

    day: date
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


def _slot_label(slot: int) -> str:
    minutes = 8 * 60 + slot * 5
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _day_label(day: date) -> str:
    return f"{day.month:02d}-{day.day:02d}"


def _render_empty(title: str, empty_text: str) -> bytes:
    figure = Figure(figsize=(13, 6.2), dpi=150, facecolor=_BACKGROUND)
    axes = figure.add_subplot(111)
    axes.set_facecolor(_BACKGROUND)
    axes.axis("off")
    if title:
        axes.set_title(title, fontsize=15, fontweight="bold", color=_TEXT_COLOR, pad=16)
    axes.text(0.5, 0.5, empty_text, ha="center", va="center", fontsize=18, color=_MUTED_COLOR)
    return _to_png(figure)


def _to_png(figure: Figure) -> bytes:
    buffer = BytesIO()
    FigureCanvasAgg(figure).print_png(buffer)
    return buffer.getvalue()


def _create_axes() -> tuple[Figure, Axes]:
    figure = Figure(figsize=(13, 6.2), dpi=150, facecolor=_BACKGROUND)
    axes = figure.add_subplot(111)
    axes.set_facecolor(_BACKGROUND)
    return figure, axes


def _price_bounds(highs: Sequence[float], lows: Sequence[float]) -> tuple[float, float, float]:
    """返回 (y 轴下界, y 轴上界, 实体最小高度)"""
    price_span = max(highs) - min(lows)
    padding = max(price_span * 0.08, max(highs) * 0.002, 0.01)
    body_floor = max(price_span * 0.002, max(highs) * 0.0001, 1e-4)
    return min(lows) - padding, max(highs) + padding, body_floor


def _draw_candle(
    axes: Axes,
    position: float,
    open_price: float,
    high: float,
    low: float,
    close: float,
    *,
    body_floor: float,
    body_alpha: float = 1.0,
    wick_alpha: float = 1.0,
) -> None:
    """在 position 处画一根红涨绿跌的蜡烛"""
    color = _UP_COLOR if close >= open_price else _DOWN_COLOR
    axes.vlines(position, low, high, color=color, linewidth=0.9, alpha=wick_alpha, zorder=3)
    bottom = min(open_price, close)
    height = max(abs(close - open_price), body_floor)
    axes.add_patch(
        Rectangle(
            (position - 0.32, bottom),
            0.64,
            height,
            facecolor=color,
            edgecolor=color,
            linewidth=0.5,
            alpha=body_alpha,
            zorder=4,
        ),
    )


def _style_axes(axes: Axes, title: str) -> None:
    """标题、网格与坐标轴样式的统一收尾"""
    axes.set_title(title, fontsize=15, fontweight="bold", color=_TEXT_COLOR, pad=16)
    axes.grid(visible=True, axis="y", alpha=0.25, linestyle="--", linewidth=0.6)
    axes.set_axisbelow(True)
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        axes.spines[spine].set_color("#D0D7DE")
    axes.tick_params(colors=_MUTED_COLOR, labelsize=9)


def _annotate_last_close(axes: Axes, position: float, close: float) -> None:
    axes.annotate(
        f"{close:.2f}",
        (position, close),
        textcoords="offset points",
        xytext=(0, 14),
        ha="center",
        fontsize=10,
        fontweight="bold",
        color=_TEXT_COLOR,
        bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": _MUTED_COLOR, "alpha": 0.9},
    )


def _day_tick_indexes(candle_count: int, total: int) -> list[int]:
    """日 K 的日期刻度：从最新一根往回按步长取，标签之间至少隔 label_gap 根蜡烛

    数据不足时所有蜡烛都挤在右侧、间距只有 1 个 slot，日期标签必须更稀疏，
    否则会互相重叠；此时宁可只标最新一根。
    """
    if candle_count <= 0:
        return []
    label_gap = max(2, round(total * 0.05))
    step = max(1, candle_count // 8)
    candidates = sorted(set(range(candle_count - 1, -1, -step)) | {0}, reverse=True)
    indexes = [candidates[0]]
    for index in candidates[1:]:
        if abs(index - indexes[-1]) >= label_gap:
            indexes.append(index)
    return sorted(indexes)


def _day_start_indexes(candles: Sequence[CandlePoint]) -> set[int]:
    """返回每段交易日在窗口中的首根蜡烛下标（窗口首根蜡烛也算一段的起点）"""
    indexes = {0}
    for index in range(1, len(candles)):
        if candles[index].day != candles[index - 1].day:
            indexes.add(index)
    return indexes


def render_kline_chart(
    current_day: date,
    candles: Sequence[CandlePoint],
    title: str,
    empty_text: str,
    reference_price: Optional[float] = None,
    visible_candles: int = VISIBLE_CANDLES,
) -> bytes:
    """渲染最近若干根 5 分钟 K 线，红涨绿跌；前一交易日的 K 线用高透明度区分。

    Args:
        current_day: 当前交易日，用于区分当日与前一交易日的蜡烛
        candles: 按时间升序排列的蜡烛，可跨交易日
        visible_candles: 固定展示的蜡烛数量；蜡烛不足时在左侧留白
        reference_price: 参考价（通常为当日开盘价）；落在可视价格区间内时画一条虚线
    """
    if not title:
        title = f"{current_day.isoformat()} 5 分钟 K 线"
    with _RENDER_LOCK:
        if not candles:
            return _render_empty(title, empty_text)

        total = max(1, visible_candles, len(candles))
        offset = total - len(candles)
        y_bottom, y_top, body_floor = _price_bounds(
            [candle.high for candle in candles],
            [candle.low for candle in candles],
        )

        figure, axes = _create_axes()

        for index, candle in enumerate(candles):
            position = offset + index
            is_current_day = candle.day == current_day
            _draw_candle(
                axes,
                position,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                body_floor=body_floor,
                body_alpha=1.0 if is_current_day else _PREVIOUS_DAY_BODY_ALPHA,
                wick_alpha=1.0 if is_current_day else _PREVIOUS_DAY_WICK_ALPHA,
            )

        day_starts = _day_start_indexes(candles)
        for index in day_starts - {0}:
            axes.axvline(
                offset + index - 0.5,
                color=_MUTED_COLOR,
                linestyle=(0, (4, 3)),
                linewidth=1.0,
                alpha=0.5,
                zorder=2,
            )

        # 参考价落在可视价格区间外时不画（axhline 会被裁剪，text 不会，会留下悬浮数字）
        if reference_price is not None and y_bottom <= reference_price <= y_top:
            axes.axhline(reference_price, color=_MUTED_COLOR, linestyle="--", linewidth=1, alpha=0.7, zorder=2)
            axes.text(
                total + 2.4,
                reference_price,
                f"{reference_price:.2f}",
                ha="right",
                va="center",
                fontsize=8,
                color=_MUTED_COLOR,
                bbox={"boxstyle": "round,pad=0.15", "facecolor": _BACKGROUND, "edgecolor": "none", "alpha": 0.85},
            )

        # 日期刻度优先保留；其余时间刻度之间至少留出 label_gap 根蜡烛，避免标签重叠
        tick_indexes = sorted(day_starts)
        label_gap = max(2, round(total * 0.05))
        tick_step = max(1, len(candles) // 8)
        for index in [*range(tick_step, len(candles), tick_step), len(candles) - 1]:
            if all(abs(index - kept) >= label_gap for kept in tick_indexes):
                tick_indexes.append(index)
        tick_indexes.sort()
        tick_positions = [offset + index for index in tick_indexes]
        tick_labels = [
            _day_label(candles[index].day) if index in day_starts else _slot_label(candles[index].slot)
            for index in tick_indexes
        ]
        axes.set_xticks(tick_positions)
        axes.set_xticklabels(tick_labels, fontsize=8)

        axes.set_xlim(-1.5, total + 2.5)
        axes.set_ylim(y_bottom, y_top)
        axes.set_ylabel("VimCoin", fontsize=10, color=_MUTED_COLOR)
        _annotate_last_close(axes, offset + len(candles) - 1, candles[-1].close)
        _style_axes(axes, title)
        figure.tight_layout()
        return _to_png(figure)


def render_daily_kline_chart(
    candles: Sequence[DailyCandlePoint],
    title: str,
    empty_text: str,
    visible_candles: int = VISIBLE_CANDLES,
) -> bytes:
    """渲染最近若干根日 K 线，红涨绿跌。

    日 K 线由该交易日实际落库的 5 分钟 K 线聚合：开盘/收盘取当日首尾 5 分钟 K 线，
    影线直接取当日实际最高/最低价（含玩家买卖冲击写入的极值），不额外合成日线影线。

    横轴按 ``visible_candles`` 固定宽度，数据不足时所有蜡烛仍紧靠右侧排列、只在左侧
    留白——宁可让少量蜡烛挤在一边，也不把它们拉开到整条横轴上留下大片空隙。
    """
    if not title:
        title = "日 K 线"
    with _RENDER_LOCK:
        if not candles:
            return _render_empty(title, empty_text)

        total = max(1, visible_candles, len(candles))
        offset = total - len(candles)
        y_bottom, y_top, body_floor = _price_bounds(
            [candle.high for candle in candles],
            [candle.low for candle in candles],
        )
        figure, axes = _create_axes()

        for index, candle in enumerate(candles):
            _draw_candle(
                axes,
                offset + index,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                body_floor=body_floor,
            )

        tick_indexes = _day_tick_indexes(len(candles), total)
        axes.set_xticks([offset + index for index in tick_indexes])
        axes.set_xticklabels([_day_label(candles[index].day) for index in tick_indexes], fontsize=8)
        axes.set_xlim(-1.5, total + 1.5)
        axes.set_ylim(y_bottom, y_top)
        axes.set_ylabel("VimCoin", fontsize=10, color=_MUTED_COLOR)
        _annotate_last_close(axes, offset + len(candles) - 1, candles[-1].close)
        _style_axes(axes, title)
        figure.tight_layout()
        return _to_png(figure)
