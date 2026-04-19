import asyncio
import json
import re
import traceback
from nonebot import get_bot
from nonebot.compat import type_validate_python
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Literal, Optional, Union, TypedDict

from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_chat.core.proactive_chat import send_proactive_private_message
from nonebot_plugin_chat.models import (
    ActionState,
    BoredAction,
    BoredActionResponse,
    CustomAction,
    MainSessionActionHistory,
    Note,
    PrivateChatSession,
    RestAction,
    SendPrivateMsgAction,
    SkipAction,
    WriteBlogAction,
)
from ..enums import StateEnum
from nonebot_plugin_chat.utils.instant_mem import get_instant_memories
from nonebot_plugin_chat.utils.note_manager import get_context_notes
from nonebot_plugin_chat.utils.prompt import get_prompt_text
from nonebot_plugin_larkuser.utils.user import get_user
from nonebot_plugin_orm import get_session
from sqlalchemy import delete, select
from ..lang import lang
from nonebot_plugin_chat.enums import MoodEnum
from nonebot_plugin_chat.utils.status_manager import StatusManager
from nonebot_plugin_openai.utils.chat import MessageFetcher
from nonebot_plugin_openai.utils.message import generate_message
from nonebot_plugin_chat.utils import parse_message_to_string
from nonebot_plugin_chat.utils.blog import create_blog_post
from pydantic import BaseModel

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.session.base import BaseSession

from nonebot_plugin_chat.core.session import groups

EFFECTIVE_ACTIONS = ["send_private_message", "do", "sleep", "write_blog"]


