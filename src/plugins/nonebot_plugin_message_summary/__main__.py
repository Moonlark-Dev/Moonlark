from datetime import datetime, timedelta

from nonebot import logger
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_broadcast import get_available_groups
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larkutils import FileType, open_file
from nonebot_plugin_larkutils.file import FileManager
from nonebot_plugin_openai import fetch_message, generate_message
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .ai_utils import extract_mvp_from_summary, generate_message_string
from .lang import lang
from .models import GroupMessage, MVPRecord

# This file is kept for backward compatibility and scheduler tasks
# Most logic has been moved to matcher.py, ai_utils.py, render_utils.py


def get_everyday_summary_config() -> FileManager:
    """Get the config file for everyday summary feature"""
    return open_file("everyday_summary_config.json", FileType.CONFIG, [])


async def send_daily_summary_to_group(group_id: str) -> None:
    """Send daily summary to a specific group"""
    async with get_session() as session:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=1)

        result = await session.scalars(
            select(GroupMessage)
            .where(GroupMessage.group_id == group_id)
            .where(GroupMessage.timestamp >= start_time)
            .where(GroupMessage.timestamp <= end_time)
            .order_by(GroupMessage.id_),
        )
        messages = list(result.all())[::-1]

        if not messages:
            return

        messages_str = await generate_message_string(list(messages), "broadcast")

        user_id = messages[0].sender_nickname

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

    try:
        image_bytes = await md_to_pic(summary_string)
        msg = await UniMessage().image(raw=image_bytes).export(bot)
        await bot.send_group_msg(group_id=int(target_group_id), message=msg)
    except Exception as e:
        logger.exception(e)

    mvp_data = await extract_mvp_from_summary(summary_string)
    if mvp_data:
        mvp_nickname, _ = mvp_data
        async with get_session() as session:
            mvp_result = await session.scalars(
                select(GroupMessage)
                .where(GroupMessage.group_id == group_id)
                .where(GroupMessage.timestamp >= start_time)
                .where(GroupMessage.timestamp <= end_time)
                .where(GroupMessage.sender_nickname == mvp_nickname),
            )
            mvp_message = mvp_result.first()
            if mvp_message and mvp_message.user_id:
                mvp_record = await session.get(MVPRecord, {"user_id": mvp_message.user_id, "group_id": group_id})
                if mvp_record:
                    mvp_record.mvp_count += 1
                else:
                    session.add(MVPRecord(user_id=mvp_message.user_id, group_id=group_id, mvp_count=1))
                await session.commit()


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
