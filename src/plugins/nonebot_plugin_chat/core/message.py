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
from nonebot_plugin_openai.utils.chat import MessageFetcher
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
        self.messages: list[OpenAIMessage] = []
        self.fetcher_lock = asyncio.Lock()
        self.continuous_response = False
        self.fetcher_task = None
        # 在初始化时从数据库恢复消息队列
        self.inserted_messages = []
        self.trace_id: str = uuid.uuid4().hex

    async def reset_chat_history(self) -> list[OpenAIMessage]:
        messages = copy.deepcopy(self.messages)
        self.messages = []
        return messages

    def _serialize_message(self, message: OpenAIMessage) -> dict:
        """将 OpenAIMessage 序列化为可 JSON 化的字典"""
        if isinstance(message, dict):
            return message  # type: ignore
        # 如果是 Pydantic 模型或其他对象，转换为字典
        if hasattr(message, "model_dump"):
            return message.model_dump()
        elif hasattr(message, "__dict__"):
            return dict(message.__dict__)
        else:
            return {"content": str(message), "role": "user"}

    def _serialize_messages(self) -> list[str]:
        """将消息列表序列化为 JSON 字符串"""
        serialized = [self._serialize_message(msg) for msg in self.messages]
        return [json.dumps(msg, ensure_ascii=False) for msg in serialized]

    async def restore_from_db(self) -> None:
        """从数据库恢复消息队列，并验证 system prompt 的有效性"""
        try:
            session_id = self.processor.session.session_id
            session_type = self.processor.session.get_session_type()
            earliest_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

            # 对于私聊会话，尝试新旧两种 key 格式加载数据
            candidate_ids = [session_id]
            if session_type == "private" and "_" in session_id:
                # 新格式: qq_USERID → 旧格式: USERID（去掉 platform 前缀）
                legacy_id = session_id.split("_", 1)[1]
                candidate_ids.append(legacy_id)

            cache_list: list[MessageQueueCache] = []
            async with get_session() as db_session:
                for gid in candidate_ids:
                    result = await db_session.scalars(
                        select(MessageQueueCache)
                        .where(MessageQueueCache.updated_time >= earliest_time, MessageQueueCache.group_id == gid)
                        .order_by(MessageQueueCache.message_id)
                    )
                    cache_list = list(result)
                    if cache_list:
                        if gid != session_id:
                            logger.info(
                                f"私聊会话 {session_id} 使用旧格式 {gid} 恢复了 {len(cache_list)} 条消息"
                            )
                        break

            self.messages = [json.loads(msg.message_json) for msg in cache_list]

            # 恢复 trace_id（从第一条有 trace_id 的记录中获取）
            for msg in cache_list:
                if msg.trace_id:
                    self.trace_id = msg.trace_id
                    logger.info(f"已从数据库恢复群 {session_id} 的 trace_id: {self.trace_id}")
                    break

            logger.info(f"已从数据库恢复群 {session_id} 的消息队列，共 {len(self.messages)} 条消息")

            if self.messages:
                if get_role(self.messages[0]) != "system":
                    logger.warning(f"群 {session_id} 恢复的消息队列缺少 system prompt，重置上下文")
                    await self._reset_and_clear_db(session_id)
                else:
                    # 检查 system prompt 内容是否与当前配置一致
                    expected_prompt = await self.processor.generate_system_prompt()
                    expected_content = (
                        expected_prompt.get("content", "")
                        if isinstance(expected_prompt, dict)
                        else getattr(expected_prompt, "content", "")
                    )
                    first_msg = self.messages[0]
                    actual_content = (
                        first_msg.get("content", "")
                        if isinstance(first_msg, dict)
                        else getattr(first_msg, "content", "")
                    )
                    if actual_content != expected_content:
                        logger.warning(f"群 {session_id} 的 system prompt 与当前配置不一致，重置上下文")
                        await self._reset_and_clear_db(session_id)
                    else:
                        logger.info(f"群 {session_id} 的 system prompt 验证通过")
        except Exception as e:
            logger.warning(f"从数据库恢复消息队列失败: {e}")

    async def _reset_and_clear_db(self, group_id: str) -> None:
        """重置消息队列并清空数据库缓存"""
        self.messages = []
        self.inserted_messages = []
        async with get_session() as session:
            await session.execute(delete(MessageQueueCache).where(MessageQueueCache.group_id == group_id))
            await session.commit()
        logger.info(f"已清空群 {group_id} 的消息队列缓存")

    async def clear_cache(self) -> None:
        """清空消息队列缓存"""
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
        """将消息队列保存到数据库"""
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
                            # 更新已有记录的 trace_id
                            result.trace_id = self.trace_id
                            continue
                        cache = MessageQueueCache(
                            group_id=group_id,
                            trace_id=self.trace_id,
                            message_json=msg,
                            message_hash=sha256.digest(),
                        )
                        session.add(cache)
                    await session.commit()
        except Exception as e:
            logger.exception(e)

    def clean_special_message(self) -> None:
        while True:
            role = get_role(self.messages[0])
            if role in ["user", "assistant"]:
                break
            self.messages.pop(0)

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
                    # 使用 dict[str, Any] 断言，绕过 TypedDict 对 tool_calls 键的限制
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

        # 记录抓取开始时间
        session_id = self.processor.session.session_id
        timing_stats_manager.record_fetch_start(session_id)

        async with self.fetcher_lock:
            self.fetcher_task = asyncio.create_task(self._fetch_reply())
            status = await self.fetcher_task
            logger.info(f"Reply fetcher ended with status: {status.name}")

        if self.continuous_response and self.processor.session.get_session_type() == "group":
            self.continuous_response = False

        # 记录抓取结束时间
        timing_stats_manager.record_fetch_end(session_id)

    async def stop_fetcher(self) -> None:
        if self.fetcher_task:
            self.fetcher_task.cancel()

    async def _fetch_reply(self) -> FetchStatus:
        state = FetchStatus.SUCCESS
        messages = await self.get_messages()
        if get_role(messages[-1]) == "assistant":
            return FetchStatus.SKIP
        # 保存 system prompt，确保后续重组时不会丢失
        system_prompt = messages[0]
        self.messages.clear()
        self.inserted_messages.clear()
        fetcher = await MessageFetcher.create(
            messages,
            False,
            identify="Chat",
            functions=await self.processor.tool_manager.select_tools("group"),
            reasoning_effort="medium",
        )
        fetcher.session.set_custom_trace_id(self.trace_id)
        retry_count = 0
        try:
            async for message in fetcher.fetch_message_stream():
                if retry_count > 5:
                    raise Exception("Failed to fetch message")
                if not message:
                    continue
                try:
                    analysis = type_validate_json(ModelResponse, message)
                except Exception as e:
                    fetcher.session.insert_message(
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
                        and isinstance(fetcher.session.messages[-1], ChatCompletionMessage)
                        and not fetcher.session.messages[-1].tool_calls
                    ):
                        fetcher.session.insert_message(
                            generate_message(await self.processor.session.text("fetcher.reply_required"), "user")
                        )
                        retry_count += 1
                if self.continuous_response:
                    fetcher.session.insert_messages(self.messages)
                    self.messages.clear()
            # 确保 system prompt 始终在首位
            fetcher_messages = fetcher.get_messages()
            if fetcher_messages and get_role(fetcher_messages[0]) == "system":
                self.messages = fetcher_messages
            else:
                self.messages = [system_prompt] + fetcher_messages
        except Exception as e:
            logger.exception(e)
            # 恢复 Message
            self.messages = messages + self.inserted_messages
            self.inserted_messages.clear()
            state = FetchStatus.FAILED
        return state

    async def _ensure_system_prompt(self) -> None:
        """确保 messages[0] 存在且是 system 消息，且不存在多余的 system 消息。

        不保证内容与当前配置一致——内容变动由 get_messages() 检测并触发清空重置。
        """
        if not self.messages or get_role(self.messages[0]) != "system":
            self.messages.insert(0, await self.processor.generate_system_prompt())

        # 清理 messages[1:] 中多余的 system 消息（只保留第一条）
        self.messages = [self.messages[0]] + [msg for msg in self.messages[1:] if get_role(msg) != "system"]

    async def append_user_message(self, message: str) -> None:
        await self._ensure_system_prompt()
        self.messages.append(generate_message(message, "user"))

    def is_last_message_from_user(self) -> bool:
        return get_role(self.messages[-1]) == "user"
