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

from typing import TYPE_CHECKING, List, Optional

from nonebot import logger
from nonebot_plugin_alconna import UniMessage
import httpx

from ...config import config
from ...lang import lang
from ..image import get_image_by_id
from ..sticker_manager import get_sticker_manager

if TYPE_CHECKING:
    from ...core.session.base import BaseSession


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
        self.meme_search_base = config.meme_search_base_url.rstrip("/")

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

    async def _search_meme_search(self, query: str, limit: int = 5) -> list[dict]:
        """
        搜索外部 Meme-Search 梗图源

        Args:
            query: 搜索关键词
            limit: 返回结果数量

        Returns:
            格式化后的结果列表，id 取相反数
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.meme_search_base}/api/search",
                    params={"q": query, "page_size": limit},
                    timeout=10.0,
                )
                if response.status_code != 200:
                    logger.warning(f"Meme-Search API returned {response.status_code}")
                    return []
                data = response.json()
                results = []
                for item in data.get("items", []):
                    results.append(
                        {
                            "id": -item["id"],  # 取相反数以区分本地库
                            "title": item.get("title", ""),
                            "description": item.get("description", ""),
                            "tags": item.get("tags", []),
                            "source": "meme-search",
                        }
                    )
                return results
        except httpx.TimeoutException:
            logger.warning("Meme-Search API request timed out")
            return []
        except Exception as e:
            logger.warning(f"Failed to search Meme-Search: {e}")
            return []

    async def _fetch_meme_search_image(self, original_id: int) -> Optional[bytes]:
        """
        从 Meme-Search 下载梗图图片

        Args:
            original_id: 原始非取反的 ID

        Returns:
            图片二进制数据，失败返回 None
        """
        try:
            async with httpx.AsyncClient() as client:
                # 先获取元数据得到文件名
                meta_resp = await client.get(
                    f"{self.meme_search_base}/api/memes/{original_id}",
                    timeout=10.0,
                )
                if meta_resp.status_code != 200:
                    logger.warning(f"Failed to get meme metadata (ID={original_id}): {meta_resp.status_code}")
                    return None
                meta = meta_resp.json()
                filename = meta.get("filename")
                if not filename:
                    logger.warning(f"Meme metadata missing filename (ID={original_id})")
                    return None

                # 下载图片文件
                img_resp = await client.get(
                    f"{self.meme_search_base}/uploads/{filename}",
                    timeout=30.0,
                )
                if img_resp.status_code != 200:
                    logger.warning(f"Failed to download meme image (ID={original_id}): {img_resp.status_code}")
                    return None
                return img_resp.content
        except httpx.TimeoutException:
            logger.warning(f"Meme-Search image download timed out (ID={original_id})")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch Meme-Search image (ID={original_id}): {e}")
            return None

    async def search_sticker(self, query: str) -> str:
        """
        根据描述搜索表情包（含本地收藏和外部梗图源）

        Args:
            query: 搜索查询字符串

        Returns:
            格式化的匹配表情包列表或空消息
        """
        # 搜索本地收藏的表情包
        stickers = await self.manager.search_sticker(query, limit=5)
        if not stickers:
            stickers = await self.manager.search_sticker_any(query, limit=5)

        # 格式化本地结果
        results = []
        for sticker in stickers:
            desc = sticker.description
            results.append(f"- {sticker.id}: {desc}")

        # 同时搜索外部 Meme-Search 梗图源
        meme_search_results = await self._search_meme_search(query, limit=5)
        for item in meme_search_results:
            desc = item["description"]
            tags = " ".join(item["tags"][:3]) if item["tags"] else ""
            tag_suffix = f" [{tags}]" if tags else ""
            results.append(f"- {item['id']}: {desc}{tag_suffix}")

        if not results:
            return await lang.text("sticker.search_empty", self.session.lang_str)

        return await lang.text("sticker.search_result", self.session.lang_str, "\n".join(results))

    async def recommend_sticker(self) -> str:
        """
        推荐表情包
        """
        recommend_str = await lang.text("fetcher.sticker_recommendation", self.session.lang_str)
        async for sticker in self.session.processor.generate_sticker_recommendations():
            recommend_str += f"\n{sticker}"
        return recommend_str

    async def send_sticker(self, sticker_id: int) -> Optional[str]:
        """
        发送表情包到群聊

        Args:
            sticker_id: 要发送的表情包的数据库 ID（外部梗图源使用负数 ID）

        Returns:
            成功或错误消息
        """
        # 负数 ID 表示外部 Meme-Search 梗图源
        if sticker_id < 0:
            original_id = -sticker_id
            image_data = await self._fetch_meme_search_image(original_id)
            if image_data is None:
                return await lang.text("sticker.id_not_found", self.session.lang_str, sticker_id)
            message = UniMessage.image(raw=image_data)
            await message.send(target=self.session.target, bot=self.session.bot)
            self.session.processor.token_bucket.add(0.5)
            return None

        sticker = await self.manager.get_sticker(sticker_id)

        if sticker is None:
            return await lang.text("sticker.id_not_found", self.session.lang_str, sticker_id)

        message = UniMessage.image(raw=sticker.raw)
        await message.send(target=self.session.target, bot=self.session.bot)

        # 发送贴纸增加 token
        self.session.processor.token_bucket.add(0.5)
