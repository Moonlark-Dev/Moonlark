#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################

"""
QQ 官方机器人按钮工具模块

提供构建 InlineKeyboard 消息和处理按钮交互的工具函数。

QQ 官方机器人按钮限制：
- 按钮不能单独发送，必须搭配 Markdown 消息段
- 每行按钮建议不超过 5 个
- button_data 回调数据最长 32 字节
- 自定义 keyboard 和模版 keyboard 二选一
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from nonebot.adapters.qq.bot import Bot as QQBot
    from nonebot.adapters.qq.event import InteractionCreateEvent
    from nonebot.adapters.qq.message import Message


# ---------------------------------------------------------------------------
# Data models (lightweight wrappers, not importing pydantic models at module level
# to avoid import errors when the QQ adapter is not installed)
# ---------------------------------------------------------------------------

ButtonType = Literal["link", "callback", "qqbot", "minigame"]


@dataclass
class ButtonDef:
    """单个按钮定义"""

    id: str
    """按钮唯一标识，也是交互事件中返回的 button_id"""

    label: str
    """按钮显示文字"""

    action_type: ButtonType = "callback"
    """动作类型：link=打开链接, callback=回调机器人, qqbot=打开指定qqbot, minigame=跳转小程序"""

    data: str | None = None
    """回调数据 (action_type=callback 时最长 32 字节)"""

    style: int = 1
    """按钮样式：1=蓝色(主按钮), 2=灰色"""

    visited_label: str | None = None
    """点击后显示的文字"""

    url: str | None = None
    """链接地址 (action_type=link 时使用)"""

    permission_type: int = 0
    """权限类型：0=所有人可点, 1=指定用户/身份组"""

    permission_user_ids: list[str] = field(default_factory=list)
    """允许点击的用户 openid 列表 (permission_type=1)"""

    permission_role_ids: list[str] = field(default_factory=list)
    """允许点击的身份组 ID 列表 (permission_type=1)"""

    reply: bool = False
    """是否弹出回复框"""

    enter: bool = False
    """是否自动发送 (需 reply=True)"""

    unsupport_tips: str | None = None
    """不支持时的提示文字"""


@dataclass
class KeyboardDef:
    """按钮键盘定义，支持链式构建"""

    rows: list[list[ButtonDef]] = field(default_factory=list)

    def add_row(self, *buttons: ButtonDef) -> KeyboardDef:
        """添加一行按钮"""
        self.rows.append(list(buttons))
        return self

    def add_button(
        self,
        row_index: int,
        button: ButtonDef,
    ) -> KeyboardDef:
        """在指定行添加按钮，行不存在则自动创建"""
        while len(self.rows) <= row_index:
            self.rows.append([])
        self.rows[row_index].append(button)
        return self


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------

_ACTION_TYPE_MAP = {
    "link": 0,
    "callback": 1,
    "qqbot": 2,
    "minigame": 3,
}


def build_button(
    id: str,
    label: str,
    *,
    action_type: ButtonType = "callback",
    data: str | None = None,
    style: int = 1,
    visited_label: str | None = None,
    url: str | None = None,
    permission_type: int = 0,
    permission_user_ids: list[str] | None = None,
    permission_role_ids: list[str] | None = None,
    reply: bool = False,
    enter: bool = False,
    unsupport_tips: str | None = None,
) -> ButtonDef:
    """构建单个按钮定义

    Args:
        id: 按钮唯一标识
        label: 按钮显示文字
        action_type: 动作类型 (link/callback/qqbot/minigame)
        data: 回调数据，最长 32 字节
        style: 按钮样式 (1=蓝色, 2=灰色)
        visited_label: 点击后显示的文字
        url: 链接地址 (action_type=link)
        permission_type: 权限类型 (0=所有人, 1=指定)
        permission_user_ids: 允许点击的用户列表
        permission_role_ids: 允许点击的身份组列表
        reply: 是否弹出回复框
        enter: 是否自动发送
        unsupport_tips: 不支持时的提示
    """
    return ButtonDef(
        id=id,
        label=label,
        action_type=action_type,
        data=data,
        style=style,
        visited_label=visited_label,
        url=url,
        permission_type=permission_type,
        permission_user_ids=permission_user_ids or [],
        permission_role_ids=permission_role_ids or [],
        reply=reply,
        enter=enter,
        unsupport_tips=unsupport_tips,
    )


def build_link_button(
    id: str,
    label: str,
    url: str,
    *,
    style: int = 1,
    visited_label: str | None = None,
) -> ButtonDef:
    """构建链接按钮快捷函数"""
    return build_button(
        id=id,
        label=label,
        action_type="link",
        url=url,
        style=style,
        visited_label=visited_label,
    )


def build_callback_button(
    id: str,
    label: str,
    data: str,
    *,
    style: int = 1,
    visited_label: str | None = None,
    reply: bool = False,
    enter: bool = False,
) -> ButtonDef:
    """构建回调按钮快捷函数

    Args:
        id: 按钮唯一标识
        label: 按钮文字
        data: 回调数据 (最长 32 字节)
        style: 按钮样式
        visited_label: 点击后文字
        reply: 是否弹出回复框
        enter: 是否自动发送
    """
    return build_button(
        id=id,
        label=label,
        action_type="callback",
        data=data,
        style=style,
        visited_label=visited_label,
        reply=reply,
        enter=enter,
    )


def build_keyboard(*rows: list[ButtonDef]) -> KeyboardDef:
    """构建键盘定义

    用法::

        keyboard = build_keyboard(
            [btn_confirm, btn_cancel],
            [btn_help],
        )
    """
    return KeyboardDef(rows=[list(row) for row in rows])


# ---------------------------------------------------------------------------
# QQ Adapter Message construction
# ---------------------------------------------------------------------------

_TYPE_INT_MAP = {"link": 0, "callback": 1, "qqbot": 2, "minigame": 3}


def _build_qq_models(keyboard: KeyboardDef):
    """构建 QQ Adapter 原生模型对象，返回 (MessageKeyboard, list[错误信息])"""
    from nonebot.adapters.qq.models.common import (
        Action,
        Button,
        InlineKeyboard,
        InlineKeyboardRow,
        MessageKeyboard,
        Permission,
        RenderData,
    )

    errors: list[str] = []
    rows: list[InlineKeyboardRow] = []

    for row_idx, row in enumerate(keyboard.rows):
        buttons: list[Button] = []
        for btn in row:
            # 构建 Permission
            permission = None
            if btn.permission_type == 1:
                permission = Permission(
                    type=1,
                    specify_user_ids=btn.permission_user_ids or None,
                    specify_role_ids=btn.permission_role_ids or None,
                )

            # 构建 Action
            action_type_int = _TYPE_INT_MAP.get(btn.action_type, 1)
            action = Action(
                type=action_type_int,
                permission=permission,
                data=btn.data,
                reply=btn.reply if btn.reply else None,
                enter=btn.enter if btn.enter else None,
                unsupport_tips=btn.unsupport_tips,
            )

            # 构建 RenderData
            render_data = RenderData(
                label=btn.label,
                visited_label=btn.visited_label,
                style=btn.style,
            )

            button = Button(
                id=btn.id,
                render_data=render_data,
                action=action,
            )
            buttons.append(button)

        rows.append(InlineKeyboardRow(buttons=buttons))

    keyboard_model = MessageKeyboard(content=InlineKeyboard(rows=rows))
    return keyboard_model, errors


def build_keyboard_message(
    markdown_content: str,
    keyboard: KeyboardDef,
    *,
    template_id: str | None = None,
    custom_template_id: str | None = None,
) -> Message:
    """构建带按钮的 QQ 消息

    按钮消息必须搭配 Markdown 才能发送 (msg_type=2)。

    Args:
        markdown_content: Markdown 正文内容
        keyboard: 键盘定义
        template_id: Markdown 模版 ID (与 custom_template_id 二选一)
        custom_template_id: 自定义模版 ID

    Returns:
        QQ Adapter Message 对象
    """
    from nonebot.adapters.qq.message import Message, MessageSegment
    from nonebot.adapters.qq.models.qq import MessageMarkdown

    keyboard_model, _ = _build_qq_models(keyboard)

    markdown = MessageMarkdown(
        content=markdown_content,
        template_id=int(template_id) if template_id else None,
        custom_template_id=custom_template_id,
    )

    msg = Message()
    msg += MessageSegment.markdown(markdown)
    msg += MessageSegment.keyboard(keyboard_model)
    return msg


def build_keyboard_message_by_template(
    template_id: str,
    params: dict[str, list[str]],
    keyboard: KeyboardDef,
) -> Message:
    """使用 Markdown 模版构建带按钮的消息

    Args:
        template_id: Markdown 模版 ID
        params: 模版参数 {key: [values]}
        keyboard: 键盘定义
    """
    from nonebot.adapters.qq.message import Message, MessageSegment
    from nonebot.adapters.qq.models.qq import MessageMarkdown, MessageMarkdownParams

    keyboard_model, _ = _build_qq_models(keyboard)

    markdown_params = [MessageMarkdownParams(key=k, values=v) for k, v in params.items()]
    markdown = MessageMarkdown(
        template_id=int(template_id),
        params=markdown_params,
    )

    msg = Message()
    msg += MessageSegment.markdown(markdown)
    msg += MessageSegment.keyboard(keyboard_model)
    return msg


# ---------------------------------------------------------------------------
# Interaction response helpers
# ---------------------------------------------------------------------------

InteractionCode = Literal[0, 1, 2, 3, 4, 5]


async def respond_interaction(
    bot: QQBot,
    event: InteractionCreateEvent,
    code: InteractionCode = 0,
) -> None:
    """响应按钮交互事件

    Args:
        bot: QQ Bot 实例
        event: 交互事件
        code: 响应码 (0=弹Toast, 1=弹 输入框, 2=更新按钮状态, 3=跳转链接,
              4=loading, 5=跳转小程序)
    """
    await bot.put_interaction(interaction_id=event.id, code=code)


def get_interaction_data(event: InteractionCreateEvent) -> dict[str, str | None]:
    """从交互事件中提取按钮数据

    Returns:
        {
            "button_id": 按钮ID,
            "button_data": 回调数据,
            "user_id": 点击用户ID,
            "message_id": 原消息ID,
        }
    """
    resolved = event.data.resolved
    return {
        "button_id": resolved.button_id,
        "button_data": resolved.button_data,
        "user_id": resolved.user_id,
        "message_id": resolved.message_id,
    }


# ---------------------------------------------------------------------------
# Convenience: send keyboard message directly
# ---------------------------------------------------------------------------

async def send_keyboard_to_group(
    bot: QQBot,
    group_openid: str,
    markdown_content: str,
    keyboard: KeyboardDef,
    *,
    template_id: str | None = None,
    custom_template_id: str | None = None,
) -> None:
    """发送带按钮的消息到群聊

    Args:
        bot: QQ Bot 实例
        group_openid: 群聊 openid
        markdown_content: Markdown 正文
        keyboard: 键盘定义
        template_id: Markdown 模版 ID
        custom_template_id: 自定义模版 ID
    """
    msg = build_keyboard_message(
        markdown_content,
        keyboard,
        template_id=template_id,
        custom_template_id=custom_template_id,
    )
    await bot.send_to_group(group_openid, msg)


async def send_keyboard_to_c2c(
    bot: QQBot,
    openid: str,
    markdown_content: str,
    keyboard: KeyboardDef,
    *,
    template_id: str | None = None,
    custom_template_id: str | None = None,
) -> None:
    """发送带按钮的消息到私聊

    Args:
        bot: QQ Bot 实例
        openid: 用户 openid
        markdown_content: Markdown 正文
        keyboard: 键盘定义
        template_id: Markdown 模版 ID
        custom_template_id: 自定义模版 ID
    """
    msg = build_keyboard_message(
        markdown_content,
        keyboard,
        template_id=template_id,
        custom_template_id=custom_template_id,
    )
    await bot.send_to_c2c(openid, msg)
