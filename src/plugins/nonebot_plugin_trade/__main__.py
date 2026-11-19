from __future__ import annotations

import asyncio
from logging import getLogger
from typing import TYPE_CHECKING

from nonebot.adapters import Bot, Event  # ruff: ignore[typing-only-third-party-import]
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, Args, Subcommand, UniMessage, on_alconna
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser import get_user, patch_matcher
from nonebot_plugin_larkutils import create_image_markdown, get_user_id
from nonebot_plugin_orm import get_session

from .chart import CandlePoint, render_kline_chart
from .config import config
from .market import (
    TradeError,
    ensure_market,
    execute_buy,
    execute_sell,
    get_holding,
    is_trading_time,
    load_candles,
    now_local,
    trading_day,
)

if TYPE_CHECKING:
    from datetime import date, datetime
    from typing import Optional

    from .market import TradeResult
    from .models import Holding, MarketState

logger = getLogger(__name__)
lang = LangHelper()
_market_lock = asyncio.Lock()

trade = on_alconna(
    Alconna(
        "trade",
        Subcommand("buy", Args["amount?", str, ""]),
        Subcommand("sell", Args["amount?", str, ""]),
    ),
)
patch_matcher(trade)


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _fmt_signed(value: float) -> str:
    if abs(value) < 0.005:
        value = 0.0
    return f"{value:+.2f}"


def _fmt_impact(value: float) -> str:
    text = f"{value:.4f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _holding_texts(holding_shares: int, cost_basis: float, price: float) -> tuple[str, str, str]:
    """返回 (平均成本, 浮动盈亏, 盈亏比例) 的展示文本"""
    if holding_shares <= 0 or cost_basis <= 0:
        return "—", "—", "—"
    average_cost = cost_basis / holding_shares
    profit = holding_shares * price - cost_basis
    profit_rate = profit / cost_basis * 100
    return _fmt(average_cost), _fmt_signed(profit), f"{_fmt_signed(profit_rate)}%"


async def build_market_info(
    user_id: str,
    now: datetime,
    state: MarketState,
    holding: Holding,
) -> str:
    trading = is_trading_time(now)
    status = await lang.text("main.status_open" if trading else "main.status_closed", user_id)
    price = state.price
    day_open = state.day_open or price
    prev_close = state.prev_close or price
    change = (price - day_open) / day_open * 100 if day_open > 0 else 0.0
    shares = holding.shares
    frozen = holding.frozen_shares
    sellable = max(0, shares - frozen)
    average_cost, profit, profit_rate = _holding_texts(shares, holding.cost_basis, price)
    hint = await lang.text("main.hint" if trading else "main.hint_closed", user_id)
    return await lang.text(
        "main.info",
        user_id,
        status=status,
        price=_fmt(price),
        day_open=_fmt(day_open),
        prev_close=_fmt(prev_close),
        change=f"{_fmt_signed(change)}%",
        shares=shares,
        sellable=sellable,
        frozen=frozen,
        avg_cost=average_cost,
        pnl=profit,
        pnl_pct=profit_rate,
        daily_bought=holding.daily_bought,
        daily_sold=holding.daily_sold,
        daily_limit=config.trade_daily_limit,
        float_shares=state.float_shares,
        total_shares=config.trade_total_shares,
        hint=hint,
    )


async def render_chart(
    user_id: str,
    chart_day: Optional[date],
    points: list[CandlePoint],
    reference_price: Optional[float],
) -> Optional[bytes]:
    if chart_day is None:
        return None
    title = await lang.text("chart.title", user_id, chart_day.strftime("%Y-%m-%d"))
    empty_text = await lang.text("chart.empty", user_id)
    try:
        return await asyncio.to_thread(
            render_kline_chart,
            chart_day,
            points,
            title,
            empty_text,
            reference_price,
        )
    except Exception:
        logger.exception("渲染 K 线图失败，回退到文本消息")
        return None


