#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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
礼物系统的 Session 处理模块

此模块提供处理礼物赠送时获取或创建 Chat Session 的功能。
作为 items 插件和 chat 插件之间的桥梁。
"""

from typing import Any, TYPE_CHECKING
from nonebot import logger

if TYPE_CHECKING:
    from nonebot_plugin_chat.core.session.base import BaseSession


async def get_or_create_session(
    session_id: str, bot: Any, event: Any
) -> "BaseSession | None":
    """
    获取或创建 Chat Session

    如果 session 已存在则返回，否则根据群聊/私聊场景创建新 session。

    Args:
        session_id: 会话 ID
        bot: Bot 实例
        event: Event 实例

    Returns:
        BaseSession 或 None（如果创建失败）
    """
    try:
        from nonebot_plugin_chat.core.session import (
            get_session_directly,
            get_group_session_forced,
            get_private_session,
        )
        from nonebot_plugin_alconna import Target

        # 尝试获取已存在的 session
        try:
            return get_session_directly(session_id)
        except KeyError:
            pass

        # Session 不存在，需要创建
        target = Target(event)
        if hasattr(event, "group_id") and event.group_id:
            # 群聊场景
            return await get_group_session_forced(session_id, target, bot)
        else:
            # 私聊场景
            return await get_private_session(session_id, target, bot)

    except Exception as e:
        logger.warning(f"获取或创建 session 失败: {e}")
        return None


async def trigger_gift_event(
    session: "BaseSession", user_id: str, gift_prompt: str
) -> bool:
    """
    触发礼物事件

    Args:
        session: Chat Session
        user_id: 用户 ID
        gift_prompt: 礼物事件描述文本

    Returns:
        是否成功触发
    """
    try:
        await session.add_event(gift_prompt, trigger_mode="all")
        return True
    except Exception as e:
        logger.warning(f"触发礼物事件失败: {e}")
        return False
