"""QQ 官方机器人群聊 @ 提及的 Markdown 发送适配。

QQ 官方机器人已不再支持在普通文本消息（``msg_type=0``）中渲染 ``@``：
``<qqbot-at-user>`` 与 ``<qqbot-at-everyone>`` 只有在 Markdown 消息（``msg_type=2``）中
才会被渲染成真正的提及；若留在纯文本或富媒体消息中，还会把原始 ``<qqbot-at-user ... />``
标签文本直接暴露到聊天界面。

与此同时，上游各插件触发 ``@`` 的发送路径并不统一：
1. ``lang.send`` / ``lang.finish`` / ``matcher.send(..., at_sender=True)`` 直接走 ``QQBot.send``，
   完全不经过 ``nonebot_plugin_alconna`` 的 ``QQMessageExporter.send_to``，且 ``QQBot.send`` 自身对群聊
   忽略了 ``at_sender`` 参数；
2. ``UniMessage(...).send(...)``（如 ``chat`` 等插件）经过 ``QQMessageExporter.send_to``；
3. ``matcher.finish(await message.export(), at_sender=True)``（如 ``/panel``、``/waifu``）先导出出原生
   ``Message``（内含 ``file_image`` / ``image`` 段），再交由 ``QQBot.send`` 发送；
4. 直接调用 ``QQBot.send_to_group`` 主动发送带 ``mention_user`` 的群消息。

本模块统一拦截 ``QQMessageExporter.send_to``、``QQBot.send`` 与 ``QQBot.send_to_group``：
- 仅对 QQ 群聊目标生效（排除不支持 ``<qqbot-at-user>`` 的 C2C 单聊与原生支持纯文本提及的频道）；
- 纯文本段自动经 ``escape_markdown`` 转义，已有 ``markdown`` 段保持原样；
- 独占一行的 ``<qqbot-at-*>`` 标签后若紧跟单换行，自动补齐空行以避免触发 CommonMark HTML 块吞掉后续格式；
- 同时包含图片（``file_image`` / ``image``）与 ``@`` 时，自动通过 QQ 素材管理接口（``create_image_markdown``）
  上传并内嵌到 Markdown 中；若下载/上传失败，或含有 ARK、音视频等无法内嵌的富媒体段，则自动剥离提及段后回退原消息，
  既不丢媒体，也不泄露原始 ``<qqbot-at-user>`` 标签。
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from io import BytesIO
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urljoin, urlparse

from nonebot import logger
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq.event import (
    C2CMessageCreateEvent,
    GroupAtMessageCreateEvent,
    GroupMessageCreateEvent,
    InteractionCreateEvent,
)
from nonebot.adapters.qq.message import Message, MessageSegment
from nonebot.drivers import Request
from nonebot_plugin_alconna.uniseg import Target
from nonebot_plugin_alconna.uniseg.adapters.qq.exporter import QQMessageExporter

from .escape import escape_markdown
from .media_image import create_image_markdown
from .url_validator import resolve_internal

if TYPE_CHECKING:
    from collections.abc import Iterator

    from nonebot.adapters import Bot, Event

# 需要原样保留在 Markdown 消息旁边的非正文段：键盘按钮、引用消息
_PRESERVED_SEGMENTS = {"$qq:button", "$qq:button_row", "keyboard", "reference"}
# 提及段类型
_MENTION_SEGMENTS = {"mention_user", "mention_everyone"}
# 下载外网图片时的体积上限（50MB，后续交由 media_image.normalize_image 压缩至平台 10MB 限制内）
_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
# `<qqbot-at-*>` 独占一行且后接单个换行时，CommonMark 会把该行直至下一个空行都视为 HTML 块，
# 导致后续行的转义字符、图片语法或表格失效；补成双换行即可提前闭合 HTML 块。
_AT_LINE_RE = re.compile(
    r"(?m)^([ \t]*(?:<qqbot-at-(?:user\b[^>]*|everyone)\s*/>[ \t]*)+)\r?\n(?!\r?\n)",
)

_skip_at_markdown: ContextVar[bool] = ContextVar("qq_skip_at_markdown", default=False)

_raw_bot_send = QQBot.send
_raw_send_to_group = QQBot.send_to_group
_raw_exporter_send_to = QQMessageExporter.send_to
_installed = False


@contextmanager
def skip_at_markdown() -> Iterator[None]:
    """在当前上下文内跳过「QQ 群聊含 @ 消息自动转 Markdown」。"""
    token = _skip_at_markdown.set(True)
    try:
        yield
    finally:
        _skip_at_markdown.reset(token)


def is_group_event(event: Event) -> bool:
    """判断事件是否来自 QQ 官方群聊（仅群聊需要且支持 ``<qqbot-at-user>``）。"""
    if isinstance(event, C2CMessageCreateEvent):
        return False
    if isinstance(event, (GroupAtMessageCreateEvent, GroupMessageCreateEvent)):
        return True
    if isinstance(event, InteractionCreateEvent):
        group_openid = getattr(event, "group_openid", None)
        return isinstance(group_openid, str) and bool(group_openid)
    if event.__class__.__module__.startswith("nonebot.adapters.qq"):
        group_openid = getattr(event, "group_openid", None)
        return isinstance(group_openid, str) and bool(group_openid)
    return False


def is_group_target(target: Target | Event) -> bool:
    """判断发送目标是否为 QQ 官方群聊。"""
    if isinstance(target, Target):
        if target.adapter is not None and target.adapter != "QQ":
            return False
        return not target.private and not target.channel
    return is_group_event(target)


def _normalize_message(message: str | Message | MessageSegment) -> Optional[Message]:
    """把待发送的消息统一包装为 ``Message``；纯字符串使用 ``MessageSegment.text`` 避免误解析标签。"""
    if isinstance(message, Message):
        return message
    if isinstance(message, MessageSegment):
        return Message([message])
    if isinstance(message, str):
        return Message([MessageSegment.text(message)])
    return None


def _resolve_at_user_id(event: Event, at_sender: Any) -> Optional[str]:
    """从 ``at_sender`` 参数与事件中解析出需要提及的群成员原生 ID（``member_openid``）。"""
    if not at_sender:
        return None
    if isinstance(at_sender, str):
        return at_sender
    try:
        uid = event.get_user_id()
    except Exception:
        return None
    return uid if isinstance(uid, str) and uid else None


def _extract_markdown_content(seg: MessageSegment) -> tuple[str, bool]:
    """提取 ``markdown`` 段的文本内容，并标记是否为不支持拼接的模板 Markdown。"""
    md_obj = seg.data.get("markdown")
    if isinstance(md_obj, dict):
        if md_obj.get("custom_template_id"):
            return "", True
        return str(md_obj.get("content") or ""), False
    if getattr(md_obj, "custom_template_id", None):
        return "", True
    return str(getattr(md_obj, "content", None) or ""), False


def _already_mentions_user(message: Message, user_id: str) -> bool:
    """检查消息中是否已经包含对指定用户的提及（含原生段与已有 Markdown 标签）。"""
    tag_prefix = f'<qqbot-at-user id="{user_id}"'
    for seg in message:
        if seg.type == "mention_user" and seg.data.get("user_id") == user_id:
            return True
        if seg.type == "markdown":
            content, _ = _extract_markdown_content(seg)
            if tag_prefix in content:
                return True
    return False


def _strip_mention_segments(message: Message) -> Optional[Message]:
    """回退原消息时剥离 ``mention_user`` / ``mention_everyone``，防止裸露 ``<qqbot-at-*>`` 标签。

    若原消息本就不含提及段（例如仅因 ``at_sender=True`` 才尝试附加提及），返回 ``None`` 保持原消息不变。
    """
    if not any(seg.type in _MENTION_SEGMENTS for seg in message):
        return None
    remaining = [seg for seg in message if seg.type not in _MENTION_SEGMENTS]
    return Message(remaining) if remaining else None


def _read_path_bytes(path: Path) -> bytes:
    return path.read_bytes()


async def _download_image_bytes(bot: QQBot, url: str) -> bytes:
    """校验外网 URL 并下载图片二进制数据（手动跟踪最多 3 次重定向并逐跳做 SSRF 校验）。"""
    current_url = url
    for _ in range(4):
        parsed = urlparse(current_url)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError(f"不支持的图片 URL 协议: {parsed.scheme!r}")
        if await resolve_internal(parsed):
            raise ValueError("拒绝访问内网或本地图片 URL")
        response = await bot.adapter.request(Request("GET", current_url, timeout=15))
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location") or response.headers.get("location")
            if not location:
                raise RuntimeError(f"图片重定向缺少 Location 头（HTTP {response.status_code}）")
            current_url = urljoin(current_url, location)
            continue
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"下载图片失败（HTTP {response.status_code}）")
        content_length = response.headers.get("Content-Length") or response.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > _MAX_DOWNLOAD_BYTES:
            raise ValueError(f"下载的图片超过 {_MAX_DOWNLOAD_BYTES} 字节上限")
        raw = response.content
        if isinstance(raw, bytes):
            data = raw
        elif isinstance(raw, bytearray):
            data = bytes(raw)
        elif isinstance(raw, str):
            data = raw.encode()
        else:
            data = b""
        if not data:
            raise ValueError("下载到的图片内容为空")
        if len(data) > _MAX_DOWNLOAD_BYTES:
            raise ValueError(f"下载的图片超过 {_MAX_DOWNLOAD_BYTES} 字节上限")
        return data
    raise RuntimeError("图片 URL 重定向次数过多")


async def _extract_image_bytes(seg: MessageSegment, bot: QQBot) -> bytes:
    """从 ``file_image`` 或 ``image`` 段提取图片二进制数据。"""
    if seg.type == "file_image":
        raw_data = seg.data.get("content")
        if raw_data is None:
            raw_data = seg.data.get("file")
        if isinstance(raw_data, bytes):
            return raw_data
        if isinstance(raw_data, (bytearray, memoryview)):
            return bytes(raw_data)
        if isinstance(raw_data, BytesIO):
            return raw_data.getvalue()
        if isinstance(raw_data, Path):
            return await asyncio.to_thread(_read_path_bytes, raw_data)
        if isinstance(raw_data, str):
            return await asyncio.to_thread(_read_path_bytes, Path(raw_data))
        if hasattr(raw_data, "read"):
            read_data = raw_data.read()
            if isinstance(read_data, (bytes, bytearray)):
                return bytes(read_data)
        raise TypeError(f"不支持的 file_image 数据类型: {type(raw_data)!r}")

    url = seg.data.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("image 段缺少有效的 url")
    return await _download_image_bytes(bot, url)


def _ensure_at_block_separation(content: str) -> str:
    """为独占一行的 ``<qqbot-at-*>`` 补齐空行，防止 CommonMark HTML 块吞掉后续内容。"""
    return _AT_LINE_RE.sub(r"\1\n\n", content)


async def convert_group_message(
    message: Message,
    bot: Optional[QQBot] = None,
    at_user_id: Optional[str] = None,
) -> Optional[Message]:
    """将含 ``@`` 的 QQ 群聊消息改写为 Markdown 消息。

    - 消息无需改写（不含 ``@`` 或处于 ``skip_at_markdown()`` 上下文）时返回 ``None``；
    - 图片上传失败或存在无法内嵌的富媒体段时，剥离 ``mention_user`` / ``mention_everyone`` 后返回回退消息
      （若原消息本就不含提及段则返回 ``None``）。
    """
    if _skip_at_markdown.get():
        return None

    working = Message(message)
    if at_user_id and not _already_mentions_user(working, at_user_id):
        working = Message([MessageSegment.mention_user(at_user_id), *working])

    if not any(seg.type in _MENTION_SEGMENTS for seg in working):
        return None

    parts: list[str] = []
    preserved: list[MessageSegment] = []
    for seg in working:
        if seg.type == "mention_user":
            uid = seg.data.get("user_id")
            if uid:
                parts.append(f'<qqbot-at-user id="{uid}" />')
        elif seg.type == "mention_everyone":
            parts.append("<qqbot-at-everyone />")
        elif seg.type == "text":
            parts.append(escape_markdown(str(seg.data.get("text") or "")))
        elif seg.type == "emoji":
            emoji_id = seg.data.get("id")
            parts.append(f"<emoji:{emoji_id}>" if emoji_id is not None else str(seg))
        elif seg.type == "markdown":
            md_content, is_template = _extract_markdown_content(seg)
            if is_template:
                return _strip_mention_segments(message)
            parts.append(md_content)
        elif seg.type in {"file_image", "image"}:
            if bot is None:
                return _strip_mention_segments(message)
            try:
                image_bytes = await _extract_image_bytes(seg, bot)
                image_md = await create_image_markdown(image_bytes, bot)
            except Exception as e:
                logger.warning(f"QQ 群聊含 @ 消息转换图片为 markdown 失败，回退为不带 @ 的原消息: {e}")
                return _strip_mention_segments(message)
            parts.append(image_md)
        elif seg.type in _PRESERVED_SEGMENTS:
            preserved.append(seg)
        else:
            # ARK、embed、音视频、文件等无法内嵌到 markdown，剥离提及段后按原消息发送
            return _strip_mention_segments(message)

    content = _ensure_at_block_separation("".join(parts))
    if not content.strip():
        return _strip_mention_segments(message)
    return Message([MessageSegment.markdown(content), *preserved])


async def _patched_bot_send(
    self: QQBot,
    event: Event,
    message: str | Message | MessageSegment,
    **kwargs: Any,
) -> Any:
    if not _skip_at_markdown.get() and is_group_event(event):
        at_user_id = _resolve_at_user_id(event, kwargs.get("at_sender", False))
        if "at_sender" in kwargs:
            kwargs = {k: v for k, v in kwargs.items() if k != "at_sender"}
        normalized = _normalize_message(message)
        if normalized is not None:
            converted = await convert_group_message(normalized, bot=self, at_user_id=at_user_id)
            if converted is not None:
                message = converted
    return await _raw_bot_send(self, event, message, **kwargs)


async def _patched_send_to_group(
    self: QQBot,
    group_openid: str,
    message: str | Message | MessageSegment,
    *args: Any,
    **kwargs: Any,
) -> Any:
    if not _skip_at_markdown.get():
        normalized = _normalize_message(message)
        if normalized is not None and any(seg.type in _MENTION_SEGMENTS for seg in normalized):
            converted = await convert_group_message(normalized, bot=self)
            if converted is not None:
                message = converted
    return await _raw_send_to_group(self, group_openid, message, *args, **kwargs)


async def _patched_exporter_send_to(
    self: QQMessageExporter,
    target: Target | Event,
    bot: Bot,
    message: Message,
    **kwargs: Any,
) -> Any:
    if not _skip_at_markdown.get() and is_group_target(target):
        at_raw = kwargs.get("at_sender", False)
        if isinstance(target, Target):
            at_user_id = at_raw if isinstance(at_raw, str) and at_raw else None
        else:
            at_user_id = _resolve_at_user_id(target, at_raw)
        if "at_sender" in kwargs:
            kwargs = {k: v for k, v in kwargs.items() if k != "at_sender"}
        qq_bot = bot if isinstance(bot, QQBot) else None
        converted = await convert_group_message(message, bot=qq_bot, at_user_id=at_user_id)
        if converted is not None:
            message = converted
    return await _raw_exporter_send_to(self, target, bot, message, **kwargs)


def install_qq_at_markdown() -> None:
    """幂等地挂载 QQ 群聊含 ``@`` 消息的自动 Markdown 转换钩子。"""
    global _installed
    if _installed:
        return
    QQBot.send = _patched_bot_send  # type: ignore[method-assign]
    QQBot.send_to_group = _patched_send_to_group  # type: ignore[method-assign]
    QQMessageExporter.send_to = _patched_exporter_send_to  # type: ignore[method-assign]
    _installed = True


install_qq_at_markdown()
