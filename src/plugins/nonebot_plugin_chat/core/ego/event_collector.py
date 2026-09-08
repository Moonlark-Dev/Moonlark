"""事件收集器

每个会话每缓存 100 条消息运行一次，生成群聊事件和话题列表并存入数据库。
"""

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from nonebot import logger
from nonebot_plugin_openai.utils.chat import fetch_json
from nonebot_plugin_openai.utils.message import generate_message, get_message_text
from nonebot_plugin_orm import get_session
from sqlalchemy import select

if TYPE_CHECKING:
    from ..session.base import BaseSession

from ...models import SessionEvent


class EventCollector:
    """会话事件收集器"""

    COLLECTION_INTERVAL = 100

    def __init__(self) -> None:
        self._session_message_counters: dict[str, int] = {}

    def on_message_cached(self, session_id: str) -> None:
        self._session_message_counters.setdefault(session_id, 0)
        self._session_message_counters[session_id] += 1
        if self._session_message_counters[session_id] >= self.COLLECTION_INTERVAL:
            self._session_message_counters[session_id] = 0
            from ..session import groups

            session = groups.get(session_id)
            if session is not None:
                import asyncio

                asyncio.create_task(self._collect(session))

    async def _collect(self, session: "BaseSession") -> None:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            chat_history = await session.get_cached_messages_string(length=100, include_self_message=True)
            if not chat_history.strip():
                return

            identity_text = await get_message_text("identity.md.jinja")
            session_name = (await session.get_session_name()) or session.session_id

            result = await fetch_json(
                [
                    generate_message(
                        f"你是 Moonlark，以下是 {session_name} 的聊天记录。\n\n{identity_text}\n\n"
                        f"请分析最近的消息，提取出：\n"
                        f"1. 讨论的主要话题（topics）\n"
                        f"2. 值得注意的事件（events）\n"
                        f"3. 群聊的氛围和动态\n\n"
                        f"以 JSON 格式返回，包含 topics（列表）和 events（列表）。",
                        "system",
                    ),
                    generate_message(chat_history, "user"),
                ],
                dict,
                identify="EventCollector",
                reasoning_effort="low",
            )

            content = json.dumps(result, ensure_ascii=False)
            async with get_session() as db_session:
                db_session.add(
                    SessionEvent(
                        session_id=session.session_id,
                        date=today,
                        content=content,
                    )
                )
                await db_session.commit()

            logger.info(f"[EventCollector] 已收集会话 {session_name} 的事件和话题")
        except Exception as e:
            logger.warning(f"[EventCollector] 收集失败: {e}")

    async def get_session_events(self, session_id: str, start_date: Optional[str] = None) -> list[SessionEvent]:
        """获取指定会话的事件，范围为 start_date（默认前一天）0:00 至今天"""
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        async with get_session() as db_session:
            result = await db_session.execute(
                select(SessionEvent)
                .where(
                    SessionEvent.session_id == session_id,
                    SessionEvent.date >= start_date,
                    SessionEvent.date <= today,
                )
                .order_by(SessionEvent.created_at)
            )
            return list(result.scalars().all())

    async def get_all_events_summary(self, date: Optional[str] = None, since: Optional[datetime] = None) -> str:
        """获取所有会话的事件摘要

        Args:
            date: 日期字符串 (YYYY-MM-DD)，默认今天
            since: 只获取此时间之后的事件，用于确保博客写完后的新事件归入下一天
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        async with get_session() as db_session:
            stmt = select(SessionEvent).where(SessionEvent.date == date).order_by(SessionEvent.created_at)
            if since is not None:
                stmt = stmt.where(SessionEvent.created_at > since)
            result = await db_session.execute(stmt)
            events = list(result.scalars().all())

        from ..session import groups

        lines = []
        seen_sessions = set()
        for event in events:
            if event.session_id not in seen_sessions:
                seen_sessions.add(event.session_id)
                session_name = event.session_id
                session = groups.get(event.session_id)
                if session is not None:
                    session_name = (await session.get_session_name()) or event.session_id
                lines.append(f"\n## 会话: {session_name}")
                try:
                    data = json.loads(event.content)
                    if isinstance(data, dict):
                        topics = data.get("topics", [])
                        events_list = data.get("events", [])
                        if topics:
                            lines.append(f"话题: {', '.join(topics[:5])}")
                        if events_list:
                            for evt in events_list[:3]:
                                lines.append(f"- {evt}")
                except (json.JSONDecodeError, TypeError):
                    lines.append(event.content[:200])

        return "\n".join(lines) if lines else "暂无事件记录。"


event_collector = EventCollector()
