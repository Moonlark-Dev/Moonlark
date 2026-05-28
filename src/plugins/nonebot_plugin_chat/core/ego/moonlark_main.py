"""Moonlark 意识主模块

严格按照 MoonlarkEgo0528.txt 设计文档实现。
不兼容旧代码，全部重构。
"""

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal, Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_openai.utils.chat import fetch_json, fetch_message
from nonebot_plugin_openai.utils.message import generate_message
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ...lang import lang
from ...models import (
    ActionDecisionResponse,
    EgoDecisionResponse,
    Note,
    PrivateChatSession,
)
from ...utils.instant_mem import get_instant_memories
from ...utils.note_manager import get_context_notes
from ...utils.prompt import get_prompt_text
from ...utils.status_manager import get_status_manager
from ..session import groups
from .sleep_controller import SleepController
from .blog_writer import BlogWriter
from .proactive_chat_ctrl import ProactiveChatController
from .self_action_ctrl import SelfActionController
from .action_advisor import ActionAdvisor


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

        # 心情：直接用外部 StatusManager
        self.status_manager = get_status_manager()

        # 内部状态
        self.state: dict = {
            "sleep_mode": False,
            "last_decision_time": None,
            "decision_history": [],
            "instant_memory_summary": "",
        }

        # 配置
        self.decision_interval_normal = 600   # 10分钟
        self.decision_interval_sleep = 1800   # 30分钟

        # MoonlarkMain 定时器（每5分钟检查是否该执行 request_think）
        scheduler.scheduled_job("interval", minutes=5, id="moonlark_main_timer")(self._on_timer)

    # ========================================================================
    # 核心方法
    # ========================================================================

    async def summary_instant_memory(self) -> str:
        memories = get_instant_memories()
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

    async def request_think(
        self,
        trigger_reason: str = "timer",
        request_text: Optional[str] = None,
        trigger_from: Optional[str] = None,
    ) -> None:
        logger.info(f"[MoonlarkMain] request_think, reason={trigger_reason}")

        # 睡眠模式
        if self.state["sleep_mode"]:
            sleep_result = await self.sleep_controller.request_think()
            if sleep_result and sleep_result.get("sleep_decision") == "wake_up":
                await self.sleep_controller.wake_up()
                self._update_decision_history("wake_up")
            return

        # 清醒模式
        summary = await self.summary_instant_memory()
        state_info = self._collect_state()
        suggestions = self.action_advisor.get_suggestions(state_info, summary)

        system_prompt = await self._generate_system_prompt(summary, state_info, suggestions)
        user_prompt = await self._generate_user_prompt(trigger_reason, request_text, trigger_from)

        try:
            decision = await fetch_json(
                [
                    generate_message(system_prompt, "system"),
                    generate_message(user_prompt, "user"),
                ],
                EgoDecisionResponse,
                identify="MoonlarkMain - Request Think",
                reasoning_effort="medium",
            )
        except Exception as e:
            logger.exception(f"[MoonlarkMain] LLM 决策失败: {e}")
            return

        await self._execute_decision(decision)
        self.state["last_decision_time"] = datetime.now()

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

        return {
            "sleep_mode": self.state["sleep_mode"],
            "blog_status": blog_status["status"],
            "draft": blog_status["draft"],
            "cooldown_remaining": blog_status["cooldown_remaining"],
            "last_blog_time": blog_status["last_blog_time"],
            "proactive_info": proactive_info,
            "current_activity": self.self_action.current_activity,
            "current_activity_remaining": self._get_activity_remaining(),
            "mood": {
                "emotion": mood.value,
                "intensity": self.status_manager.get_mood_retention(),
                "reason": mood_reason or "",
            },
        }

    def _get_activity_remaining(self) -> int:
        if not self.self_action.current_activity or not self.self_action.activity_start_time:
            return 0
        if self.self_action.activity_duration == 0:
            return -1
        elapsed = (datetime.now() - self.self_action.activity_start_time).total_seconds()
        return max(0, int(self.self_action.activity_duration - elapsed))

    def _update_decision_history(self, action_desc: str) -> None:
        self.state["decision_history"].append({
            "time": datetime.now().isoformat(),
            "action": action_desc,
        })
        self.state["decision_history"] = self.state["decision_history"][-5:]

    # ========================================================================
    # Prompt 生成
    # ========================================================================

    async def _generate_system_prompt(
        self, summary: str, state_info: dict, suggestions: str
    ) -> str:
        identity_prompt = await get_prompt_text("identity")

        draft = state_info.get("draft")
        blog_text = f"草稿《{draft['topic']}》，{draft['word_count']}字，续写{draft['continue_count']}次" if draft else "无草稿"

        proactive_info = state_info.get("proactive_info", {})
        if proactive_info:
            parts = [f"{uid}: {info.get('last_chat', '').strftime('%H:%M')}" for uid, info in proactive_info.items() if info.get("last_chat")]
            last_private_text = ", ".join(parts) if parts else "无"
        else:
            last_private_text = "无"

        activity = state_info.get("current_activity")
        remaining = state_info.get("current_activity_remaining", 0)
        activity_text = f"{activity}（剩余{remaining}秒）" if activity else "无"

        history_lines = [f"[{h['time']}] {h['action']}" for h in self.state["decision_history"]]
        history_text = "\n".join(history_lines) if history_lines else "无"

        last_time = self.state["last_decision_time"]
        elapsed = int((datetime.now() - last_time).total_seconds() / 60) if last_time else 0

        mood = state_info["mood"]

        return await lang.text(
            "moonlark_main.think.system",
            self.lang_str,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            str(elapsed),
            identity_prompt,
            summary,
            str(self.state["sleep_mode"]),
            last_private_text,
            blog_text,
            mood["emotion"],
            str(mood["intensity"]),
            mood["reason"],
            activity_text,
            suggestions,
            history_text,
        )

    async def _generate_user_prompt(
        self,
        trigger_reason: str,
        request_text: Optional[str] = None,
        trigger_from: Optional[str] = None,
    ) -> str:
        return await lang.text(
            "moonlark_main.think.user",
            self.lang_str,
            trigger_reason,
            request_text or "",
            trigger_from or "",
        )

    # ========================================================================
    # 决策执行
    # ========================================================================

    async def _execute_decision(self, decision: EgoDecisionResponse) -> None:
        """解析并执行 LLM 决策结果（Pydantic model）"""
        actions_taken = []

        # sleep_decision
        if decision.sleep_decision:
            if decision.sleep_decision == "go_to_sleep":
                await self.sleep_controller.handle_tired()
                actions_taken.append("go_to_sleep")
            elif decision.sleep_decision == "wake_up" and self.state["sleep_mode"]:
                await self.sleep_controller.wake_up()
                actions_taken.append("wake_up")

        # blog_action
        if decision.blog_action and decision.blog_action != "skip":
            await self.blog_writer.handle_action(decision.blog_action)
            actions_taken.append(f"blog: {decision.blog_action}")

        # private_chat
        if decision.private_chat:
            await self.proactive_chat.send_private_message(
                decision.private_chat.target,
                decision.private_chat.reason,
                decision.private_chat.content_hint,
            )
            actions_taken.append(f"private_chat: {decision.private_chat.target}")

        # self_action（duration 由 SelfActionController 单独请求 LLM 生成）
        if decision.self_action and decision.self_action != "nothing":
            await self.self_action.start_activity(decision.self_action)
            actions_taken.append(f"self_action: {decision.self_action}")

        if actions_taken:
            self._update_decision_history(", ".join(actions_taken))
        else:
            self._update_decision_history("no_action")

    def _on_timer(self) -> None:
        now = datetime.now()
        interval = self.decision_interval_sleep if self.state["sleep_mode"] else self.decision_interval_normal
        last = self.state["last_decision_time"]
        if last is None or (now - last).total_seconds() >= interval:
            asyncio.create_task(self.request_think("timer"))

    # ========================================================================
    # 供外部调用的接口
    # ========================================================================

    def on_message_received(self) -> None:
        self.sleep_controller.handle_message()

    def on_reply_sent(self) -> None:
        self.sleep_controller.handle_reply()

    def on_private_message_replied(self, user_id: str) -> None:
        self.proactive_chat.update_reply_status(user_id, replied=True)

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
                await self._get_additional_prompt(),
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
                await self.self_action.start_activity(do, duration_seconds=result.allocated_time * 60)

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
            if deal_type == "ready":
                await self.sleep_controller.handle_tired()
                if future and not future.done():
                    future.set_result("已进入睡眠模式。")
            else:
                delay = min(delay_minutes or 5, 30)
                if future and not future.done():
                    future.set_result(f"已延迟 {delay} 分钟睡觉。" + (f"原因: {reason}" if reason else ""))
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

    async def _get_additional_prompt(self) -> str:
        mood, mood_reason = self.status_manager.get_status()
        state_str = await lang.text(
            "prompt_group.state", self.lang_str,
            await lang.text(f"status.mood.{mood.value}", self.lang_str),
            self.status_manager.get_mood_retention(),
            mood_reason,
        )

        instant_mem_lines = []
        for mem in get_instant_memories():
            instant_mem_lines.append(
                await lang.text("prompt_group.instant_mem", self.lang_str,
                    mem["create_time"].strftime("%Y-%m-%d %H:%M:%S"),
                    mem["expire_time"].strftime("%Y-%m-%d %H:%M:%S"),
                    mem["content"])
            )
        instant_mem = "\n".join(instant_mem_lines)

        note_manager = await get_context_notes("main_")
        notes = await note_manager.filter_note(instant_mem)
        notes = notes[0] + notes[1]

        return await lang.text(
            "moonlark_main.additional_info", self.lang_str,
            await lang.text("prompt_group.time", self.lang_str, datetime.now().isoformat()),
            state_str,
            "\n".join([await self._format_note(n) for n in notes]) if notes else await lang.text("prompt.note.none", self.lang_str),
            instant_mem,
        )

    async def _format_note(self, note: Note) -> str:
        created_time = datetime.fromtimestamp(note.created_time).strftime("%y-%m-%d")
        return await lang.text("prompt.note.format", self.lang_str, note.content, note.id, created_time)

    async def get_friends(self) -> str:
        friend_list = []
        async with get_session() as session:
            for friend_record in await session.scalars(select(PrivateChatSession)):
                from ...utils.larkuser import get_user
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
    logger.info("[MoonlarkMain] 初始化完成")
