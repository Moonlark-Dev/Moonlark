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

"""外部梗图源（Meme-Search）工具模块

把梗图检索从表情包收藏体系中拆出来，自成一组工具：
- ``search_meme``：仅检索外部梗图源，返回梗图自身的正整数 ID；
- ``send_meme``：按该 ID 下载并发送梗图。

与 ``tools/sticker.py`` 的区别：这里不使用「负数 ID 表示外部图源」的约定，
ID 始终是 Meme-Search 中的原生正整数，两个工具的 ID 空间互不干扰。
"""

from typing import TYPE_CHECKING, Optional, TypedDict

import httpx
from nonebot import logger
from nonebot_plugin_alconna import UniMessage

from ...config import config
from ...lang import lang

if TYPE_CHECKING:
    from ...core.session.base import BaseSession

SEARCH_TIMEOUT = 10.0
METADATA_TIMEOUT = 10.0
IMAGE_TIMEOUT = 30.0
DEFAULT_LIMIT = 5


class MemeSearchResult(TypedDict):
    """外部梗图源的检索结果"""

    id: int
    title: str
    description: str
    tags: list[str]
    source: str


class MemeTools:
    """梗图工具类，封装外部 Meme-Search 梗图源的检索与发送"""

    def __init__(self, session: "BaseSession") -> None:
        """
        初始化梗图工具

        Args:
            session: 会话对象
        """
        self.session = session
        self.base_url = config.meme_search_base_url.rstrip("/")

    async def search_meme(self, query: str, limit: int = DEFAULT_LIMIT) -> str:
        """
        在外部梗图源中检索梗图

        Args:
            query: 搜索关键词
            limit: 返回结果数量

        Returns:
            格式化的梗图列表或空消息
        """
        results = await self._search(query, limit=limit)

        if not results:
            return await lang.text("sticker.search_empty", self.session.lang_str)

        lines = []
        for item in results:
            tags = " ".join(item["tags"][:3]) if item["tags"] else ""
            tag_suffix = f" [{tags}]" if tags else ""
            lines.append(f"- {item['id']}: {item['description']}{tag_suffix}")

        return await lang.text("sticker.search_result", self.session.lang_str, "\n".join(lines))

    async def send_meme(self, meme_id: int) -> Optional[str]:
        """
        发送指定梗图到当前会话

        Args:
            meme_id: Meme-Search 中的梗图 ID（正整数）

        Returns:
            成功返回 None，失败返回错误消息
        """
        image_data = await self._fetch_image(meme_id)
        if image_data is None:
            return await lang.text("sticker.id_not_found", self.session.lang_str, meme_id)

        message = UniMessage.image(raw=image_data)
        await message.send(target=self.session.target, bot=self.session.bot)

        # 发送梗图增加 token
        self.session.processor.token_bucket.add(0.5)
        return None

    async def _search(self, query: str, limit: int = DEFAULT_LIMIT) -> list[MemeSearchResult]:
        """
        请求 Meme-Search 检索接口

        Args:
            query: 搜索关键词
            limit: 返回结果数量

        Returns:
            检索结果列表，失败时返回空列表
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/search",
                    params={"q": query, "page_size": limit},
                    timeout=SEARCH_TIMEOUT,
                )
                if response.status_code != 200:
                    logger.warning(f"Meme-Search API returned {response.status_code}")
                    return []
                data = response.json()
                results: list[MemeSearchResult] = []
                for item in data.get("items", []):
                    results.append(
                        {
                            "id": int(item["id"]),
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

    async def _fetch_image(self, meme_id: int) -> Optional[bytes]:
        """
        从 Meme-Search 下载梗图图片

        Args:
            meme_id: 梗图 ID

        Returns:
            图片二进制数据，失败返回 None
        """
        try:
            async with httpx.AsyncClient() as client:
                # 先获取元数据得到文件名
                meta_resp = await client.get(
                    f"{self.base_url}/api/memes/{meme_id}",
                    timeout=METADATA_TIMEOUT,
                )
                if meta_resp.status_code != 200:
                    logger.warning(f"Failed to get meme metadata (ID={meme_id}): {meta_resp.status_code}")
                    return None
                meta = meta_resp.json()
                filename = meta.get("filename")
                if not filename:
                    logger.warning(f"Meme metadata missing filename (ID={meme_id})")
                    return None

                # 下载图片文件
                img_resp = await client.get(
                    f"{self.base_url}/uploads/{filename}",
                    timeout=IMAGE_TIMEOUT,
                )
                if img_resp.status_code != 200:
                    logger.warning(f"Failed to download meme image (ID={meme_id}): {img_resp.status_code}")
                    return None
                return img_resp.content
        except httpx.TimeoutException:
            logger.warning(f"Meme-Search image download timed out (ID={meme_id})")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch Meme-Search image (ID={meme_id}): {e}")
            return None
