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

"""工具包装器 - 为 WDYM 插件提供 AI 工具调用能力"""

from nonebot_plugin_chat.utils.tools.browser import browse_webpage as _browse_webpage
from nonebot_plugin_chat.utils.tools.search import web_search as _web_search
from nonebot_plugin_chat.utils.tools.bilibili import describe_bilibili_video as _describe_bilibili_video
from nonebot_plugin_chat.utils.tools.bilibili import resolve_b23_url as _resolve_b23_url
from nonebot_plugin_chat.utils.tools.wolfram_alpha import request_wolfram_alpha
from nonebot_plugin_chat.utils.tools.abbreviation import search_abbreviation as _search_abbreviation
from nonebot_plugin_chat.utils.image import query_image_content as _query_image_content
from nonebot_plugin_openai.utils.functions import create_function_list
from nonebot_plugin_larklang import LangHelper


class WdymTools:
    """WDYM 插件工具管理器，包装 chat 插件的工具函数，提供 AI 可调用的接口"""

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id
        # 工具调用的 i18n key 都在 chat 插件中，直接复用其 LangHelper
        # 工具调用的 i18n key 在 chat.yaml 中，plugin 名为 "chat"
        self._chat_lang = LangHelper("chat")

    async def _get_text(self, key: str, *args, **kwargs) -> str:
        """获取本地化文本，从 chat 插件的 i18n 中查找工具相关 key"""
        return await self._chat_lang.text(key, self._user_id, *args, **kwargs)

    async def browse_webpage(self, url: str) -> str:
        """使用浏览器访问指定 URL 并获取网页内容"""
        return await _browse_webpage(url, self._get_text)

    async def web_search(self, keyword: str) -> str:
        """调用搜索引擎，从网络中搜索信息"""
        return await _web_search(keyword, self._get_text)

    async def describe_bilibili_video(self, bv_id: str) -> str:
        """根据 Bilibili 视频的 BV 号，下载视频并进行内容总结"""
        return await _describe_bilibili_video(bv_id, self._get_text)

    async def resolve_b23_url(self, b23_url: str) -> str:
        """解析 b23.tv 短链并返回 BV 号"""
        return await _resolve_b23_url(b23_url, self._get_text)

    async def search_abbreviation(self, text_arg: str) -> str:
        """查询英文字母缩写的含义"""
        return await _search_abbreviation(text_arg, self._get_text)

    async def query_image(self, image_id: str, query_prompt: str) -> str:
        """对聊天中已出现的某张图片进行针对性的内容查询"""
        return await _query_image_content(image_id, query_prompt, self._user_id)

    async def get_tools(self) -> list:
        """获取工具列表，用于 AI 函数调用"""
        tools = [
            self.browse_webpage,
            self.web_search,
            request_wolfram_alpha,
            self.search_abbreviation,
            self.describe_bilibili_video,
            self.resolve_b23_url,
            self.query_image,
        ]
        return await create_function_list(tools)