import hashlib
import re
import traceback
import uuid
from typing import TYPE_CHECKING, Any, Optional, cast
from nonebot.compat import type_validate_json
from nonebot.log import logger

from nonebot_plugin_chat.utils.role import get_role
from nonebot_plugin_chat.models import MessageQueueCache, ModelResponse
from nonebot_plugin_chat.enums import FetchStatus
from pydantic import ValidationError
from nonebot_plugin_openai import generate_message
from nonebot_plugin_openai.utils.chat import MessageFetcher, strip_json_codeblock
from nonebot_plugin_orm import get_session
from openai.types.chat import ChatCompletionMessage
from nonebot_plugin_openai.types import Message as OpenAIMessage

import asyncio
import copy
import json
from datetime import datetime

from sqlalchemy import delete, select

from ..utils.timing_stats import timing_stats_manager

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.processor import MessageProcessor


class MessageQueue:
    def __init__(
        self,
        processor: "MessageProcessor",
    ) -> None:
        self.processor = processor
        self.fetcher: Optional[MessageFetcher] = None
        self.fetcher_lock = asyncio.Lock()
        self.continuous_response = False
        self.fetcher_task = None
        self.waiting_sequence: list[OpenAIMessage] = []
        self.trace_id: str = uuid.uuid4().hex
        self.created_at: datetime = datetime.now()
        self.last_events_summary_time: Optional[datetime] = None

    @property
    def messages(self) -> list[OpenAIMessage]:
        if self.fetcher is None:
            return []
        return self.fetcher.session.messages

    async def _create_fetcher(self) -> MessageFetcher:
        messages = list(self.messages) if self.fetcher is not None else []
        if not messages or get_role(messages[0]) != "system":
            messages.insert(0, await self.processor.generate_system_prompt())
        fetcher = await MessageFetcher.create(
            messages,
            False,
            identify="Chat",
            functions=await self.processor.tool_manager.select_tools("group"),
            pre_function_call=self.processor.send_function_call_feedback,
            reasoning_effort="medium",
        )
        fetcher.session.set_custom_trace_id(self.trace_id)
        return fetcher

    async def reset_chat_history(self) -> list[OpenAIMessage]:
        messages = copy.deepcopy(self.messages)
        if self.fetcher is not None:
            self.fetcher.session.messages.clear()
        return messages

    def _serialize_message(self, message: OpenAIMessage) -> dict:
        if isinstance(message, dict):
            return message  # type: ignore
        if hasattr(message, "model_dump"):
            return message.model_dump()
        elif hasattr(message, "__dict__"):
            return dict(message.__dict__)
        else:
            return {"content": str(message), "role": "user"}

    def _serialize_messages(self) -> list[str]:
        serialized = [self._serialize_message(msg) for msg in self.messages]
        return [json.dumps(msg, ensure_ascii=False) for msg in serialized]

    async def restore_from_db(self) -> None:
        try:
            session_id = self.processor.session.session_id
            earliest_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

            async with get_session() as db_session:
                cache = await db_session.scalars(
                    select(MessageQueueCache)
                    .where(MessageQueueCache.updated_time >= earliest_time, MessageQueueCache.group_id == session_id)
                    .order_by(MessageQueueCache.message_id)
                )
                cache_list = list(cache)

            restored_messages = [json.loads(msg.message_json) for msg in cache_list]

            for msg in cache_list:
                if msg.trace_id:
                    self.trace_id = msg.trace_id
                    logger.info(f"已从数据库恢复群 {session_id} 的 trace_id: {self.trace_id}")
                    break

            logger.info(f"已从数据库恢复群 {session_id} 的消息队列，共 {len(restored_messages)} 条消息")

            context_reset = False
            if restored_messages:
                if get_role(restored_messages[0]) != "system":
                    logger.warning(f"群 {session_id} 恢复的消息队列缺少 system prompt，重置上下文")
                    await self._reset_and_clear_db(session_id)
                    context_reset = True
                else:
                    expected_prompt = await self.processor.generate_system_prompt()
                    expected_content = (
                        expected_prompt.get("content", "")
                        if isinstance(expected_prompt, dict)
                        else getattr(expected_prompt, "content", "")
                    )
                    first_msg = restored_messages[0]
                    actual_content = (
                        first_msg.get("content", "")
                        if isinstance(first_msg, dict)
                        else getattr(first_msg, "content", "")
                    )
                    if actual_content != expected_content:
                        logger.warning(f"群 {session_id} 的 system prompt 与当前配置不一致，重置上下文")
                        await self._reset_and_clear_db(session_id)
                        context_reset = True
                    else:
                        logger.info(f"群 {session_id} 的 system prompt 验证通过")
                        self.fetcher = await self._create_fetcher()
                        self.fetcher.session.messages = restored_messages
            else:
                context_reset = True

            if context_reset:
                await self._inject_instant_memories(session_id)
        except Exception as e:
            logger.warning(f"从数据库恢复消息队列失败: {e}")

    async def _inject_instant_memories(self, session_id: str) -> None:
        from ..utils.instant_mem import get_memories_for_session, format_memories_for_injection

        memories = get_memories_for_session(session_id)
        if not memories:
            return

        injected_text = format_memories_for_injection(memories)
        if not injected_text:
            return

        if self.fetcher is None:
            self.fetcher = await self._create_fetcher()
        self.fetcher.session.messages.insert(1, generate_message(injected_text, "user"))
        logger.info(f"[InstantMemory] 已注入 {len(memories)} 条即时记忆到 {session_id}")

    async def _inject_recent_events(self) -> None:
        from ..utils.instant_mem import generate_recent_events_summary

        session_id = self.processor.session.session_id
        lang_str = self.processor.session.lang_str

        try:
            recent_events = await generate_recent_events_summary(
                session_id,
                lang_str,
                after_time=self.last_events_summary_time,
            )

            if recent_events:
                if self.fetcher is None:
                    self.fetcher = await self._create_fetcher()
                self.fetcher.session.insert_message(generate_message(recent_events, "user"))
                self.last_events_summary_time = datetime.now()
                logger.info(f"[RecentEvents] 已注入最近事件摘要到 {session_id}")
        except Exception as e:
            logger.exception(f"[RecentEvents] 注入最近事件摘要失败: {e}")

    async def _reset_and_clear_db(self, group_id: str) -> None:
        if self.fetcher is not None:
            self.fetcher.session.messages.clear()
        self.fetcher = None
        self.created_at = datetime.now()
        async with get_session() as session:
            await session.execute(delete(MessageQueueCache).where(MessageQueueCache.group_id == group_id))
            await session.commit()
        logger.info(f"已清空群 {group_id} 的消息队列缓存")

    async def clear_cache(self) -> None:
        earliest_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        group_id = self.processor.session.session_id
        async with get_session() as session:
            await session.execute(
                delete(MessageQueueCache).where(
                    MessageQueueCache.group_id == group_id, MessageQueueCache.updated_time < earliest_time
                )
            )
            await session.commit()

    async def save_to_db(self) -> None:
        try:
            async with self.fetcher_lock:
                group_id = self.processor.session.session_id
                async with get_session() as session:
                    for msg in self._serialize_messages():
                        sha256 = hashlib.sha256(msg.encode())
                        result = await session.scalar(
                            select(MessageQueueCache).where(MessageQueueCache.message_hash == sha256.digest())
                        )
                        if result is not None:
                            result.trace_id = self.trace_id
                            continue
                        cache = MessageQueueCache(
                            group_id=group_id,
                            trace_id=self.trace_id,
                            message_json=msg,
                            message_hash=sha256.digest(),
                            updated_time=self.created_at,
                        )
                        session.add(cache)
                    await session.commit()
        except Exception as e:
            logger.exception(e)

    def clean_special_message(self) -> None:
        msgs = self.messages
        while True:
            role = get_role(msgs[0])
            if role in ["user", "assistant"]:
                break
            msgs.pop(0)

    async def get_messages(self) -> list[OpenAIMessage]:
        messages = copy.deepcopy(self.messages)
        logger.debug(messages)
        system_prompt = await self.processor.generate_system_prompt()
        if len(messages) <= 0:
            raise ValueError("messages must be more than 1")
        elif len([msg for msg in messages if get_role(msg) == "user"]) <= 0:
            raise ValueError("no user input")
        elif get_role(messages[0]) != "system":
            messages.insert(0, system_prompt)
        elif messages[0] != system_prompt:
            messages = [system_prompt]
            raise ValueError("system prompt modified")

        tool_call_ids: set[str] = set()
        for msg in messages:
            role = get_role(msg)
            if role == "tool":
                if isinstance(msg, dict):
                    tcid = msg.get("tool_call_id")
                else:
                    tcid = getattr(msg, "tool_call_id", None)
                if tcid:
                    tool_call_ids.add(tcid)

        for msg in messages:
            role = get_role(msg)
            if role == "assistant":
                if isinstance(msg, dict):
                    msg_dict = cast(dict[str, Any], msg)
                    tc = msg_dict.get("tool_calls")
                    if tc:
                        valid = [t for t in tc if t["id"] in tool_call_ids]
                        if valid:
                            msg_dict["tool_calls"] = valid
                        else:
                            del msg_dict["tool_calls"]
                else:
                    tc = getattr(msg, "tool_calls", None)
                    if tc:
                        valid = [t for t in tc if t.id in tool_call_ids]
                        if valid:
                            msg.tool_calls = valid
                        else:
                            msg.tool_calls = None

        return messages

    async def fetch_reply(self) -> None:
        if self.fetcher_lock.locked():
            return

        session_id = self.processor.session.session_id
        timing_stats_manager.record_fetch_start(session_id)

        async with self.fetcher_lock:
            self.fetcher_task = asyncio.create_task(self._fetch_reply())
            status = await self.fetcher_task
            logger.info(f"Reply fetcher ended with status: {status.name}")
            await self.apply_waiting_queue()

        if self.continuous_response and self.processor.session.get_session_type() == "group":
            self.continuous_response = False

        timing_stats_manager.record_fetch_end(session_id)

    async def apply_waiting_queue(self) -> None:
        if self.waiting_sequence:
            if self.fetcher is None:
                self.fetcher = await self._create_fetcher()
            await self._ensure_system_prompt()
            self.fetcher.session.insert_messages(self.waiting_sequence)
            self.waiting_sequence.clear()

    async def stop_fetcher(self) -> None:
        if self.fetcher_task:
            self.fetcher_task.cancel()

    async def _validate_messages(self) -> bool:
        msgs = self.messages
        if not msgs:
            return True

        if get_role(msgs[0]) != "system":
            logger.warning("消息队列缺少 system prompt，重置上下文")
            await self._reset_and_clear_db(self.processor.session.session_id)
            return False

        tool_call_ids: set[str] = set()
        for msg in msgs:
            if get_role(msg) == "tool":
                if isinstance(msg, dict):
                    tcid = msg.get("tool_call_id")
                else:
                    tcid = getattr(msg, "tool_call_id", None)
                if tcid:
                    tool_call_ids.add(tcid)

        for msg in msgs:
            if get_role(msg) == "assistant":
                if isinstance(msg, dict):
                    tc = msg.get("tool_calls")
                else:
                    tc = getattr(msg, "tool_calls", None)
                if tc:
                    for tool_call in tc:
                        tc_id = tool_call.get("id") if isinstance(tool_call, dict) else tool_call.id
                        if tc_id not in tool_call_ids:
                            logger.warning(f"工具调用 {tc_id} 缺少对应的工具结果，重置上下文")
                            await self._reset_and_clear_db(self.processor.session.session_id)
                            return False

        return True

    async def _fetch_reply(self) -> FetchStatus:
        from .ego.moonlark_main import moonlark_main

        moonlark_main.on_reply_sent()

        state = FetchStatus.SUCCESS

        if self.messages and get_role(self.messages[-1]) == "assistant":
            return FetchStatus.SKIP

        if not await self._validate_messages():
            return FetchStatus.SKIP

        await self._inject_recent_events()

        system_prompt = self.messages[0] if self.messages else None

        self.fetcher = await self._create_fetcher()
        retry_count = 0
        analysis = None  # 跟踪是否已成功解析 JSON
        try:
            async for message in self.fetcher.fetch_message_stream():
                if retry_count > 5:
                    raise Exception("Failed to fetch message")
                if not message:
                    continue
                try:
                    analysis = type_validate_json(ModelResponse, strip_json_codeblock(message))
                except Exception as e:
                    # 如果当前轮次含有工具调用，忽略输出解析失败提示
                    last_msg = self.fetcher.session.messages[-1] if self.fetcher.session.messages else None
                    if last_msg and getattr(last_msg, "tool_calls", None):
                        continue
                    # 如果已成功解析过 JSON，忽略同一调用后续轮次的解析失败
                    if analysis is not None:
                        continue
                    self.fetcher.session.insert_message(
                        generate_message(await self.processor.session.text("fetcher.parse_failed", str(e)), "user")
                    )
                    retry_count += 2
                    continue
                if analysis is not None:
                    if analysis.mood:
                        await self.processor.tool_manager.set_mood(
                            analysis.mood, analysis.mood_reason, analysis.mood_intensity
                        )
                    if analysis.interest is not None:
                        self.processor.session.set_interest(analysis.interest)
                        logger.debug(f"Cached interest: {analysis.interest:.2f}")
                    if (judge := analysis.favorability_judge) is not None:
                        await self.processor.judge_user_behavior(judge.target, judge.score, judge.reason)
                    if (
                        analysis.reply_required
                        and isinstance(self.fetcher.session.messages[-1], ChatCompletionMessage)
                        and not self.fetcher.session.messages[-1].tool_calls
                    ):
                        self.fetcher.session.insert_message(
                            generate_message(await self.processor.session.text("fetcher.reply_required"), "user")
                        )
                        retry_count += 1

            fetcher_messages = self.fetcher.get_messages()
            if fetcher_messages and get_role(fetcher_messages[0]) == "system":
                pass
            elif system_prompt:
                self.fetcher.session.messages.insert(0, system_prompt)
        except Exception as e:
            logger.exception(e)
            state = FetchStatus.FAILED
        return state

    async def _ensure_system_prompt(self) -> None:
        if self.fetcher is None:
            self.fetcher = await self._create_fetcher()
        if not self.messages or get_role(self.messages[0]) != "system":
            self.fetcher.session.messages.insert(0, await self.processor.generate_system_prompt())

        self.fetcher.session.messages = [self.messages[0]] + [
            msg for msg in self.messages[1:] if get_role(msg) != "system"
        ]

    async def append_user_message(self, message: str | list) -> None:
        msg = generate_message(message, "user")
        if self.fetcher_lock.locked() and not self.continuous_response:
            self.waiting_sequence.append(msg)
        else:
            if self.fetcher is None:
                self.fetcher = await self._create_fetcher()
            await self._ensure_system_prompt()
            self.fetcher.session.insert_message(msg)

    def is_last_message_from_user(self) -> bool:
        return get_role(self.messages[-1]) == "user"
