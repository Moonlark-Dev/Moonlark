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

from .chart import CandlePoint, DailyCandlePoint, render_daily_kline_chart, render_kline_chart
from .config import config
from .market import (
    TradeError,
    ensure_market,
    execute_buy,
    execute_sell,
    get_holding,
    load_daily_candles,
    load_recent_candles,
    market_lock,
    now_local,
    trading_day,
)
from .panel import PanelData, build_panel_data, build_panel_markdown, build_panel_text
from .ranking import load_ranking_entries, render_ranking_image

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from typing import Optional

    from .market import RankingEntry, TradeResult

logger = getLogger(__name__)
lang = LangHelper()

trade = on_alconna(
    Alconna(
        "trade",
        Subcommand("buy", Args["amount?", str, ""]),
        Subcommand("sell", Args["amount?", str, ""]),
        Subcommand("history"),
        Subcommand("rank", alias=["ranking"]),
    ),
)
patch_matcher(trade)


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _fmt_signed(value: float) -> str:
    if abs(value) < 0.005:
        value = 0.0
    return f"{value:+.2f}"


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


async def render_daily_chart(user_id: str, points: list[DailyCandlePoint]) -> Optional[bytes]:
    """渲染日 K 线历史；文案或渲染失败时返回 None，由调用方回退到文本"""
    visible_candles = max(1, config.trade_history_candles)
    try:
        title = await lang.text("history.title", user_id, count=visible_candles)
        empty_text = await lang.text("history.empty", user_id)
        return await asyncio.to_thread(
            render_daily_kline_chart,
            points,
            title,
            empty_text,
            visible_candles,
        )
    except Exception:
        logger.exception("渲染日 K 线图失败，回退到文本消息")
        return None


async def build_history_caption(user_id: str, points: list[DailyCandlePoint]) -> str:
    if not points:
        return await lang.text("history.no_data", user_id)
    last = points[-1]
    return await lang.text(
        "history.caption",
        user_id,
        days=len(points),
        close=_fmt(last.close),
        date=last.day.strftime("%Y-%m-%d"),
    )


async def send_history_chart(
    bot: Bot,
    event: Event,
    user_id: str,
    caption: str,
    chart: Optional[bytes],
) -> None:
    """发送日 K 线历史：QQ 官方用 markdown 图床 + 键盘，其它适配器直接发图片"""
    if isinstance(bot, QQBot):
        text = caption
        if chart is not None:
            try:
                text = f"{text}\n\n{await create_image_markdown(chart, bot)}"
            except Exception:
                logger.exception("上传日 K 线图失败，回退到文本消息")
                text = caption
        await send_trade_keyboard(bot, event, text, await build_history_keyboard(user_id))
        return
    if chart is None:
        await trade.finish(caption)
        return
    try:
        await (UniMessage().text(caption) + UniMessage().image(raw=chart)).send(target=event, bot=bot)
    except Exception:
        logger.exception("发送日 K 线图失败，回退到文本消息")
        await trade.finish(caption)
        return
    await trade.finish()


# QQ 官方适配器把「没有 row 参数的 Keyboard 段」当作一行按钮，所以每行单独 append 一个 Keyboard 段，
# 而不是把全部按钮塞进一段再用 row 平均分行——两者渲染出来的行分组并不一样。
# 每行最多 3 个按钮，避免按钮标签被截断。
async def build_trade_keyboard(user_id: str) -> list[list[Button]]:
    """交易面板键盘（3 行）：买入、卖出各一行，行情导航占一行"""
    prefix = get_command_prefix()
    return [
        [
            # 股数由用户自行填写，所以用 input 类型：点击后把 `/trade buy `、`/trade sell ` 预填进输入框，
            # 用户补上股数（买入还可填 50%、all）再发送；enter 类型会直接发出固定股数，改不了数量。
            Button("input", await lang.text("button.buy", user_id), text=f"{prefix}trade buy "),
            Button("enter", await lang.text("button.buy_all", user_id), text=f"{prefix}trade buy all"),
        ],
        [
            Button("input", await lang.text("button.sell", user_id), text=f"{prefix}trade sell "),
            Button("enter", await lang.text("button.sell_all", user_id), text=f"{prefix}trade sell all"),
        ],
        [
            Button("enter", await lang.text("button.refresh", user_id), text=f"{prefix}trade"),
            Button("enter", await lang.text("button.daily_kline", user_id), text=f"{prefix}trade history"),
            Button("enter", await lang.text("button.rank", user_id), text=f"{prefix}trade rank"),
        ],
    ]


async def build_trade_result_keyboard(user_id: str) -> list[list[Button]]:
    """买入/卖出结果消息的键盘：沿用原来的 5 个按钮（第一行 3 个，第二行 2 个）"""
    prefix = get_command_prefix()
    return [
        [
            Button("input", await lang.text("button.buy", user_id), text=f"{prefix}trade buy "),
            Button("enter", await lang.text("button.buy_all", user_id), text=f"{prefix}trade buy all"),
            Button("input", await lang.text("button.sell", user_id), text=f"{prefix}trade sell "),
        ],
        [
            Button("enter", await lang.text("button.sell_all", user_id), text=f"{prefix}trade sell all"),
            Button("enter", await lang.text("button.refresh", user_id), text=f"{prefix}trade"),
        ],
    ]


async def build_history_keyboard(user_id: str) -> list[list[Button]]:
    """日 K 线历史键盘（2 行）：盈亏排行、五分钟 K 线各占一行"""
    prefix = get_command_prefix()
    return [
        [Button("enter", await lang.text("button.rank", user_id), text=f"{prefix}trade rank")],
        [Button("enter", await lang.text("button.chart_5m", user_id), text=f"{prefix}trade")],
    ]