class MainSession:

    def __init__(self, lang_str: str = "zh_hans") -> None:
        self.state = StateEnum.ACTIVATE
        # 开始时间，详细信息，结束时间
        self.action_history: list[tuple[datetime, BoredAction, Optional[datetime]]] = []
        self.thinking_cold_until = datetime.now() - timedelta(minutes=5)
        self.thinking_lock = asyncio.Lock()
        self.status_manager = StatusManager()
        self.lang_str = lang_str
        self.state_until = datetime.now()
        scheduler.scheduled_job("interval", minutes=5)(self.process_timer)

    def is_boredom(self) -> bool:
        dt = datetime.now()
        inactive_group_count = len(
            [
                group
                for group in groups.values()
                if group.cached_messages and (dt - group.cached_messages[-1]["send_time"]) >= timedelta(minutes=10)
            ]
        )
        group_count = len(groups)
        return (
            (group_count >= 3 and inactive_group_count >= 3)
            or (group_count < 3 and inactive_group_count >= group_count * 0.3)
        ) and (self.state_until is None or dt >= self.state_until)

    async def generate_user_prompt(
        self,
        trigger_reason: Literal["boredom_thresold", "task_finished", "chat_request"],
        request_text: Optional[str] = None,
        trigger_from: Optional[str] = None,
    ) -> str:
        event_text = await lang.text(
            f"main_session.latest_event.{trigger_reason}",
            self.lang_str,
            trigger_from=trigger_from,
            request_text=request_text,
        )
        return await lang.text("main_session.prompt_user", self.lang_str, event_text)

    async def request_think(
        self,
        trigger_reason: Literal["boredom_thresold", "task_finished", "chat_request"],
        request_text: Optional[str] = None,
        trigger_from: Optional[str] = None,
    ) -> None:
        dt = datetime.now()
        if self.state == StateEnum.SLEEPING:
            return
        if dt < self.thinking_cold_until or self.thinking_lock.locked():
            return
        async with self.thinking_lock:
            fetcher = await MessageFetcher.create(
                [
                    generate_message(await self.generate_system_prompt(), "system"),
                    generate_message(
                        await self.generate_user_prompt(trigger_reason, request_text, trigger_from), "user"
                    ),
                ],
                identify="Chat - Main Session Think",
                reasoning_effort="medium",
            )
            async for msg in fetcher.fetch_message_stream():
                message = re.sub(r"`{1,3}([a-zA-Z0-9]+)?", "", msg)
                try:
                    response = type_validate_python(BoredActionResponse, {"response": json.loads(message)})
                    action = response.response
                    if action.type in ["send_private_message", "do", "sleep", "write_blog"]:
                        self.action_history.append((datetime.now(), action, None))
                    await self.handle_action(action, fetcher)
                except Exception:
                    fetcher.session.insert_message(generate_message(traceback.format_exc(), "user"))
                    continue

    async def get_action_str(
        self, action: BoredAction, start_time: datetime, stop_time: Optional[datetime]
    ) -> Optional[str]:
        match action.type:
            case "send_private_message":
                if stop_time is not None:
                    reply_time = stop_time
                    time_str = reply_time.strftime("%H:%M") if reply_time else ""
                    return await lang.text(
                        "main_session.history.send_private_message.replied",
                        self.lang_str,
                        action.target_nickname,
                        action.subject,
                        time_str,
                    )
                else:
                    return await lang.text(
                        "main_session.history.send_private_message.no_reply",
                        self.lang_str,
                        action.target_nickname,
                        action.subject,
                    )
            case "sleep":
                if stop_time is None:
                    actual_minutes = (
                        min(datetime.now() - start_time, timedelta(minutes=action.time)).total_seconds() / 60
                    )
                else:
                    actual_minutes = min(stop_time - start_time, timedelta(minutes=action.time)).total_seconds() / 60
                return await lang.text(
                    "main_session.history.sleep.completed", self.lang_str, action.time, actual_minutes
                )
            case "do":
                return await lang.text(
                    "main_session.history.do", self.lang_str, action.information, action.estimated_time
                )
            case "write_blog":
                return await lang.text("main_session.history.write_blog", self.lang_str, action.title)

    async def generate_system_prompt(self) -> str:
        mood = self.status_manager.get_status()
        state_str = await lang.text(
            "prompt_group.state",
            self.lang_str,
            await lang.text(f"status.mood.{mood[0].value}", self.lang_str),
            self.status_manager.get_mood_retention(),
            mood[1],
        )
        instant_mem = "\n".join(
            [
                await lang.text(
                    "prompt_group.instant_mem",
                    self.lang_str,
                    mem["category"],
                    mem["expire_level"],
                    mem["create_time"].strftime("%Y-%m-%d %H:%M:%S"),
                    mem["name"],
                    mem["ctx_id"],
                    mem["content"],
                )
                for mem in get_instant_memories()
            ],
        )

        note_manager = await get_context_notes("main_")
        notes = await note_manager.filter_note(instant_mem)
        notes = notes[0] + notes[1]

        return await lang.text(
            "main_session.prompt",
            self.lang_str,
            await get_prompt_text("identity"),
            await self.get_friends(),
            await lang.text("prompt_group.time", self.lang_str, datetime.now().isoformat()),
            state_str,
            (
                "\n".join([await self.format_note(note) for note in notes])
                if notes
                else await lang.text("prompt.note.none", self.lang_str)
            ),
            instant_mem,
            await self.get_recent_actions_text(self.lang_str),
        )

    async def get_recent_actions_text(self, lang_str: str) -> str:
        return "\n".join(
            [
                f"[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] {s}"
                for start_time, item, stop_time in self.action_history[-20:]
                if (s := await self.get_action_str(item, start_time, stop_time))
            ]
        )

    async def process_timer(self):
        dt = datetime.now()
        if self.state_until and dt > self.state_until:
            self.state_until = None
            if self.state == StateEnum.BUSY:
                for action in self.action_history[::-1]:
                    if action[1].type == "do":
                        await self.request_think("task_finished", action[1].information)
                        break
            self.state = StateEnum.ACTIVATE
        if self.is_boredom():
            await self.request_think("boredom_thresold", None)
        await self.save_action_history()

    async def load_action_history(self) -> None:
        async with get_session() as session:
            for item in await session.scalars(
                select(MainSessionActionHistory)
                .order_by(MainSessionActionHistory.id_.desc())
                .limit(20)
                .order_by(MainSessionActionHistory.id_)
            ):
                self.action_history.append(
                    (
                        item.start_time,
                        type_validate_python(BoredActionResponse, {"response": item.action}).response,
                        item.end_time,
                    )
                )

    async def save_action_history(self) -> None:
        async with get_session() as session:
            await session.execute(delete(MainSessionActionHistory))
            for action in self.action_history:
                session.add(
                    MainSessionActionHistory(start_time=action[0], action=action[1].model_dump(), end_time=action[2])
                )
            await session.commit()

    async def format_note(self, note: Note) -> str:
        created_time = datetime.fromtimestamp(note.created_time).strftime("%y-%m-%d")
        return await lang.text("prompt.note.format", self.lang_str, note.content, note.id, created_time)

    async def handle_action(self, action: BoredAction, fetcher: MessageFetcher) -> None:
        match action.type:
            case "send_private_message":
                await self.send_private_message(action.target_nickname, action.subject)
            case "sleep":
                self.state = StateEnum.SLEEPING
                sleep_start = datetime.now()
                sleep_end = sleep_start + timedelta(minutes=action.time)
                self.state_until = sleep_end
            case "do":
                self.state = StateEnum.BUSY
                self.state_until = datetime.now() + timedelta(minutes=action.estimated_time)
            case "fetch_chat_history":
                await self.fetch_chat_history(action.context_id, fetcher)
            case "write_blog":
                await self.write_blog(action.title, action.content, fetcher)

    async def fetch_chat_history(self, context_id: str, fetcher: MessageFetcher) -> None:
        if context_id in groups:
            session = groups[context_id]
            result = await session.get_cached_messages_string()
            result = result or await lang.text("main_session.fetch_chat_history.no_messages", self.lang_str)
            fetcher.session.insert_message(generate_message(result, "user"))
        else:
            fetcher.session.insert_message(
                generate_message(await lang.text("main_session.fetch_chat_history.not_found", self.lang_str), "user")
            )

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
        # 记录用户ID，用于后续检查是否回复
        self._current_action_send_private_user_id = user_id
        bot = get_bot(bot_id)
        await send_proactive_private_message(bot, user_id, subject)

    async def write_blog(self, title: str, content: str, fetcher: MessageFetcher) -> None:
        await create_blog_post(title, content)
        result = await lang.text("main_session.write_blog.success", self.lang_str, title)
        fetcher.session.insert_message(generate_message(result, "user"))

    async def wake_up(self, session: Optional["BaseSession"] = None) -> None:
        if self.state != StateEnum.SLEEPING:
            return
        dt = datetime.now()
        for index in range(len(self.action_history)):
            start_time, action, stop_time = self.action_history[-index]
            if action.type == "sleep" and stop_time is None and start_time + timedelta(minutes=action.time) > dt:
                self.action_history[-index] = (start_time, action, dt)
                interrupted = True
                if interrupted and session is not None:
                    result = await lang.text(
                        "main_session.wake_up.interrupted",
                        self.lang_str,
                        dt.strftime("%H:%M:%S"),
                        action.time,
                        (dt - start_time).total_seconds() / 60,
                    )
                break
        else:
            interrupted = False
            result = None
        self.state = StateEnum.ACTIVATE
        if interrupted and result and session:
            session.processor.openai_messages.append_user_message(result)

    def update_send_private_message_state(self, user_id: str) -> None:
        for index in range(len(self.action_history)):
            start_time, action, stop_time = self.action_history[index]
            if action.type == "send_private_message" and stop_time is None:
                self.action_history[index] = (start_time, action, datetime.now())
                break

    async def get_friends(self) -> str:
        friend_list = []
        async with get_session() as session:
            for friend_record in await session.scalars(select(PrivateChatSession)):
                user = await get_user(friend_record.user_id)
                friend_list.append(
                    await lang.text(
                        "main_session.friend",
                        self.lang_str,
                        user.get_nickname(),
                        user.get_fav(),
                        await user.get_fav_level(),
                        datetime.fromtimestamp(friend_record.last_message_time).isoformat(),
                        (
                            datetime.fromtimestamp(friend_record.last_proactive_message_time).isoformat()
                            if friend_record.last_proactive_message_time
                            else await lang.text("main_session.not_chatted_private", self.lang_str)
                        ),
                    )
                )
        return await lang.text(
            "main_session.friends",
            self.lang_str,
            "\n".join(friend_list),
            await get_prompt_text("favorability"),
        )


main_session = MainSession()


async def init_main_session() -> None:
    """初始化 main_session，从数据库加载数据"""
    await main_session.load_action_history()
