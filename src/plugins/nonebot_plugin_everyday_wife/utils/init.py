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


async def init_group(members: list[str], group_id: str) -> None:
    moonlark_bot_ids = get_moonlark_bot_ids()
    unmatched_members = []
    # 记录不满足好感度要求的用户（不能与 Moonlark 匹配）
    low_fav_members = []
    today = date.today()
    async with get_session() as session:
        for member in members:
            user_id = str(member)
            result = cast(
                Optional[WifeData],
                await session.scalar(
                    select(WifeData).where(WifeData.group_id == group_id, WifeData.user_id == user_id)
                ),
            )
            if result is None or result.generate_date != today:
                # 检查是否为 Moonlark 机器人
                if user_id in moonlark_bot_ids:
                    unmatched_members.append(user_id)
                elif await can_match_moonlark(user_id):
                    unmatched_members.append(user_id)
                else:
                    low_fav_members.append(user_id)
    
    # 首先处理可以匹配 Moonlark 的用户
    c = len(unmatched_members) // 2
    for i in range(c):
        couple = (
            unmatched_members.pop(random.randint(0, len(unmatched_members) - 1)),
            unmatched_members.pop(random.randint(0, len(unmatched_members) - 1)),
        )
        await marry(couple, group_id)
    
    # 然后处理好感度不足的用户（他们之间可以互相匹配）
    # 将剩余的 unmatched_members（可能包含 Moonlark）中的非 Moonlark 用户也加入
    remaining_non_moonlark = [m for m in unmatched_members if m not in moonlark_bot_ids]
    low_fav_members.extend(remaining_non_moonlark)
    
    c = len(low_fav_members) // 2
    for i in range(c):
        couple = (
            low_fav_members.pop(random.randint(0, len(low_fav_members) - 1)),
            low_fav_members.pop(random.randint(0, len(low_fav_members) - 1)),
        )
        await marry(couple, group_id)


async def init_onebot_v11_group(bot: OneBotV11Bot, group_id: str) -> None:
    members = await bot.get_group_member_list(group_id=int(group_id))
    await init_group([user["user_id"] for user in members], group_id)


async def init_onebot_v12_group(bot: OneBotV12Bot, group_id: str) -> None:
    members = await bot.get_group_member_list(group_id=group_id)
    await init_group([user["user_id"] for user in members], group_id)


async def init_qq_group(bot: QQBot, group_id: str) -> None:
    members = await bot.post_group_members(group_id=group_id)
    await init_group([user.member_openid for user in members.members], group_id)
