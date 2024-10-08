import time
from nonebot_plugin_apscheduler import scheduler
from nonebot import logger
from nonebot.message import event_preprocessor
from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException

from .config import config


sessions: dict[str, tuple[str, float]] = {}


@event_preprocessor
async def _(bot: Bot, event: Event) -> None:
    try:
        session_id = event.get_session_id()
    except ValueError:
        logger.warning(traceback.format_exc())
        return
    if session_id not in sessions:
        sessions[session_id] = bot.self_id, time.time()
        logger.info(f"已将会话 {session_id} 分配给 {bot.self_id}")
    elif sessions[session_id][0] != bot.self_id:
        raise IgnoredException(f"此群组已分配给帐号 {session_id}")
    else:
        sessions[session_id] = bot.self_id, time.time()


@scheduler.scheduled_job("cron", minute="*", id="remove_expired_email")
async def _() -> None:
    expired_sessions = []
    for key, value in sessions.items():
        if time.time() - value[1] >= config.bots_session_remain:
            expired_sessions.append(key)
            logger.debug(f"将回收过期会话: {key} ({value})")
    for key in expired_sessions:
        sessions.pop(key)
