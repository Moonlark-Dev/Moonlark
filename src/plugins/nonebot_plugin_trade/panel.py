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
    gap_pct: str
    trend: str
    shares: int
    sellable: int
    frozen: int
    average_cost: str
    profit: str
    profit_rate: str
    daily_bought: int
    daily_sold: int
    daily_limit: int


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _fmt_signed(value: float) -> str:
    if abs(value) < 0.005:
        value = 0.0
    return f"{value:+.2f}"


def _holding_texts(shares: int, cost_basis: float, price: float) -> tuple[str, str, str]:
    """返回 (平均成本, 浮动盈亏, 盈亏比例) 的展示文本"""
    if shares <= 0 or cost_basis <= 0:
        return "—", "—", "—"
    average_cost = cost_basis / shares
    profit = shares * price - cost_basis
    profit_rate = profit / cost_basis * 100
    return _fmt(average_cost), _fmt_signed(profit), f"{_fmt_signed(profit_rate)}%"


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
    gap_pct = (day_open - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
    shares = holding.shares
    frozen = holding.frozen_shares
    average_cost, profit, profit_rate = _holding_texts(shares, holding.cost_basis, price)
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
        change_pct=f"{_fmt_signed(change_pct)}%",
        gap_pct=f"{_fmt_signed(gap_pct)}%",
        trend=trend,
        shares=shares,
        sellable=max(0, shares - frozen),
        frozen=frozen,
        average_cost=average_cost,
        profit=profit,
        profit_rate=profit_rate,
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
                trend=data.trend,
                change_pct=data.change_pct,
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
                    profit=data.profit,
                    profit_rate=data.profit_rate,
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
