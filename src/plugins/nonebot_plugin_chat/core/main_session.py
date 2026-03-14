import asyncio
import json
import re
import traceback
from nonebot import get_bot
from nonebot.compat import type_validate_python
from datetime import datetime, timedelta
from enum import Enum
from typing import Literal, Optional, Union

from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_chat.core.proactive_chat import send_proactive_private_message
from nonebot_plugin_chat.models import PrivateChatSession
from nonebot_plugin_chat.utils.instant_mem import get_instant_memories
from nonebot_plugin_larkuser.utils.user import get_user
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from ..lang import lang
from nonebot_plugin_chat.types import MoodEnum
from nonebot_plugin_chat.utils.status_manager import StatusManager
from nonebot_plugin_openai.utils.chat import MessageFetcher
from nonebot_plugin_openai.utils.message import generate_message
from pydantic import BaseModel

class StateEnum(Enum):
    SLEEPING = "sleeping"
    ACTIVATE = "activate"
    BORED = "bored"
    BUSY = "busy"



class SkipAction(BaseModel):
    type: Literal["skip"]

class CustomAction(BaseModel):
    type: Literal["do"]
    information: str
    estimated_time: int

class GetFriendsAction(BaseModel):
    type: Literal["get_friends"]

class SendPrivateMsgAction(BaseModel):
    type: Literal["send_private_message"]
    target_nickname: str
    subject: str

class RestAction(BaseModel):
    type: Literal["sleep"]
    time: int

BoredAction = Union[SkipAction, CustomAction, GetFriendsAction, SendPrivateMsgAction, RestAction]

class BoredActionResponse(BaseModel):
    response: BoredAction





class MainSession:

    def __init__(self, last_activate_time: datetime, lang_str: str = "zh_hans") -> None:
        self.lang_str = lang_str
        self.last_activate_time = last_activate_time
        self.boredom = 0.0
        self.action_history: list[tuple[datetime, BoredAction]] = []
        self.boredom_processor_lock = asyncio.Lock()
        self.state = StateEnum.ACTIVATE
        self.status_manager = StatusManager()
        self.state_until = None
        scheduler.scheduled_job("cron", minutes="*", id="chat_heartbeat")(self.process_timer)


    async def process_timer(self) -> None:
        match self.state:
            
            case StateEnum.ACTIVATE:
                self.boredom += 1
                if self.boredom >= 25 and self.status_manager.set_mood(MoodEnum.BORED)[0]:
                    self.state = StateEnum.BORED
                    self.boredom = 0.0

            case StateEnum.BORED:
                asyncio.create_task(self.process_boredom())

        if self.state_until is not None and datetime.now() > self.state_until:
            self.state = StateEnum.ACTIVATE
            self.state_until = None
            self.boredom = 0.0

    def record_activate(self, important: bool = False) -> None:
        self.last_activate_time = datetime.now()
        if important:
            self.boredom -= 10
        else:
            self.boredom -= 2
        self.boredom = max(0, self.boredom)

    async def get_action_str(self, action: BoredAction) -> Optional[str]:
        match action.type:
            case "send_private_message":
                return await lang.text("main_session.history.send_private_message", self.lang_str, action.target_nickname, action.subject)
            case "sleep":
                return await lang.text("main_session.history.sleep", self.lang_str, action.time)
            case "do":
                return await lang.text("main_session.history.do", self.lang_str, action.information, action.estimated_time)

    async def generate_system_prompt(self) -> str:
        mood = self.status_manager.get_status()
        state_str = await lang.text("prompt_group.state", self.lang_str, await lang.text(f"status.mood.{mood[0].value}", self.lang_str), self.status_manager.get_mood_retention(), mood[1])
        return await lang.text(
            "main_session.prompt",
            self.lang_str, 
            await lang.text("prompt_group.identify", self.lang_str),
            await lang.text("prompt_group.time", self.lang_str, datetime.now().isoformat()),
            state_str,
            "\n".join([await lang.text("prompt_group.instant_mem", self.lang_str, mem["category"], mem["expire_level"], mem["create_time"].strftime("%Y-%m-%d %H:%M:%S"), mem["content"]) for mem in get_instant_memories()]),
            "\n".join([f"[{dt.strftime('%Y-%m-%d %H:%M:%S')}] {s}" for dt, item in self.action_history[-20:] if (s := await self.get_action_str(item))])
        )

    async def process_boredom(self) -> None:
        if self.boredom_processor_lock.locked():
            return
        async with self.boredom_processor_lock:
            fetcher = await MessageFetcher.create(
                [
                    generate_message(await self.generate_system_prompt(), "system"),
                    generate_message(await lang.text("main_session.prompt_user", self.lang_str), "user"),
                ],
                identify="Chat - Bored",
                reasoning_effort="medium"
            )
            async for msg in fetcher.fetch_message_stream():
                message = re.sub(r"`{1,3}([a-zA-Z0-9]+)?", "", msg)
                try:
                    response = type_validate_python(BoredActionResponse, {"response": json.loads(message)})
                    action = response.response
                    self.action_history.append((datetime.now(), action))
                    await self.handle_action(action, fetcher)
                except Exception:
                    fetcher.session.insert_message(generate_message(traceback.format_exc(), "user"))
                    continue

    async def handle_action(self, action: BoredAction, fetcher: MessageFetcher) -> None:
        match action.type:
            case "get_friends":
                fetcher.session.insert_message(generate_message(await self.get_friends(), "user"))
            case "send_private_message":
                await self.send_private_message(action.target_nickname, action.subject)
            case "sleep":
                self.state = StateEnum.SLEEPING
                self.state_until = datetime.now() + timedelta(minutes=action.time)
            case "do":
                self.state = StateEnum.BUSY
                self.state_until = datetime.now() + timedelta(minutes=action.estimated_time)
        if action.type != "skip" and self.state == StateEnum.BORED:
            self.state = StateEnum.ACTIVATE
            self.boredom = 0.0

    async def send_private_message(self, target_nickname: str, subject: str) -> None:
        async with get_session() as session:
            for friend_record in await session.scalars(select(PrivateChatSession)):
                user = await get_user(friend_record.user_id)
                if user.nickname == target_nickname:
                    bot_id = friend_record.bot_id
                    user_id = user.user_id
                    break
            else:
                raise ValueError("No such friend")
        bot = get_bot(bot_id)
        await send_proactive_private_message(bot, user_id, subject)

    def wake_up(self) -> None:
        if self.state == StateEnum.SLEEPING:
            self.state = StateEnum.ACTIVATE
            # TODO 在这里传入更多信息，记录实际的睡眠时间 

    async def get_friends(self) -> str:
        friend_list = []
        async with get_session() as session:
            for friend_record in await session.scalars(select(PrivateChatSession)):
                user = await get_user(friend_record.user_id)
                friend_list.append(await lang.text(
                    "main_session.friend",
                    self.lang_str,
                    user.get_nickname(),
                    user.get_fav(),
                    await user.get_fav_level(),
                    datetime.fromtimestamp(friend_record.last_message_time).isoformat(),
                    datetime.fromtimestamp(friend_record.last_proactive_message_time).isoformat() if friend_record.last_proactive_message_time else await lang.text("main_session.not_chatted_private", self.lang_str),
                ))
        return await lang.text("main_session.friends", self.lang_str, "\n".join(friend_list), await lang.text("prompt_group.fav_rule", self.lang_str))


main_session = MainSession(datetime.now())
# TODO 使用数据库持久化保存 last_activate_time