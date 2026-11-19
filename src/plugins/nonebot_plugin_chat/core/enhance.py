"""群聊回复增强：发送前由模型重写一次消息

群聊打开 ``/chat enhance`` 后，Moonlark 通过 ``send_message`` 发出的内容不会直接
发送，而是先交给模型：以 Chat 的 System Prompt（身份、输出规则、interaction 模式）
为背景，参考最近几条对话，把这条消息重写一遍再发出。重写失败、超时或结果为空时
一律回落到原文，绝不阻塞发送。

开关状态保存在 ``ChatGroup.enhance``，由 ``/chat enhance on|off`` 修改；仅当会话
使用 OpenAI Provider 时生效（Gemini 等 Provider 走原文发送）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nonebot.log import logger
from nonebot_plugin_openai import generate_message, get_message_text
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_orm import get_session

from ..models import ChatGroup
from ..utils.provider import get_model_provider

if TYPE_CHECKING:
    from nonebot_plugin_openai.types import Message as OpenAIMessage

    from .processor import MessageProcessor

# 重写时参考的最近对话消息条数
RECENT_MESSAGE_COUNT = 5
# 重写结果的字数上限，超出部分直接截断
MAX_REWRITTEN_LENGTH = 1000
# 重写请求的超时时间（秒）
REWRITE_TIMEOUT_SECONDS = 60
# 模型输出可能整体包裹在旧式引号或引号字符里
_QUOTE_CHARS = "\"'“”‘’"


class ReplyEnhancer:
    """每个会话一个的群聊回复重写器"""

    def __init__(self, processor: "MessageProcessor") -> None:
        self.processor = processor

    @property
    def session(self):
        return self.processor.session

    async def is_enabled(self) -> bool:
        """当前会话是否启用回复增强：群聊 + 开关打开 + OpenAI Provider

        任何一步失败都按未开启处理：读不到开关比多发一条未重写的消息更安全。
        """
        try:
            if self.session.get_session_type() != "group":
                return False
            async with get_session() as db_session:
                group_config = await db_session.get(ChatGroup, {"group_id": self.session.session_id})
            # 兼容还没有 enhance 字段的旧配置对象：缺失按关闭处理
            if not group_config or not getattr(group_config, "enhance", False):
                return False
            return await get_model_provider(self.session.session_id) == "openai"
        except Exception as e:
            logger.warning(f"读取群聊回复增强开关失败，按关闭处理: {e}")
            return False

    async def process(self, content: str) -> tuple[str, bool]:
        """按开关重写消息，返回 ``(实际发送内容, 是否被重写)``"""
        if not content or not content.strip():
            return content, False
        if not await self.is_enabled():
            return content, False
        rewritten = await self.rewrite(content)
        if not rewritten or rewritten == content:
            return content, False
        return rewritten, True

    async def rewrite(self, content: str) -> str:
        """调用模型重写一条准备发送的消息（失败或结果为空时返回原文）"""
        try:
            messages = await self._build_messages(content)
            response = await fetch_message(
                messages,
                identify="Chat Enhance - Rewrite Message",
                timeout=REWRITE_TIMEOUT_SECONDS,
                reasoning_effort="low",
            )
        except Exception as e:
            logger.warning(f"重写群聊回复失败，使用原文发送: {e}")
            return content
        rewritten = self._sanitize(response or "")
        if not rewritten:
            logger.warning("重写群聊回复得到空结果，使用原文发送")
            return content
        return rewritten

    async def _build_messages(self, content: str) -> list[OpenAIMessage]:
        """构造重写请求：Chat 的 System Prompt + 任务说明 + 最近对话 + 待发送内容"""
        system_prompt = await self.processor.generate_system_prompt()
        task_prompt = await get_message_text("chat_enhance/system.md.jinja")
        system_content = f"{self._extract_content(system_prompt).strip()}\n\n{task_prompt.strip()}".strip()
        recent_messages = await self.session.get_cached_messages_string(
            length=RECENT_MESSAGE_COUNT,
            include_self_message=True,
        )
        user_content = await get_message_text(
            "chat_enhance/user.md.jinja",
            recent_messages=recent_messages or "（暂无）",
            draft=content,
        )
        return [
            generate_message(system_content, "system"),
            generate_message(user_content, "user"),
        ]

    @staticmethod
    def _extract_content(message: Any) -> str:
        """取出 System Prompt 的文本内容（content 可能是字符串或多模态分段列表）"""
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                text = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
                if text:
                    parts.append(str(text))
            return "\n".join(parts)
        return str(content or "")

    @staticmethod
    def _sanitize(text: str) -> str:
        """清洗模型输出：去空白、去代码块与引号、限制长度"""
        result = str(text).strip()
        result = ReplyEnhancer._strip_codeblock(result)
        result = ReplyEnhancer._strip_quotes(result)
        return result[:MAX_REWRITTEN_LENGTH].strip()

    @staticmethod
    def _strip_codeblock(text: str) -> str:
        """剥掉整体包裹的 Markdown 代码块（含 ``text`` 这样的语言标记）"""
        if not (text.startswith("```") and text.endswith("```")) or len(text) <= 6:
            return text
        inner = text[3:-3]
        if "\n" in inner:
            first_line, rest = inner.split("\n", 1)
            # 开头的 ``` 后面可能紧跟语言标记（```text），整行丢弃；否则保留正文
            if not first_line.strip() or " " not in first_line.strip():
                inner = rest
        return inner.strip()

    @staticmethod
    def _strip_quotes(text: str) -> str:
        """剥掉整体包裹的引号（可能叠了多层）"""
        result = text.strip()
        while len(result) >= 2 and result[0] in _QUOTE_CHARS and result[-1] in _QUOTE_CHARS:
            result = result[1:-1].strip()
        return result
