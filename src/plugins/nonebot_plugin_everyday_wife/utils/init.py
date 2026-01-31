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

import random
from datetime import date
from typing import cast, Optional

from nonebot.adapters.onebot.v11 import Bot as OneBotV11Bot
from nonebot.adapters.onebot.v12 import Bot as OneBotV12Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from nonebot_plugin_everyday_wife.models import WifeData
from nonebot_plugin_everyday_wife.utils.control import marry
from nonebot_plugin_bots.config import config as bots_config
from nonebot_plugin_larkuser import get_user

# 匹配 Moonlark 所需的最低好感度
MOONLARK_MATCH_FAV_THRESHOLD = 0.150


def get_moonlark_bot_ids() -> set[str]:
    """获取所有 Moonlark 机器人的 user_id"""
    return set(bots_config.bots_list.values())


async def can_match_moonlark(user_id: str) -> bool:
    """检查用户是否有足够的好感度来匹配 Moonlark"""
    user = await get_user(user_id)
    return user.get_fav() > MOONLARK_MATCH_FAV_THRESHOLD


async def get_available_members(group_id: str, members: list[str], exclude_user: Optional[str] = None) -> list[str]:
    """
    获取当天可用于匹配的群成员列表（尚未被匹配的成员）
    
    Args:
        group_id: 群组 ID
        members: 所有群成员列表
        exclude_user: 需要排除的用户（通常是调用者自己）
    
    Returns:
        可用于匹配的成员列表
    """
    available_members = []
    today = date.today()
    
    async with get_session() as session:
        for member in members:
            user_id = str(member)
            
            # 排除指定用户
            if exclude_user and user_id == exclude_user:
                continue
            
            # 检查该成员今天是否已被匹配
            result = cast(
                Optional[WifeData],
                await session.scalar(
                    select(WifeData).where(
                        WifeData.group_id == group_id,
                        WifeData.user_id == user_id,
                        WifeData.generate_date == today
                    )
                ),
            )
            if result is None:
                available_members.append(user_id)
    
    return available_members


async def pre_match_moonlark(group_id: str, members: list[str]) -> None:
    """
    为群内的 Moonlark 机器人进行预匹配
    
    从可用的好感度足够的用户中随机选择一个与每个未匹配的 Moonlark 进行匹配。
    这个函数应该在每次用户请求匹配前调用，以确保 Moonlark 优先被好感度足够的用户匹配。
    
    Args:
        group_id: 群组 ID
        members: 所有群成员列表
    """
    moonlark_bot_ids = get_moonlark_bot_ids()
    
    # 获取群内所有可用的 Moonlark 机器人
    available_moonlarks = []
    for bot_id in moonlark_bot_ids:
        if bot_id in members:
            # 检查该 Moonlark 是否已被匹配
            available = await get_available_members(group_id, [bot_id])
            if available:
                available_moonlarks.append(bot_id)
    
    if not available_moonlarks:
        return
    
    # 获取可用于匹配 Moonlark 的成员（好感度足够且未被匹配）
    all_available = await get_available_members(group_id, members)
    
    # 筛选出好感度足够的非 Moonlark 用户
    eligible_users = []
    for user_id in all_available:
        if user_id in moonlark_bot_ids:
            continue
        if await can_match_moonlark(user_id):
            eligible_users.append(user_id)
    
    # 为每个未匹配的 Moonlark 分配一个好感度足够的用户
    for moonlark_id in available_moonlarks:
        if not eligible_users:
            break
        
        # 随机选择一个用户与 Moonlark 匹配
        selected_user = random.choice(eligible_users)
        eligible_users.remove(selected_user)
        
        await marry((moonlark_id, selected_user), group_id)


async def match_user_with_available(
    caller_id: str, 
    group_id: str, 
    members: list[str]
) -> Optional[str]:
    """
    为调用者从可用成员中匹配一个对象
    
    匹配逻辑：
    1. 首先进行 Moonlark 预匹配（确保好感度足够的用户有机会匹配 Moonlark）
    2. 然后从剩余可用成员中随机选择一个与调用者匹配
    
    Args:
        caller_id: 调用者的 platform_user_id
        group_id: 群组 ID
        members: 所有群成员列表
    
    Returns:
        匹配到的成员 ID，如果无可用成员则返回 None
    """
    # 先进行 Moonlark 预匹配
    await pre_match_moonlark(group_id, members)
    
    # 获取可用成员（排除调用者自己）
    available = await get_available_members(group_id, members, exclude_user=caller_id)
    
    if not available:
        return None
    
    # 随机选择一个成员进行匹配
    selected = random.choice(available)
    
    # 执行匹配
    await marry((caller_id, selected), group_id)
    
    return selected


async def get_members_onebot_v11(bot: OneBotV11Bot, group_id: str) -> list[str]:
    """获取 OneBotV11 群成员列表"""
    members = await bot.get_group_member_list(group_id=int(group_id))
    return [str(user["user_id"]) for user in members]


async def get_members_onebot_v12(bot: OneBotV12Bot, group_id: str) -> list[str]:
    """获取 OneBotV12 群成员列表"""
    members = await bot.get_group_member_list(group_id=group_id)
    return [str(user["user_id"]) for user in members]


async def get_members_qq(bot: QQBot, group_id: str) -> list[str]:
    """获取 QQ 群成员列表"""
    members = await bot.post_group_members(group_id=group_id)
    return [user.member_openid for user in members.members]
