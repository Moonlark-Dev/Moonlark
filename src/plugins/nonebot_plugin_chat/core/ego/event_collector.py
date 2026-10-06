"""事件收集器

以 chat context 的 block 为单位收集会话事件：一个 block 默认 50 条消息，
达到上限时自动提交；也可以由代码（planner / 主动私聊决策 / Note 整理）提前触发。
block 一旦提交就立即冻结，其后的新消息属于下一个 block——因此「第 30 条时提前
触发」得到的是一个独立 block，不会与前一个 block 混在一起。

收集失败时 block 会被记为「未总结」保留在 chat context 里，下一次收集会重试，
避免这一批消息的事件永久丢失。
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

from nonebot import logger
from nonebot_plugin_openai.utils.chat import fetch_json
from nonebot_plugin_openai.utils.message import generate_message, get_message_text
from nonebot_plugin_orm import get_session
from sqlalchemy import select

if TYPE_CHECKING:
    from ..context import ChatContext
    from ..session.base import BaseSession

from ...models import SessionEvent


def normalize_event_content(data: Any) -> Optional[dict]:
    """把模型返回的事件内容规整为 ``{"topics": [str, ...], "events": [str, ...]}``

    模型可能把 topics/events 返回成字符串、数字等非预期结构；非对象直接返回 None。
    规整后 ``_format_events`` 等消费方可以安全地按列表处理。
    """
    if not isinstance(data, dict):
        return None

    def _str_list(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    normalized = dict(data)
    normalized["topics"] = _str_list(data.get("topics"))
    normalized["events"] = _str_list(data.get("events"))
    return normalized


def format_event_content(content: str) -> str:
    """把存储的事件 JSON 渲染为可读文本，结构异常时降级为原文片段"""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return str(content)[:200]
    normalized = normalize_event_content(data)
    if normalized is None:
        return str(content)[:200]
    lines = []
    if normalized["topics"]:
        lines.append(f"话题: {', '.join(normalized['topics'][:5])}")
    lines.extend(f"- {event}" for event in normalized["events"][:3])
    if not lines:
        lines.append("(无话题/事件)")
    return "\n".join(lines)


class EventCollector:
    """会话事件收集器"""

    # 与 ChatContext.BLOCK_MESSAGE_LIMIT 保持一致：一个 block 的消息一起提交事件总结
    COLLECTION_INTERVAL = 50
    # 未生成事件的消息数超过该值时，planner / 主动私聊决策会无视 COLLECTION_INTERVAL 立即收集一次
    FLUSH_PENDING_THRESHOLD = 5
    # 立即收集时的最大并发数，避免一次性向模型服务发起过多请求
    FLUSH_PENDING_CONCURRENCY = 5

    def __init__(self) -> None:
        self._collection_locks: dict[str, asyncio.Lock] = {}
        # 决策游标：记录上一次主动私聊决策的时间，用于只取「上次决策到现在」的新事件
        self._decision_cursor: Optional[datetime] = None

    @staticmethod
    def _get_context(session: "BaseSession") -> "ChatContext":
        return session.processor.openai_messages.context

    def get_pending_message_count(self, session_id: str) -> int:
        """获取某个会话当前 block 中尚未生成事件的消息数"""
        from ..session import groups

        session = groups.get(session_id)
        if session is None:
            return 0
        return self._get_context(session).pending_block_message_count

    def request_collection(self, session: "BaseSession") -> None:
        """当前 block 已满（50 条）时提交一次事件总结"""
        asyncio.create_task(self._collect(session, min_pending=self.COLLECTION_INTERVAL - 1))

    async def flush_pending(self, min_pending: int = FLUSH_PENDING_THRESHOLD) -> list[str]:
        """把所有积压了过多未生成事件消息的会话立即收集一次

        正常情况下每个会话每 :attr:`COLLECTION_INTERVAL` 条消息才生成一次事件，planner
        与主动私聊决策在读取事件前调用本方法：只要某个会话当前 block 里未生成事件的消息
        数**大于** ``min_pending``（或有尚未成功总结的 block），就忽略最低消息数量立即
        运行一次收集，避免决策读到的事件总是落后于最新消息。

        Returns:
            本次立即收集过的会话 ID 列表
        """
        from ..session import groups

        sessions: list[tuple[str, "BaseSession"]] = []
        for session_id, session in list(groups.items()):
            context = self._get_context(session)
            if context.pending_block_message_count <= min_pending and not context.unsummarized_blocks:
                continue
            sessions.append((session_id, session))

        if not sessions:
            return []

        semaphore = asyncio.Semaphore(self.FLUSH_PENDING_CONCURRENCY)

        async def _collect_limited(session: "BaseSession") -> None:
            async with semaphore:
                await self._collect(session, min_pending=min_pending)

        await asyncio.gather(*(_collect_limited(session) for _, session in sessions))
        flushed = [session_id for session_id, _ in sessions]
        logger.info(f"[EventCollector] 已为 {len(flushed)} 个积压会话立即生成事件: {flushed}")
        return flushed

    async def _collect(self, session: "BaseSession", min_pending: int = FLUSH_PENDING_THRESHOLD) -> None:
        """收集当前 block（以及此前失败重试的 block）的事件"""
        context = self._get_context(session)
        lock = self._collection_locks.setdefault(session.session_id, asyncio.Lock())
        if lock.locked():
            return
        async with lock:
            targets = list(context.unsummarized_blocks)
            if context.pending_block_message_count > min_pending:
                block_id = context.current_block_id
                if context.freeze_block(block_id):
                    targets.append(block_id)
            for block_id in targets:
                await self._summarize_block(session, context, block_id)

    async def _summarize_block(self, session: "BaseSession", context: "ChatContext", block_id: int) -> None:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            chat_history = context.block_history_string(block_id)
            if not chat_history.strip():
                context.mark_block_summarized(block_id)
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

            normalized = normalize_event_content(result)
            if normalized is None:
                raise ValueError(f"事件内容无法规整为 topics/events: {result!r}")
            content = json.dumps(normalized, ensure_ascii=False)
            async with get_session() as db_session:
                db_session.add(
                    SessionEvent(
                        session_id=session.session_id,
                        date=today,
                        content=content,
                        block_id=block_id,
                    )
                )
                await db_session.commit()

            context.mark_block_summarized(block_id)
            logger.info(f"[EventCollector] 已收集会话 {session_name} 的 block {block_id} 事件和话题")
        except Exception as e:
            logger.warning(f"[EventCollector] 收集失败（block {block_id} 将重试）: {e}")

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

    def get_decision_cursor(self) -> Optional[datetime]:
        """获取决策游标（上一次主动私聊决策的时间），尚未决策过时为 None"""
        return self._decision_cursor

    def advance_decision_cursor(self, cursor: Optional[datetime] = None) -> None:
        """推进决策游标，默认推进到当前时间"""
        self._decision_cursor = cursor or datetime.now()

    async def _query_events(self, date: Optional[str], since: Optional[datetime]) -> list[SessionEvent]:
        """按日期和游标查询会话事件

        Args:
            date: 日期字符串 (YYYY-MM-DD)，为 None 时不限制日期
            since: 只获取此时间之后创建的事件，为 None 时不限制
        """
        async with get_session() as db_session:
            stmt = select(SessionEvent).order_by(SessionEvent.created_at)
            if date is not None:
                stmt = stmt.where(SessionEvent.date == date)
            if since is not None:
                stmt = stmt.where(SessionEvent.created_at > since)
            result = await db_session.execute(stmt)
            return list(result.scalars().all())

    async def _format_events(self, events: list[SessionEvent], dedup_sessions: bool = True) -> str:
        """把事件记录格式化为摘要文本

        Args:
            events: 事件记录列表（按创建时间升序）
            dedup_sessions: 是否每个会话只保留第一条事件。游标增量场景下应为 False，
                否则同一会话在游标区间内的后续新事件会被丢弃。
        """
        from ..session import groups

        lines = []
        seen_sessions = set()
        session_names: dict[str, str] = {}
        for event in events:
            if dedup_sessions:
                if event.session_id in seen_sessions:
                    continue
                seen_sessions.add(event.session_id)
            session_name = session_names.get(event.session_id)
            if session_name is None:
                session_name = event.session_id
                session = groups.get(event.session_id)
                if session is not None:
                    session_name = (await session.get_session_name()) or event.session_id
                session_names[event.session_id] = session_name
            lines.append(f"\n## 会话: {session_name}")
            # format_event_content 内部会规整 topics/events 的类型并对异常内容兜底
            lines.append(format_event_content(event.content))

        return "\n".join(lines) if lines else "暂无事件记录。"

    async def get_all_events_summary(self, date: Optional[str] = None, since: Optional[datetime] = None) -> str:
        """获取所有会话的事件摘要

        Args:
            date: 日期字符串 (YYYY-MM-DD)，默认今天
            since: 只获取此时间之后的事件，用于确保博客写完后的新事件归入下一天
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return await self._format_events(await self._query_events(date=date, since=since), dedup_sessions=True)

    async def get_events_summary_since(self, cursor: Optional[datetime]) -> str:
        """获取决策游标之后新产生的所有会话事件摘要

        Args:
            cursor: 决策游标，为 None（进程重启或首次决策）时退回当天全部事件

        与 get_all_events_summary 不同，游标区间内不做会话去重，
        保证同一会话的每条新事件都会被交给决策。
        """
        if cursor is None:
            return await self.get_all_events_summary()
        events = await self._query_events(date=None, since=cursor)
        return await self._format_events(events, dedup_sessions=False)


event_collector = EventCollector()
