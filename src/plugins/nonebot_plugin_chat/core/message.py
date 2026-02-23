import re
import traceback
from typing import TYPE_CHECKING
from nonebot.compat import type_validate_python
from nonebot.log import logger
from nonebot_plugin_chat.utils.role import get_role
from nonebot_plugin_chat.models import MessageQueueCache, ModelResponse
from nonebot_plugin_chat.utils.enums import FetchStatus
from nonebot_plugin_openai import generate_message
from nonebot_plugin_openai.utils.chat import MessageFetcher
from nonebot_plugin_orm import get_session
from openai.types.chat import ChatCompletionMessage
from nonebot_plugin_openai.types import Message as OpenAIMessage

import asyncio
import copy
import json
from datetime import datetime

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.processor import MessageProcessor


class MessageQueue:

    def __init__(
        self,
        processor: "MessageProcessor",
        max_message_count: int = 50,
    ) -> None:
        self.processor = processor
        self.max_message_count = max_message_count
        self.messages: list[OpenAIMessage] = []
        self.fetcher_lock = asyncio.Lock()
        self._restore_complete = asyncio.Event()
        # 在初始化时从数据库恢复消息队列
        self.inserted_messages = []
        asyncio.create_task(self._restore_from_db())

    async def wait_for_restore(self) -> None:
        """等待数据库恢复完成"""
        await self._restore_complete.wait()

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

    async def _restore_from_db(self) -> None:
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
        finally:
            # 无论恢复成功与否，都设置恢复完成事件
            self._restore_complete.set()

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
        async with self.fetcher_lock:
            status = await self._fetch_reply()
            logger.info(f"Reply fetcher ended with status: {status.name}")

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
            functions=self.processor.functions,
            identify="Chat",
            pre_function_call=self.processor.send_function_call_feedback,
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
                except Exception as e:
                    retry_count += 1
                    fetcher.session.insert_message(
                        generate_message(await self.processor.session.text("fetcher.parse_failed", str(e)), "user")
                    )
                    continue
                if analysis.activity:
                    res = await self.processor.tool_manager.set_activity(
                        analysis.activity.content, analysis.activity.duration
                    )
                    logger.info(f"Set activity: {res}")
                if analysis.mood:
                    res = await self.processor.tool_manager.set_mood(analysis.mood, analysis.mood_reason)
                    logger.info(f"Set mood: {res}")
                if analysis.favorability_judge:
                    res = await self.processor.judge_user_behavior(
                        analysis.favorability_judge.target,
                        analysis.favorability_judge.score,
                        analysis.favorability_judge.reason,
                    )
                    logger.info(f"Judge user behavior: {res}")
                # 缓存 interest 值用于后续触发概率计算
                if analysis.interest is not None:
                    self.processor.session.set_interest(analysis.interest)
                    logger.debug(f"Cached interest: {analysis.interest:.2f}")
                # 处理连续回复同一条消息的情况：第二条开始的重复 reply_message_id 设为 None
                last_reply_id = None
                for msg in analysis.messages:
                    reply_id = msg.reply_message_id
                    # 如果当前消息的 reply_message_id 与上一条相同，则从第二条开始设为 None
                    if reply_id == last_reply_id and last_reply_id is not None:
                        reply_id = None
                    await self.processor.send_message(msg.message_content, reply_id)
                    last_reply_id = msg.reply_message_id  # 记录原始值
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
