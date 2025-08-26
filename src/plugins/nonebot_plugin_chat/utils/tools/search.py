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

import httpx
from urllib.parse import quote
from ...config import config
from .browser import browse_webpage


async def search_on_bing(keyword: str) -> str:
    q = quote(keyword)
    result = await browse_webpage(f"https://www.bing.com/search?q={q}")
    return result["content"]


async def search_on_google(keyword: str) -> str:
    """使用Google PSE API进行搜索"""
    api_key = config.google_api_key
    search_engine_id = config.google_search_engine_id

    if not api_key or not search_engine_id:
        return "Google 搜索暂不可用，以下是使用 Bing 搜索得到的结果：\n\n" + await search_on_bing(keyword)

    q = quote(keyword)
    url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={search_engine_id}&q={q}&num=6"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                results = []

                if "items" in data:
                    for item in data["items"]:
                        title = item.get("title", "")
                        link = item.get("link", "")
                        snippet = item.get("snippet", "")
                        results.append(f"**{title}**\n{snippet}\n链接: {link}\n")

                return "\n".join(results) if results else "未找到相关搜索结果"
            else:
                return f"搜索请求失败，状态码: {response.status_code}"
    except Exception as e:
        return f"搜索过程中发生错误: {str(e)}"
