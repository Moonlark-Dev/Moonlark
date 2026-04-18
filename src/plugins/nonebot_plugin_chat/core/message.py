import re
import traceback
from typing import TYPE_CHECKING, Optional
from nonebot.compat import type_validate_python
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

from ..utils.timing_stats import timing_stats_manager

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.processor import MessageProcessor


class MessageQueue:

    def __init__(
        self,
        processor: "MessageProcessor",
        max_message_count: int = 50,
    ) -> None:
        self.processor = processor
        self.instant_memory_generator_lock = asyncio.Lock()
        self.max_message_count = max_message_count
        self.messages: list[OpenAIMessage] = []
        self.fetcher_lock = asyncio.Lock()
        self.continuous_response = False
        self.fetcher_task = None
        # 在初始化时从数据库恢复消息队列
        self.inserted_messages = []

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

    def _serialize_messages(self) -> str:
        """将消息列表序列化为 JSON 字符串"""
        serialized = [self._serialize_message(msg) for msg in self.messages]
        return json.dumps(serialized, ensure_ascii=False)

    async def restore_from_db(self) -> None:
        """从数据库恢复消息队列"""
        try:
            group_id = self.processor.session.session_id
            async with get_session() as session:
                cache = await session.get(MessageQueueCache, {"group_id": group_id})
                if cache:
                    self.messages = json.loads(cache.messages_json)
                    logger.info(f"已从数据库恢复群 {group_id} 的消息队列，共 {len(self.messages)} 条消息")
        except Exception as e:
            logger.warning(f"从数据库恢复消息队列失败: {e}")

    async def save_to_db(self) -> None:
        """将消息队列保存到数据库"""
        try:
            async with self.fetcher_lock:
                group_id = self.processor.session.session_id
                async with get_session() as session:
                    cache = MessageQueueCache(
                        group_id=group_id,
                        messages_json=self._serialize_messages(),
                        updated_time=datetime.now().timestamp(),
                    )
                    await session.merge(cache)
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
        self.clean_special_message()
        self.messages = self.messages[-self.max_message_count :]
        messages = copy.deepcopy(self.messages)
        messages.insert(0, await self.processor.generate_system_prompt())
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
            asyncio.create_task(self.generate_instant_memory())

        if self.continuous_response and self.processor.session.get_session_type() == "group":
            self.continuous_response = False

        # 记录抓取结束时间
        timing_stats_manager.record_fetch_end(session_id)

    async def generate_instant_memory(self) -> None:
        if self.instant_memory_generator_lock.locked():
            return
        async with self.instant_memory_generator_lock:
            await self.processor.generate_instant_memory()
            await asyncio.sleep(5)

    async def stop_fetcher(self) -> None:
        if self.fetcher_task:
            self.fetcher_task.cancel()

    async def _fetch_reply(self) -> FetchStatus:
        state = FetchStatus.SUCCESS
        messages = await self.get_messages()
        if get_role(messages[-1]) == "assistant":
            return FetchStatus.SKIP
        self.messages.clear()
        self.inserted_messages.clear()
        fetcher = await MessageFetcher.create(
            messages,
            False,
            identify="Chat",
            functions=await self.processor.tool_manager.select_tools("group"),
            reasoning_effort="medium",
        )
        retry_count = 0
        try:
            async for message in fetcher.fetch_message_stream():
                if retry_count > 5:
                    raise Exception("Failed to fetch message")
                if not message:
                    continue
                try:
                    analysis = type_validate_python(
                        ModelResponse, json.loads(re.sub(r"`{1,3}([a-zA-Z0-9]+)?", "", message))
                    )
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse message: {message}")
                    analysis = None
                except ValidationError as e:
                    fetcher.session.insert_message(generate_message(await self.processor.session.text("fetcher.parse_failed", str(e)), "user"))
                    continue
                if analysis is not None:
                    if analysis.mood:
                        await self.processor.tool_manager.set_mood(
                            analysis.mood, analysis.mood_reason, analysis.mood_intensity
                        )
                    if analysis.interest is not None:
                        self.processor.session.set_interest(analysis.interest)
                        logger.debug(f"Cached interest: {analysis.interest:.2f}")
                    if analysis.reply_required and isinstance(fetcher.session.messages[-1], ChatCompletionMessage) and not fetcher.session.messages[-1].tool_calls:
                        fetcher.session.insert_message(generate_message(await self.processor.session.text("fetcher.reply_required"), "user"))
                if self.continuous_response or (isinstance(fetcher.session.messages[-1], ChatCompletionMessage) and fetcher.session.messages[-1].tool_calls):
                    fetcher.session.insert_messages(self.messages)
                    self.messages.clear()
            self.messages = fetcher.get_messages() + self.messages
        except Exception as e:
            logger.exception(e)
            # 恢复 Message
            self.messages = messages + self.inserted_messages
            self.inserted_messages.clear()
            state = FetchStatus.FAILED
        return state

    def append_user_message(self, message: str) -> None:
        self.messages.append(generate_message(message, "user"))

    def is_last_message_from_user(self) -> bool:
        return get_role(self.messages[-1]) == "user"