async def send_market_info(bot: Bot, event: Event, info: str, chart: Optional[bytes]) -> None:
    if chart is None:
        await trade.finish(info)
    if isinstance(bot, QQBot):
        try:
            image_markdown = await create_image_markdown(chart, bot)
            await UniMessage().style(f"{info}\n\n{image_markdown}", "markdown").send(target=event, bot=bot)
        except Exception:
            logger.exception("发送 K 线图失败，回退到文本消息")
            await trade.finish(info)
        await trade.finish()
    try:
        message = UniMessage().text(info) + UniMessage().image(raw=chart)
        await message.send(target=event, bot=bot)
    except Exception:
        logger.exception("发送 K 线图失败，回退到文本消息")
        await trade.finish(info)
    await trade.finish()


async def cap_note(side: str, user_id: str, result: TradeResult) -> str:
    if result.capped_reason == "daily":
        return await lang.text(f"{side}.note_daily", user_id, result.shares)
    if result.capped_reason == "float":
        return await lang.text(f"{side}.note_float", user_id, result.shares)
    return ""


@trade.assign("$main")
async def handle_trade_main(bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    now = now_local()
    async with _market_lock:
        async with get_session() as session:
            state = await ensure_market(session, now)
            holding = await get_holding(session, user_id, trading_day(now))
            candles, chart_day = await load_candles(session, state)
            info = await build_market_info(user_id, now, state, holding)
            points = [
                CandlePoint(
                    slot=candle.slot,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                )
                for candle in candles
            ]
            reference_price = state.day_open if chart_day == state.day else None
            await session.commit()
    chart = await render_chart(user_id, chart_day, points, reference_price)
    await send_market_info(bot, event, info, chart)


@trade.assign("buy")
async def handle_trade_buy(amount: str, user_id: str = get_user_id()) -> None:
    if not amount.strip():
        await lang.finish("error.usage_buy", user_id)
    now = now_local()
    user = await get_user(user_id)
    async with _market_lock:
        async with get_session() as session:
            state = await ensure_market(session, now)
            try:
                result = await execute_buy(session, state, user, amount, now)
            except TradeError as error:
                await session.commit()
                await lang.finish(error.key, user_id, *error.format_args)
            await session.commit()
    note = await cap_note("buy", user_id, result)
    await lang.finish(
        "buy.success",
        user_id,
        price=_fmt(result.price),
        shares=result.shares,
        gross=_fmt(result.gross),
        fee=_fmt(result.fee),
        amount=_fmt(result.amount),
        impact=_fmt_impact(result.impact * 100),
        new_price=_fmt(result.new_price),
        shares_after=result.shares_after,
        sellable_after=result.sellable_after,
        frozen_after=result.frozen_after,
        daily_bought=result.daily_bought,
        daily_limit=config.trade_daily_limit,
        balance_after=_fmt(result.balance_after),
        note=note,
    )


@trade.assign("sell")
async def handle_trade_sell(amount: str, user_id: str = get_user_id()) -> None:
    if not amount.strip():
        await lang.finish("error.usage_sell", user_id)
    now = now_local()
    user = await get_user(user_id)
    async with _market_lock:
        async with get_session() as session:
            state = await ensure_market(session, now)
            try:
                result = await execute_sell(session, state, user, amount, now)
            except TradeError as error:
                await session.commit()
                await lang.finish(error.key, user_id, *error.format_args)
            await session.commit()
    note = await cap_note("sell", user_id, result)
    await lang.finish(
        "sell.success",
        user_id,
        price=_fmt(result.price),
        shares=result.shares,
        gross=_fmt(result.gross),
        fee=_fmt(result.fee),
        amount=_fmt(result.amount),
        impact=_fmt_impact(result.impact * 100),
        new_price=_fmt(result.new_price),
        shares_after=result.shares_after,
        sellable_after=result.sellable_after,
        frozen_after=result.frozen_after,
        daily_sold=result.daily_sold,
        daily_limit=config.trade_daily_limit,
        balance_after=_fmt(result.balance_after),
        note=note,
    )
