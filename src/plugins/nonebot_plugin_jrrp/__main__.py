from __future__ import annotations

from logging import getLogger
from statistics import mean
from typing import TYPE_CHECKING, Any

from nonebot_plugin_alconna import Alconna, Args, Subcommand, UniMessage, on_alconna
from nonebot_plugin_chat.core.session import post_group_event
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkuser.utils.nickname import get_nickname
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_larkutils.group import get_group_id
from nonebot_plugin_larkutils.jrrp import get_luck_value, get_luck_value_with_reroll_count, reroll_luck_value
from nonebot_plugin_schedule.utils import complete_schedule

from .lang import lang
from .trend import render_luck_trend_chart
from .utils import get_luck_message, get_luck_trend, save_luck_trend

if TYPE_CHECKING:
    from datetime import date

    from nonebot.adapters import Bot, Event

logger = getLogger(__name__)

alc = Alconna(
    "jrrp",
    Subcommand("--rank|-r|r"),
    Subcommand("--rank-r|-rr|rr"),
    Subcommand("reroll"),
    Subcommand("--trend|-t|t", Args["days?", int, 7]),
)
jrrp = on_alconna(alc)


async def _extract_msg_id(result: Any) -> str | None:
    """从 send 返回值中提取消息 ID。"""
    if isinstance(result, dict):
        return result.get("message_id")
    if isinstance(result, list) and result:
        item = result[0]
        return item.get("message_id") if isinstance(item, dict) else getattr(item, "message_id", None)
    return getattr(result, "message_id", None)


async def process_jrrp_command(group_id: str, user_id: str, bot: Bot, event: Event) -> None:
    luck_value = await get_luck_value(user_id)

    # 记录今日人品走势
    _, reroll_count = await get_luck_value_with_reroll_count(user_id)
    await save_luck_trend(user_id, luck_value, reroll_count)

    event_text = await lang.text("chat_event", user_id, await get_nickname(user_id, bot, event), luck_value)

    result = await jrrp.send(await get_luck_message(user_id), at_sender=True)
    msg_id = await _extract_msg_id(result)

    if msg_id:
        event_text += f"\n[供回复的消息ID：{msg_id}]"

    await post_group_event(
        group_id,
        event_text,
        "probability",
    )
    await jrrp.finish()


@jrrp.assign("$main")
async def _(bot: Bot, event: Event, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    await complete_schedule(user_id, "jrrp")
    await process_jrrp_command(group_id, user_id, bot, event)


@jrrp.assign("reroll")
async def _(bot: Bot, event: Event, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    """重新计算今日人品值"""
    from .config import config

    max_reroll_count = config.jrrp_reroll_max_count

    # 获取用户数据
    user = await get_user(user_id)

    # 获取当前人品值和已重算次数
    current_luck, reroll_count = await get_luck_value_with_reroll_count(user_id)

    # 检查是否已达到重算上限
    if reroll_count >= max_reroll_count:
        await lang.finish("reroll.max_reached", user_id, max_reroll_count, at_sender=True)
        return

    # 计算本次重算所需费用
    cost = config.jrrp_reroll_base_cost * (reroll_count + 1)

    # 检查用户是否有足够的 vimcoin
    if not await user.has_vimcoin(cost):
        await lang.finish("reroll.insufficient_vimcoin", user_id, cost, round(user.get_vimcoin(), 2), at_sender=True)
        return

    # 扣除 vimcoin
    await user.use_vimcoin(cost)

    # 重新计算人品值
    result = await reroll_luck_value(user_id, max_reroll_count)
    if result is None:
        if current_luck > 100:
            await lang.finish("reroll.beyond_perfect", user_id, at_sender=True)
        elif current_luck == 100:
            await lang.finish("reroll.perfect_luck", user_id, at_sender=True)
        else:
            await lang.finish("reroll.max_reached", user_id, max_reroll_count, at_sender=True)
        return

    new_luck, new_reroll_count = result

    # 记录重算后的人品走势
    await save_luck_trend(user_id, new_luck, new_reroll_count)

    # 发送结果
    await lang.send("reroll.success", user_id, new_reroll_count, max_reroll_count, cost, at_sender=True)

    await process_jrrp_command(group_id, user_id, bot, event)


@jrrp.assign("trend")
async def _(
    user_id: str = get_user_id(),
    days: int = 7,
) -> None:
    """查看人品走势图（默认 7 天，可指定 30 天）"""
    await render_trend(user_id, days)


async def render_trend(user_id: str, days: int) -> None:
    """渲染人品走势图"""
    records = await get_luck_trend(user_id, days)

    if not records:
        # 没有历史数据，尝试获取今天的数据
        try:
            luck_value = await get_luck_value(user_id)
            await save_luck_trend(user_id, luck_value, 0)
            records = await get_luck_trend(user_id, days)
        except Exception as exc:
            logger.warning("获取今日人品值用于走势图失败: %s", exc)

    if not records:
        await lang.finish("trend.no_history", user_id, at_sender=True)

    dates_list: list[date] = [r.record_date for r in records]
    values_list: list[int] = [r.luck_value for r in records]
    avg = mean(values_list)

    image_bytes = await render_luck_trend_chart(user_id, dates_list, values_list, days, avg)
    await jrrp.finish(UniMessage().image(raw=image_bytes))
