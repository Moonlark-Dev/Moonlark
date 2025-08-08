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
from typing import Optional

import pydantic
from nonebot.log import logger
from nonebot_plugin_localstore import get_config_file
from nonebot.compat import type_validate_json
import httpx
import aiofiles

from .models import TakumiAPIResponse

# 需要在开启前配置这些内容，否则无法请求。
headers_file = get_config_file("nonebot_plugin_hkrpg_calendar", "headers.txt")
role_id_file = get_config_file("nonebot_plugin_hkrpg_calendar", "role_id.txt")

async def get_role_id() -> str:
    async with aiofiles.open(role_id_file, "r", encoding="utf-8") as f:
        return await f.readline()

async def get_headers() -> dict[str, str]:
    async with aiofiles.open(headers_file, encoding="utf-8") as f:
        text = await f.read()
    headers = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        colon_index = line.find(':')
        if colon_index != -1:
            key = line[:colon_index].strip()
            value = line[colon_index + 1:].strip()
            headers[key] = value
    return headers


async def request_takumi_api() -> Optional[TakumiAPIResponse]:
    headers = await get_headers()
    role_id = await get_role_id()
    async with httpx.AsyncClient(headers=headers) as client:
        response = await client.get(f"https://api-takumi-record.mihoyo.com/game_record/app/hkrpg/api/get_act_calender?server=prod_gf_cn&role_id={role_id}")
    if response.status_code == 200:
        try:
            return type_validate_json(TakumiAPIResponse, response.text)
        except pydantic.ValidationError as e:
            logger.exception(e)
    logger.warning(f"请求米游社 API 失败 ({response.status_code}): {response.text}")
    return None

