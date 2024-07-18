from datetime import datetime
from nonebot_plugin_apscheduler import scheduler
from nonebot import logger
from nonebot.message import event_preprocessor
from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException

from .config import config


sessions: dict[str, str] = {}


@event_preprocessor
async def _(bot: Bot, event: Event) -> None:
    try:
        session_id = event.get_session_id()
    except ValueError:
        return
    if session_id not in sessions:
        sessions[session_id] = bot.self_id
        logger.info(f"已将会话 {session_id} 分配给 {bot.self_id}")
    elif sessions[session_id] != bot.self_id:
        raise IgnoredException(f"此群组已分配给帐号 {session_id}")


@scheduler.scheduled_job("cron", minute=config.bots_session_clear_time, id="remove_expired_email")
async def _() -> None:
    sessions.clear()
