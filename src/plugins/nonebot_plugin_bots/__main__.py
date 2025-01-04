import time
from nonebot.adapters.onebot.v11.bot import Bot as V11Bot
from nonebot.adapters.onebot.v12.bot import Bot as V12Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_apscheduler import scheduler
from nonebot import logger
from nonebot.message import event_preprocessor
from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException, ActionFailed
from nonebot import get_bot
from nonebot import get_app
from fastapi import FastAPI, Request
from typing import cast

from .config import config
from .types import BotStatus

sessions: dict[str, tuple[str, float]] = {}


@cast(FastAPI, get_app()).get("/api/bots")
async def bots_status(_: Request) -> dict[str, BotStatus]:
    bots: dict[str, BotStatus] = {}
    for code, user_id in config.bots_list.items():
        try:
            bot = get_bot(user_id)
        except KeyError:
            bots[code] = {
                "user_id": user_id,
                "online": False
            }
            continue
        try:
            if isinstance(bot, QQBot):
                good = await bot.ready()
            elif isinstance(bot, V11Bot):
                good = (await bot.get_status())["good"]
            elif isinstance(bot, V12Bot):
                good = (await bot.get_status())["good"]
            else:
                good = False
        except ActionFailed:
            good = False
        bots[code] = {
            "user_id": user_id,
            "adapter_name": bot.adapter.get_name(),
            "online": True,
            "good": good
        }
    return bots


@event_preprocessor
async def _(bot: Bot, event: Event) -> None:
    try:
        session_id = event.get_session_id()
    except ValueError:
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

