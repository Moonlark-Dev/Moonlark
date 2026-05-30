"""Moonlark 意识主模块

严格按照 MoonlarkEgo0528.txt 设计文档实现。
不兼容旧代码，全部重构。
"""

import asyncio
from datetime import datetime
from typing import Any, Literal, Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_openai.types import AsyncFunction, FunctionParameter
from nonebot_plugin_openai.utils.chat import MessageFetcher, fetch_json, fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ...lang import lang
from ...models import (
    ActionDecisionResponse,
    PrivateChatSession,
)
from ...utils.instant_mem import get_instant_memories
from ...utils.prompt import get_prompt_text
from ...utils.status_manager import get_status_manager
from ..session import groups
from .action_advisor import ActionAdvisor
from .blog_writer import BlogWriter
from .proactive_chat_ctrl import ProactiveChatController
from .self_action_ctrl import SelfActionController
from .sleep_controller import SleepController


class ActionDecider:

    fetcher: MessageFetcher

    def __init__(self, moonlark_main: "MoonlarkMain") -> None:
        self.moonlark_main = moonlark_main
        self.lang = moonlark_main.lang_str
        self.lock = asyncio.Lock()

    async def setup(self) -> None:
        messages = [
            generate_message(
                await lang.text(
                    "moonlark_main.prompt",
                    self.moonlark_main.lang_str,
                    await get_prompt_text("identity"),
                    await self.moonlark_main.get_friends(),
                ),
                "system",
            ),
        ]
        fetcher = await MessageFetcher.create(
            messages,
            identify="ActionDecider",
            functions=[
                AsyncFunction(
                    func=self.moonlark_main.sleep_controller.sleep,
                    description=await lang.text("moonlark_main.tools.sleep.description", self.lang),
                    parameters={},
                ),
                AsyncFunction(
                    func=self.moonlark_main.self_action.start_action,
                    description=await lang.text("moonlark_main.tools.start_action.description", self.lang),
                    parameters={
                        "activity": FunctionParameter(
                            type="string",
                            description=await lang.text("moonlark_main.tools.start_action.activity", self.lang),
                            required=True,
                        ),
                    },
                ),
                AsyncFunction(
                    func=self.moonlark_main.blog_writer.start_new_blog,
                    description=await lang.text("moonlark_main.tools.start_new_blog.description", self.lang),
                    parameters={
                        "topic": FunctionParameter(
                            type="string",
                            description=await lang.text("moonlark_main.tools.start_new_blog.topic", self.lang),
                            required=True,
                        ),
                    },
                ),
                AsyncFunction(
                    func=self.moonlark_main.blog_writer.blog_publish_draft,
                    description=await lang.text("moonlark_main.tools.blog_publish_draft.description", self.lang),
                    parameters={},
                ),
                AsyncFunction(
                    func=self.moonlark_main.blog_writer.blog_drop_draft,
                    description=await lang.text("moonlark_main.tools.blog_drop_draft.description", self.lang),
                    parameters={},
                ),
                AsyncFunction(
                    func=self.moonlark_main.blog_writer.get_blog_state,
                    description=await lang.text("moonlark_main.tools.get_blog_state.description", self.lang),
                    parameters={},
                ),
                AsyncFunction(
                    func=self.moonlark_main.proactive_chat.send_private_message,
                    description=await lang.text("moonlark_main.tools.send_private_message.description", self.lang),
                    parameters={
                        "target": FunctionParameter(
                            type="string",
                            description=await lang.text("moonlark_main.tools.send_private_message.target", self.lang),
                            required=True,
                        ),
                        "content_hint": FunctionParameter(
                            type="string",
                            description=await lang.text("moonlark_main.tools.send_private_message.content_hint", self.lang),
                            required=True,
                        ),
                        "wait_for": FunctionParameter(
                            type="integer",
                            description=await lang.text("moonlark_main.tools.send_private_message.wait_for", self.lang),
                            required=False,
                        ),
                    },
                ),
            ],
            pre_function_call=self.pre_function_call,
            reasoning_effort="medium",
        )
        self.fetcher = fetcher

    async def loop(self) -> None:
        if self.lock.locked():
            return
        async with self.lock:
            await asyncio.sleep(60)
            await self.on_event("timer")
            async for message in self.fetcher.fetch_message_stream():
                logger.info(f"[ActionDecider] {message}")
                last_summary_time = self.moonlark_main.state.get("last_summary_time")
                memories = get_instant_memories()
                if last_summary_time:
                    memories = [m for m in memories if m["create_time"] > last_summary_time]
                if memories:
                    await self.on_event("new_group_event")

    async def pre_function_call(self, call_id: str, name: str, params: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        self.moonlark_main._update_decision_history(f"{name}({params})")
        return call_id, name, params

    async def on_event(self, reason: str) -> None:
        self.fetcher.session.insert_message(
            generate_message(
                await lang.text(
                    "moonlark_main.user",
                    self.lang,
                    reason,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    await self.moonlark_main.summary_instant_memory(),
                ),
            ),
        )

    def reset(self) -> None:
        if hasattr(self, "fetcher"):
            del self.fetcher


class MoonlarkMain:
    """Moonlark 意识主模块"""

    def __init__(self, lang_str: str = "zh_hans") -> None:
        self.lang_str = lang_str

        # 子控制器
        self.sleep_controller = SleepController(self)
        self.blog_writer = BlogWriter(self)
        self.proactive_chat = ProactiveChatController(self)
        self.self_action = SelfActionController(self)
        self.action_advisor = ActionAdvisor(self)
        self.action_decider = ActionDecider(self)

        # 心情：直接用外部 StatusManager
        self.status_manager = get_status_manager()

        # 内部状态
        self.state: dict = {
            "sleep_mode": False,
            "last_decision_time": None,
            "decision_history": [],
            "instant_memory_summary": "",
            "last_summary_time": None,
        }

        # MoonlarkMain 定时器（每10分钟，清醒时触发 action_decider.loop）
        scheduler.scheduled_job("interval", minutes=10, id="moonlark_main_timer")(self._on_timer)

    async def summary_instant_memory(self) -> str:
        last_summary_time = self.state.get("last_summary_time")
        memories = get_instant_memories()
        if last_summary_time:
            memories = [m for m in memories if m["create_time"] > last_summary_time]
        self.state["last_summary_time"] = datetime.now()
        if not memories:
            self.state["instant_memory_summary"] = "暂无群聊记忆。"
            return self.state["instant_memory_summary"]

        memory_lines = []
        for mem in memories:
            time_str = mem["create_time"].strftime("%H:%M")
            ctx = mem.get("name", mem.get("ctx_id", ""))
            memory_lines.append(f"[{time_str}][{ctx}] {mem['content']}")

        try:
            summary = await fetch_message(
                [
                    generate_message(
                        await lang.text("moonlark_main.summarize.system", self.lang_str),
                        "system",
                    ),
                    generate_message(
                        await lang.text("moonlark_main.summarize.user", self.lang_str, "\n".join(memory_lines)),
                        "user",
                    ),
                ],
                identify="MoonlarkMain - Summary Instant Memory",
                reasoning_effort="low",
            )
            self.state["instant_memory_summary"] = summary
        except Exception as e:
            logger.exception(f"[MoonlarkMain] 汇总即时记忆失败: {e}")
            self.state["instant_memory_summary"] = "记忆汇总失败。"

        return self.state["instant_memory_summary"]

    async def handle_mention(self, chat_context: list) -> bool:
        """当被 @ 或提及时调用。

        若不在睡眠状态，返回 False（正常回复）。
        若在睡眠状态，交给 SleepController 判断是否唤醒（内部处理 wake_up）。
        """
        if not self.state["sleep_mode"]:
            return False
        return await self.sleep_controller.handle_mention(chat_context)

    # ========================================================================
    # 状态收集
    # ========================================================================

    def _collect_state(self) -> dict:
        mood, mood_reason = self.status_manager.get_status()
        blog_status = self.blog_writer.get_status()
        proactive_info = self.proactive_chat.get_cooldown_info()
        self_action_status = self.self_action.get_status()

        return {
            "sleep_mode": self.state["sleep_mode"],
            "blog_status": blog_status["status"],
            "draft": blog_status["draft"],
            "cooldown_remaining": blog_status["cooldown_remaining"],
            "last_blog_time": blog_status["last_blog_time"],
            "proactive_info": proactive_info,
            "self_action": self_action_status,
            "mood": {
                "emotion": mood.value,
                "intensity": self.status_manager.get_mood_retention(),
                "reason": mood_reason or "",
            },
        }

    def _update_decision_history(self, action_desc: str) -> None:
        self.state["decision_history"].append({
            "time": datetime.now().isoformat(),
            "action": action_desc,
        })
        self.state["decision_history"] = self.state["decision_history"][-5:]

    # ========================================================================
    # 定时器
    # ========================================================================

    async def _on_timer(self) -> None:
        """定时器回调（每10分钟）。睡眠时不触发，由 SleepController 自己的定时器处理。"""
        if self.state["sleep_mode"]:
            return
        asyncio.create_task(self.action_decider.loop())

    # ========================================================================
    # 供外部调用的接口
    # ========================================================================

    def on_message_received(self) -> None:
        self.sleep_controller.handle_message()

    def on_reply_sent(self) -> None:
        self.sleep_controller.handle_reply()

    async def on_private_message_replied(self, user_id: str) -> None:
        await self.proactive_chat.update_reply_status(user_id, replied=True)

    def get_minutes_since_last_group_message(self) -> float:
        """获取距离最近一次群内发言的分钟数"""
        from ..session import groups
        dt = datetime.now()
        last_msg_time = None
        for group in groups.values():
            if group.cached_messages:
                msg_time = group.cached_messages[-1]["send_time"]
                if last_msg_time is None or msg_time > last_msg_time:
                    last_msg_time = msg_time
        if last_msg_time is None:
            return 60.0
        return (dt - last_msg_time).total_seconds() / 60.0

    # ========================================================================
    # 子会话接口（供 session.base 调用）
    # ========================================================================

    async def submit_action_decision(
        self, session_id: str, do: str, duration: Optional[int] = None,
        future: Optional[asyncio.Future] = None,
    ) -> None:
        try:
            session_info = f"会话ID: {session_id}"
            if session_id in groups:
                session_info = await groups[session_id].get_session_name()

            cached_messages = ""
            if session_id in groups:
                cached_messages = await groups[session_id].get_cached_messages_string(length=10, include_self_message=True)

            system_prompt = await lang.text(
                "moonlark_main.action_request.system", self.lang_str,
                await get_prompt_text("identity"),
                self._get_additional_prompt_text(),
                self._get_recent_actions_text(),
            )
            user_prompt = await lang.text(
                "moonlark_main.action_request.user", self.lang_str,
                session_info, do, str(duration) if duration else "未指定", cached_messages or "无消息",
            )
            result = await fetch_json(
                [generate_message(system_prompt, "system"), generate_message(user_prompt, "user")],
                ActionDecisionResponse,
                identify="MoonlarkMain - Action Request Decision",
                reasoning_effort="low",
            )

            if result.approved and result.allocated_time > 0:
                await self.self_action.start_action(do)

            if future and not future.done():
                key = "moonlark_main.action_request.result_approved" if result.approved else "moonlark_main.action_request.result_denied"
                future.set_result(await lang.text(key, self.lang_str, do, result.allocated_time))
        except Exception as e:
            logger.exception(e)
            if future and not future.done():
                future.set_result(f"决策失败: {e}")

    async def submit_sleep_request(self, session_id: str, future: Optional[asyncio.Future] = None) -> None:
        if future and not future.done():
            future.set_result("已提交睡觉申请，等待决策...")

    async def submit_sleep_decision(
        self, session_id: str, deal_type: Literal["ready", "delay"],
        delay_minutes: Optional[int] = None, reason: Optional[str] = None,
        future: Optional[asyncio.Future] = None,
    ) -> None:
        try:
            result = await self.sleep_controller.submit_sleep_decision(
                deal_type, delay_minutes or 5, reason or "",
            )
            if future and not future.done():
                future.set_result(result)
        except Exception as e:
            logger.exception(e)
            if future and not future.done():
                future.set_result(f"决策失败: {e}")

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _get_recent_actions_text(self) -> str:
        lines = [f"[{h['time']}] {h['action']}" for h in self.state["decision_history"]]
        return "\n".join(lines) if lines else ""

    def _get_additional_prompt_text(self) -> str:
        mood, mood_reason = self.status_manager.get_status()
        return f"心情：{mood.value} (强度: {self.status_manager.get_mood_retention():.2f}; 原因: {mood_reason or '无'})"

    async def get_friends(self) -> str:
        friend_list = []
        async with get_session() as session:
            for friend_record in await session.scalars(select(PrivateChatSession)):
                from nonebot_plugin_larkuser.utils.user import get_user
                user = await get_user(friend_record.user_id)
                friend_list.append(
                    await lang.text("moonlark_main.friend", self.lang_str,
                        user.get_nickname(), user.get_display_fav(), await user.get_fav_level(),
                        datetime.fromtimestamp(friend_record.last_message_time).isoformat(),
                        datetime.fromtimestamp(friend_record.last_proactive_message_time).isoformat()
                        if friend_record.last_proactive_message_time
                        else await lang.text("moonlark_main.not_chatted_private", self.lang_str))
                )
        return await lang.text("moonlark_main.friends", self.lang_str, "\n".join(friend_list), await get_prompt_text("favorability"))


# 全局实例
moonlark_main = MoonlarkMain()


async def init_moonlark_main() -> None:
    await moonlark_main.action_decider.setup()
    logger.info("[MoonlarkMain] 初始化完成")
