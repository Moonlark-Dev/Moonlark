from __future__ import annotations

import asyncio
from logging import getLogger
from typing import TYPE_CHECKING

from nonebot.adapters import Bot, Event  # ruff: ignore[typing-only-third-party-import]
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Alconna, Args, Button, Subcommand, UniMessage, on_alconna
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkuser import get_user, patch_matcher
from nonebot_plugin_larkutils import create_image_markdown, get_user_id
from nonebot_plugin_larkutils.command import get_command_prefix
from nonebot_plugin_orm import get_session

from .chart import CandlePoint, render_kline_chart
from .config import config
from .market import (
    TradeError,
    ensure_market,
    execute_buy,
    execute_sell,
    get_holding,
    load_recent_candles,
    now_local,
    trading_day,
)
from .panel import PanelData, build_panel_data, build_panel_markdown, build_panel_text

if TYPE_CHECKING:
    from datetime import date

    from typing import Optional

    from .market import TradeResult

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


async def render_chart(
    user_id: str,
    chart_day: Optional[date],
    points: list[CandlePoint],
    reference_price: Optional[float],
) -> Optional[bytes]:
    if chart_day is None:
        return None
    visible_candles = max(1, config.trade_chart_candles)
    try:
        # chart.title 使用命名占位符 {date}/{count}，必须按关键字传参，位置参数会抛 KeyError
        title = await lang.text(
            "chart.title",
            user_id,
            date=chart_day.strftime("%Y-%m-%d"),
            count=visible_candles,
        )
        empty_text = await lang.text("chart.empty", user_id)
        return await asyncio.to_thread(
            render_kline_chart,
            chart_day,
            points,
            title,
            empty_text,
            reference_price,
            visible_candles,
        )
    except Exception:
        logger.exception("渲染 K 线图失败，回退到文本消息")
        return None


def _keyboard_row(button_count: int) -> int | None:
    """按钮超过 3 个时分两行，每行最多 3 个，避免 QQ 标签被截断"""
    return (button_count + 1) // 2 if button_count > 3 else None


async def build_trade_keyboard(user_id: str) -> list[Button]:
    prefix = get_command_prefix()
    return [
        # 股数由用户自行填写，所以用 input 类型：点击后把 `/trade buy `、`/trade sell ` 预填进输入框，
        # 用户补上股数（买入还可填 50%、all）再发送；enter 类型会直接发出固定股数，改不了数量。
        Button("input", await lang.text("button.buy", user_id), text=f"{prefix}trade buy "),
        Button("enter", await lang.text("button.buy_all", user_id), text=f"{prefix}trade buy all"),
        Button("input", await lang.text("button.sell", user_id), text=f"{prefix}trade sell "),
        Button("enter", await lang.text("button.sell_all", user_id), text=f"{prefix}trade sell all"),
        Button("enter", await lang.text("button.refresh", user_id), text=f"{prefix}trade"),
    ]


async def send_trade_text_with_keyboard(bot: Bot, event: Event, user_id: str, text: str) -> None:
    buttons = await build_trade_keyboard(user_id)
    await (
        UniMessage()
        .style(text, "markdown")
        .keyboard(*buttons, row=_keyboard_row(len(buttons)))
        .send(target=event, bot=bot)
    )
    await trade.finish()


async def send_plain_panel(
    bot: Bot,
    event: Event,
    user_id: str,
    panel: PanelData,
    chart: Optional[bytes],
) -> None:
    """纯文本面板 + K 线图，供面板图片渲染失败时回退"""
    text = await build_panel_text(user_id, panel)
    if chart is None:
        await trade.finish(text)
        return
    try:
        message = UniMessage().text(text) + UniMessage().image(raw=chart)
        await message.send(target=event, bot=bot)
    except Exception:
        logger.exception("发送 K 线图失败，回退到文本消息")
        await trade.finish(text)
        return
    await trade.finish()


async def send_panel(
    bot: Bot,
    event: Event,
    user_id: str,
    panel: PanelData,
    chart: Optional[bytes],
) -> None:
    """发送交易面板：QQ 官方用 markdown + 按钮，其它适配器把面板渲染成图片"""
    markdown = await build_panel_markdown(user_id, panel)
    if isinstance(bot, QQBot):
        text = markdown
        if chart is not None:
            try:
                text = f"{text}\n\n{await create_image_markdown(chart, bot)}"
            except Exception:
                logger.exception("发送 K 线图失败，回退到文本消息")
        await send_trade_text_with_keyboard(bot, event, user_id, text)
        return

    try:
        panel_image = await md_to_pic(markdown)
    except Exception:
        logger.exception("渲染交易面板失败，回退到文本消息")
        await send_plain_panel(bot, event, user_id, panel, chart)
        return
    message = UniMessage().image(raw=panel_image)
    if chart is not None:
        message = message + UniMessage().image(raw=chart)
    try:
        await message.send(target=event, bot=bot)
    except Exception:
        logger.exception("发送交易面板失败，回退到文本消息")
        await send_plain_panel(bot, event, user_id, panel, chart)
        return
    await trade.finish()


async def send_trade_result(bot: Bot, event: Event, user_id: str, key: str, **kwargs: object) -> None:
    if isinstance(bot, QQBot):
        text = await lang.text(key, user_id, **kwargs)
        await send_trade_text_with_keyboard(bot, event, user_id, text)
        return
    await lang.finish(key, user_id, **kwargs)


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
            candles = await load_recent_candles(session, max(1, config.trade_chart_candles))
            panel = build_panel_data(state, holding, now)
            points = [
                CandlePoint(
                    day=candle.day,
                    slot=candle.slot,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                )
                for candle in candles
            ]
            reference_price = state.day_open or None
            chart_day = state.day
            await session.commit()
    chart = await render_chart(user_id, chart_day, points, reference_price)
    await send_panel(bot, event, user_id, panel, chart)


@trade.assign("buy")
async def handle_trade_buy(bot: Bot, event: Event, amount: str, user_id: str = get_user_id()) -> None:
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
    await send_trade_result(
        bot,
        event,
        user_id,
        "buy.success",
        price=_fmt(result.price),
        shares=result.shares,
        gross=_fmt(result.gross),
        fee=_fmt(result.fee),
        amount=_fmt(result.amount),
        shares_after=result.shares_after,
        sellable_after=result.sellable_after,
        frozen_after=result.frozen_after,
        daily_bought=result.daily_bought,
        daily_limit=config.trade_daily_limit,
        balance_after=_fmt(result.balance_after),
        note=note,
    )


@trade.assign("sell")
async def handle_trade_sell(bot: Bot, event: Event, amount: str, user_id: str = get_user_id()) -> None:
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
    await send_trade_result(
        bot,
        event,
        user_id,
        "sell.success",
        price=_fmt(result.price),
        shares=result.shares,
        gross=_fmt(result.gross),
        fee=_fmt(result.fee),
        amount=_fmt(result.amount),
        shares_after=result.shares_after,
        sellable_after=result.sellable_after,
        frozen_after=result.frozen_after,
        daily_sold=result.daily_sold,
        daily_limit=config.trade_daily_limit,
        balance_after=_fmt(result.balance_after),
        note=note,
    )
