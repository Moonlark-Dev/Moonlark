"""交易面板的构建。

QQ 官方机器人使用原生 markdown 消息：标题、引用块与分组拉开层次；其它适配器
没有 markdown 消息，改为把同一份 markdown 交给 ``md_to_pic`` 渲染成图片，渲染
失败时回退到纯文本面板。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from nonebot_plugin_larklang import LangHelper

from .config import config
from .market import is_trading_time

if TYPE_CHECKING:
    from datetime import datetime

    from .models import Holding, MarketState

lang = LangHelper()


@dataclass(frozen=True)
class PanelData:
    """构建面板需要的展示数据（在 handler 里一次性算好）"""

    trading: bool
    price: str
    day_open: str
    prev_close: str
    change: str
    change_pct: str
    change_formula: str
    gap_pct: str
    trend: str
    shares: int
    sellable: int
    frozen: int
    average_cost: str
    profit: str
    profit_rate: str
    profit_formula: str
    profit_rate_formula: str
    daily_bought: int
    daily_sold: int
    daily_limit: int


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _fmt_signed(value: float) -> str:
    if abs(value) < 0.005:
        value = 0.0
    return f"{value:+.2f}"


# 涨跌/盈亏文本用行内公式着色：QQ 官方 markdown 没有给文字上色的语法，但
# ``\(...\)`` 会交给公式渲染器，``\color{...}`` 可以给数字上色；非 QQ 适配器把
# 同一份 markdown 交给 md_to_pic，KaTeX 也支持 ``\color``，两边效果一致。
_TREND_ARROWS = {
    1: r"\blacktriangle",
    -1: r"\blacktriangledown",
    0: r"\cdot",
}


def _change_color(value: float) -> str:
    """红涨绿跌，平盘灰色（与 K 线图配色一致）"""
    return "red" if value > 0 else "green" if value < 0 else "gray"


def _signed_formula(value: float, text: str) -> str:
    """把带符号的数值（浮动盈亏、盈亏比例）包成上色公式"""
    # 公式里的 % 是注释符，必须转义
    body = text.replace("%", r"\%")
    return rf"\(\color{{{_change_color(value)}}}{{{body}}}\)"


def _change_formula(change: float, change_pct: str) -> str:
    """把涨跌文本包成 LaTeX 行内公式（颜色 + 箭头 + 百分比）

    百分比连同正负号放进一组花括号：``+6.06`` 直接跟在 ``\\ `` 后面会被当成
    二元运算符排成「+ 6.06」，分组后才和纯文本一样是「+6.06」。
    """
    arrow = _TREND_ARROWS[1 if change > 0 else -1 if change < 0 else 0]
    percent = "{" + change_pct.replace("%", r"\%") + "}"
    return rf"\(\color{{{_change_color(change)}}}{{{arrow}\ {percent}}}\)"


def _holding_texts(shares: int, cost_basis: float, price: float) -> tuple[str, str, str, str, str]:
    """返回 (平均成本, 浮动盈亏, 盈亏比例, 浮动盈亏公式, 盈亏比例公式) 的展示文本"""
    if shares <= 0 or cost_basis <= 0:
        return "—", "—", "—", "—", "—"
    average_cost = cost_basis / shares
    profit = shares * price - cost_basis
    profit_rate = profit / cost_basis * 100
    profit_text = _fmt_signed(profit)
    profit_rate_text = f"{_fmt_signed(profit_rate)}%"
    return (
        _fmt(average_cost),
        profit_text,
        profit_rate_text,
        _signed_formula(profit, profit_text),
        _signed_formula(profit_rate, profit_rate_text),
    )


def build_panel_data(state: MarketState, holding: Holding, now: datetime) -> PanelData:
    """把市场状态与持仓整理成面板展示数据

    今日涨跌按标准口径以昨日收盘价为基准（包含隔夜跳空）；缺口幅度单独展示在
    「今开」后面，避免跳空低开时仍显示上涨。
    """
    price = state.price
    day_open = state.day_open or price
    prev_close = state.prev_close or price
    change = price - prev_close
    change_pct = change / prev_close * 100 if prev_close > 0 else 0.0
    change_pct_text = f"{_fmt_signed(change_pct)}%"
    gap_pct = (day_open - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
    shares = holding.shares
    frozen = holding.frozen_shares
    average_cost, profit, profit_rate, profit_formula, profit_rate_formula = _holding_texts(
        shares,
        holding.cost_basis,
        price,
    )
    if change > 0:
        trend = "▲"
    elif change < 0:
        trend = "▼"
    else:
        trend = "·"
    return PanelData(
        trading=is_trading_time(now),
        price=_fmt(price),
        day_open=_fmt(day_open),
        prev_close=_fmt(prev_close),
        change=_fmt_signed(change),
        change_pct=change_pct_text,
        change_formula=_change_formula(change, change_pct_text),
        gap_pct=f"{_fmt_signed(gap_pct)}%",
        trend=trend,
        shares=shares,
        sellable=max(0, shares - frozen),
        frozen=frozen,
        average_cost=average_cost,
        profit=profit,
        profit_rate=profit_rate,
        profit_formula=profit_formula,
        profit_rate_formula=profit_rate_formula,
        daily_bought=holding.daily_bought,
        daily_sold=holding.daily_sold,
        daily_limit=config.trade_daily_limit,
    )


async def build_panel_markdown(user_id: str, data: PanelData) -> str:
    """构建 markdown 面板：QQ 官方直接发送，其它适配器渲染成图片

    多条信息用列表项分行，而不是同一个引用块里的软换行——markdown 渲染会把软换行
    折叠成空格，面板图片里会挤成一整段。
    """
    market_lines = "\n".join(
        [
            await lang.text("panel.price", user_id, price=data.price),
            await lang.text(
                "panel.change",
                user_id,
                change_formula=data.change_formula,
                change=data.change,
            ),
            await lang.text(
                "panel.open_close",
                user_id,
                day_open=data.day_open,
                gap_pct=data.gap_pct,
                prev_close=data.prev_close,
            ),
        ],
    )
    if data.shares > 0:
        holding_lines = "\n".join(
            [
                await lang.text(
                    "panel.holding_shares",
                    user_id,
                    shares=data.shares,
                    sellable=data.sellable,
                    frozen=data.frozen,
                ),
                await lang.text(
                    "panel.holding_cost",
                    user_id,
                    average_cost=data.average_cost,
                ),
                await lang.text(
                    "panel.holding_profit",
                    user_id,
                    profit_formula=data.profit_formula,
                    profit_rate_formula=data.profit_rate_formula,
                ),
            ],
        )
    else:
        holding_lines = await lang.text("panel.holding_empty", user_id)
    blocks = [
        await lang.text("panel.title", user_id),
        await lang.text("panel.status_open" if data.trading else "panel.status_closed", user_id),
        await lang.text("panel.market_title", user_id),
        market_lines,
        await lang.text("panel.holding_title", user_id),
        holding_lines,
        await lang.text("panel.trading_title", user_id),
        await lang.text(
            "panel.trading",
            user_id,
            daily_bought=data.daily_bought,
            daily_sold=data.daily_sold,
            daily_limit=data.daily_limit,
        ),
        await lang.text("panel.hint" if data.trading else "panel.hint_closed", user_id),
    ]
    return "\n\n".join(blocks)


async def build_panel_text(user_id: str, data: PanelData) -> str:
    """构建纯文本面板，供渲染图片失败时回退"""
    status = await lang.text("main.status_open" if data.trading else "main.status_closed", user_id)
    hint = await lang.text("main.hint" if data.trading else "main.hint_closed", user_id)
    return await lang.text(
        "main.info",
        user_id,
        status=status,
        price=data.price,
        day_open=data.day_open,
        prev_close=data.prev_close,
        trend=data.trend,
        change=data.change,
        change_pct=data.change_pct,
        gap_pct=data.gap_pct,
        shares=data.shares,
        sellable=data.sellable,
        frozen=data.frozen,
        avg_cost=data.average_cost,
        pnl=data.profit,
        pnl_pct=data.profit_rate,
        daily_bought=data.daily_bought,
        daily_sold=data.daily_sold,
        daily_limit=data.daily_limit,
        hint=hint,
    )
