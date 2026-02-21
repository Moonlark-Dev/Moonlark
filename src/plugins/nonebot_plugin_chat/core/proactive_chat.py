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
from ..models import PrivateChatSession, ProactiveMessageRecord
from .session import create_private_session


async def get_cooldown_hours(favorability: float) -> float:
    """根据好感度获取冷却时间（小时）

    Args:
        favorability: 用户好感度

    Returns:
        冷却时间（小时）
    """
    if favorability >= 0.301:
        return 12.0
    elif favorability >= 0.151:
        return 24.0
    elif favorability >= 0.051:
        return 36.0
    else:
        # 好感度太低，不允许主动私聊
        return float("inf")


async def is_in_cooldown(user_id: str, favorability: float) -> bool:
    """检查用户是否处于主动私聊冷却期

    Args:
        user_id: 用户 ID
        favorability: 当前好感度

    Returns:
        如果处于冷却期返回 True，否则返回 False
    """
    cooldown_hours = await get_cooldown_hours(favorability)
    if cooldown_hours == float("inf"):
        return True

    async with get_session() as session:
        # 查询最近一次主动私聊记录
        result = await session.execute(
            select(ProactiveMessageRecord)
            .where(ProactiveMessageRecord.user_id == user_id)
            .order_by(ProactiveMessageRecord.sent_time.desc())
            .limit(1)
        )
        last_record = result.scalar_one_or_none()

        if last_record is None:
            # 没有发送记录，不在冷却期
            return False

        # 检查是否超过冷却时间
        last_sent_time = datetime.fromtimestamp(last_record.sent_time)
        cooldown_end = last_sent_time + timedelta(hours=cooldown_hours)
        return datetime.now() < cooldown_end


async def record_proactive_message(user_id: str) -> None:
    """记录主动私聊消息

    Args:
        user_id: 用户 ID
    """
    async with get_session() as session:
        record = ProactiveMessageRecord(
            user_id=user_id,
            sent_time=datetime.now().timestamp(),
        )
        session.add(record)
        await session.commit()


async def get_recent_private_chat_sessions(days: int = 3) -> list[tuple[str, str]]:
    """获取近 N 天内有过私聊的会话列表

    Args:
        days: 天数，默认 3 天

    Returns:
        (user_id, bot_id) 元组列表
    """
    cutoff_time = datetime.now() - timedelta(days=days)
    cutoff_timestamp = cutoff_time.timestamp()

    async with get_session() as session:
        # 从 PrivateChatSession 查询所有近 N 天内有消息的私聊会话
        result = await session.execute(
            select(PrivateChatSession).where(PrivateChatSession.last_message_time >= cutoff_timestamp)
        )
        chat_sessions = result.scalars().all()

        return [(cs.user_id, cs.bot_id) for cs in chat_sessions]


async def check_and_send_proactive_messages() -> None:
    """检查并发送主动私聊消息

    每小时执行一次，检查所有私聊会话：
    1. 近 3 天用户有主动私聊
    2. 用户在近 30 分钟内上过线
    3. 通过好感度检查主动私聊不在冷却期间
    """
    logger.info("开始检查主动私聊...")

    # 获取近 3 天有过私聊的会话（包含 user_id 和 bot_id）
    recent_sessions = await get_recent_private_chat_sessions(days=3)
    logger.debug(f"近 3 天有过私聊的用户: {len(recent_sessions)} 人")

    for user_id, bot_id in recent_sessions:
        try:
            # 获取该用户对应的 Bot 实例
            from nonebot import get_bot

            try:
                bot = get_bot(bot_id)
            except Exception as e:
                logger.warning(f"无法获取 Bot 实例 {bot_id}: {e}")
                continue

            # 检查 30 分钟内是否在线
            if not await is_user_recently_online(user_id, minutes=30):
                logger.debug(f"用户 {user_id} 30 分钟内不在线，跳过")
                continue

            # 获取用户好感度
            user = await get_user(user_id)
            favorability = user.get_fav()

            # 检查冷却期
            if await is_in_cooldown(user_id, favorability):
                logger.debug(f"用户 {user_id} 处于冷却期，跳过")
                continue

            if random.random() >= 0.3:
                logger.debug(f"用户 {user_id} 概率检测未通过，跳过")
                continue

            # 检查通过，发送主动私聊
            await send_proactive_private_message(bot, user_id)
            logger.info(f"已向用户 {user_id} 发送主动私聊")

        except Exception as e:
            logger.exception(f"处理用户 {user_id} 时出错: {e}")
            continue


async def send_proactive_private_message(bot: Bot, user_id: str) -> None:
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
    prompt = await lang.text("proactive_message.prompt", user_id)

    # 发送事件到会话（强制触发回复）
    await session.post_event(prompt, trigger_mode="all")

    # 记录发送历史
    await record_proactive_message(user_id)


@scheduler.scheduled_job("cron", hour="8-23", minute=0, id="proactive_private_chat")
async def _scheduled_proactive_chat() -> None:
    """定时任务：每天 8:00-23:00 每小时执行一次"""
    await check_and_send_proactive_messages()
