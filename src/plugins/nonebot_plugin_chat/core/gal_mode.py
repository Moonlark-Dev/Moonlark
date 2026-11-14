"""私聊回复的延迟发送与备选回复生成

开关打开后，私聊中 Moonlark 通过 ``send_message`` 发出的消息不会立即发送，而是
进入一个容量为 1 的发送缓存：每次调用把当前消息放进缓存，并把上一条被挤出缓存
的消息真正发出。一轮回复结束时，把这一轮的最近对话、Moonlark 发出的消息、思考
内容与当前状态交给模型生成 1~3 条备选回复，再把缓存里最后一条消息以 markdown
（附带备选回复按钮）的形式发出。

开关状态保存在 ``PrivateChatConfig.gal_mode``，由 ``/gal-mode on|off`` 修改。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from nonebot.log import logger
from nonebot_plugin_openai.utils.chat import fetch_json
from nonebot_plugin_openai.utils.message import get_messages
from nonebot_plugin_orm import get_session
from pydantic import BaseModel, Field

from nonebot_plugin_larkutils.subaccount import get_main_account

from ..models import PrivateChatConfig
from ..utils.status_manager import get_status_manager

if TYPE_CHECKING:
    from .processor import MessageProcessor

# 备选回复的条数上限
MAX_SUGGESTIONS = 3
# 单条备选回复的最大字数（按钮文本与回传文本共用）
MAX_SUGGESTION_LENGTH = 100
# 生成备选回复时参考的最近对话消息条数
RECENT_MESSAGE_COUNT = 5
# 单条历史消息的最大展示长度
MAX_HISTORY_MESSAGE_LENGTH = 300
# 提供给模型的思考内容最大长度
MAX_THOUGHT_LENGTH = 2000


@dataclass
class BufferedMessage:
    """进入发送缓存的一条消息"""

    content: str
    reply_message_id: str | None
    token_cost: int
    queued_at: datetime


class GalModeSuggestions(BaseModel):
    """备选回复生成结果"""

    replies: list[str] = Field(default_factory=list, description="用户可能接着发来的 1~3 条消息")


class GalModeManager:
    """每个会话一个的私聊备选回复状态"""

    def __init__(self, processor: "MessageProcessor") -> None:
        self.processor = processor
        self._enabled = False
        self._active = False
        self._buffer: list[BufferedMessage] = []
        self._round_messages: list[BufferedMessage] = []
        self._recent_messages: list[str] = []
        self._thought_baseline = ""
        self._output_baseline = None

    @property
    def session(self):
        return self.processor.session

    @property
    def pending_contents(self) -> list[str]:
        """当前缓存中尚未发出的消息内容（供回复后判定参考）"""
        return [message.content for message in self._buffer]

    def has_sent_since(self, since: datetime) -> bool:
        """本轮是否已经通过 ``send_message`` 发送（或缓存）过消息"""
        return any(message.queued_at >= since for message in self._round_messages)

    def should_buffer(self) -> bool:
        """当前这次 ``send_message`` 是否需要进入发送缓存"""
        return self._active

    async def begin_round(self) -> None:
        """一轮回复开始：加载开关状态并记录回复前的对话快照"""
        self._buffer.clear()
        self._round_messages.clear()
        self._recent_messages = self._snapshot_recent_messages()
        self._thought_baseline = getattr(self.processor, "_latest_reasioning_content_cache", "") or ""
        self._output_baseline = self.processor.openai_messages.last_thought
        self._enabled = await self._load_enabled()
        self._active = self._enabled
        if self._enabled:
            logger.debug(f"会话 {self.session.session_id} 已开启私聊备选回复")

    async def enqueue(self, content: str, reply_message_id: str | None, token_cost: int) -> BufferedMessage | None:
        """把当前消息放进缓存，返回被挤出缓存、需要立即发送的消息"""
        message = BufferedMessage(
            content=content,
            reply_message_id=reply_message_id,
            token_cost=token_cost,
            queued_at=datetime.now(),
        )
        self._buffer.append(message)
        self._round_messages.append(message)
        if len(self._buffer) <= 1:
            return None
        return self._buffer.pop(0)

    async def finish_round(self) -> None:
        """一轮回复结束：生成备选回复并发出缓存中最后一条消息"""
        self._active = False
        if not self._buffer:
            self._reset_round_state()
            return
        message = self._buffer.pop()
        self._buffer.clear()
        try:
            suggestions = await self._generate_suggestions()
        except Exception as e:
            logger.warning(f"生成备选回复失败: {e}")
            suggestions = []
        try:
            await self.processor.deliver_buffered_message(message, suggestions)
        except Exception as e:
            logger.exception(f"发送缓存消息失败: {e}")
        finally:
            self._reset_round_state()

    def abort_round(self) -> None:
        """本轮被主动停止或超时：丢弃缓存，不再补发消息与生成备选回复"""
        self._reset_round_state()

    def _reset_round_state(self) -> None:
        self._active = False
        self._buffer.clear()
        self._round_messages.clear()
        self._recent_messages = []

    async def _load_enabled(self) -> bool:
        """读取当前私聊用户的开关状态（群聊恒为关闭）"""
        if self.session.get_session_type() != "private":
            return False
        adapter_user_id = getattr(self.session, "adapter_user_id", None)
        if not adapter_user_id:
            return False
        try:
            user_id = await get_main_account(str(adapter_user_id))
            async with get_session() as db_session:
                config = await db_session.get(PrivateChatConfig, {"user_id": user_id})
                return bool(config and config.gal_mode)
        except Exception as e:
            logger.warning(f"读取私聊备选回复开关失败: {e}")
            return False

    def _snapshot_recent_messages(self) -> list[str]:
        """回复开始前的最近几条对话消息"""
        lines: list[str] = []
        for message in self.session.cached_messages[-RECENT_MESSAGE_COUNT:]:
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            content = re.sub(r"\s+", " ", content)[:MAX_HISTORY_MESSAGE_LENGTH]
            nickname = "Moonlark" if message.get("self") else (message.get("nickname") or "用户")
            lines.append(f"{nickname}: {content}")
        return lines

    def _collect_thought(self) -> str:
        """收集本轮产生的思考内容（没有新内容时返回空串）"""
        reasoning = getattr(self.processor, "_latest_reasioning_content_cache", "") or ""
        if reasoning == self._thought_baseline:
            reasoning = ""
        output = self.processor.openai_messages.last_thought or ""
        if output == (self._output_baseline or ""):
            output = ""
        parts: list[str] = []
        for part in (reasoning, output):
            part = part.strip()
            if not part or any(part in existing or existing in part for existing in parts):
                continue
            parts.append(part)
        return "\n\n".join(parts)[:MAX_THOUGHT_LENGTH]

    async def _generate_suggestions(self) -> list[str]:
        """调用模型生成 1~3 条备选回复"""
        from .ego.moonlark_main import moonlark_main

        session = self.session
        status_manager = get_status_manager()
        mood, mood_reason = status_manager.get_status()
        mood_text = await session.text(f"status.mood.{mood.value}")
        tiredness = round(moonlark_main.sleep_controller.tiredness * 100)
        sent_messages = "\n".join(f"- {message.content}" for message in self._round_messages) or "（本轮没有发送消息）"
        messages = await get_messages(
            "gal_mode",
            recent_messages="\n".join(self._recent_messages) or "（暂无）",
            sent_messages=sent_messages,
            thought=self._collect_thought() or "（本轮没有记录到思考内容）",
            mood=mood_text,
            mood_intensity=round(status_manager.get_mood_retention(), 2),
            mood_reason=mood_reason or await session.text("status.no_reason"),
            tiredness=tiredness,
            nickname=getattr(session, "nickname", "") or session.session_id,
        )
        result = await fetch_json(
            messages,
            GalModeSuggestions,
            identify="GalMode - Suggest Replies",
            reasoning_effort="low",
            timeout=60,
        )
        return self._sanitize_suggestions(result.replies)

    @staticmethod
    def _sanitize_suggestions(replies: list[str]) -> list[str]:
        """清洗模型输出：去空白、去重、限制长度与条数"""
        suggestions: list[str] = []
        for reply in replies:
            text = re.sub(r"\s+", " ", str(reply)).strip()
            if not text:
                continue
            text = text[:MAX_SUGGESTION_LENGTH]
            if text in suggestions:
                continue
            suggestions.append(text)
            if len(suggestions) >= MAX_SUGGESTIONS:
                break
        return suggestions
