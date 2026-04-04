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
from nonebot_plugin_chat.models import Note, PrivateChatSession, MainSessionData
from nonebot_plugin_chat.utils.instant_mem import get_instant_memories
from nonebot_plugin_chat.utils.note_manager import get_context_notes
from nonebot_plugin_larkuser.utils.user import get_user
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from ..lang import lang
from nonebot_plugin_chat.types import MoodEnum
from nonebot_plugin_chat.utils.status_manager import StatusManager
from nonebot_plugin_openai.utils.chat import MessageFetcher
from nonebot_plugin_openai.utils.message import generate_message
from nonebot_plugin_chat.utils import parse_message_to_string
from pydantic import BaseModel

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.session.base import BaseSession

from nonebot_plugin_chat.core.session import groups


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


# class GetFriendsAction(BaseModel):
# type: Literal["get_friends"]


class SendPrivateMsgAction(BaseModel):
    type: Literal["send_private_message"]
    target_nickname: str
    subject: str


class RestAction(BaseModel):
    type: Literal["sleep"]
    time: int


class FetchChatHistoryAction(BaseModel):
    type: Literal["fetch_chat_history"]
    context_id: str


BoredAction = Union[SkipAction, CustomAction, SendPrivateMsgAction, RestAction, FetchChatHistoryAction]


class BoredActionResponse(BaseModel):
    response: BoredAction


# Action 状态类型
class ActionState(TypedDict, total=False):
    """动作执行后的状态信息"""

    # sleep 动作的状态
    actual_sleep_minutes: Optional[int]  # 实际睡眠时间（分钟）
    sleep_interrupted: Optional[bool]  # 是否被提前唤醒

    # send_private_message 动作的状态
    user_replied: Optional[bool]  # 用户是否回复
    reply_time: Optional[datetime]  # 用户回复时间


