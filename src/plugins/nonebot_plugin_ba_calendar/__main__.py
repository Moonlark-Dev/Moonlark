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
from typing import Any, Literal

import httpx
from nonebot_plugin_alconna import UniMessage, Alconna, on_alconna, Args
from nonebot import on_command
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
from nonebot_plugin_render import render_template, generate_render_keys

matcher = on_alconna(Alconna("ba-calendar", Args["server", Literal["in", "jp", "cn"], "cn"]), aliases={"bac"})
lang = LangHelper()

async def get_image(uri: str) -> str:
    async with httpx.AsyncClient() as client:
        req = await client.get(
            f"https:{uri}",
            headers={
                "Referer": "https://www.gamekee.com/"
            }
        )
    return f"data:image/png;base64,{base64.b64encode(req.content).decode()}"


async def get_card_pool_data(server_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        req = await client.get(
            f"https://www.gamekee.com/v1/cardPool/query-list?order_by=-1&card_tag_id=&keyword=&kind_id=6&status=0&serverId={server_id}",
            headers={"game-alias": "ba"},
        )
    # Fetch all images
    data = req.json()
    for i in range(len(data["data"])):
        data["data"][i]["icon"] = await get_image(data["data"][i]["icon"])
    return data


async def get_activities(server_id: int, expected_ids: list[int] = []) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        req = await client.get(
            f"https://www.gamekee.com/v1/activity/page-list?importance=0&sort=-1&keyword=&limit=999&page_no=1&serverId={server_id}&status=0",
            headers={"game-alias": "ba"},
        )
    # Fetch all images
    data = req.json()
    result = []
    for item in data["data"]:
        if item["id"] not in expected_ids:
            item["picture"] = await get_image(item["picture"])
            result.append(item)
    return result[::-1]


async def get_total_assault_data(server_id: int) -> list[dict[str, Any]]:
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
            item["picture"] = await get_image(item["picture"])
            result.append(item)
    return result[::-1]


@matcher.handle()
async def _(server: Literal["in", "jp", "cn"], user_id: str = get_user_id()) -> None:
    server_id = {"in": 17, "jp": 15, "cn": 16}[server]
    total_assault_data = await get_total_assault_data(server_id)
    await UniMessage().image(
        raw=await render_template(
            "ba_calendar.html.jinja",
            await lang.text("title", user_id),
            user_id,
            {
                "total_assault": total_assault_data,
                "card_pool": (await get_card_pool_data(server_id))["data"][::-1],
                "activities": await get_activities(server_id, [i["id"] for i in total_assault_data]),
                "current_time": datetime.now().timestamp(),
                
                "server_id": server_id,
                "len": len,
                "round": round,
            },
            await generate_render_keys(
                lang,
                user_id,
                [
                    f"template.{k}"
                    for k in [
                        "pool_title",
                        "coming_pool",
                        "current_up",
                        "activity_title",
                        "ongoing",
                        "day",
                        "a_remain",
                        "coming_activity",
                        "a_coming_remain",
                        "server_cn",
                        "server_jp",
                        "server_in",
                        "up_after",
                        "up_remain",
                        "total_assault",
                        "total_assault_ongoing",
                        "total_assault_soon",
                    ]
                ],
            ),
        )
    ).send()
    await matcher.finish()
