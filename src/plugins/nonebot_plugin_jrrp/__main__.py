from __future__ import annotations

from typing import Any, Optional
from datetime import date
from statistics import mean
from logging import getLogger

from nonebot.adapters import Bot, Event
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq.event import C2CMessageCreateEvent
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import create_image_markdown, get_user_id
from nonebot_plugin_larkutils.command import get_command_prefix
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_schedule.utils import complete_schedule
from nonebot_plugin_chat.core.session import post_group_event
from nonebot_plugin_larkuser.utils.nickname import get_nickname
from nonebot_plugin_alconna import Args, Alconna, Button, Subcommand, UniMessage, on_alconna
from nonebot_plugin_larkutils.jrrp import get_luck_value, reroll_luck_value, get_luck_value_with_reroll_count

from .lang import lang
from .config import config
from .trend import render_luck_trend_chart
from .card import render_luck_card
from .utils import get_luck_trend, save_luck_trend, get_luck_message

logger = getLogger(__name__)

alc = Alconna(
    "jrrp",
    Subcommand("--rank|-r|r"),
    Subcommand("--rank-r|-rr|rr"),
    Subcommand("reroll"),
    Subcommand("--trend|-t|t", Args["days?", int, 7]),
)
jrrp = on_alconna(alc)


def _extract_msg_id(result: Any) -> str | None:
    """从 send 返回值中提取消息 ID."""
    if isinstance(result, dict):
        return result.get("message_id")
    if isinstance(result, list) and result:
        item = result[0]
        return item.get("message_id") if isinstance(item, dict) else getattr(item, "message_id", None)
    return getattr(result, "message_id", None)


def is_group_event(event: Optional[Event]) -> bool:
    """群聊事件的 session id 以 group_ 开头（QQ 官方与 OneBot 都是这个约定）。"""
    return event is not None and event.get_session_id().startswith("group_")


def get_qq_at_user(event: Optional[Event]) -> str:
    """构建 QQ 官方机器人 markdown 卡片开头的 @ 前缀。

    ``<qqbot-at-user>`` 只接受适配器原生 ID（群聊里是 member_openid），因此这里取
    ``event.get_user_id()``，而不是 larkutils 的主账号 ID——主账号 ID 是 QQ 号，
    在开放平台的 openid 体系里并不存在，@ 出来会是一个无效用户。

    C2C 单聊不支持该语法（发送会报 ActionFailed），返回空串跳过 @。
    """
    if event is None or isinstance(event, C2CMessageCreateEvent):
        return ""
    return f'<qqbot-at-user id="{event.get_user_id()}" />'


async def build_jrrp_keyboard(user_id: str) -> list[Button]:
    """jrrp 的「幸运星 / 倒霉蛋 / 重新抽取」键盘按钮。"""
    prefix = get_command_prefix()
    return [
        Button("enter", await lang.text("button.lucky_star", user_id), text=f"{prefix}jrrp r"),
        Button("enter", await lang.text("button.unlucky_one", user_id), text=f"{prefix}jrrp rr"),
        Button("enter", await lang.text("button.reroll", user_id), text=f"{prefix}jrrp reroll"),
    ]


async def build_jrrp_message(bot: Bot, user_id: str, event: Optional[Event] = None) -> str | UniMessage:
    """构建 jrrp 的纯文本消息（人品卡渲染或发送失败时回退用）。

    QQ 官方机器人: 在最前面附加 @ (qqbot-at-user)，并附带键盘按钮。
    带 keyboard 的消息使用 UniMessage.send 发送，且需在末尾单独调用
    matcher.finish 结束处理器；其余平台: 返回纯文本, 由 matcher.send
    (at_sender=True) 附加 @。
    """
    if not isinstance(bot, QQBot):
        return await get_luck_message(user_id)
    return (
        UniMessage()
        .style(f"{get_qq_at_user(event)}{await get_luck_message(user_id)}", "markdown")
        .keyboard(*await build_jrrp_keyboard(user_id))
    )


async def build_jrrp_card_message(bot: Bot, user_id: str, card: bytes, event: Optional[Event] = None) -> UniMessage:
    """构建人品卡消息。

    QQ 官方机器人: 先把卡片上传到素材库，再以 markdown 图片发送，并保留键盘；
    其余平台: 返回图片消息，由调用方用 matcher.send(at_sender=True) 发送。
    """
    if not isinstance(bot, QQBot):
        return UniMessage().image(raw=card)
    markdown_image = await create_image_markdown(card, bot)
    return (
        UniMessage()
        .style(f"{get_qq_at_user(event)}{markdown_image}", "markdown")
        .keyboard(*await build_jrrp_keyboard(user_id))
    )


async def try_render_luck_card(user_id: str, luck_value: int) -> Optional[bytes]:
    """渲染人品卡；失败时只记日志并让调用方回退文本，不影响指令本身。"""
    try:
        return await render_luck_card(user_id, luck_value)
    except Exception:
        logger.exception("渲染人品卡失败，回退到文本消息")
        return None


