import json
from nonebot_plugin_htmlrender import md_to_pic

from nonebot_plugin_broadcast import get_available_groups
from nonebot_plugin_larkuser import get_user
from sqlalchemy import select
from nonebot.adapters import Event, Bot
from nonebot.adapters.qq import Bot as Bot_QQ
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot import on_message, logger

from datetime import datetime, timedelta, timezone
from nonebot_plugin_orm import async_scoped_session, get_session
from nonebot_plugin_alconna import on_alconna, Alconna, Subcommand, Args, UniMessage
from typing import Literal, Sequence
from .lang import lang
from nonebot_plugin_larkutils.file import FileManager
from nonebot_plugin_openai import fetch_message, generate_message
from nonebot_plugin_larkutils import get_user_id, get_group_id, open_file, FileType

from nonebot_plugin_chat.utils.group import parse_message_to_string
from nonebot_plugin_apscheduler import scheduler

from .models import GroupMessage, CatGirlScore
from .chart import render_horizontal_bar_chart


summary = on_alconna(
    Alconna(
        "summary",
        Subcommand("--enable|-e"),
        Subcommand("--disable|-d"),
        Subcommand("--everyday-summary", Args["status", Literal["on", "off"]]),
        Args["limit", int, 200],
        Subcommand("-s|--style", Args["style_type", Literal["default", "broadcast", "bc", "topic"], "default"]),
    )
)
recorder = on_message(priority=3, block=False)
neko_finder = on_alconna(Alconna("neko-finder"))


def get_config() -> FileManager:
    return open_file("disabled_groups.json", FileType.CONFIG, [])