async def build_rank_keyboard(user_id: str) -> list[list[Button]]:
    """收益排行榜键盘（1 行）：回到交易面板查看行情"""
    prefix = get_command_prefix()
    return [[Button("enter", await lang.text("button.market", user_id), text=f"{prefix}trade")]]


async def send_trade_keyboard(bot: Bot, event: Event, text: str, rows: list[list[Button]]) -> None:
    """发送带键盘的 markdown 消息；``rows`` 的每个元素是一行按钮"""
    message = UniMessage().style(text, "markdown")
    for row in rows:
        message = message.keyboard(*row)
    await message.send(target=event, bot=bot)
    await trade.finish()


async def send_trade_text_with_keyboard(bot: Bot, event: Event, user_id: str, text: str) -> None:
    await send_trade_keyboard(bot, event, text, await build_trade_result_keyboard(user_id))


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
        await send_trade_keyboard(bot, event, text, await build_trade_keyboard(user_id))
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


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


_RANK_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _rank_label(rank: int) -> str:
    medal = _RANK_MEDALS.get(rank)
    return f"{medal} {rank}." if medal else f"{rank}."


def _rate_text(entry: RankingEntry) -> str:
    return f"{_fmt_signed(entry.return_rate * 100)}%"


async def build_rank_text(user_id: str, entries: list[RankingEntry], nicknames: Mapping[str, str]) -> str:
    """构建收益排行榜文本：只展示前若干名，并附带发起者自己的排名"""
    if not entries:
        return await lang.text("rank.empty", user_id)
    size = max(1, config.trade_rank_size)
    visible = entries[:size]
    lines = [
        await lang.text(
            "rank.entry",
            user_id,
            label=_rank_label(entry.rank),
            nickname=nicknames.get(entry.user_id, entry.user_id),
            rate=_rate_text(entry),
            profit=_fmt_signed(entry.profit),
            bought=_fmt_money(entry.total_bought),
            sold=_fmt_money(entry.total_sold),
        )
        for entry in visible
    ]
    blocks = [
        await lang.text("rank.title", user_id),
        await lang.text("rank.metric", user_id),
        "\n".join(lines),
    ]
    if len(entries) > size:
        blocks.append(await lang.text("rank.hidden", user_id, count=size, total=len(entries)))
    me = next((entry for entry in entries if entry.user_id == user_id), None)
    if me is None:
        blocks.append(await lang.text("rank.me_none", user_id))
    else:
        blocks.append(
            await lang.text(
                "rank.me",
                user_id,
                rank=me.rank,
                rate=_rate_text(me),
                profit=_fmt_signed(me.profit),
                bought=_fmt_money(me.total_bought),
                sold=_fmt_money(me.total_sold),
            ),
        )
    return "\n".join(blocks)


async def send_rank_text(bot: Bot, event: Event, user_id: str, entries: list[RankingEntry]) -> None:
    """取排行榜所需昵称（只取上榜者与发起者）并发送文本"""
    nicknames: dict[str, str] = {}
    for entry in entries[: max(1, config.trade_rank_size)]:
        nicknames[entry.user_id] = (await get_user(entry.user_id)).get_nickname()
    me = next((entry for entry in entries if entry.user_id == user_id), None)
    if me is not None and me.user_id not in nicknames:
        nicknames[me.user_id] = (await get_user(me.user_id)).get_nickname()
    text = await build_rank_text(user_id, entries, nicknames)
    if isinstance(bot, QQBot):
        await send_trade_keyboard(bot, event, text, await build_rank_keyboard(user_id))
        return
    await trade.finish(text)


@trade.assign("$main")
async def handle_trade_main(bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    now = now_local()
    async with market_lock:
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


@trade.assign("history")
async def handle_trade_history(bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    now = now_local()
    async with market_lock:
        async with get_session() as session:
            await ensure_market(session, now)
            candles = await load_daily_candles(session, max(1, config.trade_history_candles))
            points = [
                DailyCandlePoint(
                    day=candle.day,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                )
                for candle in candles
            ]
            await session.commit()
    caption = await build_history_caption(user_id, points)
    chart = await render_daily_chart(user_id, points) if points else None
    await send_history_chart(bot, event, user_id, caption, chart)


async def send_rank_image(
    bot: Bot,
    event: Event,
    user_id: str,
    entries: list[RankingEntry],
    image: bytes,
) -> None:
    """发送 ranking 插件绘制的排行榜：QQ 官方用 markdown 图床，其它适配器直接发图"""
    if isinstance(bot, QQBot):
        try:
            text = await create_image_markdown(image, bot)
        except Exception:
            logger.exception("上传收益排行榜图片失败，回退到文本消息")
            await send_rank_text(bot, event, user_id, entries)
            return
        await send_trade_keyboard(bot, event, text, await build_rank_keyboard(user_id))
        return
    try:
        await UniMessage().image(raw=image).send(target=event, bot=bot)
    except Exception:
        logger.exception("发送收益排行榜图片失败，回退到文本消息")
        await send_rank_text(bot, event, user_id, entries)
        return
    await trade.finish()


@trade.assign("rank")
async def handle_trade_rank(bot: Bot, event: Event, user_id: str = get_user_id()) -> None:
    entries = await load_ranking_entries()
    image = await render_ranking_image(entries, user_id)
    if image is None:
        await send_rank_text(bot, event, user_id, entries)
        return
    await send_rank_image(bot, event, user_id, entries, image)


@trade.assign("buy")
async def handle_trade_buy(bot: Bot, event: Event, amount: str, user_id: str = get_user_id()) -> None:
    if not amount.strip():
        await lang.finish("error.usage_buy", user_id)
    now = now_local()
    user = await get_user(user_id, writable=True)
    async with market_lock:
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
    user = await get_user(user_id, writable=True)
    async with market_lock:
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
