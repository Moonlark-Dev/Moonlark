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
from nonebot.compat import type_validate_json
import httpx

from .models import (
    CardPoolCharacter,
    CardPoolData,
    CardPoolList,
    GachaPoolResponse,
    CardPoolResponse,
    SrWikiContentResponse,
)


async def request_character_data(url: str) -> SrWikiContentResponse:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            try:
                data = type_validate_json(SrWikiContentResponse, response.text)
                return data
            except pydantic.ValidationError as e:
                logger.error(f"Error parsing sr wiki data: {e}")
                raise e
    raise SystemError("Error fetching sr wiki data")


async def request_sr_wiki() -> Optional[CardPoolResponse]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://act-api-takumi.mihoyo.com/common/blackboard/sr_wiki/v1/gacha_pool?app_sn=sr_wiki"
        )
    if response.status_code == 200:
        try:
            gacha_response = type_validate_json(GachaPoolResponse, response.text)
        except pydantic.ValidationError as e:
            logger.exception(e)
            return None
    else:
        logger.warning(f"请求米游社 API 失败 ({response.status_code}): {response.text}")
        return None

    return CardPoolResponse(
        data=CardPoolData(
            list=[
                CardPoolList(
                    title=pool.title,
                    start_time=pool.start_time,
                    end_time=pool.end_time,
                    content_before_act=pool.content_before_act,
                    pool=[
                        CardPoolCharacter(
                            icon=c.icon,
                            url=c.url,
                            data=(d := (await request_character_data(c.url)).data.content),
                            rarity=d.ext,
                        )
                        for c in pool.pool
                    ],
                )
                for pool in gacha_response.data.list
            ]
        )
    )
