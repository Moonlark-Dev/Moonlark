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

"""主动私聊功能模块

每天 8:00 到 23:00，每小时遍历所有私聊会话进行检查。
如果用户满足条件，则主动发起私聊消息。
"""

from datetime import datetime, timedelta
import random
from typing import Optional

from nonebot import logger
from nonebot.adapters import Bot
from nonebot_plugin_alconna import Target
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_orm import get_session
from nonebot_plugin_online_timer import is_user_recently_online
from sqlalchemy import select

from ..lang import lang
from ..models import PrivateChatSession
from .session import create_private_session


# async def get_cooldown_hours(favorability: float) -> float:
#     """根据好感度获取冷却时间（小时）

#     Args:
#         favorability: 用户好感度

#     Returns:
#         冷却时间（小时）
#     """
#     if favorability >= 0.301:
#         return 12.0
#     elif favorability >= 0.151:
#         return 24.0
#     elif favorability >= 0.051:
#         return 36.0
#     else:
#         # 好感度太低，不允许主动私聊
#         return float("inf")


# async def is_in_cooldown(user_id: str, favorability: float) -> bool:
#     """检查用户是否处于主动私聊冷却期

#     Args:
#         user_id: 用户 ID
#         favorability: 当前好感度

#     Returns:
#         如果处于冷却期返回 True，否则返回 False
#     """
#     cooldown_hours = await get_cooldown_hours(favorability)
#     if cooldown_hours == float("inf"):
#         return True

#     async with get_session() as session:
#         # 查询最近一次主动私聊记录
#         result = await session.execute(select(PrivateChatSession).where(PrivateChatSession.user_id == user_id))
#         chat_session = result.scalar_one_or_none()

#         if chat_session is None or chat_session.last_proactive_message_time is None:
#             # 没有发送记录，不在冷却期
#             return False

#         # 检查是否超过冷却时间
#         last_sent_time = datetime.fromtimestamp(chat_session.last_proactive_message_time)
#         cooldown_end = last_sent_time + timedelta(hours=cooldown_hours)
#         return datetime.now() < cooldown_end


async def record_proactive_message(user_id: str) -> None:
    """记录主动私聊消息

    Args:
        user_id: 用户 ID
    """
    async with get_session() as session:
        result = await session.execute(select(PrivateChatSession).where(PrivateChatSession.user_id == user_id))
        chat_session = result.scalar_one_or_none()
        if chat_session:
            chat_session.last_proactive_message_time = datetime.now().timestamp()
            await session.merge(chat_session)
            await session.commit()




async def send_proactive_private_message(bot: Bot, user_id: str, subject: str) -> None:
    """发送主动私聊消息

    Args:
        bot: Bot 实例
        user_id: 用户 ID
    """
    # 创建 Target
    target = Target.user(user_id, adapter=bot.adapter.get_name())

    # 创建或获取 PrivateSession
    session = await create_private_session(user_id, target, bot)

    # 获取提示语
    prompt = await lang.text("proactive_message.prompt", user_id, subject)

    # 发送事件到会话（强制触发回复）
    await session.post_event(prompt, trigger_mode="all")

    # 记录发送历史
    await record_proactive_message(user_id)
