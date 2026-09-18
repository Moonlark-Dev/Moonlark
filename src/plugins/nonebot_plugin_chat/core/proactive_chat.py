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


def get_proactive_target_user_id(chat_session: PrivateChatSession, adapter_name: str) -> str:
    """获取主动私聊应发送到的适配器用户 ID

    `PrivateChatSession.user_id` 是 Moonlark 主账号 ID：QQ 官方适配器的私聊会被
    自动绑定（见 nonebot_plugin_auto_bind）映射为 QQ 号，但 QQ 官方适配器发送 C2C
    消息需要的是 openid。因此当记录中的适配器与当前 bot 一致时，优先使用记录里保存
    的适配器原始 user_id；旧记录（无该字段）回退到 user_id。

    Args:
        chat_session: 私聊会话记录
        adapter_name: 当前 bot 的适配器名称

    Returns:
        用于构造 Target 的用户 ID
    """
    if chat_session.platform_user_id and chat_session.adapter_name == adapter_name:
        return chat_session.platform_user_id
    return chat_session.user_id


async def send_proactive_private_message(bot: Bot, user_id: str, subject: str) -> None:
    """发送主动私聊消息

    Args:
        bot: Bot 实例
        user_id: 用户 ID
    """
    # 从数据库获取 session_key
    async with get_session() as db_session:
        result = await db_session.execute(select(PrivateChatSession).where(PrivateChatSession.user_id == user_id))
        chat_session = result.scalar_one_or_none()
    if not chat_session or not chat_session.session_key:
        logger.warning(f"用户 {user_id} 无私聊会话记录，无法发送主动消息")
        return

    # 创建 Target（adapter_name 用于消息发送）
    adapter_name = bot.adapter.get_name()
    if chat_session.adapter_name and chat_session.adapter_name != adapter_name:
        logger.warning(
            f"用户 {user_id} 的私聊记录适配器为 {chat_session.adapter_name}，"
            f"与 bot {chat_session.bot_id} 的实际适配器 {adapter_name} 不一致，"
            "将回退到 Moonlark 主账号 ID 发送",
        )
    target = Target.user(get_proactive_target_user_id(chat_session, adapter_name), adapter=adapter_name)

    # 创建或获取 PrivateSession
    session = await create_private_session(chat_session.session_key, target, bot)

    # 获取提示语
    prompt = await lang.text("proactive_message.prompt", user_id, subject)

    # 发送事件到会话（强制触发回复）
    await session.post_event(prompt, trigger_mode="all")

    # 记录发送历史
    await record_proactive_message(user_id)