class MainSession:

    def __init__(self, last_activate_time: datetime, lang_str: str = "zh_hans") -> None:
        self.ACTION_HISTORY_KEY = "action_history"
        self.lang_str = lang_str
        self.last_activate_time = last_activate_time
        self.boredom = 0.0
        # action_history 现在存储 (datetime, BoredAction, ActionState) 元组
        self.action_history: list[tuple[datetime, BoredAction, ActionState]] = []
        self.boredom_processor_lock = asyncio.Lock()
        self.state = StateEnum.ACTIVATE
        self.status_manager = StatusManager()
        self.state_until = None
        self.last_boredom_trigger_time = None
        # 记录当前正在执行的动作，用于后续更新状态
        self._current_action_start_time: Optional[datetime] = None
        self._current_action_sleep_plan_end: Optional[datetime] = None
        self._current_action_send_private_user_id: Optional[str] = None
        self._current_action_send_private_time: Optional[datetime] = None
        scheduler.scheduled_job("cron", minute="*", id="chat_heartbeat")(self.process_timer)

    def _serialize_action(self, action: BoredAction) -> dict:
        """将 BoredAction 序列化为字典"""
        if isinstance(action, SkipAction):
            return {"type": "skip"}
        elif isinstance(action, CustomAction):
            return {"type": "do", "information": action.information, "estimated_time": action.estimated_time}
        elif isinstance(action, SendPrivateMsgAction):
            return {
                "type": "send_private_message",
                "target_nickname": action.target_nickname,
                "subject": action.subject,
            }
        elif isinstance(action, RestAction):
            return {"type": "sleep", "time": action.time}
        return {"type": "skip"}

    def _deserialize_action(self, data: dict) -> BoredAction:
        """将字典反序列化为 BoredAction"""
        action_type = data.get("type")
        if action_type == "skip":
            return SkipAction(type="skip")
        elif action_type == "do":
            return CustomAction(type="do", information=data["information"], estimated_time=data["estimated_time"])
        elif action_type == "send_private_message":
            return SendPrivateMsgAction(
                type="send_private_message", target_nickname=data["target_nickname"], subject=data["subject"]
            )
        elif action_type == "sleep":
            return RestAction(type="sleep", time=data["time"])
        return SkipAction(type="skip")

    async def load_from_database(self) -> None:
        """从数据库加载 action_history"""
        async with get_session() as session:
            action_history_record = await session.get(MainSessionData, self.ACTION_HISTORY_KEY)
            if action_history_record:
                try:
                    data = json.loads(action_history_record.data_json)
                    self.action_history = []
                    for item in data:
                        dt = datetime.fromisoformat(item["datetime"])
                        action = self._deserialize_action(item["action"])
                        state = item["state"]
                        self.action_history.append((dt, action, state))
                except (json.JSONDecodeError, KeyError, ValueError):
                    self.action_history = []

    async def _save_action_history(self) -> None:
        """将 action_history 保存到数据库"""
        data = []
        for dt, action, state in self.action_history:
            # 处理 state 中的 datetime 对象
            state_copy = state.copy()
            if "reply_time" in state_copy and isinstance(state_copy["reply_time"], datetime):
                state_copy["reply_time"] = state_copy["reply_time"].isoformat()
            data.append({"datetime": dt.isoformat(), "action": self._serialize_action(action), "state": state_copy})

        async with get_session() as session:
            record = await session.get(MainSessionData, self.ACTION_HISTORY_KEY)
            if record is None:
                record = MainSessionData(
                    key=self.ACTION_HISTORY_KEY, data_json=json.dumps(data), updated_time=datetime.now().timestamp()
                )
                session.add(record)
            else:
                record.data_json = json.dumps(data)
                record.updated_time = datetime.now().timestamp()
            await session.commit()

    async def process_timer(self) -> None:
        match self.state:
            case StateEnum.ACTIVATE:
                self.boredom += 1
                if self.last_boredom_trigger_time and datetime.now() - self.last_boredom_trigger_time:
                    threshold = 50
                else:
                    threshold = 25
                if self.boredom >= threshold:
                    self.state = StateEnum.BORED
                    self.boredom = 0.0

            case StateEnum.BORED:
                asyncio.create_task(self.process_boredom())

        if self.state_until is not None and datetime.now() > self.state_until:
            # 如果当前是 SLEEPING 状态且是正常结束（没有被 wake_up 提前处理），更新状态
            if self.state == StateEnum.SLEEPING:
                self._update_sleep_action_state_on_timer_end()

            self.state = StateEnum.ACTIVATE
            self.state_until = None
            self.boredom = 0.0

        # 保存 action_history 到数据库
        await self._save_action_history()

    def _update_sleep_action_state_on_timer_end(self) -> None:
        """当 sleep 状态自然结束时，更新最后一个 sleep action 的状态"""
        if not self.action_history:
            return

        last_action = self.action_history[-1]
        if last_action[1].type != "sleep":
            return

        dt, action, state = last_action

        # 如果状态已经被更新过（被 wake_up 处理过），不再更新
        if state.get("actual_sleep_minutes") is not None:
            return

        # 计算实际睡眠时间
        if self._current_action_start_time is not None:
            actual_duration = (datetime.now() - self._current_action_start_time).total_seconds() / 60
            state["actual_sleep_minutes"] = int(actual_duration)
            state["sleep_interrupted"] = False  # 自然结束，不是中断

        # 清除 sleep 相关状态
        self._current_action_start_time = None
        self._current_action_sleep_plan_end = None

    def record_activate(self, important: bool = False) -> None:
        self.last_activate_time = datetime.now()
        if important:
            self.boredom -= 10
        else:
            self.boredom -= 2
        self.boredom = max(0, self.boredom)

    async def get_action_str(self, action: BoredAction, state: ActionState) -> Optional[str]:
        match action.type:
            case "send_private_message":
                if state.get("user_replied") is True:
                    reply_time = state.get("reply_time")
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
                actual_minutes = state.get("actual_sleep_minutes")
                if actual_minutes is not None:
                    if state.get("sleep_interrupted"):
                        return await lang.text(
                            "main_session.history.sleep.interrupted", self.lang_str, action.time, actual_minutes
                        )
                    else:
                        return await lang.text(
                            "main_session.history.sleep.completed", self.lang_str, action.time, actual_minutes
                        )
                else:
                    return await lang.text("main_session.history.sleep.default", self.lang_str, action.time)
            case "do":
                return await lang.text(
                    "main_session.history.do", self.lang_str, action.information, action.estimated_time
                )

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
            await lang.text("prompt_group.identify", self.lang_str),
            await self.get_friends(),
            await lang.text("prompt_group.time", self.lang_str, datetime.now().isoformat()),
            state_str,
            instant_mem,
            (
                "\n".join([await self.format_note(note) for note in notes])
                if notes
                else await lang.text("prompt.note.none", self.lang_str)
            ),
            "\n".join(
                [
                    f"[{dt.strftime('%Y-%m-%d %H:%M:%S')}] {s}"
                    for dt, item, state in self.action_history[-20:]
                    if (s := await self.get_action_str(item, state))
                ]
            ),
        )

    async def format_note(self, note: Note) -> str:
        created_time = datetime.fromtimestamp(note.created_time).strftime("%y-%m-%d")
        return await lang.text("prompt.note.format", self.lang_str, note.content, note.id, created_time)

    async def get_recent_actions_text(self, lang_str: str = "zh_hans") -> str:
        """获取最近做的事的格式化文本，用于群聊 system prompt"""
        if not self.action_history:
            return await lang.text("main_session.recent_activities.none", lang_str)

        activities = []
        for dt, item, state in self.action_history[-10:]:  # 取最近10条
            if s := await self.get_action_str(item, state):
                time_str = dt.strftime("%Y-%m-%d %H:%M")
                activities.append(f"[{time_str}] {s}")

        if not activities:
            return await lang.text("main_session.recent_activities.none", lang_str)

        return "\n".join(reversed(activities))  # 时间从早到晚排列

    async def process_boredom(self) -> None:
        if self.boredom_processor_lock.locked():
            return
        async with self.boredom_processor_lock:
            self.last_boredom_trigger_time = datetime.now()
            fetcher = await MessageFetcher.create(
                [
                    generate_message(await self.generate_system_prompt(), "system"),
                    generate_message(await lang.text("main_session.prompt_user", self.lang_str), "user"),
                ],
                identify="Chat - Bored",
                reasoning_effort="medium",
            )
            async for msg in fetcher.fetch_message_stream():
                message = re.sub(r"`{1,3}([a-zA-Z0-9]+)?", "", msg)
                try:
                    response = type_validate_python(BoredActionResponse, {"response": json.loads(message)})
                    action = response.response
                    # 初始化 action_state，对于 send_private_message 默认标记为未回复
                    action_state: ActionState = {}
                    if action.type == "send_private_message":
                        action_state["user_replied"] = False
                    if action.type != "fetch_chat_history":
                        self.action_history.append((datetime.now(), action, action_state))
                    await self.handle_action(action, fetcher)
                except Exception:
                    fetcher.session.insert_message(generate_message(traceback.format_exc(), "user"))
                    continue

    async def handle_action(self, action: BoredAction, fetcher: MessageFetcher) -> None:
        match action.type:
            case "send_private_message":
                # 记录发送私聊前的状态，用于后续判断用户是否回复
                self._current_action_send_private_time = datetime.now()
                await self.send_private_message(action.target_nickname, action.subject)
            case "sleep":
                self.state = StateEnum.SLEEPING
                sleep_start = datetime.now()
                sleep_end = sleep_start + timedelta(minutes=action.time)
                self.state_until = sleep_end
                # 记录 sleep 状态用于后续更新
                self._current_action_start_time = sleep_start
                self._current_action_sleep_plan_end = sleep_end
            case "do":
                self.state = StateEnum.BUSY
                self.state_until = datetime.now() + timedelta(minutes=action.estimated_time)
            case "fetch_chat_history":
                await self.fetch_chat_history(action.context_id, fetcher)
        if action.type not in ["skip", "fetch_chat_history"] and self.state == StateEnum.BORED:
            self.state = StateEnum.ACTIVATE
            self.boredom = 0.0

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

    async def wake_up(self, session: Optional["BaseSession"] = None) -> None:
        if self.state == StateEnum.SLEEPING:
            # 计算实际睡眠时间
            wake_time = datetime.now()
            actual_sleep_minutes = None
            sleep_interrupted = False
            planned_duration = 0

            if self._current_action_start_time is not None and self._current_action_sleep_plan_end is not None:
                planned_duration = (
                    self._current_action_sleep_plan_end - self._current_action_start_time
                ).total_seconds() / 60
                actual_duration = (wake_time - self._current_action_start_time).total_seconds() / 60
                actual_sleep_minutes = int(actual_duration)
                # 如果被提前唤醒（比计划提前超过1分钟），标记为中断
                if actual_duration < planned_duration - 1:
                    sleep_interrupted = True

            # 更新最后一个 sleep action 的状态
            if self.action_history:
                last_action = self.action_history[-1]
                if last_action[1].type == "sleep":
                    dt, action, state = last_action
                    state["actual_sleep_minutes"] = actual_sleep_minutes
                    state["sleep_interrupted"] = sleep_interrupted

            self.state = StateEnum.ACTIVATE
            self.state_until = None
            self.boredom = 0.0

            if session is not None and actual_sleep_minutes is not None:
                current_time = datetime.now().strftime("%H:%M:%S")
                if sleep_interrupted:
                    wake_up_prompt = await session.processor.session.text(
                        "main_session.wake_up.interrupted_prompt", current_time, planned_duration, actual_sleep_minutes
                    )
                else:
                    wake_up_prompt = await session.processor.session.text(
                        "main_session.wake_up.completed_prompt", current_time
                    )
                session.processor.openai_messages.append_user_message(wake_up_prompt)

            self._current_action_start_time = None
            self._current_action_sleep_plan_end = None

            # 如果提供了 session，向 openai_messages 添加唤醒提示

    def update_send_private_message_state(self, user_id: str) -> None:
        """检查用户是否回复了主动私聊，如果是，更新最后一个 send_private_message action 的状态

        Args:
            user_id: 发送消息的用户 ID
        """
        # 检查是否是目标用户回复的
        if self._current_action_send_private_user_id is None or self._current_action_send_private_user_id != user_id:
            return

        # 检查时间窗口（30分钟内）
        if self._current_action_send_private_time is None:
            return

        time_elapsed = (datetime.now() - self._current_action_send_private_time).total_seconds() / 60
        if time_elapsed > 30:
            # 超过30分钟，认为用户没有回复
            if self.action_history:
                last_action = self.action_history[-1]
                if last_action[1].type == "send_private_message":
                    dt, action, state = last_action
                    if state.get("user_replied") is None:
                        state["user_replied"] = False
            self._current_action_send_private_user_id = None
            self._current_action_send_private_time = None
            return

        # 更新状态为已回复
        if self.action_history:
            last_action = self.action_history[-1]
            if last_action[1].type == "send_private_message":
                dt, action, state = last_action
                state["user_replied"] = True
                state["reply_time"] = datetime.now()

        # 清除状态
        self._current_action_send_private_user_id = None
        self._current_action_send_private_time = None

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
            await lang.text("prompt_group.fav_rule", self.lang_str),
        )


main_session = MainSession(datetime.now())


async def init_main_session() -> None:
    """初始化 main_session，从数据库加载数据"""
    await main_session.load_from_database()
