"""Moonlark 意识主模块

严格按照 MoonlarkEgo0528.txt 设计文档实现。
EGO 模块的核心，负责：
- 维护全局状态（睡眠标志、博客草稿、私聊记录、心情值、活动计时等）
- 周期性执行 request_think 生成动作决策
- 调用子控制器执行具体动作
- 提供 summary_instant_memory 方法聚合即时记忆
"""

import asyncio
import json
import re
import traceback
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal, Optional

from nonebot import get_bot, logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_openai.utils.chat import fetch_json, fetch_message, MessageFetcher
from nonebot_plugin_openai.utils.message import generate_message
from nonebot_plugin_orm import get_session
from sqlalchemy import select

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


class MoonlarkMain:
    """Moonlark 意识主模块

    按设计文档：
    - 维护所有全局状态
    - 周期性执行 request_think 生成动作决策
    - 调用子控制器执行具体动作
    - 提供 summary_instant_memory 方法
    """

    def __init__(self, lang_str: str = "zh_hans") -> None:
        self.lang_str = lang_str

        # 子控制器
        self.sleep_controller = SleepController(self)
        self.blog_writer = BlogWriter(self)
        self.proactive_chat = ProactiveChatController(self)
        self.self_action = SelfActionController(self)
        self.action_advisor = ActionAdvisor(self)

        # 内部状态（按设计文档的 state 字典）
        self.state: dict = {
            "sleep_mode": False,
            "mood": {"emotion": "neutral", "intensity": 0.5, "reason": ""},
            "last_decision_time": None,
            "decision_history": [],       # 最近5次决策记录
            "instant_memory_summary": "",  # 当前群聊总结
        }

        # 配置（按设计文档）
        self.decision_interval_normal = 600   # 10分钟
        self.decision_interval_sleep = 1800   # 30分钟

        # 状态管理器（心情系统）
        self.status_manager = StatusManager()

        # 兼容旧代码的属性
        self.action_history: list[tuple[datetime, object, Optional[datetime]]] = []
        self.state_until: Optional[datetime] = None
        self.consecutive_replies: int = 0

        # 定时器注册
        # 注意：按设计文档，定时器间隔由 sleep_mode 动态决定
        # 这里注册一个基础定时器，内部根据状态判断
        scheduler.scheduled_job("interval", minutes=5, id="moonlark_main_timer")(self._on_timer)

    # ========================================================================
    # 核心方法：summary_instant_memory
    # ========================================================================

    async def summary_instant_memory(self) -> str:
        """聚合各 chat session 的即时记忆并生成群聊总结

        按设计文档：
        1. 遍历所有活跃的 chat session，请求每个 session 生成即时记忆摘要
        2. 将所有 session 摘要合并，调用 LLM 生成全局群聊总结（限 200 token）
        3. 更新 state["instant_memory_summary"] 并返回
        """
        memories = get_instant_memories()
        if not memories:
            self.state["instant_memory_summary"] = "暂无群聊记忆。"
            return self.state["instant_memory_summary"]

        # 格式化记忆
        memory_lines = []
        for mem in memories:
            time_str = mem["create_time"].strftime("%H:%M")
            ctx = mem.get("name", mem.get("ctx_id", ""))
            memory_lines.append(f"[{time_str}][{ctx}] {mem['content']}")

        # 调用 LLM 生成总结
        try:
            summary = await fetch_message(
                [
                    generate_message(
                        await lang.text("moonlark_main.summarize.system", self.lang_str),
                        "system",
                    ),
                    generate_message(
                        await lang.text(
                            "moonlark_main.summarize.user",
                            self.lang_str,
                            "\n".join(memory_lines),
                        ),
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

    # ========================================================================
    # 核心方法：request_think
    # ========================================================================

    async def request_think(
        self,
        trigger_reason: str = "timer",
        request_text: Optional[str] = None,
        trigger_from: Optional[str] = None,
    ) -> None:
        """定时任务入口，生成动作决策

        按设计文档：
        1. 若 sleep_mode == True：调用 sleep_controller.request_think()
        2. 否则：
           - 调用 summary_instant_memory() 获取最新群聊总结
           - 收集内部状态
           - 调用 ActionAdvisor.get_suggestions() 获取决策建议
           - 调用 LLM 生成决策 JSON
           - 解析决策，调用对应子控制器
           - 更新 decision_history
        """
        logger.info(f"[MoonlarkMain] request_think triggered, reason={trigger_reason}")

        # 若在睡眠模式，走睡眠决策流程
        if self.state["sleep_mode"]:
            sleep_result = await self.sleep_controller.request_think()
            if sleep_result and sleep_result.get("sleep_decision") == "wake_up":
                await self.sleep_controller.wake_up()
                self.state["sleep_mode"] = False
                self._update_decision_history("wake_up")
            return

        # 清醒模式：执行完整决策流程
        # 1. 汇总即时记忆
        summary = await self.summary_instant_memory()

        # 2. 收集内部状态
        state_info = self._collect_state()

        # 3. 获取 ActionAdvisor 建议
        suggestions = self.action_advisor.get_suggestions(state_info, summary)

        # 4. 组装 Prompt
        system_prompt = await self._generate_system_prompt(summary, state_info, suggestions)
        user_prompt = await self._generate_user_prompt(trigger_reason, request_text, trigger_from)

        # 5. 调用 LLM 生成决策
        try:
            response = await fetch_json(
                [
                    generate_message(system_prompt, "system"),
                    generate_message(user_prompt, "user"),
                ],
                identify="MoonlarkMain - Request Think",
                reasoning_effort="medium",
            )
        except Exception as e:
            logger.exception(f"[MoonlarkMain] LLM 决策失败: {e}")
            return

        # 6. 解析并执行决策
        await self._execute_decision(response)

        # 7. 更新状态
        self.state["last_decision_time"] = datetime.now()

    # ========================================================================
    # 核心方法：handle_mention
    # ========================================================================

    async def handle_mention(self, chat_context: list) -> bool:
        """当 processor 检测到 Moonlark 被 @ 或提及时调用

        按设计文档：
        1. 若不在睡眠状态，返回 False（正常回复）
        2. 若在睡眠状态，调用 sleep_controller.handle_mention(context)
        3. 返回 True 表示应当唤醒并回复
        """
        if not self.state["sleep_mode"]:
            return False

        # 在睡眠状态，交给 sleep_controller 判断
        should_wake = await self.sleep_controller.handle_mention(chat_context)
        if should_wake:
            await self.sleep_controller.wake_up()
            self.state["sleep_mode"] = False
            self._update_decision_history("wake_up (mention)")
            return True

        return False

    # ========================================================================
    # 内部方法
    # ========================================================================

    def _collect_state(self) -> dict:
        """收集当前状态供 ActionAdvisor 和 Prompt 使用"""
        mood = self.status_manager.get_status()
        blog_status = self.blog_writer.get_status()
        proactive_info = self.proactive_chat.get_cooldown_info()

        # 更新心情到 state
        self.state["mood"] = {
            "emotion": mood[0].value,
            "intensity": 0.5,
            "reason": mood[1] or "",
        }

        return {
            "sleep_mode": self.state["sleep_mode"],
            "blog_status": blog_status["status"],
            "draft": blog_status["draft"],
            "cooldown_remaining": blog_status["cooldown_remaining"],
            "last_blog_time": blog_status["last_blog_time"],
            "proactive_info": proactive_info,
            "current_activity": self.self_action.current_activity,
            "current_activity_remaining": self._get_activity_remaining(),
            "mood": self.state["mood"],
        }

    def _get_activity_remaining(self) -> int:
        """获取当前活动剩余秒数"""
        if not self.self_action.current_activity or not self.self_action.activity_start_time:
            return 0
        if self.self_action.activity_duration == 0:
            return -1  # 无限
        elapsed = (datetime.now() - self.self_action.activity_start_time).total_seconds()
        return max(0, int(self.self_action.activity_duration - elapsed))

    def _update_decision_history(self, action_desc: str) -> None:
        """更新决策历史（保留最近5次）"""
        self.state["decision_history"].append({
            "time": datetime.now().isoformat(),
            "action": action_desc,
        })
        self.state["decision_history"] = self.state["decision_history"][-5:]

    async def _generate_system_prompt(
        self, summary: str, state_info: dict, suggestions: str
    ) -> str:
        """生成 request_think 的系统提示（按设计文档模板）"""
        identity_prompt = await get_prompt_text("identity")

        # 博客状态
        draft = state_info.get("draft")
        if draft:
            blog_text = f"草稿《{draft['topic']}》，{draft['word_count']}字，续写{draft['continue_count']}次"
        else:
            blog_text = "无草稿"

        # 上次私聊
        proactive_info = state_info.get("proactive_info", {})
        if proactive_info:
            last_chat_lines = []
            for uid, info in proactive_info.items():
                t = info.get("last_chat")
                if t:
                    last_chat_lines.append(f"{uid}: {t.strftime('%H:%M')}")
            last_private_text = ", ".join(last_chat_lines) if last_chat_lines else "无"
        else:
            last_private_text = "无"

        # 当前活动
        activity = state_info.get("current_activity")
        remaining = state_info.get("current_activity_remaining", 0)
        activity_text = f"{activity}（剩余{remaining}秒）" if activity else "无"

        # 决策历史
        history_lines = []
        for h in self.state["decision_history"]:
            history_lines.append(f"[{h['time']}] {h['action']}")
        history_text = "\n".join(history_lines) if history_lines else "无"

        # 上次决策距今
        last_time = self.state["last_decision_time"]
        if last_time:
            elapsed = int((datetime.now() - last_time).total_seconds() / 60)
        else:
            elapsed = 0

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
            state_info["mood"]["emotion"],
            str(state_info["mood"]["intensity"]),
            state_info["mood"]["reason"],
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
        """生成 request_think 的用户提示"""
        return await lang.text(
            "moonlark_main.think.user",
            self.lang_str,
            trigger_reason,
            request_text or "",
            trigger_from or "",
        )

    async def _execute_decision(self, response: dict) -> None:
        """解析并执行 LLM 决策结果

        按设计文档，可同时包含多个字段：
        - sleep_decision → sleep_controller
        - blog_action → blog_writer
        - private_chat → proactive_chat
        - self_action → self_action
        """
        actions_taken = []

        # sleep_decision
        sleep_decision = response.get("sleep_decision")
        if sleep_decision:
            if sleep_decision == "go_to_sleep":
                await self.sleep_controller.handle_tired()
                self.state["sleep_mode"] = True
                actions_taken.append("go_to_sleep")
            elif sleep_decision == "wake_up" and self.state["sleep_mode"]:
                await self.sleep_controller.wake_up()
                self.state["sleep_mode"] = False
                actions_taken.append("wake_up")

        # blog_action
        blog_action = response.get("blog_action")
        if blog_action and blog_action != "skip":
            await self.blog_writer.handle_action(blog_action)
            actions_taken.append(f"blog: {blog_action}")

        # private_chat
        private_chat = response.get("private_chat")
        if private_chat and isinstance(private_chat, dict):
            target = private_chat.get("target", "")
            reason = private_chat.get("reason", "")
            content_hint = private_chat.get("content_hint", "")
            if target:
                await self.proactive_chat.send_private_message(target, reason, content_hint)
                actions_taken.append(f"private_chat: {target}")

        # self_action
        self_action = response.get("self_action")
        if self_action and self_action != "nothing":
            # 从 ActivityAdvisor 或默认值获取持续时间
            duration = response.get("self_action_duration", 300)
            await self.self_action.start_activity(self_action, duration_seconds=duration)
            actions_taken.append(f"self_action: {self_action}")

        # 更新决策历史
        if actions_taken:
            self._update_decision_history(", ".join(actions_taken))
        else:
            self._update_decision_history("no_action")

    def _on_timer(self) -> None:
        """定时器回调（每5分钟检查一次）"""
        now = datetime.now()

        # 根据 sleep_mode 决定实际间隔
        interval = (
            self.decision_interval_sleep
            if self.state["sleep_mode"]
            else self.decision_interval_normal
        )

        last = self.state["last_decision_time"]
        if last is None or (now - last).total_seconds() >= interval:
            asyncio.create_task(self.request_think("timer"))

    # ========================================================================
    # 兼容旧接口（供 processor, session, matchers 调用）
    # ========================================================================

    @property
    def state_enum(self) -> StateEnum:
        """兼容旧代码的 state 属性"""
        if self.state["sleep_mode"]:
            return StateEnum.SLEEPING
        return StateEnum.ACTIVATE

    async def wake_up(self, session: Optional["BaseSession"] = None) -> None:
        """兼容旧代码的唤醒接口"""
        if not self.state["sleep_mode"]:
            return
        await self.sleep_controller.wake_up()
        self.state["sleep_mode"] = False
        if session:
            await session.processor.openai_messages.append_user_message(
                "Moonlark 已被唤醒。"
            )

    def update_send_private_message_state(self, user_id: str) -> None:
        """兼容旧代码：更新私聊回复状态"""
        self.proactive_chat.update_reply_status(user_id, replied=True)

    async def get_recent_actions_text(self, lang_str: str) -> str:
        """兼容旧代码：获取最近动作历史文本"""
        lines = []
        for h in self.state["decision_history"]:
            lines.append(f"[{h['time']}] {h['action']}")
        return "\n".join(lines) if lines else ""

    async def get_additional_prompt(self) -> str:
        """兼容旧代码：生成额外提示信息"""
        mood = self.status_manager.get_status()
        state_str = await lang.text(
            "prompt_group.state",
            self.lang_str,
            await lang.text(f"status.mood.{mood[0].value}", self.lang_str),
            self.status_manager.get_mood_retention(),
            mood[1],
        )

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

        note_manager = await get_context_notes("main_")
        notes = await note_manager.filter_note(instant_mem)
        notes = notes[0] + notes[1]

        return await lang.text(
            "moonlark_main.additional_info",
            self.lang_str,
            await lang.text("prompt_group.time", self.lang_str, datetime.now().isoformat()),
            state_str,
            (
                "\n".join([await self._format_note(note) for note in notes])
                if notes
                else await lang.text("prompt.note.none", self.lang_str)
            ),
            instant_mem,
        )

    async def _format_note(self, note: Note) -> str:
        created_time = datetime.fromtimestamp(note.created_time).strftime("%y-%m-%d")
        return await lang.text("prompt.note.format", self.lang_str, note.content, note.id, created_time)

    async def get_friends(self) -> str:
        """兼容旧代码：获取好友列表"""
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

    # ========================================================================
    # 子会话接口（供 session.base 调用）
    # ========================================================================

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
                cached_messages = "无消息"

            # 调用 LLM 决策
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
                str(duration) if duration else "未指定",
                cached_messages,
            )
            result = await fetch_json(
                [generate_message(system_prompt, "system"), generate_message(user_prompt, "user")],
                ActionDecisionResponse,
                identify="MoonlarkMain - Action Request Decision",
                reasoning_effort="low",
            )

            approved = result.approved
            allocated_time = result.allocated_time

            if approved and allocated_time > 0:
                self.self_action.start_activity(do, duration_seconds=allocated_time * 60)

            if future and not future.done():
                future.set_result(
                    await lang.text(
                        "moonlark_main.action_request.result_approved" if approved else "moonlark_main.action_request.result_denied",
                        self.lang_str,
                        do,
                        allocated_time,
                    )
                )
        except Exception as e:
            logger.exception(e)
            if future and not future.done():
                future.set_result(f"决策失败: {e}")

    async def submit_sleep_request(
        self, session_id: str, future: Optional[asyncio.Future] = None
    ) -> None:
        """处理来自子会话的睡觉申请"""
        try:
            if future and not future.done():
                future.set_result("已提交睡觉申请，等待决策...")
        except Exception as e:
            logger.exception(e)
            if future and not future.done():
                future.set_result(f"申请失败: {e}")

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
                await self.sleep_controller.handle_tired()
                self.state["sleep_mode"] = True
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


# 全局实例
moonlark_main = MoonlarkMain()


async def init_moonlark_main() -> None:
    """初始化 moonlark_main"""
    logger.info("[MoonlarkMain] 初始化完成")
