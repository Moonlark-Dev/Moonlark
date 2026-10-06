"""Chat Context：会话上下文的唯一持有者

从 message queue 中独立出来的上下文管理类。一个 :class:`ChatContext` 绑定一个
base session（由 :class:`~nonebot_plugin_chat.core.message.MessageQueue` 实例化），
负责：

1. 从数据库（``nonebot_plugin_chat_contextmessage``）恢复消息列表：``context_index``
   只增不减，一个会话下最大的 ``context_index`` 就是最新会话；
2. 用同一份消息列表构建 base session（``cached_messages``）与 message queue
   （``build_openai_messages``）需要的列表，两者都不再自己保存消息；
3. 每 5 分钟把内存中的消息列表写回数据库；
4. 接收 message queue / message processor 的消息推送；
5. 用 ``session_id`` 与 ``context_index`` 组成 trace id（``thread_id``）；
6. 处理 reset：保存现有记录后直接换用新的 ``context_index``，注入 system prompt
   与会话元数据（meta）并立即保存。

消息的 block 约定：``block_id == 0`` 表示 system / meta 前导消息，真实 block 从 1
开始。同一 block 的消息会被一起提交给事件总结（默认 50 条，也可以被代码提前触发），
冻结 block 时立刻启用下一个 block_id，因此「第 30 条时提前总结」得到的是一个独立
block，其后的新消息属于下一个 block。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Iterable, Optional, Sequence

from nonebot.log import logger
from nonebot_plugin_openai.types import Message as OpenAIMessage
from nonebot_plugin_orm import get_session
from sqlalchemy import delete, func, select

from ..models import ChatContextMessage, SessionEvent
from ..types import CachedMessage
from ..utils.role import get_role

if TYPE_CHECKING:
    from .session.base import BaseSession

# 前导消息（system prompt / meta）的 block id，不参与事件总结与滑动窗口
PREAMBLE_BLOCK_ID = 0
# 一个 block 的消息条数上限，达到后自动提交事件总结
BLOCK_MESSAGE_LIMIT = 50
# 内存消息列表写回数据库的间隔（秒）
SAVE_INTERVAL_SECONDS = 300
# 单次 chat context 锁定的最长持续时间（秒）
LOCK_TIMEOUT_SECONDS = 600
# 距离上一次 LLM 请求超过该时长（秒）才执行滑动窗口清理（provider 缓存约 10 分钟过期）
SLIDING_WINDOW_IDLE_SECONDS = 600
# 恢复上下文时，最后一条消息早于当天该小时则立即 reset
RESET_HOUR = 2
# 只有 message queue 推送上来的消息才带 request id：LLM 输出与工具返回。
# 请求失败时按 request id 删除这些消息，user / system 消息（含注入进请求的图片与提示）不会丢。
REQUEST_ID_ROLES = ("assistant", "tool")
# 提供给 base session 的消息列表上限（与旧实现的 clean_cached_message 一致）
CACHED_MESSAGE_LIMIT = 50


class MessageCursorClosed(RuntimeError):
    """message cursor 已失效：chat context 已解锁或超时"""


def _message_content(message: OpenAIMessage) -> Any:
    if isinstance(message, dict):
        return message.get("content")
    return getattr(message, "content", None)


def _message_tool_calls(message: OpenAIMessage) -> Optional[list[dict]]:
    raw = message.get("tool_calls") if isinstance(message, dict) else getattr(message, "tool_calls", None)
    if not raw:
        return None
    calls: list[dict] = []
    for call in raw:
        if isinstance(call, dict):
            calls.append(call)
        elif hasattr(call, "model_dump"):
            calls.append(call.model_dump())
        else:  # pragma: no cover - 兜底，理论上不会走到
            calls.append({"id": getattr(call, "id", ""), "type": "function"})
    return calls


def _message_tool_call_id(message: OpenAIMessage) -> Optional[str]:
    if isinstance(message, dict):
        return message.get("tool_call_id")
    return getattr(message, "tool_call_id", None)


def _normalize(value: Any) -> Any:
    """把消息内容规整成可比较、可 JSON 序列化的形式"""
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return _normalize(value.model_dump())
    return value


def message_signature(message: OpenAIMessage) -> str:
    """消息指纹：用于把 message queue 的消息列表与 chat context 的消息对齐"""
    payload = {
        "role": get_role(message),
        "content": _normalize(_message_content(message)),
        "tool_calls": _normalize(_message_tool_calls(message)),
        "tool_call_id": _message_tool_call_id(message),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def serialize_cached_message(message: CachedMessage) -> dict:
    """把 CachedMessage 转成可 JSON 序列化的 dict（图片由 content 中的数据 URL 还原）"""
    data = dict(message)
    send_time = data.get("send_time")
    if isinstance(send_time, datetime):
        data["send_time"] = send_time.isoformat()
    # 不把图片二进制写进数据库：图片已经以 data URL 的形式存在于 content 里
    data.pop("images", None)
    return data


def _deserialize_cached_message(data: dict, content: Any) -> CachedMessage:
    message = dict(data)
    send_time = message.get("send_time")
    if isinstance(send_time, str):
        try:
            message["send_time"] = datetime.fromisoformat(send_time)
        except ValueError:
            message["send_time"] = datetime.now()
    elif not isinstance(send_time, datetime):
        message["send_time"] = datetime.now()
    message.setdefault("content", "")
    message.setdefault("nickname", "")
    message.setdefault("user_id", "")
    message.setdefault("platform_user_id", "")
    message.setdefault("self", False)
    message.setdefault("message_id", "")
    message.setdefault("to_me", False)
    message.setdefault("triggered_reply", False)
    message["images"] = _extract_images(content)
    return message  # type: ignore[return-value]


def _extract_images(content: Any) -> list[bytes]:
    """从消息 content 的多模态 part 中还原图片二进制"""
    images: list[bytes] = []
    if not isinstance(content, list):
        return images
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "image_url":
            continue
        image_url = part.get("image_url")
        url = image_url.get("url") if isinstance(image_url, dict) else None
        if not isinstance(url, str) or not url.startswith("data:"):
            continue
        try:
            _, encoded = url.split(",", 1)
            images.append(base64.b64decode(encoded))
        except (ValueError, binascii.Error):
            logger.debug("恢复消息缓存时跳过无法解码的图片")
    return images


@dataclass
class ContextMessage:
    """chat context 中的一条消息（对应数据库中的一行）"""

    session_id: str
    context_index: int
    index: int
    block_id: int
    role: str
    sub_type: str
    timestamp: datetime
    content: Any
    data: Optional[dict] = None
    display_only: bool = False
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None
    trigger_type: str = "none"
    request_id: Optional[str] = None

    @property
    def is_preamble(self) -> bool:
        return self.block_id == PREAMBLE_BLOCK_ID

    @property
    def is_display_only(self) -> bool:
        """只用于展示的消息：被拦截的用户消息、实际发送出去的 assistant 回复

        它们带有 processor 解析出来的 json（``data``，即 CachedMessage），会出现在
        base session 的消息列表里，但不进入 LLM 的消息列表。
        """
        return self.display_only

    @property
    def in_llm_context(self) -> bool:
        return not self.display_only

    def signature(self) -> str:
        payload = {
            "role": self.role,
            "content": _normalize(self.content),
            "tool_calls": _normalize(self.tool_calls),
            "tool_call_id": self.tool_call_id,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

    def to_openai(self) -> OpenAIMessage:
        if self.role == "tool":
            return {"role": "tool", "tool_call_id": self.tool_call_id or "", "content": self.content}
        if self.role == "assistant":
            message: dict[str, Any] = {"role": "assistant", "content": self.content}
            if self.tool_calls:
                message["tool_calls"] = self.tool_calls
            return message  # type: ignore[return-value]
        return {"role": self.role, "content": self.content}  # type: ignore[return-value]

    def to_cached_message(self) -> Optional[CachedMessage]:
        if self.data is None:
            return None
        return _deserialize_cached_message(self.data, self.content)

    def to_row(self) -> ChatContextMessage:
        return ChatContextMessage(
            session_id=self.session_id,
            context_index=self.context_index,
            index=self.index,
            block_id=self.block_id,
            role=self.role,
            sub_type=self.sub_type,
            timestamp=self.timestamp,
            content=json.dumps(_normalize(self.content), ensure_ascii=False),
            data=json.dumps(self.data, ensure_ascii=False) if self.data is not None else None,
            display_only=self.display_only,
            tool_calls=json.dumps(self.tool_calls, ensure_ascii=False) if self.tool_calls else None,
            tool_call_id=self.tool_call_id,
            trigger_type=self.trigger_type,
            request_id=self.request_id,
        )

    @classmethod
    def from_row(cls, row: ChatContextMessage) -> "ContextMessage":
        return cls(
            session_id=row.session_id,
            context_index=row.context_index,
            index=row.index,
            block_id=row.block_id,
            role=row.role,
            sub_type=row.sub_type,
            timestamp=row.timestamp,
            content=json.loads(row.content) if row.content is not None else None,
            data=json.loads(row.data) if row.data else None,
            display_only=bool(row.display_only),
            tool_calls=json.loads(row.tool_calls) if row.tool_calls else None,
            tool_call_id=row.tool_call_id,
            trigger_type=row.trigger_type,
            request_id=row.request_id,
        )

    @classmethod
    def from_openai(
        cls,
        session_id: str,
        message: OpenAIMessage,
        *,
        block_id: int,
        sub_type: str = "",
        trigger_type: str = "none",
        request_id: Optional[str] = None,
        data: Optional[dict] = None,
        display_only: bool = False,
        timestamp: Optional[datetime] = None,
    ) -> "ContextMessage":
        role = get_role(message)
        if not sub_type and role == "user":
            # 直接由消息列表解析出来的 user 消息都是提示 / 事件类
            sub_type = "event"
        return cls(
            session_id=session_id,
            context_index=0,
            index=0,
            block_id=block_id,
            role=role,
            sub_type=sub_type,
            timestamp=timestamp or datetime.now(),
            content=_normalize(_message_content(message)),
            data=data,
            display_only=display_only,
            tool_calls=_message_tool_calls(message),
            tool_call_id=_message_tool_call_id(message),
            trigger_type=trigger_type,
            request_id=request_id,
        )


class MessageCursor:
    """message queue 向 chat context 申请的写入 / 拉取游标

    - ``request_id``：本次请求的标识，只打在 message queue 推送上来的消息（LLM 输出与
      工具返回）上，请求失败时按它删除这些消息；
    - 提供给 message queue 的缓冲队列也放在这里；
    - chat context 解锁（请求结束或超时）后 cursor 立即失效，继续操作会抛
      :class:`MessageCursorClosed`。
    """

    def __init__(self, context: "ChatContext", request_id: str) -> None:
        self._context = context
        self.request_id = request_id
        # 提供给 message queue 拉取的缓冲队列
        self.buffer: list[ContextMessage] = []
        self._released = False

    @property
    def released(self) -> bool:
        return self._released

    def _ensure_active(self) -> None:
        if self._released:
            raise MessageCursorClosed(f"message cursor {self.request_id} 已失效")

    async def submit(self, messages: Sequence[OpenAIMessage]) -> list[ContextMessage]:
        """把 message queue 的完整消息列表提交给 chat context 解析"""
        self._ensure_active()
        return await self._context.absorb_messages(messages, self.request_id)

    def drain(self) -> list[ContextMessage]:
        """拉取增量消息（拉取即写入 chat context 的消息列表）"""
        self._ensure_active()
        drained, self.buffer = self.buffer, []
        self._context.commit_drained(drained)
        return drained

    def push(self, messages: Sequence[ContextMessage]) -> None:
        """把 processor 缓冲队列整体移交给 message queue（仅由 chat context 调用）"""
        self.buffer.extend(messages)

    async def report(self, success: bool) -> None:
        """汇报请求状态；失败时删除本次请求产生的所有消息"""
        if self._released:
            return
        await self._context.release(self, success)

    def _release(self) -> None:
        self._released = True


class ChatContext:
    """一个 base session 的上下文"""

    def __init__(self, session: "BaseSession") -> None:
        self.session = session
        self.context_index: int = 0
        self._messages: list[ContextMessage] = []
        self._cached_messages: Optional[list[CachedMessage]] = None
        self._next_index: int = 0
        self._block_id: int = 1
        self._next_block_id: int = 1
        self._block_message_count: int = 0
        self._unsummarized_blocks: list[int] = []
        self._pending: list[ContextMessage] = []
        self._cursor: Optional[MessageCursor] = None
        self._processor_buffer: list[ContextMessage] = []
        self._lock_deadline: Optional[datetime] = None
        self._watchdog: Optional[asyncio.Task] = None
        self._save_task: Optional[asyncio.Task] = None
        self._restored = False
        self._on_lock_timeout: Optional[Callable[[], Awaitable[None]]] = None

    # ------------------------------------------------------------------
    # 基本信息
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self.session.session_id

    @property
    def thread_id(self) -> str:
        """由 session id 与 context index 组成的 trace id"""
        return f"{self.session_id}:{self.context_index}"

    @property
    def messages(self) -> list[ContextMessage]:
        return self._messages

    @property
    def cached_messages(self) -> list[CachedMessage]:
        """base session 需要的消息列表（processor 解析过的消息）

        构建过程需要解码图片数据 URL，因此按需缓存，任何消息变更都会让它失效。
        """
        if self._cached_messages is None:
            cached: list[CachedMessage] = []
            for message in self._messages:
                converted = message.to_cached_message()
                if converted is not None:
                    cached.append(converted)
            self._cached_messages = cached
        # base session 只需要最近的一段消息（旧实现用 clean_cached_message 裁剪到 50 条）
        return self._cached_messages[-CACHED_MESSAGE_LIMIT:]

    def invalidate_cached_messages(self) -> None:
        self._cached_messages = None

    @property
    def current_block_id(self) -> int:
        return self._block_id

    @property
    def unsummarized_blocks(self) -> list[int]:
        """已冻结但尚未成功生成事件总结的 block"""
        return list(self._unsummarized_blocks)

    @property
    def pending_block_message_count(self) -> int:
        """当前 block 中尚未提交事件总结的消息数"""
        return self._block_message_count

    @property
    def locked(self) -> bool:
        return self._cursor is not None and not self._cursor.released

    def set_lock_timeout_handler(self, handler: Optional[Callable[[], Awaitable[None]]]) -> None:
        """注册锁定超时回调（由 message queue 用于取消正在进行的请求）"""
        self._on_lock_timeout = handler

    # ------------------------------------------------------------------
    # 恢复 / 保存
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """恢复上下文并启动定时保存"""
        await self.restore()
        if self._save_task is None:
            self._save_task = asyncio.create_task(self._save_loop())

    async def stop(self) -> None:
        if self._save_task is not None:
            self._save_task.cancel()
            self._save_task = None
        await self.save()

    async def restore(self) -> None:
        """从数据库恢复最新的一次会话（context_index 最大的那个）"""
        async with get_session() as db_session:
            max_index = await db_session.scalar(
                select(func.max(ChatContextMessage.context_index)).where(
                    ChatContextMessage.session_id == self.session_id
                )
            )
        if max_index is None:
            self.context_index = 0
            await self._initialize_context()
            self._restored = True
            return

        self.context_index = int(max_index)
        rows = await self._load_rows(self.context_index)
        self._messages = [ContextMessage.from_row(row) for row in rows]
        self._reindex_counters()

        if not self._messages:
            logger.warning(f"[ChatContext:{self.session_id}] context {self.context_index} 为空，重新初始化")
            await self._initialize_context()
            self._restored = True
            return

        logger.info(
            f"[ChatContext:{self.session_id}] 已恢复 context {self.context_index}，共 {len(self._messages)} 条消息"
        )
        # 最新 block 已经提交过事件总结时，新消息属于下一个 block
        if await self._block_has_event(self._block_id):
            self._block_id = self._next_block_id
            self._next_block_id += 1
            self._block_message_count = 0
        last_timestamp = self._messages[-1].timestamp
        if last_timestamp < self._reset_threshold():
            logger.info(f"[ChatContext:{self.session_id}] 最后一条消息早于当天 {RESET_HOUR}:00，立即重置上下文")
            await self.reset()
        else:
            await self._ensure_preamble()
        self._restored = True

    def _reset_threshold(self) -> datetime:
        return datetime.now().replace(hour=RESET_HOUR, minute=0, second=0, microsecond=0)

    def _reindex_counters(self) -> None:
        """根据恢复出来的消息重新计算 index / block 游标"""
        if self._messages:
            self._next_index = max(message.index for message in self._messages) + 1
        else:
            self._next_index = 0
        max_block = max((message.block_id for message in self._messages), default=PREAMBLE_BLOCK_ID)
        if max_block > PREAMBLE_BLOCK_ID:
            self._block_id = max_block
        else:
            self._block_id = PREAMBLE_BLOCK_ID + 1
        self._next_block_id = self._block_id + 1
        self._block_message_count = sum(1 for message in self._messages if message.block_id == self._block_id)
        self._unsummarized_blocks = []

    async def _load_rows(self, context_index: int) -> list[ChatContextMessage]:
        async with get_session() as db_session:
            result = await db_session.scalars(
                select(ChatContextMessage)
                .where(
                    ChatContextMessage.session_id == self.session_id,
                    ChatContextMessage.context_index == context_index,
                )
                .order_by(ChatContextMessage.index)
            )
            return list(result)

    async def _block_has_event(self, block_id: int) -> bool:
        async with get_session() as db_session:
            row = await db_session.scalar(
                select(SessionEvent.id).where(
                    SessionEvent.session_id == self.session_id,
                    SessionEvent.block_id == block_id,
                )
            )
        return row is not None

    async def save(self) -> None:
        """把内存中尚未落库的消息写回数据库"""
        if not self._pending:
            return
        pending = self._pending
        self._pending = []
        try:
            async with get_session() as db_session:
                for message in pending:
                    await db_session.merge(message.to_row())
                await db_session.commit()
        except Exception as e:
            self._pending = pending + self._pending
            logger.exception(f"[ChatContext:{self.session_id}] 保存上下文失败: {e}")

    async def _save_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(SAVE_INTERVAL_SECONDS)
                await self.save()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover - 防御性兜底
            logger.exception(f"[ChatContext:{self.session_id}] 定时保存任务异常退出: {e}")

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    async def reset(self) -> None:
        """保存现有记录后换用新的 context_index，并注入 system prompt 与会话元数据"""
        await self.save()
        self.context_index += 1
        await self._initialize_context()

    async def _initialize_context(self) -> None:
        """清空内存并写入 system prompt + meta，随后立即保存"""
        self._messages = []
        self._pending = []
        self._processor_buffer = []
        self._cached_messages = None
        self._next_index = 0
        self._block_id = 1
        self._next_block_id = 2
        self._block_message_count = 0
        self._unsummarized_blocks = []

        system_prompt = await self.session.processor.generate_system_prompt()
        await self._commit(
            ContextMessage.from_openai(
                self.session_id,
                system_prompt,
                block_id=PREAMBLE_BLOCK_ID,
                timestamp=datetime.now(),
            )
        )
        await self._commit(
            ContextMessage(
                session_id=self.session_id,
                context_index=self.context_index,
                index=0,
                block_id=PREAMBLE_BLOCK_ID,
                role="user",
                sub_type="meta",
                timestamp=datetime.now(),
                content=await self._generate_meta_content(),
            )
        )
        await self.save()
        logger.info(f"[ChatContext:{self.session_id}] 已创建新的上下文 {self.context_index}")

    async def _generate_meta_content(self) -> str:
        try:
            return await self.session.processor.generate_session_info()
        except Exception as e:
            logger.warning(f"[ChatContext:{self.session_id}] 生成会话元数据失败: {e}")
            return ""

    # ------------------------------------------------------------------
    # 消息推送
    # ------------------------------------------------------------------

    async def push_user_message(
        self,
        content: Any,
        *,
        sub_type: str = "message",
        data: Optional[dict] = None,
        trigger_type: str = "none",
        timestamp: Optional[datetime] = None,
        display_only: bool = False,
    ) -> ContextMessage:
        return await self._push(
            ContextMessage(
                session_id=self.session_id,
                context_index=self.context_index,
                index=0,
                block_id=self._block_id,
                role="user",
                sub_type=sub_type,
                timestamp=timestamp or datetime.now(),
                content=_normalize(content),
                data=data,
                display_only=display_only,
                trigger_type=trigger_type if sub_type != "meta" else "none",
            )
        )

    async def push_assistant_message(
        self,
        content: Any,
        *,
        data: Optional[dict] = None,
        tool_calls: Optional[list[dict]] = None,
        timestamp: Optional[datetime] = None,
        display_only: bool = False,
    ) -> ContextMessage:
        return await self._push(
            ContextMessage(
                session_id=self.session_id,
                context_index=self.context_index,
                index=0,
                block_id=self._block_id,
                role="assistant",
                sub_type="",
                timestamp=timestamp or datetime.now(),
                content=_normalize(content),
                data=data,
                display_only=display_only,
                tool_calls=tool_calls,
            )
        )

    async def push_tool_message(
        self,
        content: Any,
        tool_call_id: str,
        *,
        timestamp: Optional[datetime] = None,
    ) -> ContextMessage:
        return await self._push(
            ContextMessage(
                session_id=self.session_id,
                context_index=self.context_index,
                index=0,
                block_id=self._block_id,
                role="tool",
                sub_type="",
                timestamp=timestamp or datetime.now(),
                content=_normalize(content),
                tool_call_id=tool_call_id,
            )
        )

    async def _push(self, message: ContextMessage) -> ContextMessage:
        # 展示用的 assistant 消息（实际发送出去的内容）不影响 LLM 消息列表，直接落库
        if self.locked and not message.is_display_only:
            self._processor_buffer.append(message)
            self._on_processor_buffer_updated()
            return message
        return await self._commit(message)

    def _on_processor_buffer_updated(self) -> None:
        """processor 缓冲队列出现 trigger_type 为 all 的消息时，整队移交给 message queue"""
        if not any(message.trigger_type == "all" for message in self._processor_buffer):
            return
        if self._cursor is not None:
            self._cursor.push(self._processor_buffer)
        self._processor_buffer = []
        self._refresh_lock_deadline()
        logger.debug(f"[ChatContext:{self.session_id}] 检测到 all 触发消息，已提前把缓冲队列交给 message queue")

    def _refresh_lock_deadline(self) -> None:
        if self._cursor is not None:
            self._lock_deadline = datetime.now() + timedelta(seconds=LOCK_TIMEOUT_SECONDS)

    async def _commit(self, message: ContextMessage) -> ContextMessage:
        message.context_index = self.context_index
        message.index = self._next_index
        self._next_index += 1
        self._messages.append(message)
        self._pending.append(message)
        self._cached_messages = None
        if not message.is_preamble:
            self._block_message_count += 1
            if self._block_message_count >= BLOCK_MESSAGE_LIMIT:
                self._request_event_collection()
        return message

    def _request_event_collection(self) -> None:
        from .ego.event_collector import event_collector

        event_collector.request_collection(self.session)

    # ------------------------------------------------------------------
    # block
    # ------------------------------------------------------------------

    def freeze_block(self, block_id: int) -> bool:
        """冻结当前 block（提交事件总结）并启用下一个 block_id

        冻结后新消息属于新的 block，因此「第 30 条时提前触发总结」得到的是一个
        独立 block，不会与后面的消息混在一起。
        """
        if block_id != self._block_id:
            return False
        self._unsummarized_blocks.append(block_id)
        self._block_id = self._next_block_id
        self._next_block_id += 1
        self._block_message_count = 0
        return True

    def mark_block_summarized(self, block_id: int) -> None:
        if block_id in self._unsummarized_blocks:
            self._unsummarized_blocks.remove(block_id)

    def block_messages(self, block_id: int) -> list[CachedMessage]:
        """某个 block 的消息（用于生成事件总结）"""
        result: list[CachedMessage] = []
        for message in self._messages:
            if message.block_id != block_id:
                continue
            cached = message.to_cached_message()
            if cached is None:
                if isinstance(message.content, str):
                    text = message.content
                elif message.content is None:
                    text = "[工具调用]"
                else:
                    text = json.dumps(message.content, ensure_ascii=False)
                cached = {
                    "content": text,
                    "nickname": "Moonlark",
                    "user_id": "",
                    "platform_user_id": "",
                    "send_time": message.timestamp,
                    "images": [],
                    "self": True,
                    "message_id": "",
                    "to_me": False,
                    "triggered_reply": False,
                }
            result.append(cached)
        return result

    def block_history_string(self, block_id: int) -> str:
        lines = [
            f"[{message['send_time'].strftime('%H:%M:%S')}][{message['nickname']}]: {message.get('content', '')}"
            for message in self.block_messages(block_id)
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 消息列表构建
    # ------------------------------------------------------------------

    async def build_openai_messages(self, regenerate_system_prompt: bool = True) -> list[OpenAIMessage]:
        """构建 message queue 需要的消息列表（同时做合法性与工具配对修复）"""
        await self._ensure_preamble(regenerate_system_prompt=regenerate_system_prompt)
        await self._repair_tool_pairing()
        return [message.to_openai() for message in self._messages if message.in_llm_context]

    async def ensure_system_prompt(self) -> None:
        """轻量检查：保证 system prompt / meta 存在（不做内容重生成）"""
        await self._ensure_preamble(regenerate_system_prompt=False)

    async def _ensure_preamble(self, regenerate_system_prompt: bool = False) -> None:
        """检查第一条消息为 system、第二条为 user + meta，否则修复消息列表"""
        head_ok = (
            len(self._messages) >= 2
            and self._messages[0].role == "system"
            and self._messages[1].role == "user"
            and self._messages[1].sub_type == "meta"
        )
        if head_ok:
            if regenerate_system_prompt:
                await self._refresh_system_prompt()
            return

        logger.warning(f"[ChatContext:{self.session_id}] 消息列表前导结构异常，开始修复")
        # 删除全部前导消息后重新插入一份，保证它们一定排在消息列表最前面
        removed = [message for message in self._messages if message.role == "system" or message.sub_type == "meta"]
        if removed:
            await self._delete_messages(removed)

        first_index = min((message.index for message in self._messages), default=0)
        system_prompt = await self.session.processor.generate_system_prompt()
        system_message = ContextMessage.from_openai(
            self.session_id, system_prompt, block_id=PREAMBLE_BLOCK_ID, timestamp=datetime.now()
        )
        meta_message = ContextMessage(
            session_id=self.session_id,
            context_index=self.context_index,
            index=0,
            block_id=PREAMBLE_BLOCK_ID,
            role="user",
            sub_type="meta",
            timestamp=datetime.now(),
            content=await self._generate_meta_content(),
        )
        system_message.index = first_index - 2
        meta_message.index = first_index - 1
        self._messages.insert(0, meta_message)
        self._messages.insert(0, system_message)
        self._pending.extend([system_message, meta_message])

    async def _refresh_system_prompt(self) -> None:
        """system prompt 模板变化后更新前导消息的内容"""
        try:
            expected = await self.session.processor.generate_system_prompt()
        except Exception as e:
            logger.debug(f"[ChatContext:{self.session_id}] 生成 system prompt 失败: {e}")
            return
        expected_content = _normalize(_message_content(expected))
        if self._messages[0].content != expected_content:
            logger.info(f"[ChatContext:{self.session_id}] system prompt 已更新")
            self._messages[0].content = expected_content
            self._pending.append(self._messages[0])
            self._cached_messages = None

    async def refresh_meta(self) -> None:
        """更新 meta 消息（会话元数据）"""
        for message in self._messages:
            if message.role == "user" and message.sub_type == "meta":
                content = await self._generate_meta_content()
                if message.content != content:
                    message.content = content
                    self._pending.append(message)
                    self._cached_messages = None
                return

    async def _repair_tool_pairing(self) -> None:
        """删除孤立的工具调用 / 工具返回（孤立的工具调用删除整个 assistant 消息）"""
        llm_messages = [message for message in self._messages if message.in_llm_context]
        tool_ids = {message.tool_call_id for message in llm_messages if message.role == "tool" and message.tool_call_id}
        orphan_assistants = [
            message
            for message in llm_messages
            if message.role == "assistant"
            and message.tool_calls
            and any(call.get("id") not in tool_ids for call in message.tool_calls)
        ]
        if not orphan_assistants:
            orphan_tools = [
                message
                for message in llm_messages
                if message.role == "tool" and message.tool_call_id not in self._valid_tool_call_ids(llm_messages)
            ]
            if orphan_tools:
                logger.warning(f"[ChatContext:{self.session_id}] 删除 {len(orphan_tools)} 条孤立的工具返回")
                await self._delete_messages(orphan_tools)
            return

        orphan_ids = {id(message) for message in orphan_assistants}
        valid_call_ids: set[str] = set()
        for message in llm_messages:
            if id(message) in orphan_ids or not message.tool_calls:
                continue
            valid_call_ids.update(call.get("id") for call in message.tool_calls)

        removed = list(orphan_assistants)
        removed.extend(
            message for message in llm_messages if message.role == "tool" and message.tool_call_id not in valid_call_ids
        )
        logger.warning(f"[ChatContext:{self.session_id}] 删除 {len(orphan_assistants)} 条孤立的工具调用及其工具返回")
        await self._delete_messages(removed)

    @staticmethod
    def _valid_tool_call_ids(llm_messages: Iterable[ContextMessage]) -> set[str]:
        valid: set[str] = set()
        for message in llm_messages:
            if message.role == "assistant" and message.tool_calls:
                valid.update(call.get("id") for call in message.tool_calls)
        return valid

    async def _delete_messages(self, messages: Sequence[ContextMessage]) -> None:
        if not messages:
            return
        targets = set(id(message) for message in messages)
        self._messages = [message for message in self._messages if id(message) not in targets]
        self._pending = [message for message in self._pending if id(message) not in targets]
        self._processor_buffer = [message for message in self._processor_buffer if id(message) not in targets]
        if self._cursor is not None:
            self._cursor.buffer = [message for message in self._cursor.buffer if id(message) not in targets]
        self._cached_messages = None
        try:
            async with get_session() as db_session:
                for message in messages:
                    await db_session.execute(
                        delete(ChatContextMessage).where(
                            ChatContextMessage.session_id == self.session_id,
                            ChatContextMessage.context_index == message.context_index,
                            ChatContextMessage.index == message.index,
                        )
                    )
                await db_session.commit()
        except Exception as e:
            logger.exception(f"[ChatContext:{self.session_id}] 删除消息失败: {e}")

    # ------------------------------------------------------------------
    # 锁与缓冲队列
    # ------------------------------------------------------------------

    async def acquire_cursor(self) -> MessageCursor:
        """锁定 chat context 并分配 request id"""
        if self.locked:
            raise RuntimeError(f"[ChatContext:{self.session_id}] 已被锁定")
        self._processor_buffer = []
        cursor = MessageCursor(self, uuid.uuid4().hex)
        self._cursor = cursor
        self._lock_deadline = datetime.now() + timedelta(seconds=LOCK_TIMEOUT_SECONDS)
        self._watchdog = asyncio.create_task(self._watch_lock_timeout())
        return cursor

    async def _watch_lock_timeout(self) -> None:
        try:
            while self.locked:
                deadline = self._lock_deadline
                if deadline is None:
                    return
                delay = (deadline - datetime.now()).total_seconds()
                if delay > 0:
                    await asyncio.sleep(delay)
                    continue
                logger.warning(f"[ChatContext:{self.session_id}] 锁定超过 {LOCK_TIMEOUT_SECONDS}s，以失败解锁")
                cursor = self._cursor
                if cursor is not None:
                    await self.release(cursor, success=False)
                if self._on_lock_timeout is not None:
                    try:
                        await self._on_lock_timeout()
                    except Exception as e:  # pragma: no cover - 防御性兜底
                        logger.exception(f"[ChatContext:{self.session_id}] 锁定超时回调失败: {e}")
                return
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover - 防御性兜底
            logger.exception(f"[ChatContext:{self.session_id}] 锁定看门狗异常: {e}")

    async def release(self, cursor: MessageCursor, success: bool) -> None:
        """解锁 chat context：失败时删除本次请求产生的消息，并接收 processor 缓冲队列"""
        if self._cursor is not cursor:
            return
        self._cursor = None
        self._lock_deadline = None
        cursor._release()
        watchdog, self._watchdog = self._watchdog, None
        if watchdog is not None and watchdog is not asyncio.current_task():
            watchdog.cancel()

        if not success:
            await self.discard_request(cursor.request_id)

        cursor.buffer.clear()
        pending = self._processor_buffer
        self._processor_buffer = []
        for message in pending:
            await self._commit(message)

    async def discard_request(self, request_id: str) -> None:
        """删除某次请求产生的所有消息"""
        removed = [message for message in self._messages if message.request_id == request_id]
        if not removed:
            return
        logger.info(f"[ChatContext:{self.session_id}] 请求 {request_id} 失败，删除 {len(removed)} 条消息")
        await self._delete_messages(removed)

    def commit_drained(self, drained: Sequence[ContextMessage]) -> None:
        """把 message queue 拉取的增量消息加入 chat context 的消息列表"""
        if not drained:
            return
        self._cached_messages = None
        for message in drained:
            message.context_index = self.context_index
            message.index = self._next_index
            self._next_index += 1
            self._messages.append(message)
            self._pending.append(message)
            if not message.is_preamble:
                self._block_message_count += 1
        if self._block_message_count >= BLOCK_MESSAGE_LIMIT:
            self._request_event_collection()

    async def absorb_messages(
        self, messages: Sequence[OpenAIMessage], request_id: Optional[str] = None
    ) -> list[ContextMessage]:
        """把 message queue 的完整消息列表提交给 chat context 解析

        与 chat context 已有的 LLM 消息列表做前缀对齐，多出来的部分作为本次请求
        新产生的消息（assistant 输出、工具调用与工具返回）追加进来。
        """
        llm_messages = [message for message in self._messages if message.in_llm_context]
        known = [message.signature() for message in llm_messages]
        position = 0
        while (
            position < len(messages)
            and position < len(known)
            and message_signature(messages[position]) == known[position]
        ):
            position += 1
        if position < len(known):
            logger.warning(
                f"[ChatContext:{self.session_id}] message queue 的消息列表与上下文不一致"
                f"（第 {position} 条起），按新消息追加"
            )

        added: list[ContextMessage] = []
        for message in messages[position:]:
            role = get_role(message)
            context_message = ContextMessage.from_openai(
                self.session_id,
                message,
                block_id=self._block_id,
                # 只有 message queue 推送上来的消息（LLM 输出与工具返回）才带 request id：
                # 请求失败时据此删除这些消息，user / system 消息不会丢
                request_id=request_id if role in REQUEST_ID_ROLES else None,
            )
            added.append(await self._commit(context_message))
        return added

    # ------------------------------------------------------------------
    # 滑动窗口
    # ------------------------------------------------------------------

    async def last_request_time(self) -> Optional[datetime]:
        """上一次请求的时间：最后一条带 request id 的消息的 timestamp"""
        timestamps = [message.timestamp for message in self._messages if message.request_id]
        return max(timestamps) if timestamps else None

    async def run_sliding_window(self) -> bool:
        """provider 缓存过期后清理不再相关的历史 block

        从新到旧遍历当前 context 的所有 block（最新 block 不参与删除）：如果某个
        block 的事件不再出现在最后一个 block 的事件中（由 Jev 判断），则从这个
        block 开始、此前的消息全部删除，并更新 meta 消息。

        Returns:
            是否真的执行了清理
        """
        last_request = await self.last_request_time()
        if last_request is None:
            return False
        if datetime.now() - last_request <= timedelta(seconds=SLIDING_WINDOW_IDLE_SECONDS):
            return False

        blocks = sorted({message.block_id for message in self._messages if message.block_id > PREAMBLE_BLOCK_ID})
        if len(blocks) < 2:
            return False

        latest_block = blocks[-1]
        latest_events = await self._get_block_events_text(latest_block)
        if not latest_events:
            return False

        truncate_from: Optional[int] = None
        for block_id in reversed(blocks[:-1]):
            events_text = await self._get_block_events_text(block_id)
            if not events_text:
                truncate_from = block_id
                break
            if not await self._block_still_relevant(events_text, latest_events):
                truncate_from = block_id
                break
        if truncate_from is None:
            return False

        await self._truncate_from_block(truncate_from)
        return True

    async def _get_block_events_text(self, block_id: int) -> str:
        from .ego.event_collector import format_event_content

        async with get_session() as db_session:
            result = await db_session.scalars(
                select(SessionEvent)
                .where(
                    SessionEvent.session_id == self.session_id,
                    SessionEvent.block_id == block_id,
                )
                .order_by(SessionEvent.created_at)
            )
            events = list(result)
        return "\n".join(format_event_content(event.content) for event in events)

    async def _block_still_relevant(self, history_events: str, latest_events: str) -> bool:
        from nonebot_plugin_jev import JevNotConfigured, NoulAnswer, ask, lang_ref, noul

        from ..utils.jev_judge import SLIDING_WINDOW_RELEVANT_THRESHOLD

        state = {"history_events": history_events, "latest_events": latest_events}
        try:
            answers = await ask(
                state,
                {"still_relevant": noul(lang_ref("context_window.block_relevant"))},
                lang_str=self.session.lang_str,
                identify="Chat Context Window",
            )
        except JevNotConfigured as e:
            logger.warning(f"[ChatContext:{self.session_id}] 滑动窗口判断跳过：{e}")
            return True
        except Exception as e:
            logger.warning(f"[ChatContext:{self.session_id}] 滑动窗口判断失败: {e}")
            return True
        answer = answers.get("still_relevant")
        if not isinstance(answer, NoulAnswer):
            return True
        return answer.noul >= SLIDING_WINDOW_RELEVANT_THRESHOLD

    async def _truncate_from_block(self, block_id: int) -> None:
        # 前导消息（block 0）永远保留，被删除的是 block_id 及其之前的所有 block
        removed = [
            message
            for message in self._messages
            if message.block_id != PREAMBLE_BLOCK_ID and block_id <= message.block_id
        ]
        logger.info(
            f"[ChatContext:{self.session_id}] 滑动窗口清理：删除 block {block_id} 及此前的 {len(removed)} 条消息"
        )
        await self._delete_messages(removed)
        # 被删掉的可能是当前 block 的消息（事件总结尚未生成），需要同步游标
        remaining_blocks = [message.block_id for message in self._messages if message.block_id > PREAMBLE_BLOCK_ID]
        if remaining_blocks:
            max_block = max(remaining_blocks)
            if self._block_id < max_block:
                self._block_id = max_block
            self._block_message_count = sum(1 for b in remaining_blocks if b == self._block_id)
        else:
            self._block_message_count = 0
        self._unsummarized_blocks = [b for b in self._unsummarized_blocks if b in set(remaining_blocks)]
        await self._ensure_preamble()
        await self.refresh_meta()