async def send_jrrp_text(bot: Bot, user_id: str, event: Optional[Event]) -> str | None:
    message = await build_jrrp_message(bot, user_id, event)
    if isinstance(message, UniMessage):
        receipt = await message.send(target=event, bot=bot)
        return _extract_msg_id(receipt.msg_ids)
    return _extract_msg_id(await jrrp.send(message, at_sender=is_group_event(event)))


async def send_jrrp_card(bot: Bot, user_id: str, event: Event, card: bytes) -> str | None:
    message = await build_jrrp_card_message(bot, user_id, card, event)
    if isinstance(bot, QQBot):
        receipt = await message.send(target=event, bot=bot)
        return _extract_msg_id(receipt.msg_ids)
    return _extract_msg_id(await jrrp.send(await message.export(), at_sender=is_group_event(event)))


async def process_jrrp_command(group_id: str, user_id: str, bot: Bot, event: Event) -> None:
    luck_value = await get_luck_value(user_id)

    # 记录今日人品走势
    _, reroll_count = await get_luck_value_with_reroll_count(user_id)
    await save_luck_trend(user_id, luck_value, reroll_count)

    event_text = await lang.text("chat_event", user_id, await get_nickname(user_id, bot, event), luck_value)

    msg_id = None
    sent = False
    card = await try_render_luck_card(user_id, luck_value)
    if card is not None:
        try:
            msg_id = await send_jrrp_card(bot, user_id, event, card)
            sent = True
        except Exception:
            logger.exception("发送人品卡失败，回退到文本消息")
    if not sent:
        msg_id = await send_jrrp_text(bot, user_id, event)

    if msg_id:
        event_text += f"\n[供回复的消息ID：{msg_id}]"

    await post_group_event(
        group_id,
        event_text,
        "probability",
    )
    await jrrp.finish()


@jrrp.assign("$main")
async def _main_handler(bot: Bot, event: Event, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    await complete_schedule(user_id, "jrrp")
    await process_jrrp_command(group_id, user_id, bot, event)


@jrrp.assign("reroll")
async def _reroll_handler(bot: Bot, event: Event, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    """重新计算今日人品值."""
    max_reroll_count = config.jrrp_reroll_max_count

    # 获取用户数据
    user = await get_user(user_id, writable=True)

    # 获取当前人品值和已重算次数
    current_luck, reroll_count = await get_luck_value_with_reroll_count(user_id)

    # 检查是否已达到重算上限
    if reroll_count >= max_reroll_count:
        await lang.finish("reroll.max_reached", user_id, max_reroll_count, at_sender=True)

    # 计算本次重算所需费用
    cost = config.jrrp_reroll_base_cost * (reroll_count + 1)

    # 余额检查与扣费在同一次加锁修改里完成，避免并发时白嫖一次重算
    if not await user.use_vimcoin(cost):
        await lang.finish("reroll.insufficient_vimcoin", user_id, cost, round(user.get_vimcoin(), 2), at_sender=True)

    # 重新计算人品值
    result = await reroll_luck_value(user_id, max_reroll_count)
    if result is None:
        if current_luck > 100:
            await lang.finish("reroll.beyond_perfect", user_id, at_sender=True)
        elif current_luck == 100:
            await lang.finish("reroll.perfect_luck", user_id, at_sender=True)
        await lang.finish("reroll.max_reached", user_id, max_reroll_count, at_sender=True)

    new_luck, new_reroll_count = result

    # 记录重算后的人品走势
    await save_luck_trend(user_id, new_luck, new_reroll_count)

    # 发送结果
    await lang.send("reroll.success", user_id, new_reroll_count, max_reroll_count, cost, at_sender=True)

    await process_jrrp_command(group_id, user_id, bot, event)


@jrrp.assign("trend")
async def _trend_handler(
    user_id: str = get_user_id(),
    days: int = 7,
) -> None:
    """查看人品走势图（默认 7 天，可指定 30 天）."""
    await render_trend(user_id, days)


async def render_trend(user_id: str, days: int) -> None:
    """渲染人品走势图."""
    records = await get_luck_trend(user_id, days)

    if not records:
        # 没有历史数据，尝试获取今天的数据
        try:
            luck_value = await get_luck_value(user_id)
            await save_luck_trend(user_id, luck_value, 0)
            records = await get_luck_trend(user_id, days)
        except (ValueError, OSError) as exc:
            logger.warning("获取今日人品值用于走势图失败: %s", exc)

    if not records:
        await lang.finish("trend.no_history", user_id, at_sender=True)

    dates_list: list[date] = [r.record_date for r in records]
    values_list: list[int] = [r.luck_value for r in records]
    avg = mean(values_list)

    image_bytes = await render_luck_trend_chart(user_id, dates_list, values_list, days, avg)
    await jrrp.finish(UniMessage().image(raw=image_bytes))
