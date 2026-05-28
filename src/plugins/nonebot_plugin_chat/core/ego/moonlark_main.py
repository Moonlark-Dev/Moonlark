"""Moonlark 意识主模块

EGO 模块的核心，负责：
- 维护全局状态（睡眠/心情/活动等）
- 周期性执行 request_think 生成动作决策
- 调用子控制器执行具体动作
- 提供 summary_instant_memory 汇总即时记忆
"""

import asyncio
import json
import re
import traceback
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal, Optional

from nonebot import get_bot, logger
from nonebot.compat import type_validate_python
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_openai.utils.chat import fetch_json, MessageFetcher
from nonebot_plugin_openai.utils.message import generate_message
from nonebot_plugin_orm import get_session
from sqlalchemy import delete, select

from ...enums import StateEnum
from ...lang import lang
from ...models import (
    ActionDecisionResponse,
    BoredActionResponse,
    CustomAction,
    MainSessionActionHistory,
    Note,
    PrivateChatSession,
    RestAction,
    SleepDecisionResponse,
)
from ...utils.instant_mem import get_instant_memories
from ...utils.note_manager import get_context_notes
from ...utils.prompt import get_prompt_text
from ...utils.status_manager import StatusManager
from ...utils import parse_message_to_string
from ...utils.blog import create_blog_post
from ..session import groups
from ..proactive_chat import send_proactive_private_message
from .sleep_controller import SleepController
from .blog_writer import BlogWriter
from .proactive_chat_ctrl import ProactiveChatController
from .self_action_ctrl import SelfActionController
from .action_advisor import ActionAdvisor

if TYPE_CHECKING:
    from ..session.base import BaseSession

EFFECTIVE_ACTIONS = ["send_private_message", "do", "sleep", "write_blog"]


