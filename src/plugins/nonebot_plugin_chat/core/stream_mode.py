"""私聊流式发送（实验性功能）

实验性功能，**默认关闭**，需要用户用 ``/chat stream on`` 显式开启。开关打开后，
私聊中 Chat 主模型的请求会改用流式传输（见
``nonebot_plugin_openai.utils.chat.MessageFetcher``）。模型流式输出
``send_message`` 工具调用的参数分片时，这里从参数 JSON 中增量解析出消息正文，
再通过 QQ 官方机器人的「流式发送单聊消息」接口同步发送消息片段，让用户看到回复
逐字出现的效果。

接口文档：
https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_openid_stream_messages.post.html

只有 QQ 官方机器人的私聊（能拿到被动回复用的 ``msg_id``）才会真正分片发送；
其它适配器或场景仍按普通方式发送消息。开关状态保存在
``PrivateChatConfig.stream``，由 ``/chat stream on|off`` 修改；它与私聊备选回复
（``PrivateChatConfig.gal_mode``）互斥，指令层保证不会同时开启。
"""

from __future__ import annotations

import asyncio
import string
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from nonebot.adapters.qq import Bot as QQBot
from nonebot.drivers import Request
from nonebot.log import logger
from nonebot_plugin_larkutils.subaccount import get_main_account
from nonebot_plugin_orm import get_session

from ..models import PrivateChatConfig
from ..utils.provider import get_model_provider

if TYPE_CHECKING:
    from .processor import MessageProcessor

# 触发流式分片发送的工具名
SEND_MESSAGE_TOOL = "send_message"
# 两次分片之间的最小间隔（秒）：QQ 流式消息接口限制 50 QPS，按 token 逐片发送没有必要
MIN_SEND_INTERVAL = 0.5
# 内容超过该长度时不再逐片更新（超出 QQ 单条消息长度限制后平台会拒绝整个流式消息）
MAX_STREAM_CONTENT_LENGTH = 2000

# JSON 字符串里可以直接映射的转义字符
_JSON_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


def extract_partial_json_string(arguments: str, key: str = "message_content") -> Optional[str]:
    """从（可能尚未完整的）JSON 参数里取出指定键的字符串值

    流式工具调用的 ``arguments`` 是一段段拼起来的 JSON，在调用结束前通常不完整。
    这里只解析 ``key`` 对应的那个字符串（``send_message`` 的 ``message_content``），
    遇到未闭合的字符串或未写完的转义序列就返回已经解析出的前缀。

    Returns:
        已解析出的字符串前缀；还没有出现该键或值不是字符串时返回 ``None``。
    """
    marker = f'"{key}"'
    position = arguments.find(marker)
    if position < 0:
        return None
    index = position + len(marker)
    while index < len(arguments) and arguments[index].isspace():
        index += 1
    if index >= len(arguments) or arguments[index] != ":":
        return None
    index += 1
    while index < len(arguments) and arguments[index].isspace():
        index += 1
    if index >= len(arguments) or arguments[index] != '"':
        return None
    index += 1

    chars: list[str] = []
    while index < len(arguments):
        char = arguments[index]
        if char == '"':
            return "".join(chars)
        if char != "\\":
            chars.append(char)
            index += 1
            continue
        if index + 1 >= len(arguments):
            # 转义序列还没写完，先返回已解析的前缀
            return "".join(chars)
        escape = arguments[index + 1]
        if escape == "u":
            if index + 6 > len(arguments):
                return "".join(chars)
            code = arguments[index + 2 : index + 6]
            if any(digit not in string.hexdigits for digit in code):
                return "".join(chars)
            chars.append(chr(int(code, 16)))
            index += 6
            continue
        if escape not in _JSON_ESCAPES:
            # 非法转义，停止解析，避免把后面的内容误当成正文
            return "".join(chars)
        chars.append(_JSON_ESCAPES[escape])
        index += 2
    return "".join(chars)


