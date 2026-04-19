import asyncio

from nonebot_plugin_chat.utils.instant_mem import delete_sleep_memory

from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_chat.utils.instant_mem import post_instant_memory
import json
import re
import traceback
from nonebot import get_bot, logger
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
        # 睡觉时间相关
        self.pending_sleep_decisions: dict[str, dict] = {}

    def is_boredom(self) -> bool:
        dt = datetime.now()
        inactive_group_count = len([group for group in groups.values() if group.cached_messages and (dt - group.cached_messages[-1]["send_time"]) >= timedelta(minutes=10)])
        group_count = len(groups)
        return (((group_count >= 3 and inactive_group_count >= 3)
                or (group_count < 3 and inactive_group_count >= group_count * 0.3))
                and (self.state_until is None or dt >= self.state_until)
                and (self.action_history == [] or dt >= self.action_history[-1][0] + timedelta(minutes=20)))

    
    async def generate_user_prompt(self, trigger_reason: Literal["boredom_thresold", "task_finished", "chat_request", "ready_sleep"], request_text: Optional[str] = None, trigger_from: Optional[str] = None) -> str:
        event_text = await lang.text(f"main_session.latest_event.{trigger_reason}", self.lang_str, trigger_from=trigger_from, request_text=request_text)
        return await lang.text("main_session.prompt_user", self.lang_str, event_text)

    async def request_think(self, trigger_reason: Literal["boredom_thresold", "task_finished", "chat_request", "ready_sleep"], request_text: Optional[str] = None, trigger_from: Optional[str] = None) -> None:
        dt = datetime.now()
        if self.state == StateEnum.SLEEPING:
            return
        if dt < self.thinking_cold_until or self.thinking_lock.locked():
            return
        async with self.thinking_lock:
            fetcher = await MessageFetcher.create(
                [
                    generate_message(await self.generate_system_prompt(trigger_reason == "ready_sleep"), "system"),
                    generate_message(await self.generate_user_prompt(trigger_reason, request_text, trigger_from), "user"),
                ],
                identify="Chat - Main Session Think",
                reasoning_effort="medium",
            )
            async for msg in fetcher.fetch_message_stream():
                message = re.sub(r"`{1,3}([a-zA-Z0-9]+)?", "", msg)
                try:
                    response = type_validate_python(BoredActionResponse, {"response": json.loads(message)})
                    action = response.response
                    # 如果是 ready_sleep，只允许 sleep 动作
                    if trigger_reason == "ready_sleep" and action.type != "sleep":
                        fetcher.session.insert_message(generate_message("错误：在准备睡觉时只能选择 sleep 动作", "user"))
                        continue
                    if action.type in ["send_private_message", "do", "sleep", "write_blog"]:
                        self.action_history.append((datetime.now(), action, None))
                    await self.handle_action(action, fetcher)
                except Exception:
                    fetcher.session.insert_message(generate_message(traceback.format_exc(), "user"))
                    continue

    


    async def get_action_str(self, action: BoredAction, start_time: datetime, stop_time: Optional[datetime]) -> Optional[str]:
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
                    actual_minutes = min(datetime.now() - start_time, timedelta(minutes=action.time)).total_seconds() / 60
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
                return await lang.text(
                    "main_session.history.write_blog", self.lang_str, action.title
                )

    async def get_additional_prompt(self) -> str:
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
            "main_session.additional_info",
            self.lang_str,
            await lang.text("prompt_group.time", self.lang_str, datetime.now().isoformat()),
            state_str,
            (
                "\n".join([await self.format_note(note) for note in notes])
                if notes
                else await lang.text("prompt.note.none", self.lang_str)
            ),
            instant_mem
        )


    async def generate_system_prompt(self, sleep_action_only: bool = False) -> str:
        return await lang.text(
            "main_session.prompt",
            self.lang_str,
            await lang.text("main_session.action_sleep", self.lang_str),
            "" if sleep_action_only else await lang.text("main_session.action_list", self.lang_str),
            await get_prompt_text("identity"),
            await self.get_friends(),
            await self.get_additional_prompt(),
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

    async def generate_sleep_time(self) -> None:
        """每天8:30执行的定时任务，决定今天的睡觉时间"""
        # 生成睡觉时间决策的prompt
        system_prompt = await lang.text(
            "main_session.sleep_time_prompt.system",
            self.lang_str,
            await get_prompt_text("identity"),
            await self.get_additional_prompt(),
            await self.get_recent_actions_text(self.lang_str)
        )
        user_prompt = await lang.text("main_session.sleep_time_prompt.user", self.lang_str)

        try:
            messages = [
                generate_message(system_prompt, "system"),
                generate_message(user_prompt, "user"),
            ]
            response = await fetch_message(messages, identify="Sleep Time Decision")
            # 解析返回的时间（格式：HH:MM）
            time_str = response.strip()
            if ":" in time_str:
                hour, minute = map(int, time_str.split(":"))
                now = datetime.now()
                scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if scheduled_time < now:
                    return

                # 写入instant_mem
                await post_instant_memory(
                    category="myself",
                    content=f"你在决定于 {time_str} 睡觉。",
                    keywords=["睡觉", "睡眠", "休息"],
                    expire_level=4,
                    lang_str=self.lang_str,
                    ctx_id="main_",
                    name="main_session",
                )

                scheduler.add_job(
                    self.ask_sleep,
                    "date",
                    run_date=scheduled_time,
                )
        except Exception as e:
            logger.exception(e)

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
        # 检查睡觉时间
        await self.ask_sleep()
        await self.save_action_history()

    async def load_action_history(self) -> None:
        async with get_session() as session:
            for item in await session.scalars(select(MainSessionActionHistory).order_by(MainSessionActionHistory.id_.desc()).limit(20).order_by(MainSessionActionHistory.id_)):
                self.action_history.append((
                    item.start_time,
                    type_validate_python(BoredActionResponse, {"response": item.action}).response,
                    item.end_time
                ))
    
    async def save_action_history(self) -> None:
        async with get_session() as session:
            await session.execute(delete(MainSessionActionHistory))
            for action in self.action_history:
                session.add(MainSessionActionHistory(
                    start_time=action[0],
                    action=action[1].model_dump(),
                    end_time=action[2]
                ))
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


    async def ask_sleep(self) -> None:
        dt = datetime.now()
        # 开始决策流程
        self.pending_sleep_decisions = {}
        # 找出最近5分钟有活动的session
        active_sessions = []
        for session_id, group in groups.items():
            if group.cached_messages and (dt - group.cached_messages[-1]["send_time"]) < timedelta(minutes=5):
                active_sessions.append(group)
        # 向这些session发送睡觉提示
        sleep_prompt = await lang.text("main_session.sleep_prompt", self.lang_str)
        for session in active_sessions:
            await session.add_event(sleep_prompt, "all")
        # 启动决策收集任务
        asyncio.create_task(self.collect_sleep_decisions())

    async def collect_sleep_decisions(self) -> None:
        """收集所有session的睡觉决策并处理"""
        # 等待1.5分钟收集决策
        sleep_time = datetime.now()
        await asyncio.sleep(90)
        # 检查是否有delay
        delay_decisions = [
            (sid, dec) for sid, dec in self.pending_sleep_decisions.items()
            if dec["deal_type"] == "delay"
        ]
        if delay_decisions:
            # 计算平均延迟时间
            avg_delay = sum(dec["delay_minutes"] for _, dec in delay_decisions) / len(delay_decisions)
            # 拼接非空原因
            reasons = [dec["reason"] for _, dec in delay_decisions if dec["reason"]]
            reason_text = "、".join(reasons) if reasons else ""

            # 更新睡觉时间
            new_sleep_time = sleep_time + timedelta(minutes=avg_delay)
            scheduler.add_job(
                self.ask_sleep,
                "date",
                run_date=new_sleep_time
            )

            # 向所有调用了工具的session推送结果
            result_text = await lang.text(
                "main_session.sleep_decision.delay",
                self.lang_str,
                reason_text,
                new_sleep_time.strftime("%H:%M")
            )
            for session_id, decision in self.pending_sleep_decisions.items():
                if session_id in groups:
                    # 设置Future结果
                    if "future" in decision and not decision["future"].done():
                        decision["future"].set_result(result_text)
                    else:
                        await groups[session_id].add_event(result_text, "all")
        else:
            # 全部ready，5分钟后睡觉
            result_text = await lang.text("main_session.sleep_decision.ready", self.lang_str)
            for session_id, decision in self.pending_sleep_decisions.items():
                if session_id in groups:
                    # 设置Future结果
                    if "future" in decision and not decision["future"].done():
                        decision["future"].set_result(result_text)
                    else:
                        await groups[session_id].add_event(result_text, "all")

            await asyncio.sleep(300)
            await self.request_think("ready_sleep", None)

        # 清理决策状态
        self.pending_sleep_decisions = {}
        # 删除instant_mem中关于睡觉的记忆
        delete_sleep_memory()

    async def submit_sleep_decision(
        self,
        session_id: str,
        deal_type: Literal["ready", "delay"],
        delay_minutes: Optional[int] = None,
        reason: Optional[str] = None,
        future: Optional[asyncio.Future] = None,
    ) -> None:
        """提交睡觉决策"""
        if session_id in self.pending_sleep_decisions:
            return  # 已经提交过

        self.pending_sleep_decisions[session_id] = {
            "deal_type": deal_type,
            "delay_minutes": delay_minutes or 0,
            "reason": reason or "",
        }
        if future:
            self.pending_sleep_decisions[session_id]["future"] = future

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
                    result = await lang.text("main_session.wake_up.interrupted", self.lang_str, dt.strftime("%H:%M:%S"), action.time, (dt - start_time).total_seconds() / 60)
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
    # 注册每天8:30的睡觉时间决策任务
    scheduler.scheduled_job("cron", hour=8, minute=30)(main_session.generate_sleep_time)
