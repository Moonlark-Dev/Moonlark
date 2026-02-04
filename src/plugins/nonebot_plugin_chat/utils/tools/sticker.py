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

from typing import TYPE_CHECKING, List

from nonebot_plugin_alconna import UniMessage

from ...lang import lang
from ..image import get_image_by_id
from ..sticker_manager import get_sticker_manager

if TYPE_CHECKING:
    from ...matcher.group import BaseSession


class StickerTools:
    """表情包工具类，封装表情包的保存、搜索和发送功能"""

    def __init__(self, session: "BaseSession") -> None:
        """
        初始化表情包工具

        Args:
            session: 群聊会话对象
        """
        self.session = session
        self.manager = get_sticker_manager()

    async def save_sticker(self, image_id: str) -> str:
        """
        将图片保存为表情包

        Args:
            image_id: 消息上下文中的临时图片 ID

        Returns:
            成功或错误消息
        """
        from ..sticker_manager import DuplicateStickerError, NotMemeError

        # 从缓存获取图片数据
        image_data = await get_image_by_id(image_id)

        if image_data is None:
            return await lang.text("sticker.not_found", self.session.lang_str)

        # 保存表情包
        try:
            sticker = await self.manager.save_sticker(
                description=image_data["description"],
                raw=image_data["raw"],
                group_id=self.session.session_id,
            )
            return await lang.text("sticker.saved", self.session.lang_str, sticker.id)
        except DuplicateStickerError as e:
            return await lang.text("sticker.duplicate", self.session.lang_str, e.existing_sticker.id, e.similarity)
        except NotMemeError:
            return await lang.text("sticker.not_meme", self.session.lang_str)

    async def search_sticker(self, query: str) -> str:
        """
        根据描述搜索表情包

        Args:
            query: 搜索查询字符串

        Returns:
            格式化的匹配表情包列表或空消息
        """
        # 首先尝试 AND 匹配（所有关键词都必须匹配）
        stickers = await self.manager.search_sticker(query, limit=5)

        # 如果没有结果，尝试 OR 匹配（任一关键词匹配）
        if not stickers:
            stickers = await self.manager.search_sticker_any(query, limit=5)

        if not stickers:
            return await lang.text("sticker.search_empty", self.session.lang_str)

        # 格式化结果
        results = []
        for sticker in stickers:
            desc = sticker.description
            results.append(f"- {sticker.id}: {desc}")

        return await lang.text("sticker.search_result", self.session.lang_str, "\n".join(results))

    async def send_sticker(self, sticker_id: int) -> str:
        """
        发送表情包到群聊

        Args:
            sticker_id: 要发送的表情包的数据库 ID

        Returns:
            成功或错误消息
        """
        sticker = await self.manager.get_sticker(sticker_id)

        if sticker is None:
            return await lang.text("sticker.id_not_found", self.session.lang_str, sticker_id)

        try:
            # 创建并发送图片消息
            message = UniMessage.image(raw=sticker.raw)
            await message.send(target=self.session.target, bot=self.session.bot)
            return await lang.text("sticker.sent", self.session.lang_str)
        except Exception as e:
            return await lang.text("sticker.send_failed", self.session.lang_str, str(e))
