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
from nonebot_plugin_chat.types import GetTextFunc
from .browser import browse_webpage


async def search_on_bing(keyword: str, get_text: GetTextFunc) -> str:
    q = quote(keyword)
    result = await browse_webpage(f"https://www.bing.com/search?q={q}", get_text)
    return result


async def web_search(keyword: str, get_text: GetTextFunc) -> str:
    """使用 Metaso API 进行搜索"""
    api_key = config.metaso_api_key

    if not api_key:
        return await get_text("web_search.metaso_unavailable", await search_on_bing(keyword, get_text))

    url = "https://metaso.cn/api/v1/search"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json", "Content-Type": "application/json"}
    payload = {
        "q": keyword,
        "scope": "webpage",
        "includeSummary": False,
        "size": 10,
        "includeRawContent": False,
        "conciseSnippet": False,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                results = []

                if "webpages" in data and data["webpages"]:
                    for item in data["webpages"]:
                        title = item.get("title", "")
                        link = item.get("link", "")
                        snippet = item.get("snippet", "")
                        results.append(await get_text("web_search.result_item", title, snippet, link))

                return "\n".join(results) if results else await get_text("web_search.no_result")
            else:
                return await get_text("web_search.failed", response.status_code)
    except Exception as e:
        return await get_text("web_search.error", str(e))
