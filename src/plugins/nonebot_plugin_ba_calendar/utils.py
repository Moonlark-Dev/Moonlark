#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
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

import base64
from datetime import datetime
from typing import Any

import httpx

# 服务器配置
SERVER_ID_MAP = {"cn": 16, "in": 17, "jp": 15}
SERVER_NAME_KEY = {"cn": "server_cn", "in": "server_in", "jp": "server_jp"}


async def get_image(uri: str) -> str:
    """获取图片的 base64 编码"""
    async with httpx.AsyncClient() as client:
        req = await client.get(
            f"https:{uri}",
            headers={"Referer": "https://www.gamekee.com/"}
        )
    return f"data:image/png;base64,{base64.b64encode(req.content).decode()}"


async def get_card_pool_data(server_id: int) -> dict:
    """获取卡池数据"""
    async with httpx.AsyncClient() as client:
        req = await client.get(
            f"https://www.gamekee.com/v1/cardPool/query-list?order_by=-1&card_tag_id=&keyword=&kind_id=6&status=0&serverId={server_id}",
            headers={"game-alias": "ba"},
        )
    data = req.json()
    for i in range(len(data["data"])):
        data["data"][i]["icon"] = await get_image(data["data"][i]["icon"])
    return data


async def get_activities(server_id: int, expected_ids: list[int] | None = None) -> list[dict[str, Any]]:
    """获取活动数据"""
    if expected_ids is None:
        expected_ids = []
    async with httpx.AsyncClient() as client:
        req = await client.get(
            f"https://www.gamekee.com/v1/activity/page-list?importance=0&sort=-1&keyword=&limit=999&page_no=1&serverId={server_id}&status=0",
            headers={"game-alias": "ba"},
        )
    data = req.json()
    result = []
    for item in data["data"]:
        if item["id"] not in expected_ids:
            item["picture"] = await get_image(item["picture"])
            result.append(item)
    return result[::-1]


async def get_total_assault_data(server_id: int, fetch_images: bool = True) -> list[dict[str, Any]]:
    """获取总力战数据
    
    Args:
        server_id: 服务器 ID
        fetch_images: 是否获取图片，默认 True
    """
    async with httpx.AsyncClient() as client:
        req = await client.get(
            f"https://www.gamekee.com/v1/activity/page-list?importance=0&sort=-1&keyword&limit=999&page_no=1&serverId={server_id}&status=0&activity_kind_id=15",
            headers={"game-alias": "ba"},
        )
    data = req.json()
    result = []
    timestamp = datetime.now().timestamp()
    for item in data["data"]:
        if item["end_at"] >= timestamp:
            if fetch_images:
                item["picture"] = await get_image(item["picture"])
            result.append(item)
    return result[::-1]