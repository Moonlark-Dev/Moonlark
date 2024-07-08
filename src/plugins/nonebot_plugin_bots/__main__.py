from datetime import datetime
from nonebot_plugin_apscheduler import scheduler
from nonebot import logger
from nonebot.message import event_preprocessor
from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException

from .typing import SessionData
from .config import config


sessions: dict[str, SessionData] = {}


@event_preprocessor
async def _(bot: Bot, event: Event) -> None:
    try:
        session_id = event.get_session_id()
    except Exception:
        return
    if session_id not in sessions:
        sessions[session_id] = {"assign_time": datetime.now(), "bot_id": bot.self_id}
        logger.info(f"已将会话 {session_id} 分配给 {bot.self_id}，有效 {config.bot_assign_effective_time / 60} 分钟")
    elif sessions[session_id]["bot_id"] != bot.self_id:
        raise IgnoredException(f"此群组已分配给帐号 {session_id}")


@scheduler.scheduled_job("cron", minute="*", id="remove_expired_email")
async def _() -> None:
    expired_session = []
    for session_id, session_data in sessions.items():
        if (datetime.now() - session_data["assign_time"]).total_seconds() > config.bot_assign_effective_time:
            expired_session.append(session_id)
    for session_id in expired_session:
        del sessions[session_id]
        logger.info(f"已移除会话 {session_id}，因不在有效期内")
