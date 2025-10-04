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

import json
from pydantic import BaseModel, BeforeValidator, Field
from datetime import datetime
from typing import Annotated, Optional
import re
from nonebot.compat import type_validate_json


def parse_datetime(value: str) -> Optional[datetime]:
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", value):
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return None


def parse_character_url(value: str) -> str:
    return f"https://act-api-takumi-static.mihoyo.com/common/blackboard/sr_wiki/v1/content/info?app_sn=sr_wiki&content_id={value[39:-40]}"


class GachaPoolCharacter(BaseModel):
    icon: str
    url: Annotated[str, BeforeValidator(parse_character_url)]


class GachaPoolList(BaseModel):
    title: str
    content_before_act: str
    start_time: Annotated[Optional[datetime], BeforeValidator(parse_datetime)]
    end_time: Annotated[Optional[datetime], BeforeValidator(parse_datetime)]
    pool: list[GachaPoolCharacter]


class GachaPoolData(BaseModel):
    list: list[GachaPoolList]


class GachaPoolResponse(BaseModel):
    data: GachaPoolData


def get_rarity(value: str) -> int:
    data = json.loads(value)
    k = "c_18"
    for key_name in data.keys():
        if key_name.startswith("c_"):
            k = key_name
            break
    if "星级/五星" in json.loads(data[k]["filter"]["text"]):
        return 5
    return 4


class SrWikiCharacter(BaseModel):
    title: str
    ext: Annotated[int, BeforeValidator(get_rarity)]


class SrWikiContentData(BaseModel):
    content: SrWikiCharacter


class SrWikiContentResponse(BaseModel):
    data: SrWikiContentData


class CardPoolCharacter(BaseModel):
    icon: str
    url: str
    data: SrWikiCharacter
    rarity: int


class CardPoolList(BaseModel):
    title: str
    content_before_act: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    pool: list[CardPoolCharacter]


class CardPoolData(BaseModel):
    list: list[CardPoolList]


class CardPoolResponse(BaseModel):
    data: CardPoolData


class BiliGameEventInfo(BaseModel):
    """活动信息模型"""

    version: float
    event_name: str
    event_type: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    image_url: Optional[str] = None
