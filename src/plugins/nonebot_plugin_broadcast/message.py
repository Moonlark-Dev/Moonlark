"""广播消息构建

抽成独立模块，供提交广播（主动发送）与延迟被动补发共用。
"""

from typing import Optional

from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from typing_extensions import TypedDict

# QQ 官方键盘最多支持 25 个按钮
MAX_BUTTONS = 25

# 长度达到该值的广播在其余平台会被渲染为图片
IMAGE_RENDER_THRESHOLD = 200


class BroadcastButton(TypedDict):
    """广播附带的 QQ 官方自定义按钮"""

    label: str
    text: str


def build_qq_broadcast_message(content: str, buttons: list[BroadcastButton]) -> UniMessage:
    """构建 QQ 官方广播消息：直接以 markdown 发送并附上自定义按钮"""
    message = UniMessage().style(content, "markdown")
    if buttons:
        message.keyboard(
            *[Button("enter", button["label"], text=button["text"]) for button in buttons[:MAX_BUTTONS]],
            row=5,
        )
    return message


async def build_broadcast_message(
    bot: Bot, content: str, buttons: list[BroadcastButton], image: Optional[bytes] = None
) -> UniMessage:
    """按适配器构建广播消息

    QQ 官方机器人直接发送 markdown（不渲染图片），其余平台保持原有行为：
    内容较长时渲染为图片，否则发送纯文本。
    """
    if isinstance(bot, QQBot):
        return build_qq_broadcast_message(content, buttons)
    if len(content) >= IMAGE_RENDER_THRESHOLD:
        return UniMessage().image(raw=image if image is not None else await md_to_pic(content))
    return UniMessage().text(text=content)


async def render_broadcast_image(content: str) -> Optional[bytes]:
    """仅在需要图片渲染时生成一次图片"""
    if len(content) < IMAGE_RENDER_THRESHOLD:
        return None
    return await md_to_pic(content)
