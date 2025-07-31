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

from nonebot import get_bots

sessions: dict[str, tuple[str, float]] = {}


async def get_bot_status(user_id: str) -> BotStatus:
    try:
        bot = get_bot(user_id)
    except KeyError:
        return {"user_id": user_id, "online": False}
    try:
        if isinstance(bot, QQBot):
            good = bot.ready
            nickname = bot.self_info.username
        elif isinstance(bot, V11Bot):
            good = (await bot.get_status())["good"]
            nickname = (await bot.get_login_info()).get("nickname")
        elif isinstance(bot, V12Bot):
            good = (await bot.get_status())["good"]
            nickname = (await bot.get_self_info())["user_name"]
        else:
            good = False
            nickname = None
    except ActionFailed:
        good = False
        nickname = None
    return {
        "user_id": user_id,
        "adapter_name": bot.adapter.get_name(),
        "online": True,
        "good": good,
        "nickname": nickname,
    }


async def is_bot_online(bot_id: str) -> bool:
    status = await get_bot_status(bot_id)
    return status["online"] and status["good"]


@cast(FastAPI, get_app()).get("/api/bots")
async def bots_status(_: Request) -> dict[str, BotStatus]:
    bots: dict[str, BotStatus] = {}
    for code, user_id in config.bots_list.items():
        bots[code] = await get_bot_status(user_id)
    return bots


def assign_session(session_id: str, bot_id: str) -> None:
    sessions[session_id] = bot_id, time.time()
    logger.info(f"已将会话 {session_id} 分配给 {bot_id}")


async def process_to_me_message(event: Event, bot: Bot, session_id: str) -> None:
    message = event.get_message()
    for segment in message:
        if segment.type == "at":
            user_id = segment.get("user_id")
            if user_id in config.bots_list.keys() and session_id in sessions and sessions[session_id] != user_id:
                if await is_bot_online(user_id):
                    assign_session(session_id, user_id)
                else:
                    segment.user_id = bot.self_id
                    assign_session(session_id, bot.self_id)
                return



@event_preprocessor
async def _(bot: Bot, event: Event) -> None:
    if event.get_user_id() in get_bots().keys():
        raise IgnoredException("忽略自身消息")
    try:
        session_id = event.get_session_id()
    except ValueError:
        return
    try:
        await process_to_me_message(event, bot, session_id)
    except ValueError:
        pass
    if session_id in sessions and sessions[session_id][0] != bot.self_id:
        raise IgnoredException(f"此群组已分配给帐号 {session_id}")
    assign_session(session_id, bot.self_id)


@scheduler.scheduled_job("cron", minute="*", id="remove_expired_email")
async def _() -> None:
    expired_sessions = []
    for key, value in sessions.items():
        if time.time() - value[1] >= config.bots_session_remain or not await is_bot_online(value[0]):
            expired_sessions.append(key)
            logger.debug(f"将回收过期或不可用会话: {key} ({value})")
    for key in expired_sessions:
        sessions.pop(key)
