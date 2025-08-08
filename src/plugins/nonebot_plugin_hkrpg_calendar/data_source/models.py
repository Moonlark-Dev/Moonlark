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

from pydantic import BaseModel, BeforeValidator, Field
from datetime import datetime
from typing import Annotated, Optional
import re


def parse_datetime(value: str) -> Optional[datetime]:
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", value):
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return None


class TakumiAPITimeInfo(BaseModel):
    start_time: Annotated[Optional[datetime], BeforeValidator(parse_datetime)]
    end_time: Annotated[Optional[datetime], BeforeValidator(parse_datetime)]


class CardPoolCharacter(BaseModel):
    item_name: str
    icon_url: str
    rarity: str


class CardPoolEquipment(BaseModel):
    item_name: str
    item_url: str
    rarity: str


class CardPool(BaseModel):
    name: str
    is_after_version: bool
    time_info: TakumiAPITimeInfo
    version: str


class CharacterCardPool(CardPool):
    avatar_list: list[CardPoolCharacter]


class EquipmentCardPool(CardPool):
    equip_list: list[CardPoolEquipment]


class TakumiAPIActItem(BaseModel):
    version: Annotated[float, BeforeValidator(lambda target: float(target))]
    name: str
    time_info: TakumiAPITimeInfo
    panel_desc: str


class TakumiAPIData(BaseModel):
    avatar_card_pool_list: list[CharacterCardPool]
    equip_card_pool_list: list[EquipmentCardPool]
    act_list: list[TakumiAPIActItem]
    cur_game_version: Annotated[float, BeforeValidator(lambda target: float(target))]


class TakumiAPIResponse(BaseModel):
    retcode: int
    message: str
    data: TakumiAPIData


class BiliGameEventInfo(BaseModel):
    """活动信息模型"""

    version: float
    event_name: str
    event_type: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    image_url: Optional[str] = None
