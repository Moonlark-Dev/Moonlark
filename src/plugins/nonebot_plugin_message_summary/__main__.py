import json
from nonebot_plugin_htmlrender import md_to_pic

from nonebot_plugin_broadcast import get_available_groups
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_render import render_template
from nonebot_plugin_render.render import generate_render_keys
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

from .models import GroupMessage, CatGirlScore, DebateAnalysis
from .chart import render_horizontal_bar_chart
from .ai_utils import generate_message_string

# This file is kept for backward compatibility and scheduler tasks
# Most logic has been moved to matcher.py, ai_utils.py, render_utils.py

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
        messages_str = await generate_message_string(list(messages), "broadcast")

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
        msg = await UniMessage().image(raw=image_bytes).export(bot)
        await bot.send_group_msg(
            group_id=int(target_group_id), message=msg # type: ignore
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
