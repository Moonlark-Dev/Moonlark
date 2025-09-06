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
from httpx import AsyncClient

from ..image import request_describe_image




async def describe_image(image_url: str) -> str:
    async with AsyncClient() as client:
        response = await client.get(image_url)
    if response.is_success:
        image_bytes = response.read()
        return await request_describe_image(image_bytes, "mlsid::--lang=zh-hans")
    return f"获取信息失败 (HTTP {response.status_code})"
