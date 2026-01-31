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

from datetime import date
from typing import cast, Optional

from nonebot.internal.adapter import Message
from nonebot_plugin_orm import get_session, async_scoped_session, get_scoped_session
from sqlalchemy import select

from nonebot_plugin_everyday_wife.models import WifeData


async def divorce(group_id: str, session: async_scoped_session, platform_user_id: str) -> None:
    """
    解除用户当天的匹配关系
    
    此函数会同时删除用户及其配偶的匹配记录，使双方都能重新进行匹配。
    只影响当天的匹配记录。
    
    Args:
        group_id: 群组 ID
        session: 数据库会话
        platform_user_id: 用户的平台 ID
    """
    today = date.today()
    
    # 查找用户当天的匹配记录
    query = cast(
        Optional[WifeData],
        await session.scalar(
            select(WifeData).where(
                WifeData.user_id == platform_user_id, 
                WifeData.group_id == group_id,
                WifeData.generate_date == today
            )
        ),
    )
    
    if query:
        # 查找配偶当天的匹配记录（双向删除）
        result = await session.scalar(
            select(WifeData).where(
                WifeData.user_id == query.wife_id, 
                WifeData.group_id == group_id,
                WifeData.generate_date == today
            )
        )
        if result:
            await session.delete(result)
        await session.delete(query)
    
    await session.commit()


async def marry(couple: tuple[str, str], group_id: str) -> None:
    """
    为两个用户创建匹配关系
    
    此函数会先解除双方当天的现有匹配关系（如果有），然后创建新的双向匹配记录。
    
    Args:
        couple: 包含两个用户 ID 的元组
        group_id: 群组 ID
    """
    today = date.today()
    session = get_scoped_session()
    
    # 先解除双方现有的匹配关系
    for user in couple:
        await divorce(group_id, session, user)
    await session.close()
    
    # 创建新的双向匹配记录
    async with get_session() as session:
        session.add(
            WifeData(group_id=group_id, user_id=couple[0], wife_id=couple[1], generate_date=today, queried=False)
        )
        session.add(
            WifeData(group_id=group_id, user_id=couple[1], wife_id=couple[0], generate_date=today, queried=False)
        )
        await session.commit()


def get_at_argument(message: Message) -> Optional[str]:
    """从消息中提取 @ 的目标用户 ID"""
    for seg in message:
        if seg.type == "at":
            return seg.data["user_id"]
    return None
