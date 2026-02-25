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

from typing import TYPE_CHECKING, Optional

from nonebot_plugin_larkuser import get_user
from nonebot import logger

if TYPE_CHECKING:
    from nonebot_plugin_items.base.stack import ItemStack
    from nonebot_plugin_items.base.gift import GiftItem
    from ..core.session.base import BaseSession


class GiftManager:
    """
    礼物管理器

    处理礼物赠送流程：
    1. 增加用户好感度
    2. 触发 AI 回复事件
    """

    _instance: Optional["GiftManager"] = None

    def __new__(cls) -> "GiftManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

    async def handle_gift(
        self,
        stack: "ItemStack",
        session: "BaseSession",
    ) -> None:
        """
        处理礼物赠送

        Args:
            stack: 礼物物品堆叠
            session: 当前聊天会话
        """
        from nonebot_plugin_items.base.gift import GiftItem

        item = stack.item

        # 确保是 GiftItem 类型
        if not isinstance(item, GiftItem):
            logger.warning(f"尝试处理非礼物物品: {item}")
            return

        # 获取用户信息
        user_id = stack.user_id
        user = await get_user(user_id)

        # 增加好感度
        fav_value = item.fav_value * stack.count
        await user.add_fav(fav_value)
        logger.info(f"用户 {user_id} 赠送礼物 {item.getLocation()}, 好感度 +{fav_value}")

        # 获取用户昵称
        nickname = await self._get_user_nickname(session, user_id)

        # 生成礼物事件提示
        gift_prompt = await item.getGiftPrompt(stack, nickname)

        # 触发 AI 回复事件
        # 使用 "all" 模式确保 AI 会回复
        await session.add_event(
            gift_prompt,
            trigger_mode="all"
        )

    async def _get_user_nickname(self, session: "BaseSession", user_id: str) -> str:
        """
        获取用户昵称

        Args:
            session: 当前聊天会话
            user_id: 用户 ID

        Returns:
            用户昵称，如果找不到则返回 "某人"
        """
        try:
            # 尝试从 session 的用户列表中获取昵称
            users = await session.get_users()
            for nickname, uid in users.items():
                if uid == user_id:
                    return nickname
        except Exception as e:
            logger.debug(f"从 session 获取用户昵称失败: {e}")

        return "某人"


def get_gift_manager() -> GiftManager:
    """获取 GiftManager 单例实例"""
    return GiftManager()
