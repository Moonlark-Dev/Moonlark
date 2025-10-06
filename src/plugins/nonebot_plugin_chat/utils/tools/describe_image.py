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
from httpx import AsyncClient, UnsupportedProtocol

from ..image import request_describe_image


async def _describe_image(image_url: str) -> str:
    async with AsyncClient() as client:
        response = await client.get(image_url)
    if response.is_success:
        image_bytes = response.read()
        return await request_describe_image(image_bytes, "mlsid::--lang=zh-hans")
    return f"获取信息失败 (HTTP {response.status_code})"


async def describe_image(image_url: str) -> str:
    try:
        return await _describe_image(image_url)
    except UnsupportedProtocol:
        if image_url.startswith("来源/梗") or image_url.startswith("[图片"):
            return (
                f"传入的 `image_url` 不是合法的 URL，这是从消息中的 `[图片: {image_url}]` 或类似的块中提取出来的文本吗？"
                f"如果是，请不要再向将这样的内容作为图片 URL 传入，`describe_image` 工具， **`{image_url}` 就是它的描述！**"
            )
        return "传入的 `image_url` 不是合法的 URL， **请在使用该工具前检查需要解释的图片 URL 到底是不是完整的URL、有没有指向一个网络图片！**"
