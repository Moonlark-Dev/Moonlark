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
from typing import Optional, cast

from nonebot_plugin_larkutils import get_group_id
from .config import config
from .types import BotStatus, OnlineBotStatus

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
    return OnlineBotStatus(
        user_id=user_id,
        adapter_name=bot.adapter.get_name(),
        online=True,
        good=bool(good),
        nickname=nickname,
    )
    # {
    #     "user_id": user_id,
    #     "adapter_name": bot.adapter.get_name(),
    #     "online": True,
    #     "good": good,
    #     "nickname": nickname,
    # }


async def is_bot_online(bot_id: str) -> bool:
    status = await get_bot_status(bot_id)
    return bool(status["online"] and status.get("good"))


@cast(FastAPI, get_app()).get("/api/bots")
async def bots_status(_: Request) -> dict[str, BotStatus]:
    bots: dict[str, BotStatus] = {}
    for code, user_id in config.bots_list.items():
        bots[code] = await get_bot_status(user_id)
    return bots


def assign_session(session_id: str, bot_id: str) -> None:
    sessions[session_id] = bot_id, time.time()
    logger.info(f"已将会话 {session_id} 分配给 {bot_id}")


# async def process_to_me_message(event: Event, bot: Bot, session_id: str) -> None:
#     message = event.get_message()
#     for segment in message:
#         if segment.type == "at":
#             user_id = str(segment.get("user_id"))
#             if user_id in config.bots_list.keys() and session_id in sessions and sessions[session_id] != user_id:
#                 segment.user_id = bot.self_id
#                 if hasattr(event, "to_me"):
#                     event.to_me = True
#                 assign_session(session_id, bot.self_id)

from nonebot.adapters.onebot.v11.event import PokeNotifyEvent

# async def process_to_me_event(event: Event, bot: Bot, session_id: str) -> None:
#     if isinstance(event, PokeNotifyEvent):
#         target_id = str(event.target_id)
#     else:
#         return
#     if target_id in config.bots_list.keys() and session_id in sessions and sessions[session_id] != target_id:
#         assign_session(session_id, bot.self_id)
#         event.is_tome = lambda cls: True

from nonebot.adapters import Message


class ToMeProcessor:

    def __init__(self, bot: Bot, event: Event, session_id: str) -> None:
        self.bot = bot
        self.event = event
        self.session_id = session_id
        self.to_me = False

    def process_to_me_event(self) -> None:
        if self.event.is_tome():
            assign_session(self.session_id, self.bot.self_id)
            return
        if (msg := self.get_event_message()) is not None:
            self.process_message_event(msg)
        elif isinstance(self.event, PokeNotifyEvent):
            self.process_poke()
        if self.to_me:
            assign_session(self.session_id, self.bot.self_id)
            self.event.is_tome = lambda _: True  # type: ignore

    def get_event_message(self) -> Optional[Message]:
        try:
            return self.event.get_message()
        except ValueError:
            return None

    def process_message_event(self, message: Message) -> None:
        for segment in message:
            if segment.type == "at":
                user_id = str(segment.get("user_id"))
                if user_id in config.bots_list.keys():
                    self.to_me = True
                    segment["user_id"] = self.bot.self_id

    def process_poke(self) -> None:
        event = cast(PokeNotifyEvent, self.event)
        target_id = str(event.target_id)
        if target_id in config.bots_list.keys():
            event.target_id = int(self.bot.self_id)
            self.to_me = True


@event_preprocessor
async def _(bot: Bot, event: Event, session_id: str = get_group_id()) -> None:
    try:
        user_id = event.get_user_id()
    except ValueError:
        return
    if user_id in get_bots().keys():
        raise IgnoredException("忽略自身消息")
    ToMeProcessor(bot, event, session_id).process_to_me_event()
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