async def request_stream_message(bot: QQBot, openid: str, payload: dict[str, Any]) -> dict[str, Any]:
    """调用 QQ 官方「流式发送单聊消息」接口

    适配器（1.7.3）尚未封装该接口，这里复用它的通用请求方法以获得鉴权与
    access_token 刷新。
    """
    request = Request(
        "POST",
        bot.adapter.get_api_base().joinpath("v2", "users", openid, "stream_messages"),
        json=payload,
        timeout=30,
    )
    data = await bot._request(request)  # ruff: ignore[private-member-access]
    return data if isinstance(data, dict) else {}


class QQStreamMessageSender:
    """一条流式消息的发送状态

    每个分片都携带从第一条响应里拿到的 ``stream_msg_id``，``index`` 从 0 递增；
    ``input_mode=replace`` 表示 ``content_raw`` 是当前全量正文（前缀不能修改）。
    """

    def __init__(
        self,
        bot: QQBot,
        openid: str,
        msg_id: str,
        msg_seq: Optional[int] = None,
    ) -> None:
        self.bot = bot
        self.openid = openid
        self.msg_id = msg_id
        self.msg_seq = msg_seq
        self.stream_msg_id: Optional[str] = None
        self.index = 0
        self.closed = False

    async def send(self, content: str, *, final: bool = False) -> Optional[str]:
        """发送一个分片，返回流式消息 ID（首片响应里生成）"""
        if self.closed:
            return self.stream_msg_id
        payload: dict[str, Any] = {
            "input_mode": "replace",
            "input_state": 10 if final else 1,
            "index": self.index,
            "content_type": "text",
            "content_raw": content,
            "msg_id": self.msg_id,
        }
        if self.msg_seq is not None:
            payload["msg_seq"] = self.msg_seq
        if self.stream_msg_id:
            payload["stream_msg_id"] = self.stream_msg_id
        data = await request_stream_message(self.bot, self.openid, payload)
        self.index += 1
        if self.stream_msg_id is None:
            message_id = data.get("id")
            self.stream_msg_id = str(message_id) if message_id else None
        if final:
            self.closed = True
        return self.stream_msg_id


@dataclass
class _StreamedCall:
    """一次 ``send_message`` 工具调用的流式发送状态"""

    index: int
    call_id: str = ""
    name: str = ""
    arguments: str = ""
    # 从 arguments 中解析出的完整/前缀正文
    content: str = ""
    # 已经发给平台的内容（格式化后）
    sent_content: str = ""
    sender: Optional[QQStreamMessageSender] = None
    last_send_at: float = 0.0
    completed: bool = False
    failed: bool = False


