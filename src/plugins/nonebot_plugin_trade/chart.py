from __future__ import annotations

import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:
    from datetime import date

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

# 固定展示的蜡烛数量；不足时左侧留白，最新一根始终贴在右侧
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
        reference_price: 参考价（通常为当日开盘价），画一条虚线
    """
    if not title:
        title = f"{current_day.isoformat()} 5 分钟 K 线"
    with _RENDER_LOCK:
        if not candles:
            return _render_empty(title, empty_text)

        total = max(1, visible_candles, len(candles))
        offset = total - len(candles)
        lows = [candle.low for candle in candles]
        highs = [candle.high for candle in candles]

        figure = Figure(figsize=(13, 6.2), dpi=150, facecolor=_BACKGROUND)
        axes = figure.add_subplot(111)
        axes.set_facecolor(_BACKGROUND)

        price_span = max(highs) - min(lows)
        body_floor = max(price_span * 0.002, max(highs) * 0.0001, 1e-4)

        for index, candle in enumerate(candles):
            position = offset + index
            color = _UP_COLOR if candle.close >= candle.open else _DOWN_COLOR
            is_current_day = candle.day == current_day
            axes.vlines(
                position,
                candle.low,
                candle.high,
                color=color,
                linewidth=0.9,
                alpha=1.0 if is_current_day else _PREVIOUS_DAY_WICK_ALPHA,
                zorder=3,
            )
            bottom = min(candle.open, candle.close)
            height = max(abs(candle.close - candle.open), body_floor)
            axes.add_patch(
                Rectangle(
                    (position - 0.32, bottom),
                    0.64,
                    height,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=0.5,
                    alpha=1.0 if is_current_day else _PREVIOUS_DAY_BODY_ALPHA,
                    zorder=4,
                ),
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

        if reference_price is not None:
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
        padding = max(price_span * 0.08, max(highs) * 0.002, 0.01)
        axes.set_ylim(min(lows) - padding, max(highs) + padding)
        axes.set_ylabel("VimCoin", fontsize=10, color=_MUTED_COLOR)

        last = candles[-1]
        axes.annotate(
            f"{last.close:.2f}",
            (offset + len(candles) - 1, last.close),
            textcoords="offset points",
            xytext=(0, 14),
            ha="center",
            fontsize=10,
            fontweight="bold",
            color=_TEXT_COLOR,
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": _MUTED_COLOR, "alpha": 0.9},
        )

        axes.set_title(title, fontsize=15, fontweight="bold", color=_TEXT_COLOR, pad=16)
        axes.grid(visible=True, axis="y", alpha=0.25, linestyle="--", linewidth=0.6)
        axes.set_axisbelow(True)
        for spine in ("top", "right"):
            axes.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            axes.spines[spine].set_color("#D0D7DE")
        axes.tick_params(colors=_MUTED_COLOR, labelsize=9)
        figure.tight_layout()
        return _to_png(figure)