@summary.assign("style")
async def _(
    limit: int,
    style_type: str,
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    await handle_main(limit, session, style_type, user_id, group_id)


def generate_message_string(result: list[GroupMessage] | Sequence[GroupMessage], style: str) -> str:
    messages = ""
    for message in list(result)[::-1]:
        if style in ["broadcast", "bc"]:
            # Format timestamp to include both date and time for broadcast style
            timestamp_str = message.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            messages += f"[{timestamp_str}] [{message.sender_nickname}] {message.message}\n"
        else:
            messages += f"[{message.sender_nickname}] {message.message}\n"
    return messages


@summary.assign("$main")
async def handle_main(
    limit: int,
    session: async_scoped_session,
    style_type: str = "default",
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    style = style_type
    async with get_config() as conf:
        if group_id in conf.data:
            await lang.finish("disabled", user_id)
    result = (
        await session.scalars(
            select(GroupMessage)
            .where(GroupMessage.group_id == group_id)
            .order_by(GroupMessage.id_.desc())
            .limit(limit)
            .order_by(GroupMessage.id_)
        )
    ).all()
    messages = generate_message_string(result, style)
    if style in ["broadcast", "bc"]:
        summary_string = await fetch_broadcast_summary(user_id, messages)
        await summary.finish(summary_string)
    elif style == "topic":
        summary_string = await fetch_message(
            [generate_message(await lang.text("prompt_topic", user_id), "system"), generate_message(messages, "user")],
            identify="Message Summary (Topic)",
        )
        await summary.finish(UniMessage().image(raw=await md_to_pic(summary_string)))
    else:
        summary_string = await fetch_default_summary(user_id, messages)
        await summary.finish(UniMessage().image(raw=await md_to_pic(summary_string)))


async def fetch_broadcast_summary(user_id: str, messages: str) -> str:
    time_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    summary_string = await fetch_message(
        [
            generate_message(await lang.text("prompt2s", user_id, time_str), "system"),
            generate_message(await lang.text("prompt2u", user_id, messages), "user"),
        ],
        identify="Message Summary (Broadcast)",
    )
    return summary_string


async def fetch_default_summary(user_id: str, messages: str) -> str:
    summary_string = await fetch_message(
        [generate_message(await lang.text("prompt", user_id), "system"), generate_message(messages, "user")],
        identify="Message Summary",
    )
    return summary_string


async def get_catgirl_score(message_list: str) -> list[CatGirlScore]:
    """获取由聊天记录总结出来的猫娘分数

    Args:
        message_list: 聊天记录字符串

    Returns:
        list[CatGirlScore]: 猫娘分数列表，每个元素包含 rank、username、score 字段
    """
    return json.loads(
        await fetch_message(
            [
                generate_message(await lang.text("neko.prompt", message_list), "system"),
                generate_message(message_list, "user"),
            ],
            identify="Message Summary (Neko)",
        )
    )


async def clean_recorded_message(session: async_scoped_session) -> None:
    end_time = datetime.now() - timedelta(days=2)
    for item in await session.scalars(select(GroupMessage).where(GroupMessage.timestamp < end_time)):
        await session.delete(item)

from nonebot.typing import T_State
from nonebot_plugin_chat.models import ChatGroup

@recorder.handle()
async def _(event: GroupMessageEvent, session: async_scoped_session, bot: Bot, state: T_State, group_id: str = get_group_id()) -> None:
    async with get_config() as conf:
        if group_id in conf.data:
            await recorder.finish()
    await clean_recorded_message(session)
    if (g := await session.get(ChatGroup, {"group_id": group_id})) and g.enabled:
        uni_msg = UniMessage.of(event.message, bot)
        await uni_msg.attach_reply(event, bot)
        msg = await parse_message_to_string(uni_msg, event, bot, state)
    else:
        msg = event.raw_message
    session.add(GroupMessage(message=msg, sender_nickname=event.sender.nickname, group_id=group_id))
    await session.commit()
    await recorder.finish()


@recorder.handle()
async def _(
    event: Event, session: async_scoped_session, group_id: str = get_group_id(), user_id: str = get_user_id()
) -> None:
    async with get_config() as conf:
        if group_id in conf.data:
            await recorder.finish()
    await clean_recorded_message(session)
    session.add(
        GroupMessage(
            message=event.get_plaintext(), sender_nickname=(await get_user(user_id)).get_nickname(), group_id=group_id
        )
    )
    await session.commit()


@summary.assign("enable")
async def _(bot: Bot, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    if isinstance(bot, Bot_QQ):
        await lang.finish("switch.unsupported", user_id)
    async with get_config() as conf:
        if group_id in conf.data:
            conf.data.remove(group_id)
    await lang.finish("switch.enable", user_id)


@summary.assign("disable")
async def _(user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    async with get_config() as conf:
        if group_id not in conf.data:
            conf.data.append(group_id)
    await lang.finish("switch.disable", user_id)


@summary.assign("everyday-summary")
async def _(status: str, bot: Bot, user_id: str = get_user_id(), group_id: str = get_group_id()) -> None:
    if isinstance(bot, Bot_QQ):
        await lang.finish("switch.unsupported", user_id)
    everyday_config = open_file("everyday_summary_config.json", FileType.CONFIG, [])
    async with everyday_config as conf:
        if status == "on":
            if group_id not in conf.data:
                conf.data.append(group_id)
            await lang.finish("everyday_summary.enable", user_id)
        else:
            if group_id in conf.data:
                conf.data.remove(group_id)
            await lang.finish("everyday_summary.disable", user_id)


def get_everyday_summary_config() -> FileManager:
    """Get the config file for everyday summary feature"""
    return open_file("everyday_summary_config.json", FileType.CONFIG, [])


async def send_daily_summary_to_group(group_id: str) -> None:
    """Send daily summary to a specific group"""
    # Get all messages for the group from the last 24 hours
    async with get_session() as session:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=1)

        result = await session.scalars(
            select(GroupMessage)
            .where(GroupMessage.group_id == group_id)
            .where(GroupMessage.timestamp >= start_time)
            .where(GroupMessage.timestamp <= end_time)
            .order_by(GroupMessage.id_)
        )
        messages = list(result.all())[::-1]

        if not messages:
            return

        # Generate message string
        messages_str = generate_message_string(list(messages), "broadcast")

        # Get a user ID from the group for language processing
        # We'll use the first message's sender as the user ID
        user_id = messages[0].sender_nickname

    # Get bots to send the message
    target_group_id = group_id.split("_", 1)[1]
    if bot_list := (await get_available_groups()).get(target_group_id):
        bot = bot_list[0]
    else:
        return

    summary_string = await fetch_message(
        [
            generate_message(await lang.text("prompt_everyday_summary", user_id, datetime.now().isoformat()), "system"),
            generate_message(messages_str, "user"),
        ],
        identify="Message Summary (Daily)",
    )

    # Render the markdown template
    try:
        image_bytes = await md_to_pic(summary_string)
        await bot.send_group_msg(
            group_id=int(target_group_id), message=await UniMessage().image(raw=image_bytes).export(bot)
        )
    except Exception as e:
        logger.exception(e)


@scheduler.scheduled_job("cron", hour=6, minute=0, id="daily_message_summary")
# @on_command("daily_message_summary").handle()
async def send_daily_message_summary() -> None:
    """Send daily message summary to all groups that have enabled this feature"""
    # Get the list of groups that have enabled everyday summary
    async with get_everyday_summary_config() as config:
        enabled_groups = config.data

    # Send summary to each enabled group
    for group_id in enabled_groups:
        try:
            await send_daily_summary_to_group(group_id)
        except Exception as e:
            logger.exception(e)


@neko_finder.handle()
async def handle_neko_finder(
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    """处理 .neko-finder 指令"""
    # 获取广播风格的消息列表
    result = (
        await session.scalars(select(GroupMessage).where(GroupMessage.group_id == group_id).order_by(GroupMessage.id_))
    ).all()
    messages = generate_message_string(list(result), "broadcast")

    # 调用 get_catgirl_score 函数分析消息数据
    catgirl_scores = await get_catgirl_score(messages)

    # 使用matplotlib生成横向柱状图
    image_bytes = await render_horizontal_bar_chart(catgirl_scores, user_id)

    # 发送图片
    await neko_finder.finish(UniMessage().image(raw=image_bytes))