class StreamModeManager:
    """每个会话一个的私聊流式发送状态"""

    def __init__(self, processor: "MessageProcessor") -> None:
        self.processor = processor
        self._enabled = False
        self._active = False
        self._sender_ready = False
        self._provider = ""
        self._openid = ""
        self._reply_message_id = ""
        self._msg_seq: Optional[int] = None
        self._calls: dict[int, _StreamedCall] = {}
        # (原始正文, 实际发送正文, 消息 ID)：工具真正执行时据此跳过重复发送
        self._streamed: list[tuple[str, str, str]] = []

    @property
    def session(self) -> Any:
        return self.processor.session

    @property
    def active(self) -> bool:
        """本轮是否处于流式发送状态（工具执行时用于判断是否需要跳过普通发送）"""
        return self._enabled

    def should_stream(self) -> bool:
        """本轮 Chat 主模型请求是否改用流式传输"""
        return self._enabled

    @property
    def streaming(self) -> bool:
        """本轮正文是否真的会作为流式消息发出

        需要同时满足：开关打开（``/chat stream``）、当前会话是 QQ 官方私聊
        （``_sender_ready``）、Provider 支持流式请求（Gemini 没有流式接口）。
        正文真的走流式消息时，这条消息本身已经是对触发消息的被动回复，
        ``send_message`` 据此吞掉 ``reply_message_id``，避免同一条内容出现两条消息。
        """
        return self._enabled and self._sender_ready and self._provider != "gemini"

    async def begin_round(self) -> None:
        """一轮回复开始：加载开关状态并检查当前会话能否分片发送"""
        self._reset_round_state()
        self._enabled = await self._load_enabled()
        if not self._enabled:
            return
        self._provider = await self._load_provider()
        session = self.session
        self._active = session.get_session_type() == "private"
        bot = session.bot
        target = session.target
        # 只有 QQ 官方私聊能把触发消息作为被动回复的 msg_id，其它适配器无法调用
        # 流式消息接口，保持普通发送
        self._sender_ready = bool(
            self._active
            and isinstance(bot, QQBot)
            and getattr(target, "private", False)
            and getattr(target, "source", ""),
        )
        if not self._sender_ready:
            return
        self._openid = str(target.id)
        self._reply_message_id = str(target.source)
        reply_seq = getattr(target, "extra", {}).get("qq.reply_seq")
        self._msg_seq = reply_seq if isinstance(reply_seq, int) else None
        logger.debug(f"会话 {session.session_id} 已开启私聊流式发送")

    async def handle_stream_chunk(self, chunk: Any) -> None:
        """处理主模型流式响应的一个分片

        从 ``delta.tool_calls`` 里累积 ``send_message`` 的参数，并及时把新增正文
        通过流式消息接口同步发送出去。
        """
        if not self._enabled:
            return
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return
        choice = choices[0]
        delta = getattr(choice, "delta", None)
        if delta is not None:
            for tool_call in getattr(delta, "tool_calls", None) or []:
                await self._handle_tool_call_delta(tool_call)
        if getattr(choice, "finish_reason", None):
            await self._finalize_calls()

    async def consume_streamed_message(self, content: str) -> Optional[str]:
        """工具真正执行时检查正文是否已经流式发出

        Returns:
            已经发出时返回平台消息 ID；没有流式发送则返回 ``None``，调用方继续按
            普通消息发送。
        """
        if not self._enabled:
            return None
        for index, (streamed_content, _, message_id) in enumerate(self._streamed):
            if streamed_content == content:
                self._streamed.pop(index)
                return message_id
        # 部分 Provider 不发送 finish_reason 分片：工具执行时才发现调用还没收尾，
        # 这里用完整正文补发结束分片，避免真的再发一遍普通消息
        for call in self._calls.values():
            if (
                call.name == SEND_MESSAGE_TOOL
                and not call.completed
                and not call.failed
                and call.sender is not None
                and call.content == content
            ):
                await self._send_fragment(call, content, final=True)
                if call.completed:
                    return call.sender.stream_msg_id or ""
        return None

    async def finish_round(self) -> None:
        """一轮结束：收尾尚未结束的流式消息并清理状态"""
        await self._finalize_calls()
        self._reset_round_state()

    async def abort_round(self) -> None:
        """本轮被主动停止或超时：尽力收尾已发送的流式消息，避免用户一直看到生成中"""
        try:
            # 停止指令不应该被网络请求拖住：收尾最多等 3 秒
            await asyncio.wait_for(self._finalize_calls(), timeout=3)
        except Exception as e:  # pragma: no cover - 收尾失败不影响停止流程
            logger.warning(f"收尾流式消息失败: {e}")
        self._reset_round_state()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    async def _handle_tool_call_delta(self, tool_call: Any) -> None:
        index = getattr(tool_call, "index", 0)
        try:
            index = int(index)
        except (TypeError, ValueError):
            index = 0
        call = self._calls.get(index)
        call_id = getattr(tool_call, "id", None)
        if call is None or (call_id and call.call_id and str(call_id) != call.call_id):
            # 同一轮里的下一次请求会重新从 index 0 开始，用新的 call id 区分
            call = _StreamedCall(index=index, call_id=str(call_id) if call_id else "")
            self._calls[index] = call
        elif call_id:
            call.call_id = str(call_id)

        function = getattr(tool_call, "function", None)
        if function is not None:
            name = getattr(function, "name", None)
            if name:
                call.name = str(name)
            arguments = getattr(function, "arguments", None)
            if arguments:
                call.arguments += str(arguments)

        if call.name != SEND_MESSAGE_TOOL or not self._sender_ready or call.failed:
            return
        content = extract_partial_json_string(call.arguments)
        if content is None or not content:
            return
        if len(content) > MAX_STREAM_CONTENT_LENGTH:
            logger.warning(f"流式消息内容超过 {MAX_STREAM_CONTENT_LENGTH} 字，本轮改为普通发送")
            call.failed = True
            return
        call.content = content
        formatted = await self._format_content(content)
        if call.sender is None:
            call.sender = QQStreamMessageSender(self.session.bot, self._openid, self._reply_message_id, self._msg_seq)
            await self._send_fragment(call, content, formatted=formatted)
            return
        if content == call.sent_content:
            return
        if time.monotonic() - call.last_send_at < MIN_SEND_INTERVAL:
            return
        await self._send_fragment(call, content, formatted=formatted)

    async def _format_content(self, content: str) -> str:
        """按会话规则格式化正文（与 ``_deliver_message`` 的普通消息保持一致）"""
        try:
            message = await self.session.format_message(content)
            return message.extract_plain_text() or content
        except Exception as e:  # pragma: no cover - 格式化失败时退回原文
            logger.debug(f"格式化流式消息失败，使用原文: {e}")
            return content

    async def _send_fragment(
        self,
        call: _StreamedCall,
        content: str,
        *,
        formatted: Optional[str] = None,
        final: bool = False,
    ) -> None:
        if call.sender is None or call.failed:
            return
        text = formatted if formatted is not None else await self._format_content(content)
        if not text:
            return
        try:
            message_id = await call.sender.send(text, final=final)
        except Exception as e:
            logger.warning(f"流式发送消息分片失败，本轮改为普通发送: {e}")
            call.failed = True
            return
        call.sent_content = content
        call.last_send_at = time.monotonic()
        if final:
            call.completed = True
            self._streamed.append((content, text, message_id or ""))

    async def _finalize_calls(self) -> None:
        """给本轮所有尚未结束的 ``send_message`` 调用发送结束分片"""
        for call in list(self._calls.values()):
            if call.failed or call.completed or call.sender is None or not call.content:
                continue
            await self._send_fragment(call, call.content, final=True)
        self._calls.clear()

    async def _load_enabled(self) -> bool:
        """读取当前私聊用户的开关状态（群聊恒为关闭，没有记录时默认关闭）"""
        if self.session.get_session_type() != "private":
            return False
        adapter_user_id = getattr(self.session, "adapter_user_id", None)
        if not adapter_user_id:
            return False
        try:
            user_id = await get_main_account(str(adapter_user_id))
            async with get_session() as db_session:
                config = await db_session.get(PrivateChatConfig, {"user_id": user_id})
                if config is None:
                    # 私聊流式发送是实验性功能，默认关闭：还没有配置记录的用户视为关闭
                    return False
                if config.gal_mode:
                    # 历史数据或异常情况下两者同时为真时，让备选回复优先，避免重复发送
                    logger.warning(f"用户 {user_id} 同时开启了流式发送与私聊备选回复，本轮按备选回复处理")
                    return False
                return bool(config.stream)
        except Exception as e:
            logger.warning(f"读取私聊流式发送开关失败: {e}")
            return False

    async def _load_provider(self) -> str:
        """读取当前会话的 Chat Provider；读取失败时按 OpenAI 处理（与默认值一致）"""
        try:
            return await get_model_provider(self.session.session_id)
        except Exception as e:
            logger.warning(f"读取会话 Provider 失败，按 openai 处理: {e}")
            return "openai"

    def _reset_round_state(self) -> None:
        self._active = False
        self._sender_ready = False
        self._provider = ""
        self._openid = ""
        self._reply_message_id = ""
        self._msg_seq = None
        self._calls.clear()
        self._streamed.clear()
