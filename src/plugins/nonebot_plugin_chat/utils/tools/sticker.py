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

from typing import TYPE_CHECKING

from nonebot.log import logger
from nonebot_plugin_alconna import UniMessage

from ...lang import lang
from ..image import get_image_by_id
from ..sticker_manager import get_sticker_manager

if TYPE_CHECKING:
    from ...core.session.base import BaseSession

# 每次发送时提交给 Jev 的候选表情包数量
SEND_STICKER_CANDIDATE_LIMIT = 5


class StickerTools:
    """表情包工具类，封装表情包的保存、搜索和发送功能

    仅负责本地收藏的表情包；外部梗图源由 ``MemeTools``（tools/meme.py）单独提供。
    """

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

    async def recommend_sticker(self) -> str:
        """
        推荐表情包
        """
        recommend_str = await lang.text("fetcher.sticker_recommendation", self.session.lang_str)
        async for sticker in self.session.processor.generate_sticker_recommendations():
            recommend_str += f"\n{sticker}"
        return recommend_str

    async def send_sticker(self, query: str) -> str:
        """根据关键词发送表情包

        流程：用关键词在数据库中搜索候选表情包，然后把请求的关键词、
        最近五条消息与 Moonlark 的思考内容提交给 Jev，由它选出最优的
        一张发送；Jev 决定不发送或置信度过低时不发送。

        Args:
            query: 描述要发送的表情包的关键词

        Returns:
            工具执行结果：发送了什么，或为什么不发送
        """
        from ..jev_judge import select_sticker

        # 根据关键词在数据库中搜索候选
        stickers = await self.manager.search_sticker(query, limit=SEND_STICKER_CANDIDATE_LIMIT)
        if not stickers:
            stickers = await self.manager.search_sticker_any(query, limit=SEND_STICKER_CANDIDATE_LIMIT)

        if not stickers:
            return await lang.text("sticker.search_empty", self.session.lang_str)

        selection = await select_sticker(self.session.processor, query, stickers)

        if selection.status == "send" and selection.sticker_id is not None:
            sticker = await self.manager.get_sticker(selection.sticker_id)
            if sticker is not None:
                message = UniMessage.image(raw=sticker.raw)
                await message.send(target=self.session.target, bot=self.session.bot)
                # 发送贴纸增加 token
                self.session.processor.token_bucket.add(0.5)
                return await lang.text(
                    "sticker.sent_detail",
                    self.session.lang_str,
                    selection.description,
                )
            # Jev 选中的表情包在发送前被删除，按不可用处理
            logger.warning(f"Jev 选中的表情包不存在: {selection.sticker_id}")

        if selection.status == "declined":
            return await lang.text("sticker.jev_declined", self.session.lang_str)
        if selection.status == "low_confidence":
            return await lang.text("sticker.low_confidence", self.session.lang_str, f"{selection.confidence:.0%}")
        return await lang.text("sticker.judge_failed", self.session.lang_str)
