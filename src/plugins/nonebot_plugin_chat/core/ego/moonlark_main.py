"""Moonlark 意识主模块 - 重写版

替代旧的 ActionDecider 循环，使用 Planner 系统：
- 早上：计划生成（醒来+30min，最晚11:00）
- 13:30：计划修正（仅下午和晚上）
- 睡前：博客 Decider + Writter
- 每小时：主动私聊检查
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_openai.utils.message import get_message_text
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from ...lang import lang
from ...models import AgentEvent, DiaryPost, DiaryProcessResponse, PrivateChatSession
from ...utils.status_manager import get_status_manager
from .blog_writer import BlogWriter
from .event_collector import event_collector
from .planner import Planner
from .proactive_chat_ctrl import ProactiveChatController
from .sleep_controller import SleepController


class MoonlarkMain:
    def __init__(self, lang_str: str = "zh_hans") -> None:
        self.lang_str = lang_str

        self.sleep_controller = SleepController(self)
        self.blog_writer = BlogWriter(self)
        self.proactive_chat = ProactiveChatController(self)
        self.planner = Planner(self)

        self.status_manager = get_status_manager()

        self.state: dict = {
            "sleep_mode": False,
            "injected_note_ids": [],
        }
        self._blog_content: Optional[str] = None

        scheduler.scheduled_job("cron", hour=13, minute=30, id="ego_afternoon_plan")(self._run_afternoon_plan)
        scheduler.scheduled_job("cron", hour=2, id="moonlark_diary")(self.generate_diary)
        scheduler.scheduled_job("cron", minute="0", id="ego_proactive_chat")(self._check_proactive_chat)
        scheduler.scheduled_job("cron", hour=2, minute=0, id="blog_writer_daily")(self.run_before_sleep)
        scheduler.scheduled_job("cron", hour=2, minute=0, id="blog_writer_daily")(self.run_before_sleep)

    async def get_relevant_notes(self) -> str:
        from ...utils.note_manager import NoteManager

        try:
            note_manager = NoteManager("moonlark_main")
            notes = await note_manager.get_notes(except_current_context=True)

            if not notes:
                return "暂无备忘录。"

            lines = []
            for note in notes:
                if note.id in self.state["injected_note_ids"]:
                    continue
                created_time = datetime.fromtimestamp(note.created_time).strftime("%m-%d %H:%M")
                expire_info = ""
                if note.expire_time:
                    expire_info = f" (过期: {note.expire_time.strftime('%m-%d %H:%M')})"
                lines.append(f"[{created_time}]{expire_info} {note.content}")
                if note.keywords:
                    lines.append(f"  关键词: {note.keywords}")

            return "\n".join(lines) if lines else "暂无新备忘录。"
        except Exception as e:
            logger.warning(f"[MoonlarkMain] 获取备忘录失败: {e}")
            return "获取备忘录失败。"

    async def handle_mention(
        self, chat_context: list, session_name: str = "", nickname: str = "", session_id: str = ""
    ) -> bool:
        if not self.state["sleep_mode"]:
            return False
        return await self.sleep_controller.handle_mention(
            chat_context,
            session_name=session_name,
            nickname=nickname,
            session_id=session_id,
        )

    def _collect_state(self) -> dict:
        mood, mood_reason = self.status_manager.get_status()
        blog_status = self.blog_writer.get_status()
        return {
            "sleep_mode": self.state["sleep_mode"],
            "blog_status": blog_status,
            "mood": {
                "emotion": mood.value,
                "intensity": self.status_manager.get_mood_retention(),
                "reason": mood_reason or "",
            },
            "decision_history": list(self.proactive_chat.decision_history),
        }

    async def generate_diary(self) -> None:
        try:
            entries = await self._fetch_diary_entries(hours=24)
            if not entries:
                logger.info("[Diary] 近 24h 无日记条目，跳过")
                return

            context = self._format_diary_context(entries)

            from nonebot_plugin_openai.utils.chat import fetch_json, fetch_message
            from nonebot_plugin_openai.utils.message import get_messages
            from ...utils.weather import get_daily_weather_text, get_weekday_text

            diary_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            diary_messages = await get_messages(
                "diary",
                context=context,
                current_time=diary_time_str,
                weather=(await get_daily_weather_text()) or "",
                weekday=get_weekday_text(),
            )
            diary_text = await fetch_message(
                diary_messages,
                identify="MoonlarkMain - Generate Diary",
                reasoning_effort="low",
            )

            if not diary_text or not diary_text.strip():
                logger.warning("[Diary] LLM 生成的日记为空")
                return

            diary_process_messages = await get_messages("diary_process", diary_text=diary_text)
            processed = await fetch_json(
                diary_process_messages,
                DiaryProcessResponse,
                identify="MoonlarkMain - Diary Process",
                reasoning_effort="low",
            )

            from datetime import timedelta

            expire_at = datetime.now() + timedelta(hours=processed.expire_hours)

            async with get_session() as session:
                diary_post = DiaryPost(
                    content=diary_text,
                    keywords=processed.keywords,
                    expire_at=expire_at,
                )
                session.add(diary_post)
                await session.commit()
            logger.info(f"[Diary] 日记已生成: {processed.keywords}")

            await self._cleanup_diary_entries(before=entries[-1].created_at)

        except Exception as e:
            logger.exception(f"[Diary] 日记生成失败: {e}")

    async def _fetch_diary_entries(self, hours: int = 24) -> list[AgentEvent]:
        cutoff = datetime.now() - timedelta(hours=hours)
        async with get_session() as session:
            result = await session.execute(
                select(AgentEvent).where(AgentEvent.created_at >= cutoff).order_by(AgentEvent.created_at),
            )
            return list(result.scalars().all())

    def _format_diary_context(self, entries: list[AgentEvent]) -> str:
        lines = []
        for entry in entries:
            time_str = entry.created_at.strftime("%H:%M")
            lines.append(f"[{time_str}] {entry.content}")
        return "\n".join(lines)

    async def _cleanup_diary_entries(self, before: datetime) -> None:
        try:
            async with get_session() as session:
                from sqlalchemy import delete

                await session.execute(delete(AgentEvent).where(AgentEvent.created_at < before))
                await session.commit()
        except Exception as e:
            logger.warning(f"[AgentEvent] 清理条目失败: {e}")

    async def _run_afternoon_plan(self) -> None:
        if self.state["sleep_mode"]:
            return
        await self.planner.run_afternoon_plan()

    async def _check_proactive_chat(self) -> None:
        await self.proactive_chat.check_and_send()

    def on_message_received(self) -> None:
        self.sleep_controller.handle_message()

    def on_reply_sent(self) -> None:
        self.sleep_controller.handle_reply()

    def on_message_cached(self, session_id: str) -> None:
        event_collector.on_message_cached(session_id)

    async def on_private_message_replied(self, user_id: str) -> None:
        await self.proactive_chat.update_reply_status(user_id)

    async def submit_sleep_decision(
        self,
        session_id: str,
        deal_type: str,
        delay_minutes: int = 5,
        reason: str = "",
        future: Optional[asyncio.Future] = None,
    ) -> None:
        try:
            result = await self.sleep_controller.submit_sleep_decision(deal_type, delay_minutes, reason)
            if future and not future.done():
                future.set_result(result)
        except Exception as e:
            logger.exception(e)
            if future and not future.done():
                future.set_result(f"决策失败: {e}")

    async def get_friends(self) -> str:
        friend_list = []
        async with get_session() as session:
            for friend_record in await session.scalars(select(PrivateChatSession)):
                from nonebot_plugin_larkuser.utils.user import get_user

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
                    ),
                )
        return await lang.text(
            "moonlark_main.friends",
            self.lang_str,
            "\n".join(friend_list),
            await get_message_text("favorability.md.jinja"),
        )

    async def get_session_context(self, session_id: str) -> str:
        """获取会话初始化时需要的上下文"""
        parts = []

        events = await event_collector.get_session_events(session_id)
        if events:
            event_texts = []
            for e in events:
                event_texts.append(f"[{e.created_at.strftime('%H:%M')}] {e.content}")
            parts.append("## 此前的事件\n" + "\n".join(event_texts))

        plan_text = self.planner.get_plan_text()
        if plan_text and plan_text != "今日暂无计划。" and plan_text != "暂无备忘录。":
            parts.append("## 今日计划\n" + plan_text)

        return "\n\n".join(parts)

    async def run_morning_plan(self) -> None:
        """醒来后半小时运行计划生成"""
        await asyncio.sleep(1800)
        if datetime.now().hour >= 11:
            logger.info("[MoonlarkMain] 超过 11:00，跳过计划生成")
            return
        await self.planner.run_morning_plan()

    async def run_before_sleep(self) -> None:
        """博客 Decider + Writter（凌晨 2 点 cron 触发）"""
        try:
            last_blog_time = await self.blog_writer.get_last_blog_time()
            events_text = await event_collector.get_all_events_summary(since=last_blog_time)
            plan_text = self.planner.get_plan_text()

            # 获取最后一个事件的时间作为 current_time
            last_event_time = await self._get_last_event_time(last_blog_time)

            decision = await self.blog_writer.decider(events_text, plan_text, current_time=last_event_time)
            if decision is None:
                logger.info("[MoonlarkMain] 博客 Decider 返回空，跳过")
                return
            if decision.skip:
                logger.info("[MoonlarkMain] 博客 Decider 决定跳过本次博客")
                return
            self._blog_content = await self.blog_writer.writter(
                decision, events_text, plan_text, current_time=last_event_time
            )
        except Exception as e:
            logger.exception(f"[MoonlarkMain] 博客生成失败: {e}")

    async def _get_last_event_time(self, since: Optional[datetime] = None) -> Optional[str]:
        """获取最近一个事件的时间字符串"""
        from ...models import SessionEvent

        try:
            async with get_session() as session:
                stmt = select(SessionEvent).order_by(SessionEvent.created_at.desc()).limit(1)
                if since is not None:
                    stmt = stmt.where(SessionEvent.created_at > since)
                last_event = await session.scalar(stmt)
                if last_event:
                    return last_event.created_at.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.warning(f"[MoonlarkMain] 获取最后事件时间失败: {e}")
        return None


moonlark_main = MoonlarkMain()


async def init_moonlark_main() -> None:
    logger.info("[MoonlarkMain] 初始化完成")