class MoonlarkMain:
    """Moonlark 意识主模块"""

    def __init__(self, lang_str: str = "zh_hans") -> None:
        self.lang_str = lang_str
        self.state = StateEnum.ACTIVATE
        self.action_history: list[tuple[datetime, object, Optional[datetime]]] = []
        self.thinking_cold_until = datetime.now() - timedelta(minutes=5)
        self.thinking_lock = asyncio.Lock()
        self.status_manager = StatusManager()
        self.state_until = datetime.now()
        self.consecutive_replies: int = 0

        # 子控制器
        self.sleep_controller = SleepController(self)
        self.blog_writer = BlogWriter(self)
        self.proactive_chat_ctrl = ProactiveChatController(self)
        self.self_action_ctrl = SelfActionController(self)
        self.action_advisor = ActionAdvisor(self)

        # 定时器注册（每5分钟）
        scheduler.scheduled_job("interval", minutes=5, id="moonlark_main_process_timer")(self.process_timer)

    def get_minutes_since_last_group_message(self) -> float:
        """获取距离最近一次群内发言的分钟数"""
        dt = datetime.now()
        last_msg_time = None
        for group in groups.values():
            if group.cached_messages:
                msg_time = group.cached_messages[-1]["send_time"]
                if last_msg_time is None or msg_time > last_msg_time:
                    last_msg_time = msg_time
        if last_msg_time is None:
            return 60.0  # 无消息时默认 60 分钟
        return (dt - last_msg_time).total_seconds() / 60.0

    def is_boredom(self) -> bool:
        """使用困倦值公式判断是否需要触发 think"""
        if self.state_until is not None and datetime.now() < self.state_until:
            return False
        if self.action_history and datetime.now() < self.action_history[-1][0] + timedelta(minutes=20):
            return False

        minutes_since_last = self.get_minutes_since_last_group_message()
        result = self.sleep_controller.check_drowsiness(self.consecutive_replies, minutes_since_last)

        if result == "sleep":
            return True  # 强制触发，request_think 中会强制选择 sleep
        return False

    async def generate_user_prompt(
        self,
        trigger_reason: Literal["boredom_thresold", "task_finished", "chat_request", "ready_sleep"],
        request_text: Optional[str] = None,
        trigger_from: Optional[str] = None,
    ) -> str:
        event_text = await lang.text(
            f"moonlark_main.latest_event.{trigger_reason}",
            self.lang_str,
            trigger_from=trigger_from,
            request_text=request_text,
        )
        return await lang.text("moonlark_main.prompt_user", self.lang_str, event_text)

    async def request_think(
        self,
        trigger_reason: Literal["boredom_thresold", "task_finished", "chat_request", "ready_sleep"],
        request_text: Optional[str] = None,
        trigger_from: Optional[str] = None,
    ) -> None:
        """核心决策方法"""
        dt = datetime.now()
        if self.state == StateEnum.SLEEPING:
            return
        if dt < self.thinking_cold_until or self.thinking_lock.locked():
            return

        async with self.thinking_lock:
            # 触发所有会话的即时记忆生成
            for group in groups.values():
                await group.processor.generate_instant_memory()

            # 获取 ActionAdvisor 建议
            state = self._collect_state()
            summary = await self.summary_instant_memory()
            suggestions = self.action_advisor.get_suggestions(state, summary)

            # 生成系统提示
            system_prompt = await self.generate_system_prompt(trigger_reason == "ready_sleep", suggestions)
            user_prompt = await self.generate_user_prompt(trigger_reason, request_text, trigger_from)

            fetcher = await MessageFetcher.create(
                [generate_message(system_prompt, "system"), generate_message(user_prompt, "user")],
                identify="Chat - MoonlarkMain Think",
                reasoning_effort="medium",
            )

            async for msg in fetcher.fetch_message_stream():
                message = re.sub(r"`{1,3}([a-zA-Z0-9]+)?", "", msg)
                try:
                    response = type_validate_python(BoredActionResponse, {"response": json.loads(message)})
                    action = response.response

                    # 如果是 ready_sleep，只允许 sleep 动作
                    if trigger_reason == "ready_sleep" and action.type != "sleep":
                        fetcher.session.insert_message(
                            generate_message("错误：在准备睡觉时只能选择 sleep 动作", "user")
                        )
                        continue

                    if action.type in ["send_private_message", "do", "sleep", "write_blog"]:
                        self.action_history.append((datetime.now(), action, None))

                    await self.handle_action(action, fetcher)
                except Exception:
                    fetcher.session.insert_message(generate_message(traceback.format_exc(), "user"))
                    continue

    def _collect_state(self) -> dict:
        """收集当前状态供 ActionAdvisor 使用"""
        mood = self.status_manager.get_status()
        blog_status = self.blog_writer.get_status()

        return {
            "sleep_mode": self.state == StateEnum.SLEEPING,
            "blog_status": blog_status["status"],
            "draft": blog_status["draft"],
            "cooldown_remaining": blog_status["cooldown_remaining"],
            "last_blog_time": blog_status["last_blog_time"],
            "proactive_info": self.proactive_chat_ctrl.get_cooldown_info(),
            "current_activity": self.self_action_ctrl.current_activity,
            "mood": {
                "emotion": mood[0].value,
                "intensity": 0.5,
                "reason": mood[1],
            },
        }

    async def summary_instant_memory(self) -> str:
        """汇总所有活跃会话的即时记忆，生成全局总结"""
        memories = get_instant_memories()
        if not memories:
            return "暂无群聊记忆。"

        # 格式化记忆
        memory_lines = []
        for mem in memories:
            time_str = mem["create_time"].strftime("%H:%M")
            ctx = mem.get("name", mem.get("ctx_id", ""))
            memory_lines.append(f"[{time_str}][{ctx}] {mem['content']}")

        # 调用 LLM 生成总结（限 200 token）
        try:
            summary = await lang.text(
                "moonlark_main.summarize_memories",
                self.lang_str,
                "\n".join(memory_lines),
            )
            return summary
        except Exception as e:
            logger.exception(f"[MoonlarkMain] 汇总即时记忆失败: {e}")
            return "记忆汇总失败。"

    async def trigger_sleep(self) -> None:
        """触发睡眠，重置会话"""
        await asyncio.sleep(60)  # 防止马上被叫起来
        for group in groups.values():
            await group.processor.generate_instant_memory()
            await group.processor.openai_messages.reset_chat_history()

    async def get_action_str(self, action, start_time: datetime, stop_time: Optional[datetime]) -> Optional[str]:
        """格式化动作历史文本"""
        match action.type:
            case "send_private_message":
                if stop_time is not None:
                    time_str = stop_time.strftime("%H:%M") if stop_time else ""
                    return await lang.text(
                        "moonlark_main.history.send_private_message.replied",
                        self.lang_str,
                        action.target_nickname,
                        action.subject,
                        time_str,
                    )
                else:
                    return await lang.text(
                        "moonlark_main.history.send_private_message.no_reply",
                        self.lang_str,
                        action.target_nickname,
                        action.subject,
                    )
            case "sleep":
                if stop_time is None:
                    actual_minutes = (
                        min(datetime.now() - start_time, timedelta(minutes=action.time)).total_seconds() / 60
                    )
                    return await lang.text(
                        "moonlark_main.history.sleep.in_progress",
                        self.lang_str,
                        actual_minutes,
                        action.time,
                    )
                else:
                    actual_minutes = min(stop_time - start_time, timedelta(minutes=action.time)).total_seconds() / 60
                    return await lang.text(
                        "moonlark_main.history.sleep.completed",
                        self.lang_str,
                        action.time,
                        actual_minutes,
                    )
            case "do":
                if stop_time is None:
                    return await lang.text(
                        "moonlark_main.history.do.in_progress",
                        self.lang_str,
                        action.information,
                        action.estimated_time,
                    )
                else:
                    return await lang.text(
                        "moonlark_main.history.do.completed",
                        self.lang_str,
                        action.information,
                        action.estimated_time,
                    )
            case "write_blog":
                return await lang.text("moonlark_main.history.write_blog", self.lang_str, action.title)
        return None

    async def get_additional_prompt(self) -> str:
        """生成额外提示信息（心情、即时记忆、笔记等）"""
        mood = self.status_manager.get_status()
        state_str = await lang.text(
            "prompt_group.state",
            self.lang_str,
            await lang.text(f"status.mood.{mood[0].value}", self.lang_str),
            self.status_manager.get_mood_retention(),
            mood[1],
        )

        # 即时记忆
        instant_mem_lines = []
        for mem in get_instant_memories():
            instant_mem_lines.append(
                await lang.text(
                    "prompt_group.instant_mem",
                    self.lang_str,
                    mem["create_time"].strftime("%Y-%m-%d %H:%M:%S"),
                    mem["expire_time"].strftime("%Y-%m-%d %H:%M:%S"),
                    mem["content"],
                )
            )
        instant_mem = "\n".join(instant_mem_lines)

        # 笔记
        note_manager = await get_context_notes("main_")
        notes = await note_manager.filter_note(instant_mem)
        notes = notes[0] + notes[1]

        # 博客状态
        blog_status_text = self.blog_writer.get_status_text() if hasattr(self.blog_writer, "get_status_text") else ""

        # 自主活动状态
        self_action_text = self.self_action_ctrl.get_status_text()

        return await lang.text(
            "moonlark_main.additional_info",
            self.lang_str,
            await lang.text("prompt_group.time", self.lang_str, datetime.now().isoformat()),
            state_str,
            (
                "\n".join([await self.format_note(note) for note in notes])
                if notes
                else await lang.text("prompt.note.none", self.lang_str)
            ),
            instant_mem,
            blog_status_text,
            self_action_text,
        )

    async def generate_system_prompt(self, sleep_action_only: bool = False, suggestions: str = "") -> str:
        """生成系统提示"""
        return await lang.text(
            "moonlark_main.prompt",
            self.lang_str,
            await lang.text("moonlark_main.action_sleep", self.lang_str),
            "" if sleep_action_only else await lang.text("moonlark_main.action_list", self.lang_str),
            await get_prompt_text("identity"),
            await self.get_friends(),
            await self.get_additional_prompt(),
            await self.get_recent_actions_text(self.lang_str),
            suggestions,
        )

    async def get_recent_actions_text(self, lang_str: str) -> str:
        """获取最近动作历史文本"""
        return "\n".join(
            [
                f"[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] {s}"
                for start_time, item, stop_time in self.action_history[-20:]
                if (s := await self.get_action_str(item, start_time, stop_time))
            ]
        )

    async def _has_active_session(self) -> bool:
        """检查是否存在活跃会话"""
        from ...utils.group import get_group_hot_score

        dt = datetime.now()
        for session in groups.values():
            if session.get_session_type() == "group":
                if session.last_interest is not None and session.last_interest >= 0.5:
                    ghot_score = (await get_group_hot_score(session.session_id))[2]
                    if ghot_score >= 10:
                        return True
            elif session.get_session_type() == "private":
                if session.cached_messages and (dt - session.cached_messages[-1]["send_time"]) <= timedelta(minutes=5):
                    return True
        return False

    async def process_timer(self) -> None:
        """定时器处理（每5分钟）"""
        dt = datetime.now()

        # 活跃会话存在时，延长 do action 的计时
        if self.state == StateEnum.BUSY and self.state_until and dt < self.state_until:
            if await self._has_active_session():
                self.state_until += timedelta(minutes=5)
                logger.debug(f"[MoonlarkMain] 检测到活跃会话，延长 state_until 至 {self.state_until}")
                return

        if self.state_until and dt > self.state_until:
            was_sleeping = self.state == StateEnum.SLEEPING
            self.state_until = None
            if self.state == StateEnum.BUSY:
                for action in self.action_history[::-1]:
                    if action[1].type == "do":
                        await self.request_think("task_finished", action[1].information)
                        break
            self.state = StateEnum.ACTIVATE
            if was_sleeping:
                for index in range(len(self.action_history)):
                    start_time, action, stop_time = self.action_history[-(index + 1)]
                    if action.type == "sleep" and stop_time is None:
                        self.action_history[-(index + 1)] = (start_time, action, dt)
                        break
                self.sleep_controller.on_wake_up()

        # 困倦值检查
        if self.state_until is None or dt >= self.state_until:
            if not self.action_history or dt >= self.action_history[-1][0] + timedelta(minutes=20):
                minutes_since_last = self.get_minutes_since_last_group_message()
                drowsiness_result = self.sleep_controller.check_drowsiness(self.consecutive_replies, minutes_since_last)
                if drowsiness_result == "sleep":
                    await self.request_think("ready_sleep", None)
                elif drowsiness_result == "drowsy":
                    drowsy_prompt = await lang.text("sleep.drowsy_prompt", self.lang_str)
                    for group in groups.values():
                        if group.get_session_type() == "group":
                            await group.add_event(drowsy_prompt, "probability")
                            break

        # 自主活动超时检查
        await self.self_action_ctrl.tick()

        await self.save_action_history()

    async def load_action_history(self) -> None:
        """从数据库加载动作历史"""
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
        """保存动作历史到数据库"""
        async with get_session() as session:
            await session.execute(delete(MainSessionActionHistory))
            for action in self.action_history:
                session.add(
                    MainSessionActionHistory(
                        start_time=action[0],
                        action=action[1].model_dump(),
                        end_time=action[2],
                    )
                )
            await session.commit()

    async def format_note(self, note: Note) -> str:
        created_time = datetime.fromtimestamp(note.created_time).strftime("%y-%m-%d")
        return await lang.text("prompt.note.format", self.lang_str, note.content, note.id, created_time)

    async def handle_action(self, action, fetcher: Optional[MessageFetcher] = None) -> None:
        """分发动作到子控制器"""
        match action.type:
            case "send_private_message":
                await self.send_private_message(action.target_nickname, action.subject)
            case "sleep":
                self.state = StateEnum.SLEEPING
                sleep_start = datetime.now()
                sleep_end = sleep_start + timedelta(minutes=action.time)
                self.state_until = sleep_end
                await self.trigger_sleep()
            case "do":
                self.state = StateEnum.BUSY
                self.state_until = datetime.now() + timedelta(minutes=action.estimated_time)
            case "fetch_chat_history":
                if fetcher is None:
                    raise ValueError("fetcher is None")
                await self.fetch_chat_history(action.context_id, fetcher)
            case "write_blog":
                if fetcher is None:
                    raise ValueError("fetcher is None")
                await self.write_blog(action.title, action.content, fetcher)

    async def fetch_chat_history(self, context_id: str, fetcher: MessageFetcher) -> None:
        if context_id in groups:
            session = groups[context_id]
            result = await session.get_cached_messages_string()
            result = result or await lang.text("moonlark_main.fetch_chat_history.no_messages", self.lang_str)
            fetcher.session.insert_message(generate_message(result, "user"))
        else:
            fetcher.session.insert_message(
                generate_message(
                    await lang.text("moonlark_main.fetch_chat_history.not_found", self.lang_str),
                    "user",
                )
            )

    async def send_private_message(self, target_nickname: str, subject: str) -> None:
        async with get_session() as session:
            for friend_record in await session.scalars(select(PrivateChatSession)):
                from ...utils.larkuser import get_user

                user = await get_user(friend_record.user_id)
                if user.nickname == target_nickname:
                    bot_id = friend_record.bot_id
                    user_id = user.user_id
                    break
            else:
                raise ValueError("No such friend")

        self._current_action_send_private_user_id = user_id
        bot = get_bot(bot_id)
        await send_proactive_private_message(bot, user_id, subject)

    async def write_blog(self, title: str, content: str, fetcher: MessageFetcher) -> None:
        await create_blog_post(title, content)
        result = await lang.text("moonlark_main.write_blog.success", self.lang_str, title)
        fetcher.session.insert_message(generate_message(result, "user"))

    async def request_action_decision(
        self, do: str, session_info: str, cached_messages: str, duration: Optional[int] = None
    ) -> ActionDecisionResponse:
        system_prompt = await lang.text(
            "moonlark_main.action_request.system",
            self.lang_str,
            await get_prompt_text("identity"),
            await self.get_additional_prompt(),
            await self.get_recent_actions_text(self.lang_str),
        )
        user_prompt = await lang.text(
            "moonlark_main.action_request.user",
            self.lang_str,
            session_info,
            do,
            str(duration) if duration else await lang.text("moonlark_main.action_request.no_duration", self.lang_str),
            cached_messages,
        )
        return await fetch_json(
            [generate_message(system_prompt, "system"), generate_message(user_prompt, "user")],
            ActionDecisionResponse,
            identify="Chat - Action Request Decision",
            reasoning_effort="low",
        )

    async def submit_action_decision(
        self, session_id: str, do: str, duration: Optional[int] = None, future: Optional[asyncio.Future] = None
    ) -> None:
        """处理来自子会话的动作执行申请"""
        try:
            session_info = f"会话ID: {session_id}"
            if session_id in groups:
                session_info = await groups[session_id].get_session_name()

            cached_messages = ""
            if session_id in groups:
                cached_messages = await groups[session_id].get_cached_messages_string(
                    length=10, include_self_message=True
                )
            if not cached_messages:
                cached_messages = await lang.text("moonlark_main.fetch_chat_history.no_messages", self.lang_str)

            result = await self.request_action_decision(do, session_info, cached_messages, duration)
            approved = result.approved
            allocated_time = result.allocated_time

            if approved and allocated_time > 0:
                await self.handle_action(CustomAction(type="do", information=do, estimated_time=allocated_time))

            if future and not future.done():
                future.set_result(
                    await lang.text(
                        (
                            "moonlark_main.action_request.result_approved"
                            if approved
                            else "moonlark_main.action_request.result_denied"
                        ),
                        self.lang_str,
                        do,
                        allocated_time,
                    )
                )
        except Exception as e:
            logger.exception(e)
            if future and not future.done():
                future.set_result(await lang.text("moonlark_main.action_request.error", self.lang_str, str(e)))

    async def request_sleep_decision(self, session_info: str, cached_messages: str) -> SleepDecisionResponse:
        system_prompt = await lang.text(
            "moonlark_main.sleep_request.system",
            self.lang_str,
            await get_prompt_text("identity"),
            await self.get_additional_prompt(),
            await self.get_recent_actions_text(self.lang_str),
        )
        user_prompt = await lang.text(
            "moonlark_main.sleep_request.user",
            self.lang_str,
            session_info,
            cached_messages,
        )
        return await fetch_json(
            [generate_message(system_prompt, "system"), generate_message(user_prompt, "user")],
            SleepDecisionResponse,
            reasoning_effort="low",
            identify="MoonlarkMain - Sleep Request Decision",
        )

    async def submit_sleep_request(self, session_id: str, future: Optional[asyncio.Future] = None) -> None:
        """处理来自子会话的睡觉申请"""
        try:
            session_info = f"会话ID: {session_id}"
            if session_id in groups:
                session_info = await groups[session_id].get_session_name()

            cached_messages = ""
            if session_id in groups:
                cached_messages = await groups[session_id].get_cached_messages_string(
                    length=10, include_self_message=True
                )
            if not cached_messages:
                cached_messages = await lang.text("moonlark_main.fetch_chat_history.no_messages", self.lang_str)

            result = await self.request_sleep_decision(session_info, cached_messages)
            approved = result.approved

            if approved:
                self.state = StateEnum.SLEEPING
                sleep_minutes = 20
                sleep_start = datetime.now()
                sleep_end = sleep_start + timedelta(minutes=sleep_minutes)
                self.state_until = sleep_end
                self.action_history.append((sleep_start, RestAction(type="sleep", time=sleep_minutes), None))
                await self.trigger_sleep()

            if future and not future.done():
                future.set_result(
                    await lang.text(
                        (
                            "moonlark_main.sleep_request.result_approved"
                            if approved
                            else "moonlark_main.sleep_request.result_denied"
                        ),
                        self.lang_str,
                    )
                )
        except Exception as e:
            logger.exception(e)
            if future and not future.done():
                future.set_result(await lang.text("moonlark_main.sleep_request.error", self.lang_str, str(e)))

    async def submit_sleep_decision(
        self,
        session_id: str,
        deal_type: Literal["ready", "delay"],
        delay_minutes: Optional[int] = None,
        reason: Optional[str] = None,
        future: Optional[asyncio.Future] = None,
    ) -> None:
        """处理来自子会话的睡眠决策"""
        try:
            if deal_type == "ready":
                self.state = StateEnum.SLEEPING
                sleep_minutes = 20
                sleep_start = datetime.now()
                sleep_end = sleep_start + timedelta(minutes=sleep_minutes)
                self.state_until = sleep_end
                self.action_history.append((sleep_start, RestAction(type="sleep", time=sleep_minutes), None))
                await self.trigger_sleep()

                if future and not future.done():
                    future.set_result(await lang.text("moonlark_main.sleep_decision.ready_approved", self.lang_str))
            else:
                delay = min(delay_minutes or 5, 30)
                self.state_until = datetime.now() + timedelta(minutes=delay)

                if future and not future.done():
                    future.set_result(
                        await lang.text(
                            "moonlark_main.sleep_decision.delay_approved",
                            self.lang_str,
                            delay,
                            reason or await lang.text("moonlark_main.sleep_decision.no_reason", self.lang_str),
                        )
                    )
        except Exception as e:
            logger.exception(e)
            if future and not future.done():
                future.set_result(await lang.text("moonlark_main.sleep_decision.error", self.lang_str, str(e)))

    async def wake_up(self, session: Optional["BaseSession"] = None) -> None:
        if self.state != StateEnum.SLEEPING:
            return
        dt = datetime.now()
        interrupted = False
        result = None
        for index in range(len(self.action_history)):
            start_time, action, stop_time = self.action_history[-(index + 1)]
            if action.type == "sleep" and stop_time is None:
                self.action_history[-(index + 1)] = (start_time, action, dt)
                if start_time + timedelta(minutes=action.time) > dt:
                    interrupted = True
                    result = await lang.text(
                        "moonlark_main.wake_up.interrupted",
                        self.lang_str,
                        dt.strftime("%H:%M:%S"),
                        action.time,
                        (dt - start_time).total_seconds() / 60,
                    )
                break
        self.state = StateEnum.ACTIVATE
        self.sleep_controller.on_wake_up()
        if interrupted and result and session:
            await session.processor.openai_messages.append_user_message(result)

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
                from ...utils.larkuser import get_user

                user = await get_user(friend_record.user_id)
                friend_list.append(
                    await lang.text(
                        "moonlark_main.friend",
                        self.lang_str,
                        user.get_nickname(),
                        user.get_display_fav(),
                        await user.get_fav_level(),
                        datetime.fromtimestamp(friend_record.last_message_time).isoformat(),
                        (
                            datetime.fromtimestamp(friend_record.last_proactive_message_time).isoformat()
                            if friend_record.last_proactive_message_time
                            else await lang.text("moonlark_main.not_chatted_private", self.lang_str)
                        ),
                    )
                )
        return await lang.text(
            "moonlark_main.friends",
            self.lang_str,
            "\n".join(friend_list),
            await get_prompt_text("favorability"),
        )


moonlark_main = MoonlarkMain()


async def init_moonlark_main() -> None:
    """初始化 moonlark_main，从数据库加载数据"""
    await moonlark_main.load_action_history()
