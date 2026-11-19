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


@dataclass(frozen=True)
class CandlePoint:
    slot: int
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


def _slot_label(slot: int) -> str:
    minutes = 8 * 60 + slot * 5
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _render_empty(empty_text: str) -> bytes:
    figure = Figure(figsize=(10, 4), dpi=150, facecolor=_BACKGROUND)
    axes = figure.add_subplot(111)
    axes.set_facecolor(_BACKGROUND)
    axes.text(0.5, 0.5, empty_text, ha="center", va="center", fontsize=18, color=_MUTED_COLOR)
    axes.axis("off")
    return _to_png(figure)


def _to_png(figure: Figure) -> bytes:
    buffer = BytesIO()
    FigureCanvasAgg(figure).print_png(buffer)
    return buffer.getvalue()


def render_kline_chart(
    day: date,
    candles: Sequence[CandlePoint],
    title: str,
    empty_text: str,
    reference_price: Optional[float] = None,
) -> bytes:
    """渲染 5 分钟 K 线图，红涨绿跌；返回 PNG 字节"""
    if not title:
        title = f"{day.isoformat()} 5 分钟 K 线"
    with _RENDER_LOCK:
        if not candles:
            return _render_empty(empty_text)

        figure = Figure(figsize=(12, 6), dpi=150, facecolor=_BACKGROUND)
        axes = figure.add_subplot(111)
        axes.set_facecolor(_BACKGROUND)

        lows = [candle.low for candle in candles]
        highs = [candle.high for candle in candles]
        price_span = max(highs) - min(lows)
        body_floor = max(price_span * 0.002, max(highs) * 0.0001, 1e-4)

        for index, candle in enumerate(candles):
            color = _UP_COLOR if candle.close >= candle.open else _DOWN_COLOR
            axes.vlines(index, candle.low, candle.high, color=color, linewidth=0.9, zorder=3)
            bottom = min(candle.open, candle.close)
            height = max(abs(candle.close - candle.open), body_floor)
            axes.add_patch(
                Rectangle(
                    (index - 0.32, bottom),
                    0.64,
                    height,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=0.5,
                    zorder=4,
                ),
            )

        if reference_price is not None:
            axes.axhline(reference_price, color=_MUTED_COLOR, linestyle="--", linewidth=1, alpha=0.7, zorder=2)

        positions = list(range(0, len(candles), 12))
        axes.set_xticks(positions)
        axes.set_xticklabels([_slot_label(candles[position].slot) for position in positions], fontsize=9)
        axes.set_xlim(-1, len(candles))

        padding = max(price_span * 0.08, max(highs) * 0.002, 0.01)
        axes.set_ylim(min(lows) - padding, max(highs) + padding)
        axes.set_ylabel("VimCoin", fontsize=10, color=_MUTED_COLOR)

        last = candles[-1]
        axes.annotate(
            f"{last.close:.2f}",
            (len(candles) - 1, last.close),
            textcoords="offset points",
            xytext=(0, 14),
            ha="center",
            fontsize=10,
            fontweight="bold",
            color=_TEXT_COLOR,
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": _MUTED_COLOR, "alpha": 0.9},
        )

        axes.set_title(title, fontsize=16, fontweight="bold", color=_TEXT_COLOR, pad=16)
        axes.grid(visible=True, axis="y", alpha=0.25, linestyle="--", linewidth=0.6)
        axes.set_axisbelow(True)
        for spine in ("top", "right"):
            axes.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            axes.spines[spine].set_color("#D0D7DE")
        axes.tick_params(colors=_MUTED_COLOR, labelsize=9)
        figure.tight_layout()
        return _to_png(figure)
