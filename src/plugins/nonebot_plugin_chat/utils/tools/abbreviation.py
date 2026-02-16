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
from nonebot.log import logger
from nonebot_plugin_chat.types import GetTextFunc


async def search_abbreviation(text: str, get_text: GetTextFunc) -> str:
    """
    查询英文字母缩写的含义（能不能好好说话）

    Args:
        text: 要查询的缩写文本

    Returns:
        格式化的可能含义列表
    """
    url = "https://lab.magiconch.com/api/nbnhhsh/guess"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json={"text": text})
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    result = data[0]
                    trans = result.get("trans", [])
                    if trans:
                        meanings = "\n".join([f"- {meaning}" for meaning in trans])
                        return await get_text("abbreviation.success", meanings)
                return await get_text("abbreviation.not_found")
            else:
                return await get_text("abbreviation.failed", response.status_code)
    except Exception as e:
        logger.exception(e)
        return await get_text("abbreviation.error", str(e))
