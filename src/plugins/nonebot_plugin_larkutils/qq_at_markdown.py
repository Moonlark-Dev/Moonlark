"""QQ 官方机器人 @ 提及的 markdown 发送适配。

QQ 官方机器人已不再支持在非 markdown 消息（``msg_type=0``）里使用 at：
``<qqbot-at-user>`` 只有在 markdown 消息（``msg_type=2``）中才会被渲染成真正的
@。alconna 的 ``at_sender`` / ``UniMessage.at()`` 都会把 at 导出成普通的
``mention_user`` 段，整条消息于是以纯文本发出，@ 因而失效。

这里接管 alconna 的 QQ 消息导出器：只要一条群聊消息里含有 at 段，就把整条
消息改写成 markdown 消息再发送。图片、ARK、embed 等富媒体消息保持原样——
QQ 的图片消息（``msg_type=7``）不能携带 markdown，强行改写会丢掉图片。

``nonebot_plugin_chat`` 的回复保持纯文本（其中的 at 由聊天语义决定），通过
``skip_at_markdown()`` 上下文管理器显式排除；其他插件不需要改动，
``matcher.send(..., at_sender=True)`` 与 ``lang.send`` 都会自动生效。
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from nonebot.adapters import Bot, Event
from nonebot.adapters.qq.event import GroupMessageCreateEvent, InteractionCreateEvent
from nonebot.adapters.qq.message import Message, MessageSegment
from nonebot_plugin_alconna.uniseg import Target
from nonebot_plugin_alconna.uniseg.adapters import EXPORTER_MAPPING
from nonebot_plugin_alconna.uniseg.adapters.qq.exporter import QQMessageExporter
from nonebot_plugin_alconna.uniseg.constraint import SupportAdapter

# 需要保留在消息里的非文本段：键盘按钮、引用消息
_PRESERVED_SEGMENTS = {"$qq:button", "$qq:button_row", "keyboard", "reference"}
# 可以直接转成 markdown 文本的段
_TEXTUAL_SEGMENTS = {"text", "emoji", "mention_user", "mention_everyone"}
# markdown 消息自带的段
_MARKDOWN_SEGMENT = "markdown"

_skip_at_markdown: ContextVar[bool] = ContextVar("qq_skip_at_markdown", default=False)


@contextmanager
def skip_at_markdown() -> Iterator[None]:
    """在上下文内跳过「带 at 的消息转 markdown」。

    chat 插件用它保持纯文本回复：QQ 官方下这些消息里的 at 不会被渲染，
    但聊天回复的排版比 @ 更重要，因此保持原样。
    """
    token = _skip_at_markdown.set(True)
    try:
        yield
    finally:
        _skip_at_markdown.reset(token)


def _is_group_target(target: Target | Event) -> bool:
    """判断消息是否发往 QQ 群聊（只有群聊才需要 / 支持 markdown 里的 at）。"""
    if isinstance(target, Target):
        return not target.private and not target.channel
    if isinstance(target, GroupMessageCreateEvent):
        return True
    if isinstance(target, InteractionCreateEvent):
        return bool(getattr(target, "group_openid", None))
    return False


def _message_to_markdown(message: Message) -> Message | None:
    """把含 at 的 QQ 消息改写为 markdown 消息。

    无可改写的 at、或消息里含有无法转成 markdown 的段（图片等）时返回 ``None``，
    由调用方按原消息发送。
    """
    if _skip_at_markdown.get():
        return None
    if not any(seg.type in {"mention_user", "mention_everyone"} for seg in message):
        return None

    parts: list[str] = []
    preserved: list[MessageSegment] = []
    for seg in message:
        if seg.type == "text":
            parts.append(seg.data["text"])
        elif seg.type in _TEXTUAL_SEGMENTS:
            parts.append(str(seg))
        elif seg.type == _MARKDOWN_SEGMENT:
            parts.append(seg.data["markdown"].content or "")
        elif seg.type in _PRESERVED_SEGMENTS:
            preserved.append(seg)
        else:
            # 图片 / ARK / embed / 文件等无法塞进 markdown，保持原消息
            return None

    content = "".join(parts)
    if not content.strip():
        return None
    return Message([MessageSegment.markdown(content), *preserved])


class QQAtMarkdownExporter(QQMessageExporter):
    """把带 at 的 QQ 群聊消息自动改写成 markdown 的导出器。"""

    def __init__(self) -> None:
        super().__init__()
        # MessageExporter.__init__ 只登记子类自身定义的方法，这里补上父类的
        # 段导出映射（text / at / keyboard ...），否则子类会丢掉全部映射。
        self._mapping = QQMessageExporter()._mapping  # ruff: ignore[private-member-access]

    async def send_to(self, target: Target | Event, bot: Bot, message: Message, **kwargs):
        if _is_group_target(target):
            markdown_message = _message_to_markdown(message)
            if markdown_message is not None:
                message = markdown_message
        return await super().send_to(target, bot, message, **kwargs)


def _install_exporter() -> None:
    if isinstance(EXPORTER_MAPPING.get(SupportAdapter.qq.value), QQAtMarkdownExporter):
        return
    EXPORTER_MAPPING[SupportAdapter.qq.value] = QQAtMarkdownExporter()


_install_exporter()
